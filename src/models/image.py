"""Image generation: the shared abstraction plus provider routing.

The DashScope-backed `WanxImageModel` lived here until the migration removed
it, together with the DashScope-specific error explanations and connection
retry it needed. Concrete adapters now live in their own modules
(`gemini_image`, `vidu`) and are reached through `resolve_image_adapter`.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from ..utils import get_logger

logger = get_logger(__name__)


class ImageGenModel(ABC):
    """Abstract base class for image generation models."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def generate(self, prompt: str, output_path: str, **kwargs) -> Tuple[str, float]:
        """
        Generates an image from a prompt.

        Args:
            prompt: The input text prompt.
            output_path: The path to save the generated image.
            **kwargs: Additional arguments.

        Returns:
            A tuple containing:
            - The path to the generated image file.
            - The duration of the API generation process in seconds.
        """
        pass


# One adapter instance per provider, so HTTP connection pools are reused
# across the hundreds of images a single episode generates.
_IMAGE_ADAPTER_CACHE: Dict[str, ImageGenModel] = {}


def _image_provider_for(model_name: str) -> str:
    """Which provider serves this image model id, or '' for the default one."""
    name = (model_name or "").strip().lower()
    if not name:
        return ""
    if name.startswith("gemini-"):
        return "gemini"
    # Imported lazily: src.models.vidu imports ImageGenModel from this module.
    from .vidu import is_vidu_image_model
    if is_vidu_image_model(name):
        return "vidu"
    return ""


def resolve_image_adapter(model_name: str, default_adapter: ImageGenModel = None) -> ImageGenModel:
    """Route a catalog image model id to the adapter that can actually run it.

    Every image entry point (assets, storyboard, playground) shares this so a
    new image provider is one branch here instead of one branch per call site.
    Anything unrecognized falls through to ``default_adapter``, which callers
    now construct as :class:`GeminiImageModel`.
    """
    provider = _image_provider_for(model_name)
    if not provider:
        return default_adapter

    cached = _IMAGE_ADAPTER_CACHE.get(provider)
    if cached is not None:
        return cached

    if provider == "gemini":
        from .gemini_image import GeminiImageModel
        cached = GeminiImageModel({})
    elif provider == "vidu":
        from .vidu import ViduImageModel
        cached = ViduImageModel({})
    else:  # pragma: no cover - _image_provider_for returns "", "gemini" or "vidu"
        return default_adapter

    _IMAGE_ADAPTER_CACHE[provider] = cached
    return cached
