# EMG Compare

比對 **Delsys CSV**（`emgcsv(delsys)`）與 **自研 TXT**（`emgtxt2chart`）的 EMG 資料。

## 功能（分開操作）

1. **波形疊圖**：兩來源正規化後疊圖（Z-score / Max-abs）
2. **收縮區間**：各自偵測收縮，左右對照
3. **特徵比對**：時長、iEMG、RMS、MDF、MPF、Peak RMS

檔案配對支援：
- 手動各選一邊
- 依檔名自動建議（受試者 / 側別 / 肌肉 / 荷重）

## 快速開始

```powershell
cd C:\Zentan_Rita\EMG_compare
python -m pip install -r requirements.txt
python app.py
```

或雙擊 `run.bat`。

瀏覽器開啟：http://127.0.0.1:8080

## 資料放置

| 資料夾 | 內容 |
|--------|------|
| `data/delsys/` | Delsys 匯出的 `.csv` |
| `data/txt/` | 自研裝置 `.txt` |

開發時若本機資料夾為空，會自動讀取：

- `../測試專案/emgcsv(delsys)/data`
- `../測試專案/emgtxt2chart/data`

## 之後上架（XX.app）

目前是標準 Flask Web App，之後可直接部署到任意支援 Python 的主機／容器，再綁定自訂網域（例如 `https://emg-compare.xx.app`）。

建議後續：
- 用 gunicorn / waitress 當 production server
- 加上上傳檔案 API（不必只靠本機資料夾）
- 設定 HTTPS 與網域

## 結構

```
EMG_compare/
  app.py              # Flask API + 頁面
  compare.py          # 三種比對流程
  pairing.py          # 檔名標籤與建議配對
  detector.py         # 收縮區間偵測
  features.py         # iEMG / RMS / MDF / MPF
  normalize.py        # 波形正規化
  parsers/            # Delsys CSV / TXT 解析
  templates/          # 網頁
  static/             # CSS / JS
  data/delsys/        # Delsys CSV
  data/txt/           # 自研 TXT
```
