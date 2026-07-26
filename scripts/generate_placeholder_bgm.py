"""Generate recognisable placeholder BGM so the render chain can be verified.

These are NOT shippable music. Each preset gets a distinct chord and tempo so
you can tell by ear which one a render picked up. Replace with licensed audio
before any external release — see output/presets/bgm/LICENSES.md.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.apps.comic_gen.audio import BGM_PRESETS  # noqa: E402
from src.utils.system_check import get_ffmpeg_path  # noqa: E402

# (root_hz, third_hz, fifth_hz, tremolo_hz) — distinct per preset by ear.
_VOICINGS = {
    "calm_warm": (261.63, 329.63, 392.00, 0.4),
    "uplifting_pop": (329.63, 415.30, 493.88, 2.0),
    "epic_cinematic": (130.81, 164.81, 196.00, 0.8),
    "mystery_ambient": (146.83, 174.61, 220.00, 0.25),
    "sad_piano": (220.00, 261.63, 329.63, 0.5),
    "tension_drama": (110.00, 138.59, 155.56, 3.0),
    "lofi_chill": (196.00, 233.08, 293.66, 1.2),
    "fantasy_dreamy": (293.66, 369.99, 440.00, 0.6),
}

DURATION_S = 60
OUT_DIR = os.path.join("output", "presets", "bgm")


def main() -> int:
    ff = get_ffmpeg_path()
    if not ff:
        print("ffmpeg not found — cannot generate placeholders")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    for preset in BGM_PRESETS:
        pid = preset["id"]
        root, third, fifth, trem = _VOICINGS[pid]
        out = os.path.join(OUT_DIR, os.path.basename(preset["url"]))

        graph = (
            f"sine=frequency={root}:duration={DURATION_S}[a];"
            f"sine=frequency={third}:duration={DURATION_S}[b];"
            f"sine=frequency={fifth}:duration={DURATION_S}[c];"
            f"[a][b][c]amix=inputs=3:duration=longest,"
            f"tremolo=f={trem}:d=0.6,"
            f"volume=0.25,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={DURATION_S - 2}:d=2[out]"
        )
        cmd = [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={DURATION_S}",
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            out,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        print(f"  {os.path.basename(out)}  ({root:.0f}/{third:.0f}/{fifth:.0f} Hz, trem {trem})")

    print(f"\nGenerated {len(BGM_PRESETS)} placeholder tracks in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
