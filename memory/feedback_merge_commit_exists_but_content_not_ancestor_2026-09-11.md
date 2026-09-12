---
name: merge-commit-exists-but-content-not-ancestor
description: git log --graph看到merge commit存在於main歷史不代表內容真的合併進main，需雙重驗證ancestor關係與實際檔案樹
metadata:
  type: feedback
---

2026-09-11 查證 `feature/usage-tracking` 是否已合併進 `main` 時，`git log --all --oneline --graph` 清楚顯示 `8556704 Merge branch 'feature/usage-tracking' into 'main'` 存在於 main 的提交歷史裡，直覺判斷「已合併」。但深入查證發現：這個 merge commit 的第二 parent 指向的 `feature/usage-tracking` HEAD（`f8eebcb`）用 `git merge-base --is-ancestor f8eebcb main` 檢查回傳 **NO**；`git ls-tree -r main --name-only` 也確認缺少 `usage_repo.py`/`/usage/page.tsx` 等該分支的核心檔案。

**Why**：`git log --graph` 顯示的是「這個 merge commit 物件存在且被 main 的某個祖先鏈引用過」，不等於「這個 merge commit 帶來的內容變更仍留在 main 目前的 HEAD 裡」——可能是遠端做了合併但本地分支/HEAD 追蹤的位置不同步、或合併後又被後續操作（reset/覆蓋）抵銷，圖形本身不會告訴你「現在」的真相，只告訴你「歷史上發生過」。

**How to apply**：
- 判斷「某分支是否已合併進 main」，`git log --graph` 只能當作第一眼線索，不能當結論
- 正確驗證程序：① `git merge-base --is-ancestor <目標分支HEAD> main`（回 NO 代表沒真正合併）② `git ls-tree -r <目標分支> --name-only` vs `git ls-tree -r main --name-only` 用 `diff` 抓出「該分支有但 main 沒有」的檔案清單，兩者一致才能下「已合併」結論
- 這條規則同樣適用於「查證某 commit 的程式碼是否已部署到 VPS」——見 `feedback_byteplus_img_path_and_shotcard_exact_match_bugs_2026-09-11.md` 的容器 vs 宿主機檔案落差案例，同一類「間接證據 vs 直接驗證」陷阱
