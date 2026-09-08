# DashScope 下线 / Gemini + BytePlus Ark 双平台接入 —— 设计说明

- 日期：2026-09-08
- 状态：已定稿，待转实施计划
- 影响范围：LLM、图像生成、视频生成、语音合成、模型目录、设置页、构建依赖

## 1. 背景与目标

PrismReel 当前把阿里云 DashScope 同时当作五种东西在用：LLM 后端、图像模型来源、视频模型来源、TTS 供应商，以及 Kling / Vidu / PixVerse 三家的代理通道。这使得 `DASHSCOPE_API_KEY` 成为整个应用的唯一硬性凭证——设置页把它标为必填，缺失时剧本、分镜、配音三条主链路全部不可用。

本次改造的目标是把模型侧完全迁移到用户实际持有凭证的两个平台：**Google Gemini 官网直连**与 **BytePlus ModelArk（国际站）**。

**硬性约束：用户只有 `GEMINI_API_KEY` 与 `ARK_API_KEY` 两个凭证。** 所有设计必须在这两个平台的能力范围内闭合，不引入第三方供应商。这条约束是本文档一切取舍的前提。

阿里云对象存储（OSS）**不在本次范围内**，继续保留。它是产物存储，不是模型服务，现有项目的图片与视频都存在其上。

## 2. 已确认的决策

| 编号 | 决策 | 说明 |
|---|---|---|
| D1 | 彻底移除 DashScope | `DASHSCOPE_API_KEY` 及其全部代码路径删除，不保留任何降级通道 |
| D2 | Kling / Vidu 切 vendor 直连 | 两家去掉 dashscope backend，`default_backend` 改为 `vendor`。用户无这两家 key，实际会显示为缺凭证不可用 |
| D3 | PixVerse 整体下架 | 该家族只有 dashscope 一条通道，无 vendor 直连可切 |
| D4 | 不接 Google Veo | 视频由 Seedance 承担 |
| D5 | 旧项目自动映射 | 引用已下架模型的项目在读取时改写为新模型并回写落盘 |
| D6 | 分四步按能力域切换 | LLM → 图像 → TTS → 拔除，每步结束应用可运行 |
| D7 | TTS 迁到 Gemini TTS | ARK 平台无任何 TTS 模型（实测确认），Gemini 的 30 个预置音色是唯一选择 |
| D8 | 声音克隆 / 音色设计下架 | 两个平台均不提供音色克隆能力，无替代方案 |
| D9 | OSS 保留 | 不动 `ALIBABA_CLOUD_*` 与 OSS 相关代码 |
| D10 | **V2V 保留**，改路由到 Seedance | Seedance 全系支持 `VideoEditing`（实测确认），现有 `seedance.yaml` 漏标了该模态，需补 |
| D11 | 图像双供应商：Gemini（默认）+ Seedream | Gemini 支持 14 张参考图含 4 张角色一致性，为短剧刚需；Seedream 与 Seedance 同厂，风格更连贯 |
| D12 | 存量音色绑定做迁移映射 | 51 处角色音色绑定按性别 + 特征就近映射到 Gemini 音色 |

### 2.1 决策修订记录

以下决策在设计过程中被推翻过，记录在此以免后续实施时按旧结论行事：

- **D10 原为「V2V 整体移除」**。依据是 `seedance.yaml` 声明的 `supported_modalities: [t2v, i2v, r2v]`。用真实 `ARK_API_KEY` 调 `/api/v3/models` 后发现，Seedance 四个在售型号的 `task_type` 均含 `VideoEditing` 且 `input_modalities` 含 `video`——**是目录漏标，不是平台不支持**。结论反转为保留。
- **图像端点由 `/v1beta/interactions` 改为 `generateContent`**（实施第 2 步时实测）。两者
  都能出图且都支持 `aspectRatio`，但 interactions 把图像埋在 `steps[1].content[0].data`，
  generateContent 直接回 `candidates[0].content.parts[*].inlineData.data`，浅一层且
  parts 里混着文本说明也好扫描。实测 9:16 请求返回 768x1376，比例正确。
- **曾计划引入 MiniMax** 承接中文音色与音色克隆。因用户仅持有 Gemini 与 ARK 两个凭证，该方案作废，克隆能力确认无法保留。

## 3. 供应商最终形态

