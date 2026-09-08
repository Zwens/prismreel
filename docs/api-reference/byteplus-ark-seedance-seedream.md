# BytePlus ModelArk — Seedance 视频 / Seedream 图像

Local staging mirror（模式 B：仓库内 staging，外部 raw archive 与 Context Hub 尚未同步）。

| 项 | 值 |
|---|---|
| Provider | BytePlus ModelArk（国际站，别名 Volcano Ark） |
| Region | `ap-southeast-1` |
| Base URL | `https://ark.ap-southeast.bytepluses.com/api/v3` |
| 抓取日期 | 2026-09-02 |
| 认证 | 仅 API Key（`Authorization: Bearer $ARK_API_KEY`） |

## 来源

| 内容 | URL |
|---|---|
| 在架模型清单（实时） | `GET https://ark.ap-southeast.bytepluses.com/api/v3/models` |
| 创建视频生成任务 | https://docs.byteplus.com/en/docs/ModelArk/1520757 |
| 图像生成 API | https://docs.byteplus.com/en/docs/ModelArk/1541523 |
| 模型价格 | https://docs.byteplus.com/en/docs/ModelArk/1544106 |
| 模型列表 | https://docs.byteplus.com/en/docs/ModelArk/1330310 |

> 文档站是 JS 单页，正文不在裸 HTML 里。正文以 markdown 存在
> `window._ROUTER_DATA` → `…curDoc.MDContent`，抓取时取该字段。

## 一、`/api/v3/models` 实测结果（2026-09-02）

共 55 个模型，43 个非 `Shutdown`。视频与图像相关的在架项：

| model id | name | task_type | status |
|---|---|---|---|
| `dreamina-seedance-2-5-260628` | dreamina-seedance-2-5 | MultimodalToVideo, VideoEditing, VideoExtension | 在架 |
| `dreamina-seedance-2-0-260128` | dreamina-seedance-2-0 | MultimodalToVideo, VideoEditing, VideoExtension | 在架 |
| `dreamina-seedance-2-0-fast-260128` | dreamina-seedance-2-0-fast | MultimodalToVideo, VideoEditing, VideoExtension | 在架 |
| `dreamina-seedance-2-0-mini-260615` | dreamina-seedance-2-0-mini | MultimodalToVideo, VideoEditing, VideoExtension | 在架 |
| `seedance-1-5-pro-251215` | seedance-1-5-pro | ImageToVideo, TextToVideo | 在架 |
| `seedance-1-0-pro-250528` | seedance-1-0-pro | ImageToVideo, TextToVideo | 在架 |
| `seedance-1-0-pro-fast-251015` | seedance-1-0-pro-fast | ImageToVideo, TextToVideo | 在架 |
| `seedance-1-0-lite-t2v-250428` | seedance-1-0-lite-t2v | TextToVideo | **Retiring** |
| `seedance-1-0-lite-i2v-250428` | seedance-1-0-lite-i2v | ImageToVideo | **Retiring** |
| `dola-seedream-5-0-pro-260628` | dola-seedream-5-0-pro | TextToImage, ImageToImage | 在架 |
| `seedream-5-0-260128` | seedream-5-0 | TextToImage, ImageToImage | 在架 |
| `seedream-4-5-251128` | seedream-4-5 | TextToImage, ImageToImage | 在架 |
| `seedream-4-0-250828` | seedream-4-0 | TextToImage, ImageToImage | 在架 |

## 二、视频生成 `POST /contents/generations/tasks`

### 2.1 时长 `duration`（秒）

| 模型 | 默认 | 取值 |
|---|---|---|
| Seedance 2.5 | `-1` | `[4, 30]` 或 `-1` |
| Seedance 2.0 系列（含 fast / mini） | `5` | `[4, 15]` 或 `-1` |
| Seedance 1.5 pro | `5` | `[4, 12]` 或 `-1` |
| Seedance 1.0 pro / pro fast | `5` | `[2, 12]` |

`duration` 与 `frames` 二选一，`frames` 优先。返回的 duration = 实际总帧数 / 24 向下取整，
与实际时长可能有出入。

### 2.2 分辨率 `resolution`

