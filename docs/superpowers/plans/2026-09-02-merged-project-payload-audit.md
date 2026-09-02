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

## 已修（18 个）

| 方法 | 路由 |
|---|---|
| `GET` | `/projects/{script_id}` |
| `POST` | `/projects/{script_id}/art_direction/clear` |
| `POST` | `/projects/{script_id}/art_direction/save` |
| `POST` | `/projects/{script_id}/assets/generate_motion_ref` |
| `POST` | `/projects/{script_id}/assets/update_description` |
| `POST` | `/projects/{script_id}/assets/update_image` |
| `POST` | `/projects/{script_id}/assets/variant/delete` |
| `POST` | `/projects/{script_id}/assets/variant/favorite` |
| `POST` | `/projects/{script_id}/assets/variant/select` |
| `POST` | `/projects/{script_id}/characters/{char_id}/voice` |
| `POST` | `/projects/{script_id}/frames/{frame_id}/extract_last_frame` |
| `POST` | `/projects/{script_id}/frames/{frame_id}/select_video` |
| `POST` | `/projects/{script_id}/frames/{frame_id}/upload_image` |
| `POST` | `/projects/{script_id}/merge` |
| `POST` | `/projects/{script_id}/model_settings` |
| `POST` | `/projects/{script_id}/storyboard/analyze` |
| `POST` | `/projects/{script_id}/storyboard/render` |
| `POST` | `/projects/{script_id}/sync_descriptions` |

`0f683d7` 修了 storyboard analyze 与既有的 GET / bind_voice；`df46632` 修了其余 15 个
（前端已确证喂回 store 的那批），并给其中 3 个能在无媒体条件下触发的加了参数化回归测试。

## 未修（42 个）

同样返回完整 Script。「声明了 response_model」一列为「是」的，即使包上
`merged_project_payload` 也会被响应模型把 `source` 字段裁掉，必须一并去掉该声明
（理由见 `GET /projects/{script_id}` 的注释）。

| 方法 | 路由 | 声明了 response_model=Script |
|---|---|---|
| `POST` | `/projects/{script_id}/assets/generate` | 否 |
| `POST` | `/projects/{script_id}/assets/toggle_lock` | 是 |
| `POST` | `/projects/{script_id}/assets/toggle_starred` | 是 |
| `POST` | `/projects/{script_id}/assets/update_attributes` | 是 |
| `POST` | `/projects/{script_id}/assets/{asset_type}/{asset_id}/generate_video` | 是 |
| `POST` | `/projects/{script_id}/assets/{asset_type}/{asset_id}/upload` | 否 |
| `DELETE` | `/projects/{script_id}/assets/{asset_type}/{asset_id}/videos/{video_id}` | 是 |
| `PUT` | `/projects/{script_id}/audio_mix` | 是 |
| `POST` | `/projects/{script_id}/beats/align` | 是 |
| `POST` | `/projects/{script_id}/characters` | 是 |
| `DELETE` | `/projects/{script_id}/characters/{char_id}` | 是 |
| `PUT` | `/projects/{script_id}/characters/{char_id}/voice_params` | 是 |
| `POST` | `/projects/{script_id}/dialogue_audio/batch` | 否 |
| `POST` | `/projects/{script_id}/frames` | 是 |
| `POST` | `/projects/{script_id}/frames/copy` | 是 |
| `PUT` | `/projects/{script_id}/frames/reorder` | 是 |
| `POST` | `/projects/{script_id}/frames/toggle_lock` | 是 |
| `PUT` | `/projects/{script_id}/frames/trims` | 是 |
| `POST` | `/projects/{script_id}/frames/update` | 是 |
| `DELETE` | `/projects/{script_id}/frames/{frame_id}` | 是 |
| `POST` | `/projects/{script_id}/frames/{frame_id}/audio` | 是 |
| `POST` | `/projects/{script_id}/frames/{frame_id}/auto_select_latest_video` | 是 |
| `DELETE` | `/projects/{script_id}/frames/{frame_id}/dub` | 否 |
| `POST` | `/projects/{script_id}/frames/{frame_id}/dub/apply` | 否 |
| `POST` | `/projects/{script_id}/frames/{frame_id}/dub/preview` | 否 |
| `POST` | `/projects/{script_id}/frames/{frame_id}/unpin_video` | 是 |
| `POST` | `/projects/{script_id}/generate_assets` | 是 |
| `POST` | `/projects/{script_id}/generate_audio` | 是 |
| `POST` | `/projects/{script_id}/generate_storyboard` | 是 |
| `POST` | `/projects/{script_id}/generate_video` | 是 |
| `PUT` | `/projects/{script_id}/last_episode_summary` | 否 |
| `POST` | `/projects/{script_id}/mix/generate_bgm` | 是 |
| `POST` | `/projects/{script_id}/mix/generate_sfx` | 是 |
| `POST` | `/projects/{script_id}/props` | 否 |
| `DELETE` | `/projects/{script_id}/props/{prop_id}` | 否 |
| `POST` | `/projects/{script_id}/reconcile/apply` | 否 |
| `POST` | `/projects/{script_id}/scenes` | 是 |
| `DELETE` | `/projects/{script_id}/scenes/{scene_id}` | 是 |
| `PATCH` | `/projects/{script_id}/style` | 是 |
| `PUT` | `/projects/{script_id}/subtitle/settings` | 否 |
| `PUT` | `/projects/{script_id}/text` | 是 |
| `POST` | `/projects/{script_id}/toggle_starred` | 否 |

## 建议

倾向**统一处理**：让所有返回完整 Script 的 project 端点都走 `merged_project_payload`。

- 一致性本身就是防御。留着「有的合并、有的不合并」，未来任何一个端点被前端接进 store
  就会复现同一个 bug，而且下一个人没法从代码看出哪些是安全的。
- 风险可控：`GET /projects/{script_id}` 一直返回合并形状，store 里的 `currentProject`
  也一直是合并形状，所以前端从 store 读的路径本来就在处理这个形状。
- 真正的风险在于**不经 store、直接消费响应**且假设「只有本集资产」的前端代码。
  统一化前需要抽查这类调用点。

替代方案：只在有明确前端证据时逐个修。代价是这份清单要一直维护下去。
