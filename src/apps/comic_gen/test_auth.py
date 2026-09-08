import os
import pytest


def test_hash_and_verify_password_roundtrip():
    from src.apps.comic_gen.auth import hash_password, verify_password

    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-for-unit-tests")
    import importlib
    from src.apps.comic_gen import auth
    importlib.reload(auth)

    token = auth.create_access_token(user_id="user-123", role="member")
    payload = auth.decode_access_token(token)
    assert payload["user_id"] == "user-123"
    assert payload["role"] == "member"


def test_decode_access_token_rejects_garbage(monkeypatch):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-for-unit-tests")
    import importlib
    from src.apps.comic_gen import auth
    importlib.reload(auth)
    import jwt as pyjwt

    with pytest.raises(pyjwt.InvalidTokenError):
        auth.decode_access_token("not-a-real-token")
