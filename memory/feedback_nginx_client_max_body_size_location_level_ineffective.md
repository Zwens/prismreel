---
name: nginx-client-max-body-size-location-level-ineffective
description: client_max_body_size 只寫在 location 區塊沒生效，實際套用 http 層級的 1MB 預設值，2.8MB 圖片上傳一律 413
metadata:
  type: feedback
---

`docker/nginx.conf` 原本只在兩個 `location` 區塊內各寫了 `client_max_body_size 100M;`，最外層 `http {}`（`/etc/nginx/nginx.conf`）完全沒有這個指令。實測結果是 2.8MB 的上傳請求仍被拒絕（`413 Request Entity Too Large`，nginx error log 顯示 `client intended to send too large body`），且觸發門檻明顯接近 nginx 預設值 1MB，不是 location 裡設的 100M。

**Why**：2026-09-10 排查 Prismreel r2v 上傳「卡在上傳中不會結束」時發現。原始設計者顯然預期 location 層級的設定會生效（覆蓋更外層），但實測不成立——最保險的做法是直接設在 `server` 或 `http` 層級，不要依賴 location 層級覆蓋外層預設值。

**How to apply**：
1. `client_max_body_size` 一律加在 `server {}` 區塊最上方（本專案 `docker/nginx.conf` 已修正，見 commit `d317312`），不要只寫在個別 `location {}` 裡。
2. 修改 nginx 相關設定後，用 `nginx -t` 驗證語法 + 實際送一個接近舊限制邊界的 payload（如 `curl -F 'file=@...'`）驗證新限制真的生效，不要只看設定檔字面數字就當作已修好。
3. 排查「上傳卡住/沒有明確錯誤」類問題時，優先查 nginx access/error log 找 413/504 等狀態碼，這類問題常見於前端把 HTTP 錯誤吞掉沒有顯示，UI 只會呈現「一直轉圈」。
