# 「AI 视频」独立页计划复审 —— 结合 Gemini 迁移后的现状

- 日期：2026-09-08
- 复审对象：`docs/superpowers/specs/2026-09-02-ark-seedance-seedream-ai-video-design.md` §5 M6 / §10 P4
- 参照新事实：`docs/superpowers/specs/2026-09-08-dashscope-to-gemini-migration-design.md`
- 结论：**产品诉求成立，实施计划需改**。5 处前提已被推翻或低估，1 处顺序建议调整。

---

## 0. 现状快照（复审当日实测）

| 项 | 实测结果 |
|---|---|
| AI 视频页代码 | **零**。`frontend/src` 中无 `aivideo` / `ai-video` 文件或标识符；`GlobalTab` 仍为 4 项；`messages/*.json` 无 `nav.aivideo` |
| vedit / vext | **零**。全仓库仅 `config/model_catalog/families/seedance.yaml:35` 一句注释提及 |
| Seedream | **零**。无 `seedream.yaml`，无 `seedream_image.py` |
| Ark 开通状态 | `python scripts/check_ark_activation.py` → **9 个未开通，与 09-02 完全一致，6 天零变化**。两个 Seedream 均在未开通之列。2.5 本次探测连接被重置未测出，09-02 记录为已开通 |
| Gemini 迁移进度 | 4 步只做完第 1 步（LLM，`f1bd083`）。图像 / TTS / 拔除 DashScope 均未动 |
| 凭证 | `GEMINI_API_KEY`、`ARK_API_KEY`、`DASHSCOPE_API_KEY` 三者当前**都已配置** |

---

## 1. 需要调整的五点

### 调整 1 —— D5 工作量被低估约 3 倍（最重要）

09-02 spec 原文：「共享组件通过 React context 注入 store，而非复制 5 份组件」，交接单据此把风险描述为「会碰 Playground 现有 5 个组件」。

**实测：`usePlaygroundStore` 被 14 个文件引用，其中 12 个是运行时消费方；`components/modules/playground/` 共 4965 行。**

```
运行时消费（12，重构必须逐个改）：
  ModeSelector  ModelSelector  PromptInput  ParameterBar  MediaInput
  QueuePanel    ResultCard     ResultGallery  DetailPanel
  PromptHistoryDrawer  PromptTemplateModal  PlaygroundPage

仅 type-only import（2，重构不必动）：
  GalleryView（PlaygroundGeneration）  playgroundModels.ts（PlaygroundMode）
```

爆炸半径是原估「5 个组件」的 2.4 倍。最扎手的不是数量而是形态：`ResultGallery.tsx:105`
与 `PlaygroundPage.tsx:204` 直接调 `usePlaygroundStore.getState()` —— 模块级单例访问，
不在 React 树里，context 注入没法自动覆盖，两处都必须单独改写。另有 `ResultGallery` 与 `PromptTemplateModal` 用整店
解构 `usePlaygroundStore()` 而非选择器，改造时要留意重渲染范围。

> 订正：本文档初稿写「14 个文件消费」并称 `playgroundModels.ts` 也读 store，
> 后者不确——它只 `import type { PlaygroundMode }`，运行时不碰 store。

**建议**：不推翻 D5（context 注入仍是正确方向），但把它从「M6 的一个子步骤」提升为**独立的、可单独回滚的重构项**，且必须先补齐 14 个消费方的回归测试再动。若不愿承担这个成本，退路是让 AI 视频页复用同一个 store 但用 `slice` 命名空间隔离 `mode`/`prompt`/`inputMedia` —— 代价是 store 变胖，收益是零重构。

### 调整 2 —— D10 反转，v2v 保留，与 M6 的「不含 v2v」直接冲突

09-02 M6 明确写「**不含**图像模式与 `r2v / v2v`」。
09-08 D10 实测反转：Seedance 四个在售型号 `task_type` 均含 `VideoEditing`，`input_modalities` 含 `video`，是 `seedance.yaml` 漏标（该文件至今仍只声明 `t2v/i2v/r2v`）。v2v 保留并改路由到 Seedance。