| 模型 | 默认 | 取值 |
|---|---|---|
| Seedance 2.5 | `720p` | 480p / 720p / 1080p |
| Seedance 2.0 | `720p` | 480p / 720p / 1080p / **4k** |
| Seedance 2.0 **fast** | `720p` | **仅** 480p / 720p |
| Seedance 2.0 **mini** | `720p` | **仅** 480p / 720p |
| Seedance 1.5 pro | `720p` | 480p / 720p / 1080p |
| Seedance 1.0 pro / pro fast | `1080p` | 480p / 720p / 1080p |

Seedance 2.5 的 1080p 与 2.0 的 4K 输出使用 10-bit 色深 + H.265/HEVC，部分播放器不兼容。

### 2.3 画面比例 `ratio`

取值：`16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`。

| 模型 | 默认 |
|---|---|
| Seedance 2.5 / 2.0 系列 / 1.5 pro | `adaptive` |
| Seedance 1.0 pro / pro fast | t2v 为 `16:9`，i2v 为 `adaptive` |

### 2.4 编辑与续写 —— **不是独立模型，是子任务类型**

`VideoEditing` / `VideoExtension` 通过 `omni_reference_task_type` 区分，**仅 Seedance 2.5 支持该参数**：

| 值 | 含义 | 约束 |
|---|---|---|
| `auto`（默认） | 模型自行从输入与 prompt 判定 | 判定错时抛异步错误 `InvalidParameter.TaskTypeConstraint` |
| `reference` | 参考图/视频/音频生成新视频 | `ratio`、`duration` 无特殊约束 |
| `edit` | 编辑原视频的画面或音频 | `content` 至少一个 `reference_video`；源视频 **4–30 秒**；`ratio` 必须 `adaptive`；`duration` 必须 `-1` |
| `extend` | 向前或向后续写原视频 | `content` 至少一个 `reference_video`；`ratio` 必须 `adaptive` |

显式指定时在建任务阶段同步校验并立即报错；`auto` 则可能建成任务后才异步失败。
即使显式指定，模型仍会依据 prompt 二次判定，不一致会抛 `InvalidParameter.TaskTypeMismatch`。

**已实调验证（2026-09-08）**。此前 content 里 video 项的确切 JSON 结构在文档中缺失，
只写了 `content.role = reference_video`。以下形状经真实建任务确认被接受：

```json
{"type": "video_url", "video_url": {"url": "<可 GET 的 URL>"}, "role": "reference_video"}
```

同一次请求确认：`omni_reference_task_type: "edit"` 被接受；`--ratio adaptive` 解析为
源视频自身的比例（源为 9:16，返回 `ratio: "9:16"`）；`--duration -1` 使输出保持源片长度
（源 20.6 秒，返回 `duration: 20`）。任务 `cgt-20260908173854-tqf85`，约 3.5 分钟完成。

**实测计价**：一次 720p、20 秒、含视频输入的编辑 = `usage.total_tokens` 872,100，
按 6.40 USD/百万 token 计 **5.58 USD**。即约 **0.28 USD/输出秒**，明显高于官方"典型场景"
折算表里 720p 的 0.231 USD/秒——那张表的前提是**无视频输入**，源视频本身也计入输入 token。
估算 v2v 成本时不能套用那张表。

源视频必须是厂商可 GET 的地址。OSS 签名 URL 可用，但签名绑定 HTTP 方法：
`sign_url('GET', ...)` 签出的地址对 HEAD 返回 403，验证可达性要用带 Range 的 GET。

`content.role = reference_video` 支持的模型：**Seedance 2.5 与 Seedance 2.0 系列**。
也就是 2.0 系列可以做编辑/续写，但**没有** `omni_reference_task_type` 参数可用，只能靠自动判定。

### 2.5 其他参数

| 参数 | 说明 |
|---|---|
| `generate_audio` | 输出带同步音轨；对白建议在 prompt 里用双引号包裹 |
| `camera_fixed` | 固定镜头，**仅** 1.5 pro / 1.0 pro / 1.0 pro fast；参考图场景不支持 |
| `draft` | 草稿模式，**仅** 1.5 pro；草稿固定 480p，不支持末帧返回与离线推理 |
| `return_last_frame` | 返回末帧 PNG，尺寸同视频，无水印 |
| `execution_expires_after` | 任务过期秒数，默认 172800，范围 `[3600, 259200]` |
| `callback_url` | 状态变化时 POST 回调，结构同查询任务响应 |

