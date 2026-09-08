from src.utils.provider_registry import (
    ProviderFamilyConfig,
    ProviderRegistry,
    get_default_provider_registry,
    resolve_provider_backend,
)


class TestProviderRegistryRouting:
    def test_gemini_models_route_to_google(self):
        assert resolve_provider_backend("gemini-3.1-flash-image") == "google"

    def test_seedance_models_route_to_byteplus(self):
        assert resolve_provider_backend("seedance-2.5-i2v") == "byteplus"
        assert resolve_provider_backend("seedance-2.0-fast-r2v") == "byteplus"

    def test_kling_and_vidu_are_vendor_only_now(self):
        # DashScope 通道拔除后这两家只剩直连；曾经的 KLING_PROVIDER_MODE /
        # VIDU_PROVIDER_MODE 开关已随之移除，设什么都不该改变路由。
        assert resolve_provider_backend("kling-v3-i2v") == "vendor"
        assert resolve_provider_backend("viduq3-pro-i2v") == "vendor"
        assert resolve_provider_backend("kling-v3-i2v", env={"KLING_PROVIDER_MODE": "dashscope"}) == "vendor"
        assert resolve_provider_backend("viduq3-pro-i2v", env={"VIDU_PROVIDER_MODE": "dashscope"}) == "vendor"

    def test_retired_families_no_longer_resolve(self):
        # 已删家族不应还能解析出 backend —— 那意味着注册表里留了幽灵条目。
        import pytest as _pytest
        for gone in ("wan2.7-image-pro", "happyhorse-1.0-i2v", "pixverse-v4-i2v",
                     "qwen-image-2.0"):
            with _pytest.raises(KeyError):
                resolve_provider_backend(gone)

    def test_a_new_family_can_be_registered_without_resolver_changes(self):
        """路由解析器对家族是数据驱动的：新增供应商只该改数据，不该改代码。"""
        registry = ProviderRegistry()
        registry.register_family(
            ProviderFamilyConfig(
                model_family="someprovider-",
                backend_default="vendor",
                backend_env_key="SOMEPROVIDER_PROVIDER_MODE",
                credential_sources={
                    "vendor": ("SOMEPROVIDER_API_KEY",),
                    "byteplus": ("ARK_API_KEY",),
                },
                supported_modalities=("t2v", "i2v"),
                image_input_mode={"vendor": "someprovider_vendor_image_input"},
                audio_input_mode={},
                reference_video_input_mode={},
            )
        )

        assert registry.resolve_backend("someprovider-v1-i2v") == "vendor"
        assert (
            registry.resolve_backend(
                "someprovider-v1-i2v",
                env={"SOMEPROVIDER_PROVIDER_MODE": "byteplus"},
            )
            == "byteplus"
        )