于是产生一个两份 spec 都没回答的问题：**既有的 `v2v` mode，与 09-02 M3 设计的 `vedit` / `vext` 两个新 mode，是什么关系？** 三者在 Ark 侧其实是同一个 omni reference 任务，靠 `omni_reference_task_type`（`auto|reference|edit|extend`）分子类型。

**建议：不新增 vedit / vext 两个 mode**，改为在 v2v 之下暴露一个「任务子类型」选择器。理由三条：

1. 与 Ark 的实际契约同构 —— 它本来就是一个任务的四个子类型，拆成三个 mode 是把厂商模型翻译错了
2. 09-08 §8.2 已决定 v2v 相关的 7 个前端文件不动，新增 mode 会立刻破坏该决定
3. 省掉一轮 `SUPPORTED_SELECTION_GROUPS` 扩容与前端模式胶囊改造

注意 09-02 记录的约束仍然有效：只有 Seedance 2.5 支持显式指定该参数，2.0 系列只能靠 `auto`。所以子类型选择器要按所选模型动态禁用。

### 调整 3 —— D7 作废

09-02 D7：`dola-seedream-5-0-pro-260628` 接手被删的 `gpt-image-2` 的 `recommended: true`。
09-08 D11：**Gemini 图像做默认**（14 张参考图、4 张角色一致性，短剧刚需），Seedream 是第二供应商。

D7 已被 D11 覆盖，直接作废。连带影响：M5（Seedream 接入）不再是 AI 视频页的前置依赖，它被 09-08 第 2 步吸收了一半。

### 调整 4 —— 依赖链解绑：AI 视频页本身不需要那 9 个模型开通

交接单把顺序定为 `第0步开通 → B(P2实调) → C(P3) → D(P4 页面)`，把「页面」和「模型接入」捆成一个包，于是页面被开通状态卡了 6 天。

**实际上 M6 的三块内容里，只有一块有硬依赖：**

| M6 组成 | 依赖 | 现在能否做 |
|---|---|---|
| 四来源素材选择器 `AssetSourcePicker` | 无（5 个前端 API 封装均已存在，后端零改动） | ✅ 完全可做 |
| 独立页壳 + 导航 + 独立 store | catalog 稳定 | ⚠️ 见调整 5 |
| vedit/vext（或 v2v 子类型） | Seedance 2.5（**已开通**） | ✅ 可做可实调 |
| Seedream 图像 | 两个 Seedream 模型开通 | ❌ 仍被卡 |

结论：被卡的只有 Seedream 那一小块，且它已归属 09-08 第 2 步，不该继续挂在 AI 视频页名下。

### 调整 5 —— 顺序建议：AI 视频页应排在 Gemini 迁移第 4 步之后

这是本次复审最实际的一条建议。

Gemini 迁移第 4 步要做的事包括：**删 4 个 family（wan / qwen / pixverse + dashscope 通道）、加 2 个 family（gemini / seedream）、改系统默认、加退役映射、seedance 补 v2v**。

AI 视频页的核心是一个模型选择器 + 参数条。在 catalog 正处于「删 4 加 2 改默认」的动荡期新建一个消费 catalog 的顶层页面，等于让 `ModelSelector` / `ParameterBar` / `playgroundModels` 这套逻辑写两遍。

而且当前 `DASHSCOPE_API_KEY` 仍是应用硬性凭证（设置页标必填），三个 key 全配着。在这个中间态上叠新页面，调试时很难分清一个失败是新页面的 bug 还是迁移的半成品。

---

## 2. 建议的调整后顺序

```
现在可立刻开工（无阻塞、无冲突）
  └─ A. AssetSourcePicker 四来源素材选择器
        先接进现有 Playground（替换只认历史的 AssetPickerModal，433 行）
        AI 视频页将来直接复用。独立可交付，价值不等页面

主线（继续 Gemini 迁移，别插队）
  └─ 第 2 步 图像双供应商
        Gemini 图像可全做；Seedream 部分卡开通，可先写代码后验证
  └─ 第 3 步 Gemini TTS + 音色迁移
  └─ 第 4 步 拔除 DashScope + seedance 补 v2v + 退役映射
        ← catalog 在此定型

B. D5 context 注入重构 —— ✅ 已完成（272153f）。不消费 catalog，故无需等第 4 步

catalog 定型后
  └─ C. AI 视频页 M6（导航 + 独立 store + 页面，复用 A 的选择器与 B 的 provider）
  └─ D. v2v 任务子类型（edit / extend），用已开通的 Seedance 2.5 实调

始终阻塞（只能在 Ark 控制台点）
  └─ 两个 Seedream 开通 → 影响第 2 步的一半
  └─ Seedance 2.0 三个变体开通 → 影响 P2 实调，不影响页面
```

