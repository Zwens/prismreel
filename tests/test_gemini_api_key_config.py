"""GEMINI_API_KEY must be settable through the settings API.

After the DashScope removal, Gemini backs the LLM (and later image + TTS), so
it is the key the app cannot run without. If `/config/env` does not know the
field, the settings page has nowhere to put it and the user is stuck with
"LLM 未配置" and no way to fix it — exactly the hole ARK_API_KEY had before.

It is a secret, so it has to round-trip like the other keys: masked on read,
and a re-submitted mask must not overwrite the stored value.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.apps.comic_gen import api

    # get_user_config_path() resolves the project root from __file__, so it
    # returns the REAL .env no matter what the cwd is — a save test would
    # otherwise write its fixture value into the developer's own config.
    monkeypatch.setattr(
        api, "get_user_config_path", lambda: str(tmp_path / ".env")
    )
    return TestClient(api.app)


def test_gemini_api_key_is_reported_by_the_config_endpoint(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-value")

    body = client.get("/config/env").json()

    assert "GEMINI_API_KEY" in body, "no field means no way to configure the LLM"


def test_gemini_api_key_is_masked_not_echoed(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-value")

    value = client.get("/config/env").json()["GEMINI_API_KEY"]

    assert "gemini-secret-value" not in value
    assert value != ""


def test_gemini_api_key_reports_configured_state(client, monkeypatch):
    # 前端靠 secrets_configured 驱动必填校验与就绪指示，缺了它 key 填了也显示未配置。
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-value")

    configured = client.get("/config/env").json()["secrets_configured"]

    assert configured["GEMINI_API_KEY"] is True


def test_unset_gemini_api_key_reads_back_empty(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    body = client.get("/config/env").json()

    assert body["GEMINI_API_KEY"] == ""
    assert body["secrets_configured"]["GEMINI_API_KEY"] is False


def test_gemini_base_url_override_is_surfaced(client, monkeypatch):
    # GEMINI 进了 PROVIDER_DEFAULTS，端点覆盖应自动随之出现，无需单独布线。
    monkeypatch.setenv("GEMINI_BASE_URL", "https://proxy.example.com")

    overrides = client.get("/config/env").json()["endpoint_overrides"]

    assert overrides["GEMINI_BASE_URL"] == "https://proxy.example.com"
