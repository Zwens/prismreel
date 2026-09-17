# PrismReel MEMORY Index

> 進入本專案工作時 Read 載入。工作區共用規則見根目錄 CLAUDE.md。

## Library道具分類破圖（✅ 2026-09-17 已驗收完成，含既有壞資料backfill）
- [**✅ prop資產`image_url`誤存video路徑導致破圖，根因+新資料修復+既有壞資料backfill三階段全部完成**](feedback_library_asset_media_type_routing_and_backfill_2026-09-17.md) — 根因：`save_to_library()`未依`media_type`分流，一律寫入`image_url`；已修`service.py`/`pipeline.py`分流+前端`AssetLibraryPage.tsx`/`AssetInspector.tsx`補`<video>`fallback（commit`51341d6`，同commit修`feedback_library_video_asset_image_url_misroute_2026-09-17.md`）；唯一壞資料`prop_ac6600d4ef73`已手動backfill，**改`library_assets.json`後必須重啟prismreel-backend讓in-memory pipeline singleton重新讀檔**；live驗證DOM確認`<video>`正確渲染、`brokenImgCount:0`

## 照片上傳網格疊加功能（✅ 2026-09-17 上傳端+AI生成+DanceSwapWizard三缺陷全部修復完成部署驗證）
- [**✅ 使用者上傳照片可選原圖/4×4/5×5永久疊加網格輔助AI辨識比例構圖，6個上傳端點+前端共用選擇器全部接好並live像素驗證通過**](feedback_grid_overlay_upload_feature_2026-09-17.md) — commit`d89c0f8`；`apply_grid_overlay`後端純函式+`GridOverlayPicker.tsx`前端共用元件；上傳端點盤點踩坑（函式名不能當真照片上傳判準）+混合accept類型陷阱，詳見全文；**⚠️注意：該條「已完成部署驗證」結論僅涵蓋上傳路徑，AI生成/DanceSwapWizard當時未涵蓋，見下條**
- [**✅ 三個功能性缺陷修復：AI生成/素材庫選擇不套網格、prompt未注入辨識引導文字、DanceSwapWizard排除網格checkbox缺失**](feedback_grid_overlay_three_defects_ai_gen_dance_negative_prompt_2026-09-17.md) — commit`20f50b5`；新增後端`POST /playground/apply-grid`+`GRID_OVERLAY_GUIDANCE_PROMPT`正向prompt常數+DanceSwapWizard本地state版排除checkbox；用真實AI生成live驗證通過，含Monitor輪詢判定「檔案存在」誤判為「本次生成完成」的假陰性教訓
- [**✅ 既有素材庫照片backfill補套用5×5網格已完成（跨session交接）**](feedback_grid_overlay_backfill_existing_library_photos_2026-09-17.md) — 理論資料模型三代legacy欄位並存，實測production資料只有2張圖需處理（其餘全空值）；backfill前務必先唯讀盤點實際資料量再估工作量，不要只憑model定義推算

