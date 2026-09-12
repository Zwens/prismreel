"""Tests for PlaygroundStorage's orphan-generation recovery on boot."""

import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import pytest

from src.apps.playground.storage import PlaygroundStorage


def _write_history(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f)


def _make_record(gen_id, status, error=None):
    return {
        "id": gen_id,
        "owner_id": "",
        "mode": "i2v",
        "model_id": "seedance-2.5-i2v",
        "prompt": "test",
        "negative_prompt": None,
        "input_media": [],
        "parameters": {},
        "batch_size": 1,
        "outputs": [],
        "status": status,
        "error": error,
        "created_at": "2026-09-11T10:30:15.218625+00:00",
    }


@pytest.fixture
def history_path(tmp_path, monkeypatch):
    path = str(tmp_path / "playground_history.json")
    monkeypatch.setattr(PlaygroundStorage, "HISTORY_PATH", path)
    monkeypatch.setattr(PlaygroundStorage, "TEMPLATES_PATH", str(tmp_path / "playground_templates.json"))
    return path


def test_stuck_processing_generation_marked_failed_on_boot(history_path):
    _write_history(history_path, [_make_record("gen-1", "processing")])

    storage = PlaygroundStorage()

    gen = storage.get_generation("gen-1")
    assert gen.status == "failed"
    assert gen.error == PlaygroundStorage._ORPHAN_RECOVERY_REASON


def test_stuck_pending_generation_marked_failed_on_boot(history_path):
    _write_history(history_path, [_make_record("gen-2", "pending")])

    storage = PlaygroundStorage()

    gen = storage.get_generation("gen-2")
    assert gen.status == "failed"


def test_completed_generation_untouched(history_path):
    _write_history(history_path, [_make_record("gen-3", "completed")])

    storage = PlaygroundStorage()

    gen = storage.get_generation("gen-3")
    assert gen.status == "completed"
    assert gen.error is None


def test_existing_error_message_preserved(history_path):
    _write_history(history_path, [_make_record("gen-4", "processing", error="custom failure")])

    storage = PlaygroundStorage()

    gen = storage.get_generation("gen-4")
    assert gen.status == "failed"
    assert gen.error == "custom failure"


def test_recovery_persists_to_disk(history_path):
    _write_history(history_path, [_make_record("gen-5", "processing")])

    PlaygroundStorage()

    with open(history_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved[0]["status"] == "failed"
