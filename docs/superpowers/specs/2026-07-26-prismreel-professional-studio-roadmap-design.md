# PrismReel Studio 专业影视工作室平台 — 产品规划与分期设计

> **设计日期**: 2026-07-26
> **状态**: 已确认
> **版本**: v1.1 — 整合国产剧风格预设反馈（5.1 调色模块大幅扩展）

### 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-07-26 | 初稿：三期路线图 + 全部模块设计 |
| v1.1 | 2026-07-26 | 5.1 调色模块重写：9 通用预设 → 19 预设（+10 国剧品类）；新增动态调色关键帧机制；新增高级特效叠加；预设 UX 增加分类 Tab/参考作品/AI 推荐 |

---

## 1. 背景与战略定位

### 1.1 当前产品状态

PrismReel Studio 是一个 AI 原生短漫剧创作平台，已具备完整的 5 步生成管线：

```
Script → Art Direction → Cast → Storyboard → Assembly
```

| 步骤 | 能力 |
|------|------|
| **Script** | LLM 实体提取（角色/场景/道具）、Series/Episode 管理、跨集资产共享、"上回书说到"前情提要 |
| **Art Direction** | 预设风格 + 自定义正/负向提示词、AI 风格推荐、Series 级继承/覆盖 |
| **Cast** | 角色/场景/道具卡片视图、资产生成（T2I/I2I）、角色一致性管线、语音绑定 |
| **Storyboard** | LLM 剧本→分镜结构化、镜头语言（景别/角度/运镜/站位/灯光/音效）、提示词润色（双语）、I2V+R2V 双模式、多 Provider 抽卡 |
| **Assembly** | 分镜视频选取、BGM 预设、配音生成（CosyVoice）、合并导出（FFmpeg concat） |

**已集成模型**：Qwen (LLM)、Wanx 2.6 (T2I/I2I/I2V/R2V)、Kling、Vidu、HappyHorse、CosyVoice (TTS)、Demucs (音源分离)

### 1.2 战略定位

| 维度 | 选择 |
|------|------|
| **产品定位** | 专业影视工作室 — 面向 AI 短剧创业者的专业制作工具 |
| **目标用户** | AI 短剧创业者（用 AI 批量生产短剧/漫剧的内容创业团队） |
| **核心价值** | 让 AI 生成的短剧质量达到「可发布」水平，不需要外部工具二次处理 |
| **战略路径** | 纵深打磨（内容质量优先）→ 三期内把现有管线每步质量从 60 分拉到 90 分 |

### 1.3 核心差距分析

**第一层（工具 → 专业工具）**：
- 无专业剪辑（trim/split/变速/转场）
- 无画面调色（不同分镜色调不一致）
- 无字幕系统（短剧必需品）
- 多轨音频混音未完工（Mock 状态）

**第二层（工具 → 平台）**：
- 无团队协作 / 版本管理
- 无批量生产 / 素材复用
- 无多平台分发 / 成本管控 / 内容安全

本期规划聚焦**第一层**（内容质量），第二层留待后续版本。

---

## 2. 设计原则

1. **不破坏现有管线** — 新功能作为 Assembly 步骤的增强，或替换现有 Mock 实现，不影响上游 4 步
2. **AI 辅助而非 AI 替代** — 每项能力提供 AI 智能默认值，但保留人工精确控制入口
3. **所见即所得** — 所有编辑操作提供实时预览，不靠「生成后才知道」
4. **本地计算优先 + 云端 AI 加速** — FFmpeg 处理在本地/后端执行，AI 分析调用云端 API
5. **渐进交付** — 每期可独立上线、独立产生用户价值

---

## 3. 分期路线图

```
V1 — 「后期工坊」(8周)        V2 — 「音画大师」(8周)        V3 — 「成片工厂」(8周)
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│ 专业剪辑引擎         │  │ AI 智能调色          │  │ 模板系统                 │
│ 多轨时间轴编辑器      │  │ 动态字幕系统         │  │ 版本快照                 │
│ 转场效果库           │  │ 多轨音频混音台       │  │ 批量渲染队列             │
│ 变速与画面裁剪       │  │ SFX 音效库集成       │  │ 一键多平台导出           │
│ 视频预览与逐帧控制    │  │ BGM 智能推荐         │  │ 质量自检评分 + 成本预估   │
└─────────────────────┘  └─────────────────────┘  └─────────────────────────┘
```

**总周期**：24 周（约 6 个月），每期独立交付。

**核心指标**：
- 从剧本到可发布成片，**无需离开 PrismReel**
- 用户生成 10 个分镜视频，**≥80% 不需要外部工具二次处理**
- 一集 3 分钟短剧，从剧本到成片 **≤2 小时**

---

## 4. V1「后期工坊」— 详细设计

### 4.1 专业剪辑引擎

