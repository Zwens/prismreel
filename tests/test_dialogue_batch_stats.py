"""The batch dialogue stats must reflect what actually got generated.

`AudioGenerator.generate_dialogue` never raises — a TTS failure is recorded
on the frame (status=FAILED + audio_error) so the single-frame endpoint can
return 200 and let the UI show the error inline. The batch counted a frame as
generated whenever no exception escaped, so a real failure ("websocket
connection could not established within 5s") was reported as success and the
user saw "已生成 8 条对白音频" with one line silently mute.
"""

import pytest
from fastapi.testclient import TestClient

from src.apps.comic_gen.models import (
    Character, GenerationStatus, Script, StoryboardFrame,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.apps.comic_gen.api import app

    return TestClient(app)


@pytest.fixture
def two_line_episode(tmp_path):
    """Episode with two dialogue frames whose speaker lives series-side."""
    from src.apps.comic_gen.api import pipeline

    saved = (pipeline.data_file, pipeline.series_data_file,
             dict(pipeline.scripts), dict(pipeline.series_store))
    pipeline.data_file = str(tmp_path / "projects.json")
    pipeline.series_data_file = str(tmp_path / "series.json")
    pipeline.scripts = {}
    pipeline.series_store = {}
    try:
        series = pipeline.create_series("Old Nine Gates")
        series.characters = [
            Character(id="c1", name="Zhang", description="",
                      voice_id="longcheng_v2", voice_name="Long Cheng"),
        ]
        script = Script(id="ep-1", title="Episode 1", original_text="x",
                        created_at=0.0, updated_at=0.0)
        script.frames = [
            StoryboardFrame(id="f_ok", scene_id="", action_description="a",
                            dialogue="line one", character_ids=["c1"]),
            StoryboardFrame(id="f_bad", scene_id="", action_description="b",
                            dialogue="line two", character_ids=["c1"]),
        ]
        pipeline.scripts["ep-1"] = script
        pipeline.add_episode_to_series(series.id, "ep-1")
        yield script
    finally:
        (pipeline.data_file, pipeline.series_data_file,
         pipeline.scripts, pipeline.series_store) = saved


def test_a_frame_whose_tts_failed_is_counted_as_failed(client, two_line_episode, monkeypatch):
    from src.apps.comic_gen.api import pipeline

    def fake_generate_dialogue(frame, character, *args, **kwargs):
        """Mirror the real contract: never raise, record outcome on the frame."""
        if frame.id == "f_bad":
            frame.status = GenerationStatus.FAILED
            frame.audio_error = "TTS generation failed: websocket timeout"
        else:
            frame.audio_url = f"audio/dialogue/{frame.id}.mp3"
            frame.audio_error = None
            frame.status = GenerationStatus.COMPLETED
        return frame

    monkeypatch.setattr(
        pipeline.audio_generator, "generate_dialogue", fake_generate_dialogue
    )

    r = client.post("/projects/ep-1/dialogue_audio/batch")

    assert r.status_code == 200, r.text
    stats = r.json()["_batch_stats"]
    assert stats["generated"] == 1, "only the frame that produced audio counts"
    assert stats["failed"] == 1, "the TTS failure must not be reported as success"
    assert stats["no_voice"] == 0


def test_all_succeeding_frames_are_counted_generated(client, two_line_episode, monkeypatch):
    from src.apps.comic_gen.api import pipeline

    def fake_generate_dialogue(frame, character, *args, **kwargs):
        frame.audio_url = f"audio/dialogue/{frame.id}.mp3"
        frame.audio_error = None
        frame.status = GenerationStatus.COMPLETED
        return frame

    monkeypatch.setattr(
        pipeline.audio_generator, "generate_dialogue", fake_generate_dialogue
    )

    r = client.post("/projects/ep-1/dialogue_audio/batch")

    stats = r.json()["_batch_stats"]
    assert stats["generated"] == 2
    assert stats["failed"] == 0
