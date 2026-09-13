from unittest.mock import patch, MagicMock


def test_poll_extracts_usage_from_succeeded_response(monkeypatch, tmp_path):
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    from src.models.byteplus import BytePlusVideoModel

    model = BytePlusVideoModel({})

    succeeded_response = MagicMock()
    succeeded_response.raise_for_status.return_value = None
    succeeded_response.json.return_value = {
        "status": "succeeded",
        "content": {"video_url": "https://example.com/video.mp4"},
        "usage": {"completion_tokens": 108900, "total_tokens": 108900},
    }

    with patch("src.models.byteplus.requests.get", return_value=succeeded_response):
        video_url, usage = model._poll("task-123")

    assert video_url == "https://example.com/video.mp4"
    assert usage == {"completion_tokens": 108900, "total_tokens": 108900}


def test_poll_handles_missing_usage(monkeypatch):
    monkeypatch.setenv("ARK_API_KEY", "test-key")
    from src.models.byteplus import BytePlusVideoModel

    model = BytePlusVideoModel({})

    succeeded_response = MagicMock()
    succeeded_response.raise_for_status.return_value = None
    succeeded_response.json.return_value = {
        "status": "succeeded",
        "content": {"video_url": "https://example.com/video.mp4"},
    }

    with patch("src.models.byteplus.requests.get", return_value=succeeded_response):
        video_url, usage = model._poll("task-123")

    assert video_url == "https://example.com/video.mp4"
    assert usage is None
