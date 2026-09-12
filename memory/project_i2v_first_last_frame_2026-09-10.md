---
name: project-i2v-first-last-frame
description: Playground i2v 首末幀模式+提示詞無上限+Image N編號徽章，四點需求已實作並部署上線
metadata:
  type: project
---

2026-09-10 完成四點 Playground 需求並部署到 https://prismreel.soulo-ai.com：

1. r2v 多圖縮圖新增「Image N」編號徽章，讓使用者可在 prompt 文字裡明確引用特定圖片
2. 提示詞字數上限（原 2000）已移除，計數器只顯示已輸入字數
3. Playground 模式卡片 `i2v` 標題三語系統一改為「首尾幀生成影片」，因功能範圍從純首幀擴充為首尾幀
4. i2v 從單槽首幀改為雙槽（首幀必填、末幀選填，強制先上傳首幀才能上傳末幀），後端 `build_ark_content`（`src/models/byteplus.py`）依 Ark 規則明確標記 `role: first_frame` / `last_frame` / `reference_image`，三者互斥情境已用單元測試覆蓋（見 `tests/test_byteplus_seedance.py`）

**Why**：BytePlus Ark API 文件明確規定 `image_url` 的 `role` 欄位有三種互斥場景（純首幀/首末幀/omni reference），原始需求「首幀之外加入其他多圖」在 API 層面做不到（`first_frame` 與 `reference_image` 不能混用），與使用者確認後改為「首末幀」模式。

**部署過程踩坑**：VPS 部署目錄落後本機多個 commit（缺整個模式卡片重構）+ lockfile 版本不相容（見 [[feedback_lockfile_must_regenerate_in_build_env_container]]），已改用完整目錄同步（保留 `.env`/`output/`）+ 容器內重新產生 lockfile 解決。

**未竟事項**：
- OSS AccessKey（`LTAI5tEBtniJ3YmqcxBPbTYm`）對 bucket `ai-seo-video` 有簽章驗證但無 `ListBucket` 權限（`AccessDenied: The bucket you access does not belong to you`），需使用者到阿里雲 RAM 控制台確認該 AccessKey 授權範圍
- VPS `.env` 尚未同步本機新設定的 OSS 相關欄位（`OSS_ENDPOINT` 等仍是 `None`），若要在正式站測試 OSS 上傳功能需額外同步
