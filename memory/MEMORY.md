# PrismReel MEMORY Index

> 進入本專案工作時 Read 載入。工作區共用規則見根目錄 CLAUDE.md。

## ✅ DeeVid Quality V4.0 provider整合+月度點數額度已merge進main（2026-09-22）
- [**✅ commit `1f78d74`已merge並push，8任務SDD計畫Task1-7完成，Task8（消耗真實額度的端到端驗收）使用者明確選擇跳過**](feedback_deevid_provider_integration_completed_2026-09-22.md) — 動工前查證推翻原始「Quality V4.7」假設，改用實際存在的「Quality V4.0」；殘留風險是真實API回應欄位從未經過submit round trip驗證
- [**🔴 push後自動安全審查揪出race condition+SSRF（2輪修復），commit `f562f73`已merge**](feedback_deevid_post_push_security_fixes_2026-09-22.md) — quota-bypass查證後判定誤報，但race condition/SSRF/redirect bypass/連線逾時遮蔽錯誤4項屬實；vidu.py/kling.py同款SSRF redirect bypass未修，待follow-up

## ✅ 多鏡頭工作流已merge進main並上線production（2026-09-18~09-19）
- [**✅ merge commit`94cd506`已推送GitLab+GitHub雙remote，CI job 46034成功，live三層驗證通過**](feedback_video_workflow_merge_to_main_and_deploy_2026-09-19.md) — 側欄「多鏡頭工作流」已上線；merge過程順手修main既有2個TypeScript型別錯誤（與merge無關）；GitHub push protection攔截舊commit明文金鑰（皆已確認失效），使用者手動解除後補推成功
- [**Task 10手動瀏覽器E2E完成，稽核官綜合判斷分支達可merge標準**](project_video_workflow_e2e_task10_completed_2026-09-19.md) — t2v+r2v雙圖生成真實驗證通過；combine因本機缺FFmpeg跳過肉眼複驗，已交叉確認VPS production容器內建FFmpeg不受影響
- [**交接記錄（歷史脈絡）：Critical bug/排序UI/37測試三項已通過**](project_video_workflow_independent_audit_handoff_2026-09-18.md) — 環境配置全域`.env`坑+登出重登Windows帳號釋放殭屍process的過程記錄
- [**🔴 全新worktree/全新環境`output/auth.db`無表導致503**](feedback_worktree_auth_db_never_initialized_on_fresh_env_2026-09-19.md) — `api.py`從未呼叫`auth_db.init_schema()`，本機開發限定坑，VPS早已建表不受影響（live production同樣存在此缺口，只是資料庫早已建表沒踩到）
- [**🔴 本機Windows缺FFmpeg導致合成端點500**](feedback_local_windows_missing_ffmpeg_blocks_concat_2026-09-19.md) — VPS容器內建FFmpeg已確認不受影響，純本機依賴缺口

## Library道具分類破圖（✅ 2026-09-17 已驗收完成，含既有壞資料backfill）
- [**✅ prop資產`image_url`誤存video路徑導致破圖，根因+新資料修復+既有壞資料backfill三階段全部完成**](feedback_library_asset_media_type_routing_and_backfill_2026-09-17.md) — 根因：`save_to_library()`未依`media_type`分流，一律寫入`image_url`；已修`service.py`/`pipeline.py`分流+前端`AssetLibraryPage.tsx`/`AssetInspector.tsx`補`<video>`fallback（commit`51341d6`，同commit修`feedback_library_video_asset_image_url_misroute_2026-09-17.md`）；唯一壞資料`prop_ac6600d4ef73`已手動backfill，**改`library_assets.json`後必須重啟prismreel-backend讓in-memory pipeline singleton重新讀檔**；live驗證DOM確認`<video>`正確渲染、`brokenImgCount:0`

