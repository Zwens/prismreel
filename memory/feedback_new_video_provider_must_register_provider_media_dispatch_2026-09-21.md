---
name: new-video-provider-must-register-provider-media-dispatch
description: 新增影片生成 provider（除了 model catalog YAML + adapter）必須同時碰 provider_media.py 的 dispatch，否則圖片輸入解析會拋錯
metadata:
  type: feedback
---

新增一個影片生成 provider（如 DeeVid）時，容易漏掉的第三個必改檔案是 `src/utils/provider_media.py`。

新增 provider 完整需要碰的三層：
1. `config/model_catalog/families/<provider>.yaml`（驅動前端選單）
2. `src/models/<provider>.py`（`VideoGenModel` 子類別）
3. `src/apps/playground/service.py` 的 `_process_video_generation()` dispatch

但還有第四個隱藏耦合點：若 provider 的圖片輸入要走 `resolve_media_input()`（OSS 簽名 URL 上傳），`provider_media.py` 內部的 `_resolve_vendor_url_mode()` 呼叫處有一段寫死的 `if mode.startswith("vidu_vendor_") or mode.startswith("kling_vendor_") or ...` 判斷式，新 provider 的 mode 字串（如 `deevid_vendor_image_url`）不在裡面就會直接拋 `Unsupported provider media input mode`，即使 `provider_registry.py` 的 family 已經正確註冊。

**Why**：這個 dispatch 邏輯是硬編碼 if/elif 而非資料驅動（跟 model catalog YAML 是資料驅動的設計不一致），brainstorming/spec 階段只看 provider adapter 的呼叫端（如 `vidu.py` 怎麼呼叫 `resolve_media_input`）很容易忽略被呼叫端內部還有一層寫死的白名單判斷。2026-09-21 DeeVid 整合設計時，spec 階段沒查到這個缺口，是進入 writing-plans 實作規劃階段深入讀 `provider_media.py` 原始碼才發現。

**How to apply**：規劃新增任何影片/圖片生成 provider 的整合任務時，除了查 model adapter 範本（如 `vidu.py`），務必額外讀一次 `src/utils/provider_media.py` 的 `resolve_media_input()` 完整實作，確認新 provider 的 `image_input_mode`/`audio_input_mode`/`reference_video_input_mode` 字串有被對應的 `_resolve_vendor_*` 分支處理，沒有就要新增分支，不能只註冊 `provider_registry.py` 的 family config 就假設會通。
