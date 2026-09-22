import pytest
from unittest.mock import patch, MagicMock


def test_validate_outbound_url_allows_public_https(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import _validate_outbound_url

    _validate_outbound_url("https://cdn.deevid.ai/xxx.png")


def test_validate_outbound_url_blocks_link_local_metadata(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import _validate_outbound_url

    with pytest.raises(ValueError):
        _validate_outbound_url("http://169.254.169.254/latest/meta-data/")


def test_validate_outbound_url_blocks_localhost(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import _validate_outbound_url

    with pytest.raises(ValueError):
        _validate_outbound_url("http://localhost:8080/xxx")


def test_validate_outbound_url_blocks_loopback_ip(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import _validate_outbound_url

    with pytest.raises(ValueError):
        _validate_outbound_url("http://127.0.0.1/xxx")


def test_validate_outbound_url_blocks_private_network(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import _validate_outbound_url

    with pytest.raises(ValueError):
        _validate_outbound_url("http://192.168.1.1/xxx")


def test_validate_outbound_url_blocks_non_http_scheme(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import _validate_outbound_url

    with pytest.raises(ValueError):
        _validate_outbound_url("file:///etc/passwd")


def test_generate_raises_before_any_request_when_image_url_is_internal(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    with patch("src.models.deevid.requests.get") as mock_get, \
         patch("src.models.deevid.requests.post") as mock_post, \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="http://10.0.0.1/evil.png"),
         ):
        with pytest.raises(ValueError):
            model.generate(
                prompt="x", output_path="/tmp/out.mp4",
                img_url="http://10.0.0.1/evil.png", duration=5,
            )

    mock_get.assert_not_called()
    mock_post.assert_not_called()


def test_submit_and_poll_success(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    image_bytes_response = MagicMock()
    image_bytes_response.content = b"fake-image-bytes"

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {
        "success": True,
        "data": {"taskId": 10002, "status": "INIT"},
    }

    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        "success": True,
        "data": {
            "taskId": 10002,
            "status": "SUCCESS",
            "resultVideoUrl": "https://cdn.deevid.ai/videos/xxx.mp4",
        },
    }

    video_bytes_response = MagicMock()
    video_bytes_response.content = b"fake-video-bytes"

    out_path = str(tmp_path / "out.mp4")

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]), \
         patch("src.models.deevid.requests.get", side_effect=[image_bytes_response, status_response, video_bytes_response]), \
         patch("src.models.deevid.time.sleep", return_value=None), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ), \
         patch("src.models.deevid.open", create=True):
        # Real generate() call order: (1) requests.get downloads the resolved
        # image URL's bytes, (2) requests.post uploads them for userImageId,
        # (3) requests.post submits the generation task, (4) requests.get
        # polls status, (5) requests.get downloads the result video.
        result_path, elapsed = model.generate(
            prompt="a cat walking",
            output_path=out_path,
            img_url="https://example.com/input.png",
            duration=5,
        )

    assert result_path == out_path
    assert isinstance(elapsed, float)
    assert model.last_task_id == "10002"


def test_submit_failure_raises(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    image_bytes_response = MagicMock()
    image_bytes_response.content = b"fake-image-bytes"

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 400
    submit_response.text = '{"success": false, "message": "bad request"}'

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]), \
         patch("src.models.deevid.requests.get", side_effect=[image_bytes_response]), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ):
        try:
            model.generate(
                prompt="x", output_path="/tmp/out.mp4",
                img_url="https://example.com/input.png", duration=5,
            )
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "400" in str(exc)


def test_task_failed_status_raises(monkeypatch):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    image_bytes_response = MagicMock()
    image_bytes_response.content = b"fake-image-bytes"

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {"success": True, "data": {"taskId": 1, "status": "INIT"}}

    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        "success": True,
        "data": {"taskId": 1, "status": "FAILED"},
    }

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]), \
         patch("src.models.deevid.requests.get", side_effect=[image_bytes_response, status_response]), \
         patch("src.models.deevid.time.sleep", return_value=None), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ):
        try:
            model.generate(
                prompt="x", output_path="/tmp/out.mp4",
                img_url="https://example.com/input.png", duration=5,
            )
            assert False, "should have raised"
        except RuntimeError as exc:
            assert "FAILED" in str(exc) or "failed" in str(exc)


def test_duration_clamped_to_supported_range(monkeypatch):
    """Quality V4.0 durationRange is [4,15]."""
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import MIN_DURATION, MAX_DURATION

    assert MIN_DURATION == 4
    assert MAX_DURATION == 15


def _run_generate_and_capture_submitted_duration(monkeypatch, tmp_path, duration):
    monkeypatch.setenv("DEEVID_API_KEY", "test-key")
    from src.models.deevid import DeeVidModel

    model = DeeVidModel({})

    image_bytes_response = MagicMock()
    image_bytes_response.content = b"fake-image-bytes"

    upload_response = MagicMock()
    upload_response.status_code = 200
    upload_response.json.return_value = {
        "success": True,
        "data": {"userImageId": 123, "imageUrl": "https://cdn.deevid.ai/images/xxx.png"},
    }

    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {
        "success": True,
        "data": {"taskId": 10002, "status": "INIT"},
    }

    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {
        "success": True,
        "data": {
            "taskId": 10002,
            "status": "SUCCESS",
            "resultVideoUrl": "https://cdn.deevid.ai/videos/xxx.mp4",
        },
    }

    video_bytes_response = MagicMock()
    video_bytes_response.content = b"fake-video-bytes"

    out_path = str(tmp_path / "out.mp4")

    with patch("src.models.deevid.requests.post", side_effect=[upload_response, submit_response]) as mock_post, \
         patch("src.models.deevid.requests.get", side_effect=[image_bytes_response, status_response, video_bytes_response]), \
         patch("src.models.deevid.time.sleep", return_value=None), \
         patch(
             "src.models.deevid.resolve_media_input",
             return_value=MagicMock(value="https://example.com/input.png"),
         ), \
         patch("src.models.deevid.open", create=True):
        model.generate(
            prompt="a cat walking",
            output_path=out_path,
            img_url="https://example.com/input.png",
            duration=duration,
        )

    # Second requests.post call is the submit call; its json= body carries duration.
    submit_call = mock_post.call_args_list[1]
    submitted_body = submit_call.kwargs["json"]
    return submitted_body["duration"]


def test_duration_above_max_is_clamped_down(monkeypatch, tmp_path):
    submitted_duration = _run_generate_and_capture_submitted_duration(monkeypatch, tmp_path, duration=30)
    assert submitted_duration == 15


def test_duration_below_min_is_clamped_up(monkeypatch, tmp_path):
    submitted_duration = _run_generate_and_capture_submitted_duration(monkeypatch, tmp_path, duration=1)
    assert submitted_duration == 4