**现状**：`ExportManager.render_project()` 是 Mock，实际只有 `merge_videos()` 做 FFmpeg concat 合并。

**目标**：在 Assembly Step 内构建完整的非破坏性视频编辑体验。

```
Assembly Step 新增「编辑」Tab：

┌──────────────────────────────────────────────────────────────┐
│ 多轨时间轴 (Timeline)                                        │
│ ═══════════════════════════════════════════════════════════  │
│ 视频轨: [Shot1][Shot2][Shot3][Shot4]...   ↔️ 拖拽排序         │
│ 音频轨: ════配音═══ ═══BGM═══ ═══SFX═══                     │
│ 字幕轨: ════════字幕层════════                               │
│ 标尺:   0s────5s────10s────15s────20s                        │
└──────────────────────────────────────────────────────────────┘

操作面板: ✂️ 分割  ⏩ 变速  📐 裁剪  🔄 替换  🗑️ 删除
          ↔️ 拖拽排序  ⏱️ 时长调整  🔀 转场
```

#### 功能清单

| 功能 | 实现方式 | 优先级 |
|------|---------|--------|
| **时间轴拖拽排序** | 复用现有 `reorder_frames` + 前端 Timeline 组件从零重写（现有为视觉 Mock） | P0 |
| **分割 (Split)** | FFmpeg `-ss -to` 精确切割，一个分镜可切成多段。前端 canvas + video 逐帧定位切割点 | P0 |
| **裁剪 (Crop)** | FFmpeg `crop` 滤镜，支持 9:16→1:1→16:9 等比例裁剪，拖拽选框交互 | P0 |
| **变速 (Speed)** | FFmpeg `setpts` 滤镜，0.25x~4x 可调，保持音调不变 | P1 |
| **替换片段** | 允许用户上传或选择已有视频片段插入时间轴任意位置 | P1 |
| **逐帧预览** | HTML5 video + canvas 逐帧步进（← → 键），精确到帧定位编辑点 | P1 |

#### 技术方案

- **前端**：重写 `Timeline.tsx`（当前是视觉 Mock），集成 WaveSurfer.js 显示音频波形辅助定位
- **后端**：新增 `src/apps/comic_gen/editing.py::EditingEngine` 类
  - 封装 FFmpeg 命令构建
  - 支持非破坏性编辑链 — 生成 Edit Decision List (EDL) 而非反复渲染
  - 渲染时一次性应用全部编辑操作
- **数据模型**：新增 `TimelineTrack` / `EditDecision` Pydantic 模型
  ```python
  class EditDecision(BaseModel):
      shot_id: str
      operation: str  # trim / split / speed / crop / replace
      params: dict    # {start_frame, end_frame, speed_factor, crop_rect, ...}

  class TimelineData(BaseModel):
      tracks: List[TimelineTrack]
      edits: List[EditDecision]
  ```

### 4.2 转场效果库

**现状**：分镜间硬切。

**目标**：提供影视级转场效果，用户一键应用到相邻分镜间。

```
转场面板 (Transitions Panel)

基础转场:
  ├── 硬切 (默认)
  ├── 淡入淡出 (Dissolve)     ⏱️ 300ms / 500ms / 1000ms
  ├── 黑场过渡 (Fade to Black)
  └── 白场过渡 (Fade to White)

动态转场:
  ├── 推入 (Push)             方向: ← → ↑ ↓
  ├── 擦除 (Wipe)             方向: → / ← / ↓ / ↑
  ├── 缩放 (Zoom In/Out)
  └── 旋转 (Spin)

自定义: 时长 100-2000ms
```

#### 技术方案

- 全部转场基于 FFmpeg `xfade` 滤镜实现：
  ```
  ffmpeg -i shot1.mp4 -i shot2.mp4 -filter_complex \
    "xfade=transition=dissolve:duration=0.5:offset=4.5" output.mp4
  ```
- 在两个分镜间插入 `TransitionFrame` 数据模型（不改变原 Shot）
- 前端实时预览：Canvas 渲染两张相邻首帧 + CSS transition 近似转场效果
- 转场时长作为 Timeline 中两个 Shot 之间的拖拽手柄

### 4.3 视频预览与导出增强

| 功能 | 描述 | 优先级 |
|------|------|--------|
| **实时预览窗口** | Assembly 页面嵌入视频播放器，实时播放当前时间轴内容 | P0 |
| **分辨率选择** | 720p / 1080p / 原分辨率 | P0 |
| **码率控制** | 预设（抖音 2Mbps / 快手 1.5Mbps / B站 6Mbps / YouTube 8Mbps）+ 自定义 | P1 |
| **导出进度 SSE** | 参照现有 `refine_batch_generator` SSE 模式推送渲染进度 | P0 |
| **格式选项** | MP4 (H.264/H.265) / MOV / WebM | P1 |

