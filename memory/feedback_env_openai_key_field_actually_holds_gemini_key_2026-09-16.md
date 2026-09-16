---
name: feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16
description: VPS .env的OPENAI_API_KEY欄位裡實際填的是Gemini key，真正的OpenAI key已失效
metadata:
  type: project
---

2026-09-16 排查 Gemini+Ark 上游整合後圖像生成/TTS 是否可用時發現：VPS `/opt/prismreel/.env` 的 `OPENAI_API_KEY=AQ.Ab8RN6LHKblywV9dY1x118G2eKZJFyJmcnqACoI4R13rT5Zz5w`——這個值格式是 Google 發的 key（`AQ.` 開頭），不是 OpenAI 格式（`sk-proj-...`）。

**已用工具驗證**（非推測）：
- `AQ.Ab8RN6LHKblywV9dY1x118G2eKZJFyJmcnqACoI4R13rT5Zz5w` 打 `https://generativelanguage.googleapis.com/v1beta/models`（`x-goog-api-key` header）→ **200，是有效的 Gemini API Key**
- 使用者手上另一組 `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` 打 `https://api.openai.com/v1/models`（Bearer）→ **401，已失效/不可用**

**現狀**：VPS `.env` 缺 `GEMINI_API_KEY`（圖像生成`src/models/gemini_image.py`、TTS`src/audio/gemini_tts.py` 都寫死只認這個變數，無 OpenAI 相容路徑，`src/models/factory.py`已被這次遷移刪除）。`LLM_PROVIDER=openai`+`OPENAI_API_KEY`（那組錯放的Gemini key）目前能讓 LLM 文字生成勉強動起來，但這是巧合而非正確配置——需要查證 `OpenAI()` client 用這個key打openai端點時是否真的成功過，不能只看`is_configured()`回true就當作沒問題。

**Why**：使用者提供key時容易混淆兩個平台格式，`.env`裡變數名稱和實際內容不一致時肉眼難察覺，必須用真實API呼叫驗證而非只看是否"有值"。

**How to apply**：下次要補齊 `GEMINI_API_KEY` 時，直接寫入這組已驗證有效的 `AQ.Ab8RN6LHKblywV9dY1x118G2eKZJFyJmcnqACoI4R13rT5Zz5w`；同時要跟使用者確認 `OPENAI_API_KEY` 欄位是否要清掉或換回真正能用的 OpenAI key（目前那組`sk-proj-...`已確認401，若不換main LLM功能會在下次真正呼叫時才爆炸，現在的"能跑"只是因為openai client初始化不主動驗證key）。改完需 docker compose 重啟+live驗證圖像生成/TTS真的成功產出，不能只看服務啟動無報錯。

✅ 2026-09-16 已完成：`GEMINI_API_KEY` 寫入該組key，`OPENAI_API_KEY` 清空，`LLM_PROVIDER` 改 `gemini`（原為`openai`，該值本身就是retired路徑之一但未被拒絕會繼續work，改成`gemini`才是官方預設）。過程中意外發現更深層問題見 [[feedback_requirements_docker_missing_ai_ml_deps_2026-09-16]]，兩者一併修復並經CI重build+容器內真實LLM呼叫驗證成功（`reply: 'OK'`）。圖像生成/TTS因套件已補齊理論可用，但本次僅驗證LLM文字呼叫，未逐一實測圖像生成與TTS產出，下次觸碰相關功能時仍需live驗證。
