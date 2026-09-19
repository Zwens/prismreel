---
name: feedback_asset_source_picker_exit_animation_blocks_clicks_2026-09-16
description: AssetSourcePicker框架動畫exit未完成時overlay仍攔截點擊的根因與修法；驗證React state改用reactProps避免過期fiber snapshot誤判；2026-09-17補充backdrop-filter破壞fixed定位的第二種「modal點了沒反應」成因
metadata:
  type: feedback
---

2026-09-16 真人換裝舞蹈使用者實測回報5項問題，雙session協作（本session負責dance/目錄，peer session claude-wmzic-6c負責滾軸/用量顯示），互相驗收後全部結案。

**問題3/5根因**：`AssetSourcePicker.tsx` 的 `AnimatePresence` + `motion.div`（overlay第386行、modal第394行）退場動畫若因故未觸發完成回調（分頁背景節流/動畫被打斷等，本session測試環境`document.visibilityState`恆為`hidden`即是一例），React無法真正unmount該DOM節點，導致`fixed inset-0 z-50`的overlay卡在`opacity:0`但`pointerEvents:auto`，持續攔截底下Step2/Step3的所有點擊。使用者體感是「勾選框沒反應」「選了圖沒反應」，實際上state本身完全正常（用React fiber驗證`state.sheet`/`state.danceVideoPath`都有正確更新）。

**Why**：這不是state同步bug，是純CSS層的點擊攔截問題，過去排查容易被「state對不對」這個問題帶偏方向。

**修法（commit `cdd4d77`）**：把`pointerEvents`塞進variants本身，讓它隨`hidden`/`visible`狀態切換，而非依賴exit動畫完成：
```ts
const overlayVariants = {
  hidden: { opacity: 0, pointerEvents: 'none' as const },
  visible: { opacity: 1, pointerEvents: 'auto' as const },
};
```
`pointerEvents`不是可補間屬性，framer-motion在動畫**開始**的瞬間就套用該值，不等duration跑完——這正是修法的關鍵，不管exit動畫本身有沒有卡住，攔截能力立即解除。

**How to apply**：其他用`AnimatePresence`包`fixed inset-0`全螢幕遮罩的modal元件（如`MediaInput.tsx`也有多個AssetSourcePicker實例），若日後也回報「點了沒反應」且發生在modal關閉之後，優先排查是否同樣的殘留overlay攔截，而非state沒更新。

---

**驗證React state的陷阱**：排查問題2/4（新增比例/秒數功能）驗收時，用以下方式抓React hook state：
```js
let hook = fiber.memoizedState;
while (hook) { if (matchFn(hook.memoizedState)) return hook.memoizedState; hook = hook.next; }
```
曾抓到`duration: null`的過期snapshot，即使DOM輸入框已顯示正確值"12"，一度誤判為bug。改用`element[Object.keys(element).find(k=>k.startsWith('__reactProps$'))].value`直接讀React傳給DOM的最新props（非hook internal state），才確認`value: 12`是對的、功能實際正常。

**How to apply**：日後用React fiber驗證受控輸入框（controlled input）的state時，優先讀`__reactProps$`上的`value`/`checked`等prop，比遍歷`memoizedState`鏈可靠——後者在快速連續操作後可能撈到尚未commit的alternate fiber。

---

**功能新增（commit `c6179ac`）**：Step3新增比例（9:16/16:9/1:1/3:4/4:3/adaptive）+秒數（4-30s，留空送-1跟隨原片）控制項。依`docs/api-reference/byteplus-ark-seedance-seedream.md`第2.4節官方實調文件——`task_type:'reference'`明確「ratio、duration 無特殊約束」，不同於`edit`/`extend`強制`adaptive`/`-1`——才確認可安全放開自訂，避免加了UI但後端模型拒絕。