#### 技术方案
- 预览：前端用拼接的 Blob URL（各视频片段已生成，无需重渲染）
- 导出：后端 FFmpeg 完整渲染管线（apply edits → transitions → encode）
- 进度 API：`GET /projects/{script_id}/export/progress` SSE 端点，推送 `{current_frame, total_frames, eta}`

---

## 5. V2「音画大师」— 详细设计

### 5.1 AI 智能调色 + 国产剧风格预设库

**现状**：完全缺失。各分镜由不同模型/不同 batch 生成，色调/亮度/饱和度参差不齐。

**目标**：提供影视级调色能力，内置 19 个精准锚定国产短剧品类的风格预设，支持动态分镜级调色关键帧。

#### 预设库总览（19 个）

**A 组 — 通用风格（9 个，保留）**：

| # | 名称 | 图标 | 核心调性 | FFmpeg 参数方向 |
|---|------|------|---------|----------------|
| 01 | 电影感 | 🎬 | 高对比、胶片颗粒、暗角 | contrast↑, grain, vignette |
| 02 | 日系 | 🌸 | 低饱和、柔光、过曝高光 | saturation↓, glow, exposure↑ |
| 03 | 复古 | 📻 | 褪色暖黄、颗粒、暗角 | colorbalance(warm), grain, vignette |
| 04 | 冷调 | ❄️ | 偏蓝青、低饱和 | colorbalance(blue-cyan), saturation↓ |
| 05 | 暖调 | ☀️ | 偏橙黄、高光暖 | colorbalance(orange-yellow), warmth↑ |
| 06 | 赛博 | 🤖 | 霓虹青紫、高饱和 | colorbalance(cyan-magenta), saturation↑↑ |
| 07 | 清新 | 🌿 | 高亮、低对比、偏绿 | brightness↑, contrast↓, colorbalance(green) |
| 08 | 暗黑 | 🖤 | 压暗、去饱和、冷青阴影 | brightness↓, saturation↓↓, shadows(cold) |
| 09 | 港风 | 🌆 | 高饱和暖色、胶片颗粒、偏黄绿 | saturation↑, colorbalance(yellow-green), grain |

**B 组 — 国产剧品类（10 个，新增）**：

| # | 名称 | 图标 | 核心调性 | 参数要点 | 参考质感 |
|---|------|------|---------|---------|---------|
| 10 | 仙侠 | 🏔️ | 青绿冷调 + 柔光溢出 | 阴影偏青绿，高光偏淡紫/淡蓝，降饱和保留绿色通道，加 Bloom 柔光层，对比度中低 | 《苍兰诀》《长月烬明》 |
| 11 | 修真 | ⚡ | 深蓝紫底 + 金色高光 | 暗部拉向深蓝紫，高光加暖金色溢出，对比度拉高，加径向光晕模拟"灵气"，锐度提升 | 《凡人修仙传》《斗破苍穹》 |
| 12 | 古风 | 📜 | 暖黄低饱和 + 绢纸质感 | 整体偏暖黄，饱和度大幅降低，中间调提亮，加轻微颗粒模拟绢帛纹理，暗角适中 | 《知否》《清平乐》 |
| 13 | 古偶爱情 | 🌺 | 粉暖柔调 + 柔焦 | 中间调偏粉橙，高光柔化溢出，阴影偏暖紫，饱和度中等偏高（突出肤色），对比度偏低 | 《花千骨》《香蜜沉沉烬如霜》 |
| 14 | 玄幻 | 🌋 | 暗红橙 + 深青底 | 阴影压向深青/墨绿，高光偏暗红橙，整体饱和度中等但红色通道拉高，对比度拉满，加暗角和轻微色差 | 《将夜》《九州》系列 |
| 15 | 都市 | 🏙️ | 冷暖对撞 (Teal & Orange) | 阴影偏冷蓝，高光偏暖橙，对比度高，饱和度中高，锐度提升，轻微光晕 | 《都挺好》《三十而已》 |
| 16 | 穿越 | ⏳ | **动态双模式** | 现代线：正常色温/中等对比/自然饱和。古代线：偏暖黄或冷青（根据朝代），加颗粒，降饱和，柔光。穿越瞬间：闪白 + 径向模糊 + 色散 | 《庆余年》《步步惊心》 |
| 17 | 悬疑 | 🌫️ | 青绿冷调 + 低饱和 + 颗粒 | 整体偏青绿，饱和度大幅降低，暗部压暗但不死黑，高光压暗，加明显胶片颗粒，对比度中偏高 | 《隐秘的角落》《沉默的真相》 |
| 18 | 大反转 | 💥 | **三段式动态变化** | 前期：温暖正常色调（放松警惕）。反转点：瞬间切换冷青去饱和 + 暗角收紧。揭秘后：极端对比，暗部偏冷蓝，高光偏惨白 | 《开端》《回来的女儿》 |
| 19 | 同人 | 🎭 | 高饱和 + 强风格化 + 可过曝 | 饱和度拉满，对比度拉高，色相可自由偏移，加明显暗角和光斑，允许过调/漏光/色差等高级特效叠加 | B站/LOFTER 同人剪辑风 |

