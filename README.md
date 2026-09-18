# emg-compare.app

比對 **Delsys CSV**、**ZE1 TXT**（自研裝置）與 **ZE2 TXT** 的 EMG 資料。

以 **Streamlit** 提供網頁介面（可部署到 Streamlit Community Cloud）。Canonical 入口是 `streamlit_app.py`。

## 功能（分開操作）

1. **波形疊圖**：Delsys × ZE1 × ZE2 正規化後疊圖（Z-score / Max-abs / 原始值）；ZE1／ZE2 可開 20–400 Hz 帶通
2. **收縮區間**：RMS 峰值法或 ZE1 施密特觸發
3. **特徵比對**：Spectral 或 TTRI/ZE1（含 Δ 與相似度 %）
4. **匯出**：收縮／特徵頁可下載 PDF 與 CSV ZIP

檔案配對支援：
- 手動各選一邊（ZE1／ZE2 可多選）
- 依檔名自動建議（含 ZE2 中文 左/右 + 脛前/腓腸）
- 上傳 CSV / ZE1 TXT / ZE2 TXT

## 本機快速開始

```powershell
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

或雙擊 `run.bat`。依賴含 `scipy`（ZE1／ZE2 帶通）與 `pandas`。

## 怎麼試 ZE2

1. 啟動後側欄應列出 `data/ZE2_txt/` 內的樣本（含子資料夾 `2608/`、`2609-09/`）。
2. 可只跑 **ZE2** 波形／收縮／特徵；或選一個 Delsys CSV + ZE2，按 **一起疊圖**／**一起（含 Δ）**。
3. 沒有本機 Delsys／ZE1 時請從側欄上傳成對檔案；ZE2 樣本已在 repo 內。
4. 側欄 **ZE1 / ZE2 參數** 可改 mV/count 與 ZE2 採樣率（ZE2 預設 1000 Hz、`0.000048` mV/count，仍屬暫定校正）。
5. 特徵 Δ：若同時選了 ZE1 與 ZE2，Δ 仍對 **第一個 ZE1**；只選 ZE2 時 Δ 對 ZE2。

## 部署到 Streamlit Community Cloud

1. 確認 GitHub repo 已推送：https://github.com/frankrita0728-coder/EMG_compare
2. 開啟 [share.streamlit.io](https://share.streamlit.io/) → **Deploy a public app from GitHub**
3. 選擇：
   - Repository：`frankrita0728-coder/EMG_compare`
   - Branch：`master`（或此 ZE2 分支做預覽）
   - Main file path：`streamlit_app.py`
4. Deploy 後網址可設為 `https://emg-compare.streamlit.app`

## 資料放置（本機）

| 資料夾 | 內容 |
|--------|------|
| `data/delsys/` | Delsys 匯出的 `.csv` |
| `data/txt/` | ZE1 自研裝置 `.txt` |
| `data/ZE2_txt/` | ZE2 `.txt`（可放子資料夾；repo 已含樣本） |

開發時若 Delsys／ZE1 本機資料夾為空，會自動讀取：

- `../emgcsv(delsys)/data`
- `../emgtxt2chart/data`

## 結構

```
EMG_compare/
  streamlit_app.py    # Streamlit 入口（雲端 Main file）
  compare.py          # 波形／收縮／特徵流程
  pairing.py          # 檔名標籤與建議配對
  detector.py         # 收縮區間偵測
  features.py         # Spectral / TTRI 特徵
  ze1_algo.py         # ZE1 / TTRI 演算法
  emg_filter.py       # ZE1／ZE2 20–400 Hz 帶通
  parsers/            # Delsys CSV / ZE1 TXT / ZE2 TXT
  data/delsys/        # Delsys CSV
  data/txt/           # ZE1 TXT
  data/ZE2_txt/       # ZE2 TXT 樣本
```
