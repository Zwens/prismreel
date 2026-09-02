"""计价数据与能力定义解耦，且折扣必须会过期。

原价入库、折扣单列，是因为限时活动到期后如果价格已被折后价覆盖，
就再也拿不回真实单价了。
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from src.utils.model_catalog import (
    GENERATED_MODEL_CATALOG_PATH,
    active_promotions,
    load_pricing,
)


def test_pricing_covers_every_active_video_model():
    pricing = load_pricing()
    for model_id in [
        "dreamina-seedance-2-5-260628",
        "dreamina-seedance-2-0-260128",
        "dreamina-seedance-2-0-fast-260128",
        "dreamina-seedance-2-0-mini-260615",
    ]:
        assert model_id in pricing, f"missing pricing for {model_id}"


def test_list_price_is_stored_not_the_discounted_one():
    """2.5 的 1080p 原价是 11.70；限时 28% off 只应出现在 promotions 里。"""
    entry = load_pricing()["dreamina-seedance-2-5-260628"]
    assert entry["online"]["1080p"]["without_video"] == 11.70
    assert entry["promotions"][0]["discount"] == 0.28


def test_reference_per_second_matches_the_vendor_table():
    """厂商给的典型场景折算：16:9、5 秒、无视频输入。"""
    entry = load_pricing()["dreamina-seedance-2-0-260128"]
    assert entry["reference_per_second"] == {
        "480p": 0.07, "720p": 0.15, "1080p": 0.37, "4k": 0.78,
    }


def test_expired_promotions_are_filtered_out():
    entry = {
        "promotions": [
            {"scope": ["1080p"], "discount": 0.28, "ends_at": "2026-09-17T14:00:00+08:00"},
        ]
    }
    before = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    after = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)

    assert len(active_promotions(entry, now=before)) == 1
    assert active_promotions(entry, now=after) == []


def test_pricing_is_merged_into_the_generated_catalog():
    catalog = json.loads(Path(GENERATED_MODEL_CATALOG_PATH).read_text(encoding="utf-8"))
    assert catalog["models"]["seedance-2.5-t2v"]["pricing"]["unit"] == "per_million_tokens"


def test_every_promotion_has_a_parsable_end_date():
    for model_id, entry in load_pricing().items():
        for promo in entry.get("promotions", []):
            assert "ends_at" in promo, f"{model_id} promotion without ends_at"
            dt.datetime.fromisoformat(promo["ends_at"])