#### 预设 UX 设计

```
调色面板 (Color Grading) — 更新版

┌─────────────────────────────────────────────────────┐
│  Tab: [🎨 全部预设] [🏔️ 古风仙侠] [🏙️ 都市现代]     │
│       [🌫️ 悬疑惊悚] [🎭 创意风格]                   │
│                                                     │
│  预设卡片网格:                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 🏔️ 仙侠   │ │ ⚡ 修真   │ │ 📜 古风   │            │
│  │ 青绿冷调   │ │ 深蓝金高光│ │ 绢帛质感   │            │
│  │ 参考:苍兰诀│ │ 参考:凡人 │ │ 参考:知否 │            │
│  │ [预览] [套用]│ │ [预览] [套用]│ │ [预览] [套用]│            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  ... 更多卡片 ...                                    │
│                                                     │
│  🤖 AI 智能推荐: 根据剧本分析结果推荐最佳预设           │
│     "检测到古装爱情题材 → 推荐: 🌺 古偶爱情 / 📜 古风"  │
│                                                     │
│  [应用到全部 Shot] [仅应用到选中 Shot]                 │
└─────────────────────────────────────────────────────┘
```

#### 动态调色关键帧（新增能力）

部分预设（穿越 ⏳ / 大反转 💥）要求同一剧集内不同时间段使用不同调色参数。这需要引入**调色关键帧**机制：

```
时间轴调色轨道 (Color Timeline)
┌─────────────────────────────────────────────────────┐
│ Shot1      Shot2      Shot3      Shot4      Shot5   │
│ ├─ 现代线 ─┤                    ├─ 古代线 ──────────┤│
│ 自然色调    │                    │ 暖黄+颗粒+柔光     ││
│            ├─ 穿越瞬间 ─────────┤                   ││
│            │ 闪白+径向模糊+色散  │                   ││
│                                                      │
│  关键帧: ●────────────────────●                      │
│         现代调色               古代调色                │
│         过渡时长: 0.5s (穿越瞬间特效)                 │
└─────────────────────────────────────────────────────┘
```

#### 功能清单（更新版）

| 功能 | 实现方式 | 优先级 |
|------|---------|--------|
| **19 预设 LUT 库** | 每个预设编译为 `.cube` LUT + 参数元数据 JSON（色调方向/参考作品/适用品类标签） | P0 |
| **AI 智能推荐预设** | LLM 分析剧本标题+正文 → 输出品类标签 → 匹配 Top-3 预设 | P0 |
| **AI 自动统一色调** | QWEN-VL 分析参考帧色彩分布 → 自动输出 FFmpeg eq/colorbalance 参数 | P0 |
| **手动参数调整** | FFmpeg `eq` + `colorbalance` + `unsharp` + `vignette` 参数滑块 | P0 |
| **逐段独立调色** | 每个 Shot 存储独立 `ColorGrade`，支持「全局 LUT + 逐段 override」| P0 |
| **动态调色关键帧** | 时间轴上插入调色切换点，支持过渡时长和特效（闪白/模糊/色散） | P1 |
| **高级特效叠加** | 同人预设扩展：光斑/漏光/色差/过曝等可选叠加层 | P2 |
| **实时预览** | 前端 Canvas + WebGL 加载 LUT shader，参数调整即时预览 | P1 |

#### 技术方案

- LUT 编译管线：`预设参数描述 → 3D LUT 生成器（Python colour-science 库）→ .cube 文件`
  - 方向：手动调参生成 LUT 作为静态资源内置于项目
- FFmpeg 渲染管线（静态调色）：
  ```
  ffmpeg -i shot.mp4 -vf \
    "lut3d=file=style.cube, \
     eq=brightness=0.05:contrast=1.1:saturation=0.95, \
     vignette=PI/4" output.mp4
  ```
- FFmpeg 渲染管线（动态调色关键帧）：
  ```
  # 穿越瞬间特效（闪白 + 径向模糊 + 色散）
  ffmpeg -i shot.mp4 -vf \
    "geq=r='min(255,r+50)':g='min(255,g+50)':b='min(255,b+50)':enable='between(t,3,3.5)', \
     zoompan=z='1.2':d=1:s=1920x1080:enable='between(t,3,3.5)', \
     chromashift=cbh=4:crh=-4:enable='between(t,3,3.5)'" output.mp4
  ```