---

## 3. 仍然成立、不需要改的部分

- **D4 独立顶层入口，不复用 Playground 页** —— 用户明确选择，无新事实推翻
- **M6 的页面布局**（左栏模式胶囊 → 模型选择器 → 输入槽 → prompt → 参数条 → 生成按钮，右栏结果画廊）
- **四来源素材选择器的取图归一化设计**（`lib/assetImageResolver.ts` 的 `resolveAssetMedia`）
- **轮询与队列逻辑抽成共享 hook `useGenerationRunner(store)`**
- **§6.2 的四类错误映射**（模型未开通 / TaskTypeConstraint / TaskTypeMismatch / 时长越界）—— 「模型未开通」那条在当前 9 个未开通的现实下价值反而更高

---

## 4. 裁决结果（2026-09-08 用户已采纳）

| # | 问题 | 裁决 |
|---|---|---|
| 1 | vedit/vext 做独立 mode，还是 v2v 的任务子类型？ | **v2v 的任务子类型**。09-02 spec §5 M3 的「新增两个 mode」作废 |
| 2 | D5 context 重构（14 文件）真做，还是走 store 命名空间退路？ | **真做**，但独立成可回滚提交，且前置补齐 14 个消费方的回归测试 |
| 3 | AI 视频页排在 Gemini 迁移之后，还是插队现在做？ | **排在之后**。当前只交付 `AssetSourcePicker` |
| 4 | 何时开通 Ark 剩余 9 个模型？ | 用户执行，越早越好 |

---

## 5. 已交付：AssetSourcePicker（2026-09-08）

调整 4 里唯一无阻塞的那块已落地，走 TDD（先看红，再最小实现）。

**新增**

| 文件 | 说明 |
|---|---|
| `frontend/src/lib/assetImageResolver.ts` | `resolveAssetMedia(asset, kind)`，五种 kind（character/scene/prop/frame/generation）的取图归一化 |
| `frontend/src/__tests__/asset-image-resolver.test.ts` | 12 个用例，钉死每种容器形状与降级链 |
| `frontend/src/components/modules/playground/AssetSourcePicker.tsx` | 四来源选择器（素材库 / 系列 / 项目 / 生成历史），按 source 懒加载 |
| `frontend/src/components/modules/playground/__tests__/AssetSourcePicker.spec.tsx` | 10 个用例 |
| `frontend/src/components/modules/playground/__tests__/MediaInput.assetSource.spec.tsx` | 1 个集成用例：从 MediaInput 打开的是四来源选择器且落在素材库 |

**修改 / 删除**

- `MediaInput.tsx` 改用 `AssetSourcePicker`
- **删除** `AssetPickerModal.tsx`（433 行，替换后成死代码）及其 `playground.assetPicker.*` 文案
- `messages/{zh,en}.json` 新增 `playground.assetSourcePicker.*`

**验证**：`typecheck` 通过；`npm test` 205/205；`npm run test:ui` 57/57。

### 5.1 实现中发现的两处 spec 事实错误

09-02 spec §5 M6 的素材选择器表格有两处与代码不符，已按代码实现，spec 待订正：

1. **字段名错**。spec 写项目分镜帧取 `t2i_image_urls[active_t2i_index]`；代码里该字段叫 **`t2i_selected_index`**（见 `storyboard-r2v/shotNodeHelpers.ts:229`）。且它会失效——服务端把 `t2i_image_urls` 按 10 条 FIFO 截断，索引可能越界，所以解析器像 `ShotCard.tsx:254` 那样做了 clamp。
2. **多了一次 N+1 请求**。spec 写系列 Tab 走 `listSeries()` → 再对每个系列 `getSeriesAssets(id)`；实际 `listSeries()` 返回的每个 series 已内嵌 `characters/scenes/props`（`AssetLibraryPage.tsx:109` 就是这么用的）。已改为只发一次 `listSeries()`，钻取零额外请求。

