# 设计：BytePlus Ark 模型补全 + 独立「AI 视频」页

日期：2026-09-02
状态：待评审

## 1. 目标

一次性解决四件互相牵连的事：

1. 新增一个独立的「AI 视频」顶层入口，做单条视频生成，并能直接取用系统里已有的素材。
2. 把 Seedance 的 **VideoEditing（编辑）** 与 **VideoExtension（续写）** 两种能力接进来 —— 目前完全没有。
3. 图像侧接入 Seedream 5.0（`seedream-5-0-260128` 与 `dola-seedream-5-0-pro-260628`）。
4. 把各模型的**时长 / 分辨率 / 计费**元数据补全并落进 catalog —— Ark 的 `/api/v3/models`
   不返回这些，只能取自厂商文档。

事实依据全部记录在 `docs/api-reference/byteplus-ark-seedance-seedream.md`（2026-09-02 抓取）。

## 2. 现状

### 2.1 已确认的 catalog 缺陷

对照 Ark 文档核出三处会直接导致请求失败的错误：

| 位置 | 现状 | 应为 |
|---|---|---|
| `families/seedance.yaml:273,300,327` | Seedance 2.5 的 `resolution` 含 `4k` | 2.5 无 4K，仅 480p/720p/1080p |
| `families/seedance.yaml:66,92,122` | Seedance 2.0 的 `resolution` 无 `4k` | 2.0 支持 4K |
| `families/seedance.yaml:167,193,223` | Seedance 2.0 **fast** 含 `1080p` | fast 仅 480p/720p |

即 4K 被挂到了错误的那一代上。另外：

- catalog 中**没有** `seedance-2.0-mini`（`dreamina-seedance-2-0-mini-260615`）。
- 所有 Seedance 条目的 `resolution.default` 写死 `1080p`，厂商默认是 `720p`。
- Seedance 2.5 的 `duration` 未暴露 `-1`（自动时长），而 `-1` 是厂商默认值。

### 2.2 运行时现状

- `src/models/byteplus.py` 只实现了视频任务（`/contents/generations/tasks`），**没有图像能力**。
- `ARK_MODEL_IDS` 只映射了 2.5 的三个 mode。
- Seedance family `default_backend: mulerouter`，2.0 系列全部走 MuleRouter。

### 2.3 阻塞项（需要账号侧操作）

用 `.env` 中的 `ARK_API_KEY`（末四位 `91d2`，与运行中后端 `/config/env` 一致）逐个探测，
账号 `3004342898` **在 Ark 上没有开通任何模型** —— Seedance 全系列与 Seedream 全系列均返回
`has not activated the model`。对照组 `seedream-9-9-nonexistent` 返回 `does not exist`，
证明该探测能区分「不存在」与「未开通」。

连带后果：

- 提交 `d3084d6` 把 Seedance 2.5 切到 Ark 之后，**2.5 目前是坏的**。
- `MULEROUTER_API_KEY` 为空，走 MuleRouter 的 Seedance 2.0 家族同样没有凭证。
- **结论：Seedance 全家当前都不可用。** 因此「2.0 切 Ark」不是迁移，而是让它恢复可用的唯一路径。

开通需在 Ark 控制台操作（需登录），不阻塞编码，**阻塞阶段七的端到端验证**。

## 3. 范围

### 3.1 做

- Seedance catalog 数据修正（2.1 全部条目）
- 新增 `seedance-2.0-mini`
- 新增 `vedit` / `vext` 两种 mode，打通 catalog → 运行时 → 前端
- Seedance 2.0 系列 `default_backend` 切到 `byteplus`
- 新增 `seedream` family 与 Ark 图像运行时
- 新增 `config/model_catalog/pricing.yaml` 及其构建/校验管线
- 新增独立「AI 视频」页与四来源素材选择器

### 3.2 不做