- 动态调色数据模型：
  ```python
  class ColorGrade(BaseModel):
      preset_id: Optional[str] = None          # 预设编号 (01-19)
      preset_name: Optional[str] = None        # 预设名称
      lut_file: Optional[str] = None
      # 基础参数
      brightness: float = 0.0      # -1.0 to 1.0
      contrast: float = 1.0        # 0.0 to 2.0
      saturation: float = 1.0      # 0.0 to 3.0
      color_temp: int = 5500       # Kelvin
      sharpness: float = 1.0       # 0.5 to 2.0
      vignette: float = 0.0        # 0.0 to 0.5
      # 高级特效（同人等风格扩展）
      grain: float = 0.0           # 0.0 to 1.0 胶片颗粒
      bloom: float = 0.0           # 0.0 to 1.0 柔光溢出
      chromatic_aberration: float = 0.0  # 0.0 to 1.0 色散
      light_leak: float = 0.0      # 0.0 to 1.0 漏光

  class ColorKeyframe(BaseModel):
      """动态调色关键帧 — 用于穿越/大反转等叙事性色调切换"""
      at_shot_index: int            # 在哪个 Shot 处切换
      at_time_offset: float = 0.0   # 该 Shot 内的偏移秒数
      color_grade: ColorGrade       # 切换到的调色参数
      transition_duration: float = 0.5  # 过渡时长(秒)
      transition_effect: Optional[str] = None  # flash_white / radial_blur / chroma_shift

  class ProjectColorGrade(BaseModel):
      """项目级调色配置"""
      global_grade: ColorGrade                # 全局基础调色
      per_shot_overrides: Dict[str, ColorGrade] = {}  # shot_id → 逐段覆盖
      keyframes: List[ColorKeyframe] = []     # 动态关键帧序列
  ```
- AI 推荐：LLM 分析剧本 → 输出 `genre_tags` + 置信度 → 与预设的品类标签做匹配 → 返回 Top-3
- 参考作品展示：预设元数据中存储参考作品名称，前端卡片渲染时展示

### 5.2 动态字幕系统

**现状**：完全缺失。短剧必须带烧录字幕才能发布。

**目标**：AI 自动生成字幕 → 样式编辑 → 烧录到视频。

```
字幕编辑器 (Subtitle Editor)

Step 1: 生成字幕
  🤖 AI 语音识别 (Paraformer) → 自动生成带时间码的 SRT
  📝 支持导入外部 SRT/ASS 文件
  📋 表格视图手动编辑 (行号 + 起始时间 + 结束时间 + 文本)

Step 2: 字幕样式
  字体 / 大小 / 颜色 / 描边 / 位置 / 背景条 / 动画效果

Step 3: 字幕轨道预览
  时间轴与视频轨对齐，拖拽调整时间码

支持: 中文字幕 / 双语字幕（中+英）/ 多语
```

#### 功能清单

| 功能 | 实现方式 | 优先级 |
|------|---------|--------|
| **AI 语音→字幕** | DashScope Paraformer 语音识别（免费额度充足）→ SRT 输出 | P0 |
| **SRT 编辑** | 前端表格视图编辑器（`subtitles-parser` 库解析），支持增删改行 | P0 |
| **字幕烧录** | FFmpeg `subtitles` 滤镜 + ASS 样式标签 | P0 |
| **动态字幕效果** | ASS override tags（逐字出现/弹跳/淡入），FFmpeg `ass` 滤镜 | P1 |
| **双语字幕** | 中文上方叠加英文翻译。LLM 翻译 + 手动校对 | P1 |
| **字幕模板** | 预设样式模板（抖音风/电影风/综艺风），一键切换 | P2 |

#### 技术方案

- 语音识别：DashScope `paraformer-realtime-v2` API
  - 输入：合并后的视频音频轨
  - 输出：带 `begin_time` / `end_time` 的逐句文本
- SRT 编辑：前端使用 `subtitles-parser` 库解析 → 表格 UI 编辑 → 序列化回 SRT
- 烧录：`ffmpeg -i video.mp4 -vf "subtitles=subtitle.srt:force_style='FontName=Alibaba PuHuiTi,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'" output.mp4`
- 字幕样式数据模型：
  ```python
  class SubtitleStyle(BaseModel):
      font_family: str = "Alibaba PuHuiTi"
      font_size: int = 16
      primary_color: str = "#FFFFFF"
      outline_color: str = "#000000"
      outline_width: int = 2
      position: str = "bottom"  # bottom / top / center
      background: bool = False
      animation: str = "none"   # none / word_by_word / fade / bounce
  ```

### 5.3 多轨音频混音台

**现状**：`AudioGenerator` 大部分是 Mock。配音 TTS 已有 CosyVoice 实现但 BGM/SFX/混音未完工。

**目标**：类 DAW 简化版的多轨混音控制。

