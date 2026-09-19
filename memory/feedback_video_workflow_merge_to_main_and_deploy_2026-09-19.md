---
name: feedback_video_workflow_merge_to_main_and_deploy_2026-09-19
description: video-workflow-multi-shot分支merge進main並全線部署上線，含兩個排查方法論教訓（FastAPI路由檢查方式/GitLab CI job log精確過濾）
metadata:
  type: feedback
---

`feature/video-workflow-multi-shot`（HEAD `374a7b9`）merge進main，commit `94cd506`
（含順手修復main既有的`StoryboardR2V.tsx`兩個TypeScript型別錯誤——
`resolveAssetByTagName<T>`泛型從異質陣列字面量`[characters, scenes, props]`
自動推斷單一T導致型別不符，改用`resolveAssetByTagName<NamedAsset>`明確標註解決）。
推送GitLab（觸發CI job 46034成功）+GitHub雙remote，容器重建確認，live三次
fetch+瀏覽器實測確認上線。後續memory commit `b516781`同步推送。

## 坑1：新版FastAPI用`app.routes`檢查掛載路由已不可靠
`app.include_router(router, prefix=...)`後，被包含的路由不會攤平出現在
`app.routes`頂層列表，而是包裝成`_IncludedRouter`物件，直接遍歷`app.routes`
找特定path字串會得到假陰性（明明有掛載卻查不到），一度誤判`/playground/concat`
完全沒被路由到主app。

**Why**：Starlette/FastAPI較新版本的路由樹結構改變，`.path`屬性檢查法是舊版
心智模型殘留。

**How to apply**：驗證FastAPI路由是否真的掛載，改用
`fastapi.testclient.TestClient`實際發送請求（如`client.options(path)`），
看回傳`401`（middleware正常攔截，代表路由存在）還是`404`（路由不存在）
來判斷，不要遍歷`app.routes`比對path字串。

## 坑2：GitLab CI runner journalctl log用寬鬆關鍵字grep會誤抓其他專案的job
`journalctl -u gitlab-runner | grep "job-status=success"`會抓到同一時段內
其他不相關專案（如`pbn-group/seo-report`）剛好也成功的job，造成誤判「目標
job已完成」。

**Why**：同一台VPS上的gitlab-runner服務同時跑多個專案的job，log是交錯的，
不篩選具體job編號就等於在賭運氣。

**How to apply**：輪詢CI job狀態一律先取得`job=<編號>`（從觸發push後的
第一筆`Added job to processing list`log行取得），後續grep一律帶上
`job=<編號>`精確過濾，不用寬鬆的status關鍵字。

## 相關
[[project_video_workflow_e2e_task10_completed_2026-09-19]] — Task 10稽核結論
