---
name: vps-env-not-synced-with-local-env
description: VPS /opt/prismreel/.env 與本機 .env 是兩份獨立檔案，本機新增的環境變數不會自動出現在 VPS，功能會被後端啟動時的預設停用邏輯靜默關閉
metadata:
  type: feedback
---

本機 `.env`（開發用）與 VPS `/opt/prismreel/.env`（正式環境）是完全獨立的兩份檔案，沒有任何自動同步機制。2026-09-10 一次 session 在本機補上 OSS AccessKey/Secret/Bucket/Endpoint 等 5 個欄位並確認功能可用，但從未同步到 VPS，導致下一個 session 排查「r2v 圖片上傳完全無反應」時，查了半天才在 backend log 發現 `OSS credentials not fully configured. OSS upload will be disabled.`——後端啟動時偵測到 OSS 設定不完整，直接靜默停用整個上傳功能，沒有任何前端錯誤提示。

**Why**：跟 [[git-push-does-not-deploy]] 是同一類「本機/VPS 兩份獨立副本」問題，但那條記的是程式碼檔案，這條記的是環境變數——性質不同，觸發時機也不同（環境變數缺口通常不會在部署當下報錯，而是等到某個依賴該變數的功能被使用者實際觸發時才出現，且很多後端會選擇「靜默降級」而非拋錯，更難排查）。

**How to apply**：
1. 任何在本機 `.env` 新增/修改環境變數的任務，完成後主動確認是否也需要同步到 VPS `/opt/prismreel/.env`（`ssh vps_main "grep -i <KEY_PREFIX> /opt/prismreel/.env"` 核對），不要只驗證本機功能就回報完成。
2. 排查「功能完全無反應、沒有任何錯誤訊息」類問題時，優先查後端啟動時的 log（`docker logs <container> --tail 200 | grep -iE "not.*configured|disabled|STARTUP"`），這類問題很可能是啟動時某個環境變數缺失導致功能被靜默關閉，而不是程式碼邏輯壞掉。
3. 修改 VPS `.env` 前先備份（`cp .env .env.bak.$(date +%Y%m%d%H%M%S)`），改完必須 `docker compose up -d --force-recreate <service>` 才會生效（單純 `restart` 不會重讀 `.env`）。
