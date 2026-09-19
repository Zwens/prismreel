from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.apps.comic_gen.api import app
from src.apps.playground import api as playground_api
from src.apps.playground.concat_service import ConcatError


@pytest.fixture
def client():
    return TestClient(app)


def _auth_headers(client):
    """No headers needed: PRISMREEL_JWT_SECRET is unset in the test
    environment (no .env file in this worktree, and no other test in this
    session mutates it without monkeypatch auto-revert), so
    auth.require_login hits its dev-mode bypass and returns the anonymous
    admin unconditionally — see
    src/apps/comic_gen/test_enforce_login_middleware.py::test_login_gate_disabled_when_jwt_secret_unset
    for the same convention against a different route."""
    return {}


def test_concat_endpoint_rejects_path_outside_output(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/playground/concat",
        json={"video_paths": ["../../etc/passwd"]},
        headers=headers,
    )
    assert resp.status_code == 400


def test_concat_endpoint_rejects_missing_file(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/playground/concat",
        json={"video_paths": ["playground/videos/does_not_exist_12345.mp4"]},
        headers=headers,
    )
    assert resp.status_code == 400


def test_concat_endpoint_rejects_empty_list(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/playground/concat",
        json={"video_paths": []},
        headers=headers,
    )
    assert resp.status_code == 400


def test_concat_endpoint_returns_500_when_ffmpeg_missing(client, tmp_path):
    output_root = tmp_path / "output"
    (output_root / "playground" / "videos").mkdir(parents=True)
    clip = output_root / "playground" / "videos" / "clip1.mp4"
    clip.write_bytes(b"fake video bytes")

    with patch.object(playground_api, "resolve_local_media_path", return_value=str(clip)), \
         patch.object(playground_api, "get_ffmpeg_path", return_value=None):
        resp = client.post(
            "/playground/concat",
            json={"video_paths": ["playground/videos/clip1.mp4"]},
            headers=_auth_headers(client),
        )

    assert resp.status_code == 500


def test_concat_endpoint_success_returns_output_path(client, tmp_path):
    output_root = tmp_path / "output"
    (output_root / "playground" / "videos").mkdir(parents=True)
    clip = output_root / "playground" / "videos" / "clip1.mp4"
    clip.write_bytes(b"fake video bytes")
    fake_output = str(output_root / "playground" / "videos" / "workflow_abc.mp4")

    with patch.object(playground_api, "resolve_local_media_path", return_value=str(clip)), \
         patch.object(playground_api, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
         patch.object(playground_api, "concat_videos", return_value=fake_output) as mock_concat:
        resp = client.post(
            "/playground/concat",
            json={"video_paths": ["playground/videos/clip1.mp4"]},
            headers=_auth_headers(client),
        )

    assert resp.status_code == 200
    assert resp.json()["path"].endswith("workflow_abc.mp4")
    mock_concat.assert_called_once()


def test_concat_endpoint_returns_500_when_concat_raises(client, tmp_path):
    output_root = tmp_path / "output"
    (output_root / "playground" / "videos").mkdir(parents=True)
    clip = output_root / "playground" / "videos" / "clip1.mp4"
    clip.write_bytes(b"fake video bytes")

    with patch.object(playground_api, "resolve_local_media_path", return_value=str(clip)), \
         patch.object(playground_api, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"), \
         patch.object(playground_api, "concat_videos", side_effect=ConcatError("ffmpeg failed: boom")):
        resp = client.post(
            "/playground/concat",
            json={"video_paths": ["playground/videos/clip1.mp4"]},
            headers=_auth_headers(client),
        )

    assert resp.status_code == 500