- 不修 `frontend/src/lib/api.ts:1756` 那个指向不存在后端路由的 `save-to-library`（属于 Playground 的独立问题）
- 不接 Seedance 1.x（1.0 lite 已 Retiring；1.0/1.5 pro 与现有能力重叠，无新增价值）
- 不接 Ark 的文本模型（`llm_adapter` 目前是 dashscope，属另一课题）
- 不在 UI 上做精确成本计算（见 6.3）

## 4. 已批准的架构决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 默认分辨率对齐厂商，全部改为 `720p` | 与 Ark 文档一致；Seedance 2.5 从 0.569 USD/秒 降到 0.231 USD/秒。代价是现有项目再生成时默认画质下降，需手动选 1080p |
| D2 | `vedit` / `vext` 各建一个 mode，而非复用 `v2v` | 两者参数约束不同（edit 强制 `duration=-1` + `ratio=adaptive`），分开建模才能在**提交前**同步校验，避免 Ark 建任务后才异步报错 |
| D3 | 计费独立成 `pricing.yaml` | 价格变动频率远高于能力定义；分开后改价不污染 family 定义的 diff |
| D4 | 「AI 视频」为独立顶层入口，不复用 Playground 页 | 用户明确选择 |
| D5 | 共享组件通过 React context 注入 store | 避免复制 5 个组件；代价是要改动 Playground 现有组件，有回归风险 |

## 5. 分模块设计

### M1 — Catalog 数据修正

改 `config/model_catalog/families/seedance.yaml`：

