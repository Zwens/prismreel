---
name: feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16
description: VPS .env的OPENAI_API_KEY欄位裡實際填的是Gemini key，真正的OpenAI key已失效
metadata:
  type: project
---

2026-09-16 排查 Gemini+Ark 上游整合後圖像生成/TTS 是否可用時發現：VPS `/opt/prismreel/.env` 的 `OPENAI_API_KEY=AQ.Ab8R...`（已遮蔽，2026-09-17 revoke後補記）——這個值格式是 Google 發的 key（`AQ.` 開頭），不是 OpenAI 格式（`sk-proj-...`）。

**已用工具驗證**（非推測）：
- 該Gemini格式key 打 `https://generativelanguage.googleapis.com/v1beta/models`（`x-goog-api-key` header）→ **200，是有效的 Gemini API Key**
- 使用者手上另一組 OpenAI 格式key（`sk-proj-...`）打 `https://api.openai.com/v1/models`（Bearer）→ **401，已失效/不可用**

**現狀**：VPS `.env` 缺 `GEMINI_API_KEY`（圖像生成`src/models/gemini_image.py`、TTS`src/audio/gemini_tts.py` 都寫死只認這個變數，無 OpenAI 相容路徑，`src/models/factory.py`已被這次遷移刪除）。`LLM_PROVIDER=openai`+`OPENAI_API_KEY`（那組錯放的Gemini key）目前能讓 LLM 文字生成勉強動起來，但這是巧合而非正確配置——需要查證 `OpenAI()` client 用這個key打openai端點時是否真的成功過，不能只看`is_configured()`回true就當作沒問題。

**Why**：使用者提供key時容易混淆兩個平台格式，`.env`裡變數名稱和實際內容不一致時肉眼難察覺，必須用真實API呼叫驗證而非只看是否"有值"。

**How to apply**：下次要補齊 `GEMINI_API_KEY` 時，寫入使用者提供的有效key（不在memory檔案留完整明文，見[[feedback_memory_md_files_are_git_tracked_redact_keys_2026-09-17]]）；同時要跟使用者確認 `OPENAI_API_KEY` 欄位是否要清掉或換回真正能用的 OpenAI key（目前那組`sk-proj-...`已確認401，若不換main LLM功能會在下次真正呼叫時才爆炸，現在的"能跑"只是因為openai client初始化不主動驗證key）。改完需 docker compose 重啟+live驗證圖像生成/TTS真的成功產出，不能只看服務啟動無報錯。

✅ 2026-09-16 已完成：`GEMINI_API_KEY` 寫入該組key，`OPENAI_API_KEY` 清空，`LLM_PROVIDER` 改 `gemini`（原為`openai`，該值本身就是retired路徑之一但未被拒絕會繼續work，改成`gemini`才是官方預設）。過程中意外發現更深層問題見 [[feedback_requirements_docker_missing_ai_ml_deps_2026-09-16]]，兩者一併修復並經CI重build+容器內真實LLM呼叫驗證成功（`reply: 'OK'`）。圖像生成/TTS因套件已補齊理論可用，但本次僅驗證LLM文字呼叫，未逐一實測圖像生成與TTS產出，下次觸碰相關功能時仍需live驗證。

## 2026-09-17 事件收尾：換新key（見[[feedback_memory_md_files_are_git_tracked_redact_keys_2026-09-17]]）
舊key（`AQ.Ab8R...`，本檔上方記錄過完整明文那組）因memory檔案曾明文寫入並push到GitLab，判定已洩漏。使用者反映Google帳號權限只能「刪除」不能單純revoke，且顧慮到刪除/revoke會讓Cloud Console用量儀表板依key切分的歷史統計失真（使用者用不同key區分不同API/專案用量），故不強求立即刪除舊key本身，改採「新key頂替+舊key用量歷史留待使用者自行判斷」的處理方式：
1. 使用者提供新key（`gen-lang-client-0254947352`專案，格式`AQ.Ab8RN6Ly...`），直接於SSH session內用`sed -i`原地替換VPS `.env`的`GEMINI_API_KEY`，全程未落地明文到任何本機檔案/log/memory
2. `docker compose restart backend`重啟，容器內`printenv`前綴比對確認新值生效
3. 容器內`python3 -c`直接呼叫`LLMAdapter().chat()`（非裸API ping），拿到真實回覆`OK`，確認應用層可用非僅網路層200
4. 使用者往後若決定刪除/revoke舊key本身，屬於Google Cloud Console操作，AI無法代勞

**Why**：多把key共用一組`.env`欄位名稱時，任何一次「查證後記錄下來」的動作都有機會把明文寫進版控（本次事件根因）；`.env`本身已在`.gitignore`（`git check-ignore`可驗證正確），漏洞出在memory檔案而非`.env`本身外洩。

**How to apply**：往後任何一次touch這個欄位（新增/替換/查證），in-session操作全程不得讓key完整字串出現在會被write進磁碟檔案的位置（含memory/scratchpad/commit message），只能存在於單次SSH command的參數或環境變數展開中；記錄「換了新key」這件事本身即可，不必附值。
