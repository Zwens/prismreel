---
name: project-r2v-upload-fix-2026-09-10
description: r2v多圖上傳從完全無反應修復到正常可用的完整過程，三層根因依序排查 + 縮圖UX迭代
metadata:
  type: project
---

2026-09-10，使用者回報 Playground r2v 多圖模式拖圖上傳完全無反應，排查出三層獨立根因，依序修復：

## 根因鏈（依發現順序）

1. **OSS 環境變數未同步到 VPS** — 本機 `.env` 已設 OSS AccessKey/Secret/Bucket/Endpoint，VPS `/opt/prismreel/.env` 完全沒有這些欄位，後端啟動時記錄 `OSS credentials not fully configured. OSS upload will be disabled.` 靜默停用上傳功能。已補上並 `docker compose up -d --force-recreate backend`。見 [[vps-env-not-synced-with-local-env]]。
2. **OSS AccessKey 對 bucket `ai-seo-video` 缺 PutObject 權限** — 用 `oss2` 直接測 `put_object` 回傳 `403 AccessDenied: bucket acl`。使用者到阿里雲 RAM 控制台調整後，重測 `put_object`+`object_exists` 確認成功並清除測試檔案。
3. **nginx `client_max_body_size` 設在 location 層級不生效** — 2.8MB 圖片一律 413，實際套用的是 http 層級 1MB 預設值。已改設在 `server` 層級，寫回 `docker/nginx.conf`（commit `d317312`）。見 [[nginx-client-max-body-size-location-level-ineffective]]。

中途一次「Application error: client-side exception」是瀏覽器快取舊版 chunk 造成的 404，硬性重新整理（Ctrl+Shift+R）後排除，非新增問題。

## 縮圖 UX 迭代（4 次，均已部署驗證）

1. 72px → 96px（`w-24 h-24`），字體同步放大
2. 檔名從圖片內漸層遮罩移到圖片下方獨立一行（原本疊圖上無法正常選取複製）
3. 移除 `truncate`，改 `break-all` 讓長檔名完整換行顯示（原本省略號導致選取只拿到截斷部分）
4. 最終改為完全移除檔名顯示，只留左上角「Image N」徽章 — 因為檔名本身是後端 `uuid.uuid4()` 產生的無意義亂碼，見 [[upload-filename-is-backend-uuid-not-original]]，且已查證模型辨識多圖靠 `ref_image_urls` 陣列順序而非檔名/徽章文字。

## Commits（分支 `feature/multi-tenant-auth`）
- `d317312` fix(nginx): set client_max_body_size at server level
- `5a176f0` fix(playground): enlarge r2v thumbnails
- `245ce34` fix(playground): move filename below thumbnail
- `276b6f9` fix(playground): stop truncating filenames
- `4a2e2a0` fix(playground): drop filename display entirely

每次前端改動均走：本機改 → commit+push → scp 同步 `/opt/prismreel` → `docker compose build frontend` → `docker compose up -d --force-recreate frontend` → curl 驗證 200，符合 [[git-push-does-not-deploy]] 既定流程。

## 狀態
✅ 已完成，使用者確認可正常上傳。無待辦事項。
