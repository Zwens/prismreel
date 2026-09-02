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
5. **彻底移除 MuleRouter 网关**，平台后续一律采用厂商官方直连。

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

### 2.3 MuleRouter 现状

两个 family 挂在 MuleRouter：`seedance` 与 `gpt-image`。代码体量：

| 项 | 量 |
|---|---|
| `src/models/mulerouter.py` | 630 行 |
| 后端引用 | `playground/service.py` 16、`pipeline.py` 8、`api.py` 3，另 factory / image / endpoints / provider_registry / model_catalog 各 1–4 |
| 前端 | `SettingsPage.tsx` 9、`EnvConfigDialog.tsx` 8、`modelCatalog.ts` 1，加 zh/en 两份 i18n |
| 测试 | `test_mulerouter_seedance_body.py`（79 行）、`test_seedance_variant_routing.py` |
| 文档 | `docs/api-reference/seedance-mulerouter.md` |

`MULEROUTER_API_KEY` 为空，因此挂在其上的模型**当前已全部不可用**——移除属于删死代码，不是功能回退。
`~/.prismreel` 下无任何已保存项目引用 seedance 或 gpt-image，**不需要数据迁移**。

`gpt-image-2` 是 MuleRouter 独占（`src/models/mulerouter.py:86`
`MULEROUTER_ONLY_MODELS = ("openai/gpt-image-2",)`，走 `/vendors/openai/v1/gpt-image-2/*`），
且在 catalog 中 `recommended: true`、三个设置页可见。移除后无落脚点，处理方式见 D7。

### 2.4 阻塞项（需要账号侧操作）

用 `.env` 中的 `ARK_API_KEY`（末四位 `91d2`，与运行中后端 `/config/env` 一致）探测，
账号 `3004342898` **在 Ark 上没有开通任何模型**。

证据链：

| 测试 | 结果 | 结论 |
|---|---|---|
| 同一把 key 打 `ark.cn-beijing.volces.com` | 401 `The API key doesn't exist` | key 属国际站，`ARK_REGION=intl` 配置正确 |
| 打 `ark.ap-southeast.bytepluses.com` | 404 `has not activated the model` | 鉴权通过，卡在开通 |
| 文本模型 `seed-2-0-pro-260328` | 同样 `not activated` | 非视频模型特有，是账号级 |
| `GET /endpoints` | 返回空 | 账号下未创建任何 endpoint |
| 对照组 `seedream-9-9-nonexistent` | `does not exist` | 探测能区分「不存在」与「未开通」 |

**key 本身有效**（无效会像 cn-beijing 那样返回 401，且它能成功列出 55 个模型）。
Ark 上「API Key 权限范围」与「模型开通状态」是两件独立的事：key 的全资源权限意味着它能访问
账号**已开通**的全部资源，但不能代替开通动作。`/api/v3/models` 是公共目录，不是账号权限清单。

连带后果：提交 `d3084d6` 把 Seedance 2.5 切到 Ark 之后，**2.5 目前是坏的**；
加上 MuleRouter 无凭证，**Seedance 全家当前都不可用**。
因此「2.0 切 Ark」不是迁移，而是让它恢复可用的唯一路径。

开通需在 Ark 控制台的「开通管理」操作（需登录），不阻塞编码，**阻塞阶段七的端到端验证**。

## 3. 范围

### 3.1 做

- **移除 MuleRouter 全部代码、配置、UI、测试与文档**
- 移除 `gpt-image` family，`recommended` 位置交给 Seedream 5.0 pro
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
| D6 | 彻底移除 MuleRouter，平台一律厂商官方直连 | 少一层网关、少一套凭证、少一处故障点；且其当前无凭证、无项目引用，移除成本最低的时机就是现在 |
| D7 | 删除 `gpt-image` family，不改走 OpenAI 直连 | 它已随 MuleRouter 一同不可用且无项目引用；本期正在接的 `dola-seedream-5-0-pro` 同为 t2i+i2i 且是 Ark 官方直连，直接顶替其 `recommended` 位置，避免为一个模型新引入 OpenAI 凭证与运行时 |

## 5. 分模块设计

### M0 — 移除 MuleRouter

删除：

- `src/models/mulerouter.py`（630 行）
- `tests/test_mulerouter_seedance_body.py`
- `docs/api-reference/seedance-mulerouter.md`
- `config/model_catalog/families/gpt-image.yaml`（整个 family，见 D7）

改造：

| 文件 | 动作 |
|---|---|
| `src/utils/model_catalog.py:9` | `SUPPORTED_PROVIDER_BACKENDS` 去掉 `"mulerouter"` |
| `src/models/factory.py` | 去掉 mulerouter 分支 |
| `src/models/image.py:886` | 去掉 `gpt-image` 分支 |
| `src/utils/endpoints.py`、`src/utils/provider_registry.py` | 去掉 mulerouter 条目 |
| `src/apps/playground/service.py`（16 处） | Seedance 一律走 `BytePlusVideoModel`，删除网关分支 |
| `src/apps/comic_gen/pipeline.py`（8 处） | 同上；`use_byteplus` 判断退化为常量 |
| `src/apps/comic_gen/api.py`（3 处） | 配置清单去掉 `MULEROUTER_API_KEY` |
| `families/seedance.yaml` | `provider`/`supported_backends`/`default_backend`/`credential_sources`/`transport` 只留 byteplus；删除 `SEEDANCE_PROVIDER_MODE` 回切开关 |
| `tests/test_seedance_variant_routing.py` | 改写为只断言 Ark 路由 |
| 前端 `SettingsPage.tsx`(9)、`EnvConfigDialog.tsx`(8)、`modelCatalog.ts`(1) | 移除 MuleRouter 凭证项与相关分支 |
| `frontend/messages/{zh,en}.json` | 删除对应文案键 |
| `frontend/src/__tests__/provider-credentials.test.ts` | 更新期望 |
| `README.md`、`README_EN.md` | 更新 provider 说明 |

