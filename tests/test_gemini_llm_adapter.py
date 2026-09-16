"""LLM 必须走 Google Gemini 直连，而不是已下线的 DashScope。

DashScope 被整体移除后，`DASHSCOPE_API_KEY` 不再存在于任何配置里。若
`LLMAdapter` 仍把 dashscope 当默认 provider，剧本生成、分镜拆解、提示词润色
三条链路会在 `is_configured` 这一关就判定为未配置，用户拿到的是
「LLM 未配置」而不是任何可操作的提示。

Gemini 提供 OpenAI 兼容层（`/v1beta/openai/`），所以复用现有的 OpenAI 客户端
即可，无需新 SDK —— 但 base_url 必须拼对，拼错会得到 404 而非鉴权错误，
两者的排查成本差很多。
"""

import pytest

from src.apps.comic_gen.llm_adapter import LLMAdapter
from src.utils.endpoints import get_provider_base_url


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    """每个用例从干净的供应商环境开始，避免开发机 .env 泄漏进断言。"""
    for key in (
        "LLM_PROVIDER",
        "GEMINI_API_KEY",
        "GEMINI_BASE_URL",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


class TestProviderDefault:
    def test_default_provider_is_gemini(self):
        assert LLMAdapter().provider == "gemini"

    def test_openai_provider_still_selectable(self, monkeypatch):
        # 第三方 OpenAI 兼容通道（DeepSeek / Ollama 等）不在本次移除范围内。
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        assert LLMAdapter().provider == "openai"


class TestLegacyProviderNormalisation:
    """改默认值不足以完成迁移：`.env.example` 长期教用户显式写
    `LLM_PROVIDER=dashscope`，所以每个既有安装的 .env 里都钉着这一行。仅改默认
    值时它们会绕过新默认、把 provider 标成 dashscope —— 客户端其实已经指向
    Gemini，但日志和错误标签都在说谎，下一个在这里加 elif 分支的人就会踩坑。"""

    def test_legacy_dashscope_value_is_normalised_to_gemini(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "dashscope")
        assert LLMAdapter().provider == "gemini"

    def test_legacy_value_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "DashScope")
        assert LLMAdapter().provider == "gemini"

    def test_legacy_value_warns_so_the_stale_line_gets_cleaned_up(self, monkeypatch, caplog):
        monkeypatch.setenv("LLM_PROVIDER", "dashscope")
        with caplog.at_level("WARNING"):
            LLMAdapter()
        assert any("dashscope" in r.message.lower() for r in caplog.records), \
            "静默改写会让用户永远不知道该删掉这行"

    def test_unknown_value_falls_back_to_gemini(self, monkeypatch):
        # 拼错的值不该悄悄变成「非 openai 即 Gemini」的隐式行为，显式落到 gemini。
        monkeypatch.setenv("LLM_PROVIDER", "qwen")
        assert LLMAdapter().provider == "gemini"

    def test_empty_value_falls_back_to_gemini(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "")
        assert LLMAdapter().provider == "gemini"


class TestIsConfigured:
    def test_gemini_key_makes_it_configured(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-live-key")
        assert LLMAdapter().is_configured is True

    def test_missing_gemini_key_is_not_configured(self):
        assert LLMAdapter().is_configured is False

    def test_dashscope_key_no_longer_counts(self, monkeypatch):
        # 迁移的核心断言：残留的 DashScope key 不得再让适配器自称已配置，
        # 否则调用会一路走到 API 层才失败。
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-leftover-dashscope")
        assert LLMAdapter().is_configured is False

    def test_openai_branch_checks_its_own_key(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        assert LLMAdapter().is_configured is True


class TestClientWiring:
    def test_gemini_client_uses_openai_compat_base_url(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-live-key")

        client = LLMAdapter()._get_client()

        assert str(client.base_url).rstrip("/").endswith("/v1beta/openai")
        assert "generativelanguage.googleapis.com" in str(client.base_url)
        assert client.api_key == "gemini-live-key"

    def test_gemini_base_url_override_is_honoured(self, monkeypatch):
        # 留这个覆盖口是为了将来换中转地址时不必改代码。
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-live-key")
        monkeypatch.setenv("GEMINI_BASE_URL", "https://proxy.example.com")

        client = LLMAdapter()._get_client()

        assert str(client.base_url).startswith("https://proxy.example.com/v1beta/openai")

    def test_openai_client_untouched(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

        client = LLMAdapter()._get_client()

        assert str(client.base_url).startswith("https://api.deepseek.com/v1")


class TestDefaultModel:
    def test_default_model_is_a_stable_gemini_flash(self):
        assert LLMAdapter()._get_default_model() == "gemini-3.8-flash"

    def test_fallback_chain_holds_only_stable_ids(self):
        # gemini-2.0-* 与 gemini-3-pro-preview 已被 Google 标为弃用；把它们
        # 留在 fallback chain 里等于给自己埋一个将来必然失效的兜底。
        chain = LLMAdapter._GEMINI_MODEL_FALLBACK_CHAIN
        assert chain[0] == "gemini-3.8-flash"
        assert len(chain) >= 2, "单一型号没有兜底，型号下线即整条 LLM 链断掉"
        deprecated = {"gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-3-pro-preview"}
        assert not (set(chain) & deprecated)

    def test_openai_default_model_untouched(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        assert LLMAdapter()._get_default_model() == "gpt-4o"


class TestEndpointRegistry:
    def test_gemini_has_a_registered_default_endpoint(self):
        assert get_provider_base_url("GEMINI") == "https://generativelanguage.googleapis.com"

    # 注：`DASHSCOPE` 此刻仍留在 PROVIDER_DEFAULTS 中，因为 image.py / wanx.py
    # 尚未迁移，提前摘掉会让图像生成拿到空 base_url 而当场失效。它的移除断言
    # 属于迁移第 4 步（拔除 DashScope），与那批改动一起加。