```
音频混音台 (Audio Mixer)

🎤 配音轨 (Dialogue):          音量 80%
   逐段可调音量/语速/音高

🎵 BGM 轨:                    音量 30%
   预设库 + 智能推荐 + 上传本地
   支持循环 / 淡入淡出 / 自动闪避配音

🔊 SFX 音效轨:                音量 60%
   AI 自动从视频场景推荐音效
   Freesound API 集成

📊 总输出电平表: -12dB  (不爆音)
```

#### 功能清单

| 功能 | 实现方式 | 优先级 |
|------|---------|--------|
| **配音轨编辑** | 扩展 TTS Pipeline → 增加逐段 FFmpeg `volume`/`atempo`/`asetrate` 后处理 | P0 |
| **BGM 库** | 现有 8 预设 → 扩展至 50+（Pixabay Music API 免费库） | P0 |
| **自动闪避 (Ducking)** | FFmpeg `sidechaincompress`：检测到配音时自动压低 BGM 音量 | P0 |
| **混音导出** | FFmpeg `amix` 多轨混音 → 与视频轨一并输出 | P0 |
| **BGM 智能推荐** | LLM 分析剧本情绪曲线 → 推荐匹配的 BGM 分段列表 | P1 |
| **SFX 自动推荐** | LLM 分析 Shot `action_description` → 推荐音效关键词 → Freesound API 搜索 Top-3 | P1 |
| **SFX 库集成** | Freesound API 接入 + 内置 200+ 常用音效 | P1 |
| **电平表可视化** | 前端 Web Audio API `AnalyserNode` 实时显示 | P1 |

#### 技术方案

- BGM 闪避混音：`ffmpeg -i bgm.wav -i dialogue.wav -filter_complex "[0:a][1:a]sidechaincompress=threshold=0.1:ratio=4:attack=5:release=50[ducked];[ducked][1:a]amix=inputs=2:duration=first"`
- BGM 情绪映射：LLM 分析剧本全文 → 输出情绪时间线 → 映射至 BGM 分类（calm / uplifting / epic / mystery / sad / tension / lofi / fantasy）
- 数据模型（扩展现有 `MixSettings`）：
  ```python
  class MixSettings(BaseModel):
      bgm_url: Optional[str] = None
      dialogue_volume: float = 0.8
      bgm_volume: float = 0.3
      sfx_volume: float = 0.6
      ducking_enabled: bool = True
  ```

---

## 6. V3「成片工厂」— 详细设计

### 6.1 模板系统

**现状**：每个新项目从零配置风格/模型/提示词。

**目标**：用户可保存、复用、分享项目模板。

```
模板包含的配置快照:
  ✅ 风格配置 (Art Direction + LUT 预设)
  ✅ 模型设置 (T2I/I2I/I2V/R2V 模型选择 + 比例)
  ✅ 提示词模板 (润色/视频/R2V 提示词)
  ✅ 字幕样式 (字体/位置/动画)
  ✅ 音频预设 (BGM 列表/音量/闪避参数)
  ✅ 分镜模板 (默认镜头语言/时长建议/默认转场)
  ✅ 导出预设 (分辨率/码率/平台)

创建方式: 从现有项目 [提取模板] / 手动新建
使用方式: 创建项目时选择模板 → 预填全部配置
覆盖模式: 全用模板 / 部分覆盖（如只用风格+模型，其他自定义）
```

#### 技术方案

- 数据模型：
  ```python
  class ProjectTemplate(BaseModel):
      id: str
      name: str
      description: str = ""
      category: str  # 古装 / 都市 / 悬疑 / 科幻 / ...
      art_direction: Optional[ArtDirection]
      model_settings: Optional[ModelSettings]
      prompt_config: Optional[PromptConfig]
      subtitle_style: Optional[SubtitleStyle]
      mix_settings: Optional[MixSettings]
      color_grade: Optional[ColorGrade]
      export_presets: List[ExportPreset]
      created_at: float
      usage_count: int = 0
  ```
- 存储：`output/templates.json`
- API：
  - `POST /templates` — 手动创建
  - `POST /templates/from_project/{script_id}` — 从项目提取
  - `GET /templates` — 列表
  - `DELETE /templates/{id}` — 删除
  - `POST /projects/from_template/{template_id}` — 从模板创建

### 6.2 版本快照

**现状**：覆盖式保存（`output/projects.json` 每次 save 覆盖），无历史。

**目标**：自动 + 手动快照，可回溯任意历史版本。

```
版本时间线 (每个项目的快照历史):
v5  今天 16:30  ← 当前（自动: 视频生成后）
v4  今天 15:00  (自动: 每隔 5 次操作)
v3  今天 14:00  (自动: 每 1 小时)
v2  今天 11:30  🔒 手动标记「送审版 v1」
v1  今天 10:15  (自动: 项目创建时)

操作: [恢复到 v2] [预览 v2 元数据] [删除旧版本]
设置: 最大保留 20 个版本，FIFO 自动清理
```

