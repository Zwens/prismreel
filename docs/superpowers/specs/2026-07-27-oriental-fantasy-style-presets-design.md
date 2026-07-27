# 风格定调 · 东方奇幻预设扩充

> **版本**: v1.0 — 2026-07-27
> **模块**: Art Direction（风格定调）
> **状态**: 设计已确认，待实施

---

## 1. 背景与问题

风格定调（Art Direction）是 Studio 的第一步，为全片定义视觉基准。它的预设库在
`src/apps/comic_gen/style_presets.json`，当前 15 个预设分 4 类：

| 分类 | 数量 | 预设 |
|------|------|------|
| `live_action` 真人电影级 | 5 | 电影写实、黑色电影、日系胶片、港片、对称粉彩 |
| `japanese_anime` 日式动漫 | 4 | 手绘暖调、现代赛璐璐、80-90年代都市、时尚战斗 |
| `american_animation` 美式动画 | 3 | 风格化 3D、图像小说、绘画感 3D |
| `style_lab` 风格实验室 | 3 | 暗黑奇幻、东方水墨奇幻、黏土定格 |

**问题**：东方奇幻题材（仙侠 / 修真 / 玄幻 / 古风 / 古偶 / 武侠）是国产短剧的主力品类，
但预设库里只有一个「东方水墨奇幻」，且被埋在「风格实验室」这个杂烩分类下。用户要做仙侠剧时，
没有可直接套用的画风基准。

### 与调色模块的区分（重要）

`docs/superpowers/specs/2026-07-26-prismreel-professional-studio-roadmap-design.md` §5.1
规划了 19 个**调色预设**（含仙侠 / 修真 / 玄幻 等），那是后期 FFmpeg 色彩参数，属于尚未实现的
调色模块。本 spec 处理的是**风格定调的生图提示词预设**，两者数据结构与作用阶段完全不同：

| | 风格定调预设（本 spec） | 调色预设（roadmap §5.1） |
|---|---|---|
| 数据 | `positive_prompt` / `negative_prompt` / 缩略图 | 阴影/高光偏移、饱和度、颗粒、Bloom |
| 作用 | 生成阶段，决定 AI 出什么画 | 后期阶段，决定成片色调 |
| 状态 | 已上线，本 spec 扩充内容 | 未实现，需完整立项 |

调色模块不在本 spec 范围内。

---

## 2. 目标

在风格定调新增一个「东方奇幻」分类，补齐 6 个东方题材画风预设，让东方题材在一个 Tab 内可选完。

**非目标**：
- 不实现调色模块
- 不重做已有 4 个分类的预设
- 不压缩存量 16 张缩略图（独立优化，另行处理）

---

## 3. 方案

### 3.1 分类调整

`style_presets.json` 的 `categories` 新增一项，`style_lab` 的 `sort_order` 顺延：

```json
{ "id": "oriental_fantasy", "name": "Oriental Fantasy", "name_zh": "东方奇幻", "sort_order": 4 }
```

`style_lab` 由 `sort_order: 4` 改为 `5`。

调整后的 Tab 排列：

```
[真人电影级 5] [日式动漫 4] [美式动画 3] [东方奇幻 7] [风格实验室 2]
```

### 3.2 预设变更

**迁移 1 个**：`chinese_ink_fantasy` 的 `category` 由 `style_lab` 改为 `oriental_fantasy`。
其余字段不动。

**新增 6 个**（全部 `category: "oriental_fantasy"`）：

| id | name_zh | 调性 | 提示词核心 | 参考质感 |
|----|---------|------|-----------|---------|
| `xianxia_ethereal` | 仙侠 · 缥缈仙境 | 青绿冷调 + 柔光溢出 | jade-green / pale cyan、soft bloom、流云飞袂、淡紫高光、低对比 | 苍兰诀、长月烬明 |
| `cultivation_qi` | 修真 · 天地灵气 | 深蓝紫底 + 金色高光 | indigo / violet 暗部、熔金轮廓光、灵气漩涡、径向神光、高对比高锐度 | 凡人修仙传、斗破苍穹 |
| `xuanhuan_primordial` | 玄幻 · 洪荒异世 | 暗红橙 + 深青底 | 深青去饱和暗部、暗橙余烬高光、洪荒巨构遗迹、大气雾霾、暗角 + 轻微色差 | 将夜、九州 |
| `guofeng_period_drama` | 古风 · 庭院深深 | 暖黄低饱和 | 琥珀低饱和、自然窗光、浅景深、宋式内景、克制刺绣、胶片颗粒 | 知否、清平乐 |
| `palace_romance` | 古偶爱情 · 桃花灼灼 | 粉暖柔调 + 柔焦 | 粉桃中间调、暖紫阴影、柔焦光晕、落英、纱质汉服、低对比梦幻散景 | 花千骨、香蜜沉沉烬如霜 |
| `wuxia_jianghu` | 武侠 · 江湖风尘 | 尘土冷灰 + 刀锋冷冽 | 去饱和土色、冷钢高光、风沙布屑、竹林 / 客栈、硬直射光、胶片颗粒 | 徐克、胡金铨 |

前 5 个的调性沿用 2026-07-26 会话中确认的国产剧品类色调方向。第 6 个「武侠」原方案未涉及，
本 spec 定为**写实江湖**路线（尘土与钢），刻意与「仙侠」的仙气柔光拉开距离，避免两个预设出图撞车。

每个预设按现有 schema 补全：`name` / `name_zh` / `subtitle_zh` / `description` /
`best_for` / `avoid_for` / `positive_prompt` / `negative_prompt` / `sample_prompt` /
`thumbnail` / `object_position`。