**跨session協作記錄**：與peer session `claude-wmzic-6c` 採「互相驗收」機制（使用者中途下達新規則）：一方完成一項先SendMessage附檔案/行號/實測結果，等對方讀code diff+複核通過才進下一項，避免建立在未驗證的基礎上疊加。分工依檔案領域切（本session：dance/目錄；peer：PlaygroundPage.tsx/ResultGallery.tsx等），commit前用`git status`確認staging範圍不誤觸對方未提交的改動。

---

## 🔴🔴 2026-09-17補充：同一元件第二種「modal點了沒反應」根因——backdrop-filter破壞fixed包含塊

使用者回報「從素材庫選擇→三視圖沒有自動被勾選」，**純代碼推理**（檢查`pickSheet`/`useSheet`預設值等state邏輯）判斷根因、修復後使用者仍回報「依舊不像上傳圖片那樣會被自動抓取」——第一輪修法完全找錯方向，因為問題根本不在state邏輯。

**真正根因**：`AssetSourcePicker`被渲染在`DanceSwapWizard`的`StepShell`（`glass-panel atelier-card`class，帶`backdrop-filter: blur(20px) saturate(1.15)`）DOM樹內部，而非portal到`document.body`。CSS規範：**任何祖先設了非none的`filter`或`backdrop-filter`，都會成為子孫`position:fixed`元素的包含塊**（等同`transform`的效果）。導致modal的`fixed inset-0`被限制在該`<section>`的~360px邊界內而非viewport，footer的「選擇」確認按鈕被擠出可視範圍、看不到也點不到。使用者點圖片只觸發`setSelected`（顯示勾選標記），從未能按到真正呼叫`onSelect`的按鈕，`pickSheet`從未被呼叫，`state.sheet`保持null，checkbox正確顯示未勾選——**state邏輯本身完全正常**，跟上面問題3/5的教訓一樣是純CSS層陷阱，但這次是不同的CSS機制（containing block，非pointer-events）。

**排查方法（如何在純代碼審查失敗後找到根因）**：用瀏覽器`getComputedStyle`+`getBoundingClientRect`逐層往上查`overlay`祖先鏈的`transform`/`filter`/`backdropFilter`/`contain`，找到`overlay.getBoundingClientRect()`不等於`(0,0,innerWidth,innerHeight)`時，问題必定出在某層祖先的containing block屬性，純看Tailwind class猜不出來，必須實測DOM。

**修法（commit `af21286`）**：`AssetSourcePicker.tsx`改用`createPortal(<...>, document.body)`——與專案裡其他10個modal元件（`DetailPanel.tsx`/`PromptTemplateModal.tsx`等）的既有慣例一致，此元件是唯一遺漏的。

**How to apply（更新排查清單）**：日後modal元件回報「點了沒反應」/「選了沒生效」，依序排查：① state有沒有真的更新（React fiber/`__reactProps$`） ② overlay是否殘留`pointerEvents:auto`攔截（問題3/5案例） ③ **overlay/modal的`getBoundingClientRect()`是否等於viewport大小**——不等於就去查是否被嵌在`backdrop-filter`/`filter`/`transform`容器內，改成`createPortal`到`document.body`根治。新建任何`fixed inset-0`全螢幕modal時，直接預設用`createPortal`，不要巢狀在頁面內容DOM樹裡，避免重演。

---

## 🔴🔴🔴 未解決：使用者實測後回報上述兩個修復依舊無效（2026-09-17，本次記錄留給下一個session重查）

`48a0ab1`（`ResultGallery.tsx`+`AiVideoPage.tsx`加`flex flex-col`修滾軸）與`af21286`（`AssetSourcePicker.tsx`改`createPortal`修三視圖勾選）兩個commit都已推送、CI部署完成，且**本session用claude-in-chrome瀏覽器對live站台做了DOM層級實測**（`getComputedStyle`/`getBoundingClientRect`/`elementFromPoint`/checkbox `.checked`讀值），當時測得的結果顯示兩個問題都已修復（RESULTS區`outerClientHeight`從2630px降到568px與父層一致、checkbox讀到`checked:true`）。

