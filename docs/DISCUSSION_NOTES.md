# EMG_compare — 討論紀錄與已確認規格

整理自專案開發討論（含相關係數、配對、通道建議等）。技術詞保留 English；產品／UI 用語用繁中。

## 專案定位

- 專案：**EMG_compare** — 比對 Delsys 與自研裝置（ZE1／ZE2）EMG 資料。
- 介面：Streamlit 網頁（可部署 Streamlit Community Cloud）。
- 功能分開操作：波形疊圖｜收縮區間｜特徵｜**相關係數**。

## 資料來源與放置

| 來源 | 資料夾 |
|------|--------|
| Delsys CSV | `data/delsys/` |
| ZE1 TXT | `data/txt/` |
| ZE2 TXT | `data/ZE2_txt/` |

- ZE2／大量資料可依日期或受試者分子資料夾；程式會遞迴掃描。
- 大檔不宜整包 commit；本機／環境放 `data/` 即可。
- 相關分析依側邊欄**當前選取檔**計算；多選 ZE1／ZE2 時各自與 Delsys 成對。

## 相關係數／ICC／TTRI

| 項目 | 約定 |
|------|------|
| 初版特徵相關 | 加在特徵結果（非整段波形相關） |
| 係數 | **Pearson *r*** |
| TTRI | 用 TTRI **滑動視窗**特徵曲線算 *r* |
| 收縮-only | **只對收縮區間內**的窗點算 *r*，排除休息段 |
| 區間摘要 | 另算收縮區間特徵的 Pearson *r* + **ICC(A,1)**（絕對一致） |
| 獨立分頁 | 「相關係數」另開；特徵頁只留 Δ／% |
| 分組顯示 | Delsys（參考）／ZE1／ZE2 分別與 Delsys 比 |

解讀共識：

- **Δ／%**：幅度差；`% = (裝置 / Delsys) × 100`
- **Pearson**：同向／走勢
- **ICC(A,1)**：數值是否真接近（系統性偏低時 ICC 常低於 *r*）

## 自動配對（資料量大時）

使用者選擇：**掃過 `data/` 自動列出可配對的 Delsys–ZE1–ZE2 組合**（優先於側邊欄篩選）。

- 依檔名標籤：受試者／肌肉／側／日期分組
- 「相關係數」分頁可一鍵套用分組選取

## 通道建議（依部位）

ZE2 與 ZE1 **相反**：

| 部位 | ZE1 | ZE2 |
|------|-----|-----|
| 左脛前肌 | Ch1 | Ch2 |
| 左腓腸肌 | Ch2 | Ch1 |
| 右脛前肌 | Ch2 | Ch1 |
| 右腓腸肌 | Ch1 | Ch2 |

- 側邊欄與相關係數分頁會顯示此表
- 自動配對／一鍵套用會**優先選建議通道**
- 側邊欄「依通道建議篩選目前選取」可手動套用

## 單位／換算／濾波（摘要）

- Delsys：數值當 **mV**（不做倍率轉換）
- ZE1／ZE2：`mV/count` 等係數側欄可調；ZE2 預設曾設為約 `0.000048`
- ZE1／ZE2 分析前：**20–400 Hz** 帶通（Butterworth、零相位）；特徵比對固定用濾波後資料
- Y 軸顯示：**mV**

## 韌體／nRF52832（討論方向，非正式規格書）

- 收縮區間判定適合做在韌體（濾波 → envelope → Schmitt → BLE 事件）
- 時域特徵（RMS／iEMG／AEMG）可上韌體；MPF／MDF 宜精簡或改 App 算
- 多檔比對、報表、長緩衝後處理不建議塞進 nRF52832

## 相關文件

- 初版相關計畫：[`plans/feature_correlation_coeffs.md`](plans/feature_correlation_coeffs.md)
- 實作入口：`streamlit_app.py`、`features.py`、`pairing.py`、`compare.py`
