# 后续工作交接单

日期：2026-09-02（第二次会话末更新）
当前分支：`main`（P0+P1 的 18 个提交**已推送**，见下方任务 A）

**本次会话增量**：任务 A 已完成；零散技术债 1/2/3/4 已完成；后端 506 测试全绿、
前端 46 UI + 193 单元测试全绿。B/C/D 仍被第 0 步阻塞。

## 已完成（本次会话）

P0 + P1 已实现、评审、合入 `main`：

- **P0** —— MuleRouter 网关彻底移除（630 行模块、后端配置项、`/config/mulerun-login` 端点、
  前端凭证界面、`.env.example` 说明、独占的 `gpt-image` family）。平台改为厂商官方直连。
- **P1** —— 修正 Seedance catalog 三处会产生失败请求的错误（4K 挂错代、2.0-fast 虚报 1080p、
  默认分辨率全为 1080p），新增 2.0-mini 变体，新增 `config/model_catalog/pricing.yaml`
  与其加载、合并、校验管线。

依据文档（均已提交）：

| 文件 | 作用 |
|---|---|
| `docs/superpowers/specs/2026-09-02-ark-seedance-seedream-ai-video-design.md` | **总设计（权威）**，含 D1–D7 决策与 §10 分期 |
| `docs/api-reference/byteplus-ark-seedance-seedream.md` | 厂商事实来源：时长/分辨率/比例/编辑续写契约/计价 |
| `docs/superpowers/plans/2026-09-02-p0-p1-mulerouter-removal-and-catalog-fix.md` | 已执行完的 P0+P1 计划（历史参考） |

---

## 第 0 步：Ark 模型开通（**阻塞 P2–P4，最优先**）

截至 2026-09-02，账号 `3004342898`（BytePlus 国际站 `ap-southeast-1`）：

| 模型 | 状态 |
|---|---|
| `dreamina-seedance-2-5-260628` | ✅ **已开通** |
| `dreamina-seedance-2-0-260128` | ❌ 未开通 |
| `dreamina-seedance-2-0-fast-260128` | ❌ 未开通 |
| `dreamina-seedance-2-0-mini-260615` | ❌ 未开通 |
| `dola-seedream-5-0-pro-260628` | ❌ 未开通（P4 需要） |
| `seedream-5-0-260128` | ❌ 未开通（P4 需要） |

2.5 已通证明账号与区域都对，开通是**逐个模型**执行的。到 Ark 控制台把上表其余项开通。

**本次会话已复检，状态与上表一致，无变化**（脚本另外报出 `seedance-1-x` 与 `seedream-4-5`
也未开通，共 9 项）。

随时复检：

```bash
python scripts/check_ark_activation.py
```

零成本（用非法参数探测，不建任务、不计费）。

---

## 任务 A：推送 main 到 GitHub —— ✅ 已完成

18 个提交（17 个 P0+P1 的，加上交接单自身那次）已走 prismreel-git-publish 流程推送，
`origin/main` 与本地一致。扫描六项全过，唯一命中是下面注明的那个已知误报。

**下次推送仍需注意**：扫描第 2 项（`alibaba-inc.com`）会命中 `.claude/commands/prismreel-git-publish.md`
与 `.codex/workflows/prismreel-git-publish.md` —— 那是扫描命令自身的文本，**误报**。
lockfile 里的真实命中已在 `cfef80d` 清理完毕。现在交接单自身也会命中同一项（它描述了这件事），
同样是误报。

另外扫描第 4 项会列出 `frontend/src/__tests__/provider-credentials.test.ts` —— 只是文件名含
`credential`，内容里的 `sk-live-x` 是测试假值。

---

## 任务 B（P2）：Seedance 2.0 切 Ark 的实调验证

**依赖**：第 0 步开通 2.0 / 2.0-fast / 2.0-mini。

代码已经全部切到 Ark（P0 完成），但**从未发出过一次真实的 2.0 系列请求**。
2.5 现已开通，可先用它验证整条链路，再验 2.0 三个变体。

要验证的点：

1. 三个变体各发一次最小 t2v 任务，确认 `ARK_MODEL_IDS` 映射的 wire id 被 Ark 接受
2. 确认 fast / mini **只接受 480p/720p**，传 1080p 会被拒（catalog 已收窄，验证与厂商一致）
3. 确认 2.0 标准版接受 `4k`
4. 确认 `duration: -1`（自动时长）可用
5. 记录实际计费，与 `pricing.yaml` 的 `reference_per_second` 对照

