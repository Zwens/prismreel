---
name: feedback_requirements_docker_missing_ai_ml_deps_2026-09-16
description: requirements-docker.txt在Gemini+Ark遷移時漏同步openai/numpy/pillow/soundfile，容器內LLMAdapter完全不能用
metadata:
  type: feedback
---

2026-09-16 排查 `GEMINI_API_KEY` 補齊後 LLM 是否真的能呼叫時發現：`Dockerfile.backend` 實際安裝的是 `requirements-docker.txt`（非 `requirements.txt`），`docker compose --force-recreate` 只重讀 `.env` 不會重裝套件，容器內 `pip list` 完全查不到 `openai`/`numpy`/`pillow`/`soundfile` 等一整批套件——`LLMAdapter.chat()` 不論 provider 是 `gemini` 還是 `openai`，內部都透過 `openai` SDK 呼叫（Gemini 走其 OpenAI 相容層），缺這個套件會直接 `RuntimeError`，不是優雅降級。

**根因**：`requirements.txt`（本機/桌面應用用）與 `requirements-docker.txt`（容器部署用）是兩份獨立檔案，這次 Gemini+Ark 上游大合併（[[project_gemini_ark_upstream_integration_2026-09-16]]）把 `openai`/`pillow`/`numpy`/`soundfile` 等新依賴加進了 `requirements.txt`，但沒有同步進 `requirements-docker.txt`。`requirements.txt` 裡另有 `torch`/`torchvision`/`einops`/`easydict`/`tqdm`/`opencv-python`/`demucs` 一批，這些是本地深度視頻推理（GPU-only、桌面 `pywebview` 應用場景）專屬，Dockerfile 本來就刻意不裝，不算缺漏。

**判斷依據**：逐一查每個缺的套件是否有 try/except 優雅降級——`demucs`/`soundfile`（DUB人聲分離）已有 try/except，缺了只印警告不崩潰；`numpy`（`beats.py`模組頂層硬import）、`openai`（`llm_adapter.py` 無降級路徑）、`pillow`（`vidu.py`圖像轉碼必經路徑）都會直接讓對應功能報錯，判定為必須補的容器依賴。

**Why**：容器與本機兩份 requirements 檔案沒有 CI 檢查同步性，純靠人工記得同步；這次上游合併是大批次變更，遺漏一份非核心設定檔的同步很容易被忽略（PR/commit review 焦點通常在主程式碼邏輯）。

**How to apply**：往後任何在 `requirements.txt` 新增/修改依賴的改動，完成後必須同步核對 `requirements-docker.txt` 是否需要同步更新（排除明確標註為「本地GPU推理/桌面應用專屬」的套件）。判斷某個缺失套件是否阻塞：先查有無 try/except 包裹（優雅降級 vs 硬崩潰），硬崩潰的才需要立即補。修改後走 `git commit → push → 等 GitLab CI docker compose build`（非本機 SSH 手動裝套件，避免容器與 repo 狀態分岔），build 時間會因新依賴明顯變長（這次約 33 分鐘：09:04 push 觸發 → 09:05:21 image build 完成才是假象，實際容器切換發生在後續某個時間點，過程中若只看 `docker images` 建立時間容易誤判「已完成」，務必同時查 `docker ps` 容器實際 `CreatedAt`/`Up` 秒數）。
