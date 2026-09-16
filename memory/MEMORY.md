# PrismReel MEMORY Index

> 進入本專案工作時 Read 載入。工作區共用規則見根目錄 CLAUDE.md。

## GitHub上游整合
- [**✅ Gemini+Ark模型遷移大合併完成，含官方角色斷點修復+安全審查誤判查證（2026-09-16）**](project_gemini_ark_upstream_integration_2026-09-16.md) — DashScope全家族下架；官方角色tab移植進新AssetSourcePicker；部署驗證需CI success+容器穩定性+live三層；記錄鑑權全域middleware模式避免誤判

## 影片下載功能
- [**✅ 生成歷史列表頁下載按鈕fetch+blob阻塞主執行緒導致大影片下載卡死無提示（已修復並部署，2026-09-15）**](feedback_fetch_blob_download_blocks_main_thread_large_video_2026-09-15.md) — `ResultCard.tsx`改為與`DetailPanel.tsx`一致的原生`a href download`寫法；commit`7e8338e`已同步GitLab+GitHub並live驗證；排查時claude-in-chrome的javascript_tool內fetch回傳值與真實network log矛盾，以後者為準

## AI影片生成 API gotcha
- [**✅ 官方角色庫縮圖：全部問題已結案，480/480筆live驗證通過（2026-09-15第五輪最終結案）**](feedback_official_character_thumbnail_root_cause_no_virtualization_permanent_fallback_2026-09-15.md) — ①前端`AssetPickerModal.tsx`一次性渲染480個img+onError永久不重試已改IntersectionObserver+重試2次根治 ②30筆縮圖第一次抓取搜尋框卡死全抓成同一張圖，改用React fiber `item.SID`比對`group_id`修正，commit`c5db137` ③殘留3對(6筆)雜湊重複經搜尋框單次查詢+SHA-256雜湊比對確認是ModelArk資料庫本身重複記錄，非抓取錯誤，無需修復 ④額外發現30筆live 404是CF edge cache卡舊快照（源站早已正常），CF Dashboard Purge Everything後480/480全數複驗200通過
- [**🔴🔴 用ModelArk搜尋框抓取asset_id對應圖片前，必須驗證`fetch(url)`雜湊或完整src是否真變化，不能只看alt文字或單次截圖**](feedback_official_character_thumbnail_root_cause_no_virtualization_permanent_fallback_2026-09-15.md) — 搜尋框連續程式化輸入會卡死在第一次結果不刷新，`img.alt`殘留值會誤導判斷；改用React fiber讀`item.SID`比對`group_id`+滾動預設列表最可靠
- [**✅ Seedance官方Digital Character Library兩個回報問題已修復（2026-09-15）**](feedback_official_character_library_thumbnail_and_count_fix_2026-09-15.md) — ①第1張破圖根因是CF edge cache卡住部署前的404 ②角色庫遠不止60筆，重新滾動抓取拿到510筆並上線；已live驗證
- [**🔴 CF edge cache會卡住部署視窗內的404，源站已修好仍持續破圖**](feedback_cf_edge_cache_stale_404_during_deploy_window.md) — 判斷方法+CF Dashboard自訂清除SOP；排查「檔案明明存在卻404」優先比對此案例
- [**🔴 排查前端fallback UI「大量顯示假人icon」時，先確認fallback是否保留原`<img>`標籤**](feedback_official_character_thumbnail_root_cause_no_virtualization_permanent_fallback_2026-09-15.md) — `querySelectorAll('img')`統計會漏掉已onError切換成SVG的卡片，改用`button[title]`比對`querySelector('img')`有無存在才準確
- [**🔴 claude-in-chrome連續fetch+Blob下載2-3次後渲染器會凍結，需單張逐一執行**](feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15.md) — 根因未查證，僅找到迂迴解法；批量抓縮圖/附件時工具呼叫數與張數1:1，量大時先評估是否可行
- [**Seedance官方Digital Character Library整合技術參考**](reference_seedance_real_person_face_restriction_and_asset_library.md) — 不需企業認證的官方數位角色庫，asset://<asset_id>直通image_url.url、真實API呼叫已驗證成功生成影片；企業認證+自有虛構角色路徑仍待公司驗證中，見全文「已確認可行路徑」章節
- [**✅ Seedance多圖prompt引用語法：@Image1僅限Playground網頁UI，API呼叫需用`Image 1`格式（2026-09-14已修復並上線）**](reference_seedance_multi_image_prompt_reference_syntax.md) — 查證後發現後端無自動組裝邏輯，根因是前端PromptInput.tsx缺提示；已補UI提示三語言版本並驗證live bundle生效

