# 台灣停電地圖（免費優先 MVP）

以 Leaflet 顯示行政區地圖，整合台電官方公開的災情停電與計畫性工作停電資料，透過 GitHub Actions 定時產生 `data/outages.json`，由 GitHub Pages 靜態託管。

## 官方資料來源（免 API Key）
- 災情停電 XML：<https://service.taipower.com.tw/data/opendata/apply/file/d006012/001.xml>
- 災情停電 KML 備援：<https://service.taipower.com.tw/data/opendata/apply/file/d006012/001.kml>
- 計畫性工作停電 ZIP：<https://service.taipower.com.tw/data/opendata/apply/file/d077004/001.zip>
- 官方資料集說明：<https://data.gov.tw/dataset/44799>、<https://data.gov.tw/dataset/26144>

## 重要限制
1. 災情資料官方說明為災害期間約每小時更新、平時不更新；施工停電資料標示每日更新。GitHub 排程只是「嘗試抓取」頻率，不會讓官方資料變得更即時。
2. 這是公開資料視覺化，不是台電官方服務。資料空白不代表正常供電。
3. 台電來源的 ZIP 內部表格格式可能調整；如果解析器無法識別欄位，請查看 Actions 日誌並更新 `scripts/update_data.py` 的欄位別名。
4. 鄉鎮著色依資料內文字描述推測對應行政區。若官方只提供文字範圍、沒有座標，不能保證精確到街道或建築；沒有成功解析的事件仍會出現在事件清單（若資料列被解析）。
5. 底圖使用 OpenStreetMap，行政區 GeoJSON 暫用公開的 `ronnywang/twgeojson` 來源；這是第三方資料，不是台電資料。上游網址或屬性欄位變動時，需調整 `index.html` 中的 GeoJSON URL/欄位名稱。

## 部署步驟

### 1. 建立 GitHub repository
1. 登入 GitHub，建立新的公開 repository，例如 `taiwan-outage-map`。
2. 將此資料夾內的所有檔案上傳到 repository 根目錄。可用 GitHub 網頁的 **Add file → Upload files**，或電腦安裝 Git 後推送。
3. 確認以下檔案位於正確位置：
   - `index.html`
   - `data/outages.json`
   - `scripts/update_data.py`
   - `.github/workflows/update.yml`

### 2. 執行第一次資料更新
1. 打開 repository 的 **Actions**。
2. 若提示需要啟用 workflow，按 **I understand my workflows, go ahead and enable them**。
3. 選擇 **Update Taiwan outage data** → **Run workflow** → **Run workflow**。
4. 等待工作完成，進入執行紀錄檢查 `Emergency records`、`Planned records` 和是否有錯誤。
5. 若任一官方來源下載或解析失敗，查看日誌；若兩個來源都失敗，工作會故意失敗且不覆蓋上一份資料。

### 3. 開啟 GitHub Pages
1. repository → **Settings → Pages**。
2. 在 **Build and deployment** 選 **Deploy from a branch**。
3. Branch 選 `main`，資料夾選 `/(root)`，按 **Save**。
4. 等待部署完成後，Pages 頁面會顯示網址，通常是 `https://你的帳號.github.io/taiwan-outage-map/`。
5. 開啟網址；如果剛剛才更新資料，等 Pages 部署完成後重新整理。

### 4. 自動更新
Workflow 已設定每小時 UTC 的 00、20、40 分執行（台灣時間每小時 08、28、48 分）。GitHub 排程不是精準即時服務，尖峰時可能延遲；官方來源也可能較久才更新。你可以在 Actions 手動執行。

## 本機測試（Windows）
安裝 Python 3.11+，在專案根目錄開啟終端機：
```powershell
py -m pip install openpyxl xlrd
py scripts/update_data.py
py -m http.server 8000
```
瀏覽器開啟 `http://localhost:8000`。不要直接雙擊 `index.html`，因為瀏覽器可能限制 `fetch()` 讀取本機 JSON。

## 常見問題
- **Actions 的資料來源下載失敗**：官方網址可能短暫不可用或限制自動請求；檢查日誌，不要把失敗當作無停電。
- **地圖沒變色**：事件範圍文字可能無法準確匹配鄉鎮名稱。請先看右側事件清單，再檢查 `county_town()` 與 GeoJSON 欄位名稱。
- **施工停電 ZIP 解析出 0 筆**：檢查 ZIP 內檔名、工作表與標題列；必要時擴充 `decode_table()` 支援的檔案格式及欄位別名。
- **GitHub Pages 沒更新**：確認 Pages 部署完成，且瀏覽器重新載入；資料檔網址使用 query string 避免快取。
- **GitHub Actions 沒按時執行**：排程可能延遲；GitHub 也可能停用長期無活動 repository 的排程，需定期查看 Actions。

## 授權與責任
官方資料依政府資料開放授權條款使用；請保留來源連結。第三方底圖/邊界資料另依其授權使用。此專案不提供停電保證或緊急通報服務。
