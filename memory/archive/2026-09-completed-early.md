# PrismReel 已完結舊條目歸檔（2026-09-10~09-11，搬移於2026-09-17瘦身）

> 以下條目皆已✅完結、非常駐必讀規則，從主索引搬出以控制檔案大小。技術細節仍在各自連結的feedback檔案內，此處僅保留索引可搜尋。

## 圖片抓取踩坑（i2v首末幀 / R2V多圖標籤）
- [**✅ BytePlus/Ark首末幀本機檔案未接上provider_media半成品 + ShotCard.tsx三處精確比對重演assetTags.ts已修過的bug（已合併main並部署2026-09-11）**](../feedback_byteplus_img_path_and_shotcard_exact_match_bugs_2026-09-11.md) — catalog已定義`byteplus_ark_image_url` mode但dispatch層從未實作；`resolveAssetByTagName`容錯函式只在一處被呼叫，其餘三處各自重寫精確比對
- [**✅ 同分支首版遺漏R2V的ref_image_urls，本機上傳圖片直送Ark造成400（已補修復並部署2026-09-11）**](../feedback_r2v_ref_image_urls_bypassed_resolver_2026-09-11.md) — 2026-09-11使用者實測R2V生成400才發現；同一`generate()`函式內多個分支吃本機路徑時，修一處要順手查其他分支是否也漏；VPS容器重啟後已用3次live驗證確認本機路徑正確轉OSS簽名URL且可公開存取

## i18n / 語言設定
- [**✅ 主要語言預設改為繁體中文（2026-09-11）**](../feedback_default_locale_switched_to_traditional_chinese_2026-09-11.md) — settingsStore預設值+i18n fallback+html lang屬性三處同步；順手修正isCJK判斷原本只認簡體zh、繁體會誤判非CJK排版的既有bug（改用`!== "en"`）

## 多租戶登入系統操作
- [**🔴 邀請碼兌換入口是獨立`/redeem?code=`頁面，非登入頁**](../feedback_invite_redeem_ui_location_unverified_wrong_guidance.md) — 2026-09-10首次踩坑，未查前端就講錯操作位置，被使用者當場糾正

## 官方角色庫縮圖（✅ 2026-09-15第五輪最終結案，480/480筆live驗證通過）
- [**✅ 全部問題已結案**](../feedback_official_character_thumbnail_root_cause_no_virtualization_permanent_fallback_2026-09-15.md) — ①前端`AssetPickerModal.tsx`一次性渲染480個img+onError永久不重試已改IntersectionObserver+重試2次根治 ②30筆縮圖第一次抓取搜尋框卡死全抓成同一張圖，改用React fiber `item.SID`比對`group_id`修正，commit`c5db137` ③殘留3對(6筆)雜湊重複確認是ModelArk資料庫本身重複記錄，非抓取錯誤 ④額外發現30筆live 404是CF edge cache卡舊快照，Purge Everything後480/480全數複驗200通過
- [**🔴🔴 用ModelArk搜尋框抓取asset_id對應圖片前，必須驗證`fetch(url)`雜湊或完整src是否真變化，不能只看alt文字或單次截圖**](../feedback_official_character_thumbnail_root_cause_no_virtualization_permanent_fallback_2026-09-15.md) — 搜尋框連續程式化輸入會卡死在第一次結果不刷新，`img.alt`殘留值會誤導判斷；改用React fiber讀`item.SID`比對`group_id`+滾動預設列表最可靠
- [**✅ Seedance官方Digital Character Library兩個回報問題已修復（2026-09-15）**](../feedback_official_character_library_thumbnail_and_count_fix_2026-09-15.md) — ①第1張破圖根因是CF edge cache卡住部署前的404 ②角色庫遠不止60筆，重新滾動抓取拿到510筆並上線；已live驗證
- [**🔴 排查前端fallback UI「大量顯示假人icon」時，先確認fallback是否保留原`<img>`標籤**](../feedback_official_character_thumbnail_root_cause_no_virtualization_permanent_fallback_2026-09-15.md) — `querySelectorAll('img')`統計會漏掉已onError切換成SVG的卡片，改用`button[title]`比對`querySelector('img')`有無存在才準確

