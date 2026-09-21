def test_resolve_media_input_deevid_passthrough_url():
    from src.utils.provider_media import resolve_media_input
    from src.utils.provider_registry import ProviderRegistry, DEFAULT_PROVIDER_FAMILIES

    fallback_registry = ProviderRegistry(DEFAULT_PROVIDER_FAMILIES)
    resolved = resolve_media_input(
        "https://example.com/photo.png",
        model_name="deevid/quality-v4.0",
        modality="image",
        backend="vendor",
        uploader=None,
        registry=fallback_registry,
    )
    assert resolved.value == "https://example.com/photo.png"


def test_deevid_family_registered_in_default_provider_families():
    """驗證本任務新增的 DEFAULT_PROVIDER_FAMILIES deevid entry 本身正確——
    刻意繞開 get_default_provider_registry()，因為那個函式在 catalog JSON
    載入成功時會直接用 catalog 建 registry（不含 deevid，要到 Task 4 建立
    deevid.yaml 並重新生成 catalog 後才會有），不會走到這個 fallback tuple。
    這裡改為直接用 DEFAULT_PROVIDER_FAMILIES 建一個獨立 registry 來驗證
    entry 本身，讓本測試不依賴 Task 4 是否已完成。"""
    from src.utils.provider_registry import ProviderRegistry, DEFAULT_PROVIDER_FAMILIES

    registry = ProviderRegistry(DEFAULT_PROVIDER_FAMILIES)
    config = registry.get_family_config("deevid/quality-v4.0")
    assert config.model_family == "deevid"
