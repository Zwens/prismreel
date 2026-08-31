# 同步生图（Vidu-Q 系列 / O 协议格式）

> 抓取日期: 2026-08-24
> 原文标题: 【同步-生图】Vidu-Q系列模型接口（O协议格式）
> 原文修改日期: 8月10日
> provider / family: vidu
> 覆盖 model: q3-lite、q3-fast、q2-pro、q2-fast（按次计费）
>              q3-lite-bytoken、q3-fast-bytoken、q2-pro-bytoken、q2-fast-bytoken（按 token 计费）
> 域名: 国内 https://api.vidu.cn ／ 海外 https://api.vidu.com

---

## 接口地址

```
POST /ent/v2/open/reference2image
```

本接口为**同步**接口：请求返回时图片已生成，响应体直接带图片 URL，无需轮询任务状态。
这与 Vidu 视频接口（异步 + 轮询）不同。

## 请求头

| 字段 | 描述 | 值 |
|---|---|---|
| Content-Type | 数据交换格式 | application/json |
| Authorization | 将 {your api key} 替换为您的 token | Token {your api key} |

## model

按调用次数计费，模型枚举值：

- `q3-lite`
- `q3-fast`
- `q2-pro`
- `q2-fast`

按 token 计费，模型枚举值：

- `q3-lite-bytoken`
- `q3-fast-bytoken`
- `q2-pro-bytoken`
- `q2-fast-bytoken`

## 请求体

采用 OpenAI 协议（O 协议）的 messages 结构，`content` 为数组，可混排以下 part：

| type | 说明 |
|---|---|
| `text` | 文本提示词 |
| `image_url` | 参考图，`{"url": "<公网可访问的图片地址>"}`，可出现多次 |
| `output_image` | 输出图规格，`{"size": "<宽x高>"}` |

```bash
curl -X POST "https://api.vidu.cn/ent/v2/open/reference2image" \
  -H "Authorization: Token $api_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "q3-fast",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "Create a professional e-commerce fashion photo."},
          {"type": "image_url", "image_url": {"url": "https://.../ref-1.png"}},
          {"type": "image_url", "image_url": {"url": "https://.../ref-2.png"}},
          {"type": "output_image", "image": {"size": "1920x1088"}}
        ]
      }
    ]
  }'
```

## 响应体

```json
{
  "created": "1787585699",
  "data": [
    {"url": "https://cdn.vidu.cn/api/image.png"}
  ],
  "credits": 8,
  "usageMetadata": {
    "candidatesTokenCount": 1523,
    "candidatesTokensDetails": [{"modality": "IMAGE", "tokenCount": 1120}],
    "promptTokenCount": 16,
    "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 16}],
    "serviceTier": "standard",
    "totalTokenCount": 1539
  }
}
```

## Size 与分辨率&比例映射关系

| OpenAI size | aspect_ratio | resolution |
|---|---|---|
| 1024x1024 | 1:1 | 1K |
| 512x2064 | 1:4 | 1K |
| 2046x512 | 4:1 | 1K |
| 352x2928 | 1:8 | 1K |
| 2928x352 | 8:1 | 1K |
| 896x1200 | 3:4 | 1K |
| 1200x896 | 4:3 | 1K |
| 1376x768 | 16:9 | 1K |
| 768x1376 | 9:16 | 1K |
| 2192x928 | 21:9 | 1K |
| 2048x2048 | 1:1 | 2K |
| 1536x2752 | 9:16 | 2K |
| 2752x1536 | 16:9 | 2K |
| 4384x1872 | 21:9 | 4K |
| 4800x3584 | 4:3 | 4K |
| 3584x4800 | 3:4 | 4K |
| 2048x8256 | 1:4 | 4K |
| 8256x2048 | 4:1 | 4K |
| 1408x11712 | 1:8 | 4K |
| 11712x1408 | 8:1 | 4K |

## 定价（按次计费）

| 模型 | vidu 积分消耗 | vidu 价格（元） |
|---|---|---|
| q3-lite | 1K: 8 积分 | 0.25 |
| q3-fast | 1K: 15 积分 | 0.46875 |
| q3-fast | 2K: 25 积分 | 0.78125 |
| q3-fast | 4K: 35 积分 | 1.09375 |
| q2-pro | 1K: 30 积分 | 0.9375 |

## 按 token 计费

```
input_text_token价格   = input_text_tokens   * token积分单价 * 14
input_image_token价格  = input_image_tokens  * token积分单价 * 14
output_image_token价格 = output_image_tokens * token积分单价 * 800
output_text_token价格  = output_text_tokens  * token积分单价 * 80
```

q3-lite(nano-2-lite) 按 token 计费：

| 模型 | 输入类型 | input（每百万 tokens） | output（每百万 tokens） |
|---|---|---|---|
| q3-lite-bytoken | 图片/文本 | 国内 2 元 ／ 海外 $0.25 | 文本&思考：国内 10 元 ／ 海外 $1.5<br>图片：国内 200 元 ／ 海外 $30 |

---

## 实测补充（2026-08-24，本仓库用真实 key 验证）

以下几点文档未写明，但会直接影响实现，均为实际调用验证所得：

1. **纯文生图可用**。接口名虽为 `reference2image`，但 `content` 中不提供任何 `image_url`
   时同样正常出图，可直接用作 t2i 通道。
2. **`created` 返回的是字符串**（如 `"1787585699"`），而非原文示例中的数字
   `1712563200`。按整型解析会失败。
3. **返回的图片 URL 是 S3 预签名地址，`X-Amz-Expires=86400`，即 24 小时后失效。**
   必须在收到响应后立即下载落地或转存 OSS，不能把该 URL 当作长期地址存库。
4. 实测耗时：纯文生图 12–18 秒；带 1 张参考图 85.7 秒（约 5 倍差距）。
5. 实测计费：q3-lite 1K，纯文生图与带参考图均为 `credits: 8`，与文档「1K: 8 积分」一致。
6. 实测 `size` 语义准确：请求 `1376x768` 返回的就是 1376x768 的 16:9 图。

## 仍待同步

外部 raw archive 与 Context Hub 源仓在当前工作区不可用，本文件为仓库内 staging mirror
（onboarding 流程模式 B）。跨仓同步尚未完成。
