"""Google Gemini text-to-speech.

Replaces the DashScope-backed CosyVoice / Qwen3-TTS paths. This is not a
preference — probing BytePlus Ark on 2026-09-08 (`GET /api/v3/models`) found
no TTS model among its 43 live entries, so with only Gemini and Ark
credentials available, Gemini is the sole option for dubbing.

Two things differ from the CosyVoice contract and are handled here:

* Gemini returns **raw PCM** (`audio/l16; rate=24000; channels=1`), not an
  encoded file. Without a RIFF header nothing downstream can play it, and the
  failure would only surface during video assembly, so we wrap it here.
* There is no numeric speed/pitch/volume control. Style is steered with
  natural language in the prompt, so `instructions` becomes a directive line
  and a non-default `speech_rate` becomes a worded hint. Pitch and volume have
  no honest equivalent and are ignored — see `UNSUPPORTED_CONTROLS`.

Voice genders below are NOT from Google, which publishes only a one-word
characteristic per voice. They come from a human listening pass over all 30
voices speaking the same gender-neutral Chinese line, because the migration of
existing character bindings must never flip a character's gender.
"""
import base64
import logging
import os
import struct
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import yaml

from ..utils.endpoints import get_provider_base_url

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = "gemini-3.1-flash-tts-preview"
DEFAULT_VOICE = "Kore"

SAMPLE_RATE = 24000
CHANNELS = 1
BITS_PER_SAMPLE = 16

# Controls the old CosyVoice path accepted that Gemini cannot honour. Listed
# explicitly so the UI can hide them instead of showing sliders that do nothing.
UNSUPPORTED_CONTROLS = ("pitch_rate", "volume")

_REQUEST_TIMEOUT = 300
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2.0
# 429 限流与 5xx 是会自愈的；4xx 的其余状态是请求本身的问题，重试无意义。
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# voice_key -> metadata. Shape mirrors the retired TTS_VOICE_REGISTRY so
# audio.py's get_available_voices() keeps working unchanged.
# `trait` is Google's own word; the Chinese gloss and `gender` are ours.
GEMINI_VOICES: Dict[str, Dict[str, str]] = {
    "Zephyr":        {"name": "Zephyr · 泽菲尔 (明亮女)",      "gender": "Female", "trait": "Bright"},
    "Puck":          {"name": "Puck · 帕克 (阳光男)",          "gender": "Male",   "trait": "Upbeat"},
    "Charon":        {"name": "Charon · 卡戎 (博学男)",        "gender": "Male",   "trait": "Informative"},
    "Kore":          {"name": "Kore · 科瑞 (知性女)",          "gender": "Female", "trait": "Firm"},
    "Fenrir":        {"name": "Fenrir · 芬里尔 (雀跃女)",      "gender": "Female", "trait": "Excitable"},
    "Leda":          {"name": "Leda · 勒达 (少女音)",          "gender": "Female", "trait": "Youthful"},
    "Orus":          {"name": "Orus · 俄鲁斯 (沉稳男)",        "gender": "Male",   "trait": "Firm"},
    "Aoede":         {"name": "Aoede · 阿俄德 (轻快女)",       "gender": "Female", "trait": "Breezy"},
    "Callirrhoe":    {"name": "Callirrhoe · 卡利罗 (随和女)",  "gender": "Female", "trait": "Easy-going"},
    "Autonoe":       {"name": "Autonoe · 奥托诺 (清亮女)",     "gender": "Female", "trait": "Bright"},
    "Enceladus":     {"name": "Enceladus · 恩克拉多 (气声男)", "gender": "Male",   "trait": "Breathy"},
    "Iapetus":       {"name": "Iapetus · 伊阿珀托 (清晰男)",   "gender": "Male",   "trait": "Clear"},
    "Umbriel":       {"name": "Umbriel · 天卫二 (随和男)",     "gender": "Male",   "trait": "Easy-going"},
    "Algieba":       {"name": "Algieba · 轩辕十二 (深情男)",   "gender": "Male",   "trait": "Smooth"},
    "Despina":       {"name": "Despina · 得斯庇娜 (柔顺女)",   "gender": "Female", "trait": "Smooth"},
    "Erinome":       {"name": "Erinome · 厄里诺墨 (清晰女)",   "gender": "Female", "trait": "Clear"},
    "Algenib":       {"name": "Algenib · 壁宿一 (低音男)",     "gender": "Male",   "trait": "Gravelly"},
    "Rasalgethi":    {"name": "Rasalgethi · 帝座 (讲述男)",    "gender": "Male",   "trait": "Informative"},
    "Laomedeia":     {"name": "Laomedeia · 拉俄墨得 (欢快女)", "gender": "Female", "trait": "Upbeat"},
    "Achernar":      {"name": "Achernar · 水委一 (柔和女)",    "gender": "Female", "trait": "Soft"},
    "Alnilam":       {"name": "Alnilam · 参宿二 (坚定男)",     "gender": "Male",   "trait": "Firm"},
    "Schedar":       {"name": "Schedar · 王良四 (平稳男)",     "gender": "Male",   "trait": "Even"},
    "Gacrux":        {"name": "Gacrux · 十字架一 (成熟女)",    "gender": "Female", "trait": "Mature"},
    "Pulcherrima":   {"name": "Pulcherrima · 普尔切 (进取男)", "gender": "Male",   "trait": "Forward"},
    "Achird":        {"name": "Achird · 王良三 (暖心男)",      "gender": "Male",   "trait": "Friendly"},
    "Zubenelgenubi": {"name": "Zubenelgenubi · 氐宿一 (随性男)", "gender": "Male", "trait": "Casual"},
    "Vindemiatrix":  {"name": "Vindemiatrix · 东次将 (温柔女)", "gender": "Female", "trait": "Gentle"},
    "Sadachbia":     {"name": "Sadachbia · 危宿一 (活泼男)",   "gender": "Male",   "trait": "Lively"},
    "Sadaltager":    {"name": "Sadaltager · 虚宿一 (睿智男)",  "gender": "Male",   "trait": "Knowledgeable"},
    "Sulafat":       {"name": "Sulafat · 织女二 (温暖女)",     "gender": "Female", "trait": "Warm"},
}