#### 技术方案

- 存储策略：`output/projects/{script_id}/snapshots/v{timestamp}.json`
  - 只存 JSON 配置引用，不复制视频文件（视频 URL 不变）
- 触发策略：
  - 自动：项目创建 / 每 5 次变更操作 / 每 1 小时 / 关键 Milestone（生成完成）
  - 手动：用户显式创建标签快照
- 变更摘要：LLM 自动生成一句话描述（比较前后两个快照 diff → 生成中文描述）
- API：
  - `POST /projects/{script_id}/snapshots` — 手动创建
  - `GET /projects/{script_id}/snapshots` — 列表
  - `POST /projects/{script_id}/snapshots/{version}/restore` — 恢复
  - `DELETE /projects/{script_id}/snapshots/{version}` — 删除

### 6.3 批量渲染队列

**现状**：逐集手动操作。创业者通常同时管理 5-10 部剧，每部 6-12 集。

**目标**：在 Series 级别编排批量渲染任务。

```
批量渲染队列:
  渲染范围: 全部未渲染 / 指定集数 [1-6]
  渲染内容: ☑ 关键帧图 ☑ 分镜视频 ☑ 配音 ☑ 调色 ☑ 字幕 ☑ 最终合并
  并发控制: [2] 个并行任务（避免 API 限流）

⚡ 智能缓存: 未修改的分镜自动跳过（hash 对比检测 stale）
📊 实时进度: SSE 推送每集/每步状态
```

#### 技术方案

- 后端：`src/apps/comic_gen/batch.py::BatchRenderManager`
  - DAG 依赖编排：图片→视频→音频→调色→字幕→合并
  - 缓存失效：对比每个 Shot 的 hash(prompt + reference_images + params)
  - 并发控制：`asyncio.Semaphore(N)` 限制同时 API 调用数
- API：
  - `POST /series/{series_id}/batch_render` — 提交批量任务
  - `GET /series/{series_id}/batch_render/progress` — SSE 进度订阅
  - `POST /series/{series_id}/batch_render/cancel` — 取消

### 6.4 多平台一键导出

**目标**：一键输出适配各平台格式的视频 + 封面图。

```
平台预设:
  抖音    | 快手    | B站      | YouTube
  1080×1920 | 720×1280 | 1920×1080 | 1920×1080
  9:16竖屏  | 9:16竖屏  | 16:9横屏  | 16:9横屏
  H.264    | H.264    | H.264    | H.264

智能适配:
  🤖 自动缩放/裁剪至目标比例
  🤖 自动添加安全边距（避开各平台 UI 遮挡）
  🤖 自动生成封面图（首帧 + 标题 drawtext）

成本预估:
  本集 API 用量汇总:
    LLM tokens:   12,500    约 ¥0.25
    T2I 图片:      8 张     约 ¥0.64
    I2V 视频:      8 段     约 ¥3.20
    TTS 配音:      6 条     约 ¥0.12
    ─────────────────────────────
    本集总成本:              约 ¥4.21
```

#### 技术方案

- FFmpeg 转换链：`scale + pad（竖屏）/ crop（横屏）+ format`
- 安全边距：自动 `pad` 顶部/底部留 120px（避开抖音 UI 遮挡区）
- 封面图：首帧截图 + `drawtext` 叠加标题（用户可自定义文字/位置/字体）
- 成本追踪：各 API 调用完成后记录 token/调用次数，汇总到项目级别
- API：`GET /projects/{script_id}/usage` — 成本查询

### 6.5 质量自检评分

**目标**：导出前自动扫描成片质量，给出可操作的改进建议。

```
质量报告 (5 维度 × 权重):

画面质量 (40%):  分辨率一致性、AI 伪影检测、色调一致性
音频质量 (25%):  爆音检测、口型同步、BGM 与配音冲突
字幕质量 (15%):  时间轴准确、安全区域、阅读速度
节奏与时长 (10%): 单镜头时长、总时长、镜头切换频率
技术规范 (10%):  分辨率、帧率、编码格式、码率符合目标平台要求

可自动修复项: 🔧 一键修复
需人工确认项: ⚠ 跳转到对应位置手动处理
```

#### 检查实现方式

| 检查项 | 技术手段 |
|--------|---------|
| 分辨率一致性 | FFprobe 读取所有片段分辨率 → 对比 |
| AI 伪影检测 | QWEN-VL 逐帧采样 → 评分（可选，成本较高）|
| 色调跳变 | 连续片段间直方图相似度（OpenCV `compareHist`）|
| 爆音检测 | FFmpeg `volumedetect` → 检查峰值是否超过阈值 |
| 口型同步 | 可选：对比 TTS 音频 timecode 与视频脸部运动 |
| 字幕安全区 | SRT 时间轴与帧边界对比 |
| 阅读速度 | 字数/秒数 → 标准范围 3-8 字/秒 |
| 时长异常 | 统计每个 Shot 时长 → 标记超过 95 百分位的 |