| 能力 | 改造前 | 改造后 | 所需凭证 |
|---|---|---|---|
| LLM（剧本 / 分镜 / 提示词润色） | Qwen via DashScope | Gemini | `GEMINI_API_KEY` |
| 文生图 / 图生图 | wan2.7-image-pro、qwen-image-* | Gemini 图像（默认）+ Seedream | `GEMINI_API_KEY`、`ARK_API_KEY` |
| 语音合成 | CosyVoice / qwen3-tts via DashScope | Gemini TTS | `GEMINI_API_KEY` |
| 音色克隆 / 音色设计 | CosyVoice 复刻 | **无替代，下架** | — |
| 文生视频 / 图生视频 / 参考生视频 | happyhorse + kling/vidu/pixverse 代理 | Seedance | `ARK_API_KEY` |
| 视频编辑（v2v） | wan2.7-videoedit、happyhorse-1.0-video-edit | Seedance（`VideoEditing`） | `ARK_API_KEY` |
| 对象存储 | 阿里云 OSS | 不变 | `ALIBABA_CLOUD_ACCESS_KEY_ID` / `_SECRET` |

Kling 与 Vidu 的家族定义保留在目录中并切到 vendor backend，但用户无对应凭证，UI 会按既有的凭证就绪机制标记为不可用。

## 4. 供应商事实核验

以下均为 2026-09-08 当日核验的结果，实现时若与线上不符以线上为准。

### 4.1 Gemini 端点（抓取自 ai.google.dev）

- 原生端点有两套，实测均可用：`POST /v1beta/interactions`（`input` 数组 + `response_format`）与
  `POST /v1beta/models/{model}:generateContent`（`contents` + `generationConfig.responseModalities`）。
  **图像实现选用 generateContent**，理由见 2.1 修订记录；TTS 端点在第 3 步实测后再定。
- OpenAI 兼容层：`https://generativelanguage.googleapis.com/v1beta/openai/`。支持 chat completions、流式、function calling、结构化输出、图像理解；官方标注仍为 beta，不支持的参数会被静默忽略。
- 连通性：本机 curl 直连返回 403（缺 key，端点可达），无需代理。

### 4.2 Gemini 型号

- LLM 稳定版：`gemini-3.8-flash`、`gemini-3.7-flash`、`gemini-3.6-flash`、`gemini-3.5-flash`、`gemini-3.5-flash-lite`、`gemini-3.1-flash-lite`、`gemini-2.5-flash`、`gemini-2.5-flash-lite`、`gemini-2.5-pro`。已弃用：`gemini-2.0-flash`、`gemini-2.0-flash-lite`、`gemini-3-pro-preview`。
- 图像稳定版：`gemini-3.1-flash-image`（Nano Banana 2）、`gemini-3.1-flash-lite-image`、`gemini-3-pro-image`（Nano Banana Pro）、`gemini-2.5-flash-image`。已弃用：`imagen-4.0-generate`。
- TTS：`gemini-3.1-flash-tts-preview`、`gemini-2.5-flash-preview-tts`、`gemini-2.5-pro-preview-tts` —— **全部为 preview，无稳定版**。

### 4.3 Gemini 图像能力

- 宽高比：`1:1`、`3:2`、`2:3`、`3:4`、`4:3`、`4:5`、`5:4`、`9:16`、`16:9`、`21:9`
- 分辨率：1K 全系支持；2K / 4K 仅 Flash 与 Pro；0.5K 仅 Flash Lite
- 参考图上限 14 张（10 物体 + 4 角色一致性 + 3 风格）——强于原 Wan 通道，角色一致性是能力提升
- 返回 base64，字段形如 `{"type":"image","data":...,"mime_type":...}`

### 4.4 Gemini TTS 能力

- 输出为 base64 的 24kHz / 16bit / 单声道 PCM，**需自行封装 WAV 头**（CosyVoice 直接返回已编码音频，此处多一步）
- 30 个预置音色，官方仅给出特征词，**未标注性别**：Zephyr(Bright)、Puck(Upbeat)、Charon(Informative)、Kore(Firm)、Fenrir(Excitable)、Leda(Youthful)、Orus(Firm)、Aoede(Breezy)、Callirrhoe(Easy-going)、Autonoe(Bright)、Enceladus(Breathy)、Iapetus(Clear)、Umbriel(Easy-going)、Algieba(Smooth)、Despina(Smooth)、Erinome(Clear)、Algenib(Gravelly)、Rasalgethi(Informative)、Laomedeia(Upbeat)、Achernar(Soft)、Alnilam(Firm)、Schedar(Even)、Gacrux(Mature)、Pulcherrima(Forward)、Achird(Friendly)、Zubenelgenubi(Casual)、Vindemiatrix(Gentle)、Sadachbia(Lively)、Sadaltager(Knowledgeable)、Sulafat(Warm)
- 支持 90+ 语言自动识别（**含普通话**）；单说话人与双说话人
- **不支持音色克隆，不支持按文字描述设计音色**

