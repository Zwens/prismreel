"""Dialogue speaker resolution must see the series-shared cast.

An episode whose characters were never forked locally keeps an EMPTY
`script.characters` — the whole cast lives in the parent series' shared pool
(that is the normal state for a series episode). Speaker resolution read only
`script.characters`, so for such an episode every line of dialogue resolved to
no speaker and the batch reported "N 条对白的角色尚未绑定语音" even though every
character had a voice bound. bind_voice already resolves across layers via
_find_asset_with_source; resolution has to agree with it.
"""

import time
import uuid
from unittest.mock import patch

import pytest

from src.apps.comic_gen.models import Series, Script, Character, StoryboardFrame
from src.apps.comic_gen.pipeline import ComicGenPipeline


@pytest.fixture
def pipeline(tmp_path):
    with patch("src.apps.comic_gen.pipeline.ScriptProcessor"), \
         patch("src.apps.comic_gen.pipeline.AssetGenerator"), \
         patch("src.apps.comic_gen.pipeline.StoryboardGenerator"), \
         patch("src.apps.comic_gen.pipeline.VideoGenerator"), \
         patch("src.apps.comic_gen.pipeline.AudioGenerator"), \
         patch("src.apps.comic_gen.pipeline.ExportManager"):
        p = ComicGenPipeline()
    p.data_file = str(tmp_path / "projects.json")
    p.series_data_file = str(tmp_path / "series.json")
    p.scripts = {}
    p.series_store = {}
    return p


def _series_with_voiced_cast(series_id="S1"):
    now = time.time()
    return Series(
        id=series_id,
        title="21世纪的九门",
        created_at=now,
        updated_at=now,
        characters=[
            Character(id="c_zqs", name="张启山 (浴袍)", description="",
                      voice_id="longcheng_v2", voice_name="龙诚"),
            Character(id="c_wlg", name="吴老狗 (浴袍)", description="",
                      voice_id="longze_v2", voice_name="龙泽"),
        ],
    )


def _episode_with_series_cast(series_id="S1"):
    """Episode with NO local characters — the real shape for a series episode."""
    now = time.time()
    return Script(
        id=str(uuid.uuid4()),
        title="第二集",
        original_text="",
        series_id=series_id,
        characters=[],
        created_at=now,
        updated_at=now,
        frames=[
            StoryboardFrame(
                id="f1",
                scene_id="",
                action_description="热气腾腾的浴室内，两人相对而立",
                dialogue="佛爷，今时不同往日。",
                character_ids=["c_zqs"],
            ),
        ],
    )


def test_speaker_resolves_from_the_series_shared_cast(pipeline):
    series = _series_with_voiced_cast()
    episode = _episode_with_series_cast()
    pipeline.series_store[series.id] = series
    pipeline.scripts[episode.id] = episode

    speaker = pipeline.resolve_dialogue_speaker(episode, episode.frames[0])

    assert speaker is not None, "speaker lives in the series pool, not the episode"
    assert speaker.name == "张启山 (浴袍)"
    assert speaker.voice_id == "longcheng_v2"


def test_episode_local_character_still_wins(pipeline):
    """A locally forked character overrides the series version of the same id."""
    series = _series_with_voiced_cast()
    episode = _episode_with_series_cast()
    episode.characters = [
        Character(id="c_zqs", name="张启山 (本集改)", description="",
                  voice_id="local_voice", voice_name="本集音色"),
    ]
    pipeline.series_store[series.id] = series
    pipeline.scripts[episode.id] = episode

    speaker = pipeline.resolve_dialogue_speaker(episode, episode.frames[0])

    assert speaker.voice_id == "local_voice"


def test_speaker_resolves_by_name_when_the_frame_has_no_character_ids(pipeline):
    series = _series_with_voiced_cast()
    episode = _episode_with_series_cast()
    episode.frames[0].character_ids = []
    episode.frames[0].speaker = "吴老狗 (浴袍)"
    pipeline.series_store[series.id] = series
    pipeline.scripts[episode.id] = episode

    speaker = pipeline.resolve_dialogue_speaker(episode, episode.frames[0])

    assert speaker is not None
    assert speaker.voice_id == "longze_v2"


def test_speaker_resolves_from_a_reference_tag_as_last_resort(pipeline):
    """R2V frames carry no speaker name — fall back to the first [characterN:] tag."""
    series = _series_with_voiced_cast()
    episode = _episode_with_series_cast()
    episode.frames[0].character_ids = []
    episode.frames[0].speaker = None
    episode.frames[0].action_description = (
        "吴老狗掏出一个盒子 [character1:吴老狗 (浴袍)] [character2:张启山 (浴袍)]"
    )
    pipeline.series_store[series.id] = series
    pipeline.scripts[episode.id] = episode

    speaker = pipeline.resolve_dialogue_speaker(episode, episode.frames[0])

    assert speaker is not None
    assert speaker.voice_id == "longze_v2"


def test_returns_none_when_the_frame_names_nobody(pipeline):
    series = _series_with_voiced_cast()
    episode = _episode_with_series_cast()
    episode.frames[0].character_ids = []
    episode.frames[0].speaker = None
    episode.frames[0].action_description = "空镜：雨水打在窗上"
    pipeline.series_store[series.id] = series
    pipeline.scripts[episode.id] = episode

    assert pipeline.resolve_dialogue_speaker(episode, episode.frames[0]) is None
