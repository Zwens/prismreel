"""Catalog 的 Seedance 参数必须与厂商文档一致。

依据：docs/api-reference/byteplus-ark-seedance-seedream.md（2026-09-02 抓取）。
在此之前 catalog 把 4K 挂在 2.5 上（它没有），2.0 上却没有（它有），
而 2.0-fast 开放了 1080p（它只到 720p）——三者都会让请求在 Ark 侧失败。
"""

import json
from pathlib import Path

import pytest

CATALOG = json.loads(
    (Path(__file__).resolve().parents[1]
     / "config" / "model_catalog" / "generated" / "model_catalog.json")
    .read_text(encoding="utf-8")
)
MODELS = CATALOG["models"]

MODES = ["t2v", "i2v", "r2v"]


@pytest.mark.parametrize("mode", MODES)
def test_25_has_no_4k(mode):
    params = MODELS[f"seedance-2.5-{mode}"]["params"]
    assert "4k" not in params["resolution"]["options"]
    assert params["resolution"]["options"] == ["480p", "720p", "1080p"]


@pytest.mark.parametrize("mode", MODES)
def test_20_standard_has_4k(mode):
    params = MODELS[f"seedance-2.0-{mode}"]["params"]
    assert params["resolution"]["options"] == ["480p", "720p", "1080p", "4k"]


@pytest.mark.parametrize("mode", MODES)
def test_20_fast_tops_out_at_720p(mode):
    params = MODELS[f"seedance-2.0-fast-{mode}"]["params"]
    assert params["resolution"]["options"] == ["480p", "720p"]


@pytest.mark.parametrize("mode", MODES)
def test_20_mini_exists_and_tops_out_at_720p(mode):
    params = MODELS[f"seedance-2.0-mini-{mode}"]["params"]
    assert params["resolution"]["options"] == ["480p", "720p"]


@pytest.mark.parametrize("model_id", [
    f"seedance-{v}-{m}"
    for v in ["2.0", "2.0-fast", "2.0-mini", "2.5"]
    for m in MODES
])
def test_default_resolution_matches_the_vendor_default(model_id):
    """厂商默认是 720p；catalog 之前一律写死 1080p，画质与成本都对不上。"""
    assert MODELS[model_id]["params"]["resolution"]["default"] == "720p"


@pytest.mark.parametrize("mode", MODES)
def test_25_duration_range(mode):
    duration = MODELS[f"seedance-2.5-{mode}"]["duration"]
    assert (duration["min"], duration["max"]) == (4, 30)


@pytest.mark.parametrize("model_id", [
    f"seedance-{v}-{m}"
    for v in ["2.0", "2.0-fast", "2.0-mini"]
    for m in MODES
])
def test_20_family_duration_range(model_id):
    duration = MODELS[model_id]["duration"]
    assert (duration["min"], duration["max"]) == (4, 15)


@pytest.mark.parametrize("model_id", [
    f"seedance-{v}-{m}"
    for v in ["2.0", "2.0-fast", "2.0-mini", "2.5"]
    for m in MODES
])
def test_duration_advertises_the_auto_option(model_id):
    """厂商的 duration 支持 -1（自动）。2.5 的默认值就是 -1，而滑杆表达不了它，
    所以用一个独立的布尔位声明「本模型接受自动时长」。"""
    assert MODELS[model_id]["duration"]["allow_auto"] is True
