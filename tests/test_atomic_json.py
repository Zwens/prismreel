import json
import os
import time

import pytest

from src.utils.atomic_json import (
    DataCorruptionError,
    atomic_write_json,
    load_json_strict,
)


def test_missing_file_returns_none(tmp_path):
    """文件不存在是合法的首次运行状态，不是错误。"""
    assert load_json_strict(str(tmp_path / "nope.json")) is None


def test_corrupt_file_raises(tmp_path):
    """损坏文件必须抛错，绝不能静默返回默认值 —— 那会导致下次写入覆盖全库。"""
    p = tmp_path / "broken.json"
    p.write_text('{"a": 1, "b":', encoding="utf-8")
    with pytest.raises(DataCorruptionError) as exc:
        load_json_strict(str(p))
    assert "broken.json" in str(exc.value)


def test_roundtrip(tmp_path):
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"k": {"n": 1}})
    assert load_json_strict(p) == {"k": {"n": 1}}


def test_no_temp_files_left_behind(tmp_path):
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"k": 1})
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert leftovers == []


def test_first_write_creates_no_backup(tmp_path):
    """没有原文件时不该产生备份。"""
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"v": 1})
    assert [f for f in os.listdir(tmp_path) if ".bak." in f] == []


def test_backup_created_on_overwrite(tmp_path):
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"v": 1})
    atomic_write_json(p, {"v": 2}, backup_interval_s=0)
    baks = sorted(f for f in os.listdir(tmp_path) if ".bak." in f)
    assert len(baks) == 1
    assert json.loads((tmp_path / baks[0]).read_text(encoding="utf-8")) == {"v": 1}
    assert load_json_strict(p) == {"v": 2}


def test_backup_interval_throttles(tmp_path):
    """121 个调用点每次都复制整库会很贵；间隔内不重复备份。"""
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"v": 1})
    for i in range(2, 6):
        atomic_write_json(p, {"v": i}, backup_interval_s=300)
    baks = [f for f in os.listdir(tmp_path) if ".bak." in f]
    assert len(baks) == 1


def test_backup_pruning(tmp_path):
    p = str(tmp_path / "d.json")
    atomic_write_json(p, {"v": 0})
    for i in range(1, 8):
        time.sleep(0.01)
        atomic_write_json(p, {"v": i}, backup_interval_s=0, backups=3)
    baks = [f for f in os.listdir(tmp_path) if ".bak." in f]
    assert len(baks) == 3


def test_creates_parent_dir(tmp_path):
    p = str(tmp_path / "deep" / "nested" / "d.json")
    atomic_write_json(p, {"v": 1})
    assert load_json_strict(p) == {"v": 1}