### 4.5 BytePlus Ark 实测（用真实 `ARK_API_KEY` 调 `GET /api/v3/models`）

区域：国际站 `https://ark.ap-southeast.bytepluses.com/api/v3`。返回 55 个模型，其中 43 个在售（非 `Shutdown`）。

**语音合成：不存在。** 43 个在售模型中，没有任何一个的 `output_modalities` 含 `audio`，也没有 `TextToSpeech` 任务类型。仅 `seed-2-0-mini-260428` / `seed-2-0-lite-260428` 支持 `SpeechToText`（语音转文字，方向相反）。**这是「TTS 只能用 Gemini」这一结论的实证依据。**

**视频编辑：全系支持。** 以下四个在售型号 `task_type` 均含 `MultimodalToVideo`、`VideoExtension`、`VideoEditing`，`input_modalities` 均含 `video`：

```
dreamina-seedance-2-0-260128        in=[image, video, audio, text]
dreamina-seedance-2-0-fast-260128   in=[image, video, audio, text]
dreamina-seedance-2-0-mini-260615   in=[text, image, video, audio]
dreamina-seedance-2-5-260628        in=[text, image, video, audio]
```

这些 `api_model_id` 与现有 `seedance.yaml` 中登记的一致。

**图像生成：在售 6 个。**

```
seedream-5-0-260128            [ImageToImage, TextToImage]
dola-seedream-5-0-pro-260628   [ImageToImage, TextToImage]
seedream-4-5-251128            [TextToImage, ImageToImage]
seedream-4-0-20260415          [ImageToImage, TextToImage]
seedream-4-0-250828            [ImageToImage, TextToImage]
seedream-3-0-t2i-250415        [TextToImage]        (Retiring)
```

连通性：`ark.ap-southeast.bytepluses.com` 可达，无需代理。

## 5. 环境变量

新增：

```
GEMINI_API_KEY=...                                          # 必填
GEMINI_BASE_URL=https://generativelanguage.googleapis.com   # 可选，留空用默认
```

`GEMINI_BASE_URL` 沿用 `src/utils/endpoints.py` 既有的 `{PROVIDER}_BASE_URL` 约定，在 `PROVIDER_DEFAULTS` 中增加一行即可，无需新机制。保留该覆盖口是为了将来切换中转地址时不必改代码。

