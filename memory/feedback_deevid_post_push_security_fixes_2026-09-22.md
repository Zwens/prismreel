---
name: deevid-post-push-security-fixes
description: DeeVid整合push後自動安全審查揪出race condition+SSRF，兩輪修復完成merge
metadata:
  type: feedback
---

DeeVid provider 整合（[[feedback_deevid_provider_integration_completed_2026-09-22]]）push 進 main 後，push 後自動安全審查（background security review hook）揪出真實漏洞，經兩輪修復後 commit `f562f73` merge 完成。

**第一輪自動審查發現 3 項**：quota-bypass（親自逐行核實**不成立**，額度檢查/扣點順序其實正確）、race condition（**屬實**，`get_remaining_points()`讀+`record_usage()`寫之間無鎖，並發請求可各自通過檢查導致總扣點超過上限）、SSRF（**屬實**，`requests.get`直接呼叫外部提供的URL無host驗證）。

**第一輪修復後，commit本身又觸發第二次自動審查，再抓出2項**：SSRF redirect bypass（`requests.get`預設`allow_redirects=True`，驗證只檢查初始URL未檢查重導向後的實際目的地）、`release_reservation`連線逾時可能遮蔽真實錯誤且永久洩漏預留額度（並發時5秒逾時可能對鎖失敗）。

**Why**：自動安全審查的宣稱不能照單全收也不能照單全否——必須逐項親自查證。quota-bypass這項最終判定為誤報（審查工具可能對「額度檢查」與「API呼叫」的順序判斷有誤），但另外4項都是真實漏洞，經獨立reviewer用**mutation testing**（刪掉修復本身看測試是否真的失敗）方式驗證修復確實有效，非僅讀程式碼推論。

**How to apply**：
1. Push後自動安全審查通知只給摘要，必須自己讀程式碼逐項核實再決定是否修復，不可照單全收（可能有誤報）也不可因為「聽起來很技術」就假設一定成立
2. 修復完成後不能只看「測試通過」幾個字就採信，要親自讀關鍵測試的程式碼邏輯，確認它是否真的重現了要修的那個具體場景（本案`test_generate_video_deevid_reraises_original_error_even_if_release_reservation_fails`親自逐行核對過，確認Python裸`raise`語意正確保留最外層例外，非測試斷言鬆散僥倖通過）
3. 安全性修復的審查應派最強模型並要求用「mutation testing」等更嚴謹方式驗證（第二輪reviewer刪掉修復本身讓測試故意失敗，證明測試不是虛設）
4. 已知遺留：`vidu.py`/`kling.py`也有相同SSRF redirect bypass模式未修（本次範圍僅限DeeVid），需要獨立follow-up任務處理
