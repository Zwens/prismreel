"""Gemini 图像适配器：入参映射、参考图编码与返回体解析。

DashScope 下线后文生图 / 图生图由 Gemini 承担。三处容易悄悄出错、且出错时
不会报错只会出坏图的地方，用测试钉死：

1. **画幅**。项目内部用 "宽*高" 字符串（如 "576*1024"），Gemini 只认
   aspect_ratio 枚举。映射错了不会报错，只会默默出一张比例不对的图 —— 分镜
   里混进一张 1:1 的竖屏镜头，要到成片时才发现。
2. **参考图上限**。Gemini 单次最多 14 张参考图，超了会整个请求失败。角色
   参考图是逐个累加的，很容易越界，必须截断而不是让请求炸掉。
3. **返回体路径**。图像藏在 candidates[0].content.parts[*].inlineData.data，
   真实响应里 parts 可能同时含文本说明，取错下标就拿不到图。

API 形态取自 2026-09-08 对真实端点的实测：generateContent + responseModalities
可用且直接回 inlineData，比设计文档里写的 /v1beta/interactions 好解析（后者
把图埋在 steps[1].content[0].data）。
"""

import base64
import io
import json
import pytest

from src.models.gemini_image import GeminiImageModel, size_to_aspect_ratio


class TestSizeToAspectRatio:
    """项目里的 size 字符串 → Gemini 的 aspect_ratio 枚举。"""

    @pytest.mark.parametrize("size,expected", [
        ("1024*1024", "1:1"),
        ("576*1024", "9:16"),    # assets.py 里角色立绘的默认竖屏
        ("1024*576", "16:9"),    # assets.py 里场景图的默认横屏
        ("1024*1536", "2:3"),
        ("1536*1024", "3:2"),
        ("1024*1280", "4:5"),
        ("1280*1024", "5:4"),
        ("768*1024", "3:4"),
        ("1024*768", "4:3"),
        ("2560*1080", "21:9"),
    ])
    def test_known_sizes_map_to_supported_ratios(self, size, expected):
        assert size_to_aspect_ratio(size) == expected

    def test_odd_size_snaps_to_nearest_supported_ratio(self):
        # 1000x1010 几乎是方的，应落到 1:1 而不是报错或原样透传。
        assert size_to_aspect_ratio("1000*1010") == "1:1"

    @pytest.mark.parametrize("bad", [None, "", "abc", "1024", "0*0", "1024*0"])
    def test_unparseable_size_falls_back_to_square(self, bad):
        # 宁可出一张 1:1，也不要因为解析失败让整条分镜生成链断掉。
        assert size_to_aspect_ratio(bad) == "1:1"

    def test_result_is_always_a_supported_ratio(self):
        supported = {"1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
        for w in (256, 512, 999, 1920):
            for h in (256, 512, 999, 1080):
                assert size_to_aspect_ratio(f"{w}*{h}") in supported


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    @property
    def ok(self):
        return self.status_code == 200

    def json(self):
        return self._payload


def _image_response(data: bytes, mime="image/jpeg", with_text_part=True):
    """真实响应里 parts 常常先是一段文本说明，再是图 —— 复现这个形状。"""
    parts = []
    if with_text_part:
        parts.append({"text": "好的，这是生成的图像。"})
    parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}})
    return {"candidates": [{"content": {"parts": parts}}]}


@pytest.fixture
def captured(monkeypatch):
    """拦截 requests.post，记录请求体并回一张假图。"""
    box = {}

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        box["url"] = url
        box["headers"] = headers or {}
        box["payload"] = json
        return _FakeResponse(_image_response(b"\xff\xd8\xff\xe0FAKEJPEG"))

    monkeypatch.setattr("src.models.gemini_image.requests.post", fake_post)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    return box


