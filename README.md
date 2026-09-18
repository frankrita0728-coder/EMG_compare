# emg-compare.app

比對 **Delsys CSV** 與自研 **ZE1／ZE2 TXT** 的 EMG 資料。

以 **Streamlit** 提供網頁介面（可部署到 Streamlit Community Cloud）。

## 功能（分開操作）

1. **波形疊圖**：兩來源正規化後疊圖（Z-score / Max-abs / 原始值）
2. **收縮區間**：RMS 峰值法或 ZE1 施密特觸發
3. **特徵比對**：Spectral 或 TTRI/ZE1（含 Δ／%）
4. **相關係數**：收縮區間內 TTRI 曲線 Pearson *r*、區間摘要 Pearson *r* + ICC(A,1)

檔案配對支援：
- 手動各選一邊（ZE1／ZE2 可多選）
- 依檔名自動建議、掃描可配對分組
- 依部位的 ZE1／ZE2 **通道建議**
- 上傳 CSV / TXT

討論中已確認的規格與決策見 [`docs/DISCUSSION_NOTES.md`](docs/DISCUSSION_NOTES.md)。

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
4. Deploy 後網址可設為 `https://emg-compare.streamlit.app`

## 資料放置（本機）

| 資料夾 | 內容 |
|--------|------|
| `data/delsys/` | Delsys 匯出的 `.csv` |
| `data/txt/` | ZE1 `.txt` |
| `data/ZE2_txt/` | ZE2 `.txt`（可分子資料夾） |

開發時若本機 Delsys／ZE1 資料夾為空，會自動讀取：

- `../emgcsv(delsys)/data`
- `../emgtxt2chart/data`

## 結構

```
EMG_compare/
  streamlit_app.py    # Streamlit 入口（雲端 Main file）
  compare.py          # 比對流程
  pairing.py          # 檔名標籤、配對與通道建議
  detector.py         # 收縮區間偵測
  features.py         # Spectral / TTRI / Pearson / ICC
  ze1_algo.py         # ZE1 / TTRI 演算法
  parsers/            # Delsys / ZE1 / ZE2 解析
  docs/               # 討論紀錄與計畫
  data/delsys/        # Delsys CSV
  data/txt/           # ZE1 TXT
  data/ZE2_txt/       # ZE2 TXT
```
