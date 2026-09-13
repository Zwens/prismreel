# PrismReel 用户手册

> 作者：星莲(StarLotus，张钧贺)

## 📋 目录

1. [快速开始](#-快速开始)
2. [API 密钥配置](#-api-密钥配置)
3. [OSS 存储配置（可选）](#-oss-存储配置可选)
4. [日志查看](#-日志查看)
5. [常见问题](#-常见问题)

---

## 🚀 快速开始

### 首次启动（仅限应用打包方式）

1. **双击应用图标**启动 PrismReel
2. 应用会自动打开**设置页面**
3. 按照提示完成 **API 密钥配置**

### 应用数据目录

所有用户数据存储在以下位置：

| 系统 | 路径 |
|------|------|
| macOS / Linux | `~/.prismreel/` |
| Windows | `C:\Users\<用户名>\.prismreel\` |

---

## 🔑 API 密钥配置

PrismReel 的 AI 能力分两块：**Google Gemini** 负责剧本分析、提示词润色、图像生成与配音；**视频生成**由 BytePlus ModelArk（Seedance）、Kling 原厂或 Vidu 原厂提供，按需配置其一即可。

| 密钥 | 是否必填 | 承担的能力 |
|------|----------|------------|
| `GEMINI_API_KEY` | **必填** | 剧本分析、Prompt 润色、图像生成、TTS 配音 |
| `ARK_API_KEY` | 视频必填其一 | Seedance 2.5 / 2.0 / 2.0 Fast / 2.0 Mini |
| `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | 视频必填其一 | Kling V3 |
| `VIDU_API_KEY` | 视频必填其一 | Vidu Q3 系列（视频 + 图像） |

### 获取 Gemini API Key（必填）

1. 访问 [Google AI Studio](https://aistudio.google.com/apikey)
2. 登录您的 Google 账号
3. 点击 **Create API key**
4. 复制生成的 API Key

### 获取 Ark API Key（生成视频时需要）

1. 访问 BytePlus ModelArk 控制台
2. 创建 API Key
3. 在控制台中 **激活 Seedance 模型** —— 仅有 API Key 而未激活模型时，调用会返回 404

### 在应用中配置

1. 启动 PrismReel
2. 点击左上角 **设置图标** ⚙️
3. 找到 **GEMINI_API_KEY** 输入框，粘贴您的 API Key
4. 如需生成视频，再填入 **ARK_API_KEY**（或 Kling / Vidu 的原厂凭证）
5. 点击 **保存**

> ⚠️ **重要**：请妥善保管您的 API Key，不要泄露给他人。

---

## 🧩 运行模式说明（含必填项）

PrismReel 的媒体存储是 **本地优先**：

- 所有素材先落盘到 `output/`；
- OSS 仅在你配置后作为“可选镜像 + 签名 URL”使用；
- Kling 与 Vidu 只有原厂直连一条路径，不再有代理后端。

### 模式 1：Gemini-only（推荐起步）

- 适用：先跑通剧本分析、美术指导、图像资产与配音，暂不生成视频。
- 必填：
  - `GEMINI_API_KEY`

### 模式 2：Gemini + BytePlus ModelArk（完整链路）

- 适用：要跑通「剧本 → 分镜 → 资产 → 视频 → 合成 → 导出」全流程。
- 必填：
  - `GEMINI_API_KEY`
  - `ARK_API_KEY`（并已在 ModelArk 控制台激活 Seedance 模型）

### 模式 3：追加 Kling 原厂

- 适用：视频侧想用 Kling V3。
- 在模式 1 或 2 的基础上追加：
  - `KLING_ACCESS_KEY`
  - `KLING_SECRET_KEY`

### 模式 4：追加 Vidu 原厂

- 适用：视频侧想用 Vidu Q3 系列（同时也提供 Q3 图像模型）。
- 在模式 1 或 2 的基础上追加：
  - `VIDU_API_KEY`

### 模式 5：追加 OSS（可选增强）

- 适用：希望保留本地文件，同时在 OSS 做镜像和 URL 服务。
- 在上述任一模式的基础上追加：
  - `ALIBABA_CLOUD_ACCESS_KEY_ID`
  - `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
  - `OSS_BUCKET_NAME`
  - `OSS_ENDPOINT`
- 可选：
  - `OSS_BASE_PATH`

> 提示：是否配置 OSS 与选用哪家视频厂商是彼此独立的开关，可自由组合；视频厂商也可以同时配置多家，在模型选择器里逐次切换。

---

## ☁️ OSS 存储配置（可选）

OSS 配置用于云端存储生成的资产，适合团队协作或跨设备使用。

### 获取 OSS 配置信息

1. 访问 [阿里云 OSS 控制台](https://oss.console.aliyun.com/)
2. 创建或选择一个 **Bucket**
3. 记录以下信息：
   - **Bucket 名称**
   - **Endpoint**（如 `oss-cn-beijing.aliyuncs.com`）
4. 在 **RAM 访问控制** 中创建 AccessKey

### 在应用中配置

在设置页面填写以下字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| ALIBABA_CLOUD_ACCESS_KEY_ID | AccessKey ID | `LTAI5t...` |
| ALIBABA_CLOUD_ACCESS_KEY_SECRET | AccessKey Secret | `xxxxxx...` |
| OSS_BUCKET_NAME | Bucket 名称 | `my-prismreel-bucket` |
| OSS_ENDPOINT | OSS 地域节点 | `oss-cn-beijing.aliyuncs.com` |
| OSS_BASE_PATH | 存储路径前缀 | `prismreel` |

---

## 📋 日志查看

当遇到问题时，日志文件可帮助排查原因。

### 日志文件位置

| 系统 | 路径 |
|------|------|
| macOS / Linux | `~/.prismreel/logs/app.log` |
| Windows | `C:\Users\<用户名>\.prismreel\logs\app.log` |

### 打开日志目录

**macOS**：
1. 打开 Finder
2. 按 `Cmd + Shift + G`
3. 输入 `~/.prismreel/logs` 并回车

**Windows**：
1. 打开资源管理器
2. 在地址栏输入 `%USERPROFILE%\.prismreel\logs`
3. 按回车

### 如何提交问题报告

如需技术支持，请提供：
1. **app.log** 文件（或其中的错误部分）
2. 操作步骤描述

---

## ❓ 常见问题

### Q: 为什么需要配置 API Key？

A: PrismReel 调用的是各厂商的云端 AI 模型 —— Gemini 负责文本、图像与配音，Seedance / Kling / Vidu 负责视频。API Key 用于验证您的身份并由对应厂商计费。

### Q: OSS 配置失败怎么办？

请检查：
1. AccessKey ID 和 Secret 是否正确
2. Bucket 名称是否存在
3. Endpoint 格式是否正确（不需要 `https://` 前缀）
4. RAM 权限是否包含 OSS 读写权限

### Q: 生成失败如何排查？

1. 查看日志文件中的错误信息
2. 检查 API Key 是否过期或余额不足
3. 确认网络连接正常

### Q: 如何清理缓存？

删除 `~/.prismreel/` 目录下的 `webview_storage` 文件夹，然后重启应用。

---

## 📞 获取帮助

如有问题，请联系本项目开发者 星莲（StarLotus，张钧贺） 或查看项目 README 文档。
