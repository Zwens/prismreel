# V-1「首个完整成片」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 PrismReel 用一部剧走通全流程，产出带烧录字幕、BGM 自动闪避、电平归一的可直接发布成片，同时堵住现存的数据丢失路径。

**Architecture:** 在现有 `merge_videos()`（`pipeline.py:2798`，已是可用的 concat 实现）之上，抽出一个两趟渲染的 `RenderEngine`：第一趟 concat + 重编码，第二趟一次性完成音频链（ducking + loudnorm）与字幕烧录。字幕**不使用 ASR** —— 台词在 `frame.dialogue`、偏移在 `frame.dub_offset_ms`、TTS 音频时长用 ffprobe 探测，三者可精确推算时间码。数据层保持 JSON 不变（PostgreSQL 迁移是 V0 的事），只把写入改为原子替换、加载改为 fail-fast。

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / FFmpeg + FFprobe / pytest / Next.js 14 + React 18 + TypeScript + Tailwind + Zustand

## Global Constraints

- Python 3.11。测试从仓库根目录运行：`pytest tests/ -v`（配置见 `pyproject.toml` 的 `[tool.pytest.ini_options]`，`testpaths = ["tests"]`）。
- 代码风格：black line-length 100，isort profile black，flake8 max-line-length 100。
- **Git 提交信息中禁止出现 `Co-Authored-By` 行**（`AGENTS.md:7` 明确要求）。推送只推 `github` remote，忽略 `origin`。
- 新增 FastAPI 端点**一律用 `def` 而非 `async def`**（`api.py:1-22` 有完整审计说明：`async def` 里做阻塞 I/O 会冻结事件循环）。
- 前端只用语义配色 token（`bg-surface` / `text-text-secondary` / `border-glass-border` / `glass-panel` 等），禁止硬编码颜色。提交前跑 `npm run check:colors`。
- 前端所有文案走 `useTranslations`，`frontend/messages/zh.json` 与 `en.json` 必须同步新增同名 key。
- **禁止**把新功能加进这些已超标的文件：`StoryboardR2V.tsx`(2300行)、`ArtDirection.tsx`(1204行)、`SettingsPage.tsx`(1150行)、`Cast.tsx`(1078行)。
- 所有把用户可控字符串当本地路径打开的地方，必须走 `_safe_resolve_path`（`pipeline.py:38`）。
- FFmpeg 二进制路径一律通过 `get_ffmpeg_path()`（`src/utils/system_check.py:13`）获取，不要硬编码 `"ffmpeg"`。
- 本阶段**不改动**数据模型的存储后端（仍是 `output/*.json`），不引入 SQLAlchemy、不引入任务队列、不做鉴权。

---

## File Structure

**新建**

| 文件 | 职责 |
|---|---|
| `src/utils/atomic_json.py` | 原子 JSON 写入 + 滚动备份 + 严格加载（区分"文件不存在"与"文件损坏"） |
| `src/utils/media_probe.py` | ffprobe 封装：探测媒体时长与视频分辨率 |
| `src/apps/comic_gen/audio_mixer.py` | 纯函数：构建音频 filter_complex 字符串（ducking + loudnorm） |
| `src/apps/comic_gen/subtitle.py` | 字幕时间轴推算 + ASS 生成 + 样式模板 |
| `src/apps/comic_gen/editing.py` | `RenderEngine`：分段收集 + 两趟渲染编排 |
| `tests/test_atomic_json.py` | Task 1 |
| `tests/test_media_probe.py` | Task 2 |
| `tests/test_bgm_presets.py` | Task 3 |
| `tests/test_audio_mixer.py` | Task 4 |
| `tests/test_subtitle_timing.py` | Task 5 |
| `tests/test_subtitle_ass.py` | Task 6 |
| `tests/test_render_engine.py` | Task 7 |
| `frontend/src/components/assembly/SubtitlePanel.tsx` | 字幕 UI（新目录，不进 VideoAssembly.tsx） |

**修改**

| 文件 | 改动 |
|---|---|
| `src/utils/system_check.py` | 新增 `get_ffprobe_path()` |
| `src/apps/comic_gen/pipeline.py` | `_load_data`/`_save_data`/`_save_series_data_unlocked`/`_save_library_data_unlocked` 接原子写与严格加载；`merge_videos` 委托给 `RenderEngine`；新增字幕 CRUD 方法 |
| `src/apps/comic_gen/models.py` | 新增 `SubtitleStyle`、`SubtitleSettings`；`Script` 增加 `subtitle_settings` 字段 |
| `src/apps/comic_gen/audio.py` | BGM 预设增加 `available` 标记；新增 `verify_bgm_assets()` |
| `src/apps/comic_gen/api.py` | 新增 4 个字幕端点；启动时调用 `verify_bgm_assets()` |
| `frontend/src/lib/api.ts` | 新增 4 个字幕 API 方法 |
| `frontend/src/components/modules/VideoAssembly.tsx` | `AssemblyPhase` 增加 `"subtitle"`；tab 条增加一项；渲染 `<SubtitlePanel>` |
| `frontend/messages/zh.json` / `en.json` | 字幕文案 |
| `docker-compose.yml` / `Dockerfile.backend` | 确保 `output/presets/bgm/` 随镜像发布 |

**设计说明：为什么是两趟渲染而不是一趟**
一趟 `filter_complex` 同时做 concat + 转场 + 调色 + 音频 + 字幕是 V2「RenderEngine 完全体」的目标。V-1 采用两趟（Pass 1 concat 重编码、Pass 2 音频链 + 字幕烧录），因为：单趟的 filter graph 在分段数不定时极难调试，而 V-1 的目标是**正确产出第一个成片**，不是最快产出。Pass 2 把音频与字幕合并在一次 ffmpeg 调用里（字幕是视频滤镜、音频链是音频滤镜，互不冲突），所以只多一次编码而非两次。

---

## Task 1: 原子 JSON 写入与 fail-fast 加载

修复 B1（`pipeline.py:395-397` 解析失败静默 `return {}`，下次写入即用空 dict 覆盖全库）和 B2（三处 `open(path,'w')` 直接截断覆写）。

**Files:**
- Create: `src/utils/atomic_json.py`
- Create: `tests/test_atomic_json.py`
- Modify: `src/apps/comic_gen/pipeline.py:388-406`（`_load_data` / `_save_data`）
- Modify: `src/apps/comic_gen/pipeline.py:3873-3925`（series 与 library 的 load/save）

**Interfaces:**
- Consumes: 无
- Produces:
  - `class DataCorruptionError(Exception)`
  - `def load_json_strict(path: str) -> Optional[Any]` — 文件不存在返回 `None`；损坏抛 `DataCorruptionError`
  - `def atomic_write_json(path: str, payload: Any, *, backup_interval_s: int = 300, backups: int = 10) -> None`

---

- [ ] **Step 1: 写失败测试**

创建 `tests/test_atomic_json.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_atomic_json.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.atomic_json'`

- [ ] **Step 3: 实现 atomic_json**

创建 `src/utils/atomic_json.py`：

```python
"""Atomic JSON persistence with rolling backups.

Replaces the previous `open(path, 'w') + json.dump` pattern, which left a
truncated file if the process died mid-write, and the `except: return {}`
load pattern, which caused the *next* write to overwrite the whole store
with an empty dict.
"""

import glob
import json
import os
import shutil
import time
from typing import Any, Optional

from . import get_logger

logger = get_logger(__name__)


class DataCorruptionError(Exception):
    """Raised when a store file exists but cannot be parsed.

    Callers MUST NOT swallow this. Starting with an empty store means the
    next save silently destroys every project on disk.
    """


def load_json_strict(path: str) -> Optional[Any]:
    """Load JSON from `path`.

    Returns None when the file does not exist (legitimate first-run state).
    Raises DataCorruptionError when the file exists but is unparseable.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        backups = _list_backups(path)
        hint = (
            f" Recent backups available: {', '.join(os.path.basename(b) for b in backups[:3])}"
            if backups
            else " No backups found."
        )
        raise DataCorruptionError(
            f"Failed to parse {path}: {e}.{hint} "
            f"Refusing to start with an empty store — fix or restore the file first."
        ) from e


def atomic_write_json(
    path: str,
    payload: Any,
    *,
    backup_interval_s: int = 300,
    backups: int = 10,
) -> None:
    """Write `payload` to `path` atomically, rotating a backup first.

    Temp file lands in the same directory so os.replace stays atomic
    (cross-filesystem rename is not).
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)

    _maybe_backup(path, backup_interval_s=backup_interval_s, backups=backups)

    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _backup_glob(path: str) -> str:
    return f"{path}.bak.*"


def _list_backups(path: str) -> list:
    """Newest first."""
    return sorted(glob.glob(_backup_glob(path)), reverse=True)


def _maybe_backup(path: str, *, backup_interval_s: int, backups: int) -> None:
    if not os.path.exists(path) or backups <= 0:
        return

    existing = _list_backups(path)
    if existing and backup_interval_s > 0:
        try:
            if time.time() - os.path.getmtime(existing[0]) < backup_interval_s:
                return
        except OSError:
            pass

    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    try:
        shutil.copy2(path, f"{path}.bak.{stamp}")
    except OSError as e:
        logger.warning(f"Backup of {path} failed (continuing with write): {e}")
        return

    for stale in _list_backups(path)[backups:]:
        try:
            os.remove(stale)
        except OSError:
            pass
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_atomic_json.py -v`
Expected: 9 passed

- [ ] **Step 5: 提交工具模块**

```bash
git add src/utils/atomic_json.py tests/test_atomic_json.py
git commit -m "feat(storage): atomic JSON writes with rolling backups and strict loading"
```

- [ ] **Step 6: 接入 pipeline 的三个 store**

修改 `src/apps/comic_gen/pipeline.py`。

顶部 import 区加入：

```python
from ...utils.atomic_json import DataCorruptionError, atomic_write_json, load_json_strict
```

把 `_load_data`（`pipeline.py:388-397`）整个替换为：

```python
    def _load_data(self) -> Dict[str, Script]:
        data = load_json_strict(self.data_file)
        if data is None:
            return {}
        return {k: Script(**v) for k, v in data.items()}
```

把 `_save_data`（`pipeline.py:399-406`）整个替换为：

```python
    def _save_data(self):
        """Save data with thread lock to prevent concurrent write issues."""
        with self._save_lock:
            try:
                atomic_write_json(
                    self.data_file,
                    {k: v.model_dump() for k, v in self.scripts.items()},
                )
            except Exception as e:
                logger.error(f"Failed to save data: {e}")
```

> 注意 `.dict()` → `.model_dump()`：这同时修掉 B12（三个 store 中只有这一个还用 pydantic v1 API）。

把 `_load_series_data`（`pipeline.py:3873-3882`）替换为：

```python
    def _load_series_data(self) -> Dict[str, Series]:
        data = load_json_strict(self.series_data_file)
        if data is None:
            return {}
        return {k: Series(**v) for k, v in data.items()}
```

把 `_save_series_data_unlocked`（`pipeline.py:3884-3891`）替换为：

```python
    def _save_series_data_unlocked(self):
        """Save series data without acquiring the lock (caller must hold self._save_lock)."""
        try:
            atomic_write_json(
                self.series_data_file,
                {k: v.model_dump() for k, v in self.series_store.items()},
            )
        except Exception as e:
            logger.error(f"Failed to save series data: {e}")
```

把 `_load_library_data`（`pipeline.py:3902-3911`）替换为：

```python
    def _load_library_data(self) -> GlobalAssetLibrary:
        data = load_json_strict(self.library_data_file)
        if data is None:
            return GlobalAssetLibrary()
        return GlobalAssetLibrary(**data)
```

把 `_save_library_data_unlocked`（`pipeline.py:3913-3920`）替换为：

```python
    def _save_library_data_unlocked(self):
        """Save global library data without acquiring the lock (caller must hold self._save_lock)."""
        try:
            atomic_write_json(self.library_data_file, self.library_store.model_dump())
        except Exception as e:
            logger.error(f"Failed to save library data: {e}")
```

- [ ] **Step 7: 加 pipeline 集成测试**

追加到 `tests/test_atomic_json.py`：

```python
def test_pipeline_refuses_to_start_on_corrupt_store(tmp_path, monkeypatch):
    """回归 B1：损坏的 projects.json 必须让启动失败，而不是静默清空。"""
    from src.apps.comic_gen.pipeline import ComicGenPipeline

    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)
    with open("output/projects.json", "w", encoding="utf-8") as f:
        f.write('{"proj-1": {"id": "proj-1", ')  # 截断，模拟写到一半被杀

    with pytest.raises(DataCorruptionError):
        ComicGenPipeline()


def test_pipeline_starts_clean_when_no_store(tmp_path, monkeypatch):
    from src.apps.comic_gen.pipeline import ComicGenPipeline

    monkeypatch.chdir(tmp_path)
    p = ComicGenPipeline()
    assert p.scripts == {}
```

- [ ] **Step 8: 运行完整测试套件**

Run: `pytest tests/ -v`
Expected: 全部通过，包括新增的 11 个用例与现有全部用例。

