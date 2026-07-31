# emg-compare.app

比對 **Delsys CSV**（`emgcsv(delsys)`）與 **自研 TXT**（`emgtxt2chart`）的 EMG 資料。

以 **Streamlit** 提供網頁介面（可部署到 Streamlit Community Cloud）。

## 功能（分開操作）

1. **波形疊圖**：兩來源正規化後疊圖（Z-score / Max-abs / 原始值）
2. **收縮區間**：RMS 峰值法或 ZE1 施密特觸發
3. **特徵比對**：Spectral 或 TTRI/ZE1（含 Δ）

檔案配對支援：
- 手動各選一邊（TXT 可多選）
- 依檔名自動建議
- 上傳 CSV / TXT（雲端部署建議用上傳）

## 本機快速開始

```powershell
cd C:\Zentan_Rita\測試專案\EMG_compare
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

或雙擊 `run.bat`。

## 部署到 Streamlit Community Cloud

1. 確認 GitHub repo 已推送：https://github.com/frankrita0728-coder/EMG_compare
2. 開啟 [share.streamlit.io](https://share.streamlit.io/) → **Deploy a public app from GitHub**
3. 選擇：
   - Repository：`frankrita0728-coder/EMG_compare`
   - Branch：`master`
   - Main file path：`streamlit_app.py`
4. Deploy 後會得到類似 `https://xxxx.streamlit.app` 的網址
5. （可選）在 App settings → **Custom domain** 綁定例如 `emg-compare.xx.app`（需你已擁有該網域並依指示設定 DNS）

雲端沒有本機 `data/` 時，請在側邊欄 **上傳檔案**。

## 資料放置（本機）

| 資料夾 | 內容 |
|--------|------|
| `data/delsys/` | Delsys 匯出的 `.csv` |
| `data/txt/` | 自研裝置 `.txt` |

開發時若本機資料夾為空，會自動讀取：

- `../emgcsv(delsys)/data`
- `../emgtxt2chart/data`

## 結構

```
EMG_compare/
  streamlit_app.py    # Streamlit 入口（雲端 Main file）
  compare.py          # 三種比對流程
  pairing.py          # 檔名標籤與建議配對
  detector.py         # 收縮區間偵測
  features.py         # Spectral / TTRI 特徵
  ze1_algo.py         # ZE1 / TTRI 演算法
  parsers/            # Delsys CSV / TXT 解析
  data/delsys/        # Delsys CSV
  data/txt/           # 自研 TXT
```
