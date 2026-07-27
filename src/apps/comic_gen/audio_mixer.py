"""Audio filter graph construction for the final render.

Extracted from the inline filter string in pipeline._maybe_apply_bgm_mux so
the graph can be unit-tested without invoking ffmpeg, and extended with
sidechain ducking plus loudness normalisation.

Input convention (set by the caller's -i order):
    [0:a] = dialogue / original program audio of the concatenated video
    [1:a] = background music (only present when has_bgm is True)
Output label is always [aout].

The dialogue label is overridable via `dialogue_label` because the
concatenated video may have no audio stream at all — the generation
pipeline's default is Silent Mode — in which case the caller appends a
synthetic silent input and points the graph at it. Referencing [0:a]
unconditionally makes ffmpeg abort with "matches no streams" and takes the
BGM, the loudness normalisation and the subtitle burn down with it.
"""

# EBU R128 targets. -16 LUFS is the de-facto loudness for short-form
# vertical video platforms; -1.5 dBTP leaves headroom for lossy re-encode.
LOUDNORM_TARGET_I = -16.0
LOUDNORM_TARGET_TP = -1.5
LOUDNORM_TARGET_LRA = 11.0

# Ducking: fire early and release slowly so music dips before a line starts
# and recovers between lines instead of pumping on every syllable.
_DUCK_THRESHOLD = 0.05
_DUCK_RATIO = 8
_DUCK_ATTACK_MS = 20
_DUCK_RELEASE_MS = 300


def _level(pct: int) -> float:
    return max(0, min(100, int(pct))) / 100.0


def _loudnorm() -> str:
    return (
        f"loudnorm=I={LOUDNORM_TARGET_I}" f":TP={LOUDNORM_TARGET_TP}" f":LRA={LOUDNORM_TARGET_LRA}"
    )


def build_audio_filter(
    *,
    dialogue_level: int,
    bgm_level: int,
    has_bgm: bool,
    ducking: bool = True,
    normalize: bool = True,
    dialogue_label: str = "0:a",
) -> str:
    """Build the -filter_complex string for the final audio mix.

    Args:
        dialogue_level: 0-100 gain for the program audio.
        bgm_level: 0-100 gain for the background music.
        has_bgm: whether a second audio input [1:a] is present.
        ducking: sidechain-compress the music against the dialogue.
        normalize: apply EBU R128 loudness normalisation to the result.
        dialogue_label: ffmpeg stream specifier for the dialogue input.
            Defaults to the concatenated video's own audio; the caller
            overrides it when that video has no audio stream and a
            synthetic silent input was appended instead.

    Returns:
        A filter_complex string whose final output label is [aout].
    """
    dial = _level(dialogue_level)
    bgm = _level(bgm_level)
    dlg = f"[{dialogue_label}]"
    parts = []

    if not has_bgm:
        if normalize:
            parts.append(f"{dlg}volume={dial:.3f},apad,{_loudnorm()}[aout]")
        else:
            parts.append(f"{dlg}volume={dial:.3f},apad[aout]")
        return ";".join(parts)

    if ducking:
        # asplit is mandatory: the dialogue stream feeds both the mix and the
        # sidechain detector, and a filter output can only be consumed once.
        parts.append(f"{dlg}volume={dial:.3f},apad,asplit=2[dial_mix][dial_sc]")
        parts.append(f"[1:a]volume={bgm:.3f},aloop=loop=-1:size=2e9[bgm_raw]")
        parts.append(
            f"[bgm_raw][dial_sc]sidechaincompress="
            f"threshold={_DUCK_THRESHOLD}"
            f":ratio={_DUCK_RATIO}"
            f":attack={_DUCK_ATTACK_MS}"
            f":release={_DUCK_RELEASE_MS}[bgm_ducked]"
        )
        mix_inputs = "[dial_mix][bgm_ducked]"
    else:
        parts.append(f"{dlg}volume={dial:.3f},apad[dial_mix]")
        parts.append(f"[1:a]volume={bgm:.3f},aloop=loop=-1:size=2e9[bgm_ducked]")
        mix_inputs = "[dial_mix][bgm_ducked]"

    mix_out = "[aout]" if not normalize else "[mixed]"
    parts.append(f"{mix_inputs}amix=inputs=2:duration=first:dropout_transition=0{mix_out}")
    if normalize:
        parts.append(f"[mixed]{_loudnorm()}[aout]")

    return ";".join(parts)
