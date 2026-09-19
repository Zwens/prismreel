---
name: feedback_local_windows_missing_ffmpeg_blocks_concat_2026-09-19
description: 本機Windows開發環境未安裝FFmpeg導致/playground/concat合成影片端點500，已交叉確認VPS production不受影響
metadata:
  type: feedback
---

多鏡頭工作流「合成完整影片」點擊後回傳 500，後端log明確：
`FFmpeg not found in PATH or common Windows paths`。`where ffmpeg`確認
本機完全沒裝。

**Why**：VPS production 用 Docker 容器部署，`prismreel-backend`容器內建
FFmpeg（已SSH確認：容器內7.1.5、VPS宿主機4.4.2），只有本機Windows裸機
開發環境缺這個外部依賴，屬於本機開發環境限制不是程式碼bug或部署缺陷。

**How to apply**：本機遇到concat/影片合成類500錯誤，先查log是否為
FFmpeg相關，不要假設是程式邏輯問題。如需在本機驗證完整combine流程，
需先手動裝FFmpeg（winget/choco）並加入PATH；若只是要驗證生成/API串接
邏輯本身，可比照2026-09-19案例：確認VPS已裝ffmpeg後，跳過本機combine
肉眼複驗，改信任既有整合測試（`VideoWorkflowPage.spec.tsx`已mock網路層
驗證combine呼叫時outputPath順序正確）作為邏輯正確性佐證。

## 相關
[[project_video_workflow_e2e_task10_completed_2026-09-19]]
