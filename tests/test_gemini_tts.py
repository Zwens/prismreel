"""Gemini TTS 适配与存量音色迁移。

DashScope 下线后配音只剩 Gemini 一条路（Ark 平台 43 个在售模型无一个 TTS，
2026-09-08 实测）。这带来三类必须钉死的行为：

1. **WAV 封装**。Gemini 只回裸 PCM（`audio/l16; rate=24000; channels=1`），
   直接落盘得到的文件浏览器和 ffmpeg 都不认。少了 44 字节头，问题会一路
   潜伏到合成视频那一步才炸。
2. **音色性别**。30 个预置音色 Google 未标注性别，注册表里的 gender 来自
   人工试听。存量 51 处角色绑定按性别就近迁移，**男声绝不能映射成女声**，
   反之亦然 —— 错一个就毁掉一整集已完成的配音。
3. **参数落差**。CosyVoice 支持 speech_rate / pitch_rate / volume 三个数值
   参数，Gemini 只能靠自然语言描述控制。能近似的要近似，不能的要明确失效，
   不能让 UI 上的滑块看起来在工作、实际什么也没做。
"""

import base64
import json
import struct
import pytest

from src.audio.gemini_tts import (
    GEMINI_VOICES,
    pcm_to_wav,
    synthesize_gemini,
)


class TestVoiceRegistry:
    def test_all_thirty_preset_voices_are_registered(self):
        assert len(GEMINI_VOICES) == 30

    def test_every_voice_declares_a_gender(self):
        missing = [k for k, v in GEMINI_VOICES.items() if v.get("gender") not in
                   ("Male", "Female", "Neutral")]
        assert not missing, f"未标性别的音色会让迁移映射无法校验: {missing}"

    def test_both_genders_have_enough_voices_to_map_onto(self):
        # 存量音色 1 女 6 男。任一侧为空都会逼出跨性别映射。
        genders = [v["gender"] for v in GEMINI_VOICES.values()]
        assert genders.count("Female") >= 5
        assert genders.count("Male") >= 5

    def test_registry_shape_matches_the_legacy_one(self):
        # audio.py 的 get_available_voices() 直接消费这个结构，字段名不能变。
        for key, meta in GEMINI_VOICES.items():
            assert {"model_id", "name", "gender", "model"} <= set(meta)
            assert meta["model_id"] == key

    def test_display_name_carries_the_english_id(self):
        # 音色名是英文的，中文描述是我们加的；两者都要在，否则用户对不上
        # 官方文档，也看不懂这音色是什么调性。
        assert "Kore" in GEMINI_VOICES["Kore"]["name"]
        assert any("一" <= ch <= "鿿" for ch in GEMINI_VOICES["Kore"]["name"])


class TestPcmToWav:
    def test_adds_a_44_byte_riff_header(self):
        pcm = b"\x00\x01" * 1000
        wav = pcm_to_wav(pcm)
        assert len(wav) == len(pcm) + 44
        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"

    def test_header_declares_24khz_mono_16bit(self):
        wav = pcm_to_wav(b"\x00\x01" * 100)
        channels, rate, _, _, bits = struct.unpack("<HIIHH", wav[22:36])
        assert channels == 1
        assert rate == 24000
        assert bits == 16

    def test_declared_sizes_match_the_payload(self):
        # 长度字段写错时播放器往往只播一半且不报错，最难查。
        pcm = b"\x00\x01" * 512
        wav = pcm_to_wav(pcm)
        assert struct.unpack("<I", wav[4:8])[0] == 36 + len(pcm)
        assert struct.unpack("<I", wav[40:44])[0] == len(pcm)

    def test_empty_pcm_still_produces_a_valid_header(self):
        wav = pcm_to_wav(b"")
        assert len(wav) == 44
        assert struct.unpack("<I", wav[40:44])[0] == 0


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status
        self.text = json.dumps(payload)

    @property
    def ok(self):
        return self.status_code == 200

    def json(self):
        return self._payload


def _audio_response(pcm: bytes, with_text_part=False):
    parts = []
    if with_text_part:
        parts.append({"text": "好的。"})
    parts.append({"inlineData": {"mimeType": "audio/l16; rate=24000; channels=1",
                                 "data": base64.b64encode(pcm).decode()}})
    return {"candidates": [{"content": {"parts": parts}}]}