## 真人換裝舞蹈功能修復全紀錄（✅ 2026-09-17雙session獨立驗證通過；2026-09-16那輪8個commit已驗收完成）
- [**✅ 2026-09-17：AI影片頁滾軸+真人換裝舞蹈三視圖勾選，兩個修復commit經雙session各自獨立驗證（VPS原始碼+容器版本+瀏覽器實測）皆確認正常**](feedback_asset_source_picker_exit_animation_blocks_clicks_2026-09-16.md) — 使用者曾回報「未發現問題」，已排除代碼/部署問題，懸案歸因使用者端瀏覽器快取，已請對方強制重新整理+附證據；見檔案末段「雙session獨立驗證通過」章節
- ✅ 第一輪三個commit(54c35a3/57ba767/be41788)：素材庫破圖mediaUrl修復+Step1上傳/生成二選一+Step1/Step2「從素材庫選擇」按鈕。「從素材庫選擇」按鈕僅存在於「我已有三視圖」分頁、非「AI生成」分頁，屬既定設計非缺漏（見DanceSwapWizard.tsx）
- [**✅ 問題3/5根因：AssetSourcePicker退場動畫卡住時overlay仍pointerEvents:auto持續攔截點擊**](feedback_asset_source_picker_exit_animation_blocks_clicks_2026-09-16.md) — commit`cdd4d77`；variants加`pointerEvents:'none'/'auto'`隨hidden/visible狀態立即切換，不等exit動畫跑完；live驗收用`document.elementFromPoint`命中真實checkbox+`.click()`觸發checked切換
- [**✅ 問題2/4：Step3新增比例(9:16/16:9/1:1/3:4/4:3/adaptive)+秒數(4-30s)控制項**](feedback_asset_source_picker_exit_animation_blocks_clicks_2026-09-16.md) — commit`c6179ac`；依`docs/api-reference/byteplus-ark-seedance-seedream.md`第2.4節確認`task_type:'reference'`無ratio/duration約束才放開自訂，避開edit/extend強制adaptive/-1限制
- [**🔴 驗證React state時，`findHookState`遍歷memoizedState可能抓到過期fiber snapshot，改讀`element[__reactProps$xxx].value`才準確**](feedback_asset_source_picker_exit_animation_blocks_clicks_2026-09-16.md) — 排查duration輸入時一度誤判為bug，改用reactProps驗證後確認實際正常
- 問題1（選定感受）已排除非缺陷；跨session協作記錄（claude-wmzic-6c互相驗收機制）見全文

## GitHub上游整合
- [**✅ Gemini+Ark模型遷移大合併完成，含官方角色斷點修復+安全審查誤判查證（2026-09-16）**](project_gemini_ark_upstream_integration_2026-09-16.md) — DashScope全家族下架；官方角色tab移植進新AssetSourcePicker；部署驗證需CI success+容器穩定性+live三層；記錄鑑權全域middleware模式避免誤判
- [**✅ VPS憑證缺口已補齊：GEMINI_API_KEY寫入+OPENAI_API_KEY清空+LLM_PROVIDER改gemini，容器內真實LLM呼叫驗證成功（2026-09-16）**](feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16.md) — 過程中意外揪出更深層問題見下一條；圖像生成/TTS套件已補齊但未逐一實測
- [**🔴 requirements-docker.txt漏同步openai/numpy/pillow/soundfile，容器LLMAdapter完全不能用（已修復，2026-09-16）**](feedback_requirements_docker_missing_ai_ml_deps_2026-09-16.md) — 容器用requirements-docker.txt非requirements.txt，上游遷移時新增依賴只進了後者；已補齊必要4項（排除torch等GPU-only桌面應用專屬套件），commit`5e6d8de`推送觸發CI build+驗證通過
- [**🔴 CI用`rsync -a --delete`部署，VPS上手動建立的`.bak`備份檔會在下次CI部署時被清掉**](feedback_ci_rsync_delete_wipes_manual_backup_files_on_vps.md) — exclude清單只涵蓋`.env`/`output/`等固定路徑；改VPS檔案前備份不可靠，優先走本機git commit流程留痕

## 影片下載功能
- [**✅ 生成歷史列表頁下載按鈕fetch+blob阻塞主執行緒導致大影片下載卡死無提示（已修復並部署，2026-09-15）**](feedback_fetch_blob_download_blocks_main_thread_large_video_2026-09-15.md) — `ResultCard.tsx`改為與`DetailPanel.tsx`一致的原生`a href download`寫法；commit`7e8338e`已同步GitLab+GitHub並live驗證；排查時claude-in-chrome的javascript_tool內fetch回傳值與真實network log矛盾，以後者為準

## Library素材庫 gotcha
- [**✅ save_to_library()未依media_type分流，video輸出(dance換裝)硬塞image_url造成破圖，已修復部署+舊資料backfill（2026-09-17）**](feedback_library_video_asset_image_url_misroute_2026-09-17.md) — commit`51341d6`；Prop model原生已有video_url欄位但create_library_asset()從未填入；前端AssetLibraryPage/AssetInspector補<video>fallback；改library_assets.json這類pipeline singleton持久化檔須配docker restart才生效

