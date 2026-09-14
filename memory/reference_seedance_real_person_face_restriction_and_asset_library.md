---
name: reference-seedance-real-person-face-restriction-and-asset-library
description: Seedance 2.0/2.5（BytePlus ModelArk國際版）真人臉孔審核機制與合法繞過路徑；用戶本人偏寫實AI生成虛擬分身臉孔被真人分類器誤判時的處理依據
metadata:
  type: reference
---

## 錯誤現象
呼叫 image-to-video API 時偏寫實的 AI 生成人臉（非真實存在人物）被拒絕，錯誤碼：
`HTTP 400 InputImageSensitiveContentDetected.PrivacyInformation`
"The request failed because the input image may contain a real person"

**根因**：分類器基於畫面視覺特徵判斷（皮膚紋理/光影/五官立體感），不看圖片來源metadata。偏寫實風格的AI生成人臉在統計特徵上跟真人照片無法區分，會被同一套分類器誤判，這是官方已知現象、非bug。2026農曆年後審核明顯收緊。

## 官方兩套資產庫，性質完全相反，不可混淆
BytePlus ModelArk（國際版，`ark.ap-southeast-1.bytepluses.com`）與火山方舟（中國版Ark，`ark.cn-beijing.volces.com`）是分開產品線但機制文件同源（文件ID相同，如`/docs/ModelArk/2315856`中英對應）。

1. **Real-Person Portrait Library（真人肖像庫）**——要求上傳素材對應「真實存在、可活體驗證的人」，核驗人本人需掃碼+活體檢測。**不適用於純虛構角色**，即使角色由AI生成也一樣，因為驗證的是「這張臉的所有權屬於某個真人」，虛構角色沒有真人可去做活體驗證。
2. **Private Virtual Portrait Library（私有虛擬肖像庫）**——官方文件明文要求上傳素材「must **not** resemble the portrait or likeness of any natural person」，即反過來要求必須是不對應真人的虛構角色。**這才是「自己捏的AI虛構角色」該走的路**，不需要活體驗證。

判斷依據：用途是「代表使用者本人」→走真人庫；用途是「虛構人設/虛擬分身，不對應任何真實存在的人」→走虛擬肖像庫。

## Private Virtual Portrait Library 開通門檻（2026-09查證）
- 需要開通 **Advanced Creation Rights**，其中 **Entry版本免費**（50 asset/50 asset group額度，3 QPM，開放API）；付費版（$14,000/年起）是給企業級百萬資產量產用。
- **卡點**：無論免費或付費版，都要求 **Business（組織）帳號 + 企業實名認證**（上傳公司登記證明正反面、商業登記編號、組織全名）。BytePlus官方文件明寫「Currently, real name registration is limited to organizations」——**個人帳號目前無法自行完成實名認證**，這是平台級限制，非Seedance專屬。
- 使用者（Prismreel專案負責人）已確認有公司實體可用於申請企業實名認證，走此路徑。

## Prismreel實際使用情境（2026-09-14釐清）
非個人用途——Prismreel是公司內部團隊共同經營同一套AI虛構角色，**所有團隊成員目前打的是同一支後端API**做影片生成。這代表：
- 不需要多租戶asset隔離設計，單一/少數Asset Group即可，50 asset額度大機率夠用
- 目前現狀是後端`image_url`直接傳角色圖網址（原圖URL），完全未經過Asset Library，這是每次呼叫都被真人分類器擋下的根因——改成先建asset_id、之後呼叫改傳`asset://<asset_id>`即可解決，不需要改動「所有人打同一支API」的架構本身

## 待驗證風險（2026-09-14，公司已安排執行，尚未有結果）
1. **CreateAsset上傳審核是否等同於image-to-video的人臉分類器**：官方文件只確認Private Virtual Portrait Library"要求素材不像真人"，但未查到「上傳asset這一關的審核跟直接呼叫image-to-video那關是否用同一套/同樣寬鬆的分類器」。存在上傳時就被拒的可能性，**必須用實際角色圖跑一次CreateAsset實測**，不能只憑文件描述假設會過
2. **Basic免費版(非Advanced Entry)是否也需要企業認證**：目前只確認到Advanced Creation Rights系列（含Entry免費版）都寫在同一個要求企業認證的Prerequisites段落下，未獨立查證最基礎的Basic免費層級（50asset/僅限控制台上傳）是否對個人帳號開放，若是則可能有更低成本的過渡方案
3. `Moderation.Strategy: "Skip"`這個上傳時可跳過部分審核的官方參數，未查證是否涵蓋人臉真人判斷本身，濫用有違反服務條款風險

## API使用方式（開通後）
`CreateAssetGroup`→`CreateAsset`上傳圖片(格式jpeg/png/webp/bmp/tiff/gif/heic/heif，寬高比0.4-2.5，長邊300-6000px，單張<30MB)→輪詢`GetAsset`等`Status`變`Active`→呼叫視頻生成API時用`asset://<asset_id>`格式的URI取代原圖URL。

## 不協助的類別（已向使用者明確劃界）
第三方部落格（character-sheet trick/grid overlay等）宣稱靠疊加網格線、色塊干擾人臉偵測器的第一步定位來規避審核——這是對抗性樣本手法，攻擊偵測pipeline上游而非走正規驗證，不論使用者意圖是否正當都不協助操作，僅可說明其原理供理解。