# audio.py reads `model_id` and `model`; fill them from the key so callers that
# round-trip a voice through the registry keep working.
for _key, _meta in GEMINI_VOICES.items():
    _meta["model_id"] = _key
    _meta["model"] = DEFAULT_TTS_MODEL
    _meta["family"] = "gemini"
    _meta["supports_instruction"] = True

_VOICE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "voice_migration.yaml"
)
_migration_cache: Optional[Dict[str, str]] = None


def load_voice_migration() -> Dict[str, str]:
    """Legacy CosyVoice voice_id -> Gemini voice name.

    Read once and cached. Missing file yields an empty map rather than an
    error: a fresh install has no legacy bindings to migrate.
    """
    global _migration_cache
    if _migration_cache is None:
        try:
            raw = yaml.safe_load(_VOICE_MIGRATION_PATH.read_text(encoding="utf-8")) or {}
            _migration_cache = dict(raw.get("mappings") or {})
        except FileNotFoundError:
            logger.warning("voice_migration.yaml not found; legacy voice ids will fall back")
            _migration_cache = {}
    return _migration_cache


def resolve_voice(voice: Optional[str]) -> str:
    """Map any incoming voice id onto a real Gemini voice.

    Order: already-valid name -> legacy migration table -> default. Falling
    back beats sending an unknown name and taking a 400 mid-render; the
    migration pass rewrites project files so this path should be rare.
    """
    name = (voice or "").strip()
    if name in GEMINI_VOICES:
        return name
    migrated = load_voice_migration().get(name)
    if migrated in GEMINI_VOICES:
        logger.info("Migrated legacy voice %s -> %s", name, migrated)
        return migrated
    if name:
        logger.warning("Unknown voice %r; falling back to %s", name, DEFAULT_VOICE)
    return DEFAULT_VOICE


def pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE, channels: int = CHANNELS,
               bits: int = BITS_PER_SAMPLE) -> bytes:
    """Wrap raw PCM in a 44-byte RIFF/WAVE header."""
    byte_rate = rate * channels * bits // 8
    block_align = channels * bits // 8
    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, rate, byte_rate, block_align, bits)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


