import pytest
from fastapi import HTTPException


def test_get_owned_script_returns_script_for_owner(monkeypatch):
    from src.apps.comic_gen import api
    from src.apps.comic_gen.models import Script

    fake_script = Script(id="s1", title="t", original_text="x", owner_id="user-1", created_at=0.0, updated_at=0.0)
    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: fake_script if sid == "s1" else None)

    class FakeUser:
        id = "user-1"
        role = "member"

    result = api.get_owned_script("s1", user=FakeUser())
    assert result.id == "s1"


def test_get_owned_script_404_for_non_owner(monkeypatch):
    from src.apps.comic_gen import api
    from src.apps.comic_gen.models import Script

    fake_script = Script(id="s1", title="t", original_text="x", owner_id="user-1", created_at=0.0, updated_at=0.0)
    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: fake_script if sid == "s1" else None)

    class OtherUser:
        id = "user-2"
        role = "member"

    with pytest.raises(HTTPException) as exc_info:
        api.get_owned_script("s1", user=OtherUser())
    assert exc_info.value.status_code == 404


def test_get_owned_script_admin_bypasses_ownership(monkeypatch):
    from src.apps.comic_gen import api
    from src.apps.comic_gen.models import Script

    fake_script = Script(id="s1", title="t", original_text="x", owner_id="user-1", created_at=0.0, updated_at=0.0)
    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: fake_script if sid == "s1" else None)

    class AdminUser:
        id = "admin-id"
        role = "admin"

    result = api.get_owned_script("s1", user=AdminUser())
    assert result.id == "s1"


def test_get_owned_script_404_when_not_found(monkeypatch):
    from src.apps.comic_gen import api

    monkeypatch.setattr(api.pipeline, "get_script", lambda sid: None)

    class AnyUser:
        id = "user-1"
        role = "member"

    with pytest.raises(HTTPException) as exc_info:
        api.get_owned_script("missing", user=AnyUser())
    assert exc_info.value.status_code == 404