### 5.2 与 D5 的关系

本组件**不依赖** `usePlaygroundStore`——它只收 `isOpen / onClose / onSelect / accept` 四个 prop。
所以调整 2 的 context 重构可以晚做，`AssetSourcePicker` 将来给 AI 视频页复用时无需改动。

---

## 6. 已交付：D5 前置回归测试（2026-09-08）

裁决 2 要求「context 重构前先补齐消费方回归测试」。**12 个运行时消费方已全部覆盖**，共 43 条用例。

**为什么是这些断言**：context 注入的失败模式是静默的——某个组件仍读旧的模块级单例，
照样渲染、照样接受点击，只是不再和它周围的页面达成一致。所以每条用例都双向钉住这条缝：
塞进 store 的状态必须到达组件，对组件的操作必须落回 store。

| 文件 | 覆盖组件 | 用例 |
|---|---|---|
| `__tests__/storeWiring.compose.spec.tsx` | ModeSelector / PromptInput / MediaInput / QueuePanel | 11 |
| `__tests__/storeWiring.results.spec.tsx` | ResultCard / PromptHistoryDrawer | 10 |
| `__tests__/storeWiring.catalog.spec.tsx` | ModelSelector / ParameterBar | 6 |
| `__tests__/storeWiring.surfaces.spec.tsx` | ResultGallery / DetailPanel / PromptTemplateModal / PlaygroundPage | 16 |

**变异验证**（这批是既有代码的表征测试，"通过"本身不证明有效），做了两次：

1. 把 `ModeSelector` 从 store 上摘下来改用局部 `useState`——正是 D5 重构会犯的错——
   恰好它那 2 条（读、写各一）变红，其余 9 条不动。
2. 删掉 `ResultGallery.tsx:105` 的 `usePlaygroundStore.getState().removeGeneration(...)`
   ——正是 context 注入漏掉非 React 调用点后会留下的样子——恰好删除那 1 条变红，其余 12 条不动。
3. 把 `PlaygroundPage.tsx:204` 队列泵的 `getState()` 换成写死的空状态——恰好
   「泵出队列请求」那 1 条变红，其余 15 条不动。

三次改动均已还原，`git diff` 干净。

> 订正：本文档一度写 `getState()`「全仓库仅此一处」，不确。生产代码有**两处**，
> 第二处是 `PlaygroundPage` 的队列泵——首次排查时用的 grep 只匹配了选择器形态，漏了它。
> 该处原本也无测试覆盖，已补三条（i2i 自动判定、泵出并清空队列、并发满时按住不发）。

**目录变动免疫**：`ModelSelector` / `ParameterBar` 那 6 条不硬编码任何模型 id，
期望值在运行时由 `getModelsForMode()` 现算。Gemini 迁移第 4 步要删 4 个家族、加 2 个，
硬编码 id 的测试会在那时集体变红并被当成噪音改掉，正好在最需要它们的时候失效。

**验证**：playground 相关 UI 用例 100 条全过（本轮前 57）；`npm test` 205/205；`typecheck` 干净。
（`npm run test:ui` 全量此刻为 105，多出的 5 条是并行会话新增的 cast 测试。）

### 6.1 重构时最需要当心的三处

覆盖过程中确认的、`usePlaygroundStore` 的三种不同接入形态——context 注入要分别处理：

| 形态 | 出现处 | 为什么危险 |
|---|---|---|
| `getState()` 模块级单例调用 | `ResultGallery.tsx:105`（删除处理）、`PlaygroundPage.tsx:204`（队列泵） | **不在 React 树里，provider 无法覆盖**，两处都必须手工改写 |
| 整店解构 `usePlaygroundStore()` | `ResultGallery.tsx:43`、`PromptTemplateModal.tsx:58` | 订阅整个 store，任何字段变化都重渲染；换 context 时若照搬会放大重渲染范围 |
| 选择器 `usePlaygroundStore((s) => ...)` | 其余 10 处 | 最容易改，逐个换 hook 即可 |

