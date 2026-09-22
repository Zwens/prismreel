import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMREEL_JWT_SECRET", "test-secret-needs-32-chars-minimum")
    import importlib
    from src.apps.comic_gen import auth_db, credit_ledger
    monkeypatch.setattr(auth_db, "_DB_PATH", str(tmp_path / "auth.db"))
    importlib.reload(credit_ledger)
    conn = auth_db.get_connection()
    auth_db.init_schema(conn)
    conn.close()
    yield


def _make_service():
    from src.apps.playground.service import PlaygroundService
    from src.apps.playground.storage import PlaygroundStorage
    storage = MagicMock(spec=PlaygroundStorage)
    return PlaygroundService(storage)


def _make_gen(duration=5):
    from src.apps.playground.models import PlaygroundGeneration, PlaygroundMode
    return PlaygroundGeneration(
        id="gen-1", mode=PlaygroundMode.I2V, model_id="deevid/quality-v4.0",
        prompt="test", input_media=["https://example.com/in.png"],
        parameters={"duration": duration}, created_at="2026-09-21T00:00:00Z",
    )


def test_generate_video_deevid_success_records_usage():
    service = _make_service()
    gen = _make_gen(duration=5)

    fake_model = MagicMock()
    fake_model.generate.return_value = ("/tmp/out.mp4", 12.3)
    fake_model.last_task_id = "task-99"

    with patch("src.models.deevid.DeeVidModel", return_value=fake_model):
        usage = service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert usage == {"provider": "deevid", "duration": 5, "resolution": "720p"}

    from src.apps.comic_gen import credit_ledger
    assert credit_ledger.get_remaining_points() == 580  # 600 - 5*4


def test_generate_video_deevid_blocks_when_quota_exhausted():
    from src.apps.comic_gen import credit_ledger

    for _ in range(30):
        credit_ledger.record_usage(points=20, duration=5, task_id=None)
    # 30 * 20 = 600, remaining = 0

    service = _make_service()
    gen = _make_gen(duration=5)

    with pytest.raises(RuntimeError) as exc_info:
        service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert "額度" in str(exc_info.value) or "quota" in str(exc_info.value).lower()


def test_generate_video_deevid_failure_does_not_consume_quota():
    service = _make_service()
    gen = _make_gen(duration=5)

    fake_model = MagicMock()
    fake_model.generate.side_effect = RuntimeError("DeeVid task failed: content policy")

    from src.apps.comic_gen import credit_ledger

    with patch("src.models.deevid.DeeVidModel", return_value=fake_model):
        with pytest.raises(RuntimeError):
            service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert credit_ledger.get_remaining_points() == 600  # 未扣點


def test_process_video_generation_routes_deevid_model_id():
    service = _make_service()
    gen = _make_gen(duration=5)

    with patch.object(service, "_generate_video_deevid", return_value=None) as mock_deevid, \
         patch.object(service, "_extract_video_thumbnail", return_value=None):
        service._process_video_generation(gen)

    mock_deevid.assert_called_once()


def test_generate_video_deevid_releases_reservation_when_resolve_input_media_fails():
    """_resolve_first_input_media(gen) must run inside the try block so that
    a failure there still triggers release_reservation -- previously it ran
    after the reservation but before the try, leaking the reservation
    forever on failure."""
    service = _make_service()
    gen = _make_gen(duration=5)

    from src.apps.comic_gen import credit_ledger

    with patch.object(
        service, "_resolve_first_input_media", side_effect=ValueError("bad input media")
    ):
        with pytest.raises(ValueError, match="bad input media"):
            service._generate_video_deevid(gen, "/tmp/out.mp4")

    assert credit_ledger.get_remaining_points() == 600  # reservation released, not leaked


def test_generate_video_deevid_reraises_original_error_even_if_release_reservation_fails():
    """If release_reservation itself raises (e.g. it still times out even at
    30s under extreme contention), the exception that reaches the caller
    must be the ORIGINAL generation failure, not the release-path exception --
    otherwise the real root cause is masked by an unrelated DB error."""
    import sqlite3

    service = _make_service()
    gen = _make_gen(duration=5)

    fake_model = MagicMock()
    fake_model.generate.side_effect = RuntimeError("DeeVid task failed: content policy")

    with patch("src.models.deevid.DeeVidModel", return_value=fake_model), \
         patch(
             "src.apps.comic_gen.credit_ledger.release_reservation",
             side_effect=sqlite3.OperationalError("database is locked"),
         ):
        with pytest.raises(RuntimeError, match="content policy"):
            service._generate_video_deevid(gen, "/tmp/out.mp4")
