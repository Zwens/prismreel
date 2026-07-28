"""BGM 节拍检测，供 Assembly 的卡点功能使用。

只依赖 numpy 与 ffmpeg。不引入 librosa（会带来 numba/joblib/soxr/audioread
一串依赖），也不引入 scipy——全程只需要一次 STFT，用 numpy 的 rfft 直接写
比为它装一个 50MB 的包划算。

流程：ffmpeg 解码单声道 PCM -> STFT 谱通量 onset 包络 -> 自相关取周期。

测速对音乐本就不是能保证正确的问题，最常见的失败是**倍频歧义**（锁到半速或
倍速）：实测 128 BPM 的点击轨会被读成 63.8。这里用对数正态先验压制，但压不干净，
所以 UI 必须让用户能直接改 BPM——detect 的结果是建议，不是判决。
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List, Optional

import numpy as np

from ...utils import get_logger

logger = get_logger(__name__)

# 22.05kHz 对节拍来说绰绰有余，且解码量只有 44.1k 的一半。
SAMPLE_RATE = 22050
# 每帧 ~11.6ms，足以分辨 200 BPM（300ms 一拍）的节拍间隔。
HOP = 256

BPM_MIN = 60.0
BPM_MAX = 200.0
# 只分析开头这么长。配乐的速度在一分半内不会变到影响卡点，而全曲分析会让
# STFT 的中间数组随时长线性膨胀（5 分钟的曲子要几百 MB）。
MAX_ANALYSIS_S = 90.0
# 先验中心。绝大多数配乐落在这附近，用它把倍频错误拉回来。
BPM_PRIOR_CENTER = 120.0
BPM_PRIOR_WIDTH = 0.9


class BeatAnalysisError(RuntimeError):
    """解码失败、音频过短等无法给出结果的情况。"""


def decode_mono(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """用 ffmpeg 把任意音频解码成单声道 float32。"""
    if not os.path.isfile(path):
        raise BeatAnalysisError(f"音频文件不存在: {path}")

    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-f", "f32le", "-ac", "1", "-ar", str(sr), "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as e:
        raise BeatAnalysisError("未找到 ffmpeg，无法解码 BGM") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", "replace").strip()
        raise BeatAnalysisError(f"ffmpeg 解码失败: {stderr[:200]}") from e

    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size < sr:  # 不足 1 秒，测不出周期
        raise BeatAnalysisError("音频过短，无法检测节拍")
    return y


def _stft_magnitude(y: np.ndarray, nperseg: int, hop: int) -> np.ndarray:
    """加汉宁窗的 STFT 幅度谱，形状 (freq, frames)。

    只为 onset 包络服务，所以不补零、不要相位——省掉 scipy 依赖。
    用 sliding_window_view 取帧，避免为每一帧复制一份数据。
    """
    if y.size < nperseg:
        raise BeatAnalysisError("音频过短，无法计算 onset 包络")

    window = np.hanning(nperseg).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(y, nperseg)[::hop]
    return np.abs(np.fft.rfft(frames * window, axis=1)).T


def onset_envelope(y: np.ndarray, sr: int = SAMPLE_RATE, hop: int = HOP):
    """谱通量 onset 包络。返回 (envelope, envelope_fps)。

    只累加能量**上升**的部分——音符起始表现为频谱能量突增，
    衰减部分是噪声，计入会糊掉峰值。
    """
    mag = _stft_magnitude(y, nperseg=hop * 4, hop=hop)
    flux = np.maximum(0.0, np.diff(mag, axis=1)).sum(axis=0)
    if flux.size == 0:
        raise BeatAnalysisError("音频过短，无法计算 onset 包络")
    return flux - flux.mean(), sr / hop


def estimate_bpm(env: np.ndarray, env_fps: float) -> float:
    """自相关测速，叠加对数正态先验压制倍频错误。"""
    env = env - env.mean()
    if not np.any(env):
        raise BeatAnalysisError("音频没有可用的节奏信息（可能是静音或纯音）")

    ac = np.correlate(env, env, mode="full")[len(env) - 1:]

    lag_lo = max(1, int(env_fps * 60.0 / BPM_MAX))
    lag_hi = int(env_fps * 60.0 / BPM_MIN)
    lag_hi = min(lag_hi, len(ac) - 1)
    if lag_hi <= lag_lo:
        raise BeatAnalysisError("音频过短，无法在合理 BPM 区间内测速")

    lags = np.arange(lag_lo, lag_hi + 1)
    strength = ac[lag_lo:lag_hi + 1].astype(np.float64)
    candidate_bpm = 60.0 * env_fps / lags

    # 对数正态先验：偏离 120 BPM 越远压得越狠。这是压制 64/240 这类
    # 倍频误判的标准做法，但压不干净——UI 侧必须能手动改。
    prior = np.exp(-0.5 * (np.log2(candidate_bpm / BPM_PRIOR_CENTER) / BPM_PRIOR_WIDTH) ** 2)

    return float(candidate_bpm[int(np.argmax(strength * prior))])


def analyze(path: str, sr: int = SAMPLE_RATE) -> Dict[str, Any]:
    """分析一个音频文件，返回 BPM、拍点时间与总时长。

    拍点是按 BPM 铺的**均匀网格**，相位取 onset 包络与脉冲串相关性最强处。
    对稳定速度的配乐足够；不做逐拍跟踪（那需要的复杂度换不来卡点场景的收益）。
    """
    y = decode_mono(path, sr)
    duration_s = len(y) / sr

    # 拍点网格要铺满整首曲子，但测速只看开头一段就够（见 MAX_ANALYSIS_S）
    env, env_fps = onset_envelope(y[: int(MAX_ANALYSIS_S * sr)], sr)
    bpm = estimate_bpm(env, env_fps)

    period_frames = 60.0 * env_fps / bpm
    # 在一个周期内滑动脉冲串，取包络能量最大的相位
    offsets = np.arange(0, int(round(period_frames)))
    if offsets.size == 0:
        offsets = np.array([0])
    scores = []
    for off in offsets:
        idx = np.round(np.arange(off, len(env), period_frames)).astype(int)
        idx = idx[idx < len(env)]
        scores.append(env[idx].sum() if idx.size else -np.inf)
    best_offset = int(offsets[int(np.argmax(scores))])

    beat_times: List[float] = []
    t = best_offset / env_fps
    interval = 60.0 / bpm
    while t < duration_s:
        beat_times.append(round(t, 4))
        t += interval

    return {
        "bpm": round(bpm, 2),
        "beat_interval_s": round(interval, 4),
        "first_beat_s": round(best_offset / env_fps, 4),
        "beat_times": beat_times,
        "duration_s": round(duration_s, 3),
    }


def snap_to_beats(
    source_duration_s: float,
    beat_interval_s: float,
    *,
    min_beats: int = 1,
    max_beats: Optional[int] = None,
) -> float:
    """把一个镜头的时长吸附到最接近的整数拍。

    结果**不会超过原始时长**——渲染只能剪短，不能凭空补帧。所以一个比
    1 拍还短的镜头会原样返回，而不是被拉长到 1 拍。
    """
    if beat_interval_s <= 0:
        return source_duration_s

    beats = round(source_duration_s / beat_interval_s)
    beats = max(min_beats, beats)
    if max_beats is not None:
        beats = min(beats, max_beats)

    target = beats * beat_interval_s
    if target > source_duration_s:
        # 向下取到能放进原片长的拍数；放不下 1 拍就保持原样。
        beats = int(source_duration_s // beat_interval_s)
        if beats < min_beats:
            return source_duration_s
        target = beats * beat_interval_s
    return target