## 照片上傳網格疊加功能（✅ 2026-09-18第五輪架構最終收斂；第一~四輪已搬archive）
- [**✅ 最終架構：所有內嵌上傳入口(video-gen多圖生成/首尾幀/Cast/StoryboardComposer/VideoCreator/T2ISubsection/UploadAssetModal/NewLibraryAssetDialog)移除GridOverlayPicker並固定送原圖，網格燒錄統一收斂到「圖片生成›燒入網格」獨立卡片(GridBurnCard.tsx)，DanceSwapWizard維持原樣不動**](feedback_grid_overlay_removed_from_inline_entries_2026-09-18.md) — commit`e678bce`；🔴附帶教訓：使用者可見功能改動要同步bump`APP_VERSION`（三處硬編碼：GlobalSidebar/SettingsPage/UpdateChecker）並版控，勿只改功能程式碼；第一~四輪演進歷史（原圖/4×4/5×5可選、燒圖時機延後又撤銷等）已搬[archive](archive/2026-09-completed-early.md)
- [**✅ GridBurnCard.tsx（唯一燒圖入口）改回「上傳前先選樣式、上傳當下一次性燒入」，撤銷「先傳原圖再獨立按鈕套用」方案**](feedback_grid_burn_card_oss_upload_apply_grid_404_2026-09-18.md) — 根因：走`/library/assets/upload`(comic_gen路由)，`OSS_ENABLE=true`回傳OSS URL，事後呼叫`/playground/apply-grid`對OSS URL必404（該端點只認本機`output/`路徑）；comic_gen路由整體沒有「對已上傳圖片事後燒網格」端點；🔴查既有memory時搜API路由字串比搜元件名更能命中同一條架構限制