另有一处不是 store 形态、但重构时容易破坏的行为：`DetailPanel.tsx:87` 故意
**优先用 store 里的副本而非传进来的 prop**（`history.find(...) ?? generationProp`），
为的是别处改了 `saved_to_library` 后详情页能同步。已有用例钉住。

## 7. 已交付：D5 store 工厂 + context 注入（2026-09-08）

裁决 2 的重构本体。`272153f`，单个可回滚提交。

**做法**：store 由模块级单例改为工厂 `createPlaygroundStore()`；组件跟哪个实例说话
由上方的 `PlaygroundStoreProvider` 决定，而非由 import 决定。保留默认实例
`playgroundStore`，`usePlaygroundStoreApi()` 在无 provider 时回退到它——创作台因此
一行未改、行为照旧；AI 视频页只需把子树包进 provider。

**两处手工改写**（provider 覆盖不到的非 React 调用点）：

| 位置 | 改法 |
|---|---|
| `ResultGallery` 删除处理 | 从已有的整店解构里取 `removeGeneration` |
| `PlaygroundPage` 队列泵 | 改用 `usePlaygroundStoreApi().getState()` 取快照。这里要的是快照不是订阅——为读队列而订阅队列会让页面每次队列变动都重渲染，反过来冲击它自己驱动的泵 |

**关键验证点**：其余 43 条 storeWiring 用例全都跑在无 provider 的回退路径上，
它们证明创作台没坏，但对隔离一无所知。因此另加 `storeWiring.isolation.spec.tsx` 5 条，
正面断言两个子树两个 store、互相看不见。变异验证：让 `usePlaygroundStoreApi` 无视
context 永远返回默认实例（即"重构其实没生效"），恰好其中 3 条变红，不依赖 provider
的 2 条保持绿。

**留给下一步的两件小事**（有意不塞进这个提交，以免"可回滚"变成空话）：

- `ResultGallery` 与 `PromptTemplateModal` 仍用整店解构，改成选择器可收窄重渲染范围
- store 里 localStorage 支撑的两项（featured、并发数）目前所有实例共用同一组 key。
  创作台与 AI 视频页要不要共享"精选"标记和并发上限，是产品决策，做 AI 视频页时再定

**验证**：`typecheck` 干净；`test:ui` 110/110；`test` 205/205。

---

## 8. 已交付：独立「AI 视频」页（2026-09-08）

M6 本体，也是这条线最初的需求。`22c0f7e`（i18n）、`9365f1e`（抽 hook）、`4834089`（页面）。

**排序订正**：复审初稿把 C 排在"catalog 定型后"，理由是"新页面要重写一遍模型选择器
和参数条"。D5 做完后这条理由不成立了——页面复用创作台的 6 个组件，靠 provider 接到
自己的 store，不产生第二套目录逻辑。实际唯一的耦合是 `messages/*.json`，与并行会话
约定后单独提交解决。

| 组成 | 落法 |
|---|---|
| 自有 store | 每次挂载建一个 `createPlaygroundStore()` 实例，初始模态 t2v |
| 模态 | 只有 t2v / i2v / v2v。无图像模态；无 r2v（参考图驱动的镜头属于系列分镜，不属于一次性生成）；按裁决 1，编辑/续写是 v2v 之下的子类型而非独立模态 |
| 组件 | ModelSelector / MediaInput / PromptInput / ParameterBar / ResultGallery / QueuePanel 全部复用 |
| 编排 | `useGenerationRunner()`，从 PlaygroundPage 抽出（M6 要求）。PlaygroundPage 347 → 169 行 |
| 素材选择器 | 复用第 5 节的 `AssetSourcePicker`，零改动 |

**顺带修掉的两个真问题**：