## 圖片抓取踩坑（i2v首末幀 / R2V多圖標籤）
- [**✅ BytePlus/Ark首末幀本機檔案未接上provider_media半成品 + ShotCard.tsx三處精確比對重演assetTags.ts已修過的bug（已合併main並部署2026-09-11）**](feedback_byteplus_img_path_and_shotcard_exact_match_bugs_2026-09-11.md) — catalog已定義`byteplus_ark_image_url` mode但dispatch層從未實作；`resolveAssetByTagName`容錯函式只在一處被呼叫，其餘三處各自重寫精確比對
- [**✅ 同分支首版遺漏R2V的ref_image_urls，本機上傳圖片直送Ark造成400（已補修復並部署2026-09-11）**](feedback_r2v_ref_image_urls_bypassed_resolver_2026-09-11.md) — 2026-09-11使用者實測R2V生成400才發現；同一`generate()`函式內多個分支吃本機路徑時，修一處要順手查其他分支是否也漏；VPS容器重啟後已用3次live驗證確認本機路徑正確轉OSS簽名URL且可公開存取

## 部署機制（🔴 最重要，動手前必讀）
- [**✅ 2026-09-11起已改為 GitLab CI 自動部署：merge 到 main 才觸發**](feedback_gitlab_ci_auto_deploy_setup_2026-09-11.md) — 取代下方手動流程；VPS 上既有 shell-executor runner 直接 rsync+docker rebuild，push/merge 到非main分支不會動到 production
- [**（已過時，僅供歷史對照）舊手動部署流程：git push GitLab 不會自動部署，VPS 是手動複製非 git clone**](feedback_git_push_does_not_deploy_manual_vps_sync_required.md) — 2026-09-08首次踩坑；2026-09-11起已被上方CI取代，除非CI故障需要手動兜底才照此流程操作
- [**VPS lockfile 需在 node:20-alpine 容器內重新產生，本機 npm 版本不相容**](feedback_lockfile_must_regenerate_in_build_env_container.md) — 本機npm11 vs VPS build用npm10，package-lock.json 格式差異導致 npm ci 失敗
- [**🔴 VPS `.env` 與本機 `.env` 不會自動同步，新增環境變數需手動補到VPS**](feedback_vps_env_not_synced_with_local_env.md) — 2026-09-10 OSS設定本機有VPS沒有，後端靜默停用上傳功能且無錯誤提示
- [**🔴 nginx `client_max_body_size` 只設在location區塊不生效，需設在server層級**](feedback_nginx_client_max_body_size_location_level_ineffective.md) — 2026-09-10 2.8MB圖片一律413，實際套用的是http層級1MB預設值

## 專案基本資訊
- 產品：AI Comic Generator / PrismReel Studio，文字腳本→漫畫式短片產製平台
- 技術棧：Next.js 14 App Router 前端 + FastAPI 後端，Docker Compose 部署
- Live 站台：https://prismreel.soulo-ai.com （容器：prismreel-frontend / prismreel-backend）
- VPS：`vps_main`（202.182.117.182，SSH config 別名），部署目錄 `/opt/prismreel`
- 本機開發目錄：`AI 短片系統 Prismreel/`（也是一個獨立 git repo，remote origin 指向 GitLab `gjseo.qit1.net`，非 VPS 真正吃的來源）
- 桌面單機模式（`python main.py`）與 VPS 多用戶部署模式並存，改動時注意兩者行為差異

