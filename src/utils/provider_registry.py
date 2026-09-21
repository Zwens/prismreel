import os
from dataclasses import dataclass, field, replace
from typing import Dict, Mapping, Optional, Sequence, Tuple

from .model_catalog import build_provider_family_configs, load_generated_model_catalog

# DashScope 已随迁移整体下线；保留在这里会让一个失效的 backend 通过校验。
SUPPORTED_PROVIDER_BACKENDS = ("vendor", "byteplus", "google")


@dataclass
class ProviderFamilyConfig:
    model_family: str
    backend_default: str = "vendor"
    backend_env_key: Optional[str] = None
    credential_sources: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    supported_modalities: Tuple[str, ...] = field(default_factory=tuple)
    image_input_mode: Dict[str, str] = field(default_factory=dict)
    audio_input_mode: Dict[str, str] = field(default_factory=dict)
    reference_video_input_mode: Dict[str, str] = field(default_factory=dict)


class ProviderRegistry:
    """Data-driven provider routing registry keyed by model family prefix."""

    def __init__(self, families: Optional[Sequence[ProviderFamilyConfig]] = None):
        self._families: Dict[str, ProviderFamilyConfig] = {}
        for family in families or ():
            self.register_family(family)

    def register_family(self, config: ProviderFamilyConfig) -> None:
        family = (config.model_family or "").strip().lower()
        if not family:
            raise ValueError("model_family cannot be empty")
        backend_default = (config.backend_default or "").strip().lower()
        if backend_default not in SUPPORTED_PROVIDER_BACKENDS:
            raise ValueError(f"Unsupported backend_default: {config.backend_default}")
        self._families[family] = replace(
            config,
            model_family=family,
            backend_default=backend_default,
        )

    def get_family_config(self, model_name: str) -> ProviderFamilyConfig:
        normalized = (model_name or "").strip().lower()
        if not normalized:
            raise ValueError("model_name cannot be empty")

        for family in sorted(self._families.keys(), key=len, reverse=True):
            if normalized.startswith(family):
                return self._families[family]
        raise KeyError(f"No provider family registered for model '{model_name}'")

    def resolve_backend(self, model_name: str, env: Optional[Mapping[str, str]] = None) -> str:
        family = self.get_family_config(model_name)
        mode = ""
        if family.backend_env_key:
            env_mapping = env if env is not None else os.environ
            mode = (env_mapping.get(family.backend_env_key) or "").strip().lower()

        if mode in SUPPORTED_PROVIDER_BACKENDS:
            return mode
        return family.backend_default


DEFAULT_PROVIDER_FAMILIES: Tuple[ProviderFamilyConfig, ...] = (
    # 仅在生成目录加载失败时兜底。DashScope 下线后 wan / qwen-image /
    # happyhorse / pixverse 四个家族已删除，这里同步移除。
    ProviderFamilyConfig(
        model_family="gemini-",
        backend_default="google",
        credential_sources={"google": ("GEMINI_API_KEY",)},
        supported_modalities=("t2i", "i2i"),
        image_input_mode={"google": "gemini_inline_base64"},
        audio_input_mode={},
        reference_video_input_mode={},
    ),
    ProviderFamilyConfig(
        model_family="seedance",
        backend_default="byteplus",
        credential_sources={"byteplus": ("ARK_API_KEY",)},
        supported_modalities=("t2v", "i2v", "r2v", "v2v"),
        image_input_mode={"byteplus": "byteplus_ark_image_url"},
        audio_input_mode={},
        reference_video_input_mode={"byteplus": "byteplus_ark_video_url"},
    ),
    ProviderFamilyConfig(
        model_family="kling",
        backend_default="vendor",
        credential_sources={"vendor": ("KLING_ACCESS_KEY", "KLING_SECRET_KEY")},
        supported_modalities=("t2v", "i2v", "r2v"),
        image_input_mode={"vendor": "kling_vendor_base64_image"},
        audio_input_mode={"vendor": "kling_vendor_audio_url"},
        reference_video_input_mode={"vendor": "kling_vendor_video_url"},
    ),
    ProviderFamilyConfig(
        model_family="vidu",
        backend_default="vendor",
        credential_sources={"vendor": ("VIDU_API_KEY",)},
        supported_modalities=("t2v", "i2v", "r2v", "t2i", "i2i"),
        image_input_mode={"vendor": "vidu_vendor_image_url"},
        audio_input_mode={"vendor": "vidu_vendor_audio_url"},
        reference_video_input_mode={"vendor": "vidu_vendor_video_url"},
    ),
    ProviderFamilyConfig(
        model_family="deevid",
        backend_default="vendor",
        credential_sources={"vendor": ("DEEVID_API_KEY",)},
        supported_modalities=("i2v",),
        image_input_mode={"vendor": "deevid_vendor_image_url"},
        audio_input_mode={},
        reference_video_input_mode={},
    ),
)


def get_default_provider_registry() -> ProviderRegistry:
    try:
        catalog = load_generated_model_catalog()
        return ProviderRegistry(build_provider_family_configs(catalog))
    except Exception:
        return ProviderRegistry(DEFAULT_PROVIDER_FAMILIES)


def resolve_provider_backend(model_name: str, env: Optional[Mapping[str, str]] = None) -> str:
    return get_default_provider_registry().resolve_backend(model_name=model_name, env=env)


# ---------------------------------------------------------------------------
# Phase 2: Gateway metadata inspection (read-only, no routing changes)
# ---------------------------------------------------------------------------

def get_gateway_for_model(
    model_id: str,
    backend: Optional[str] = None,
) -> Optional[str]:
    """Inspect the gateway metadata for a model (flat or canonical ID).

    This is a read-only diagnostic helper.  It does NOT change routing
    behavior — current routing remains family-prefix based.
    """
    from .model_catalog import get_catalog_accessor

    accessor = get_catalog_accessor()
    canonical_id = accessor.resolve_legacy_to_canonical(model_id)
    if canonical_id is None:
        canonical_id = model_id  # already canonical or unknown

    # 不再硬编码兜底 backend —— DashScope 下线后没有一个「大多数模型都用」的
    # 默认值可写死。按模型所属家族解析，解析不出就不猜。
    if backend:
        resolved_backend = backend
    else:
        try:
            resolved_backend = resolve_provider_backend(model_id)
        except (KeyError, ValueError):
            return None
    return accessor.get_gateway(canonical_id, resolved_backend)
