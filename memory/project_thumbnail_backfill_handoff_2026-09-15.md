---
name: project-thumbnail-backfill-handoff-2026-09-15
description: 官方角色庫縮圖補齊任務交接狀態（2026-09-15），含虛擬列表洗牌分區發現與下載卡點
metadata:
  type: project
---

## 目前真實狀態（已用工具驗證，非推測）

- `config/digital_characters/official.json`：**480筆**（已從510筆移除30筆線上已下架的過時asset_id，commit `bf997a0`，已push GitLab+GitHub）
- `config/digital_characters/thumbnails/`：**120張**已有縮圖
- **缺圖：360筆**，asset_id完整清單存於本次session的瀏覽器`window.__missingIds`（未落地到本機檔案，需要時重新用以下指令產生）：

```js
const fs=require('fs');
const data=JSON.parse(fs.readFileSync('config/digital_characters/official.json','utf8'));
const chars = data.characters || data;
const ids = chars.map(c=>c.asset_id).filter(Boolean);
const files = fs.readdirSync('config/digital_characters/thumbnails/').map(f=>f.replace(/\.jpg$/,''));
const fileSet = new Set(files);
const missing = ids.filter(id=>!fileSet.has(id));
```

## 已驗證有效的抓取手法（沿用即可）

ModelArk Playground（`https://ai.byteplus.com/ark/region:ap-southeast-1/experience/gen_video` → Digital characters分頁）用React fiber tree手法：
```js
function getItem(el) {
  const key = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
  if (!key) return null;
  let node = el[key];
  let depth = 0;
  while (node && depth < 15) {
    if (node.memoizedProps && node.memoizedProps.item) return node.memoizedProps.item;
    node = node.return;
    depth++;
  }
  return null;
}
// document.querySelectorAll('[class*="cardInner"]') 逐卡取 item
// assetId = item.Content.Image['0'].AssetID
// url = item.Content.Image['0'].URL （12小時簽名URL，含query string，javascript_tool輸出會截斷/擋掉特殊字元，只能在頁面內直接fetch不能印出完整字串）
```

## 🔴🔴 本次新發現的關鍵坑：虛擬列表洗牌不是均勻隨機，是「分區群聚」

**現象**：連續滾動10輪以上（每輪30張新卡片），命中「缺圖清單360筆」中任何一筆的asset_id機率持續為0。已有縮圖的120筆角色反而反覆重複出現（甚至同一批卡片在不同滾動位置重複兩次）。

**推論**（未100%證實，但滾動證據一致）：虛擬列表的洗牌池似乎把「已被使用/已產生縮圖」的角色排在洗牌序列前段，缺圖的360筆集中在後段更深處。上次（2026-09-15更早的session）滾動到累積599筆不重複asset_id時才逐漸覆蓋到360筆缺圖中的330筆左右，且越後面才刷出的批次命中率越高。

**How to apply**：
1. 抓取阶段（只抓asset_id做覆蓋率檢查）可以用純Set累積，不需保留item物件，比較穩定，之前已驗證滾動20+輪可達599筆覆蓋度。
2. **下載階段**（需要item.Content.Image['0'].URL）不能只存id，必須同一次滾動內把item完整存下來（DOM會被虛擬列表回收，只存id事後拿不到URL）。這次卡在：改成邊滾動邊存url的模式後，連續10+輪都落在「已有縮圖」的前段區域，命中率0。
3. **建議下次做法**：不要在同一個瀏覽器session裡先做「純id覆蓋率確認」再做「item+url收集」兩階段（會重新從頭洗牌，重複踩到前段0命中區）。改成**從一開始就同時收集id+url**，跳過純id驗證階段，並且做好心理預期：可能需要滾動15-25輪才會進入缺圖密集區，不要在前10輪0命中就懷疑手法失效。
4. 每次`javascript_exec`只能滾動+掃描一次（不能寫迴圈，會導致CDP渲染器凍結，見[[feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15]]），所以「滾動15-25輪才進入密集區」代表光是抓URL階段就要15-25次工具呼叫，抓完360張還要再360次下載呼叫，總量遠大於之前預估的390次。

## 已确认可丢弃的方向

- 查找React更上層fiber props裡是否有完整510+筆資料陣列：**沒有**，虛擬列表只在DOM可視範圍附近保留渲染，上層fiber也只找到`children`長度60的陣列（非完整資料源）。
- 用搜尋欄位（`Enter portrait gender, age, nationality search`）按asset_id或SID搜尋：**未實測**，值得下次一試，如果支援可能比盲目滾動更精準（但搜尋欄位設計初衷是性別/年齡/國籍描述詞，不確定是否支援ID查詢）。

## 下次接手步驟建議

1. 重新整理ModelArk頁面（每次reload會重新洗牌，之前的`window.__missingSet`等state會清空，需要用本檔案上方的node腳本重新產生360筆清單並貼回頁面）
2. 點擊Digital characters分頁
3. **直接一步到位**：滾動+同時收集`assetId→url`到`window.__pendingDownloads`，不要分兩階段
4. 心理預期滾動15-25輪才進入缺圖密集區，不要因為前10輪0命中就換手法
5. 每收集到約30-50筆url後，開始逐張下載（同一批一張一張`javascript_tool`呼叫，見[[feedback_browser_blob_download_freezes_renderer_after_few_calls_2026-09-15]]的凍結限制）
6. 下載完成的原圖需用PIL壓縮成150x200 JPEG（RGB、quality=85、寬邊等比縮放後從中間裁切150px寬），存入`config/digital_characters/thumbnails/<asset_id>.jpg`
7. 過渡檔案（Downloads原圖）確認已成功複製進正式目錄後才能刪除，不可貿然清理（見[[feedback_never_delete_unmoved_downloaded_artifacts_as_cleanup]]）
8. 每完成一批（建議50張）就commit+push一次，保持之前的節奏（52張/8張的分批commit紀錄）

## 已知30筆過時asset_id處理紀錄

已於commit `bf997a0`從official.json移除（這些角色在滾動抵達599筆不重複asset_id後仍找不到對應，判定為ModelArk線上庫已下架/替換）。清單見該commit diff，不需要重新排查。
