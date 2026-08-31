# Seedance via MuleRouter vendor passthrough

> 抓取日期: 2026-08-30
> 原文链接: 无公开文档（vendor 透传路径不在 https://mulerouter.ai/docs/llms.txt 索引内）
> Provider: mulerouter / family: seedance / 范围: seedance-2.0, seedance-2.0-fast
> 文档修改日期: —

## 证据来源说明

MuleRouter 的公开文档索引（`llms.txt`）**不包含任何 Seedance 页面**——本仓库使用的是
`/vendors/bytedance/` 透传路径，不在其自有模型列表中。因此本文件的参数契约
**全部来自对生产端点的实测**。

关键性质：**该网关的参数校验发生在鉴权之前**。因此所有必填字段、枚举值和数值区间
都可以在**没有有效 API key** 的情况下探明，且**不产生任何扣费**——请求在创建任务前
就被拒绝。下表每一行都标注了实测所得的原始错误信息。

外部 raw archive / Context Hub 同步：**待办**，当前工作区只有本仓库（模式 B）。

---

## 端点

```
POST https://api.mulerouter.ai/vendors/bytedance/v1/seedance-2.0/text-to-video/generation
POST https://api.mulerouter.ai/vendors/bytedance/v1/seedance-2.0/image-to-video/generation
POST https://api.mulerouter.ai/vendors/bytedance/v1/seedance-2.0/reference-to-video/generation
```

`seedance-2.0-fast` 为同构路径，三个模式齐全（运行时已实现，catalog 尚未暴露）。

鉴权：`Authorization: Bearer <MULEROUTER_API_KEY>`
缺失时返回 `401 / error_code 1001 / "Missing Authorization header"`；
无效或吊销的 key 返回 `401 / error_code 1001 / "Invalid or revoked API key"`。

## 各模式必填字段（实测）

| 模式 | 必填 | 实测错误（缺字段时） |
|---|---|---|
| text-to-video | `prompt` | — （仅 prompt 即通过校验） |
| image-to-video | `prompt`, `image` | `Invalid parameters: 'image' expected to be provided, got None` |
| reference-to-video | `prompt`, `images`（或 `videos`） | `at least one of 'images' or 'videos' must be provided` |

**`reference_images` 不是有效字段名**——传入后网关完全忽略，仍报上述缺 `images` 错误。
本仓库曾使用该字段，导致 R2V 100% 失败；已于 2026-08-30 修正为 `images`
（见 `tests/test_mulerouter_seedance_body.py`）。

## 参数区间（实测）

| 参数 | 取值 | 实测错误（越界时） |
|---|---|---|
| `duration` | `-1`（auto）或 `[4, 15]` 整数 | `duration must be -1 (auto) or an integer in [4, 15], got 99` |
| `resolution` | `480p` \| `720p` \| `1080p` | `'resolution' expected Input should be '480p', '720p' or '1080p', got '4k'` |

注：catalog 此前只暴露 `720p / 1080p`，缺 `480p`；已补齐。

## 错误码

| HTTP | error_code | 含义 |
|---|---|---|
| 400 | 2001 | Parameter validation failed（**先于鉴权**） |
| 401 | 1001 | Authentication failed |
| 404 | — | 路径不存在 |

---

## Seedance 2.5 可用性结论

**MuleRouter 目前不提供 Seedance 2.5。** 实测（2026-08-30）：

| 探测路径 | HTTP |
|---|---|
| `seedance-2.0`, `seedance-2.0-fast` | 400（存在，参数校验失败） |
| `seedance-2.5`, `seedance-2.5-fast` | 404 |
| `seedance-2-5`, `seedance2.5`, `seedance-v2.5`, `seedance-2.5-pro`, `doubao-seedance-2.5`, `seedance-25` | 404 |
| 阴性对照 `does-not-exist-xyz` | 404 |

Seedance 2.5（ByteDance，2026-07-31 上线）目前已知的可用通道：

| 通道 | model id |
|---|---|
| BytePlus ModelArk（国际） | `dreamina-seedance-2-5-260628` |
| 火山引擎 Ark（国内） | `doubao-seedance-2.5` / `doubao-seedance-2-5-260628` |
| OpenRouter | `bytedance/seedance-2.5` |

### 已实现的接入方式（2026-08-30）

2.5 改走 **BytePlus ModelArk / Volcano Ark**，实现见 `src/models/byteplus.py`，
新增 backend `byteplus`（`SUPPORTED_PROVIDER_BACKENDS`）。

契约来源：本仓库既有的 Ark SDK 用法（`src/models/doubao.py`）——
`content_generation.tasks.create(model=..., content=[{type:text},{type:image_url}])`
+ `tasks.get(task_id)`，生成参数以 `--flag value` 形式拼在 text 内。
本模块用 REST 直接说这套协议，不引入 `volcenginesdkarkruntime` 依赖。

**实测（2026-08-30）**：`ark.ap-southeast.bytepluses.com`（国际）与
`ark.cn-beijing.volces.com`（国内）均返回 `401 AuthenticationError`，
证明 host 与 `/api/v3` 前缀真实存在。但 Ark **鉴权先于校验**（与 MuleRouter 相反），
因此在无有效 key 的情况下**无法探明请求体**。

| 项 | 状态 |
|---|---|
| host 可达性 | ✅ 实测 401 |
| 请求体 / 轮询结构 | ⚠️ 依据仓库既有 SDK 用法推定，**未经真实调用验证** |
| REST 路径 `/contents/generations/tasks` | ⚠️ 未验证（可用 `ARK_TASKS_PATH` 覆盖） |
| wire model id `dreamina-seedance-2-5-260628` | ⚠️ 来自公开资料，未验证 |

因此 host / 路径 / model id 全部做成环境变量可覆盖：
`ARK_BASE_URL`、`ARK_REGION`（intl\|cn）、`ARK_TASKS_PATH`。
配置 `ARK_API_KEY` 后需做一次真实调用验证。