**但使用者接著用自己的瀏覽器實際操作後，回報「未發現問題」（即兩者依舊沒修好）**。這代表本session的DOM實測與使用者實際看到的狀態不一致，可能原因待查：
- 使用者瀏覽器快取了更舊的bundle，未真正載入`af21286`後的版本（本session測試時已強制`location.reload(true)`+確認webpack chunk hash改變才判定生效，但使用者端不確定是否同樣清過快取）
- 本session測試的操作路徑與使用者實際路徑不同（例如使用者可能用了不同瀏覽器/裝置/帳號/不同的資料狀態）
- CF edge cache對這個部署視窗又卡住了舊版（見`feedback_cf_edge_cache_stale_404_during_deploy_window.md`已知模式，之前是404，這次可能是卡住整個JS bundle未必只有404才會發生）
- 也可能兩個commit本身在某些情境下仍有本session未覆蓋到的邊界案例（例如不同瀏覽器寬度、不同資料狀態下的DanceSwapWizard）

**How to apply（下一個session重查SOP）**：
1. 不要相信「DOM實測通過」的舊結論，要求使用者提供這次操作的**新截圖或錄影**，逐一比對是不是同一個live版本
2. 先確認使用者瀏覽器實際載入的`_next/static/chunks/webpack-*.js`/`main-app-*.js`等chunk hash，是否等於`af21286`部署後的版本（比對方法見上方「排查方法」段落的fetch no-store手法）
3. 若bundle hash確認是新版但問題依舊→ 回到零式檢視，不帶任何上次結論，重新用使用者的確切操作步驟（瀏覽器、分頁、裝置）重現
4. 若bundle hash是舊版 → 查CF/CDN快取層，而非懷疑代碼修法本身

---

## ✅ 2026-09-17後續：雙session獨立驗證通過，懸案暫歸因使用者端瀏覽器快取

交接給peer session `claude-wmzic-6f`後，對方**獨立**（非重述本session結論）驗證：①SSH進VPS(202.182.117.182)比對`/opt/prismreel`原始碼確認`createPortal`（`AssetSourcePicker.tsx`）+`flex-col`（`AiVideoPage.tsx`第260行包`<ResultGallery />`）兩處改動都已同步，容器建立時間2026-09-17 03:18確認是`af21286`部署後的新版 ②`claude-in-chrome`走完整操作流程實測：RESULTS區`scrollHeight:3683 > clientHeight:522`且`canScroll:true`滾輪操作確認真的能捲動；`/#/playground`真人換裝舞蹈Step1「我已有三視圖」→「從素材庫選擇」→modal正確置中彈出→選圖→按選擇→Step1立即顯示已選圖+步驟圈變綠勾→Step3 checkbox讀`input.checked === true`。

**過程教訓**：驗證session第一次截圖時肉眼誤判modal footer按鈕位置跑版，改用`zoom`截圖比對DOM座標後確認按鈕本來就在該位置、視覺正常——小尺寸截圖判斷modal是否跑版前，優先用`zoom`放大該區域或直接讀DOM `getBoundingClientRect()`，不要單憑整頁截圖肉眼判斷。

**結論**：兩個修復代碼（`48a0ab1`第一輪、`af21286`第二輪）本身正確、VPS/容器都已是新版，本session與peer session各自獨立測試都通過。使用者回報「未發現問題」最可能是使用者端瀏覽器快取了舊版JS（非CDN層，是瀏覽器本機cache）或操作路徑不同，已請使用者強制重新整理（Ctrl+Shift+R / Cmd+Shift+R）並附新截圖佐證，非CI/代碼問題。**若使用者強制刷新後仍回報未解決，才需要重啟排查**（且應優先懷疑操作路徑/瀏覽器/裝置差異，而非重新懷疑這兩個commit的修法方向）。

**How to apply**：雙session各自獨立用工具驗證（非其中一方複誦另一方結論）都通過，且已排除部署層面（VPS原始碼/容器版本）問題時，可以合理將「使用者仍回報未解決」歸因於使用者端快取，請使用者強制刷新+附證據，而非無限期重新排查代碼本身。