def _speech_rate_hint(speech_rate: float) -> str:
    """Turn a numeric rate into words, since Gemini takes no rate parameter.

    Returns "" at the default so ordinary lines are sent verbatim — an
    unnecessary directive is itself a prompt the model may act on.
    """
    if speech_rate >= 1.35:
        return "语速明显加快"
    if speech_rate > 1.05:
        return "语速稍快"
    if speech_rate <= 0.7:
        return "语速明显放慢"
    if speech_rate < 0.95:
        return "语速稍慢"
    return ""


def _build_text(text: str, instructions: Optional[str], speech_rate: float) -> str:
    directives = [d for d in (instructions or "").strip().splitlines() if d.strip()]
    hint = _speech_rate_hint(speech_rate)
    if hint:
        directives.append(hint)
    if not directives:
        return text
    return "；".join(directives) + "：\n" + text


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Gemini TTS requires GEMINI_API_KEY. "
            "Set it in .env or in the in-app API configuration."
        )
    return key


def _extract_audio(payload: dict) -> bytes:
    """Pull PCM bytes out of the response, or explain why there are none.

    A text-only reply means the model refused (safety filter, unsupported
    input). Writing a headerless empty file instead would only fail later,
    during audio mixing, with no trace of the real cause.
    """
    texts = []
    for candidate in payload.get("candidates") or []:
        for part in (candidate.get("content", {}) or {}).get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
            if part.get("text"):
                texts.append(part["text"])
    detail = " ".join(texts).strip()
    raise RuntimeError(
        f"Gemini returned no audio. Model said: {detail}" if detail
        else "Gemini returned no audio and gave no reason."
    )


def _post_with_retry(url: str, key: str, body: dict) -> dict:
    """POST with bounded retry on transient failures.

    Dubbing an episode is dozens to hundreds of consecutive calls, so a single
    dropped connection would otherwise abort the whole batch — and a
    ConnectionReset from this endpoint has been observed in practice, it is not
    a hypothetical. Deterministic failures (bad request, bad key, unknown
    model) are raised immediately: retrying them only burns time and quota.
    """
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
    last_error: Optional[str] = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = requests.post(url, headers=headers, json=body,
                                     timeout=_REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            last_error = f"{type(e).__name__}: {e}"
        else:
            if response.ok:
                return response.json()
            if response.status_code not in _RETRYABLE_STATUS:
                raise RuntimeError(
                    f"Gemini TTS API error {response.status_code}: {response.text[:500]}"
                )
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"

        if attempt < _MAX_ATTEMPTS - 1:
            delay = _RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("Gemini TTS transient failure (%s); retry %d/%d in %.1fs",
                           last_error, attempt + 1, _MAX_ATTEMPTS - 1, delay)
            time.sleep(delay)

    raise RuntimeError(f"Gemini TTS failed after {_MAX_ATTEMPTS} attempts. {last_error}")


def synthesize_gemini(
    text: str,
    output_path: str,
    voice: Optional[str] = None,
    speech_rate: float = 1.0,
    instructions: Optional[str] = None,
    model_override: Optional[str] = None,
    **_ignored,
) -> Tuple[str, float, str]:
    """Synthesize `text` to a WAV file.

    Returns ``(output_path, first_package_delay_ms, request_id)`` to match the
    signature `TTSProcessor.synthesize` has always returned. Gemini is a
    non-streaming call, so the delay is reported as the full round-trip.
    """
    start = time.time()
    key = _api_key()
    used_voice = resolve_voice(voice)
    used_model = model_override or DEFAULT_TTS_MODEL

    base = get_provider_base_url("GEMINI")
    url = f"{base}/v1beta/models/{used_model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": _build_text(text, instructions, speech_rate)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": used_voice}}
            },
        },
    }
    payload = _post_with_retry(url, key, body)
    wav = pcm_to_wav(_extract_audio(payload))

    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(wav)

    elapsed_ms = (time.time() - start) * 1000
    return output_path, elapsed_ms, payload.get("responseId", "")
