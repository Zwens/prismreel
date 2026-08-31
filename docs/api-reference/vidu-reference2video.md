# 参考生视频 (Reference-to-Video, Q3)

> 抓取日期: 2026-08-01
> 原文链接: https://shengshu.feishu.cn/wiki/URYzwxfMWizDM7kRlCwcRI3Ynzf
> Provider: vidu / family: vidu / 范围: viduq3-drama, viduq3, viduq3-mix, viduq3-ad
> 文档修改日期: 2026-07-30

## 证据来源说明

飞书 wiki 需登录，自动抓取返回 302 跳登录页。本文件的参数表来自用户提供的文档截图，
**并以真实 API 探测结果校正**（探测用无效图片 URL，任务一律以 `ImageDownloadFailure`
失败，不产生扣费）。凡截图与实测冲突处，以实测为准并在下方标注。

外部 raw archive / Context Hub 同步：**待办**，当前工作区只有本仓库（模式 B）。

---

## 端点

```
POST https://api.vidu.cn/ent/v2/reference2video
```

响应体 `type` 字段返回 `character2video`。

## 请求头

| 字段 | 值 | 描述 |
|---|---|---|
| Content-Type | application/json | 数据交换格式 |
| Authorization | Token {your api key} | 将 {your api key} 替换为您的 token |

## 模型

文档标题：**「新增 viduq3-drama 模型，为剧而生！」推荐使用主体库。**

端点的 model 白名单（飞书《参考生 API（Q3）》rev. 2026-08-24 原文，共 9 个）：

| model | 实测 credits (5s/720p) | 默认 aspect_ratio | audio_type | 说明 |
|---|---|---|---|---|
| `viduq3-drama` | 100 | **9:16** | unspecified | 行业微调，为剧而生。1-7 张图，**时长 2-15s**，支持 1080p |
| `viduq3-ad` | 未测 | — | — | 行业微调，为广告而生。1-7 张图，时长 3-15s，720p/1080p |
| `viduq3-mix` | 未测 | — | — | 画面质感强，智能切镜，音画同出，**均衡性最强**。不支持错峰 |
| `viduq3-turbo` | 未测 | — | — | 智能切镜，音画同出，生成最快，性价比最高 |
| `viduq3` | 60 | 16:9 | all | 智能切镜，音画同出，多机位一致性更出色。audio=true 时支持错峰 |
| `viduq2-pro` | 未测 | — | — | 支持参考视频、视频编辑/替换（`videos` 参数仅此模型支持）|
| `viduq2` | 未测 | — | — | 动态效果好，细节丰富 |
| `viduq1` | 未测 | — | — | 画面清晰，平滑转场，运镜稳定 |
| `vidu2.0` | 未测 | — | — | 生成速度快 |

**`viduq3-pro` 不在此列** —— 它是 i2v/t2v 专用线。把 catalog id `viduq3-pro-r2v`
机械剥掉模式后缀会得到 `viduq3-pro`，该端点以
`FieldInvalid: model is not supported` 拒绝（2026-08-25 线上实测 6 次全拒）。
因此 r2v 的 vendor 模型名由 catalog 的 `runtime.vendor.api_model_id` 显式钉死，
而非从 id 推导：`viduq3-pro-r2v -> viduq3-mix`（与百炼侧
`vidu/viduq3-mix_reference2video` 保持一致）。白名单在
`src/models/vidu.py::VENDOR_R2V_MODELS`，提交前本地校验，不再靠原厂 400 兜底。

对照实验：`viduq3-bogusname` 返回 `FieldInvalid: model is not supported`，
确认上述模型名合法（注意：账户余额不足时余额检查会前置，导致该判据失效）。

## 请求体

### 主体库形式（推荐）

```json
{
  "model": "viduq3-drama",
  "subjects": [
    { "name": "1", "images": ["your_image1", "your_image2"] },
    { "name": "2", "server_id": "321321" }
  ],
  "prompt": "...",
  "duration": 5,
  "resolution": "720p"
}
```

### 扁平形式（实测同样被接受）

```json
{ "model": "viduq3-drama", "images": ["url1", "url2"], "prompt": "..." }
```

服务端响应会把两种形式统一归一为 `images` 字段回显。

### 参数表

| 参数名称 | 类型 | 必填 | 参数描述 |
|---|---|---|---|
| model | String | 是 | 本次调用的模型名称 |
| subjects | Array[Object] | 二选一 | 主体库。每项含 `name`（主体名）+ `images`（图片 URL 数组）或 `server_id`（已上传主体 ID） |
| images | Array[String] | 二选一 | 参考图像 URL 数组（扁平形式） |
| prompt | String | 可选 | 提示词 |
| duration | Int | 可选 | **实测 2–15 秒**。截图内 resolution 表列出 `viduq3-turbo` 1-16 秒、`viduq3` 3-16 秒，但 API 对 `viduq3-drama` 返回 `duration only support between 2 to 15` |
| seed | Int | 可选 | 随机种子。drama 不传时回显 0；viduq3 不传时服务端自动填随机值 |
| aspect_ratio | String | 可选 | 可选 1:1、9:16、16:9、3:4、4:3、auto。**drama 默认 9:16**，viduq3 默认 16:9 |
| resolution | String | 可选 | 540p / 720p / 1080p，默认 720p |
| movement_amplitude | String | 可选 | auto / small / medium / large。**注：q2、q3 系列模型该参数不生效** |
| watermark | Bool | 可选 | 默认 **true**。实测传 `false` 生效，回显 `watermark: false` |
| payload | String | 可选 | 透传参数，最多 1048576 字符。**注：仅 q3-drama、q3-mix、q3-ad 模型支持** |
| off_peak | Bool | 可选 | 错峰模式，默认 false。错峰积分更低，48 小时内生成，未完成自动取消并返还积分 |

## 响应体

实测返回样例（已脱敏）：

```json
{
  "task_id": "9810121814xxxxxxxx",
  "type": "character2video",
  "state": "created",
  "model": "viduq3-drama",
  "style": "general",
  "prompt": "...",
  "images": ["..."],
  "duration": 5,
  "seed": 0,
  "aspect_ratio": "9:16",
  "resolution": "720p",
  "movement_amplitude": "auto",
  "credits": 100,
  "payload": "",
  "off_peak": false,
  "watermark": true,
  "audio_type": "unspecified",
  "created_at": "2026-08-01T05:44:05Z"
}
```

`state` 枚举：created / queueing / processing / success / failed。
查询任务：`GET /ent/v2/tasks/{task_id}/creations`，失败时带 `err_code`（如 `ImageDownloadFailure`）。

## 计费实测

| 配置 | credits |
|---|---|
| viduq3-drama 5s / 720p | 100 |
| viduq3-drama 8s / 1080p | 192 |
| viduq3 5s / 720p | 60 |

账户额度查询：`GET /ent/v2/credits`。

## 尚未确认

- `subjects` 数量上限
- drama 的音频行为（回显 `audio_type: unspecified`，而 viduq3 为 `all`）
- 截图中被遮挡的音频参数（露出 `data:video/mp3;base64,{base64_encode}` 字样，注明仅 q3-drama / q3-mix / q3-ad 支持，参数名不可见）
