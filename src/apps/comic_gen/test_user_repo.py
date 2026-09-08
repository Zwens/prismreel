import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret")
    import importlib
    from src.apps.comic_gen import auth_db, user_repo
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(user_repo)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def test_create_and_get_user_by_email():
    from src.apps.comic_gen import user_repo

    created = user_repo.create_user("alice@example.com", "hunter2", role="admin")
    fetched = user_repo.get_user_by_email("alice@example.com")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.role == "admin"
    assert fetched.password_hash != "hunter2"


def test_create_user_duplicate_email_raises():
    from src.apps.comic_gen import user_repo

    user_repo.create_user("bob@example.com", "pw1")
    with pytest.raises(Exception):
        user_repo.create_user("bob@example.com", "pw2")


def test_invite_lifecycle():
    from src.apps.comic_gen import user_repo

    admin = user_repo.create_user("admin@example.com", "adminpw", role="admin")
    code = user_repo.create_invite(created_by=admin.id, role="member")

    new_user = user_repo.redeem_invite(code, "newmember@example.com", "memberpw")
    assert new_user.role == "member"

    with pytest.raises(ValueError):
        user_repo.redeem_invite(code, "another@example.com", "pw")


def test_redeem_invite_invalid_code_raises():
    from src.apps.comic_gen import user_repo

    with pytest.raises(ValueError):
        user_repo.redeem_invite("does-not-exist", "x@example.com", "pw")
