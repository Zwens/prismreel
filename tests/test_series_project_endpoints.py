"""Regression: endpoints returning a project whose assets live series-side.

GET /projects/{id} merges the parent series' shared characters into the
episode payload, so the character ids the frontend holds routinely live
series-side, not in script.characters. Both halves of the round trip
have to honour that:

  1. the write must find the character (else 500 "Character not found"),
  2. the response must carry the same merged shape as GET, because the
     frontend shallow-merges it into its project store — returning the
     raw episode Script would blank the whole cast list.
"""

import pytest
from fastapi.testclient import TestClient

from src.apps.comic_gen.models import Character, Script


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.apps.comic_gen.api import app

    return TestClient(app)


@pytest.fixture
def shared_char_episode(tmp_path):
    """An episode whose only character lives in the series pool.

    The API module holds a single module-level pipeline, so every field
    this touches is saved and restored — otherwise the seeded script /
    series and the redirected data files leak into whichever test runs
    next.
    """
    from src.apps.comic_gen.api import pipeline

    saved = (pipeline.data_file, pipeline.series_data_file,
             dict(pipeline.scripts), dict(pipeline.series_store))
    pipeline.data_file = str(tmp_path / "projects.json")
    pipeline.series_data_file = str(tmp_path / "series.json")
    pipeline.scripts = {}
    pipeline.series_store = {}
    try:
        series = pipeline.create_series("Old Nine Gates")
        char = Character(id="char-shared", name="Er Yue Hong", description="calm")
        series.characters = [char]
        script = Script(id="ep-1", title="Episode 1", original_text="x",
                        created_at=0.0, updated_at=0.0)
        pipeline.scripts["ep-1"] = script
        pipeline.add_episode_to_series(series.id, "ep-1")
        assert script.characters == []
        yield series, script, char
    finally:
        (pipeline.data_file, pipeline.series_data_file,
         pipeline.scripts, pipeline.series_store) = saved


def test_bind_voice_succeeds_for_series_shared_character(client, shared_char_episode):
    series, _, char = shared_char_episode

    r = client.post(
        "/projects/ep-1/characters/char-shared/voice",
        json={"voice_id": "longxiaochun_v2", "voice_name": "龙小淳 (知性女)"},
    )

    assert r.status_code == 200, r.text
    assert series.characters[0].voice_id == "longxiaochun_v2"


def test_bind_voice_response_keeps_the_merged_cast(client, shared_char_episode):
    """The response feeds the frontend's project store directly."""
    r = client.post(
        "/projects/ep-1/characters/char-shared/voice",
        json={"voice_id": "longxiaochun_v2", "voice_name": "龙小淳 (知性女)"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    returned = {c["id"]: c for c in body["characters"]}
    assert "char-shared" in returned, "series-shared character dropped from response"
    assert returned["char-shared"]["voice_id"] == "longxiaochun_v2"
    assert returned["char-shared"]["source"] == "series"


def test_bind_voice_unknown_character_is_404(client, shared_char_episode):
    r = client.post(
        "/projects/ep-1/characters/nope/voice",
        json={"voice_id": "v", "voice_name": "V"},
    )
    assert r.status_code == 404


def test_storyboard_analyze_response_keeps_the_merged_cast(client, shared_char_episode, monkeypatch):
    """The frontend shallow-merges this response into its project store.

    Returning the raw episode Script blanks characters/scenes/props for
    any episode whose assets live in the series pool — the cast chips
    vanish and the next R2V generation refuses every reference tag with
    "尚未生成图片".
    """
    from src.apps.comic_gen.api import pipeline

    _, script, _ = shared_char_episode
    monkeypatch.setattr(pipeline, "analyze_text_to_frames",
                        lambda script_id, text: script)

    r = client.post("/projects/ep-1/storyboard/analyze", json={"text": "some text"})

    assert r.status_code == 200, r.text
    returned = {c["id"] for c in r.json()["characters"]}
    assert "char-shared" in returned, "series-shared cast dropped from response"
