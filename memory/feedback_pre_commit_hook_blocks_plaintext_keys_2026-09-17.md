---
name: feedback_pre_commit_hook_blocks_plaintext_keys_2026-09-17
description: 已建立.git/hooks/pre-commit機械掃描攔截明文API key格式字串，防止memory檔案再度洩漏金鑰
metadata:
  type: project
---

Gemini key洩漏事件（見[[feedback_env_openai_key_field_actually_holds_gemini_key_2026-09-16]]、[[feedback_memory_md_files_are_git_tracked_redact_keys_2026-09-17]]）收尾時，plan-end驗收發現「靠記得遮蔽」屬於規則層級而非機制層級防護，不符合「規則存在但遵守率非100%」的教訓（CLAUDE.md「規則層級vs機制層級判準」三條件：代價可逆+純本機低風險+機械可測，三條皆成立）。

已建立`.git/hooks/pre-commit`，regex掃描staged diff新增行是否含`AQ\.[A-Za-z0-9_-]{20,}`（Gemini）、`sk-proj-[A-Za-z0-9_-]{20,}`/`sk-[A-Za-z0-9]{20,}`（OpenAI）、`AIza[A-Za-z0-9_-]{20,}`（Google API key另一種格式）任一格式，命中即擋下commit並印出匹配行，允許`--no-verify`繞過誤判。已用假金鑰字串實測攔截成功（exit 1），真實commit不受影響。

**Why**：memory檔案是git追蹤檔案，前一次事件就是因為「查證時順手記錄完整key」被commit+push才洩漏；純文字規則「記得要遮蔽」已證實會失手一次，機械化掃描不依賴記憶力。

**How to apply**：這個hook只存在本機`.git/hooks/`目錄，**不受版控、不會自動同步給其他clone這個repo的session或協作者**（`.git`目錄本身不進版控）。若要讓其他session/協作者也受保護，需個別在自己的工作目錄手動建立同一份hook，或改用`.githooks/`+`git config core.hooksPath`納入repo管理才能真正共用——目前尚未做這一步，屬已知限制，非全域防護。下次若在此repo其他clone/session踩到同類洩漏，優先確認是否只是「這個clone沒裝hook」，不必重新懷疑hook邏輯本身失效。