> 新窗口启动指令：
>
> ```
> 读 docs/superpowers/specs/2026-09-02-ark-seedance-seedream-ai-video-design.md 的 §10 P2，
> 以及 docs/api-reference/byteplus-ark-seedance-seedream.md 的 §2。
> P0/P1 已合入 main：Seedance 全族已切 BytePlus Ark，catalog 参数已按厂商文档修正。
> 现在做 P2：对 Seedance 2.0 / 2.0-fast / 2.0-mini 做真实调用验证。
> 先跑 python scripts/check_ark_activation.py 确认开通状态。
> 每个变体发一次最小 t2v 任务，验证 wire id、分辨率边界（fast/mini 仅 480p/720p）、
> duration=-1，并把实际计费与 config/model_catalog/pricing.yaml 的 reference_per_second 对照。
> 这会产生真实费用，动手前先把预计花费告诉我。
> ```

⚠️ **这一步会真实计费**（2.0 标准版 720p 约 0.15 USD/秒）。

---

## 任务 C（P3）：编辑（vedit）与续写（vext）能力

**依赖**：任务 B 完成。

spec §5 M3 有完整设计。要点回顾：

- 编辑/续写**不是独立模型**，是同一个 omni reference 任务的子类型，
  靠 `omni_reference_task_type` = `auto | reference | edit | extend` 区分
- **只有 Seedance 2.5 支持显式指定**该参数；2.0 系列只能靠 `auto` 自动判定
- `edit` 硬约束：至少一个 `reference_video`、源视频 **4–30 秒**、
  `ratio` 必须 `adaptive`、`duration` 必须 `-1`
- `extend` 硬约束：至少一个 `reference_video`、`ratio` 必须 `adaptive`

工作量：`SUPPORTED_SELECTION_GROUPS` 扩容、catalog 加两个 mode、
`byteplus.py` 加参数与**提交前本地校验**（用 ffprobe 读源视频时长）、前端加模式与视频输入槽。

> 新窗口启动指令：
>
> ```
> 读 docs/superpowers/specs/2026-09-02-ark-seedance-seedream-ai-video-design.md 的 §5 M3 与 §6.1，
> 以及 docs/api-reference/byteplus-ark-seedance-seedream.md 的 §2.4（编辑与续写契约）。
> P0/P1 已合入 main。现在为 P3 出实施计划：给 Seedance 2.5 接入 vedit / vext 两个 mode。
> 用 superpowers:writing-plans 出计划，先不要写代码。
> ```

---

## 任务 D（P4）：Seedream 5.0 接入 + 独立「AI 视频」页

**依赖**：任务 C 完成；第 0 步开通两个 Seedream 模型。

这是**你最初提的那个需求**。spec §5 M5 与 M6 有完整设计，含已批准的决策：

- **D4** —— 独立顶层入口，不复用 Playground 页（你选的）
- **D5** —— 共享组件通过 React context 注入 store，而非复制 5 份组件
  （**本期最大风险面**：会碰 Playground 现有 5 个组件，需先补回归测试）
- **D7** —— `dola-seedream-5-0-pro-260628` 接手被删的 `gpt-image-2` 的 `recommended` 位置

素材选择器要接四个来源：全局素材库、系列资产、项目分镜帧、生成历史。
后端零改动 —— 五个接口的前端封装均已存在。

**待核实**：`/api/v3/models` 返回 `seedream-5-0-260128`，而价格文档写
`seedream-5-0-lite-260128`。探测显示两个 id **都真实存在**，是两个不同模型，差异未知。

> 新窗口启动指令：
>
> ```
> 读 docs/superpowers/specs/2026-09-02-ark-seedance-seedream-ai-video-design.md 的 §5 M5 与 M6。
> P0–P3 已完成。现在为 P4 出实施计划：接入 Seedream 5.0，并新建独立的「AI 视频」顶层页面
> （模式/模型选择器 + 首帧槽 + prompt + 参数条 + 四来源素材选择器）。
> 用 superpowers:writing-plans 出计划。
> 注意 D5：共享组件要改成 context 注入，会碰 Playground 现有 5 个组件，
> 计划里必须把「先补 Playground 回归测试」作为前置步骤，并让 context 重构单独成一个可回滚的提交。
> ```

---

## 零散技术债

### 已完成

