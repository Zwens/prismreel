# 卡点 · 按 BGM 节拍对齐分镜时长

> **版本**: v1.0 — 2026-07-28
> **模块**: Assembly（成片合成）+ 渲染管线
> **状态**: 设计已确认，待实施

---

## 1. 背景

短视频「卡点」指把每个镜头的切点对齐到 BGM 的节拍上。这是
2026-07-28 会话中用户提出的一批需求的最后一项（画风预设与动作 chip 已完成）。

它被单独拆出来，是因为前两项只往提示词里插文本，而卡点要动**成片渲染的核心路径**。

---

## 2. 实测结论（设计的依据）

设计前对 ffmpeg 与测速算法做了实测，结论直接决定了方案形状。

### 2.1 concat demuxer 的裁剪精度

现有渲染是 `-f concat` 读一个文件列表后重编码（`pipeline.py:2884`）。
concat demuxer 支持逐条 `inpoint` / `outpoint`，实测（源 25fps）：

| 请求 | 期望 | 实得 | 误差 |
|---|---|---|---|
| `inpoint=0, outpoint=2.0` | 2.00 | 2.04 | +1 帧 |
| `inpoint=0, outpoint=10.0` | 10.00 | 10.04 | +1 帧 |
| `inpoint=5.0, outpoint=7.0` | 2.00 | **3.08** | **+1.08s** |
| `inpoint=5.0, outpoint=8.5` | 3.50 | **4.60** | **+1.10s** |

**`inpoint` 会向前吸附到关键帧**，误差可达 1 秒以上，不可用于精确对齐。
`outpoint` 只差 1 帧，且规律确定：

```
emitted_frames = ceil(outpoint × fps) + 1
```

反解得：要精确 N 帧，请求 `outpoint = (N - 1) / fps`。实测验证：

| 目标 | 请求 outpoint | 实得 | 误差 |
|---|---|---|---|
| 0.8 | 0.76 | 0.80 | 0 |
| 1.2 | 1.16 | 1.20 | 0 |
| 2.0 | 1.96 | 2.00 | 0 |
| 2.5 | 2.44 | 2.48 | −0.02（2.5s 不在 25fps 帧网格上） |
| 3.6 | 3.56 | 3.60 | 0 |

**结论**：只裁**出点**，不裁入点。镜头从自然起点播放、剪短到落拍——
这恰好也是卡点的实际需求。残差仅为帧网格量化（上界半帧，25fps 下 20ms），
且因为每段都是整数帧，**误差不累积**。

### 2.2 测速算法

项目已装 numpy 2.3.5 与 scipy 1.17.1（随 torch 传递引入），未装 librosa。
用「ffmpeg 解码 → STFT 谱通量 onset 包络 → 自相关取周期」在合成点击轨上实测：

| 真值 BPM | 测得 | 误差 |
|---|---|---|
| 90 | 90.67 | 0.74% |
| 128 | **63.80** | **50.15%（半频）** |
| 140 | 139.67 | 0.23% |

**结论**：精度够用，但存在经典的**倍频歧义**（锁到半速或倍速）。
应对是两层：算法侧加偏好 90–150 BPM 的先验；UI 侧**让用户能直接改 BPM**。
后者是硬要求——测速对音乐来说本就不是能保证正确的问题，不能做成不可推翻的黑箱。

不引入 librosa：它会带来 numba/joblib/soxr/audioread 一串依赖，
而上述精度已满足需求。

### 2.3 内置 BGM 是占位音频

`output/presets/bgm/` 下 8 个文件全部由 `scripts/generate_placeholder_bgm.py`
用 ffmpeg 合成（正弦和弦 + tremolo），`LICENSES.md` 明确标注
「不是可用的配乐」「不可对外发布」。

**影响**：卡点开箱演示不了——对正弦音测速只会锁到 tremolo 频率。
但 `bgm_url` 支持用户上传的 URL（`models.py:583`），所以自备音乐时功能可用。
替换内置 BGM 不在本 spec 范围内。

### 2.4 字幕时间轴的耦合

`collect_render_segments` 返回的 `RenderSegment.duration_s` 同时喂给
concat 列表与 `RenderEngine._write_ass` 的字幕时间轴，代码注释明确警告过
两者不一致会让其后每一条字幕错位（`editing.py:143-149`）。

**因此 `duration_s` 必须返回裁剪后的有效时长**，而不是在别处单独算一遍。

---

## 3. 方案

### 3.1 数据模型

`Frame` 新增：

```python
trim_end_s: Optional[float] = Field(None, description="裁剪后的时长（秒）；None 表示用完整时长")
```

存秒而不是拍数，因为渲染层不该依赖 BPM——BPM 改了，已确定的时长不该被动改写。
UI 层负责把「N 拍」换算成秒。

### 3.2 节拍检测

新增 `src/apps/comic_gen/beats.py`：

- `decode_mono(path, sr)` — ffmpeg 解码成单声道 f32 PCM
- `onset_envelope(y, sr, hop)` — STFT 谱通量，只累加能量上升部分
- `estimate_bpm(env, fps)` — 自相关取周期，叠加对数正态先验（中心 120 BPM）压制倍频错误
- `analyze(path)` — 返回 `{"bpm": float, "beat_times": [float, ...], "duration_s": float}`

新增 `GET /projects/{script_id}/beats`：分析该项目当前的 `bgm_url`。
没有 BGM 时返回 400 并说明原因。

### 3.3 渲染管线

`RenderSegment` 增加 `source_duration_s`，`duration_s` 改为有效（裁剪后）时长：

- `collect_render_segments` 探测原始时长后，若 `frame.trim_end_s` 有值且小于原始时长，
  则 `duration_s = trim_end_s`，并记录原始时长备查
- `merge_videos` 写 concat 列表时，对有裁剪的段追加
  `outpoint = (round(duration_s × fps) − 1) / fps`

fps 从源文件探测（`media_probe`），不硬编码 25。

### 3.4 Assembly UI

- 显示检测到的 BPM，可手动改（含一键 ×2 / ÷2，针对倍频歧义）
- 「按节拍对齐」：每个镜头取最接近的整数拍时长，钳制在 [1 拍, 原始时长]
- 每个镜头显示「×N 拍」，可单独加减

---

## 4. 验证

- `tests/test_beats.py`：对合成点击轨（90/128/140 BPM）断言测速在倍频容差内命中
- `tests/test_render_engine.py` 既有用例：断言加了 `trim_end_s` 后字幕时间轴同步收缩
- 端到端：实际渲染一次，`ffprobe` 核对成片总时长等于各段裁剪时长之和

---

## 5. 不在本 spec 范围内

- 替换内置占位 BGM
- 带节拍网格的可拖拽时间线（`Timeline.tsx` 现仅 77 行，等于新写一个组件）
- 裁剪入点（实测不可行，见 2.1）