@pytest.fixture
def captured(monkeypatch):
    box = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        box["url"], box["headers"], box["payload"] = url, headers or {}, json
        return _FakeResponse(_audio_response(b"\x11\x22" * 400))

    monkeypatch.setattr("src.audio.gemini_tts.requests.post", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-tts-key")
    return box


class TestSynthesis:
    def test_writes_a_playable_wav_not_raw_pcm(self, captured, tmp_path):
        out = tmp_path / "line.wav"
        path, delay, req_id = synthesize_gemini("你好", str(out), voice="Kore")

        assert path == str(out)
        data = out.read_bytes()
        assert data[:4] == b"RIFF", "落盘的必须是 WAV，裸 PCM 下游放不了"
        assert len(data) == 800 + 44

    def test_voice_name_reaches_the_speech_config(self, captured, tmp_path):
        synthesize_gemini("你好", str(tmp_path / "a.wav"), voice="Sulafat")
        cfg = captured["payload"]["generationConfig"]
        assert cfg["responseModalities"] == ["AUDIO"]
        assert cfg["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Sulafat"

    def test_api_key_travels_in_a_header(self, captured, tmp_path):
        synthesize_gemini("你好", str(tmp_path / "a.wav"), voice="Kore")
        assert captured["headers"].get("x-goog-api-key") == "gemini-tts-key"
        assert "gemini-tts-key" not in captured["url"]

    def test_instructions_become_a_style_directive(self, captured, tmp_path):
        # Gemini 的风格控制就是自然语言前缀，这是 instructions 唯一能落地的方式。
        synthesize_gemini("我不同意。", str(tmp_path / "a.wav"), voice="Kore",
                          instructions="用压抑的愤怒说")
        text = captured["payload"]["contents"][0]["parts"][0]["text"]
        assert "用压抑的愤怒说" in text
        assert "我不同意。" in text

    def test_non_default_speech_rate_is_expressed_in_words(self, captured, tmp_path):
        # 没有数值参数可传，只能转成语言描述；静默丢弃会让 UI 上的语速条骗人。
        synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="Kore", speech_rate=1.5)
        text = captured["payload"]["contents"][0]["parts"][0]["text"]
        assert any(k in text for k in ("快", "faster"))

    def test_default_speech_rate_adds_no_noise(self, captured, tmp_path):
        synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="Kore", speech_rate=1.0)
        text = captured["payload"]["contents"][0]["parts"][0]["text"]
        assert text.strip() == "台词"

    @staticmethod
    def _sent_voice(captured):
        cfg = captured["payload"]["generationConfig"]["speechConfig"]
        return cfg["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]

    def test_legacy_voice_id_is_migrated_not_merely_defaulted(self, captured, tmp_path):
        # 特意选 longzhe_v2 而不是 longxiaochun_v2：后者的迁移目标恰好就是
        # DEFAULT_VOICE(Kore)，用它做断言时即使迁移查表完全失效、只是回落到
        # 默认音色，测试也照样绿 —— 名字承诺的和实际验证的就不是一回事了。
        # longzhe_v2 → Achird，与默认值不同，能真正区分"迁移"和"兜底"。
        from src.audio.gemini_tts import DEFAULT_VOICE

        synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="longzhe_v2")

        sent = self._sent_voice(captured)
        assert sent == "Achird"
        assert sent != DEFAULT_VOICE, "该断言必须能区分迁移与默认兜底"

    def test_truly_unknown_voice_falls_back_to_the_default(self, captured, tmp_path):
        from src.audio.gemini_tts import DEFAULT_VOICE

        synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="never-existed-voice")
        assert self._sent_voice(captured) == DEFAULT_VOICE

    def test_text_only_response_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr("src.audio.gemini_tts.requests.post",
                            lambda *a, **k: _FakeResponse(
                                {"candidates": [{"content": {"parts": [{"text": "内容不合规"}]}}]}))
        with pytest.raises(RuntimeError, match="内容不合规|no audio"):
            synthesize_gemini("x", str(tmp_path / "a.wav"), voice="Kore")

    def test_http_error_surfaces_the_status(self, monkeypatch, tmp_path):
        # 400 是确定性失败（请求本身有问题），不重试，直接把状态码抛出去。
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr("src.audio.gemini_tts.requests.post",
                            lambda *a, **k: _FakeResponse({"error": {"message": "bad"}}, status=400))
        with pytest.raises(RuntimeError, match="400"):
            synthesize_gemini("x", str(tmp_path / "a.wav"), voice="Kore")

    def test_missing_key_fails_before_the_request(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr("src.audio.gemini_tts.requests.post",
                            lambda *a, **k: pytest.fail("缺 key 时不应发请求"))
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            synthesize_gemini("x", str(tmp_path / "a.wav"), voice="Kore")


class TestVoiceMigration:
    """存量 7 个 CosyVoice 音色 → Gemini 音色的迁移映射。"""

    @pytest.fixture
    def mapping(self):
        from src.audio.gemini_tts import load_voice_migration
        return load_voice_migration()

    LEGACY = {
        "longxiaochun_v2": ("Female", "龙小淳 知性女", 17),
        "longzhe_v2": ("Male", "龙哲 暖心男", 11),
        "longcheng_v2": ("Male", "龙诚 睿智青年", 8),
        "longze_v2": ("Male", "龙泽 阳光男", 6),
        "longxiaocheng_v2": ("Male", "龙小诚 低音男", 4),
        "longxiu_v2": ("Male", "龙修 博学男", 3),
        "longhan_v2": ("Male", "龙翰 深情男", 2),
    }

    def test_every_in_use_legacy_voice_is_covered(self, mapping):
        missing = [v for v in self.LEGACY if v not in mapping]
        assert not missing, f"漏映射的音色会让存量角色配音失效: {missing}"

    def test_targets_are_real_registered_voices(self, mapping):
        for legacy, target in mapping.items():
            assert target in GEMINI_VOICES, f"{legacy} 映射到了不存在的音色 {target}"

    def test_gender_is_preserved_for_every_mapping(self, mapping):
        """本文件最重要的一条断言。"""
        for legacy, (gender, label, _) in self.LEGACY.items():
            target = mapping[legacy]
            assert GEMINI_VOICES[target]["gender"] == gender, (
                f"{label} 是 {gender}，却被映射到 {target}"
                f"（{GEMINI_VOICES[target]['gender']}）—— 会毁掉已完成的配音"
            )

    def test_distinct_legacy_voices_do_not_collapse_onto_one(self, mapping):
        # 7 个角色音色全挤到一个上，等于全片一个人配音。
        targets = [mapping[v] for v in self.LEGACY]
        assert len(set(targets)) == len(targets)

    def test_unknown_voice_id_is_not_silently_remapped(self, mapping):
        assert "totally-unknown-voice" not in mapping


class TestProcessorIntegration:
    def test_list_voices_returns_the_gemini_registry(self):
        from src.audio.tts import TTSProcessor
        voices = TTSProcessor.list_voices()
        assert "Kore" in voices
        assert not any(k.startswith("long") for k in voices), \
            "CosyVoice 音色必须从列表消失，否则用户还能选到已下线的音色"

    def test_processor_no_longer_requires_dashscope(self, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        from src.audio.tts import TTSProcessor
        TTSProcessor()   # 不应因为缺 DashScope 凭证或缺 dashscope 包而抛错


class TestTransientRetry:
    """网络抖动必须能自愈。

    实测中遇到过 `ConnectionResetError(10054)` —— 对端强制关闭连接。配一整集
    台词是几十上百次连续调用，其中任意一次裸奔失败就会让整批配音中断，用户
    看到的是「配音失败」而不是「重试一次就好」。所以瞬时错误要有界重试，
    而鉴权、内容不合规这类确定性失败必须立刻抛，重试只是浪费时间和配额。
    """

    def test_connection_error_is_retried_and_can_succeed(self, monkeypatch, tmp_path):
        import requests as _rq
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _rq.exceptions.ConnectionError("Connection aborted.")
            return _FakeResponse(_audio_response(b"\x01\x02" * 100))

        monkeypatch.setattr("src.audio.gemini_tts.requests.post", flaky)
        monkeypatch.setattr("src.audio.gemini_tts.time.sleep", lambda *_: None)

        path, _, _ = synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="Kore")
        assert calls["n"] == 2
        assert open(path, "rb").read()[:4] == b"RIFF"

    def test_rate_limit_is_retried(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        calls = {"n": 0}

        def throttled(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResponse({"error": {"message": "quota"}}, status=429)
            return _FakeResponse(_audio_response(b"\x01\x02" * 100))

        monkeypatch.setattr("src.audio.gemini_tts.requests.post", throttled)
        monkeypatch.setattr("src.audio.gemini_tts.time.sleep", lambda *_: None)

        synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="Kore")
        assert calls["n"] == 2

    def test_auth_failure_is_not_retried(self, monkeypatch, tmp_path):
        # 401/403 重试只会烧时间，错的 key 再试一百次还是错的。
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        calls = {"n": 0}

        def denied(*a, **k):
            calls["n"] += 1
            return _FakeResponse({"error": {"message": "API key not valid"}}, status=403)

        monkeypatch.setattr("src.audio.gemini_tts.requests.post", denied)
        monkeypatch.setattr("src.audio.gemini_tts.time.sleep", lambda *_: None)

        with pytest.raises(RuntimeError, match="403"):
            synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="Kore")
        assert calls["n"] == 1

    def test_retries_are_bounded(self, monkeypatch, tmp_path):
        import requests as _rq
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        calls = {"n": 0}

        def always_down(*a, **k):
            calls["n"] += 1
            raise _rq.exceptions.ConnectionError("down")

        monkeypatch.setattr("src.audio.gemini_tts.requests.post", always_down)
        monkeypatch.setattr("src.audio.gemini_tts.time.sleep", lambda *_: None)

        with pytest.raises(RuntimeError):
            synthesize_gemini("台词", str(tmp_path / "a.wav"), voice="Kore")
        assert calls["n"] <= 4, "无上限重试会把一次网络故障变成一次挂起"