## 用量追蹤功能踩坑（✅ pipeline.py+Playground流程皆已合併main並上線，2026-09-12確認）
- [**🔴 用量追蹤只接了pipeline.py（漫畫生成），Playground完全沒有user_id/usage_events串接，發現時已誤記成「已完成並上線」**](feedback_usage_tracking_never_wired_into_playground_2026-09-11.md) — 2026-09-11使用者實測/usage頁面無數據才發現；根因鏈：`/generate`無auth依賴→`PlaygroundGeneration`無owner_id欄位→四個`_generate_video_*`丟棄model.generate()的usage回傳值→`usage_events`永遠0筆寫入；同一輪也補了生成前費用預估(Ark公式反推,誤差0.6%)+影片實際費用標記
- [**🔴 新增帶預設值的可選參數（如 user_id: Optional[str]=None）threading 到多個既有呼叫點時，最終全分支審查不可省略**](feedback_additive_param_default_silently_undermines_new_feature_across_call_sites.md) — 2026-09-11；per-task review全過，但3處呼叫點忘傳user_id、1處死參數，只有最終跨任務整合審查才抓得到
- [**✅ JWT_SECRET因import順序早於load_dotenv在乾淨環境會被快取成空值（已根治2026-09-11）+ usage_events表從未被自動建立（已補migration但呼叫點仍缺）**](feedback_jwt_secret_import_order_and_usage_events_table_missing.md) — 2026-09-11首次在乾淨worktree啟動時踩到；正式服務因系統環境變數兜底而未曾暴露；根治：`from . import auth, user_repo` 移到 `load_dotenv()` 之後
- [**🔴 跨session交接檔稱「已完整實作+curl驗證通過」不等於已commit**](feedback_handoff_claims_implemented_but_uncommitted_2026-09-11.md) — 2026-09-11接手時發現13個檔案仍是unstaged，功能行為是真的做了但從未進版控；接手先查git status/log，不先信文字敘述
- [**🔴 git merge commit存在於main歷史≠內容真的合併進main，需用`git merge-base --is-ancestor`+`git ls-tree`雙重驗證**](feedback_merge_commit_exists_but_content_not_ancestor_2026-09-11.md) — 2026-09-11 feature/usage-tracking的merge commit `8556704`在main歷史可見，但`git merge-base --is-ancestor`回NO、main檔案樹也確認缺usage_repo.py等檔案；只看`git log --graph`會被誤導
- [**🔴 清理測試殘留禁止`rm -rf output/`，output/底下混雜版控素材(presets/bgm)與執行期產物，需精確指定路徑如`output/auth.db`**](feedback_rm_rf_output_deletes_tracked_assets_2026-09-11.md) — 2026-09-11測試usage_repo時誤刪`output/presets/bgm/*`八個版控音樂素材檔案，靠`git status`發現+`git restore`救回，未造成實際損失但已達建記憶門檻

## i18n / 語言設定
- [**✅ 主要語言預設改為繁體中文（2026-09-11）**](feedback_default_locale_switched_to_traditional_chinese_2026-09-11.md) — settingsStore預設值+i18n fallback+html lang屬性三處同步；順手修正isCJK判斷原本只認簡體zh、繁體會誤判非CJK排版的既有bug（改用`!== "en"`）

## ✅ 多租戶登入系統（2026-09-11 已合併main並上線）
- [**登入系統實作進度交接（2026-09-08，歷史脈絡）**](project_auth_implementation_handoff_2026-09-08.md) — `feature/multi-tenant-auth`分支開發過程記錄；2026-09-11該分支+usage-tracking已一併merge進main並觸發CI自動部署，功能已live
- [**登入系統spec交接（已過時，見上方進度交接）**](project_auth_handoff.md) — spec本身已審閱通過，此檔僅保留spec歷史脈絡

