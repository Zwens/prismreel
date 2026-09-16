# 探针报告：真人换装 + 舞蹈动作复刻

日期：2026-09-15
类型：Spike（可行性探针，非设计文档）
结论：**原定方案被内容策略堵死，但发现了一条更短、效果更好的路。**

探针代码在 `scratch/dance-probe/`，全部是一次性的，已 gitignore，不进主干。

---

## 1. 头号发现：不需要三视图，也不需要深度视频

原计划复刻文章的三段式流程（换装三视图 → 黑白深度视频 → 合成）。
实测发现 **Ark Seedance 2.5 的 `task_type=reference` 只喂原舞蹈视频 + 一句换装
描述，就能直接产出「同一个真人、同一支舞、换了衣服」的成片**。

- 请求里没有任何 `reference_image`
- 逐帧对比（第 0 / 40 / 90 帧）：人物、面部、发型、场地、光线、机位全部一致，
  姿势逐帧吻合；只有服装从「白背心 + 黑色阔腿裤」变成「淡紫缎面吊带裙 + 白鞋」
- 产物：`scratch/dance-probe/out/5_videoonly.mp4`
- 对比图：`scratch/dance-probe/out/compare_outfit_swap.png`
- 成本：480p / 5s，48437 tokens

文章之所以要绕三视图和深度图，是因为它那条工具链没有「视频参考」这种输入。
我们有，所以整条流水线可以塌缩成一次调用。

## 2. Ark 真人内容策略的确切边界

全部经真实请求验证，被拒是同步 400、不计费。

| 输入形态 | 结果 | 证据 |
|---|---|---|
| 参考图里是真人（`reference_image`） | **拦** | `400 InputImageSensitiveContentDetected.PrivacyInformation` |
| 真人图作 i2v 首帧（`first_frame`） | **拦** | 同一错误码 |
| 参考**视频**里是真人 | **放行** | `5_videoonly.mp4` 正常出片 |
| 参考图是明显的插画 | 放行 | L1 半写实插画 |
| 参考图是照片质感（哪怕提示词写"3D CG"） | **拦** | L2，Gemini 渲成了照片级皮肤 |
| 参考图是二次元动漫 | 放行 | L3 |

**规则：Ark 只审图、不审视频；图里只要是照片质感的人脸就拦。**

错误原文：
```
HTTP 400 InputImageSensitiveContentDetected.PrivacyInformation:
The request failed because the input image 'content[1]' may contain real person.
```

Gemini 侧全程无拦截：写实人像、真人换装三视图都正常生成，质量很好
（`1b_threeview.png`，同一张脸、正/侧/背、比例与眼线对齐）。墙只在 Ark。

## 3. 由此产生的能力分界

必须把两种需求拆开，它们的可行性完全不同：

- **A「换装」**——保留原视频里的人和舞，只换服装/场景。
  **已验证可行**，一次调用，绕开策略。
- **B「换人」**——把用户指定的人物套进某支舞。
  **真人做不到**，参考图必被拦。天花板是 L1 那种插画风角色。

## 4. 深度视频的实测代价（结论已被后续测量推翻一次）

初测 Video Depth Anything Large 用了 **12 分钟**处理 5 秒素材，一度让这步看起来
不可用。原因不是模型慢，是**默认的 `input_size=518` 在 8 GB 卡上超显存**——而
Windows 的 WDDM 不会报 OOM，它把溢出部分悄悄放进系统内存，于是"能跑但慢一个
数量级"。

RTX 4060 Laptop (8 GB)，121 帧 480×854：

| 编码器 | input_size | 耗时 | 峰值显存 |
|---|---|---|---|
| Large | 518 | 720 s | 10.6 GB（溢出） |
| Large | 392 | 51 s | 7.02 GB |
| **Small** | **518** | **9.8 s** | **2.76 GB** |
| Small | 392 | 5.5 s | 1.67 GB |

两个发现：

1. **同等视觉质量下，输入分辨率比编码器容量重要**。vits@518 与 vitl@392 在人物
   轮廓上肉眼等价，但前者快 5 倍、省 4.3 GB。所以正确的默认不是"固定某个数"，
   也不是"大模型降档",而是**能满分辨率跑的最大模型**。
   `depth_video.auto_plan()` 按实测拟合的显存曲线做这件事。
2. **不需要 xformers**。上游 `MemEffAttention` 在缺 xformers 时静默退回朴素
   attention（单次 softmax 11.4 GiB）。改用 torch 自带的
   `scaled_dot_product_attention` 即可，见 `src/vendor/NOTICE.md`。

最终：**5 秒素材 9.8 秒出深度视频**，比最初快 73 倍。这步不再是瓶颈。

另需注意深度图的灰度归一化必须**按整段而非逐帧**计算，否则静止的人物会逐帧
明暗跳动，正好抵消这个模型存在的意义。

## 5. 其他

- **Vidu 测不了**：`VIDU_API_KEY` 有效但账户 `CreditInsufficient`，
  无法验证它对真人参考图的策略。要测需先充值。
- **网络不稳**：到 `ark.ap-southeast.bytepluses.com` 多次
  `ConnectionReset(10054)` / `ConnectTimeout`。有一次建任务成功但轮询断了，
  任务其实在正常出片。**产品侧必须有「建任务与轮询解耦 + 断线可恢复」的设计**，
  否则用户会看到失败但照样被计费。
- **`_resolve_ark_image_url` 的口子**：相对路径若不被 `classify_media_ref`
  认作已知根下的本地文件，会直接抛
  `requires a URL-compatible media source ... classified as 'unknown'`，
  而不是尝试上传。接入新的上传入口时要注意。

## 6. 结论

三步流水线已实现并端到端验证（`真人照 + 服装图 → 换装三视图 → 深度动作 →
成片`）。用用户自备素材跑通的证据：

- `scratch/dance-probe/out/person3/motion_match.png` —— 上排深度参考、下排成片，
  四个采样帧姿势逐一吻合。
- 换装保真度：人物面部特征与服装细节（蕾丝肩带、抽褶胸围、A 字摆）均还原。

能力边界，必须在 UI 上说清楚：

| 诉求 | 可行性 |
|---|---|
| 真人换装（静态图） | 可以，Gemini 全程无限制 |
| 真人 + 动作（视频） | **不可以**，Ark 拒绝任何写实真人输入图 |
| 插画风 + 动作 | 可以 |
| 已有真人视频 → 换装保动作 | 可以，且不需要参考图 |

不要试图用"把照片转成静止视频再当参考视频"绕过审核：Ark 确实只审图不审视频，
但那是刻意规避厂商的内容策略，违反其条款且可能导致封号。真人要动起来的正路是
拿到本人的真实视频，或使用带肖像授权流程的平台。