## MediaInput.tsx本地上傳還原 + 環境配置誤操作事故（✅ 2026-09-18）
- [**✅ f654d25誤把本地拖檔上傳整個拿掉，peer交接後核實範圍並還原；本地上傳與資產庫選取並存**](feedback_media_input_upload_removed_beyond_user_intent_2026-09-18.md) — 動手前查git log+plan文件發現交接轉述與原始commit意圖有落差，AskUserQuestion核實後確認使用者確實要加回本地上傳；typecheck+既有單元測試綠燈，瀏覽器視覺驗收因下一條事故中止；⚠️文中「網格燒入維持選圖當下立即燒」一句已被[[feedback_grid_overlay_removed_from_inline_entries_2026-09-18]]取代（燒入選項本身已從此入口移除，不再適用）
- [**🔴🔴 「環境配置」彈窗POST的是全域`.env`非per-account，用假key跨過必填彈窗覆寫了使用者真實GEMINI_API_KEY且無git版控可復原**](feedback_env_config_dialog_writes_global_env_not_per_account_2026-09-18.md) — 任何「設定/配置」類UI表單，動手填測試值前必先查該端點實際寫入目的地（per-user還是共用檔案）；事故後已通知全部5個並行session
- [**🔴🔴 同一個坑在獨立worktree場景重演：誤把「全域.env」當成worktree間process衝突排查30+分鐘**](feedback_env_config_global_env_gotcha_recurred_worktree_2026-09-18.md) — 2026-09-18 video-workflow稽核案；踩到卡點時務必先Grep專案memory再展開技術排查，不要把已知架構限制當新bug深挖
- [**🔴🔴 使用者說「多圖生成/影生影沒有上傳」，未grep i18n key就假設是storyboard-r2v分鏡工作流改錯檔案push上線；真正目標是Playground的MediaInput.tsx；驗證過程意外揪出useCallback宣告在條件式early return之後的真實hooks-order bug（已修，commit`6bf9ad7`）**](feedback_ui_label_must_grep_i18n_before_assuming_target_file_2026-09-18.md) — 使用者引用具體UI文字/方括號標籤時先grep messages/*.json反查i18n key，不要憑術語聯想；多套並行系統共用同一技術詞彙（本案「R2V」）時尤其不可假設

## 導覽拆分：影片生成/圖片生成獨立入口（✅ 2026-09-18，三session協作完成）
- [**✅ 左側導覽從6項改5項，`#/ai-video`廢棄併入「影片生成」5tab直開；「圖片生成」新增燒入網格卡片；VideoGenPage/ImageGenPage各自獨立store**](feedback_nav_reorg_video_image_gen_split_2026-09-18.md) — commit`9fa3884`，pipeline #45782通過，live驗證全通過；測試遷移教訓（storeWiring/emptyMode需改用Provider注入店例）+vitest雙config(`test`只跑node環境/`test:ui`才跑DOM測試)+多session協作檔案覆蓋教訓，詳見全文

## 真人換裝舞蹈功能修復全紀錄（✅ 2026-09-17雙session獨立驗證通過；2026-09-16那輪8個commit已驗收完成）
- [**✅ 三視圖生成人物/服裝角色混淆修復（已部署）+ compose步驟新增Seedance 2.0/2.5模型選擇（已部署，2.0效果未驗證待使用者實測）**](feedback_dance_swap_multi_ref_image_role_confusion_and_model_choice_2026-09-17.md) — commit`012572c`+`4372925`；根因是系統代寫prompt送多張參考圖卻沒指名角色，模型自行選錯主體且正常計費不報錯，難以被動察覺；2.0 v2v是否真能用參考影片驅動動作從未實測，廠商後台聲稱支援但官方文件與程式碼註解證實2.0會拒絕task_type欄位
- [**✅ 2026-09-17：AI影片頁滾軸+真人換裝舞蹈三視圖勾選，兩個修復commit經雙session各自獨立驗證（VPS原始碼+容器版本+瀏覽器實測）皆確認正常**](feedback_asset_source_picker_exit_animation_blocks_clicks_2026-09-16.md) — 使用者曾回報「未發現問題」，已排除代碼/部署問題，懸案歸因使用者端瀏覽器快取，已請對方強制重新整理+附證據；見檔案末段「雙session獨立驗證通過」章節
- [**✅ 2026-09-17：pickSheet素材庫選圖未燒網格+Seedance/Ark不支援negative_prompt導致排除checkbox形同虛設，兩缺口皆修復**](feedback_dance_swap_pickSheet_and_seedance_negative_prompt_gap_2026-09-17.md) — commit`65d4f3a`+`a76fa95`；更正`feedback_grid_overlay_three_defects_ai_gen_dance_negative_prompt_2026-09-17.md`的「已修復」結論；教訓：UI狀態存在≠下游API真的接收該值，跨模型家族prompt功能每條路徑要重新確認該模型實際支援的欄位
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

## ✅ 多租戶登入系統（2026-09-11 已合併main並上線）
- [**登入系統實作進度交接（2026-09-08，歷史脈絡）**](project_auth_implementation_handoff_2026-09-08.md) — `feature/multi-tenant-auth`分支開發過程記錄；2026-09-11該分支+usage-tracking已一併merge進main並觸發CI自動部署，功能已live；spec歷史交接已搬[archive](archive/2026-09-completed-early.md)

## 歸檔
- [**2026-09-10~09-17已完結舊條目**](archive/2026-09-completed-early.md) — 圖片抓取踩坑(i2v/R2V)、i18n語言設定、多租戶登入系統操作、Playground體驗直覺化改造、官方角色庫縮圖、用量追蹤功能、影片下載功能、導覽命名重構第一輪、多session交接過期快照，皆✅完結非常駐必讀

## 🔴🔴 Line B 視覺重構（HANDOFF.md）＝上游歷史，非使用者授權（2026-09-16 核實）
- [**🔴🔴 HANDOFF.md「用戶已選定Line B」查證為誤判：Prismreel fork自alibaba/lumenx，該決策是上游作者歷史紀錄，使用者本人從未下達此需求**](project_prismreel_handoff_line_b_not_user_authorized.md) — git log作者比對揭穿；HANDOFF.md第6節下一步建議與待決策事項（資產庫二級篩選欄）一律不執行，已加註警示
- [**（技術SOP仍有效，任務前提已修正）Modal對齊Line B時登入頁擋截圖的處理方式**](feedback_ui_change_visual_verify_blocked_by_login_pattern_reuse_accepted_2026-09-16.md) — commit `b1b8297`+`31b2c38`+`16e0d88`已上線屬既成事實非回滾範圍；截圖SOP本身可參考，但不代表該任務是已授權需求

## 導覽命名重構延續（2026-09-17，第一輪已搬archive）
- [**🔴 「AI影片頁面」對應AiVideoPage.tsx(#/ai-video)，非PlaygroundPage.tsx(#/playground創作台)，兩者外觀高度相似**](feedback_ai_video_page_vs_playground_page_route_confusion_2026-09-17.md) — 2026-09-17首次改錯檔案push+CI後才發現；動手前先grep page.tsx確認路由對應元件

## 舞蹈換裝上傳驗證+存檔回饋修復（✅ 2026-09-17 跨session補做live驗收完成）
- [**✅ DanceSwapWizard.tsx兩個UX缺口已修並live驗證：圖片上傳收斂jpg/jpeg/png+副檔名不符跳toast擋下（已實測.gif被擋且跳繁中toast）；SaveToLibrary原本fire-and-forget無回饋，改saving/saved/error三態+toast成功失敗提示（同commit部署已確認生效，轉場動畫本身未逐一實測）**](feedback_dance_swap_upload_ext_validation_and_save_toast_2026-09-17.md) — commit`a77a3da`
- [**✅ DanceSwapWizard網格疊加按鈕簡體字已確認並非快取問題，是commit`a0e3c2e`只commit沒push所致，已補推並live驗證繁體生效**](feedback_simplified_chinese_ui_cleanup_and_unpushed_commit_2026-09-17.md) — 詳見全文「commit了沒push」排查方法論
- [**✅ 程式碼註解簡體字清理（59交接待辦）已完成：前端src全部53個乾淨檔案（排除當時5f正在改的4個網格疊加相關檔案）opencc轉換+typecheck/lint交叉驗證無新增錯誤**](feedback_opencc_s2t_leaves_variant_character_爲_2026-09-17.md) — commit`2b11692`已push；opencc s2t會殘留「爲」異體字需額外正規化為「為」，詳見全文
- [**✅ VPS `.env`洩漏的Gemini API Key事件已收尾：換新key+重啟+應用層真實LLM呼叫驗證通過**](feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16.md) — 2026-09-17；使用者Google帳號權限只能刪除不能單純revoke，且顧慮刪除會讓Console用量儀表板依key切分的歷史統計失真，故未強制刪除舊key，改採新key頂替；全程SSH `sed -i`原地替換.env，未落地明文到任何本機檔案/memory；`docker compose restart backend`+容器內`LLMAdapter().chat()`真實呼叫拿到`OK`確認生效
- [**🔴 已建`.git/hooks/pre-commit`機械掃描攔截明文API key格式字串，防止memory檔案再度洩漏金鑰**](feedback_pre_commit_hook_blocks_plaintext_keys_2026-09-17.md) — 已用假金鑰實測攔截成功；⚠️限制：hook不受版控，只保護本機這個工作目錄，不會自動同步給其他clone/session
- [**🔴 本機同時啟動前後端才能開發除錯：前端真實port是3008非3000，後端`npm run dev:backend`(uvicorn 17177)沒開會被「環境配置」強制彈窗鎖死無法關閉**](feedback_dance_swap_upload_ext_validation_and_save_toast_2026-09-17.md) — 2026-09-17首次踩坑；uvicorn`--reload`監督行程被強殺後可能留下`Get-Process`/`tasklist`都查不到PID但socket仍真實回應(200)的孤兒行程，多次嘗試清理無效時不必死磕，純本機開發用途可留待重開機釋放