移除：`DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`KLING_PROVIDER_MODE`、`VIDU_PROVIDER_MODE`、`PIXVERSE_PROVIDER_MODE`。后三者在只剩单一 backend 后已无意义。

保留不动：`ARK_API_KEY`、`ARK_REGION`、`ARK_BASE_URL`、`ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`、`OSS_*`、`KLING_ACCESS_KEY`、`KLING_SECRET_KEY`、`VIDU_API_KEY`、`OPENAI_*`（第三方 OpenAI 兼容通道继续可用）。

改造后必填凭证为 `GEMINI_API_KEY` 与 `ARK_API_KEY` 两项——前者管文本、图像、配音，后者管视频。缺任一项对应能力不可用，设置页需分别给出就绪指示。

## 6. 后端改造

### 6.1 LLM

`src/apps/comic_gen/llm_adapter.py`（144 行）已具备 OpenAI 兼容分支，Gemini 官方提供兼容层，因此改造量最小：

- 新增 `provider == "gemini"` 分支，`base_url` 取 `get_provider_base_url("GEMINI")` 拼上 `/v1beta/openai/`，`api_key` 取 `GEMINI_API_KEY`
- `LLM_PROVIDER` 默认值由 `dashscope` 改为 `gemini`
- `is_configured` 改判 `GEMINI_API_KEY`
- 删除 dashscope 分支

默认模型 `gemini-3.8-flash`（稳定版、最新一代 flash，兼顾速度与成本）；设置页可切至 `gemini-2.5-pro` 用于高质量剧本生成。

`src/apps/comic_gen/llm.py`（1475 行）：第 761、923、1220–1221、1361–1362 行共 6 处 `DASHSCOPE_API_KEY` 判断与中英文报错文案改为 `GEMINI_API_KEY`；第 70–73 行关于「DashScope 无法访问 localhost，本地路径必须内联」的注释与逻辑改为针对 Gemini 表述（结论不变，Gemini 同样无法访问本机地址，本地图仍需内联为 data URI）。

### 6.2 图像（双供应商）

**新增 `src/models/gemini_image.py`** —— 实现 `src/models/image.py` 中既有的 `ImageGenModel` 抽象基类，走 `generateContent` + `responseModalities: ["IMAGE"]`（端点选型依据见 2.1 修订记录）：

- 默认模型 `gemini-3.1-flash-image`，高质档 `gemini-3-pro-image`
- 入参映射：现有 `size` 参数转换为 Gemini 的 `aspect_ratio` + `image_size`
- 参考图：本地路径编码为 base64 塞进 `input` 数组，上限 14 张，超出时截断并记日志
- 出参：解析返回的 base64 图像数据写盘

**新增 `src/models/seedream_image.py`** —— 同样实现 `ImageGenModel`，复用现有 Seedance 的 ARK 通道与鉴权：

- 默认模型 `seedream-5-0-260128`，高质档 `dola-seedream-5-0-pro-260628`
- 与 Seedance 同厂，图像风格与后续视频生成更连贯

**`src/models/image.py`（916 行）**：`_image_provider_for()` 增加 `gemini-` 前缀分支，按 id 路由到 `GeminiImageModel`。
**不在本步把 `default_adapter` 换成 Gemini** —— wan / qwen-image 尚未迁移、存量项目仍引用它们，改默认会把这些请求送错供应商且不会报错，只会出坏图；该替换随 wan 家族删除一并进行。`_image_provider_for()` 增加 `seedream` 分支（现有 vidu 分支不动）；`WanxImageModel` 类及其全部 `_generate_*` 私有方法删除；第 37 行 `DASHSCOPE_API_KEY 无效` 文案改为 Gemini。

删除文件：`src/models/wanx.py`（1042 行）、`src/models/qwen_vl.py`（111 行）。已核实 `qwen_vl.py` 在 `src`、`scripts`、`tests` 中均无调用方，可直接删除，无需替代实现。

### 6.3 TTS

现状：`src/audio/tts.py`（368 行）内含 78 个硬编码音色（37 女 / 41 男），分属三个模型——`cosyvoice-v2` 28 个、`cosyvoice-v3-flash` 2 个、`qwen3-tts-flash` 48 个，全部依赖 DashScope。

改造后全部由 Gemini TTS 承担。**这不是首选，是唯一选项**——4.5 节的实测确认 ARK 平台不提供任何 TTS 模型。

**新增 `src/audio/gemini_tts.py`**

- 30 个预置音色的静态注册表（官方固定，不会动态变化），结构对齐现有 `TTS_VOICE_REGISTRY`（`{voice_key: {name, gender, model}}`）
- `name` 用「英文名（中文特征描述）」形式，例如 `Kore（沉稳）`
- PCM → WAV 封装：24kHz / 16bit / 单声道，标准 44 字节 WAV 头
- 默认模型 `gemini-3.1-flash-tts-preview`

**`gender` 字段的取得方式**：Gemini 官方未标注音色性别，只给了特征词。因此需在实施时用 `GEMINI_API_KEY` 对 30 个音色各生成一段中文样本，试听后归类填入注册表。这是第 3 步的第一个动作，不是遗留待办。无法明确判定的标 `Neutral`。

**改造 `src/audio/tts.py`**

- 删除 `_synthesize_cosyvoice`、`_synthesize_qwen3` 两条路径与 78 个音色的硬编码表
- `TTSProcessor` 对外接口（`synthesize`、`list_voices`）保持不变，`pipeline.py` 与 `/voices`、`/tts` 端点无需改动
- 现有 `speed` / `pitch` / `volume` 参数在 Gemini TTS 无直接对应项，需确认能否通过提示词控制；若不能则在 UI 中隐藏这三个控件而非留下无效控件

`src/apps/comic_gen/audio.py`（364 行）第 239 行错误文案改 Gemini。

### 6.4 存量音色迁移

存量项目共 **51 处**角色音色绑定，涉及 7 个音色（`output/` 实测）：

| 旧 voice_id | 名称与特征 | 性别 | 出现次数 |
|---|---|---|---|
| `longxiaochun_v2` | 龙小淳（知性女） | Female | 17 |
| `longzhe_v2` | 龙哲（暖心男） | Male | 11 |
| `longcheng_v2` | 龙诚（睿智青年） | Male | 8 |
| `longze_v2` | 龙泽（阳光男） | Male | 6 |
| `longxiaocheng_v2` | 龙小诚（低音男） | Male | 4 |
| `longxiu_v2` | 龙修（博学男） | Male | 3 |
| `longhan_v2` | 龙翰（深情男） | Male | 2 |

新增 `config/voice_migration.yaml`，与模型退役映射同样在项目读取时改写并回写落盘。

映射规则，按优先级：

1. **性别必须一致**——男声不得映射为女声，反之亦然。这是硬约束，违反会直接毁掉已完成的配音。该约束依赖 6.3 节的音色性别归类先完成
2. 特征标签就近匹配。初步对应关系（待试听后确认）：知性 → Erinome(Clear) 或 Kore(Firm)；暖心 → Sulafat(Warm)；睿智 → Sadaltager(Knowledgeable)；阳光 → Puck(Upbeat) 或 Laomedeia(Upbeat)；低音 → Algenib(Gravelly) 或 Gacrux(Mature)；博学 → Charon(Informative) 或 Rasalgethi(Informative)；深情 → Achernar(Soft) 或 Vindemiatrix(Gentle)
3. 使用量最高的 `longxiaochun_v2`（17 处）优先保证匹配度

未命中映射表的历史 voice_id：**不静默替换**，在角色配音面板标记为「音色已失效，请重选」，并按性别给出推荐候选。

### 6.5 声音克隆与音色设计下架

两个可用平台均不提供音色克隆或按描述设计音色的能力，无替代方案，因此整体下架。

删除 `src/apps/comic_gen/api.py` 中的端点：`POST /voice/clone`、`POST /voice/design/preview`、`POST /voice/design/accept`、`GET /series/{id}/custom_voices`、`DELETE /series/{id}/custom_voices/{voice_id}`，以及 `pipeline.py` 中对应的 `create_voice_clone`、`list_custom_voices`、`voice_design_preview`、`voice_design_save` 方法。

`series.custom_voices[]` 中已有数据**保留在磁盘上不删除**，仅不再读取与渲染。理由：那是用户资产，下架功能不等于有权销毁数据；将来若接入其他克隆供应商还能复用。

### 6.6 V2V（视频编辑）改路由到 Seedance

**本节为决策反转，原计划是整体移除。** 4.5 节的实测显示 Seedance 四个在售型号均支持 `VideoEditing` 且接受 video 输入，现有 `seedance.yaml` 的 `supported_modalities` 漏标了 v2v。

因此：

- 创作台 V2V 模式**保留**，`src/apps/playground/models.py` 的 `Mode` 枚举与 `service.py` 的 v2v 分支均不动
- `seedance.yaml` 补 `v2v` 模态与对应的 mode 条目、`legacy_id: seedance-2.5-v2v`
- 视频输入的 transport mode 需新增，Ark 的 content 数组接受 video_url 项，具体字段名在实施时以 Ark 视频编辑接口文档为准
- `wan2.7-videoedit`、`happyhorse-1.0-video-edit` 映射到 `seedance-2.5-v2v`

### 6.7 其他

- `src/apps/comic_gen/pipeline.py`（4982 行）：第 4385、4496、4626 行三处 `DASHSCOPE_API_KEY` 依赖改 Gemini
- `src/apps/comic_gen/api.py`（4235 行）：第 1122、2819、4104、4155 行——配置模型字段、TTS 报错文案、`/config/env` 的 key 白名单与掩码输出，把 `DASHSCOPE_API_KEY` 换成 `GEMINI_API_KEY`、`GEMINI_BASE_URL`
- `src/utils/endpoints.py`（20 行）：`PROVIDER_DEFAULTS` 删 `DASHSCOPE`，增 `"GEMINI": "https://generativelanguage.googleapis.com"`
- `requirements.txt` / `requirements-docker.txt`：删 `dashscope>=1.20.0`；`openai` 依赖保留（Gemini 兼容层复用它）。Gemini 原生端点与 Seedream 均以 `requests` 直连，**不引入新的 SDK 依赖**
- 删除 `.pyinstaller-hooks/hook-dashscope.py`
- `.env.example`：重写供应商段落

## 7. 模型目录改动

### 7.1 家族增删

- 删除：`config/model_catalog/families/qwen.yaml`、`wan.yaml`、`happyhorse.yaml`、`pixverse.yaml`
- 新增：`config/model_catalog/families/gemini.yaml`
  - `family: gemini`，`provider: google`
  - `routing_prefixes: [gemini-]`
  - `supported_backends: [google]`，`default_backend: google`
  - `credential_sources: {google: [GEMINI_API_KEY]}`
  - `supported_modalities: [t2i, i2i]`
  - `transport.image_input_mode.google: gemini_inline_base64`
  - 模型条目：`gemini-3.1-flash-image`、`gemini-3-pro-image`、`gemini-3.1-flash-lite-image`
- 新增：`config/model_catalog/families/seedream.yaml`
  - `family: seedream`，`provider: byteplus`
  - `routing_prefixes: [seedream-, dola-seedream-]`
  - `supported_backends: [byteplus]`，`default_backend: byteplus`
  - `credential_sources: {byteplus: [ARK_API_KEY]}`
  - `supported_modalities: [t2i, i2i]`
  - 模型条目按 4.5 节实测的在售清单登记，`seedream-3-0-t2i-250415` 状态为 `Retiring` 不予登记
- 修改：`seedance.yaml` —— `supported_modalities` 补 `v2v`，各模型补 v2v mode 与 `legacy_id`
- 修改：`kling.yaml`、`vidu.yaml` —— `supported_backends` 去掉 `dashscope`，`default_backend` 改 `vendor`，删 `backend_env_key`，`credential_sources` 只留 vendor 项，`transport` 各 mode 只留 vendor 映射

### 7.2 系统默认

`config/model_catalog/catalog.meta.yaml`：

```yaml
version: 1
defaults:
  model_settings:
    t2i_model: gemini-3.1-flash-image
    i2i_model: gemini-3.1-flash-image
    image_model: gemini-3.1-flash-image
    i2v_model: seedance-2.5-i2v
    r2v_model: seedance-2.5-r2v