| 模型 | duration | resolution | 默认 |
|---|---|---|---|
| Seedance 2.5（3 个 mode） | `[4,30]`，新增 `-1` 选项 | 480p/720p/1080p（**去掉 4k**） | 720p |
| Seedance 2.0 | `[4,15]` | 480p/720p/1080p/**4k** | 720p |
| Seedance 2.0 fast | `[4,15]` | **仅** 480p/720p | 720p |
| Seedance 2.0 mini（**新增**） | `[4,15]` | **仅** 480p/720p | 720p |

`ratio` 统一为 `16:9 / 4:3 / 1:1 / 3:4 / 9:16 / 21:9 / adaptive`，默认 `adaptive`。

`duration` 需要表达「`-1` = 自动」。现有 `duration.type` 只有 `slider|buttons|fixed`，
新增布尔字段 `allow_auto`，前端在滑杆旁渲染一个「自动」开关；开启时提交 `duration: -1`。

### M2 — pricing.yaml 与构建管线

新增 `config/model_catalog/pricing.yaml`：

```yaml
version: 1
currency: USD
models:
  dreamina-seedance-2-5-260628:
    unit: per_million_tokens          # 厂商 canonical 计价单位
    online:
      "480p": { without_video: 10.70, with_video: 6.40 }
      "720p": { without_video: 10.70, with_video: 6.40 }
      "1080p": { without_video: 11.70, with_video: 7.00 }
    reference_per_second:             # 官方折算表：16:9、5 秒、无视频输入
      "480p": 0.103
      "720p": 0.231
      "1080p": 0.569
    promotions:
      - scope: ["1080p"]
        discount: 0.28
        ends_at: "2026-09-17T14:00:00+08:00"
```

规则：

- **入库的永远是原价**，限时折扣单独放 `promotions`，带明确到期时间。
- 前端只读 `reference_per_second` 做展示，`promotions` 过期则不显示折扣角标。
- 构建脚本把 pricing 合并进生成物的 `models[].pricing`，前端 mirror 同步。

改动点：`src/utils/model_catalog.py` 增加 pricing 加载与合并；
`scripts/validate_model_catalog.py` 增加校验 —— 每个 `active` 且 UI 可见的模型必须有 pricing 条目，
`promotions[].ends_at` 必须可解析。

### M3 — vedit / vext 能力

**Catalog 层**

`src/utils/model_catalog.py:12` 的 `SUPPORTED_SELECTION_GROUPS` 扩为
`("t2i","i2i","image","i2v","r2v","t2v","vedit","vext")`。

Seedance 2.5 新增两个 mode：

| mode | capabilities | duration | ratio | 输入 |
|---|---|---|---|---|
| `vedit` | `[vedit]` | `fixed: -1`（不可改） | `fixed: adaptive` | 1 个源视频，**时长必须 4–30 秒** |
| `vext` | `[vext]` | `[4,30]` + auto | `fixed: adaptive` | 1 个源视频 |

Seedance 2.0 系列：`/api/v3/models` 声明支持 VideoEditing / VideoExtension，
但 `omni_reference_task_type` 参数**只有 2.5 支持**，2.0 只能靠 `auto` 自动判定。
因此 2.0 的这两个 mode 以 `status: hidden` 落库，等实测确认后再放出。

**运行时层**

`src/models/byteplus.py`：

- `ARK_MODEL_IDS` 补齐 2.0 / fast / mini / 2.5 的 vedit / vext 映射。
- 请求体新增 `omni_reference_task_type`（仅 2.5 时下发）与
  `content[].{type: video_url, role: reference_video}`。
- **提交前本地校验**，命中即抛错，不发请求：
  - `vedit`：源视频时长 ∈ [4,30]、`duration == -1`、`ratio == adaptive`
  - `vext`：`ratio == adaptive`
- 异步错误码 `InvalidParameter.TaskTypeConstraint` 与 `InvalidParameter.TaskTypeMismatch`
  需映射成可读文案回传前端。

源视频时长在提交前用 `ffprobe` 读取（项目已依赖 ffmpeg）。

### M4 — Seedance 2.0 切 Ark

`families/seedance.yaml`：`default_backend: mulerouter` → `byteplus`，
`routing_prefixes` 增加 Ark 侧 id 前缀。

由于 2.0 在 MuleRouter 与 Ark 上是两套 id（`seedance/seedance-2.0-video`
vs `dreamina-seedance-2-0-260128`），`ARK_MODEL_IDS` 需补全映射。
`SEEDANCE_PROVIDER_MODE` 环境变量保留，可回切 MuleRouter。

**风险**：两个网关的出片质量与参数语义未必一致，切换后需实测比对。
当前 MuleRouter 无凭证，无法做 A/B，只能记录为待验证项。

### M5 — Seedream family

新增 `config/model_catalog/families/seedream.yaml`，provider `byteplus`：

| 模型 | capabilities | size | 默认 |
|---|---|---|---|
| `dola-seedream-5-0-pro-260628` | t2i, i2i | 1K / 1.5K / 2K（编辑场景另有 `auto`） | 2K |
| `seedream-5-0-260128` | t2i, i2i | 同上 | 2K |

`size` 还支持直接给 `宽x高` 像素（默认 `2048x2048`），与档位二选一，不可同时使用。
本期只暴露档位，像素模式留待后续。

**运行时**：`src/models/byteplus.py` 新增 `BytePlusImageModel`，走
`POST /api/v3/images/generations`（同步接口，与视频的异步任务模式不同）。
`sequential_image_generation` 本期固定 `disabled`。

**待核实**：`/api/v3/models` 返回的 id 是 `seedream-5-0-260128`，
而价格文档写 `seedream-5-0-lite-260128`。探测显示**两个 id 都真实存在**，
说明是两个不同模型而非命名不一致。接入前需确认二者差异，
本期先接 `/models` 里那个（`seedream-5-0-260128`）。

### M6 — 「AI 视频」独立页

**导航**（3 处）

- `components/layout/GlobalSidebar.tsx:8,17` — `GlobalTab` 加 `"aivideo"`，
  `GLOBAL_NAV_ITEMS` 插入 `{ id:"aivideo", icon: Clapperboard, hash:"#/ai-video" }`，
  位置在 `library` 与 `playground` 之间
- `app/page.tsx:463,606` — `currentView` 联合类型与 hash 分支
- `messages/{zh,en}.json` — `nav.aivideo` 与 `aivideo.*` 文案段

**页面** `components/modules/aivideo/AiVideoPage.tsx`

左栏自上而下：模式胶囊（`t2v / i2v / vedit / vext`）→ 模型选择器（仅视频族）→
输入槽（i2v 为首帧图，vedit/vext 为源视频）→ prompt → 参数条 → 生成按钮。
右栏为结果画廊。**不含**图像模式与 `r2v / v2v`。

**状态** `useAiVideoStore.ts` 独立于 `usePlaygroundStore`，避免两页互相改
`mode` / `prompt` / `inputMedia`。轮询与队列逻辑从
`PlaygroundPage.tsx:133-223` 抽成共享 hook `useGenerationRunner(store)`，两边共用。

**组件复用**（D5）：`ModelSelector` / `PromptInput` / `ParameterBar` /
`MediaInput` / `ResultGallery` 目前直接 `usePlaygroundStore(...)` 硬绑，
改为 `<GenerationStoreProvider store={...}>` + `useGenerationStore()`。

**素材选择器** `AssetSourcePicker.tsx`，四个 Tab（替代只认历史的 `AssetPickerModal`）：

| Tab | 数据源 | 取图 |
|---|---|---|
| 素材库 | `libraryApi.getLibraryAssets()` | character 复用 `lib/characterImage.ts`；scene/prop 走 `image_asset.variants[selected_id]`，`image_url` 兜底 |
| 系列 | `listSeries()` → `getSeriesAssets(id)` | 同上 |
| 项目 | `getProjects()` → `getProject(id)` | 分镜帧 `t2i_image_urls[active_t2i_index]` |
| 生成历史 | 沿用 `AssetPickerModal.tsx:88` 逻辑 | — |

取图归一化统一收进 `lib/assetImageResolver.ts` 的 `resolveAssetMedia(asset, kind)`。
后端零改动 —— 五个接口的前端封装均已存在。

## 6. 关键流程

### 6.1 编辑 / 续写请求

```
用户选 vedit → 选源视频（素材选择器 or 上传）
  → 前端 ffprobe 不可用，时长校验在后端做
  → POST /playground/generate { mode: "vedit", input_media: [video], parameters: {} }
  → service 路由到 BytePlusVideoModel
  → 本地校验：时长 ∈ [4,30]、duration == -1、ratio == adaptive
      ├─ 不通过 → 400，返回可读文案，不消耗额度
      └─ 通过 → POST /contents/generations/tasks
                 { model, omni_reference_task_type: "edit",
                   content: [{type:"text"},{type:"video_url", role:"reference_video"}],
                   duration: -1, ratio: "adaptive" }
  → 轮询 tasks/{id} 直到 succeeded/failed
```

### 6.2 错误处理

| 情形 | 处理 |
|---|---|
| 模型未开通（404 `not activated`） | 映射为明确文案：「该模型未在 Ark 控制台开通」，附控制台链接 |
| `InvalidParameter.TaskTypeConstraint` | 说明是 auto 判定与参数冲突，提示显式选择 vedit/vext |
| `InvalidParameter.TaskTypeMismatch` | 说明 prompt 意图与所选模式不符 |
| 源视频时长越界 | 提交前拦截 |

### 6.3 成本展示

厂商未公开 token 换算公式，只给了典型场景（16:9 / 5 秒 / 无视频输入）折算表。
因此 UI 上**只做参考区间提示**，不做精确计算，文案需明说是估算。

## 7. 测试策略

TDD，先测后码。

| 层 | 用例 |
|---|---|
| `assetImageResolver` | legacy `full_body` / 新 `reference_sheet` / 仅 `image_url` / 全空 四种兜底路径 |
| pricing 加载 | 缺失条目报错、`promotions` 过期判定、原价与折扣分离 |
| catalog 校验 | 2.5 不含 4k、fast/mini 不含 1080p、默认值均为 720p |
| `BytePlusVideoModel` | vedit/vext 参数约束拦截（时长越界、ratio 非 adaptive、duration 非 -1） |
| `BytePlusImageModel` | 请求体构造、size 档位映射 |
| `AiVideoPage` | 渲染、模式切换、选素材 → 填入输入槽 → 触发生成 |
| Playground 回归 | context 重构后 5 个共享组件行为不变 |

阶段七完整验证：

```bash
pytest -q
cd frontend && npm run typecheck && npm run test:all && npm run build
python scripts/build_model_catalog.py
python scripts/validate_model_catalog.py
```

## 8. 风险

| 风险 | 缓解 |
|---|---|
| **账号未开通任何 Ark 模型**，端到端无法验证 | 需你在 Ark 控制台开通。代码与单测不受阻，实调验证挂起 |
| D5 的 context 重构碰 Playground 现有 5 个组件 | 先补 Playground 回归测试再重构 |
| 2.0 切 Ark 后出片质量与 MuleRouter 有差异 | MuleRouter 当前无凭证，无法 A/B，记为待验证 |
| D1 改默认分辨率影响现有项目 | 仅改默认值，不动已保存的项目设置 |
| `seedream-5-0` 与 `seedream-5-0-lite` 是两个模型，差异未知 | 本期只接前者，差异待查 |
| 限时折扣会过期 | 原价入库，折扣带 `ends_at`，过期自动不展示 |

## 9. 交付物

- `config/model_catalog/families/seedance.yaml`（修正 + 新增 mini + vedit/vext）
- `config/model_catalog/families/seedream.yaml`（新增）
- `config/model_catalog/pricing.yaml`（新增）
- `src/utils/model_catalog.py`（selection_group 扩展、pricing 合并、`allow_auto`）
- `scripts/validate_model_catalog.py`（pricing 校验）
- `src/models/byteplus.py`（vedit/vext、2.0 映射、`BytePlusImageModel`）
- 重新生成的 `generated/model_catalog.json` 与 `frontend/src/generated/modelCatalog.json`
- 前端：`aivideo/` 新模块、`AssetSourcePicker`、`assetImageResolver`、
  `useGenerationRunner`、`GenerationStoreProvider`、导航与 i18n
- 测试与验证记录
- `docs/api-reference/byteplus-ark-seedance-seedream.md`（已落盘）

**延期项**：外部 raw archive 与 Context Hub 的跨仓同步未做（模式 B）；
Ark 模型开通；MuleRouter/Ark 出片质量比对；`seedream-5-0-lite` 差异确认。

## 10. 实施分期

六个模块不应塞进一个实施计划。按依赖关系分四期，每期自身可验证、可独立合并：

| 期 | 内容 | 依赖 | 验证方式 |
|---|---|---|---|
| P1 | M1 catalog 数据修正 + M2 pricing.yaml 与构建管线 | 无 | 纯数据与构建脚本，`validate_model_catalog.py` + `pytest` 即可完全验证，**不需要模型开通** |
| P2 | M4 Seedance 2.0 切 Ark | P1 | 需要模型开通才能实调；未开通时只能验证请求体构造 |
| P3 | M3 vedit/vext（catalog + 运行时 + 参数校验） | P1、P2 | 提交前校验逻辑可完全单测；实调需开通 |
| P4 | M5 Seedream + M6 「AI 视频」页 | P1、P3 | 前端可完全本地验证；图像实调需开通 |

**P1 优先，且不受开通阻塞** —— 它同时修掉 2.1 那三个会导致请求失败的错误，
即便后面几期延后，P1 单独合并也有正收益。

M6 内部还可再拆：导航与页面骨架 → context 重构 → 素材选择器。
其中「context 重构」风险最高（碰 Playground 现有 5 个组件），应单独成一个可回滚的提交。