#### 技术方案

- 在 Export/Merge 完成后自动执行检查 Pipeline
- 结果存入 `QualityReport` 模型
- 前端在 Assembly「导出」Tab 展示质量报告卡片
- 可自动修复项：调用 FFmpeg 参数调整后重新合成

---

## 7. 技术架构影响

### 7.1 新增后端模块

```
src/apps/comic_gen/
├── editing.py          # V1: EditingEngine — 非破坏性编辑链 + FFmpeg 命令构建
├── color_grade.py      # V2: ColorGrader — LUT 管理 + AI 调色分析
├── subtitle.py         # V2: SubtitleEngine — ASR → SRT → ASS 烧录
├── audio_mixer.py      # V2: AudioMixer — 替换现有 Mock AudioGenerator
├── batch.py            # V3: BatchRenderManager — DAG 编排 + 并发控制
├── quality.py          # V3: QualityChecker — 多维度检查 Pipeline
└── template.py         # V3: 模板 CRUD
```

### 7.2 新增数据模型

```
models.py 扩展:
├── EditDecision, TimelineData          # V1
├── TransitionConfig                    # V1
├── ColorGrade, ColorKeyframe,          # V2: 19 预设库 + 动态调色关键帧
│   ProjectColorGrade, ColorPresetMeta
├── SubtitleStyle, SubtitleTrack        # V2
├── MixSettings (扩展现有)              # V2
├── ProjectTemplate, SnapshotRecord     # V3
├── BatchRenderTask, ExportPreset       # V3
└── QualityReport, UsageSummary         # V3
```

### 7.3 新增前端组件

```
frontend/src/components/modules/
├── Timeline.tsx              # V1: 重写（当前为 Mock）
├── TransitionPicker.tsx      # V1
├── ColorGradePanel.tsx       # V2
├── SubtitleEditor.tsx        # V2
├── AudioMixer.tsx            # V2
├── TemplateManager.tsx       # V3
├── SnapshotTimeline.tsx       # V3
├── BatchRenderPanel.tsx      # V3
├── ExportPresetPanel.tsx     # V3
└── QualityReport.tsx         # V3
```

### 7.4 对外部能力的依赖

| 外部能力 | 用途 | 备注 |
|---------|------|------|
| FFmpeg | 所有视频/音频/字幕处理 | 已集成，需扩展滤镜链 |
| DashScope Paraformer | 语音→字幕 | 免费额度充足 |
| QWEN-VL | 调色分析 / 伪影检测 / 封面分析 | 已有 QwenVLModel 集成 |
| Freesound API | SFX 音效搜索 | 免费，需注册 API key |
| Pixabay Music API | BGM 素材库 | 免费，需注册 API key |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **FFmpeg 滤镜链性能** | 复杂渲染链可能导致导出时间过长 | 非破坏性编辑链一次渲染；智能缓存跳过未变更片段 |
| **前端实时预览流畅度** | Canvas + WebGL 同时处理可能卡顿 | 缩略图代理（low-res proxy）；仅预览当前可见区域 |
| **LUT 兼容性** | .cube 格式 WebGL 加载在不同浏览器表现差异 | 优先测试 Chrome/Edge（目标用户主力浏览器）|
| **语音识别准确率** | Paraformer 对非标准普通话/方言识别率低 | 提供手动编辑入口作为兜底 |
| **批量渲染 API 限流** | 并发过高触发 DashScope 限流 | 并发数可配置；自动重试 + exponential backoff |

---

## 9. 附录：与现有设计的兼容性

### 向后兼容

- V1/V2/V3 所有新功能在 **Assembly 步骤之后**作为独立后期环节
- 不改变现有 Script → Art Direction → Cast → Storyboard → Assembly 管线的数据结构
- 现有 `merge_videos()` 保持可用，新导出管线作为 `export_with_post()` 新增
- 模板/快照为新模块，不影响现有 `projects.json` / `series.json` 的读写

### 现有能力增强

- `AudioGenerator` Mock → V2 中替换为 `AudioMixer` 真实实现
- `ExportManager` Mock → V1 中替换为 `EditingEngine` 真实实现
- `generate_sfx_from_video` Mock → V2 中接入 Freesound API
- 8 个 BGM 预设 → V2 中扩展至 50+

---

> 🎯 本设计文档已获确认，下一步：按 V1 → V2 → V3 顺序，每期独立生成实施计划（Implementation Plan），进入开发。
