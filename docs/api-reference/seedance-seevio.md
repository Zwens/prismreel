# Seedance via Seevio (api.seevio.ai)

> 抓取日期: 2026-08-31
> 原文链接: https://seevio.ai/zh-hant/api-docs
> Provider: seevio / family: seedance / 范围: seedance-2.0, seedance-2.0-fast, seedance-2.5
> 文档修改日期: —

## 为什么是这条路径

PrismReel 使用的 Seedance key 由 **Seevio 聚合平台**签发（`sk_live_` / `sk_test_` 前缀），
**不是**火山引擎 Ark / BytePlus ModelArk 官网直连的 key，也不是 MuleRouter 的 `muk-` key。

历史上本仓库把 Seedance 2.0 接到 MuleRouter（`src/models/mulerouter.py`）、
把 Seedance 2.5 接到 Ark 官网直连（`src/models/byteplus.py`）。两者的 wire format
与 Seevio 完全不同，因此 Seevio key 在旧路径上必然失败——这是缺 backend，不是配置问题。

外部 raw archive / Context Hub 同步：**待办**，当前工作区只有本仓库（模式 B）。

---

## 端点

```
POST https://api.seevio.ai/v1/videos/generations   创建任务
GET  https://api.seevio.ai/v1/tasks/{task_id}      查询任务
```

鉴权：`Authorization: Bearer <SEEVIO_API_KEY>`
key 前缀 `sk_live_`（生产）/ `sk_test_`（测试）。缺失或无效返回 `401 invalid_api_key`。

## 模型 id（wire）

| wire model id | 时长 | 说明 |
|---|---|---|
| `seedance-2-5` | 4–30s | 最新版 |
| `seedance-2-0` | 4–15s | |
| `seedance-2-0-fast` | 4–15s | |
| `seedance-2-0-mini` | 4–15s | 本仓库暂未接入 |

注意 wire id 用连字符（`seedance-2-5`），与本仓库 catalog id（`seedance-2.5-*`）不同，需映射。

## 请求体

```bash
curl https://api.seevio.ai/v1/videos/generations \
  -H "Authorization: Bearer sk_live_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "seedance-2-5",
    "callback_url": "https://your-domain.com/api/seedance/webhook",
    "input": {
      "prompt": "a cat surfing on a neon wave, cinematic lighting",
      "generation_type": "text-to-video",
      "duration": 5,
      "aspect_ratio": "16:9",
      "resolution": "1080p",
      "generate_audio": true,
      "watermark": false,
      "web_search": false,
      "return_last_frame": false
    }
  }'
```

必填：`model`、`input.prompt`、`input.generation_type`。

| 字段 | 取值 |
|---|---|
| `input.generation_type` | `text-to-video` \| `image-to-video` \| `reference-to-video` |
| `input.image_urls[]` | 公网可访问图片 URL |
| `input.video_urls[]` | 公网可访问视频 URL |
| `input.audio_urls[]` | 公网可访问音频 URL |
| `input.duration` | 秒，4–30（2.0 系列 4–15） |
| `input.aspect_ratio` | `16:9` \| `4:3` \| `1:1` \| `adaptive` 等 |
| `input.resolution` | `480p` \| `720p` \| `1080p` |
| `input.generate_audio` | boolean |
| `callback_url` | HTTPS 回调（可选，本仓库不用，走轮询） |

### 媒体输入是硬约束

`image_urls` 文档明确要求 **可公开存取的 URL**：不接受 base64 data URI，平台也**没有**上传接口。
因此 seevio backend 必须复用本仓库既有的 OSS 上传+签名链路
（`provider_media` 的 vendor url mode），即 seevio 路径**硬依赖 OSS 配置**。
这与 MuleRouter（收 base64）和 Ark（收 data URI）都不同。

## 响应

创建成功：

```json
{ "taskId": "3f2aK9mR...", "credits": 100 }
```

查询完成：

```json
{
  "id": "3f2aK9mR...",
  "status": "completed",
  "created_at": 1781234567,
  "model": "seedance-2-5",
  "billing_status": "charged",
  "credits": 100,
  "failed_reason": null,
  "data": {
    "results": ["https://cdn.seevio.ai/.../x.mp4"],
    "video_expires_at": "2026-06-13T10:00:00Z",
    "last_frame_url": null,
    "processing_time": 48
  }
}
```

查询失败：

```json
{
  "id": "3f2aK9mR...",
  "status": "failed",
  "billing_status": "refunded",
  "failed_reason": "provider_failed"
}
```

状态机：`queued` → `generating` → `completed` | `failed`。
成片 URL 在 `data.results[]`（数组，取第一个）。

轮询频率：文档建议 **不超过每 10 秒一次**。

## 计费

点数随分辨率、时长、模型、以及 reference-to-video 是否含视频参考而变；
创建响应里返回本次 `credits`，失败会 `refunded`。具体单价见 seevio 价格页。

## 未验证项

| 项 | 状态 |
|---|---|
| 端点 / 鉴权 / 请求体 / 响应体 | 来自官方文档，未做真实调用验证 |
| `aspect_ratio` 完整枚举 | 文档写"16:9 / 4:3 / 1:1 / adaptive 等"，未穷举 |
| 2.0 系列是否支持 `generate_audio` | 文档未按模型区分，实现上原样透传 |

因此 base URL 做成环境变量可覆盖：`SEEVIO_BASE_URL`。