## 用量追蹤功能（✅ 2026-09-12已合併main並上線，全部結案）
- [**🔴 用量追蹤只接了pipeline.py，Playground完全沒有user_id/usage_events串接，發現時已誤記成「已完成並上線」**](../feedback_usage_tracking_never_wired_into_playground_2026-09-11.md) — 根因鏈：`/generate`無auth依賴→`PlaygroundGeneration`無owner_id欄位→四個`_generate_video_*`丟棄model.generate()的usage回傳值→`usage_events`永遠0筆寫入；同一輪也補了生成前費用預估(Ark公式反推,誤差0.6%)+影片實際費用標記
- [**🔴 新增帶預設值的可選參數threading到多個既有呼叫點時，最終全分支審查不可省略**](../feedback_additive_param_default_silently_undermines_new_feature_across_call_sites.md) — 2026-09-11；per-task review全過，但3處呼叫點忘傳user_id、1處死參數，只有最終跨任務整合審查才抓得到
- [**✅ JWT_SECRET因import順序早於load_dotenv在乾淨環境會被快取成空值 + usage_events表從未被自動建立**](../feedback_jwt_secret_import_order_and_usage_events_table_missing.md) — 正式服務因系統環境變數兜底而未曾暴露；根治：`from . import auth, user_repo` 移到 `load_dotenv()` 之後
- [**🔴 跨session交接檔稱「已完整實作+curl驗證通過」不等於已commit**](../feedback_handoff_claims_implemented_but_uncommitted_2026-09-11.md) — 接手時發現13個檔案仍是unstaged，功能行為是真的做了但從未進版控；接手先查git status/log，不先信文字敘述
- [**🔴 git merge commit存在於main歷史≠內容真的合併進main，需用`git merge-base --is-ancestor`+`git ls-tree`雙重驗證**](../feedback_merge_commit_exists_but_content_not_ancestor_2026-09-11.md) — merge commit在main歷史可見，但`--is-ancestor`回NO、main檔案樹也確認缺檔；只看`git log --graph`會被誤導
- [**🔴 清理測試殘留禁止`rm -rf output/`，output/底下混雜版控素材與執行期產物**](../feedback_rm_rf_output_deletes_tracked_assets_2026-09-11.md) — 誤刪`output/presets/bgm/*`八個版控音樂素材檔案，靠`git status`發現+`git restore`救回

## Playground 體驗直覺化改造（2026-09-10 完成）
- [**✅ Playground UX改造已完成（2026-09-10）**](../project_playground_ux_overhaul_2026-09-10.md) — 兩份plan-review清單皆已實作+瀏覽器驗收通過：卡片選模式+雙狀態全寬工作區、Ark/Seedance Key表單缺口；OSS雲端儲存開通仍擱置未購買
- [**🔴 EnvConfigDialog.tsx 與 SettingsPage.tsx 是兩份平行環境設定表單，改欄位需兩處同步**](../feedback_env_config_settings_duplicate_surfaces_must_sync.md) — 2026-09-10首次踩坑，交接記憶只判定其中一處缺欄位，另一處同樣缺但被漏查
- [**✅ i2v 首末幀模式+提示詞無上限+Image N編號徽章已完成並部署（2026-09-10）**](../project_i2v_first_last_frame_2026-09-10.md) — Ark first_frame/last_frame/reference_image role三者互斥已驗證；OSS權限問題已於2026-09-10解決（見下方r2v上傳修復條目）
- [**✅ r2v上傳全鏈路修復：OSS未同步+bucket權限+nginx 413+縮圖UX（2026-09-10）**](../project_r2v_upload_fix_2026-09-10.md) — 上傳從完全無反應到正常可用；根因OSS未配置→bucket權限→nginx body size限制三層依序排查；縮圖UI迭代4次定案96px+移除UUID檔名顯示
- [**🔴 上傳檔名是後端UUID非原始檔名，模型辨識多圖靠陣列順序非文字標籤**](../feedback_upload_filename_is_backend_uuid_not_original.md) — 2026-09-10；前端顯示優化解決不了UUID本身無意義的問題，需改後端保留原始檔名才有效