class TestRequestShape:
    def test_prompt_and_aspect_ratio_reach_the_api(self, captured, tmp_path):
        out = tmp_path / "a.jpg"
        GeminiImageModel({}).generate("雨夜街头", str(out), size="576*1024")

        payload = captured["payload"]
        cfg = payload["generationConfig"]
        assert cfg["responseModalities"] == ["IMAGE"]
        assert cfg["imageConfig"]["aspectRatio"] == "9:16"
        texts = [p["text"] for p in payload["contents"][0]["parts"] if "text" in p]
        assert "雨夜街头" in texts[0]

    def test_api_key_is_sent_as_header_not_query(self, captured, tmp_path):
        GeminiImageModel({}).generate("x", str(tmp_path / "a.jpg"))
        assert captured["headers"].get("x-goog-api-key") == "gemini-test-key"
        assert "gemini-test-key" not in captured["url"], "key 不得出现在 URL 里，会进日志"

    def test_model_name_override_selects_the_endpoint(self, captured, tmp_path):
        GeminiImageModel({}).generate("x", str(tmp_path / "a.jpg"), model_name="gemini-3-pro-image")
        assert "gemini-3-pro-image:generateContent" in captured["url"]

    def test_default_model_is_flash_image(self, captured, tmp_path):
        GeminiImageModel({}).generate("x", str(tmp_path / "a.jpg"))
        assert "gemini-3.1-flash-image:generateContent" in captured["url"]

    def test_negative_prompt_is_folded_into_the_text(self, captured, tmp_path):
        # Gemini 没有独立的 negative_prompt 字段，只能并进提示词；
        # 静默丢弃会让"避免出现文字水印"这类约束失效且无人察觉。
        GeminiImageModel({}).generate("城市夜景", str(tmp_path / "a.jpg"), negative_prompt="文字, 水印")
        text = captured["payload"]["contents"][0]["parts"][-1]["text"]
        assert "文字, 水印" in text


class TestReferenceImages:
    def _png(self, tmp_path, name="ref.png"):
        p = tmp_path / name
        p.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        return str(p)

    def test_single_reference_is_inlined_before_the_prompt(self, captured, tmp_path):
        ref = self._png(tmp_path)
        GeminiImageModel({}).generate("换个场景", str(tmp_path / "o.jpg"), ref_image_path=ref)

        parts = captured["payload"]["contents"][0]["parts"]
        assert "inline_data" in parts[0], "参考图必须排在提示词之前，模型才会以它为准"
        assert parts[0]["inline_data"]["mime_type"] == "image/png"
        assert base64.b64decode(parts[0]["inline_data"]["data"]) == b"\x89PNG\r\n\x1a\nFAKE"

    def test_ref_image_paths_are_all_included(self, captured, tmp_path):
        refs = [self._png(tmp_path, f"r{i}.png") for i in range(3)]
        GeminiImageModel({}).generate("合成", str(tmp_path / "o.jpg"), ref_image_paths=refs)

        parts = captured["payload"]["contents"][0]["parts"]
        assert sum(1 for p in parts if "inline_data" in p) == 3

    def test_duplicate_references_are_deduped(self, captured, tmp_path):
        ref = self._png(tmp_path)
        GeminiImageModel({}).generate(
            "x", str(tmp_path / "o.jpg"), ref_image_path=ref, ref_image_paths=[ref, ref]
        )
        parts = captured["payload"]["contents"][0]["parts"]
        assert sum(1 for p in parts if "inline_data" in p) == 1

    def test_references_are_capped_at_the_api_limit(self, captured, tmp_path):
        # 超过 14 张 Gemini 会整个请求失败；截断保住这次生成，总比全炸好。
        refs = [self._png(tmp_path, f"r{i}.png") for i in range(20)]
        GeminiImageModel({}).generate("x", str(tmp_path / "o.jpg"), ref_image_paths=refs)

        parts = captured["payload"]["contents"][0]["parts"]
        assert sum(1 for p in parts if "inline_data" in p) == 14

    def test_missing_reference_file_is_skipped_not_fatal(self, captured, tmp_path):
        good = self._png(tmp_path)
        GeminiImageModel({}).generate(
            "x", str(tmp_path / "o.jpg"),
            ref_image_paths=[good, str(tmp_path / "gone.png")],
        )
        parts = captured["payload"]["contents"][0]["parts"]
        assert sum(1 for p in parts if "inline_data" in p) == 1