> 若 `tests/test_local_only_flow.py` 等直接注入 store 的测试报错，是因为它们把 `data_file` 指向了不存在的路径 —— 那是合法的 `None` 分支，不应报错。若真报错，读取错误信息定位，不要为了让测试通过而放宽 `load_json_strict` 的严格性。

- [ ] **Step 9: 提交**

```bash
git add src/apps/comic_gen/pipeline.py tests/test_atomic_json.py
git commit -m "fix(storage): fail-fast on corrupt store files, atomic writes for all three stores

Fixes two data-loss paths:
- _load_data returned {} on parse failure, so the next save wiped every project
- All three stores truncated the target file before writing; a kill mid-write lost the store

Also unifies serialization on pydantic v2 model_dump()."
```

---

## Task 2: ffprobe 媒体探测

字幕时间码推算与 ASS 的 `PlayResX/Y` 都需要探测媒体时长和视频分辨率。

**Files:**
- Modify: `src/utils/system_check.py`（新增 `get_ffprobe_path`）
- Create: `src/utils/media_probe.py`
- Create: `tests/test_media_probe.py`

**Interfaces:**
- Consumes: `get_ffmpeg_path()`（`src/utils/system_check.py:13`）
- Produces:
  - `def get_ffprobe_path() -> Optional[str]`
  - `def probe_duration(path: str) -> float` — 秒，探测失败抛 `MediaProbeError`
  - `def probe_dimensions(path: str) -> Tuple[int, int]` — `(width, height)`
  - `class MediaProbeError(Exception)`

---

- [ ] **Step 1: 写失败测试**

创建 `tests/test_media_probe.py`：

```python
import os
import subprocess

import pytest

from src.utils.media_probe import MediaProbeError, probe_dimensions, probe_duration
from src.utils.system_check import get_ffmpeg_path, get_ffprobe_path

requires_ffmpeg = pytest.mark.skipif(
    not get_ffmpeg_path() or not get_ffprobe_path(),
    reason="ffmpeg/ffprobe not installed",
)


def test_get_ffprobe_path_returns_something_or_none():
    p = get_ffprobe_path()
    assert p is None or os.path.exists(p) or os.path.basename(p).startswith("ffprobe")


def test_probe_missing_file_raises():
    with pytest.raises(MediaProbeError):
        probe_duration("/definitely/not/here.mp4")


@pytest.fixture
def sample_video(tmp_path):
    """2 秒 320x240 测试视频 + 静音音轨。"""
    ff = get_ffmpeg_path()
    if not ff:
        pytest.skip("ffmpeg not installed")
    out = str(tmp_path / "sample.mp4")
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return out


@requires_ffmpeg
def test_probe_duration(sample_video):
    assert probe_duration(sample_video) == pytest.approx(2.0, abs=0.2)


@requires_ffmpeg
def test_probe_dimensions(sample_video):
    assert probe_dimensions(sample_video) == (320, 240)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_media_probe.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_ffprobe_path'`

- [ ] **Step 3: 新增 get_ffprobe_path**

在 `src/utils/system_check.py` 中，紧跟 `get_ffmpeg_path` 之后追加：

```python
def get_ffprobe_path() -> Optional[str]:
    """Get path to the ffprobe binary, mirroring get_ffmpeg_path resolution.

    ffprobe ships alongside ffmpeg in every distribution we support, so we
    derive it from the resolved ffmpeg path first and only fall back to PATH.
    """
    ffmpeg = get_ffmpeg_path()
    if ffmpeg:
        directory, name = os.path.split(ffmpeg)
        candidate = os.path.join(directory, name.replace("ffmpeg", "ffprobe", 1))
        if os.path.exists(candidate):
            return candidate
    return shutil.which("ffprobe")
```

确认 `src/utils/system_check.py` 顶部已 import `os`、`shutil` 与 `typing.Optional`；缺什么补什么。

- [ ] **Step 4: 实现 media_probe**

创建 `src/utils/media_probe.py`：

```python
"""Thin ffprobe wrapper for duration and dimension lookups.

Subtitle timing needs the real duration of each rendered shot and of each
TTS audio file; the ASS header needs the output resolution.
"""

import json
import os
import subprocess
from typing import Tuple

from .system_check import get_ffprobe_path

_TIMEOUT_S = 30


class MediaProbeError(Exception):
    """ffprobe could not read the file."""


def _run_ffprobe(path: str, args: list) -> dict:
    if not os.path.exists(path):
        raise MediaProbeError(f"File not found: {path}")

    ffprobe = get_ffprobe_path()
    if not ffprobe:
        raise MediaProbeError(
            "ffprobe not found. It ships with ffmpeg — install ffmpeg and restart."
        )

    cmd = [ffprobe, "-v", "error", "-print_format", "json", *args, path]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise MediaProbeError(f"ffprobe timed out on {path}") from e

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:400]
        raise MediaProbeError(f"ffprobe failed on {path}: {stderr}")

    try:
        return json.loads(result.stdout.decode(errors="replace"))
    except json.JSONDecodeError as e:
        raise MediaProbeError(f"ffprobe returned invalid JSON for {path}") from e


def probe_duration(path: str) -> float:
    """Duration in seconds."""
    data = _run_ffprobe(path, ["-show_entries", "format=duration"])
    raw = (data.get("format") or {}).get("duration")
    if raw is None:
        raise MediaProbeError(f"No duration reported for {path}")
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        raise MediaProbeError(f"Unparseable duration {raw!r} for {path}") from e


def probe_dimensions(path: str) -> Tuple[int, int]:
    """(width, height) of the first video stream."""
    data = _run_ffprobe(
        path,
        ["-select_streams", "v:0", "-show_entries", "stream=width,height"],
    )
    streams = data.get("streams") or []
    if not streams:
        raise MediaProbeError(f"No video stream in {path}")
    w, h = streams[0].get("width"), streams[0].get("height")
    if not w or not h:
        raise MediaProbeError(f"Missing dimensions in {path}")
    return int(w), int(h)
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_media_probe.py -v`
Expected: 4 passed（无 ffmpeg 环境下 2 passed, 2 skipped）

- [ ] **Step 6: 提交**

```bash
git add src/utils/system_check.py src/utils/media_probe.py tests/test_media_probe.py
git commit -m "feat(media): add ffprobe-backed duration and dimension probing"
```

---

## Task 3: BGM 素材落地与启动校验

`audio.py:23-32` 定义了 8 个 BGM 预设，`pipeline.py:2991 _maybe_apply_bgm_mux` 的混音实现是完整的，但 `output/presets/bgm/` 目录不存在，导致 `pipeline.py:3009-3011` 每次静默跳过 → 导出永远静音。前端 `VideoAssembly.tsx:436-446` 已有一条硬编码告警横幅。

**这一步零代码修复主路径**，代码改动只是把"静默跳过"变成"可见的缺失清单"。

**Files:**
- Create: `scripts/generate_placeholder_bgm.py`
- Create: `output/presets/bgm/*.mp3`（8 个占位音频，由上述脚本生成）
- Create: `output/presets/bgm/LICENSES.md`
- Modify: `src/apps/comic_gen/audio.py`（新增 `verify_bgm_assets`，预设增加 `available` 字段）
- Modify: `src/apps/comic_gen/api.py`（启动时校验 + `/bgm/presets` 返回 `available`）
- Modify: `Dockerfile.backend`（确保目录随镜像发布）
- Create: `tests/test_bgm_presets.py`

**Interfaces:**
- Consumes: `BGM_PRESETS`（`src/apps/comic_gen/audio.py:23`）、`get_bgm_presets()`（`audio.py:37`）
- Produces:
  - `def verify_bgm_assets() -> List[str]` — 返回缺失文件的相对路径列表
  - `get_bgm_presets()` 返回的每项新增 `"available": bool`

---

- [ ] **Step 1: 用 ffmpeg 生成 8 个占位音频**

**决策（2026-07-26，由人类伙伴确认）**：真实 BGM 是内容选型，需人工挑选并逐条核实授权，无法由本任务完成。本任务改为**生成可辨识的占位音频**，让渲染链路能端到端验证；真素材由人工替换。

创建 `scripts/generate_placeholder_bgm.py`：

