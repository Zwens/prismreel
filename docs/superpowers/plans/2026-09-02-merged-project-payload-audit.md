# `merged_project_payload` 覆盖面排查

日期：2026-09-02　　对应交接单「零散技术债 #7」

## 判据

`merged_project_payload` 的 docstring 定的规则是：

> Every endpoint whose response the frontend feeds back into its project store
> must go through this -- the store shallow-merges the response, so handing back
> a raw episode Script blanks the cast list for any episode whose assets live
> series-side.

前端 `projectStore.updateProject` 是 `{ ...p, ...data }` 浅合并。所以只要端点返回
**完整 episode Script**，而该 Script 的 `characters/scenes/props` 因资产存在系列侧而为空，
喂回 store 就会把已合并的列表抹成空。症状：cast chips 消失，随后的 R2V 对每个 reference tag
报「尚未生成图片」。

## 排查方法

1. 前端：正则提取全部 `updateProject(id, X)` 调用（81 处，其中 52 处传变量），
   回溯变量来源到 `api.<method>`，再由 `src/lib/api.ts` 映射到后端路由。
2. 后端：遍历 `api.py` 里全部 `/projects/{script_id}` 路由，判断函数体是否
   `return signed_response(<script 变量>)` 且未经 `merged_project_payload`。

方法 1 会漏（`generateAsset` / `toggleAssetLock` 等经由 `assetGenerationTask.ts`、
`.then()` 链等路径），所以最终以方法 2 为准 —— **任何返回完整 Script 的 project 端点**
都在风险面内，无论今天前端有没有把它喂回 store。

## 结果：全部已处理（61 个端点）

`/projects/{script_id}` 下所有返回完整 episode Script 的端点，现已 **100%** 经过
`merged_project_payload`。复核脚本对「仍返回 raw script 的 project 端点」的计数为 **0**。

分三次提交完成：

| 提交 | 范围 |
|---|---|
| `0f683d7` | storyboard analyze —— 唯一有既存回归测试盯着的那个（该测试自 `04a190b` 加入起就是红的） |
| `df46632` | 15 个由前端 `updateProject` 调用链确证会喂回 store 的端点 |
| `6a263de` | 其余 43 个，统一化 |

`response_model=Script` 一并从 42 条路由上摘除：该响应模型会把 `merged_project_payload`
添加的 `source` 字段裁掉，而前端靠它区分 episode / series / global 资产并路由写入
（理由原本就写在 `GET /projects/{script_id}` 的注释里）。

### 未纳入的端点

返回的**不是** Script 的 8 处保持原样 —— 单个 `asset` / `frame` / `task` / `tasks` /
`{"url": ...}`。它们的响应里根本没有 `characters` 键，浅合并抹不掉任何东西。

### 统一化前做的安全抽查

风险模式是「不经 store、直接消费响应，且假设只有本集资产」。全库搜索对响应
`.characters/.scenes/.props` 的直接访问，只有 3 处：

- `CastWorkbenchModal.tsx:243` 与 `assetGenerationTask.ts:86` —— 数据来自 `api.getProject`，
  本来就是合并形状，且逻辑是按 id 查找，多出系列资产不影响。
- `ReconcileModal.tsx:68-70` —— 数据来自 `/reconcile/suggestions`，返回的是建议列表而非 Script。

未发现会被统一化破坏的消费方。

### 回归测试

`test_store_fed_endpoints_keep_the_merged_cast` 参数化覆盖 8 个无需真实媒体即可触发的端点。
已验证其辨别力：把 `toggle_starred` 的合并撤掉，**只有**该用例转红。
render / merge / variant 那批走同一条代码路径，但需要真实媒体才能跑，未纳入。

### 最重要的一个

`/reparse`。`projectStore` 的 `confirmExtraction` 与 `analyzeScript` 用
`{ ...project }` **整体替换** `currentProject`，而不是浅合并 —— 未合并的响应在这里会把
cast 彻底清空，而不只是部分覆盖。它还因为返回变量名叫 `result`（而非 `script`/`updated_script`）
躲过了第一轮正则扫描，是靠「按 `response_model=Script` 复查」才捞出来的。