1. **空模态**。`ModelSelector` 的自动改选 effect 条件是 `availableModels.length > 0`，
   为 0 时整个不执行，上一个模态的 `modelId` 留下来被提交。实测过：删掉四家族后 v2v
   一度归零，t2i 采纳 `gemini-3-pro-image`，切到 v2v 后 modelId 还是它。新页面改为明说
   「该模式暂无可用模型」并禁用生成。**创作台仍有此行为，未改**（不在本次范围）
2. **导航切片**。`GlobalSidebar` 原用 `GLOBAL_NAV_ITEMS.slice(0, 3)` 切主导航，是写死
   的个数。加第 4 项而不动它，新入口会从桌面侧栏消失、却仍出现在移动端 `BottomTabBar`
   ——静默，且只错在一个断点上。改成按 id 排除 settings，并补 4 条用例钉住

**变异验证**：把页面的 `storeRef` 换成共享的 `playgroundStore`，恰好那两条隔离用例
（提示词不外泄、模态不外泄）变红。

**页面 spec 用桩目录而非真目录**：DashScope 下线正在重写目录，一条因为家族被退役而
红掉的页面用例只会被删掉而不是修好。桩目录也是让 v2v 真的为空、从而能测到空状态的
唯一办法。

**验证**：typecheck 干净；`test:ui` **123/123**。
（`npm test` 此刻 185/205，20 条失败全在 `model-catalog` / `video-params` /
`settings-store` / `provider-credentials`，是并行会话第 4 步的目录连带，已报给对方。）

### 8.1 已交付：v2v 任务子类型（D）

`12c4c2f`（适配器）、`99ad903`（选择器）、`a076674`（透传测试），共 19 个后端用例。

按裁决 1 参数化而非新增 mode。并行会话独立印证了这个选择：`SUPPORTED_SELECTION_GROUPS`
里根本没有 v2v 槽位，新增 mode 还得先扩那个白名单，成本比参数化高得多。

**顺带修的第三个真问题**：目录里有 `seedance-2.5-v2v`，而 `ARK_MODEL_IDS` 里没有对应
条目，`resolve_model_id` 返回 None、`generate()` 抛 `Unrecognized Seedance model id`
——这个模态在 UI 里看得见、一提交就失败。是并行会话补目录时漏了适配器映射表，
它已确认。

约束落法：edit 要求 ratio=adaptive、duration=-1、源视频 4–30 秒；extend 只要求
adaptive。**仅对 2.5 下发**该参数；`auto` 通过不发送表达。源视频时长用 ffprobe 读，
**读不到就放行**——OSS 上的要下载才能探测，Ark 本来就会同步校验，在这里猜只会拦住
合法请求。UI 选「编辑」时自动锁定画幅与时长，不锁的话用户能组装出必然被拒的请求。

**一处未经验证的推断**：content 里 video 项的形状
`{"type":"video_url","video_url":{"url":...},"role":"reference_video"}` 是照
`image_url` 加 spec §6.1 推出来的，厂商文档快照只写了 `content.role = reference_video`，
没给确切 JSON 结构。代码注释已标注，**只有真实调用能确认**。

### 8.2 还剩什么

- **实调验证**（未做，需用户批准）：一次 5 秒 720p 编辑约 0.7–1.5 USD，edit + extend
  各验一次约 1.5–3 USD。要确认的是上面那个 video 项形状，以及
  `InvalidParameter.TaskTypeConstraint` / `TaskTypeMismatch` 两个异步错误码的实际文案
- 创作台的空模态行为（§8 第 1 条），要不要一并修，是产品决策

---

## 9. 并行作业提示（2026-09-08）

本次复审执行期间，另一个会话（`lengjinglumenxstudio-aa`）在同一仓库并行推进 Gemini 迁移：

- `427925a feat(image): 接入 Gemini 图像生成` —— 迁移第 2 步的 Gemini 部分已完成并提交
  （走 `generateContent` 而非设计文档原写的 `/v1beta/interactions`，spec §2.1 已补修订记录）
- 根目录未跟踪的 `gen_voice_samples.py`（15:20 写入）—— 第 3 步的第一个动作，30 个音色试听样本

因此本轮**没有**去做迁移第 3 步，改为推进裁决 2 的前置项。后续接手前请先 `git log` 确认
第 3 / 4 步的进度，避免重复劳动。
