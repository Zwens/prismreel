"""A refined frame's prompt must be writable.

The storyboard reads a shot's prompt from `visual_description` when the frame
has one and from `action_description` otherwise, but /frames/update only ever
accepted `action_description`. For a refined frame the write therefore landed
in the shadowed field: reference tags and hand-typed prompt edits both
vanished on reload. The endpoint has to be able to write the field that is
actually read.
"""

import pytest
from fastapi.testclient import TestClient

from src.apps.comic_gen.models import Script, StoryboardFrame


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.apps.comic_gen.api import app

    return TestClient(app)


@pytest.fixture
def episode(tmp_path):
    from src.apps.comic_gen.api import pipeline

    saved = (pipeline.data_file, pipeline.series_data_file,
             dict(pipeline.scripts), dict(pipeline.series_store))
    pipeline.data_file = str(tmp_path / "projects.json")
    pipeline.series_data_file = str(tmp_path / "series.json")
    pipeline.scripts = {}
    pipeline.series_store = {}
    try:
        script = Script(id="ep-1", title="Episode 1", original_text="x",
                        created_at=0.0, updated_at=0.0)
        script.frames = [
            StoryboardFrame(
                id="f_refined", scene_id="",
                action_description="coarse text",
                visual_description="polished text",
            ),
            StoryboardFrame(
                id="f_raw", scene_id="",
                action_description="coarse only",
            ),
        ]
        pipeline.scripts["ep-1"] = script
        yield script
    finally:
        (pipeline.data_file, pipeline.series_data_file,
         pipeline.scripts, pipeline.series_store) = saved


def test_visual_description_can_be_written(client, episode):
    r = client.post("/projects/ep-1/frames/update", json={
        "frame_id": "f_refined",
        "visual_description": "polished text [character1:Zhang]",
    })

    assert r.status_code == 200, r.text
    frame = next(f for f in episode.frames if f.id == "f_refined")
    assert frame.visual_description == "polished text [character1:Zhang]"


def test_writing_visual_description_leaves_action_description_alone(client, episode):
    """The two fields carry different content; writing one must not clobber
    the other, or the coarse description used elsewhere gets overwritten."""
    client.post("/projects/ep-1/frames/update", json={
        "frame_id": "f_refined",
        "visual_description": "new polished",
    })

    frame = next(f for f in episode.frames if f.id == "f_refined")
    assert frame.action_description == "coarse text"


def test_action_description_still_writable_for_unrefined_frames(client, episode):
    r = client.post("/projects/ep-1/frames/update", json={
        "frame_id": "f_raw",
        "action_description": "coarse only [character1:Zhang]",
    })

    assert r.status_code == 200, r.text
    frame = next(f for f in episode.frames if f.id == "f_raw")
    assert frame.action_description == "coarse only [character1:Zhang]"
    assert frame.visual_description is None
