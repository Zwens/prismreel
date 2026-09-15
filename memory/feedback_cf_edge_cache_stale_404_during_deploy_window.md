---
name: feedback-cf-edge-cache-stale-404-during-deploy-window
description: 新增的靜態檔案路徑若在CI部署完成前被瀏覽器/爬蟲探測過一次，Cloudflare會把那次404快取住（max-age=86400），即使源站後來已有檔案，外部訪客仍持續看到破圖/404
metadata:
  type: feedback
---

Prismreel 走 Cloudflare Tunnel（cloudflared，非傳統 CF Pages），nginx 對 `/files/digital-characters/*.jpg` 這類靜態圖片設定 `cache-control: public, max-age=86400`。這個快取策略本身沒問題，但有個競態視窗：**如果某個新檔案路徑在 CI 部署完成、檔案真正寫入容器之前，被任何請求（包含使用者自己的瀏覽器、健康檢查、爬蟲）命中過一次並拿到 404**，Cloudflare edge 會把這次 404 當成正常回應快取住 24 小時，之後源站即使已經有檔案了，外部訪客仍會持續看到 404/破圖，直到快取自然過期或手動清除。

**判斷這是 CF 快取問題而非真實檔案缺失的方法**：
1. 直接 SSH 進容器內部打後端 port（略過 nginx/CF）：`docker exec <backend> python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:<port>/path').status)"` — 若這裡是 200，代表源站沒問題
2. 對外部 URL 加 query string（如 `?cb=1`）繞開 CF 快取鍵重新請求 — 若這樣就 200，確認是快取鍵命中了舊的 404
3. `curl -D -` 檢查 `cf-cache-status: HIT` + `Age:` header — `Age` 值接近部署時間點就能對上時間線

**修復方式**：Cloudflare Dashboard → 該 Zone → Caching → 設定 → 自訂清除（Custom Purge）→ 選「URL」→ 貼上完整 URL（一行一個，最多30個）→ 清除。5秒內生效。

**How to apply（預防）**：對於「先部署 metadata json，縮圖檔案分批陸續補上」這類非同步上線模式，理論上每次新增檔案後首次外部訪問都有機會撞到這個競態；不必為了預防這個而改變部署流程（發生機率低、修復成本也低），但排查「明明檔案存在卻404/破圖」時，此案例應優先比對，不要先假設是程式邏輯或檔案本身的問題。

**🔴 2026-09-15 縮圖補齊案規模化重演**：分5次commit陸續補480筆角色庫縮圖（120→450），使用者實測「資產庫圖片很多還是沒有」才發現。批次curl檢測450張中**316張**（70%）被CF快取住舊404，只有134張正常——受影響比例遠高於單筆案例，證實「先讀json、圖檔分批補」的模式下，只要中途曾有人（含開發中自己測試）訪問過缺圖階段，就會大量累積。**排查方法補充**：前端若在圖片URL為空/載入失敗時直接fallback成SVG（不留`<img>`標籤），肉眼看到「灰色人形圖示」但`document.querySelectorAll('img')`完全抓不到對應項目，容易誤判成別的角色資料正常。應改用`button[title]`比對biography文字反查asset_id，或直接`fetch(url)`看真實status（瀏覽器fetch與Bash curl可能命中不同CF節點給出不同結果，不能只信其中一種）。**解法**：CF Dashboard → Caching → 設定 → 清除快取 → 清除全部（Purge Everything），5秒生效，450/450全數轉正常，比逐一URL清除更適合這種大比例受影響的場景。