class TestResponseHandling:
    def test_image_is_written_to_the_requested_path(self, captured, tmp_path):
        out = tmp_path / "sub" / "img.jpg"
        path, elapsed = GeminiImageModel({}).generate("x", str(out))

        assert path == str(out)
        assert out.read_bytes() == b"\xff\xd8\xff\xe0FAKEJPEG"
        assert elapsed >= 0

    def test_text_only_response_raises_with_a_readable_reason(self, monkeypatch, tmp_path):
        # 安全过滤命中时 Gemini 会只回文本。静默写出 0 字节文件会让下游在
        # 拼接视频时才炸，报错要停在这里。
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr(
            "src.models.gemini_image.requests.post",
            lambda *a, **k: _FakeResponse({"candidates": [{"content": {"parts": [{"text": "内容不合规"}]}}]}),
        )
        with pytest.raises(RuntimeError, match="内容不合规|no image"):
            GeminiImageModel({}).generate("x", str(tmp_path / "o.jpg"))

    def test_http_error_surfaces_status_and_body(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr(
            "src.models.gemini_image.requests.post",
            lambda *a, **k: _FakeResponse({"error": {"message": "API key not valid"}}, status=400),
        )
        with pytest.raises(RuntimeError, match="400"):
            GeminiImageModel({}).generate("x", str(tmp_path / "o.jpg"))

    def test_missing_api_key_fails_before_any_request(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        def explode(*a, **k):
            raise AssertionError("缺 key 时不应发出请求")

        monkeypatch.setattr("src.models.gemini_image.requests.post", explode)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiImageModel({}).generate("x", str(tmp_path / "o.jpg"))


class TestAdapterRouting:
    """按模型 id 前缀路由到 Gemini，其余保持原样。

    这一步不能把 default_adapter 直接换成 Gemini：wan / qwen-image 还没迁移，
    存量项目里 28 处引用仍指向它们，改默认会把这些请求送错供应商并出坏图。
    默认适配器的替换属于迁移第 4 步（wan 家族删除时）。
    """

    def test_gemini_ids_route_to_the_gemini_adapter(self):
        from src.models.image import resolve_image_adapter
        from src.models.gemini_image import GeminiImageModel

        for model_id in ("gemini-3.1-flash-image", "gemini-3-pro-image",
                         "gemini-3.1-flash-lite-image"):
            adapter = resolve_image_adapter(model_id, default_adapter=object())
            assert isinstance(adapter, GeminiImageModel), model_id

    def test_wan_and_qwen_still_reach_the_default_adapter(self):
        from src.models.image import resolve_image_adapter

        sentinel = object()
        for model_id in ("wan2.7-image-pro", "wan2.6-image", "qwen-image-2.0-pro"):
            assert resolve_image_adapter(model_id, sentinel) is sentinel, model_id

    def test_routing_is_case_insensitive(self):
        from src.models.image import resolve_image_adapter
        from src.models.gemini_image import GeminiImageModel

        adapter = resolve_image_adapter("GEMINI-3.1-Flash-Image", default_adapter=object())
        assert isinstance(adapter, GeminiImageModel)

    def test_adapter_instance_is_cached(self):
        from src.models.image import resolve_image_adapter

        a = resolve_image_adapter("gemini-3.1-flash-image", default_adapter=object())
        b = resolve_image_adapter("gemini-3-pro-image", default_adapter=object())
        assert a is b, "每次调用都新建适配器会丢掉连接复用"


class TestCatalogIntegration:
    """gemini 家族必须能被运行时目录加载器接受。

    scripts/validate_model_catalog.py 与 src/utils/model_catalog.py 是两套独立
    的校验路径：前者放行了 backend "google"，后者的 SUPPORTED_PROVIDER_BACKENDS
    白名单没有它，于是校验脚本报 PASSED、而整个测试套件在 collection 阶段就
    炸掉。任何新 backend 都必须同时进这两处，这条测试守住后半边。
    """

    def test_runtime_loader_accepts_the_gemini_family(self):
        from src.utils.model_catalog import build_catalog_dict

        catalog = build_catalog_dict()
        assert "gemini" in catalog["families"]
        assert catalog["families"]["gemini"]["default_backend"] == "google"

    def test_google_is_a_recognised_backend_in_both_registries(self):
        from src.utils.model_catalog import SUPPORTED_PROVIDER_BACKENDS as a
        from src.utils.provider_registry import SUPPORTED_PROVIDER_BACKENDS as b

        assert "google" in a
        assert "google" in b
        assert set(a) == set(b), "两处白名单一旦分叉，就会重现校验通过但运行时炸掉"

    def test_gemini_image_models_are_visible_for_selection(self):
        from src.utils.model_catalog import build_catalog_dict

        models = build_catalog_dict()["models"]
        ids = {m["id"] for m in models.values() if m.get("family") == "gemini"}             if isinstance(models, dict) else {m["id"] for m in models if m.get("family") == "gemini"}
        assert {"gemini-3.1-flash-image", "gemini-3-pro-image"} <= ids