```

`seedance-2.5-i2v` 与 `seedance-2.5-r2v` 为 `seedance.yaml` 中已存在的 `legacy_id`（第 429、464 行），无需新增。

### 7.3 退役映射

下表已按四个待删家族的**完整** id 清单（含容器 id 与 `legacy_id`）逐条核对，无遗漏：

```yaml
version: 1
mappings:
  # --- 图像：wan / qwen → Gemini ---
  wan2.7-image-pro:          gemini-3-pro-image
  wan2.7-image:              gemini-3.1-flash-image
  wan2.6-t2i:                gemini-3.1-flash-image
  wan2.6-image:              gemini-3.1-flash-image
  wan2.5-t2i-preview:        gemini-3.1-flash-image
  wan2.5-i2i-preview:        gemini-3.1-flash-image
  wan2.2-t2i-plus:           gemini-3.1-flash-image
  wan2.2-t2i-flash:          gemini-3.1-flash-image
  qwen-image-2.0-pro:        gemini-3-pro-image
  qwen-image-2.0:            gemini-3.1-flash-image

  # --- 视频：wan / happyhorse / pixverse → Seedance ---
  wan2.7-i2v:                seedance-2.5-i2v
  wan2.7-r2v:                seedance-2.5-r2v
  wan2.7-t2v:                seedance-2.5-t2v
  wan2.6-i2v:                seedance-2.5-i2v
  wan2.6-r2v:                seedance-2.5-r2v
  wan2.6-i2v-flash:          seedance-2.0-fast-i2v
  wan2.5-i2v-preview:        seedance-2.5-i2v
  wan2.2-i2v-plus:           seedance-2.5-i2v
  wan2.2-i2v-flash:          seedance-2.0-fast-i2v
  happyhorse-1.0-i2v:        seedance-2.5-i2v
  happyhorse-1.0-r2v:        seedance-2.5-r2v
  happyhorse-1.0-t2v:        seedance-2.5-t2v
  pixverse-c1-i2v:           seedance-2.5-i2v
  pixverse-c1-r2v:           seedance-2.5-r2v
  pixverse-v5.6-r2v:         seedance-2.5-r2v
  pixverse-v4-i2v:           seedance-2.5-i2v

  # --- 视频编辑：v2v 有替代，不再是断点 ---
  wan2.7-videoedit:          seedance-2.5-v2v
  happyhorse-1.0-video-edit: seedance-2.5-v2v

  # --- 容器 id（带斜杠的家族级 id）→ 对应模态的默认替代 ---
  wan/wan2.7-video:                  seedance-2.5-i2v
  wan/wan2.6-video:                  seedance-2.5-i2v
  happyhorse/happyhorse-1.0-video:   seedance-2.5-i2v
  pixverse/pixverse-v6-video:        seedance-2.5-i2v
  pixverse/pixverse-c1-video:        seedance-2.5-i2v
