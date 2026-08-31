"""ARK_API_KEY must be settable through the settings API.

Seedance 2.5 runs on BytePlus / Volcano Ark and needs ARK_API_KEY, but the
config endpoint knew nothing about that variable — the model appeared in the
picker flagged "未配置密钥" with no field anywhere in the UI to configure it.

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
    # (It did, once; hence this redirect.)
    monkeypatch.setattr(
        api, "get_user_config_path", lambda: str(tmp_path / ".env")
    )
    return TestClient(api.app)


def test_ark_api_key_is_reported_by_the_config_endpoint(client, monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "ark-secret-value")

    body = client.get("/config/env").json()

    assert "ARK_API_KEY" in body, "no field means no way to configure Seedance 2.5"


def test_ark_api_key_is_masked_not_echoed(client, monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "ark-secret-value")

    value = client.get("/config/env").json()["ARK_API_KEY"]

    assert "ark-secret-value" not in value
    assert value != ""


def test_unset_ark_api_key_reads_as_empty(client, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    assert client.get("/config/env").json()["ARK_API_KEY"] == ""


def test_ark_api_key_can_be_saved(client, monkeypatch):
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    r = client.post("/config/env", json={"ARK_API_KEY": "ark-new-key"})

    assert r.status_code == 200, r.text
    import os
    assert os.environ.get("ARK_API_KEY") == "ark-new-key"


def test_resubmitting_the_mask_does_not_clobber_the_stored_key(client, monkeypatch):
    """The UI sends back whatever it was given; a masked value means unchanged."""
    monkeypatch.setenv("ARK_API_KEY", "ark-original")
    masked = client.get("/config/env").json()["ARK_API_KEY"]

    client.post("/config/env", json={"ARK_API_KEY": masked})

    import os
    assert os.environ.get("ARK_API_KEY") == "ark-original"