## Playground 體驗直覺化改造（2026-09-10 完成）
- [**✅ Playground UX改造已完成（2026-09-10）**](project_playground_ux_overhaul_2026-09-10.md) — 兩份plan-review清單皆已實作+瀏覽器驗收通過：卡片選模式+雙狀態全寬工作區、Ark/Seedance Key表單缺口；OSS雲端儲存開通仍擱置未購買
- [**🔴 EnvConfigDialog.tsx 與 SettingsPage.tsx 是兩份平行環境設定表單，改欄位需兩處同步**](feedback_env_config_settings_duplicate_surfaces_must_sync.md) — 2026-09-10首次踩坑，交接記憶只判定其中一處缺欄位，另一處同樣缺但被漏查
- [**✅ i2v 首末幀模式+提示詞無上限+Image N編號徽章已完成並部署（2026-09-10）**](project_i2v_first_last_frame_2026-09-10.md) — Ark first_frame/last_frame/reference_image role三者互斥已驗證；OSS權限問題已於2026-09-10解決（見下方r2v上傳修復條目）
- [**✅ r2v上傳全鏈路修復：OSS未同步+bucket權限+nginx 413+縮圖UX（2026-09-10）**](project_r2v_upload_fix_2026-09-10.md) — 上傳從完全無反應到正常可用；根因OSS未配置→bucket權限→nginx body size限制三層依序排查；縮圖UI迭代4次定案96px+移除UUID檔名顯示
- [**🔴 上傳檔名是後端UUID非原始檔名，模型辨識多圖靠陣列順序非文字標籤**](feedback_upload_filename_is_backend_uuid_not_original.md) — 2026-09-10；前端顯示優化解決不了UUID本身無意義的問題，需改後端保留原始檔名才有效

## 多租戶登入系統操作
- [**🔴 邀請碼兌換入口是獨立`/redeem?code=`頁面，非登入頁**](feedback_invite_redeem_ui_location_unverified_wrong_guidance.md) — 2026-09-10首次踩坑，未查前端就講錯操作位置，被使用者當場糾正

## 🔴🔴 Line B 視覺重構（HANDOFF.md）＝上游歷史，非使用者授權（2026-09-16 核實）
- [**🔴🔴 HANDOFF.md「用戶已選定Line B」查證為誤判：Prismreel fork自alibaba/lumenx，該決策是上游作者歷史紀錄，使用者本人從未下達此需求**](project_prismreel_handoff_line_b_not_user_authorized.md) — git log作者比對揭穿；HANDOFF.md第6節下一步建議與待決策事項（資產庫二級篩選欄）一律不執行，已加註警示
- [**（技術SOP仍有效，任務前提已修正）Modal對齊Line B時登入頁擋截圖的處理方式**](feedback_ui_change_visual_verify_blocked_by_login_pattern_reuse_accepted_2026-09-16.md) — commit `b1b8297`+`31b2c38`+`16e0d88`已上線屬既成事實非回滾範圍；截圖SOP本身可參考，但不代表該任務是已授權需求

## 導覽命名重構（2026-09-12，解決ComicGen/Playground命名落差誤導）
- [**✅ 「資料遺失」誤判已結案：查證時混淆ComicGen(漫畫生成)與Playground(影片生成)兩條獨立產線**](feedback_output_data_loss_was_misdiagnosis_two_pipelines_confused_2026-09-12.md) — 2026-09-11判定的VPS資料遺失，2026-09-12重查證實Playground資料從未丟失，只是查錯路徑；已推動導覽重新命名根治
- [**✅ 工作區/資產庫/創作台重新命名為漫畫生成/素材庫/影片生成+新增獨立生成歷史分頁（feat/nav-rename-and-history-tab分支）**](feedback_output_data_loss_was_misdiagnosis_two_pipelines_confused_2026-09-12.md) — 生成歷史分頁直接重用PlaygroundPage的ResultGallery，跳過select/compose階段
- [**🔴 動工前未確認本機分支落後遠端main 67個commit，對著已被取代的舊版api.ts重複寫用量追蹤函式**](feedback_local_branch_67_commits_behind_before_editing_2026-09-12.md) — 修多人協作repo既有檔案前先`git fetch && git log HEAD..origin/main`核對落差
