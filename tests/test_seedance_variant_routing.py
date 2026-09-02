"""Seedance 变体必须按调用解析，且只走 Ark。

模型实例是缓存复用的（pipeline 的 self._byteplus_video_model），所以变体必须
每次调用现算。存到实例上会让上一次的选择泄漏到下一次生成里。

fast / mini 与标准版计费不同（fast 720p 约 0.12 USD/秒，标准版约 0.15），
所以解析不出来时 resolve_ark_model_id 返回 None 而不是猜一个默认值——静默
退回标准版会把 fast/mini 的调用算成标准版的账，这正是要避免的错误计费。
"""

import pytest

from src.models.byteplus import resolve_ark_model_id


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_plain_model_id_maps_to_the_standard_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.0-{mode}") == "dreamina-seedance-2-0-260128"


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_fast_model_id_maps_to_the_fast_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.0-fast-{mode}") == "dreamina-seedance-2-0-fast-260128"


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_mini_model_id_maps_to_the_mini_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.0-mini-{mode}") == "dreamina-seedance-2-0-mini-260615"


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_25_model_id_maps_to_the_25_ark_id(mode):
    assert resolve_ark_model_id(f"seedance-2.5-{mode}") == "dreamina-seedance-2-5-260628"


def test_canonical_mode_id_with_fast_is_recognised():
    """Catalog 规范 id 形如 seedance/seedance-2.0-fast-video#t2v。"""
    assert resolve_ark_model_id(
        "seedance/seedance-2.0-fast-video#t2v"
    ) == "dreamina-seedance-2-0-fast-260128"


def test_canonical_mode_id_without_variant_is_recognised():
    assert resolve_ark_model_id(
        "seedance/seedance-2.0-video#i2v"
    ) == "dreamina-seedance-2-0-260128"


def test_unknown_or_missing_model_id_returns_none():
    """调用方没传型号时不能猜；返回 None 让上层报错，而不是静默按标准版计费。"""
    assert resolve_ark_model_id(None) is None
    assert resolve_ark_model_id("") is None
    assert resolve_ark_model_id("something-else") is None


def test_consecutive_calls_do_not_leak_the_variant():
    """缓存的模型实例是共享的，解析必须是纯函数。"""
    fast = resolve_ark_model_id("seedance-2.0-fast-t2v")
    plain = resolve_ark_model_id("seedance-2.0-t2v")

    assert fast == "dreamina-seedance-2-0-fast-260128"
    assert plain == "dreamina-seedance-2-0-260128"
