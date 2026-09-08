import os

# Provider endpoint registry: {provider_key: default_base_url}
PROVIDER_DEFAULTS = {
    "GEMINI": "https://generativelanguage.googleapis.com",
    # DASHSCOPE 正在下线：LLM 已切到 Gemini，图像侧（image.py / wanx.py）尚未
    # 迁移，仍需要这个地址。迁移收尾时一并删除。
    "DASHSCOPE": "https://dashscope.aliyuncs.com",
    "KLING": "https://api-beijing.klingai.com/v1",
    "VIDU": "https://api.vidu.cn/ent/v2",
}


def get_provider_base_url(provider: str, default: str = None) -> str:
    """Get base URL for a provider. Convention: reads {PROVIDER}_BASE_URL env var.

    Args:
        provider: Provider key, e.g. "KLING", "DASHSCOPE"
        default: Fallback URL if env var is not set. If None, looks up PROVIDER_DEFAULTS.
    """
    env_key = f"{provider.upper()}_BASE_URL"
    fallback = default or PROVIDER_DEFAULTS.get(provider.upper(), "")
    return (os.getenv(env_key) or fallback).rstrip("/")
