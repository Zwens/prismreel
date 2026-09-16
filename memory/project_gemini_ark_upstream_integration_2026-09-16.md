---
name: project_gemini_ark_upstream_integration_2026-09-16
description: GitHub上游39 commit的Gemini+Ark模型遷移大合併，含官方角色斷點修復與自動安全審查誤判查證
metadata:
  type: project
---

2026-09-16 完成 GitHub 上游 `Zwens/prismreel`（fork 自 `alibaba/lumenx`）main 分支 39 個 commit 的合併，核心是把 DashScope（Wan/Qwen/PixVerse/HappyHorse）整個下架，改用 Gemini（LLM/圖像/TTS）+ BytePlus Ark（Seedance）。

**合併前查證**：origin/main 本身沒有任何獨有於上游的 commit（兩邊共同祖先就是 origin/main HEAD），fast-forward 零衝突。7 條本地舊功能分支經 `git log origin/main..origin/<branch>` 核對全部 ahead=0，都已合併進 main，不是待整合內容——不要看到分支名稱陌生就假設是遺漏。

**已知斷點與修復**：上游把 `AssetPickerModal.tsx`（舊四tab架構）合併成 `AssetSourcePicker.tsx`（新四來源架構）時，「官方角色選擇」這個 tab 在兩條分支各自獨立開發、合流時漏接（上游 commit 訊息裡有留 TODO 說明）。移植方式：把官方角色當第五個 `AssetSource`，轉成通用 `PickerItem` 格式重用既有 grid/loading/選取邏輯，`toDisplayUrl()` 對 `asset://` 路徑改查 `officialCharacterCache`，並搬移舊版 `CharacterThumbnail`（IntersectionObserver 懶載入+失敗重試2次+文字卡片容錯）。TDD 全程：先寫3個新測試紅燈，實作後 13 個測試（10舊+3新）綠燈，全專案 338 個既有測試無迴歸。

**部署驗證鏈路**：GitLab CI push main → pipeline success ≠ 完成。`.gitlab-ci.yml` 的 `deploy_production` job 本身就是 rsync+`docker compose build/up`，pipeline success 代表部署動作已觸發，但容器重啟需要額外等穩定（`docker ps` 確認 `Up` 時間、`docker logs` 確認無崩潰重啟迴圈）才能算真正驗證完成。後端 17177 port 沒有對外映射（`docker port` 顯示 null），只能透過 nginx `proxy_pass http://backend:17177`（docker network 內部 hostname）或 live 網域驗證，直接 curl VPS `localhost:17177` 會得到 000，不代表後端掛了。

**自動安全審查誤判記錄**：這次推送後系統自動觸發的安全審查回報 `src/apps/playground/api.py` 有路徑穿越、存取控制缺失、資訊洩漏三項。查證後三項皆非真實問題：①該檔案路由函式個別未寫 `Depends(auth.require_login)`，但 `src/apps/comic_gen/api.py` 有全域 `enforce_login` middleware 攔截所有非 `_AUTH_PUBLIC_PREFIXES`（`/health`/`/files/`/`/static/`/`/docs`等）路徑的未登入請求，`/playground/*` 不在排除清單內，故有保護，只是不靠裝飾器實現；②`upload_media` 用 `uuid.uuid4()` 生成檔名而非使用者輸入，無路徑穿越風險；③這個鑑權模式（個別路由不寫 `Depends`，靠全域 middleware 兜底）是 origin/main 合併前既有架構，非這次合併引入。

**Why**：這是先前跟使用者確認「有些漏掉的東西」後，全面掃描 14 個被刪除檔案+比對關鍵表單同步+驗證模型遷移映射表後才動手的大整合，範圍包含 breaking change（DASHSCOPE_API_KEY 失效）。

**How to apply**：往後再有上游/第三方大批次合併，先用 `git merge-base` 確認真實 ahead/behind 關係再判斷是否有衝突；被刪除檔案清單逐一查有無殘留引用（`git grep` 確認乾淨移除 vs 斷鏈遺漏）；部署驗證不能只看 CI pipeline 狀態，要查容器重啟穩定性+log+live 端點三層；自動安全掃描的發現要先查該專案的鑑權架構全貌（全域 middleware vs 逐路由裝飾器）再判斷是否誤判，不要照單全收也不要照單忽略。
