---
name: simplified-chinese-ui-cleanup-and-unpushed-commit
description: Prismreel前端UI簡體字清理完成記錄，含「commit了沒push」導致live驗收誤判為快取問題的踩坑
metadata:
  type: project
---

前端UI顯示層簡體字已分兩輪清理完成：第一輪17個檔案（交接自claude-wmzic-23的opencc s2t掃描清單），第二輪對`frontend/src`全部149個`.ts`/`.tsx`檔（排除test/spec）重新精確掃描，補漏7個檔案（`GroupedModelGrid.tsx`/`ModelSettingsModal.tsx`/`PropertiesPanel.tsx`/`StoryboardR2V.tsx`/`VideoCreator.tsx`/`PromptConfigModal.tsx`/`SeriesPromptConfigModal.tsx`）。commit `f70ffb5`＋`8915af1`，皆已push並經CI部署，容器建立時間戳（2026-09-17 07:53 UTC）親自SSH核實對應push時間點。

純程式碼註解裡的簡體字（約426行/60檔，全是`//`或`/** */`開頭，不影響畫面）使用者已裁示暫緩，優先度低於UI文字。

**🔴 關鍵坑點**：claude-wmzic-23那輪的`GridOverlayPicker.tsx`修正（commit `a0e3c2e`）**只commit沒push**，導致VPS容器一直跑舊版原始碼。這造成「本機原始碼已確認乾淨，但live驗收(claude-wmzic-0a)仍看到簡體字」的假象，一度被合理懷疑為CF/瀏覽器快取問題或元件重複邏輯問題，多花一輪排查才靠`git merge-base --is-ancestor <commit> origin/main`查出commit根本沒推送。

**Why**：多人協作repo下，「本地commit存在」≠「已同步到遠端」≠「已部署」，三者是獨立的狀態，任何一環斷開都會產生「代碼明明是對的但live沒生效」的表象，若沒有系統性查核容易被誤導去查錯方向（快取/邏輯bug）。

**How to apply**：live驗收發現「原始碼查起來是對的，但live行為對不上」時，優先序應該是：①`git log <commit> --format=%H` 確認commit真的存在於當前分支 ②`git merge-base --is-ancestor <commit> origin/main`確認已推送到遠端 ③ SSH查容器/服務建立時間戳是否晚於push時間，確認CI真的部署了這次改動——三層都過了才輪到懷疑快取或元件邏輯本身。這三個指令都不需要GitLab API token，純git+ssh即可查完，比先假設「可能是快取」更省時間。

另見PrismReel MEMORY.md「部署機制」章節既有[[feedback_gitlab_ci_auto_deploy_setup_2026-09-11]]，該條記錄的是「push後多久才生效」的時間差問題，本條記錄的是更前一步「有沒有真的push」的問題，兩者互補、判斷順序上本條在前。
