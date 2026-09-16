"""
Text-to-Speech (TTS) module using Google Gemini.
Converts text to speech audio for use in video lip-sync.

Replaces the DashScope CosyVoice / Qwen3-TTS implementation. That was not a
preference: probing BytePlus Ark on 2026-09-08 found no TTS model among its 43
live entries, so with Gemini and Ark as the only available platforms, Gemini
is the sole option for dubbing.

`TTSProcessor`'s public surface (`synthesize`, `list_voices`) is deliberately
unchanged so `pipeline.py` and the `/voices` and `/tts` endpoints keep working
without edits. The voice registry, the audio format, and the meaning of the
style parameters are what changed — see src/audio/gemini_tts.py.
"""
import logging
from typing import Optional, Tuple

from .gemini_tts import (
    DEFAULT_TTS_MODEL,
    DEFAULT_VOICE,
    GEMINI_VOICES,
    UNSUPPORTED_CONTROLS,
    resolve_voice,
    synthesize_gemini,
)

logger = logging.getLogger(__name__)


# Voice registry: key -> {model_id, name, gender, model, family, ...}
# Genders come from a human listening pass, not from Google — see gemini_tts.
VOICES = GEMINI_VOICES


class TTSProcessor:
    """Text-to-Speech processor using Gemini."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_TTS_MODEL,
        voice: str = DEFAULT_VOICE,
    ):
        """
        Initialize TTS processor

        Args:
            api_key: Unused; kept so existing call sites do not break. The key
                is read from GEMINI_API_KEY at request time, which also lets a
                key saved through the settings page take effect without a
                restart.
            model: TTS model name
            voice: Default voice ID
        """
        self.model = model
        self.voice = voice
        if api_key:
            logger.debug("TTSProcessor api_key argument is ignored; using GEMINI_API_KEY")
        logger.info(f"TTS Processor initialized with model={model}, voice={voice}")

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speech_rate: float = 1.0,
        pitch_rate: float = 1.0,
        volume: int = 50,
        instructions: Optional[str] = None,
        model_override: Optional[str] = None,
        family_override: Optional[str] = None,
    ) -> Tuple[str, float, str]:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            voice: Voice ID; legacy CosyVoice ids are migrated via
                config/voice_migration.yaml, unknown ids fall back to the default
            speech_rate: Rendered as a worded hint — Gemini takes no numeric
                rate. 1.0 sends the line verbatim.
            pitch_rate, volume: **Not supported by Gemini.** Accepted so call
                sites keep type-checking, but they do nothing; a warning is
                logged when they deviate from the default so the gap is visible
                rather than silently swallowed.
            instructions: Natural-language style directive, prepended to the
                line. This is Gemini's only style control.
            model_override: Force a specific TTS model.
            family_override: Unused; only one family remains.

        Returns:
            Tuple[str, float, str]: (output_path, first_package_delay_ms, request_id)
        """
        ignored = [
            name for name, value, default in
            (("pitch_rate", pitch_rate, 1.0), ("volume", volume, 50))
            if value != default
        ]
        if ignored:
            logger.warning(
                "Gemini TTS ignores %s (%s); style can only be steered via "
                "`instructions`.", ", ".join(ignored), ", ".join(UNSUPPORTED_CONTROLS),
            )

        return synthesize_gemini(
            text,
            output_path,
            voice=voice or self.voice,
            speech_rate=speech_rate,
            instructions=instructions,
            model_override=model_override,
        )

    def _voice_meta(self, voice_id: str) -> dict:
        """Return registry metadata for a voice_id."""
        return VOICES.get(resolve_voice(voice_id), {})

    def _resolve_model_for_voice(self, voice_id: str) -> str:
        """Resolve the model for a voice. All Gemini voices share one model."""
        return self._voice_meta(voice_id).get("model", self.model)

    def _resolve_family_for_voice(self, voice_id: str) -> str:
        """Only one family remains; kept for call-site compatibility."""
        return "gemini"

    def _voice_supports_instruction(self, voice_id: str) -> bool:
        """Every Gemini voice accepts a natural-language style directive."""
        return True

    @staticmethod
    def list_voices():
        """List available voices with metadata"""
        return VOICES
