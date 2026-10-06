# PrismReel MEMORY Index

> 進入本專案工作時 Read 載入。工作區共用規則見根目錄 CLAUDE.md。

## GitHub上游整合
- [**✅ Gemini+Ark模型遷移大合併完成，含官方角色斷點修復+安全審查誤判查證（2026-09-16）**](project_gemini_ark_upstream_integration_2026-09-16.md) — DashScope全家族下架；官方角色tab移植進新AssetSourcePicker；部署驗證需CI success+容器穩定性+live三層；記錄鑑權全域middleware模式避免誤判
- [**✅ VPS憑證缺口已補齊：GEMINI_API_KEY寫入+OPENAI_API_KEY清空+LLM_PROVIDER改gemini，容器內真實LLM呼叫驗證成功（2026-09-16）**](feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16.md) — 過程中意外揪出更深層問題見下一條；圖像生成/TTS套件已補齊但未逐一實測
- [**🔴 requirements-docker.txt漏同步openai/numpy/pillow/soundfile，容器LLMAdapter完全不能用（已修復，2026-09-16）**](feedback_requirements_docker_missing_ai_ml_deps_2026-09-16.md) — 容器用requirements-docker.txt非requirements.txt，上游遷移時新增依賴只進了後者；已補齊必要4項（排除torch等GPU-only桌面應用專屬套件），commit`5e6d8de`推送觸發CI build+驗證通過
- [**🔴 CI用`rsync -a --delete`部署，VPS上手動建立的`.bak`備份檔會在下次CI部署時被清掉**](feedback_ci_rsync_delete_wipes_manual_backup_files_on_vps.md) — exclude清單只涵蓋`.env`/`output/`等固定路徑；改VPS檔案前備份不可靠，優先走本機git commit流程留痕

## Library素材庫 gotcha
- [**✅ save_to_library()未依media_type分流，video輸出(dance換裝)硬塞image_url造成破圖，已修復部署+舊資料backfill（2026-09-17）**](feedback_library_video_asset_image_url_misroute_2026-09-17.md) — commit`51341d6`；Prop model原生已有video_url欄位但create_library_asset()從未填入；前端AssetLibraryPage/AssetInspector補<video>fallback；改library_assets.json這類pipeline singleton持久化檔須配docker restart才生效

## AI影片生成 API gotcha
- [**🔴 新增影片生成provider除了model catalog YAML+adapter+service.py dispatch，還要碰provider_media.py的硬編碼白名單**](feedback_new_video_provider_must_register_provider_media_dispatch_2026-09-21.md) — 2026-09-21 DeeVid整合規劃時發現；`_resolve_vendor_url_mode()`對mode字串是寫死if/elif判斷，只註冊provider_registry.py的family不夠，沒補分支會拋`Unsupported provider media input mode`
- [**🔴 CF edge cache會卡住部署視窗內的404，源站已修好仍持續破圖**](feedback_cf_edge_cache_stale_404_during_deploy_window.md) — 判斷方法+CF Dashboard自訂清除SOP；排查「檔案明明存在卻404」優先比對此案例
- [**🔴 claude-in-chrome連續fetch+Blob下載2-3次後渲染器會凍結，需單張逐一執行**](feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15.md) — 根因未查證，僅找到迂迴解法；批量抓縮圖/附件時工具呼叫數與張數1:1，量大時先評估是否可行
- [**Seedance官方Digital Character Library整合技術參考**](reference_seedance_real_person_face_restriction_and_asset_library.md) — 不需企業認證的官方數位角色庫，asset://<asset_id>直通image_url.url、真實API呼叫已驗證成功生成影片；企業認證+自有虛構角色路徑仍待公司驗證中，見全文「已確認可行路徑」章節
- [**✅ Seedance多圖prompt引用語法：@Image1僅限Playground網頁UI，API呼叫需用`Image 1`格式（2026-09-14已修復並上線）**](reference_seedance_multi_image_prompt_reference_syntax.md) — 查證後發現後端無自動組裝邏輯，根因是前端PromptInput.tsx缺提示；已補UI提示三語言版本並驗證live bundle生效

## 部署機制（🔴 最重要，動手前必讀）
- [**✅ 2026-09-11起已改為 GitLab CI 自動部署：merge 到 main 才觸發**](feedback_gitlab_ci_auto_deploy_setup_2026-09-11.md) — VPS 上既有 shell-executor runner 直接 rsync+docker rebuild，push/merge 到非main分支不會動到 production；舊手動部署流程已搬[archive](archive/2026-09-completed-early.md)
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

## 歸檔
- [**2026-09-10~09-17已完結舊條目**](archive/2026-09-completed-early.md) — 圖片抓取踩坑(i2v/R2V)、i18n語言設定、多租戶登入系統操作、Playground體驗直覺化改造、官方角色庫縮圖、用量追蹤功能、影片下載功能、導覽命名重構第一輪、多session交接過期快照，皆✅完結非常駐必讀

## 🔴🔴 Line B 視覺重構（HANDOFF.md）＝上游歷史，非使用者授權（2026-09-16 核實）
- [**🔴🔴 HANDOFF.md「用戶已選定Line B」查證為誤判：Prismreel fork自alibaba/lumenx，該決策是上游作者歷史紀錄，使用者本人從未下達此需求**](project_prismreel_handoff_line_b_not_user_authorized.md) — git log作者比對揭穿；HANDOFF.md第6節下一步建議與待決策事項（資產庫二級篩選欄）一律不執行，已加註警示
- [**（技術SOP仍有效，任務前提已修正）Modal對齊Line B時登入頁擋截圖的處理方式**](feedback_ui_change_visual_verify_blocked_by_login_pattern_reuse_accepted_2026-09-16.md) — commit `b1b8297`+`31b2c38`+`16e0d88`已上線屬既成事實非回滾範圍；截圖SOP本身可參考，但不代表該任務是已授權需求

## 導覽命名重構延續（2026-09-17，第一輪已搬archive）
- [**🔴 「AI影片頁面」對應AiVideoPage.tsx(#/ai-video)，非PlaygroundPage.tsx(#/playground創作台)，兩者外觀高度相似**](feedback_ai_video_page_vs_playground_page_route_confusion_2026-09-17.md) — 2026-09-17首次改錯檔案push+CI後才發現；動手前先grep page.tsx確認路由對應元件


## 歸檔（2026-09-30 瘦身）
- [**已完成段落 9 個**](MEMORY-archive-2026-09-30.md) — 已完成且無後續依賴，需查細節時Read
## 舞蹈換裝真人審核（2026-10-06）
- [**🔴 舞蹈換裝失敗先查VPS playground_history.json的error欄；素材庫≠BytePlus肖像庫，需填asset ID走asset://（b409298，待實測）**](feedback_dance_swap_real_face_needs_byteplus_asset_id_2026-10-06.md)