```

`wan2.7-image-pro` 与 `qwen-image-2.0-pro` 映射到 `gemini-3-pro-image` 而非 flash 档，是为了保持「pro 档对 pro 档」的质量预期——存量项目里 18 处引用的正是 `wan2.7-image-pro`。

**生效时机**：在项目读取路径（`pipeline` 加载项目 JSON 时）做一次改写并**回写落盘**，不在渲染时临时换算。这样老 id 只存在一个版本周期，映射表可在后续版本删除；若只做渲染期换算，映射表将永远无法退休。

映射表随 `scripts/build_model_catalog.py` 一并生成进 `frontend/src/generated/`，前后端共用同一份事实。

### 7.4 重新生成

`scripts/build_model_catalog.py` 与 `scripts/validate_model_catalog.py` 需支持新的 `google` backend、`gemini_inline_base64` transport mode 与 seedance 的 v2v 模态；重新生成 `config/model_catalog/generated/model_catalog.json` 与 `frontend/src/generated/modelCatalog.json`。

## 8. 前端改造

### 8.1 设置页

`frontend/src/components/settings/SettingsPage.tsx`（1084 行）：

- `EnvConfig` 类型：删 `DASHSCOPE_API_KEY`、`KLING_PROVIDER_MODE`、`VIDU_PROVIDER_MODE`、`PIXVERSE_PROVIDER_MODE`；增 `GEMINI_API_KEY`、`GEMINI_BASE_URL`
- `renderApiKeys()`：删 DashScope key 字段与三个 provider mode 切换器（第 674–720 行区域），新增 Gemini 分区——`GEMINI_API_KEY` 必填带就绪指示，`GEMINI_BASE_URL` 可选，placeholder 为默认端点。现有 `ARK_API_KEY` 字段从「可选」提升为「必填」并加就绪指示，因为视频生成已完全依赖它
- 必填校验（第 92 行）：`DASHSCOPE_API_KEY` 改为同时校验 `GEMINI_API_KEY` 与 `ARK_API_KEY`
- 端点配置列表（第 55 行）：`DASHSCOPE_BASE_URL` 条目改为 `GEMINI_BASE_URL`
- 第 342 行关于「Storage(OSS) 保存不应被 DashScope 必填项挡住」的既有豁免逻辑改为针对新的必填项，行为不变

### 8.2 其他前端文件

- `frontend/src/components/EnvConfigChecker.tsx`（49 行）：必填项改为 Gemini + Ark
- `frontend/src/components/project/EnvConfigDialog.tsx`（500 行）：同上
- `frontend/src/lib/modelCatalog.ts`（530 行）：接入退役映射查询函数
- `frontend/src/components/modules/cast/VoiceCloneModal.tsx`（302 行）：删除，连同 `frontend/src/lib/api.ts` 中的克隆相关调用与所有入口按钮
- 角色配音面板：对映射失效的历史音色显示「音色已失效，请重选」+ 同性别推荐候选；若 6.3 节确认 Gemini TTS 不支持语速 / 音调 / 音量调节，则隐藏对应控件
- `frontend/src/components/modules/storyboard-r2v/shot-panel/TaskQueuePanel.tsx`：清理 dashscope 相关引用
- **创作台 V2V 模式相关文件不改**（`ModeSelector.tsx`、`MediaInput.tsx`、`ParameterBar.tsx`、`GalleryView.tsx`、`playgroundModels.ts`、`DetailPanel.tsx`、`PlaygroundPage.tsx`）——v2v 由 Seedance 承接，UI 保持原样
- `frontend/messages/zh.json`、`frontend/messages/en.json`：更新 `dashscopeKeyLabel`、`dashscopeKeyHint` 等文案键为 Gemini 版本，删除克隆相关文案

### 8.3 测试

- `frontend/src/__tests__/provider-credentials.test.ts`：第 35 行「dashscope 系模型要求 DASHSCOPE_API_KEY」用例改为 Gemini 模型要求 `GEMINI_API_KEY`；「多选一」用例因 Kling 只剩单一 backend 需重写
- `frontend/src/__tests__/model-catalog.test.ts`、`endpoint-config.test.ts`：同步更新
- 新增退役映射的单元测试：老 id 能映射到新 id，未知 id 原样返回不报错
- 新增音色迁移的单元测试：**性别一致性是断言重点**，7 个存量音色映射后性别不得改变

## 9. 实施顺序

四步，每步结束应用处于可运行状态。

**第 1 步 —— Gemini LLM**
改 `llm_adapter.py`、`llm.py`、`endpoints.py`，设置页先临时并列新旧 key 字段。
验收：剧本生成、分镜拆解、提示词润色（图生视频与参考生视频两条）跑通。
此步的核心价值是**尽早验证 `GEMINI_API_KEY` 真实可用**——该 key 目前尚未配置到 `.env`。

**第 2 步 —— 图像双供应商**
新增 `gemini_image.py`、`seedream_image.py` 与 `gemini.yaml`、`seedream.yaml`，改 `resolve_image_adapter`。
验收：两家各跑通文生图与图生图；Gemini 多参考图角色一致性生成可用；画幅比例正确。

**第 3 步 —— Gemini TTS + 音色迁移**
子步骤有先后依赖：

1. 用 `GEMINI_API_KEY` 对 30 个音色各生成一段中文样本，试听归类性别与特征（本步第一个动作）
2. 新增 `gemini_tts.py`，填入带性别标注的音色注册表，改造 `tts.py`
3. 依据归类结果编写 `config/voice_migration.yaml`，覆盖 7 个存量音色
4. 删除克隆与音色设计的端点及 UI

验收：`/voices` 返回 30 个带性别标注的音色；中文配音生成与试听跑通，输出 WAV 可正常播放；51 处存量绑定全部映射到有效音色且**性别未错位**。

**第 4 步 —— 拔除 DashScope**
删四个家族、Kling/Vidu 切 vendor、seedance 补 v2v、退役映射、设置页定稿、依赖与构建钩子清理、文档更新。
验收：全链路（新建项目 → 剧本 → 分镜图 → 视频 → 配音 → 导出）跑通；6 个存量项目全部可打开并继续生成；创作台 V2V 模式能选到 Seedance 并跑通一次视频编辑；全仓库 `grep -i dashscope` 只在 CHANGELOG 与历史 spec 中命中。

每步执行后端 `pytest` 与前端 `vitest`；第 4 步额外做一次人工全链路验证。

## 10. 功能损失清单

改造完成后以下能力不再具备：

1. **声音克隆**（上传参考音频复刻音色）—— 消失。Gemini 与 Ark 均不提供，无替代方案
2. **音色设计**（按文字描述生成音色）—— 消失，同上
3. **音色数量与特征** —— 从 78 个中文优化音色缩减到 30 个通用音色。中文配音本身不受影响（Gemini 音色支持普通话），但**音色听感必然改变**，存量 51 处绑定会换成映射后的近似音色
4. **配音的语速 / 音调 / 音量调节** —— 待第 3 步确认；Gemini TTS 若无对应参数则一并失去
5. **PixVerse** —— 整个供应商下架
6. **Kling / Vidu** —— 不再能借 DashScope 通道调用，需自备 `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` 与 `VIDU_API_KEY`。用户无这两家凭证，实际表现为在 UI 中标记不可用
7. **TTS 稳定性下降** —— Gemini TTS 全部型号处于 preview，Google 可能变更或下线，且没有第二家可切换

**未损失**（曾一度以为会丢，经实测证伪）：视频编辑 v2v —— Seedance 支持，能力保留。

## 11. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| Gemini TTS 为 preview 且是唯一 TTS 通道，若变更或下线则无备选 | 配音功能整体中断 | TTS 型号写入配置而非硬编码；`TTSProcessor` 对外接口不变，便于日后接入新供应商。这是本次改造最集中的单点风险 |
| Gemini 音色未标注性别，归类依赖人工试听 | 映射错性别会毁掉存量配音 | 性别一致性写成单元测试断言；归类结果落盘到注册表可复核 |
| `/v1beta/interactions` 为较新的 API 形态，文档与实际可能有出入 | 图像 / TTS 开发返工 | 第 2、3 步各自独立验收，出错不影响已完成步骤 |
| Seedance v2v 的 Ark 请求字段未核实 | 视频编辑改造返工 | 第 4 步实施前先用 `ARK_API_KEY` 打一次真实请求确认字段，方法与 4.5 节相同 |
| 退役映射遗漏某个老模型 id | 个别老项目打不开 | 映射表以四个待删家族的完整 id 清单为准生成；未命中的 id 保持原值并在 UI 标记「已下架」而非崩溃 |
| 两个 key 都成必填，任一失效即半个应用不可用 | 可用性下降 | 设置页对两个 key 分别给出就绪指示与失效提示，不混为一谈 |
| OpenAI 兼容层为 beta，不支持的参数被静默忽略 | LLM 行为与预期不符且难察觉 | 只使用文档明确支持的参数；结构化输出结果做校验（`llm.py` 已有 `model_echo` 等校验机制） |

## 12. 不做的事

- 不接 Google Veo（视频由 Seedance 承担）
- 不引入第三方 TTS 或克隆供应商（用户只有 Gemini 与 Ark 两个凭证，这是硬约束）
- 不动阿里云 OSS 与 `ALIBABA_CLOUD_*` 凭证
- 不为本次切换新建通用 provider 抽象层（`model_catalog` 已承担该职责）
- 不删除用户已有的 `custom_voices` 数据
- 不把 LLM 迁到 Ark —— Ark 上有 deepseek-v4、glm-5-2、seed-2-0-pro 等可用型号，但 Gemini 已覆盖该能力，双写没有收益
- 不改 `UpdateChecker.tsx` 中指向 `alibaba/prismreel` 的仓库地址（另案处理）