| # | 内容 | 结果 |
|---|---|---|
| 1 | `pytest` 未声明为依赖 | ✅ `ac2155b`。新建 `requirements-dev.txt`。比原描述多一层：测试用 `TestClient`，它需要 `httpx`，而 fastapi 核心**不依赖** httpx（现在能跑只因为 `openai` 传递装上了），所以 httpx 也一并明写。AGENTS.md 原本完全没有测试章节，已补 |
| 2 | 6 个既有失败测试 | ✅ 后端 **506 passed / 0 failed**（原 500/6）。三个独立根因，见下方「根因备忘」 |
| 3 | 46 个前端 `test:ui` 失败 | ✅ `b5afdb0`。**46/46 通过**。不止 intl 一个原因，三层套娃，见下方「根因备忘」 |
| 4 | `quality` 参数残留死代码 | ✅ 上一会话的 `d74f76b` 已清掉，交接单写这条时已过时。复查 `ParameterBar.tsx` / `playgroundModels.ts` 均无残留 |

### 待办

| # | 内容 | 说明 |
|---|---|---|
| 5 | `seedance.yaml` 两个空 transport map | **建议不做，等你拍板**。全部 7 个 family 里只有 seedance 这两个键为空，其余都真用到。当前 `_require_mapping` 强制三个键必填，`{}` 恰好表达了"该 family 无特殊音频/参考视频传输模式"，是自文档化的；放宽后「故意留空」和「忘了写」就无法区分了。零风险的替代：给这两行加注释说明留空是有意的 |
| 6 | `CHANGELOG.md` 自 1.2.1（2026-06-09）停更 | 未动，要不要重启由你定 |
| 7 | `merged_project_payload` 覆盖面 | ✅ **已完成**。61 个返回完整 Script 的 project 端点现已 100% 走合并（复核脚本对 raw 端点的计数为 0），42 条路由摘掉 `response_model=Script`。报告：`docs/superpowers/plans/2026-09-02-merged-project-payload-audit.md`。提交 `0f683d7` / `df46632` / `6a263de` |

### 根因备忘（债 2 / 债 3）

后端 6 个：

- 2 个 catalog —— `fc71a24` 把整个 wan2.6 族标为 deprecated 并清空 `visible_in`、
  `ebc5780` 把默认 r2v 改成 `happyhorse-1.0-r2v`（消除 `ui.order=80` 并列时的任意 tie-break）。
  两次都是有意的生产变更，但 `ebc5780` 只同步了**前端**测试，从没碰过 `tests/`。
  修的是测试，不是生产。顺带把 wan2.6 的逐 id 断言改成一条规则 —— 逐 id 写法让另外两处
  不匹配藏在了第一条失败断言后面。
- 3 个 dashscope —— 断言写死了 POSIX 分隔符 `endswith("output/video/ref.mp4")`，
  在 Windows 上**永远不可能通过**。生产无 bug，只是断言不可移植。
- 1 个分镜合并 —— **这个是真的生产 bug**（`0f683d7`）。`analyze_to_storyboard` 返回未合并的
  episode Script，而两个前端调用方都把它直接喂给浅合并的 `updateProject`，于是把已合并的
  cast 抹成空。`04a190b` 加这条测试时用同样的方式修了 `bind_voice`，却漏了这个端点，
  所以它**从落地那天起就是红的**。

前端 46 个，三层，每层都被上一层挡住：

1. 两个 spec 都没包 `NextIntlClientProvider`，首个 `useTranslations` 直接抛错，整文件全灭。
   已加 `frontend/src/test-utils/intl.tsx`，复刻 `Providers.tsx`，喂**真的** `messages/zh.json`
   （spec 断言的中文文案就是 i18n 时原样搬进去的，用真 messages 才能让改 key 立刻暴露）。
2. `SeriesDetailPage` 的 lucide-react mock 逐个列举图标，漏了 `SeriesSidebar` 用的 `Palette`，
   React 渲染 undefined 抛错 → 页面全空 → 25 个测试全报"找不到文本"这种误导性错误。
   改成 Proxy 兜住任意图标名。
3. `createEpisodeForSeries` 多了第 4 个参数（新集数从系列继承的 workflow mode），断言还写着 3 个。

---

## 建议顺序

```
第 0 步（开通剩余模型）──→ 任务 B（P2 实调）──→ 任务 C（P3）──→ 任务 D（P4）
                          ↑
                    唯一的阻塞点，只能你在 Ark 控制台点
```

任务 A ✅ 已完成。技术债 1–4 ✅ 已完成。**现在整条链路只卡在第 0 步。**

在你开通之前，能推进的只剩债 5 / 6 / 7，其中 5 和 6 都需要你先拍板（见上表），
7 是新发现的、可以独立开工的一项。