```python
"""Generate recognisable placeholder BGM so the render chain can be verified.

These are NOT shippable music. Each preset gets a distinct chord and tempo so
you can tell by ear which one a render picked up. Replace with licensed audio
before any external release — see output/presets/bgm/LICENSES.md.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.apps.comic_gen.audio import BGM_PRESETS  # noqa: E402
from src.utils.system_check import get_ffmpeg_path  # noqa: E402

# (root_hz, third_hz, fifth_hz, tremolo_hz) — distinct per preset by ear.
_VOICINGS = {
    "calm_warm": (261.63, 329.63, 392.00, 0.4),
    "uplifting_pop": (329.63, 415.30, 493.88, 2.0),
    "epic_cinematic": (130.81, 164.81, 196.00, 0.8),
    "mystery_ambient": (146.83, 174.61, 220.00, 0.25),
    "sad_piano": (220.00, 261.63, 329.63, 0.5),
    "tension_drama": (110.00, 138.59, 155.56, 3.0),
    "lofi_chill": (196.00, 233.08, 293.66, 1.2),
    "fantasy_dreamy": (293.66, 369.99, 440.00, 0.6),
}

DURATION_S = 60
OUT_DIR = os.path.join("output", "presets", "bgm")


def main() -> int:
    ff = get_ffmpeg_path()
    if not ff:
        print("ffmpeg not found — cannot generate placeholders")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    for preset in BGM_PRESETS:
        pid = preset["id"]
        root, third, fifth, trem = _VOICINGS[pid]
        out = os.path.join(OUT_DIR, os.path.basename(preset["url"]))

        graph = (
            f"sine=frequency={root}:duration={DURATION_S}[a];"
            f"sine=frequency={third}:duration={DURATION_S}[b];"
            f"sine=frequency={fifth}:duration={DURATION_S}[c];"
            f"[a][b][c]amix=inputs=3:duration=longest,"
            f"tremolo=f={trem}:d=0.6,"
            f"volume=0.25,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={DURATION_S - 2}:d=2[out]"
        )
        cmd = [
            ff, "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={DURATION_S}",
            "-filter_complex", graph, "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k", out,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        print(f"  {os.path.basename(out)}  ({root:.0f}/{third:.0f}/{fifth:.0f} Hz, trem {trem})")

    print(f"\nGenerated {len(BGM_PRESETS)} placeholder tracks in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

运行：

```bash
python scripts/generate_placeholder_bgm.py
ls output/presets/bgm/*.mp3 | wc -l   # 应为 8
```

创建 `output/presets/bgm/LICENSES.md`：

```markdown
# BGM 素材授权记录

## ⚠️ 当前状态：全部为占位音频，不可对外发布

以下 8 个文件由 `scripts/generate_placeholder_bgm.py` 用 ffmpeg 合成
（正弦和弦 + tremolo），仅用于验证渲染链路能正确混入 BGM。
它们不是可用的配乐，替换前不要用于任何对外分发的成片。

| 文件 | 状态 | 来源 | 作者 | 许可证 | 日期 |
|---|---|---|---|---|---|
| calm_warm.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| uplifting_pop.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| epic_cinematic.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| mystery_ambient.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| sad_piano.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| tension_drama.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| lofi_chill.mp3 | 占位 | ffmpeg 合成 | — | — | — |
| fantasy_dreamy.mp3 | 占位 | ffmpeg 合成 | — | — | — |

## 替换真实素材时

1. 只用 CC0 / Public Domain。推荐：[Pixabay Music](https://pixabay.com/music/)
   （Pixabay Content License，允许商用免署名）、
   [Free Music Archive](https://freemusicarchive.org/) 的 CC0 条目。
   **不要用 CC-BY-NC**（禁止商用）。
2. **必须无人声** —— 有人声的 BGM 会与配音打架，sidechaincompress 也压不干净。
3. 时长 60-180 秒即可（渲染时 `-stream_loop -1` 自动循环）。
4. 文件名必须与 `src/apps/comic_gen/audio.py` 的 `BGM_PRESETS[*].url` 一致。
5. 替换后把上表该行的「状态」改为「已授权」并填齐来源/作者/许可证/日期。
```

- [ ] **Step 2: 写失败测试**

创建 `tests/test_bgm_presets.py`：

```python
import os

from src.apps.comic_gen.audio import BGM_PRESETS, get_bgm_presets, verify_bgm_assets

BGM_DIR = os.path.join("output", "presets", "bgm")


def test_all_presets_have_files():
    """回归：8 个预设的 catalog 存在但音频文件缺失，导致导出静音。"""
    missing = verify_bgm_assets()
    assert missing == [], (
        f"缺少 BGM 音频文件: {missing}. "
        f"请放置到 {BGM_DIR}/ —— 缺失会导致 _maybe_apply_bgm_mux 静默跳过，成片没有背景音乐。"
    )


def test_licenses_documented():
    assert os.path.exists(os.path.join(BGM_DIR, "LICENSES.md")), (
        "BGM 素材必须附 LICENSES.md 记录来源与许可证"
    )


def test_placeholder_status_is_visible():
    """占位音频不可对外发布 —— LICENSES.md 必须把这件事说清楚。

    这条测试是故意留下的提醒：等真实素材替换完、表里不再有「占位」，
    它自然就变成对「授权已登记」的断言。
    """
    with open(os.path.join(BGM_DIR, "LICENSES.md"), encoding="utf-8") as f:
        content = f.read()
    if "占位" in content:
        assert "不可对外发布" in content, (
            "LICENSES.md 中仍有占位音频，必须显著标注不可对外发布"
        )


def test_presets_expose_availability():
    presets = get_bgm_presets()
    assert len(presets) == len(BGM_PRESETS)
    for p in presets:
        assert "available" in p
        assert isinstance(p["available"], bool)
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_bgm_presets.py -v`
Expected: FAIL — `ImportError: cannot import name 'verify_bgm_assets'`

- [ ] **Step 4: 实现校验函数**

修改 `src/apps/comic_gen/audio.py`，把 `get_bgm_presets()`（`audio.py:37-40`）替换为：

```python
def _bgm_abs_path(rel_url: str) -> str:
    """Preset urls are relative to output/, e.g. 'presets/bgm/calm_warm.mp3'."""
    return os.path.join("output", rel_url)


def verify_bgm_assets() -> List[str]:
    """Return the relative urls of presets whose audio file is missing.

    The catalog and the mux implementation (pipeline._maybe_apply_bgm_mux)
    have always been complete; only the audio files were never shipped, so
    every export came out silent while the code logged at INFO and moved on.
    Surfacing the gap loudly is the whole point of this function.
    """
    return [p["url"] for p in BGM_PRESETS if not os.path.exists(_bgm_abs_path(p["url"]))]


def get_bgm_presets() -> List[Dict[str, Any]]:
    """PR-3k · Return BGM preset list with per-entry availability.

    UI displays these in the Mix phase picker; selected entry's url is
    stored on Script.bgm_url.
    """
    return [
        {**p, "available": os.path.exists(_bgm_abs_path(p["url"]))}
        for p in BGM_PRESETS
    ]
```

确认 `audio.py` 顶部已 import `os`、`List`、`Dict`、`Any`。

- [ ] **Step 5: 启动时告警**

在 `src/apps/comic_gen/api.py` 创建输出目录的位置（`api.py:95-98` 附近）之后追加：

```python
# BGM presets: the mux code path is complete but silently skips when the
# audio file is absent, which used to make every export silent. Warn loudly.
try:
    from .audio import verify_bgm_assets

    _missing_bgm = verify_bgm_assets()
    if _missing_bgm:
        logger.warning(
            f"[STARTUP] {len(_missing_bgm)} BGM preset file(s) missing — "
            f"exports using them will have no background music: {_missing_bgm}"
        )
except Exception as e:  # never block startup on a cosmetic check
    logger.warning(f"[STARTUP] BGM asset verification skipped: {e}")
```

- [ ] **Step 6: 确保随镜像/打包发布**

在 `Dockerfile.backend` 的 `COPY` 段落中确认 `output/presets/` 被包含。若 `.dockerignore` 排除了 `output/`，加一条例外：

```
output/*
!output/presets/
```

同样检查 `build.spec.template`（PyInstaller），把 `output/presets/bgm` 加入 `datas`。

- [ ] **Step 7: 运行确认通过**

Run: `pytest tests/test_bgm_presets.py -v`
Expected: 3 passed

- [ ] **Step 8: 手工验证端到端出声**

```bash
# 启动后端，在 UI 中给任一项目选一个 BGM，执行合并
# 后端日志应出现: [MERGE/BGM] muxing BGM dial=1.00 bgm=0.35 — calm_warm.mp3
# 不应出现: [MERGE/BGM] preset file missing
ffmpeg -i output/video/merged_*.mp4 -af volumedetect -f null - 2>&1 | grep mean_volume
# mean_volume 不应是 -91dB（静音）
```

- [ ] **Step 9: 提交**

```bash
git add scripts/generate_placeholder_bgm.py output/presets/bgm \
        src/apps/comic_gen/audio.py src/apps/comic_gen/api.py \
        Dockerfile.backend build.spec.template tests/test_bgm_presets.py
git commit -m "fix(audio): ship BGM preset files and surface missing assets

The mux path in _maybe_apply_bgm_mux was complete, but output/presets/bgm/
never existed, so every export silently came out without music.

Ships ffmpeg-synthesised placeholders so the render chain is verifiable end
to end; LICENSES.md marks them not-for-release pending licensed replacements."
```

> ⚠️ `output/` 整体在 `.gitignore` 里。提交前需在 `.gitignore` 加例外，与 Task 3 Step 6 的 `.dockerignore` 处理一致：
> ```
> output/*
> !output/presets/
> ```
> 若 `git add output/presets/bgm` 报「ignored by .gitignore」，先改 `.gitignore` 再提交，不要用 `git add -f` 绕过 —— 那样别人 clone 后目录还是空的。

---

## Task 4: 音频滤镜链构建器

把当前 `_maybe_apply_bgm_mux`（`pipeline.py:2991`）里内联的 filter_complex 抽成可测的纯函数，并加上 ducking 与 loudnorm。

**关键技术点**：`sidechaincompress` 的签名是 `[main][sidechain]sidechaincompress`。BGM 是 main、人声是 sidechain。人声轨要同时进侧链和最终混音，**必须先 `asplit=2` 成两路**，否则 filter graph 会因为一个输出被消费两次而报错。现有代码没有这一步。

**Files:**
- Create: `src/apps/comic_gen/audio_mixer.py`
- Create: `tests/test_audio_mixer.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `LOUDNORM_TARGET_I = -16.0` / `LOUDNORM_TARGET_TP = -1.5` / `LOUDNORM_TARGET_LRA = 11.0`
  - `def build_audio_filter(*, dialogue_level: int, bgm_level: int, has_bgm: bool, ducking: bool = True, normalize: bool = True) -> str` — 返回 filter_complex 字符串，输出标签固定为 `[aout]`

---

- [ ] **Step 1: 写失败测试**

创建 `tests/test_audio_mixer.py`：

```python
import pytest

from src.apps.comic_gen.audio_mixer import build_audio_filter


def test_no_bgm_normalizes_only():
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=False)
    assert "amix" not in f
    assert "sidechaincompress" not in f
    assert "loudnorm=I=-16" in f
    assert f.endswith("[aout]")


def test_no_bgm_without_normalize_is_passthrough_volume():
    f = build_audio_filter(
        dialogue_level=80, bgm_level=35, has_bgm=False, normalize=False
    )
    assert "volume=0.800" in f
    assert "loudnorm" not in f
    assert f.endswith("[aout]")


def test_bgm_with_ducking_splits_dialogue():
    """人声既要进混音又要做侧链 —— 不 asplit 会让 filter graph 报错。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    assert "asplit=2" in f
    assert "sidechaincompress" in f
    assert "amix=inputs=2" in f
    assert "loudnorm" in f
    assert f.endswith("[aout]")


def test_ducking_sidechain_order():
    """必须是 [bgm][dialogue]sidechaincompress —— 反了就变成人声被BGM压。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    seg = next(s for s in f.split(";") if "sidechaincompress" in s)
    assert seg.startswith("[bgm_raw][dial_sc]"), seg


def test_ducking_disabled_skips_sidechain():
    f = build_audio_filter(
        dialogue_level=100, bgm_level=35, has_bgm=True, ducking=False
    )
    assert "sidechaincompress" not in f
    assert "amix=inputs=2" in f


def test_bgm_loops():
    """BGM 通常比片子短，必须循环，否则后半段没音乐。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    assert "aloop=loop=-1" in f


def test_levels_are_clamped():
    f = build_audio_filter(dialogue_level=500, bgm_level=-20, has_bgm=True)
    assert "volume=1.000" in f
    assert "volume=0.000" in f


def test_no_duplicate_labels():
    """同一个标签被定义两次是 filter graph 最常见的错误。"""
    f = build_audio_filter(dialogue_level=100, bgm_level=35, has_bgm=True)
    produced = []
    for seg in f.split(";"):
        tail = seg[seg.rindex("]", 0, len(seg)) :] if seg.endswith("]") else ""
        if tail:
            produced.append(tail)
    assert len(produced) == len(set(produced)), produced
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_audio_mixer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.comic_gen.audio_mixer'`

- [ ] **Step 3: 实现**

创建 `src/apps/comic_gen/audio_mixer.py`：

```python
"""Audio filter graph construction for the final render.

Extracted from the inline filter string in pipeline._maybe_apply_bgm_mux so
the graph can be unit-tested without invoking ffmpeg, and extended with
sidechain ducking plus loudness normalisation.

Input convention (set by the caller's -i order):
    [0:a] = dialogue / original program audio of the concatenated video
    [1:a] = background music (only present when has_bgm is True)
Output label is always [aout].
"""

# EBU R128 targets. -16 LUFS is the de-facto loudness for short-form
# vertical video platforms; -1.5 dBTP leaves headroom for lossy re-encode.
LOUDNORM_TARGET_I = -16.0
LOUDNORM_TARGET_TP = -1.5
LOUDNORM_TARGET_LRA = 11.0

# Ducking: fire early and release slowly so music dips before a line starts
# and recovers between lines instead of pumping on every syllable.
_DUCK_THRESHOLD = 0.05
_DUCK_RATIO = 8
_DUCK_ATTACK_MS = 20
_DUCK_RELEASE_MS = 300


def _level(pct: int) -> float:
    return max(0, min(100, int(pct))) / 100.0


def _loudnorm() -> str:
    return (
        f"loudnorm=I={LOUDNORM_TARGET_I}"
        f":TP={LOUDNORM_TARGET_TP}"
        f":LRA={LOUDNORM_TARGET_LRA}"
    )


def build_audio_filter(
    *,
    dialogue_level: int,
    bgm_level: int,
    has_bgm: bool,
    ducking: bool = True,
    normalize: bool = True,
) -> str:
    """Build the -filter_complex string for the final audio mix.

    Args:
        dialogue_level: 0-100 gain for the program audio.
        bgm_level: 0-100 gain for the background music.
        has_bgm: whether a second audio input [1:a] is present.
        ducking: sidechain-compress the music against the dialogue.
        normalize: apply EBU R128 loudness normalisation to the result.

    Returns:
        A filter_complex string whose final output label is [aout].
    """
    dial = _level(dialogue_level)
    bgm = _level(bgm_level)
    parts = []

    if not has_bgm:
        if normalize:
            parts.append(f"[0:a]volume={dial:.3f},apad,{_loudnorm()}[aout]")
        else:
            parts.append(f"[0:a]volume={dial:.3f},apad[aout]")
        return ";".join(parts)

    if ducking:
        # asplit is mandatory: the dialogue stream feeds both the mix and the
        # sidechain detector, and a filter output can only be consumed once.
        parts.append(f"[0:a]volume={dial:.3f},apad,asplit=2[dial_mix][dial_sc]")
        parts.append(f"[1:a]volume={bgm:.3f},aloop=loop=-1:size=2e9[bgm_raw]")
        parts.append(
            f"[bgm_raw][dial_sc]sidechaincompress="
            f"threshold={_DUCK_THRESHOLD}"
            f":ratio={_DUCK_RATIO}"
            f":attack={_DUCK_ATTACK_MS}"
            f":release={_DUCK_RELEASE_MS}[bgm_ducked]"
        )
        mix_inputs = "[dial_mix][bgm_ducked]"
    else:
        parts.append(f"[0:a]volume={dial:.3f},apad[dial_mix]")
        parts.append(f"[1:a]volume={bgm:.3f},aloop=loop=-1:size=2e9[bgm_ducked]")
        mix_inputs = "[dial_mix][bgm_ducked]"

    mix_out = "[aout]" if not normalize else "[mixed]"
    parts.append(
        f"{mix_inputs}amix=inputs=2:duration=first:dropout_transition=0{mix_out}"
    )
    if normalize:
        parts.append(f"[mixed]{_loudnorm()}[aout]")

    return ";".join(parts)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_audio_mixer.py -v`
Expected: 8 passed

- [ ] **Step 5: 用真实 ffmpeg 验证 filter graph 合法**

这一步很重要 —— 单元测试只验证字符串形状，不验证 ffmpeg 是否接受。追加到 `tests/test_audio_mixer.py`：

```python
import subprocess

from src.utils.system_check import get_ffmpeg_path

requires_ffmpeg = pytest.mark.skipif(
    not get_ffmpeg_path(), reason="ffmpeg not installed"
)


@requires_ffmpeg
@pytest.mark.parametrize("ducking", [True, False])
def test_graph_accepted_by_ffmpeg(tmp_path, ducking):
    """字符串形状对不代表 ffmpeg 认 —— 真跑一遍。"""
    ff = get_ffmpeg_path()
    out = str(tmp_path / f"mix_{ducking}.wav")
    f = build_audio_filter(
        dialogue_level=100, bgm_level=35, has_bgm=True, ducking=ducking
    )
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=220:duration=1",
            "-filter_complex", f,
            "-map", "[aout]", "-t", "3",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert os.path.exists(out)


@requires_ffmpeg
def test_no_bgm_graph_accepted_by_ffmpeg(tmp_path):
    ff = get_ffmpeg_path()
    out = str(tmp_path / "solo.wav")
    f = build_audio_filter(dialogue_level=80, bgm_level=0, has_bgm=False)
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-filter_complex", f,
            "-map", "[aout]", "-t", "3",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert os.path.exists(out)
```

需要在文件顶部补 `import os`。

- [ ] **Step 6: 运行**

Run: `pytest tests/test_audio_mixer.py -v`
Expected: 11 passed（无 ffmpeg 则 8 passed, 3 skipped）

- [ ] **Step 7: 提交**

```bash
git add src/apps/comic_gen/audio_mixer.py tests/test_audio_mixer.py
git commit -m "feat(audio): filter graph builder with sidechain ducking and loudnorm

Dialogue is asplit into mix + sidechain paths; a filter output can only be
consumed once, so the previous inline graph could not have supported ducking."
```

---

## Task 5: 字幕时间轴推算

**核心设计：不用 ASR。** 台词已在 `frame.dialogue`（`models.py:361`），偏移已在 `frame.dub_offset_ms`（`models.py:415`），TTS 音频在 `frame.audio_url`（`models.py:403`）可用 ffprobe 测长。时间码可精确推算，比 ASR 准确且零成本。

**Files:**
- Create: `src/apps/comic_gen/subtitle.py`（本任务只做时间轴部分）
- Create: `tests/test_subtitle_timing.py`

**Interfaces:**
- Consumes: `probe_duration`（Task 2）、`StoryboardFrame`（`models.py:352`）
- Produces:
  - `@dataclass class RenderSegment: frame_id: str; video_path: str; duration_s: float`
  - `@dataclass class SubtitleCue: start_s: float; end_s: float; text: str; speaker: Optional[str]`
  - `CHARS_PER_SECOND = 5.0` / `MIN_CUE_S = 0.8`
  - `def build_subtitle_cues(frames: List[StoryboardFrame], segments: List[RenderSegment], *, probe: Callable[[str], float] = probe_duration) -> List[SubtitleCue]`

`probe` 参数可注入，让时间轴逻辑不依赖真实文件即可测试。

---

- [ ] **Step 1: 写失败测试**

创建 `tests/test_subtitle_timing.py`：

```python
import pytest

from src.apps.comic_gen.models import StoryboardFrame
from src.apps.comic_gen.subtitle import (
    MIN_CUE_S,
    RenderSegment,
    build_subtitle_cues,
)


def _frame(fid, dialogue=None, offset_ms=0, audio_url=None):
    # StoryboardFrame requires id + scene_id (models.py:353-354); there is no
    # `description` field — the free-text field is `action_description`.
    return StoryboardFrame(
        id=fid,
        scene_id="sc1",
        dialogue=dialogue,
        dub_offset_ms=offset_ms,
        audio_url=audio_url,
    )


def _seg(fid, dur):
    return RenderSegment(frame_id=fid, video_path=f"/x/{fid}.mp4", duration_s=dur)


def test_cues_are_cumulative_across_shots():
    frames = [_frame("a", "第一句", audio_url="/a.mp3"), _frame("b", "第二句", audio_url="/b.mp3")]
    segs = [_seg("a", 5.0), _seg("b", 4.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 2.0)

    assert len(cues) == 2
    assert cues[0].start_s == pytest.approx(0.0)
    assert cues[0].end_s == pytest.approx(2.0)
    assert cues[1].start_s == pytest.approx(5.0)   # 第二段从第一段结束处开始
    assert cues[1].end_s == pytest.approx(7.0)


def test_dub_offset_shifts_start():
    frames = [_frame("a", "台词", offset_ms=1500, audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 6.0)], probe=lambda p: 2.0)
    assert cues[0].start_s == pytest.approx(1.5)
    assert cues[0].end_s == pytest.approx(3.5)


def test_frames_without_dialogue_are_skipped_but_still_advance_clock():
    frames = [_frame("a"), _frame("b", "只有这句有台词", audio_url="/b.mp3")]
    segs = [_seg("a", 3.0), _seg("b", 4.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 2.0)

    assert len(cues) == 1
    assert cues[0].start_s == pytest.approx(3.0)


def test_blank_dialogue_treated_as_absent():
    frames = [_frame("a", "   ")]
    assert build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 2.0) == []


def test_estimates_duration_when_no_audio():
    """没生成 TTS 时用阅读速度兜底，不能让字幕消失。"""
    frames = [_frame("a", "十个字的一句话啊")]  # 8 chars
    cues = build_subtitle_cues(frames, [_seg("a", 10.0)], probe=lambda p: 99.0)
    assert cues[0].end_s == pytest.approx(8 / 5.0)


def test_cue_clamped_to_shot_end():
    """TTS 比镜头长时，字幕不能溢出到下一镜头。"""
    frames = [_frame("a", "很长的台词", audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 10.0)
    assert cues[0].end_s == pytest.approx(3.0)


def test_minimum_cue_duration_enforced():
    """偏移把起点推到镜头末尾时，仍要保证可读的最短时长。"""
    frames = [_frame("a", "短", offset_ms=2900, audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 3.0)], probe=lambda p: 0.1)
    assert cues[0].end_s - cues[0].start_s == pytest.approx(MIN_CUE_S)


def test_probe_failure_falls_back_to_estimate():
    def boom(path):
        raise RuntimeError("ffprobe exploded")

    frames = [_frame("a", "十个字的一句话啊", audio_url="/a.mp3")]
    cues = build_subtitle_cues(frames, [_seg("a", 10.0)], probe=boom)
    assert cues[0].end_s == pytest.approx(8 / 5.0)


def test_speaker_from_structured_dialogue():
    from src.apps.comic_gen.models import DialogueStructured

    f = _frame("a", "你好", audio_url="/a.mp3")
    f.dialogue_structured = DialogueStructured(speaker="林一", line="你好")
    cues = build_subtitle_cues([f], [_seg("a", 4.0)], probe=lambda p: 1.5)
    assert cues[0].speaker == "林一"


def test_segments_without_matching_frame_are_ignored():
    frames = [_frame("a", "台词", audio_url="/a.mp3")]
    segs = [_seg("ghost", 2.0), _seg("a", 4.0)]
    cues = build_subtitle_cues(frames, segs, probe=lambda p: 1.0)
    assert cues[0].start_s == pytest.approx(2.0)  # ghost 段仍然推进时钟
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_subtitle_timing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.comic_gen.subtitle'`

- [ ] **Step 3: 实现时间轴部分**

创建 `src/apps/comic_gen/subtitle.py`：

```python
"""Subtitle generation from script data — deliberately not from ASR.

The dialogue text is authored in the app (StoryboardFrame.dialogue), the
TTS audio is synthesised by the app (StoryboardFrame.audio_url), and the
per-shot offset is already tracked (StoryboardFrame.dub_offset_ms). That is
strictly more information than speech recognition could recover, so running
ASR over our own output would only introduce transcription errors and cost.

ASR stays available as a V2 fallback for imported external audio.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from ...utils.media_probe import probe_duration
from .models import StoryboardFrame

# Comfortable Chinese subtitle reading rate. Also the fallback cue length
# when no TTS audio exists yet.
CHARS_PER_SECOND = 5.0
# Below this a cue flashes past unreadably.
MIN_CUE_S = 0.8


@dataclass
class RenderSegment:
    """One shot as it will appear in the concatenated output."""

    frame_id: str
    video_path: str
    duration_s: float


@dataclass
class SubtitleCue:
    start_s: float
    end_s: float
    text: str
    speaker: Optional[str] = None


def _estimate_duration(text: str) -> float:
    return max(MIN_CUE_S, len(text) / CHARS_PER_SECOND)


def _spoken_duration(
    frame: StoryboardFrame, text: str, probe: Callable[[str], float]
) -> float:
    """Real TTS length when available, reading-rate estimate otherwise."""
    if not frame.audio_url:
        return _estimate_duration(text)
    try:
        return probe(frame.audio_url)
    except Exception:
        # A missing or unreadable audio file must not drop the subtitle.
        return _estimate_duration(text)


def build_subtitle_cues(
    frames: List[StoryboardFrame],
    segments: List[RenderSegment],
    *,
    probe: Callable[[str], float] = probe_duration,
) -> List[SubtitleCue]:
    """Map dialogue onto the concatenated timeline.

    `segments` must be in render order and carry real measured durations —
    the cumulative sum of those durations is the output timeline. Segments
    with no matching frame still advance the clock so later cues stay aligned.
    """
    by_id = {f.id: f for f in frames}
    cues: List[SubtitleCue] = []
    offset = 0.0

    for seg in segments:
        frame = by_id.get(seg.frame_id)
        if frame is None:
            offset += seg.duration_s
            continue

        text = (frame.dialogue or "").strip()
        if not text:
            offset += seg.duration_s
            continue

        shot_end = offset + seg.duration_s
        start = offset + (frame.dub_offset_ms or 0) / 1000.0
        start = min(start, max(offset, shot_end - MIN_CUE_S))

        end = start + _spoken_duration(frame, text, probe)
        end = min(end, shot_end)
        if end - start < MIN_CUE_S:
            end = start + MIN_CUE_S

        speaker = frame.dialogue_structured.speaker if frame.dialogue_structured else None
        cues.append(SubtitleCue(start_s=start, end_s=end, text=text, speaker=speaker))
        offset = shot_end

    return cues
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_subtitle_timing.py -v`
Expected: 10 passed

- [ ] **Step 5: 提交**

```bash
git add src/apps/comic_gen/subtitle.py tests/test_subtitle_timing.py
git commit -m "feat(subtitle): derive cue timing from script dialogue and TTS duration

No ASR: the app authored the text and synthesised the audio, so exact
timings are already known. ASR would only add transcription error."
```

---

## Task 6: ASS 生成与样式模板

**Files:**
- Modify: `src/apps/comic_gen/subtitle.py`（追加 ASS 部分）
- Modify: `src/apps/comic_gen/models.py`（新增 `SubtitleStyle` / `SubtitleSettings`，`Script` 加字段）
- Create: `tests/test_subtitle_ass.py`

**Interfaces:**
- Consumes: `SubtitleCue`（Task 5）
- Produces:
  - `SUBTITLE_TEMPLATES: Dict[str, SubtitleStyle]` — key: `"douyin"` / `"cinematic"`
  - `def render_ass(cues, style, *, play_res: Tuple[int, int]) -> str`
  - `def wrap_cjk(text: str, per_line: int, max_lines: int) -> str`
  - models: `class SubtitleStyle(BaseModel)` / `class SubtitleSettings(BaseModel)`；`Script.subtitle_settings: SubtitleSettings`

**ASS 格式要点（容易写错，务必照抄）**
- 颜色是 `&HAABBGGRR` —— **BGR 顺序 + 前置 alpha**，`00` 表示不透明。白色 = `&H00FFFFFF`，黑色 = `&H00000000`。
- 时间是 `H:MM:SS.CC`（**厘秒两位**，不是毫秒三位）。
- `Alignment` 用 numpad 数字：`2` = 底部居中，`8` = 顶部居中，`5` = 正中。
- `PlayResX/Y` 必须等于输出视频分辨率，否则字号会被缩放到不对。

---

- [ ] **Step 1: 新增数据模型**

在 `src/apps/comic_gen/models.py` 中 `class Script(BaseModel)` 定义**之前**插入：

```python
class SubtitleStyle(BaseModel):
    """ASS style parameters. Colors are #RRGGBB; conversion to the ASS
    &HAABBGGRR form happens in subtitle.render_ass."""

    font_family: str = Field("Alibaba PuHuiTi", description="字体名（需在渲染机上已安装）")
    font_size: int = Field(64, description="字号，基于 1080x1920 参考分辨率")
    primary_color: str = Field("#FFFFFF", description="字体颜色 #RRGGBB")
    outline_color: str = Field("#000000", description="描边颜色 #RRGGBB")
    outline_width: int = Field(3, description="描边宽度")
    bold: bool = Field(True)
    alignment: int = Field(2, description="ASS numpad 对齐：2=底部居中, 8=顶部居中, 5=正中")
    margin_v: int = Field(180, description="垂直边距，避开平台 UI 遮挡区")
    chars_per_line: int = Field(18, description="每行字数，超出自动换行")
    max_lines: int = Field(2, description="最大行数，超出截断并加省略号")


class SubtitleSettings(BaseModel):
    """Per-project subtitle configuration."""

    enabled: bool = Field(True, description="导出时是否烧录字幕")
    template_id: str = Field("douyin", description="样式模板 id：douyin / cinematic")
    style_override: Optional[SubtitleStyle] = Field(
        None, description="非空时覆盖模板样式"
    )
```

在 `class Script(BaseModel)` 内部，紧跟 `mix_settings`（`models.py:562`）之后加一个字段：

```python
    # V-1 · Burned-in subtitle configuration. Cues are derived from frame
    # dialogue + TTS timing at render time, not stored.
    subtitle_settings: SubtitleSettings = Field(
        default_factory=SubtitleSettings,
        description="字幕烧录配置（时间码在渲染时从台词与 TTS 时长推算）",
    )
```

- [ ] **Step 2: 写失败测试**

创建 `tests/test_subtitle_ass.py`：

```python
import pytest

from src.apps.comic_gen.subtitle import (
    SUBTITLE_TEMPLATES,
    SubtitleCue,
    render_ass,
    wrap_cjk,
)


def test_two_templates_exist():
    assert set(SUBTITLE_TEMPLATES) == {"douyin", "cinematic"}


def test_douyin_avoids_platform_ui():
    assert SUBTITLE_TEMPLATES["douyin"].margin_v >= 150


def test_wrap_short_text_unchanged():
    assert wrap_cjk("短句", 18, 2) == "短句"


def test_wrap_inserts_ass_newline():
    text = "一" * 25
    out = wrap_cjk(text, 18, 2)
    assert out == "一" * 18 + r"\N" + "一" * 7


def test_wrap_truncates_beyond_max_lines():
    text = "一" * 60
    out = wrap_cjk(text, 18, 2)
    assert out.count(r"\N") == 1
    assert out.endswith("…")


def test_ass_has_required_sections():
    ass = render_ass([], SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass


def test_color_conversion_is_bgr_with_alpha():
    """ASS 用 &HAABBGGRR —— 写成 RGB 会让红蓝对调。"""
    style = SUBTITLE_TEMPLATES["douyin"].model_copy(
        update={"primary_color": "#FF0000", "outline_color": "#00FF00"}
    )
    ass = render_ass([], style, play_res=(1080, 1920))
    assert "&H000000FF" in ass  # 红 RGB=FF0000 → BGR=0000FF
    assert "&H0000FF00" in ass  # 绿 RGB=00FF00 → BGR=00FF00


def test_timecode_format_is_centiseconds():
    cues = [SubtitleCue(start_s=0.0, end_s=3.456, text="你好")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "0:00:00.00,0:00:03.45" in ass


def test_timecode_handles_hours():
    cues = [SubtitleCue(start_s=3723.5, end_s=3725.0, text="很久以后")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "1:02:03.50,1:02:05.00" in ass


def test_dialogue_line_per_cue():
    cues = [
        SubtitleCue(start_s=0.0, end_s=1.0, text="第一句"),
        SubtitleCue(start_s=1.0, end_s=2.0, text="第二句"),
    ]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert len([ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]) == 2


def test_braces_are_escaped():
    """ASS 里 {} 是 override tag 定界符，台词里的花括号必须转义。"""
    cues = [SubtitleCue(start_s=0.0, end_s=1.0, text="他说{很好}")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "{很好}" not in ass
    assert r"\{很好\}" in ass


def test_newlines_in_text_become_ass_breaks():
    cues = [SubtitleCue(start_s=0.0, end_s=1.0, text="第一行\n第二行")]
    ass = render_ass(cues, SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    assert "\n第二行" not in ass.split("[Events]")[1]
    assert r"第一行\N第二行" in ass


def test_bold_flag_maps_to_minus_one():
    """ASS 里 Bold 是 -1 表示真，0 表示假 —— 写 1 不生效。"""
    ass = render_ass([], SUBTITLE_TEMPLATES["douyin"], play_res=(1080, 1920))
    style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style:"))
    assert ",-1," in style_line
```

- [ ] **Step 3: 运行确认失败**

Run: `pytest tests/test_subtitle_ass.py -v`
Expected: FAIL — `ImportError: cannot import name 'SUBTITLE_TEMPLATES'`

- [ ] **Step 4: 实现 ASS 部分**

追加到 `src/apps/comic_gen/subtitle.py` 末尾（并把 import 行补成 `from typing import Callable, Dict, List, Optional, Tuple`，新增 `from .models import DialogueStructured, StoryboardFrame, SubtitleStyle`）：

```python
# ----------------------------------------------------------------------
# ASS rendering
# ----------------------------------------------------------------------

SUBTITLE_TEMPLATES: Dict[str, SubtitleStyle] = {
    # Large, heavy, high-contrast. margin_v clears the platform action rail.
    "douyin": SubtitleStyle(
        font_family="Alibaba PuHuiTi",
        font_size=64,
        primary_color="#FFFFFF",
        outline_color="#000000",
        outline_width=4,
        bold=True,
        alignment=2,
        margin_v=180,
        chars_per_line=18,
        max_lines=2,
    ),
    # Restrained, thinner outline, sits lower — reads as film subtitling.
    "cinematic": SubtitleStyle(
        font_family="Alibaba PuHuiTi",
        font_size=52,
        primary_color="#F5F5F5",
        outline_color="#000000",
        outline_width=2,
        bold=False,
        alignment=2,
        margin_v=90,
        chars_per_line=22,
        max_lines=2,
    ),
}


def _hex_to_ass_color(hex_rgb: str) -> str:
    """#RRGGBB -> &HAABBGGRR with AA=00 (opaque).

    ASS stores colour as BGR, not RGB. Getting this backwards silently swaps
    red and blue, which is easy to miss on white text and obvious on any
    coloured template.
    """
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper().replace("&H00", "&H00", 1)


def _ass_time(seconds: float) -> str:
    """H:MM:SS.CC — ASS uses centiseconds, not milliseconds."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def wrap_cjk(text: str, per_line: int, max_lines: int) -> str:
    """Hard-wrap by character count and join with the ASS line break \\N.

    CJK has no word boundaries, so counting characters is the correct
    strategy here — a word-based wrapper would never break.
    """
    text = text.strip()
    if per_line <= 0 or len(text) <= per_line:
        return text

    lines = [text[i : i + per_line] for i in range(0, len(text), per_line)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) >= per_line else lines[-1] + "…"
    return r"\N".join(lines)


def _escape_ass_text(text: str) -> str:
    """Braces delimit override tags; literal braces must be escaped."""
    return text.replace("{", r"\{").replace("}", r"\}")


def render_ass(
    cues: List[SubtitleCue],
    style: SubtitleStyle,
    *,
    play_res: Tuple[int, int],
) -> str:
    """Render cues to an ASS subtitle document.

    play_res must match the output video resolution or font sizes will be
    scaled by the renderer and come out wrong.
    """
    width, height = play_res
    primary = _hex_to_ass_color(style.primary_color)
    outline = _hex_to_ass_color(style.outline_color)
    bold = -1 if style.bold else 0

    head = [
        "[Script Info]",
        "; Generated by PrismReel Studio",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Default,{style.font_family},{style.font_size},"
            f"{primary},&H000000FF,{outline},&H80000000,"
            f"{bold},0,0,0,100,100,0,0,1,{style.outline_width},0,"
            f"{style.alignment},60,60,{style.margin_v},1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text"
        ),
    ]

    events = []
    for cue in cues:
        text = _escape_ass_text(cue.text).replace("\r\n", "\n").replace("\n", r"\N")
        text = wrap_cjk(text, style.chars_per_line, style.max_lines) if r"\N" not in text else text
        events.append(
            f"Dialogue: 0,{_ass_time(cue.start_s)},{_ass_time(cue.end_s)},"
            f"Default,,0,0,0,,{text}"
        )

    return "\n".join(head + events) + "\n"
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_subtitle_ass.py -v`
Expected: 13 passed

- [ ] **Step 6: 确认没有回归**

Run: `pytest tests/ -v`
Expected: 全绿

- [ ] **Step 7: 提交**

```bash
git add src/apps/comic_gen/subtitle.py src/apps/comic_gen/models.py tests/test_subtitle_ass.py
git commit -m "feat(subtitle): ASS rendering with douyin and cinematic templates"
```

---

## Task 7: RenderEngine — 分段收集与两趟渲染

把 `merge_videos`（`pipeline.py:2798-2989`）中「选片逻辑」抽出来复用，并在其后接一趟音频 + 字幕的合成。

**Files:**
- Create: `src/apps/comic_gen/editing.py`
- Create: `tests/test_render_engine.py`
- Modify: `src/apps/comic_gen/pipeline.py`（`merge_videos` 尾部改为调用 `RenderEngine.finalize`）

**Interfaces:**
- Consumes: `build_audio_filter`（Task 4）、`build_subtitle_cues` / `render_ass` / `SUBTITLE_TEMPLATES` / `RenderSegment`（Task 5、6）、`probe_duration` / `probe_dimensions`（Task 2）
- Produces:
  - `def collect_render_segments(script: Script, *, resolve: Callable[[str], str], probe: Callable[[str], float]) -> List[RenderSegment]`
  - `def escape_filter_path(path: str) -> str`
  - `class RenderEngine` with `def finalize(self, script: Script, concat_path: str, *, ffmpeg_path: str, segments: List[RenderSegment]) -> Optional[str]`

**Windows 路径陷阱**：`ass=` 滤镜的文件名参数里，`\` 是转义符、`:` 是参数分隔符。`C:\a\b.ass` 直接传进去必然解析失败。必须转成 `C\:/a/b.ass`。这是 Windows 上最常见的字幕烧录失败原因。

---

- [ ] **Step 1: 写失败测试**

创建 `tests/test_render_engine.py`：

```python
import os
import subprocess

import pytest

from src.apps.comic_gen.editing import collect_render_segments, escape_filter_path
from src.apps.comic_gen.models import Script, StoryboardFrame, VideoTask
from src.utils.system_check import get_ffmpeg_path

requires_ffmpeg = pytest.mark.skipif(
    not get_ffmpeg_path(), reason="ffmpeg not installed"
)


def test_escape_path_windows_drive():
    assert escape_filter_path(r"C:\out\sub.ass") == "C\\:/out/sub.ass"


def test_escape_path_posix():
    assert escape_filter_path("/out/sub.ass") == "/out/sub.ass"


def _script_with(frames, tasks):
    return Script(
        id="s1",
        title="t",
        original_text="x",
        frames=frames,
        video_tasks=tasks,
        created_at=0.0,
        updated_at=0.0,
    )


# StoryboardFrame requires scene_id; VideoTask requires image_url + prompt
# (models.py:353-354, :171-176). Helpers keep the noise out of the tests.
def _frame(fid, **kw):
    return StoryboardFrame(id=fid, scene_id="sc1", **kw)


def _task(tid, frame_id, video_url):
    return VideoTask(
        id=tid,
        project_id="s1",
        frame_id=frame_id,
        image_url="",
        prompt="",
        status="completed",
        video_url=video_url,
    )


def test_prefers_dubbed_video():
    """回归 merge_videos 的选片优先级：配音版 > 选中版 > 首个完成版。"""
    f = _frame("f1", dubbed_video_url="video/dub.mp4")
    f.selected_video_id = "t1"
    t = _task("t1", "f1", "video/sel.mp4")
    segs = collect_render_segments(
        _script_with([f], [t]), resolve=lambda u: f"/abs/{u}", probe=lambda p: 3.0
    )
    assert len(segs) == 1
    assert segs[0].video_path == "/abs/video/dub.mp4"
    assert segs[0].frame_id == "f1"


def test_falls_back_to_selected_then_first_completed():
    f1 = _frame("f1")
    f1.selected_video_id = "t1"
    f2 = _frame("f2")  # 无 selected
    tasks = [_task("t1", "f1", "video/a.mp4"), _task("t2", "f2", "video/b.mp4")]
    segs = collect_render_segments(
        _script_with([f1, f2], tasks), resolve=lambda u: f"/abs/{u}", probe=lambda p: 2.0
    )
    assert [s.video_path for s in segs] == ["/abs/video/a.mp4", "/abs/video/b.mp4"]


def test_frames_without_any_video_are_dropped():
    segs = collect_render_segments(
        _script_with([_frame("f1")], []), resolve=lambda u: f"/abs/{u}", probe=lambda p: 2.0
    )
    assert segs == []


def test_segments_carry_measured_duration():
    f = _frame("f1", dubbed_video_url="video/a.mp4")
    segs = collect_render_segments(
        _script_with([f], []), resolve=lambda u: f"/abs/{u}", probe=lambda p: 4.25
    )
    assert segs[0].duration_s == pytest.approx(4.25)


@requires_ffmpeg
def test_ass_burn_accepted_by_ffmpeg(tmp_path):
    """真跑一次烧录 —— 路径转义写错在单测里看不出来。"""
    from src.apps.comic_gen.editing import escape_filter_path
    from src.apps.comic_gen.subtitle import SUBTITLE_TEMPLATES, SubtitleCue, render_ass

    ff = get_ffmpeg_path()
    ass_path = tmp_path / "s.ass"
    ass_path.write_text(
        render_ass(
            [SubtitleCue(start_s=0.0, end_s=1.5, text="测试字幕")],
            SUBTITLE_TEMPLATES["douyin"],
            play_res=(320, 240),
        ),
        encoding="utf-8",
    )
    out = str(tmp_path / "burned.mp4")
    subprocess.run(
        [
            ff, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
            "-vf", f"ass='{escape_filter_path(str(ass_path))}'",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "2",
            out,
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert os.path.exists(out)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_render_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.apps.comic_gen.editing'`

- [ ] **Step 3: 实现 RenderEngine**

创建 `src/apps/comic_gen/editing.py`：

```python
"""Final-render orchestration.

V-1 renders in two ffmpeg passes:

  Pass 1 (owned by pipeline.merge_videos)  concat + re-encode -> concat.mp4
  Pass 2 (this module)                     audio chain + subtitle burn -> final

A single filter_complex doing everything is the V2 target. Two passes are
chosen here because a variable-length concat graph combined with sidechain
audio and subtitle burning is very hard to debug when it fails, and V-1's
goal is a correct first film rather than the fastest possible render. The
audio chain and the subtitle burn share pass 2, so this costs one extra
encode, not two.
"""

import os
import subprocess
from typing import Callable, List, Optional

from ...utils import get_logger
from ...utils.media_probe import probe_dimensions, probe_duration
from .audio_mixer import build_audio_filter
from .models import Script
from .subtitle import (
    SUBTITLE_TEMPLATES,
    RenderSegment,
    build_subtitle_cues,
    render_ass,
)

logger = get_logger(__name__)

_PASS2_TIMEOUT_S = 1800


def escape_filter_path(path: str) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter argument.

    Inside a filter, '\\' is an escape character and ':' separates options,
    so a Windows path like C:\\out\\s.ass must become C\\:/out/s.ass. This is
    the single most common cause of subtitle burn failures on Windows.
    """
    return path.replace("\\", "/").replace(":", "\\:")


def collect_render_segments(
    script: Script,
    *,
    resolve: Callable[[str], str],
    probe: Callable[[str], float] = probe_duration,
) -> List[RenderSegment]:
    """Pick the video for each frame and measure it.

    Mirrors the selection precedence already used by merge_videos:
    dubbed video > explicitly selected take > first completed take.
    Frames with no usable video are skipped, exactly as before.

    `resolve` maps a stored relative url to an absolute filesystem path
    (production passes _safe_resolve_path bound to "output").
    """
    segments: List[RenderSegment] = []

    for frame in script.frames:
        url = None
        if frame.dubbed_video_url:
            url = frame.dubbed_video_url
        elif frame.selected_video_id:
            task = next(
                (t for t in script.video_tasks if t.id == frame.selected_video_id), None
            )
            url = task.video_url if task else None
        if not url:
            task = next(
                (
                    t
                    for t in script.video_tasks
                    if t.frame_id == frame.id and t.status == "completed" and t.video_url
                ),
                None,
            )
            url = task.video_url if task else None

        if not url:
            logger.debug(f"[RENDER] frame {frame.id}: no usable video, skipping")
            continue

        abs_path = resolve(url)
        try:
            duration = probe(abs_path)
        except Exception as e:
            logger.warning(f"[RENDER] frame {frame.id}: duration probe failed ({e}); using 0")
            duration = 0.0

        segments.append(
            RenderSegment(frame_id=frame.id, video_path=abs_path, duration_s=duration)
        )

    return segments


class RenderEngine:
    """Pass 2 of the render: audio mix + burned-in subtitles."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir

    def _write_ass(
        self, script: Script, segments: List[RenderSegment], concat_path: str
    ) -> Optional[str]:
        settings = script.subtitle_settings
        if not settings.enabled:
            return None

        cues = build_subtitle_cues(script.frames, segments)
        if not cues:
            logger.info("[RENDER/SUB] no dialogue found; skipping subtitle burn")
            return None

        style = settings.style_override or SUBTITLE_TEMPLATES.get(
            settings.template_id, SUBTITLE_TEMPLATES["douyin"]
        )
        try:
            play_res = probe_dimensions(concat_path)
        except Exception as e:
            logger.warning(f"[RENDER/SUB] dimension probe failed ({e}); assuming 1080x1920")
            play_res = (1080, 1920)

        ass_path = f"{os.path.splitext(concat_path)[0]}.ass"
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(render_ass(cues, style, play_res=play_res))
        logger.info(f"[RENDER/SUB] wrote {len(cues)} cues -> {os.path.basename(ass_path)}")
        return ass_path

    def finalize(
        self,
        script: Script,
        concat_path: str,
        *,
        ffmpeg_path: str,
        segments: List[RenderSegment],
        bgm_abs_path: Optional[str] = None,
    ) -> Optional[str]:
        """Apply the audio chain and subtitle burn to `concat_path`.

        Returns the path of the finished file, or None when nothing needed
        doing (caller then keeps the concat output as-is).
        """
        ass_path = self._write_ass(script, segments, concat_path)
        has_bgm = bool(bgm_abs_path and os.path.exists(bgm_abs_path))

        mix = script.mix_settings or {"dialogue": 100, "bgm": 35, "sfx": 60}
        audio_filter = build_audio_filter(
            dialogue_level=int(mix.get("dialogue", 100)),
            bgm_level=int(mix.get("bgm", 35)),
            has_bgm=has_bgm,
            ducking=True,
            normalize=True,
        )

        out_path = concat_path.replace(".mp4", "_final.mp4")
        cmd = [ffmpeg_path, "-y", "-i", concat_path]
        if has_bgm:
            cmd += ["-stream_loop", "-1", "-i", bgm_abs_path]
        cmd += ["-filter_complex", audio_filter]

        if ass_path:
            cmd += ["-vf", f"ass='{escape_filter_path(ass_path)}'"]
            cmd += ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p"]
        else:
            cmd += ["-c:v", "copy"]

        cmd += [
            "-map", "0:v",
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            out_path,
        ]

        logger.info(
            f"[RENDER] pass 2 — bgm={has_bgm} subtitles={bool(ass_path)} "
            f"ducking=on loudnorm=on"
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=_PASS2_TIMEOUT_S)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace")[:600] if e.stderr else ""
            logger.error(f"[RENDER] pass 2 failed: {stderr}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("[RENDER] pass 2 timed out")
            return None

        if not os.path.exists(out_path):
            logger.error(f"[RENDER] pass 2 produced no output at {out_path}")
            return None
        return out_path
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_render_engine.py -v`
Expected: 7 passed（无 ffmpeg 则 6 passed, 1 skipped）

- [ ] **Step 5: 接入 merge_videos**

修改 `src/apps/comic_gen/pipeline.py`。顶部 import 加：

```python
from .editing import RenderEngine, collect_render_segments
```

把 `merge_videos` 中 BGM mux 那一段（`pipeline.py:2949-2964`，即 `# PR-3l · Pass 2: BGM mux.` 注释到 `except Exception as bgm_err:` 块结束）整段替换为：

```python
            # V-1 · Pass 2: audio chain (ducking + loudnorm) + subtitle burn.
            # Replaces the old BGM-only mux. Any failure here is non-fatal —
            # the concat output stays usable.
            try:
                segments = collect_render_segments(
                    script,
                    resolve=lambda u: _safe_resolve_path("output", u),
                )
                bgm_abs = None
                if (script.bgm_url or "").strip():
                    bgm_abs = _safe_resolve_path("output", script.bgm_url.strip())
                    if not os.path.exists(bgm_abs):
                        logger.warning(
                            f"[MERGE/BGM] preset file missing — {bgm_abs}; "
                            f"rendering without background music"
                        )
                        bgm_abs = None

                final_path = RenderEngine().finalize(
                    script,
                    output_path,
                    ffmpeg_path=ffmpeg_path,
                    segments=segments,
                    bgm_abs_path=bgm_abs,
                )
                if final_path:
                    os.replace(final_path, output_path)
                    logger.info(f"[MERGE] ✅ pass 2 applied — final file: {output_filename}")
            except Exception as post_err:
                logger.warning(f"[MERGE] pass 2 skipped due to error: {post_err}")
```

> 注意 `preset file missing` 从 `logger.info` 提到了 `logger.warning` —— 这正是让 Task 3 的静音问题能被看见的地方。

`_maybe_apply_bgm_mux`（`pipeline.py:2991-3049`）现在已无调用者，**删除整个方法**。

- [ ] **Step 6: 全量测试**

Run: `pytest tests/ -v`
Expected: 全绿

- [ ] **Step 7: 手工端到端验证**

```bash
# 选一个已有配音和台词的项目，在 UI 里执行合并
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name output/video/merged_*.mp4
# 应输出 codec_name=aac

ffmpeg -i output/video/merged_*.mp4 -af loudnorm=print_format=json -f null - 2>&1 | grep input_i
# input_i 应接近 -16

# 肉眼确认：字幕出现、位置在底部、描边清晰、时间对得上口型
```

- [ ] **Step 8: 提交**

```bash
git add src/apps/comic_gen/editing.py src/apps/comic_gen/pipeline.py tests/test_render_engine.py
git commit -m "feat(render): two-pass RenderEngine with ducking, loudnorm and subtitle burn

Pass 2 replaces the BGM-only mux. Subtitle cue timing comes from script
dialogue plus measured TTS duration, so no ASR is involved."
```

---

## Task 8: 字幕 API 端点

**Files:**
- Modify: `src/apps/comic_gen/pipeline.py`（新增 3 个方法）
- Modify: `src/apps/comic_gen/api.py`（新增 4 个端点）
- Create: `tests/test_subtitle_api.py`

**Interfaces:**
- Consumes: `SubtitleSettings` / `SubtitleStyle`（Task 6）、`collect_render_segments`（Task 7）、`build_subtitle_cues` / `render_ass` / `SUBTITLE_TEMPLATES`
- Produces:
  - `pipeline.get_subtitle_preview(script_id) -> List[Dict]`
  - `pipeline.update_subtitle_settings(script_id, settings: SubtitleSettings) -> Script`
  - `pipeline.export_subtitle_file(script_id, fmt: str) -> str`（`fmt` ∈ `"ass"` / `"srt"`）
  - 端点：`GET /subtitle/templates`、`GET /projects/{id}/subtitle/preview`、`PUT /projects/{id}/subtitle/settings`、`GET /projects/{id}/subtitle/export`

---

- [ ] **Step 1: 写失败测试**

创建 `tests/test_subtitle_api.py`：

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.apps.comic_gen.api import app

    return TestClient(app)


def test_list_templates(client):
    r = client.get("/subtitle/templates")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert ids == {"douyin", "cinematic"}
    for t in r.json():
        assert "font_size" in t and "margin_v" in t


def test_preview_unknown_project_404(client):
    r = client.get("/projects/nope/subtitle/preview")
    assert r.status_code == 404


def test_update_settings_roundtrip(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p1"] = Script(
        id="p1", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )

    r = client.put(
        "/projects/p1/subtitle/settings",
        json={"enabled": True, "template_id": "cinematic"},
    )
    assert r.status_code == 200
    assert pipeline.scripts["p1"].subtitle_settings.template_id == "cinematic"


def test_update_settings_rejects_unknown_template(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p2"] = Script(
        id="p2", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )
    r = client.put(
        "/projects/p2/subtitle/settings",
        json={"enabled": True, "template_id": "does_not_exist"},
    )
    assert r.status_code == 400


def test_export_rejects_bad_format(client):
    from src.apps.comic_gen.api import pipeline
    from src.apps.comic_gen.models import Script

    pipeline.scripts["p3"] = Script(
        id="p3", title="t", original_text="x", created_at=0.0, updated_at=0.0
    )
    r = client.get("/projects/p3/subtitle/export", params={"fmt": "vtt"})
    assert r.status_code == 400
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_subtitle_api.py -v`
Expected: FAIL — 404 on `/subtitle/templates`

- [ ] **Step 3: 新增 pipeline 方法**

在 `src/apps/comic_gen/pipeline.py` 的 `merge_videos` 之后追加：

```python
    # ============================================================
    # V-1 · Subtitles
    # ============================================================

    def get_subtitle_preview(self, script_id: str) -> List[Dict[str, Any]]:
        """Compute the cue list without rendering, for UI display."""
        _validate_safe_id(script_id, "script_id")
        script = self.scripts.get(script_id)
        if not script:
            raise ValueError("Script not found")

        from .subtitle import build_subtitle_cues

        segments = collect_render_segments(
            script, resolve=lambda u: _safe_resolve_path("output", u)
        )
        cues = build_subtitle_cues(script.frames, segments)
        return [
            {
                "index": i + 1,
                "start_s": round(c.start_s, 2),
                "end_s": round(c.end_s, 2),
                "text": c.text,
                "speaker": c.speaker,
            }
            for i, c in enumerate(cues)
        ]

    def update_subtitle_settings(self, script_id: str, settings) -> Script:
        _validate_safe_id(script_id, "script_id")
        script = self.scripts.get(script_id)
        if not script:
            raise ValueError("Script not found")
        script.subtitle_settings = settings
        script.updated_at = time.time()
        self._save_data()
        return script

    def export_subtitle_file(self, script_id: str, fmt: str = "ass") -> str:
        """Write a standalone subtitle file and return its absolute path."""
        _validate_safe_id(script_id, "script_id")
        if fmt not in ("ass", "srt"):
            raise ValueError(f"Unsupported subtitle format: {fmt}")

        script = self.scripts.get(script_id)
        if not script:
            raise ValueError("Script not found")

        from .subtitle import (
            SUBTITLE_TEMPLATES,
            build_subtitle_cues,
            render_ass,
            render_srt,
        )

        segments = collect_render_segments(
            script, resolve=lambda u: _safe_resolve_path("output", u)
        )
        cues = build_subtitle_cues(script.frames, segments)

        out_dir = _safe_resolve_path("output", "subtitles")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{script_id}.{fmt}")

        if fmt == "srt":
            content = render_srt(cues)
        else:
            settings = script.subtitle_settings
            style = settings.style_override or SUBTITLE_TEMPLATES.get(
                settings.template_id, SUBTITLE_TEMPLATES["douyin"]
            )
            content = render_ass(cues, style, play_res=(1080, 1920))

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        return out_path
```

- [ ] **Step 4: 新增 SRT 渲染器**

追加到 `src/apps/comic_gen/subtitle.py` 末尾：

```python
def _srt_time(seconds: float) -> str:
    """HH:MM:SS,mmm — SRT uses milliseconds and a comma separator."""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render_srt(cues: List[SubtitleCue]) -> str:
    """Plain SRT for import into external editors."""
    blocks = []
    for i, cue in enumerate(cues, start=1):
        text = cue.text.replace(r"\N", "\n")
        blocks.append(f"{i}\n{_srt_time(cue.start_s)} --> {_srt_time(cue.end_s)}\n{text}\n")
    return "\n".join(blocks)
```

追加到 `tests/test_subtitle_ass.py`：

```python
def test_srt_format():
    from src.apps.comic_gen.subtitle import render_srt

    out = render_srt([SubtitleCue(start_s=1.5, end_s=3.25, text="你好")])
    assert "1\n00:00:01,500 --> 00:00:03,250\n你好" in out
```

- [ ] **Step 5: 新增 API 端点**

在 `src/apps/comic_gen/api.py` 中 `/bgm/presets`（`api.py:2968`）附近追加。**注意全部用 `def` 而非 `async def`**：

```python
class UpdateSubtitleSettingsRequest(BaseModel):
    enabled: bool = True
    template_id: str = "douyin"
    style_override: Optional[Dict[str, Any]] = None


@app.get("/subtitle/templates")
def list_subtitle_templates():
    """Available burned-in subtitle style templates."""
    from .subtitle import SUBTITLE_TEMPLATES

    return [{"id": tid, **style.model_dump()} for tid, style in SUBTITLE_TEMPLATES.items()]


@app.get("/projects/{script_id}/subtitle/preview")
def preview_subtitles(script_id: str):
    """Cue list derived from dialogue + TTS timing. No rendering, no ASR."""
    try:
        return pipeline.get_subtitle_preview(script_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/projects/{script_id}/subtitle/settings")
def update_subtitle_settings(script_id: str, request: UpdateSubtitleSettingsRequest):
    from .models import SubtitleSettings, SubtitleStyle
    from .subtitle import SUBTITLE_TEMPLATES

    if request.template_id not in SUBTITLE_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template '{request.template_id}'. "
            f"Available: {sorted(SUBTITLE_TEMPLATES)}",
        )
    try:
        settings = SubtitleSettings(
            enabled=request.enabled,
            template_id=request.template_id,
            style_override=(
                SubtitleStyle(**request.style_override) if request.style_override else None
            ),
        )
        script = pipeline.update_subtitle_settings(script_id, settings)
        return signed_response(script)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/projects/{script_id}/subtitle/export")
def export_subtitle(script_id: str, fmt: str = "ass"):
    from fastapi.responses import FileResponse

    if fmt not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="fmt must be 'ass' or 'srt'")
    try:
        path = pipeline.export_subtitle_file(script_id, fmt)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(path, filename=os.path.basename(path))
```

> `signed_response` 是本文件中已有的响应包装器；照现有端点的用法调用即可。

- [ ] **Step 6: 运行确认通过**

Run: `pytest tests/test_subtitle_api.py tests/test_subtitle_ass.py -v`
Expected: 全部通过

- [ ] **Step 7: 全量测试并提交**

Run: `pytest tests/ -v`

```bash
git add src/apps/comic_gen/api.py src/apps/comic_gen/pipeline.py \
        src/apps/comic_gen/subtitle.py tests/test_subtitle_api.py tests/test_subtitle_ass.py
git commit -m "feat(subtitle): templates, preview, settings and export endpoints"
```

---

## Task 9: 前端字幕面板

**Files:**
- Create: `frontend/src/components/assembly/SubtitlePanel.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/modules/VideoAssembly.tsx:13`（`AssemblyPhase`）、tab 条（`:136-158`）、渲染分支
- Modify: `frontend/messages/zh.json`、`frontend/messages/en.json`

**Interfaces:**
- Consumes: Task 8 的 4 个端点
- Produces: `<SubtitlePanel projectId={string} />`

新建 `components/assembly/` 目录，**不要**把面板塞进 `VideoAssembly.tsx`（已 620 行）。

---

- [ ] **Step 1: 新增 API 方法**

在 `frontend/src/lib/api.ts` 的 `api` 对象里追加（沿用文件中现有的 axios 写法）：

```ts
  // ---- V-1 subtitles ----
  listSubtitleTemplates: async (): Promise<SubtitleTemplate[]> => {
    const res = await axios.get(`${API_URL}/subtitle/templates`);
    return res.data;
  },

  previewSubtitles: async (projectId: string): Promise<SubtitleCue[]> => {
    const res = await axios.get(`${API_URL}/projects/${projectId}/subtitle/preview`);
    return res.data;
  },

  updateSubtitleSettings: async (
    projectId: string,
    settings: { enabled: boolean; template_id: string }
  ) => {
    const res = await axios.put(
      `${API_URL}/projects/${projectId}/subtitle/settings`,
      settings
    );
    return res.data;
  },

  subtitleExportUrl: (projectId: string, fmt: "ass" | "srt") =>
    `${API_URL}/projects/${projectId}/subtitle/export?fmt=${fmt}`,
```

在文件的类型声明区（`api.ts:105` 的 `BgmPreset` 附近）追加：

```ts
export interface SubtitleTemplate {
  id: string;
  font_family: string;
  font_size: number;
  primary_color: string;
  outline_color: string;
  outline_width: number;
  bold: boolean;
  alignment: number;
  margin_v: number;
  chars_per_line: number;
  max_lines: number;
}

export interface SubtitleCue {
  index: number;
  start_s: number;
  end_s: number;
  text: string;
  speaker: string | null;
}
```

- [ ] **Step 2: 新增文案**

`frontend/messages/zh.json` 加一个 `subtitle` 命名空间：

```json
  "subtitle": {
    "tab": "字幕",
    "title": "字幕",
    "description": "字幕由台词和配音时长自动推算，无需语音识别",
    "enabled": "导出时烧录字幕",
    "template": "样式模板",
    "templateDouyin": "抖音风",
    "templateCinematic": "影视风",
    "preview": "字幕预览",
    "empty": "还没有台词。请先在分镜步骤填写台词。",
    "cueCount": "共 {count} 条字幕",
    "exportAss": "导出 ASS",
    "exportSrt": "导出 SRT",
    "loadFailed": "加载字幕失败",
    "saveFailed": "保存字幕设置失败",
    "saved": "字幕设置已保存"
  }
```

`frontend/messages/en.json` 加同名 key 的英文版：

```json
  "subtitle": {
    "tab": "Subtitles",
    "title": "Subtitles",
    "description": "Cues are derived from dialogue and dub timing — no speech recognition needed",
    "enabled": "Burn subtitles on export",
    "template": "Style template",
    "templateDouyin": "Douyin",
    "templateCinematic": "Cinematic",
    "preview": "Cue preview",
    "empty": "No dialogue yet. Add dialogue in the storyboard step first.",
    "cueCount": "{count} cues",
    "exportAss": "Export ASS",
    "exportSrt": "Export SRT",
    "loadFailed": "Failed to load subtitles",
    "saveFailed": "Failed to save subtitle settings",
    "saved": "Subtitle settings saved"
  }
```

- [ ] **Step 3: 实现面板组件**

创建 `frontend/src/components/assembly/SubtitlePanel.tsx`：

```tsx
"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Download, Loader2, Subtitles } from "lucide-react";

import { api, SubtitleCue, SubtitleTemplate } from "@/lib/api";
import { toast } from "@/store/toastStore";
import { extractErrorDetail } from "@/lib/utils";

interface Props {
  projectId: string;
  initialEnabled?: boolean;
  initialTemplateId?: string;
}

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
}

export function SubtitlePanel({
  projectId,
  initialEnabled = true,
  initialTemplateId = "douyin",
}: Props) {
  const t = useTranslations("subtitle");

  const [templates, setTemplates] = useState<SubtitleTemplate[]>([]);
  const [cues, setCues] = useState<SubtitleCue[]>([]);
  const [enabled, setEnabled] = useState(initialEnabled);
  const [templateId, setTemplateId] = useState(initialTemplateId);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([api.listSubtitleTemplates(), api.previewSubtitles(projectId)])
      .then(([tpl, cs]) => {
        if (cancelled) return;
        setTemplates(tpl);
        setCues(cs);
      })
      .catch((e) => {
        if (!cancelled) toast.error(extractErrorDetail(e, t("loadFailed")));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, t]);

  const save = async (next: { enabled: boolean; template_id: string }) => {
    setSaving(true);
    try {
      await api.updateSubtitleSettings(projectId, next);
      toast.success(t("saved"));
    } catch (e) {
      toast.error(extractErrorDetail(e, t("saveFailed")));
      setEnabled(initialEnabled);
      setTemplateId(initialTemplateId);
    } finally {
      setSaving(false);
    }
  };

  const labelFor = (id: string) =>
    id === "douyin" ? t("templateDouyin") : id === "cinematic" ? t("templateCinematic") : id;

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-text-secondary">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex items-start gap-3">
        <Subtitles className="mt-1 h-5 w-5 text-text-secondary" />
        <div>
          <h3 className="text-lg font-medium text-text-primary">{t("title")}</h3>
          <p className="text-sm text-text-secondary">{t("description")}</p>
        </div>
      </header>

      <label className="glass-panel flex items-center justify-between rounded-lg p-4">
        <span className="text-sm text-text-primary">{t("enabled")}</span>
        <input
          type="checkbox"
          checked={enabled}
          disabled={saving}
          onChange={(e) => {
            setEnabled(e.target.checked);
            void save({ enabled: e.target.checked, template_id: templateId });
          }}
        />
      </label>

      <section className="flex flex-col gap-2">
        <span className="text-sm text-text-secondary">{t("template")}</span>
        <div className="grid grid-cols-2 gap-3">
          {templates.map((tpl) => (
            <button
              key={tpl.id}
              type="button"
              disabled={saving}
              onClick={() => {
                setTemplateId(tpl.id);
                void save({ enabled, template_id: tpl.id });
              }}
              className={`glass-button rounded-lg p-4 text-left transition ${
                templateId === tpl.id ? "border-accent" : "border-glass-border"
              } border`}
            >
              <div className="text-sm font-medium text-text-primary">{labelFor(tpl.id)}</div>
              <div className="mt-1 text-xs text-text-secondary">
                {tpl.font_size}px · {tpl.chars_per_line}/line
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-text-secondary">{t("preview")}</span>
          <span className="text-xs text-text-secondary">
            {t("cueCount", { count: cues.length })}
          </span>
        </div>

        {cues.length === 0 ? (
          <p className="glass-panel rounded-lg p-6 text-center text-sm text-text-secondary">
            {t("empty")}
          </p>
        ) : (
          <div className="custom-scrollbar max-h-96 overflow-y-auto rounded-lg">
            {cues.map((c) => (
              <div
                key={c.index}
                className="flex gap-3 border-b border-glass-border px-3 py-2 text-sm last:border-b-0"
              >
                <span className="w-8 shrink-0 text-text-secondary">{c.index}</span>
                <span className="w-28 shrink-0 font-mono text-xs text-text-secondary">
                  {fmtTime(c.start_s)} → {fmtTime(c.end_s)}
                </span>
                <span className="text-text-primary">
                  {c.speaker ? <b className="mr-1 text-text-secondary">{c.speaker}:</b> : null}
                  {c.text}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <footer className="flex gap-3">
        <a
          className="glass-button flex items-center gap-2 rounded-lg px-4 py-2 text-sm"
          href={api.subtitleExportUrl(projectId, "ass")}
        >
          <Download className="h-4 w-4" /> {t("exportAss")}
        </a>
        <a
          className="glass-button flex items-center gap-2 rounded-lg px-4 py-2 text-sm"
          href={api.subtitleExportUrl(projectId, "srt")}
        >
          <Download className="h-4 w-4" /> {t("exportSrt")}
        </a>
      </footer>
    </div>
  );
}
```

> Toast 用法已核对 `frontend/src/store/toastStore.ts:76-87`：导出的是一个 `toast` 单例，签名为 `toast.error(title, opts?)` / `toast.success(title, opts?)`，**不是** `useToastStore(s => s.push)`。`error` 的 `autoCloseMs` 默认为 0（不自动关闭），符合报错场景。

- [ ] **Step 4: 接进 Assembly**

修改 `frontend/src/components/modules/VideoAssembly.tsx`：

第 13 行的类型改为：

```ts
type AssemblyPhase = "takes" | "mix" | "subtitle" | "export";
```

在 tab 条（`:136-158`）的 `mix` 与 `export` 之间插入一个 `subtitle` tab，沿用相邻 tab 的 className 与结构。

在 phase 渲染分支中，`mix` 分支之后加：

```tsx
{phase === "subtitle" && (
  <SubtitlePanel
    projectId={projectId}
    initialEnabled={project?.subtitle_settings?.enabled ?? true}
    initialTemplateId={project?.subtitle_settings?.template_id ?? "douyin"}
  />
)}
```

顶部加 import：

```ts
import { SubtitlePanel } from "@/components/assembly/SubtitlePanel";
```

在 `frontend/src/store/projectStore.ts` 的 `Project` 接口（`:253-282`）中补字段：

```ts
  subtitle_settings?: { enabled: boolean; template_id: string };
```

- [ ] **Step 5: 验证前端**

```bash
cd frontend
npm run lint
npm run check:colors
npm run build
```
Expected: 三条全部通过。`check:colors` 报错说明用了硬编码颜色，改成语义 token。

- [ ] **Step 6: 手工验证**

启动前后端，打开任一有台词的项目 → Assembly → 字幕 tab：
- 预览列表显示台词与时间码，序号连续
- 切换模板后刷新页面，选择被保留
- 导出 SRT 能下载，用文本编辑器打开时间码格式正确
- 关闭「烧录字幕」后执行导出，成片无字幕

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/assembly/SubtitlePanel.tsx frontend/src/lib/api.ts \
        frontend/src/components/modules/VideoAssembly.tsx frontend/src/store/projectStore.ts \
        frontend/messages/zh.json frontend/messages/en.json
git commit -m "feat(ui): subtitle panel in Assembly with template picker and cue preview"
```

---

## Task 10: 端到端验证与基线报告

产出 V-1 的核心交付物之一：**基线报告**。V0 与 V1 的排期要按它复评（见 spec §11 Q1/Q2）。

**Files:**
- Create: `scripts/baseline_report.py`
- Create: `docs/superpowers/reports/2026-XX-XX-v-1-baseline.md`（日期填实际完成日）

**Interfaces:**
- Consumes: `output/projects.json`、`output/video/merged_*.mp4`
- Produces: 基线报告 Markdown

---

- [ ] **Step 1: 跑通一部完整的剧**

选一部 12 集短剧，从剧本导入到导出全程走一遍。**每一集都记录**：

| 记录项 | 怎么拿 |
|---|---|
| 各步墙钟耗时 | 后端日志时间戳 |
| API 调用次数 | 按 provider 统计日志中的 submit 行 |
| 人工点击次数 | 手动计数（挑图/挑视频/重试/微调） |
| 失败与重试次数 | 日志中的 `status.*failed` |
| 成片文件大小与时长 | `ffprobe` |

- [ ] **Step 2: 写指标采集脚本**

创建 `scripts/baseline_report.py`：

```python
"""Collect V-1 baseline metrics from the on-disk store and rendered output.

Usage:
    python scripts/baseline_report.py --series-id <id>
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.media_probe import probe_duration  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--store", default="output/projects.json")
    args = parser.parse_args()

    with open(args.store, "r", encoding="utf-8") as f:
        scripts = json.load(f)

    episodes = [
        s for s in scripts.values() if s.get("series_id") == args.series_id
    ]
    episodes.sort(key=lambda s: s.get("episode_number") or 0)
    if not episodes:
        print(f"No episodes found for series {args.series_id}")
        return 1

    print(f"# V-1 Baseline — series {args.series_id}\n")
    print("| Ep | Shots | Video tasks | Completed | Failed | With dialogue | Merged | Duration |")
    print("|----|-------|-------------|-----------|--------|---------------|--------|----------|")

    totals = {"shots": 0, "tasks": 0, "done": 0, "failed": 0, "dialogue": 0, "dur": 0.0}

    for ep in episodes:
        frames = ep.get("frames") or []
        tasks = ep.get("video_tasks") or []
        done = sum(1 for t in tasks if t.get("status") == "completed")
        failed = sum(1 for t in tasks if t.get("status") == "failed")
        with_dialogue = sum(1 for fr in frames if (fr.get("dialogue") or "").strip())

        merged = ep.get("merged_video_url")
        duration = 0.0
        if merged:
            path = os.path.join("output", merged)
            try:
                duration = probe_duration(path)
            except Exception:
                duration = 0.0

        print(
            f"| {ep.get('episode_number')} | {len(frames)} | {len(tasks)} | {done} | "
            f"{failed} | {with_dialogue} | {'yes' if merged else 'NO'} | {duration:.1f}s |"
        )

        totals["shots"] += len(frames)
        totals["tasks"] += len(tasks)
        totals["done"] += done
        totals["failed"] += failed
        totals["dialogue"] += with_dialogue
        totals["dur"] += duration

    attempts = totals["done"] + totals["failed"]
    rate = (totals["done"] / attempts * 100) if attempts else 0.0
    per_shot = (totals["tasks"] / totals["shots"]) if totals["shots"] else 0.0

    print(f"\n## Totals\n")
    print(f"- Episodes: {len(episodes)}")
    print(f"- Shots: {totals['shots']}")
    print(f"- Video tasks: {totals['tasks']}  (avg {per_shot:.2f} takes/shot)")
    print(f"- Success rate: {rate:.1f}%  ({totals['done']} ok / {totals['failed']} failed)")
    print(f"- Shots with dialogue: {totals['dialogue']}")
    print(f"- Total runtime: {totals['dur'] / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 运行采集**

```bash
python scripts/baseline_report.py --series-id <你的剧集ID> > /tmp/metrics.md
cat /tmp/metrics.md
```

- [ ] **Step 4: 逐集质量抽检**

```bash
for f in output/video/merged_*.mp4; do
  echo "=== $f"
  ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$f"
  ffmpeg -i "$f" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
done
```

判定标准：
- 每个文件都有 `aac` 音轨（不能为空）
- `max_volume` < -1 dB（无爆音）
- `mean_volume` 不是 -91 dB（不是静音）
- 随机抽 3 集肉眼看：字幕清晰、位置不遮挡、时间对得上口型、BGM 在人声处明显压低

- [ ] **Step 5: 撰写基线报告**

创建 `docs/superpowers/reports/2026-XX-XX-v-1-baseline.md`，必须包含以下六节：

```markdown
# V-1 基线报告

## 1. 采集范围
剧集名 / 集数 / 采集日期 / 运行环境（CPU 核数、内存、是否容器）

## 2. 量化指标
（粘贴 scripts/baseline_report.py 的输出表格）
补充手工记录：
- 一集从剧本到成片的墙钟耗时：___ 分钟
- 其中纯 API 等待：___ 分钟
- 其中 FFmpeg 渲染：___ 分钟
- 其中人工操作：___ 分钟，___ 次点击
- 各 provider 调用次数与失败率

## 3. 质量抽检结论
音轨 / 电平 / 字幕 / BGM 闪避 的逐项判定与截图

## 4. ⚠️ 调色决策（spec §11 Q1）
分镜之间色调跳变是否严重到影响发布？
- [ ] 是 —— 建议把「6 预设全局静态 LUT」加入 V-1，代价 +1 周
- [ ] 否 —— 维持原计划，调色留在 V3
附 3-5 张相邻分镜首帧对比图作为依据。

## 5. ⚠️ V0/V1 排期修正建议（spec §11 Q2）
基于实测回答：
- 人工点击次数是否印证「4 万次点击是瓶颈」的估算？自动挑卡（V1.5）的优先级要不要再提？
- 全量 dump 的写入耗时实测多少？PG 迁移（V0）的紧迫性比预期高还是低？
- 失败率实测多少？失败看板与一键重试（V1.4）的优先级要不要调整？
- 单集渲染实测多少分钟？据此重算 30 部剧的渲染总时长。

## 6. 遗留问题清单
V-1 期间发现但未修的问题，按严重性排序，标注建议归入哪一期。
```

- [ ] **Step 6: 提交**

```bash
git add scripts/baseline_report.py docs/superpowers/reports/
git commit -m "docs: V-1 baseline report and metrics collection script"
```

- [ ] **Step 7: 走完成前验证**

**REQUIRED SUB-SKILL:** 使用 `superpowers:verification-before-completion`，在宣布 V-1 完成之前逐项确认下列证据（**贴实际命令输出，不要凭印象**）：

- [ ] `pytest tests/ -v` 全绿，粘贴末尾摘要行
- [ ] `cd frontend && npm run lint && npm run check:colors && npm run build` 三条全过
- [ ] 12 集成片全部存在，每集都有 aac 音轨
- [ ] 每集 `max_volume < -1dB`
- [ ] 每集 LUFS 在 -16 ± 1
- [ ] 抽检 3 集字幕肉眼正确
- [ ] `verify_bgm_assets()` 返回 `[]`
- [ ] 损坏 `projects.json` 后启动会 fail-fast（真做一次，别只看测试）
- [ ] 基线报告 6 节全部填写完毕，§4 和 §5 有明确结论

---

## Self-Review

**Spec 覆盖检查**（对照 `2026-07-26-prismreel-platform-roadmap-v2-design.md` §5 V-1）

| Spec 条目 | 覆盖任务 |
|---|---|
| -1.1 数据安全急救（B1 / B2 / B12） | Task 1 |
| -1.2 BGM 素材落地 | Task 3 |
| -1.3 渲染管线 v1 | Task 7（依赖 Task 2 的 ffprobe） |
| -1.4 音频完善（ducking + loudnorm） | Task 4 + Task 7 |
| -1.5 字幕系统 v1（2 套模板 + 时间码微调入口） | Task 5、6、8、9 |
| -1.6 端到端验证与基线报告 | Task 10 |
| 验收：可直发抖音 | Task 10 Step 4 |
| 验收：ffprobe 音轨 / volumedetect / LUFS | Task 10 Step 4、Step 7 |
| 验收：强杀后 projects.json 完好 | Task 1 Step 7 + Task 10 Step 7 |
| 验收：基线报告 | Task 10 Step 5 |
| §11 Q1 调色决策 | 基线报告 §4 |
| §11 Q2 排期复评 | 基线报告 §5 |
| §11 Q4 BGM 授权 | Task 3 Step 1（LICENSES.md + 测试断言） |

**范围外确认**：本计划不含 PostgreSQL、任务队列、鉴权、粗剪、工程文件导出、调色 —— 与 spec 中 V-1 的「明确不做」一致。

**类型一致性检查**
- `RenderSegment` 在 `subtitle.py` 定义（Task 5），`editing.py` 从 `.subtitle` 导入（Task 7）——一致。
- `build_audio_filter` 全部为关键字参数，Task 4 定义、Task 7 调用签名一致。
- `SubtitleStyle` / `SubtitleSettings` 在 `models.py` 定义（Task 6），`subtitle.py`、`pipeline.py`、`api.py` 引用一致。
- `probe_duration` 在 `media_probe.py`（Task 2），`subtitle.py` 默认参数与 `editing.py` 均从此导入。
- 音频滤镜输出标签在所有分支恒为 `[aout]`，与 `editing.py` 的 `-map "[aout]"` 一致。
- `escape_filter_path` 仅在 `editing.py` 定义与使用；Task 7 测试从 `editing` 导入 —— 一致。
- 前端 `SubtitleTemplate` / `SubtitleCue` 字段与 `api.py` 的 `list_subtitle_templates`（`model_dump()` + `id`）、`get_subtitle_preview`（index/start_s/end_s/text/speaker）返回结构一致。

**已核对的构造签名**（这三处若按直觉写会直接跑不通，测试代码中已用正确形式）
- `StoryboardFrame` 必填 `id` + `scene_id`（`models.py:353-354`）；**没有 `description` 字段**，自由文本字段叫 `action_description`。
- `VideoTask` 必填 `id` / `project_id` / `image_url` / `prompt`（`models.py:172-176`）；`frame_id` 是 Optional。
- `toast` 是从 `@/store/toastStore` 导出的单例，用 `toast.error(title)` / `toast.success(title)`（`toastStore.ts:76-87`）。
- `signed_response` 定义在 `api.py:136`，新端点照现有端点用法调用。

**唯一需在实现时就地确认的一处**（已在正文标注，不是占位符）
- `VideoAssembly.tsx` tab 条的具体 className —— Task 9 Step 4 要求沿用相邻 tab 的既有写法，避免视觉不一致。

---

Plan complete and saved to `docs/superpowers/plans/2026-07-26-v-1-first-complete-film.md`.