`catalog.meta.yaml` 的默认模型当前为 `wan2.7-image-pro`，不涉及被删模型，**无需调整默认值**。

由于无凭证、无项目引用，此模块**不需要数据迁移，也不存在运行时行为回退**。

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
vs `dreamina-seedance-2-0-260128`），`ARK_MODEL_IDS` 需补全映射，
catalog 中的 model id 一并改为 Ark 侧写法。

按 D6，MuleRouter 整体移除，因此**不保留 `SEEDANCE_PROVIDER_MODE` 回切开关**——
family 只剩 `byteplus` 一个 backend，多留一个只有单一取值的开关是无谓的分支。

**风险**：两个网关的出片质量与参数语义未必一致。但 MuleRouter 当前无凭证，
本来就无法做 A/B，且它即将被删除，故不设比对任务；以 Ark 的实测结果为准。

### M5 — Seedream family

新增 `config/model_catalog/families/seedream.yaml`，provider `byteplus`：

| 模型 | capabilities | size | 默认 |
|---|---|---|---|
| `dola-seedream-5-0-pro-260628` | t2i, i2i | 1K / 1.5K / 2K（编辑场景另有 `auto`） | 2K |
| `seedream-5-0-260128` | t2i, i2i | 同上 | 2K |

按 D7，`dola-seedream-5-0-pro-260628` 接手被删除的 `gpt-image-2` 的
`recommended: true` 与 `visible_in: [project_settings, series_settings, global_settings]`。

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
| M0 删除验收 | 全仓 `grep -ri mulerouter` 归零；`SUPPORTED_PROVIDER_BACKENDS` 不再含 `mulerouter`；`provider-credentials.test.ts` 不再期望该凭证；catalog 中不存在 `gpt-image` family |
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
| 2.0 切 Ark 后出片质量与 MuleRouter 有差异 | MuleRouter 无凭证且即将删除，不设比对，以 Ark 实测为准 |
| M0 删除面广（12 个文件 + 前端设置 UI + i18n），易漏 | 删除后以 `grep -ri mulerouter` 全仓归零为验收条件，并跑完整测试套件 |
| 删除 `gpt-image` 后平台少一个图像模型 | 同期接入的两个 Seedream 5.0 填补；且 `catalog.meta.yaml` 默认值本就是 `wan2.7-image-pro`，不受影响 |
| D1 改默认分辨率影响现有项目 | 仅改默认值，不动已保存的项目设置 |
| `seedream-5-0` 与 `seedream-5-0-lite` 是两个模型，差异未知 | 本期只接前者，差异待查 |
| 限时折扣会过期 | 原价入库，折扣带 `ends_at`，过期自动不展示 |

## 9. 交付物

- **删除**：`src/models/mulerouter.py`、`tests/test_mulerouter_seedance_body.py`、
  `docs/api-reference/seedance-mulerouter.md`、`config/model_catalog/families/gpt-image.yaml`
- MuleRouter 引用清理：后端 8 个文件、前端 3 个组件 + 2 份 i18n + 1 个测试、2 份 README
- `config/model_catalog/families/seedance.yaml`（修正 + 新增 mini + vedit/vext + 只留 byteplus backend）
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
| P0 | M0 移除 MuleRouter + 删除 `gpt-image` family | 无 | 纯删除。验收：全仓 `grep -ri mulerouter` 归零、完整测试套件通过、`validate_model_catalog.py` 通过。**不需要模型开通** |
| P1 | M1 catalog 数据修正 + M2 pricing.yaml 与构建管线 | P0 | 纯数据与构建脚本，`validate_model_catalog.py` + `pytest` 即可完全验证，**不需要模型开通** |
| P2 | M4 Seedance 2.0 切 Ark | P0、P1 | 需要模型开通才能实调；未开通时只能验证请求体构造 |
| P3 | M3 vedit/vext（catalog + 运行时 + 参数校验） | P1、P2 | 提交前校验逻辑可完全单测；实调需开通 |
| P4 | M5 Seedream + M6 「AI 视频」页 | P1、P3 | 前端可完全本地验证；图像实调需开通 |

**P0 与 P1 都不受开通阻塞，应先做完。** P0 删掉一整层死网关，让后续所有改动
只面对 Ark 一条路径；P1 顺带修掉 2.1 那三个会导致请求失败的错误。
即便 P2 之后全部延后，P0 + P1 单独合并也有正收益。

M6 内部还可再拆：导航与页面骨架 → context 重构 → 素材选择器。
其中「context 重构」风险最高（碰 Playground 现有 5 个组件），应单独成一个可回滚的提交。