## AI影片生成 API gotcha
- [**🔴 CF edge cache會卡住部署視窗內的404，源站已修好仍持續破圖**](feedback_cf_edge_cache_stale_404_during_deploy_window.md) — 判斷方法+CF Dashboard自訂清除SOP；排查「檔案明明存在卻404」優先比對此案例
- [**🔴 claude-in-chrome連續fetch+Blob下載2-3次後渲染器會凍結，需單張逐一執行**](feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15.md) — 根因未查證，僅找到迂迴解法；批量抓縮圖/附件時工具呼叫數與張數1:1，量大時先評估是否可行
- [**Seedance官方Digital Character Library整合技術參考**](reference_seedance_real_person_face_restriction_and_asset_library.md) — 不需企業認證的官方數位角色庫，asset://<asset_id>直通image_url.url、真實API呼叫已驗證成功生成影片；企業認證+自有虛構角色路徑仍待公司驗證中，見全文「已確認可行路徑」章節
- [**✅ Seedance多圖prompt引用語法：@Image1僅限Playground網頁UI，API呼叫需用`Image 1`格式（2026-09-14已修復並上線）**](reference_seedance_multi_image_prompt_reference_syntax.md) — 查證後發現後端無自動組裝邏輯，根因是前端PromptInput.tsx缺提示；已補UI提示三語言版本並驗證live bundle生效

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

## ✅ 多租戶登入系統（2026-09-11 已合併main並上線）
- [**登入系統實作進度交接（2026-09-08，歷史脈絡）**](project_auth_implementation_handoff_2026-09-08.md) — `feature/multi-tenant-auth`分支開發過程記錄；2026-09-11該分支+usage-tracking已一併merge進main並觸發CI自動部署，功能已live
- [**登入系統spec交接（已過時，見上方進度交接）**](project_auth_handoff.md) — spec本身已審閱通過，此檔僅保留spec歷史脈絡

## 歸檔
- [**2026-09-10~09-15已完結舊條目**](archive/2026-09-completed-early.md) — 圖片抓取踩坑(i2v/R2V)、i18n語言設定、多租戶登入系統操作、Playground體驗直覺化改造、官方角色庫縮圖、用量追蹤功能，皆✅完結非常駐必讀

## 🔴🔴 Line B 視覺重構（HANDOFF.md）＝上游歷史，非使用者授權（2026-09-16 核實）
- [**🔴🔴 HANDOFF.md「用戶已選定Line B」查證為誤判：Prismreel fork自alibaba/lumenx，該決策是上游作者歷史紀錄，使用者本人從未下達此需求**](project_prismreel_handoff_line_b_not_user_authorized.md) — git log作者比對揭穿；HANDOFF.md第6節下一步建議與待決策事項（資產庫二級篩選欄）一律不執行，已加註警示
- [**（技術SOP仍有效，任務前提已修正）Modal對齊Line B時登入頁擋截圖的處理方式**](feedback_ui_change_visual_verify_blocked_by_login_pattern_reuse_accepted_2026-09-16.md) — commit `b1b8297`+`31b2c38`+`16e0d88`已上線屬既成事實非回滾範圍；截圖SOP本身可參考，但不代表該任務是已授權需求