`avoid_for` 互相排除，让卡片的适用提示有真实区分度——例如「仙侠」avoid 写实武打，
「武侠」avoid 仙气柔光。

### 3.3 无需代码改动

后端 `/art_direction/presets`（`src/apps/comic_gen/api.py:3733`）直接透传 JSON；
前端分类 Tab 与筛选完全由 JSON 驱动（`ArtDirection.tsx:53,529`）。因此**本次不改任何前后端代码**。

分类迁移不影响已有项目：项目存储的 `style_config` 只保留 id / 名称 / 提示词
（`ArtDirection.tsx:197` `toStyleConfig`），不含 `category`。

---

## 4. 缩略图

### 4.1 现状约束

- 存放于 `frontend/public/assets/styles/`，git 跟踪，16 个文件约 32MB
- `static/assets/styles/` 是 `next build` 产物，已被 gitignore，PyInstaller 通过
  `--add-data static;static` 打包（`build_windows.ps1:116`）。**因此只需改 `frontend/public/`**
- 命名规范：`{category}__{preset_id}__{scene_slug}__{orientation}.png`
- 缺图时前端有降级（显示占位图标，`ArtDirection.tsx:965`），不会崩

### 4.2 生成流程

新增 `scripts/generate_style_thumbnails.py`：

1. 读 `style_presets.json`，对指定 preset id 用它自己的 `positive_prompt` +
   `negative_prompt` + `sample_prompt` 拼提示词
2. 调 `wan2.7-image-pro`（DashScope，凭 `DASHSCOPE_API_KEY`），尺寸 `1440*1440`
3. 每个风格出 4 张候选，落到 `output/style_thumbs/<preset_id>/cand_N.png`
4. **由用户挑选定稿**，不自动选图

缩略图即该预设的真实出图样本，而非另画的示意图——所见即所得。

**尺寸选择**：模型档位无 4:3，取 1440×1440 方图。卡片是 `aspect-[4/3]` + `object-cover`
（`ArtDirection.tsx:964`），详情弹窗是 `object-contain` 全图，方图两边都不吃亏，
再用 `object_position` 微调裁切焦点。

### 4.3 定稿落盘

用 ffmpeg 压到长边 1200px，按命名规范放入 `frontend/public/assets/styles/`，
回填 JSON 的 `thumbnail` 字段。

**格式用 JPEG，不用 PNG**。这些是照片类图像，PNG 无损编码在 1200px 下仍是
2.1–2.6MB，压不到目标体积；JPEG（ffmpeg `-q:v 3`）同样观感下只有 210–350KB。
`thumbnail` 是自由路径字段，前端 `<img src>` 不关心扩展名。

存量 16 张 PNG 不动。

---

## 5. 验证

### 5.1 新增 `tests/test_style_presets.py`

当前无任何测试覆盖 `style_presets.json`。补 5 条：

1. JSON 可解析，`version == 2`
2. 每个 preset 的 `category` 都存在于 `categories` 中（防孤儿预设——本次迁移
   `chinese_ink_fantasy` 正是该风险）
3. preset id 唯一
4. 必填字段齐全：`name` / `name_zh` / `positive_prompt` / `negative_prompt`
5. 声明了 `thumbnail` 的，文件必须真实存在于 `frontend/public/assets/styles/`

第 5 条挡住「JSON 写了路径但图没放」。

### 5.2 端到端

- `curl http://localhost:17177/art_direction/presets` 确认返回 5 个分类 / 21 个预设
- Playwright 打开风格定调页截图，确认「东方奇幻」Tab 出现、7 张卡片渲染正常

---

## 6. 影响面

| 文件 | 改动 |
|------|------|
| `src/apps/comic_gen/style_presets.json` | 新增 1 分类 + 6 预设，1 个预设改分类 |
| `frontend/public/assets/styles/*.jpg` | 新增 6 张 |
| `scripts/generate_style_thumbnails.py` | 新增 |
| `tests/test_style_presets.py` | 新增 |

前后端代码零改动。

---

## 7. 实施记录（2026-07-27 完成）

出图评审阶段发现两个提示词缺陷，都会影响用户实际套用的结果，不只是缩略图：

- **修真**：`floating talisman glyphs` 让模型渲染出满屏可读汉字（敕令/归元/镇/破…），
  4 张候选全废。删除该词后恢复正常。
- **古风**：`silk scroll paper grain` 把模型推向平面工笔插画，与「参考知否/清平乐」的
  真人正剧意图相悖，也与同分类其他 5 个预设的影视质感不成体系。改写为
  period-drama cinematography，并把 id 从 `guofeng_silk_scroll` 改为
  `guofeng_period_drama`、名称改为「古风 · 庭院深深」，让名实相符（当时无任何项目引用旧 id）。

此外中式场景会绕过普通的 `text` negative 生成招牌与碑刻，6 个预设统一补充
`chinese characters, calligraphy, signage`。

**顺带修复**：`src/models/image.py` 的 `_download_image` 用 `os.rename` 做「原子重命名」，
但在 Windows 上目标文件已存在时会抛 `FileExistsError`，导致任何重复生成到同一路径的
调用在图片已下载完成后才失败。改为 `os.replace`。

**验证**：`tests/test_style_presets.py` 6 条通过；`/art_direction/presets` 返回
5 分类 / 21 预设；前端东方奇幻 Tab 下 7 张卡片缩略图全部 `naturalWidth > 0` 加载成功。