参考音频约束：2.5 每段 2–30 秒、最多 10 段、总计 ≤30 秒；2.0 系列每段 2–15 秒、最多 3 段、
总计 ≤15 秒，且**不支持纯音频输入**，必须至少带一张参考图或一个参考视频。

## 三、视频计价

计价单位是 **USD / 百万 token**（在线推理），随输出分辨率与「输入是否含视频」变化。

| model id | 在线推理（USD / M tokens） | 离线推理 |
|---|---|---|
| `dreamina-seedance-2-5-260628` | 480p/720p：无视频输入 10.70，含视频 6.40<br>1080p：无视频输入 11.7，含视频 7.0（限时 28% off） | 暂不支持 |
| `dreamina-seedance-2-0-260128` | 480p/720p：7.0 / 4.3<br>1080p：7.7 / 4.7<br>4K：4.0 / 2.4 | 暂不支持 |
| `dreamina-seedance-2-0-fast-260128` | 480p/720p：5.6 / 3.3（限时 25% off） | 暂不支持 |
| `dreamina-seedance-2-0-mini-260615` | 480p/720p：3.5 / 2.1（限时 60% off） | 暂不支持 |
| `seedance-1-5-pro-251215` | 带音频 2.4，不带 1.2 | 带音频 1.2，不带 0.6 |
| `seedance-1-0-pro-250528` | 2.5 | 1.25 |
| `seedance-1-0-pro-fast-251015` | 1 | 0.5 |

官方给的典型场景折算（16:9、5 秒、无视频输入）：

| 模型 | 480p | 720p | 1080p | 4K |
|---|---|---|---|---|
| Seedance 2.5 | 0.103 /秒 | 0.231 /秒 | 0.569 /秒 | — |
| Seedance 2.0 | 0.07 /秒 | 0.15 /秒 | 0.37 /秒 | 0.78 /秒 |
| Seedance 2.0 fast | 0.06 /秒 | 0.12 /秒 | 不支持 | 不支持 |
| Seedance 2.0 mini | 0.04 /秒 | 0.08 /秒 | 不支持 | 不支持 |

限时折扣窗口：2.5 的 1080p 到 2026-09-17 14:00 (UTC+8)；2.0 fast / mini 到 2026-09-07 14:00 (UTC+8)。
**折扣会过期，写进 catalog 的应当是原价，折扣只作展示。**

## 四、图像生成 `POST /images/generations`

### 4.1 `size`

| 模型 / 场景 | 默认 | 取值 |
|---|---|---|
| Seedream 5.0 pro — 生成 | `2K` | `1K` / `1.5K` / `2K` |
| Seedream 5.0 pro — 编辑（含分层） | `auto` | `1K` / `1.5K` / `2K` / `auto` |

也可用方法二直接给 `宽x高` 像素（默认 `2048x2048`），两种方法不可同时使用。
`1.5K` 与 `1K` 同价。

`sequential_image_generation`（默认 `disabled`）设为 `auto` 时可批量生成一组关联图像，
数量由 `sequential_image_generation_options.max_images` 控制。

### 4.2 图像计价（USD / 张）

| model id | 输入 | 输出 |
|---|---|---|
| `dola-seedream-5-0-pro-260628` | 首图免费，第 2 张起 0.003 | 单图：≤2.61 MP（1.5K 及以下）0.045；>2.61 MP 0.09<br>分层分解：0.0225 / 0.045 |
| `seedream-5-0-lite-260128` | 免费 | 0.035 |
| `seedream-4-5-251128` | 免费 | 0.04 |
| `seedream-4-0-250828` | 免费 | 0.03 |

## 五、待核实 / 冲突项

1. **Seedream 5.0 的 model id 对不上**：`/api/v3/models` 返回 `seedream-5-0-260128`（name `seedream-5-0`），
   价格文档写的是 `seedream-5-0-lite-260128`。两者日期后缀相同（`260128`），疑为同一模型的不同命名。
   接入前需实调一次确认网关接受哪个 id。
2. **Seedance 2.0 系列的编辑/续写**：`/models` 的 `task_type` 声明支持 `VideoEditing` 与 `VideoExtension`，
   但 API 文档的 `omni_reference_task_type` 明确只列 Seedance 2.5。2.0 只能走 `auto` 自动判定，
   无法在提交阶段同步校验约束。
3. 视频计价的 token 换算规则文档未给出公式，只给了典型场景折算表。
   若要在 UI 上做成本预估，只能用折算表插值，不能精确计算。