## 導覽命名重構（2026-09-12，解決ComicGen/Playground命名落差誤導）
- [**✅ 「資料遺失」誤判已結案：查證時混淆ComicGen(漫畫生成)與Playground(影片生成)兩條獨立產線**](feedback_output_data_loss_was_misdiagnosis_two_pipelines_confused_2026-09-12.md) — 2026-09-11判定的VPS資料遺失，2026-09-12重查證實Playground資料從未丟失，只是查錯路徑；已推動導覽重新命名根治
- [**✅ 工作區/資產庫/創作台重新命名為漫畫生成/素材庫/影片生成+新增獨立生成歷史分頁（feat/nav-rename-and-history-tab分支）**](feedback_output_data_loss_was_misdiagnosis_two_pipelines_confused_2026-09-12.md) — 生成歷史分頁直接重用PlaygroundPage的ResultGallery，跳過select/compose階段
- [**🔴 動工前未確認本機分支落後遠端main 67個commit，對著已被取代的舊版api.ts重複寫用量追蹤函式**](feedback_local_branch_67_commits_behind_before_editing_2026-09-12.md) — 修多人協作repo既有檔案前先`git fetch && git log HEAD..origin/main`核對落差
- [**🔴 「AI影片頁面」對應AiVideoPage.tsx(#/ai-video)，非PlaygroundPage.tsx(#/playground創作台)，兩者外觀高度相似**](feedback_ai_video_page_vs_playground_page_route_confusion_2026-09-17.md) — 2026-09-17首次改錯檔案push+CI後才發現；動手前先grep page.tsx確認路由對應元件

## 🔴 2026-09-17多session並行協作交接（新session開場必讀）
- [**🔴🔴 當日四個peer session分工狀態總覽：claude-wmzic-5f正在修網格疊加三缺陷（本session接手時仍busy，動手前務必ListAgents+git status雙重確認排除其未提交檔案）**](project_multi_session_handoff_2026-09-17.md) — 簡體字清理待辦已由本session完成（見上方commit`2b11692`）；5f的網格疊加修復狀態需新session自行重新查證，不沿用本記錄的「進行中」snapshot

## 舞蹈換裝上傳驗證+存檔回饋修復（✅ 2026-09-17 跨session補做live驗收完成）
- [**✅ DanceSwapWizard.tsx兩個UX缺口已修並live驗證：圖片上傳收斂jpg/jpeg/png+副檔名不符跳toast擋下（已實測.gif被擋且跳繁中toast）；SaveToLibrary原本fire-and-forget無回饋，改saving/saved/error三態+toast成功失敗提示（同commit部署已確認生效，轉場動畫本身未逐一實測）**](feedback_dance_swap_upload_ext_validation_and_save_toast_2026-09-17.md) — commit`a77a3da`
- [**✅ DanceSwapWizard網格疊加按鈕簡體字已確認並非快取問題，是commit`a0e3c2e`只commit沒push所致，已補推並live驗證繁體生效**](feedback_simplified_chinese_ui_cleanup_and_unpushed_commit_2026-09-17.md) — 詳見全文「commit了沒push」排查方法論
- [**✅ 程式碼註解簡體字清理（59交接待辦）已完成：前端src全部53個乾淨檔案（排除當時5f正在改的4個網格疊加相關檔案）opencc轉換+typecheck/lint交叉驗證無新增錯誤**](feedback_opencc_s2t_leaves_variant_character_爲_2026-09-17.md) — commit`2b11692`已push；opencc s2t會殘留「爲」異體字需額外正規化為「為」，詳見全文
- [**✅ VPS `.env`洩漏的Gemini API Key事件已收尾：換新key+重啟+應用層真實LLM呼叫驗證通過**](feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16.md) — 2026-09-17；使用者Google帳號權限只能刪除不能單純revoke，且顧慮刪除會讓Console用量儀表板依key切分的歷史統計失真，故未強制刪除舊key，改採新key頂替；全程SSH `sed -i`原地替換.env，未落地明文到任何本機檔案/memory；`docker compose restart backend`+容器內`LLMAdapter().chat()`真實呼叫拿到`OK`確認生效
- [**🔴 已建`.git/hooks/pre-commit`機械掃描攔截明文API key格式字串，防止memory檔案再度洩漏金鑰**](feedback_pre_commit_hook_blocks_plaintext_keys_2026-09-17.md) — 已用假金鑰實測攔截成功；⚠️限制：hook不受版控，只保護本機這個工作目錄，不會自動同步給其他clone/session
- [**🔴 本機同時啟動前後端才能開發除錯：前端真實port是3008非3000，後端`npm run dev:backend`(uvicorn 17177)沒開會被「環境配置」強制彈窗鎖死無法關閉**](feedback_dance_swap_upload_ext_validation_and_save_toast_2026-09-17.md) — 2026-09-17首次踩坑；uvicorn`--reload`監督行程被強殺後可能留下`Get-Process`/`tasklist`都查不到PID但socket仍真實回應(200)的孤兒行程，多次嘗試清理無效時不必死磕，純本機開發用途可留待重開機釋放
