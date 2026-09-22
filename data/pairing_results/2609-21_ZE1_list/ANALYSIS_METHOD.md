# 分析設定（本批結果用此配方）

來源清單：`ze1_source_list.xlsx`

## 參數

| 項目 | 值 |
|------|----|
| 收縮判斷 | `ze1_schmitt` — ZE1 施密特觸發（Schmitt trigger） |
| 特徵計算 | `ttri` — TTRI（AEMG + 滑動窗 RMS/iEMG/MPF/MDF） |
| 區間一致性 | Pearson r, ICC(A,1)；跨收縮區間特徵（同 index 配對） |
| 序列相關 | TTRI 滑動窗 Pearson r（僅 Delsys/對照收縮區間內） |
| ZE1 換算 | TXT × 0.00026 mV/count |
| ZE2 取樣率 | 1000.0 Hz |
| ZE2 換算 | ×4.8e-05 mV/count |
| ZE2 濾波 | 20–400 Hz（apply_bandpass=True） |
| a10 濾波 | 20–400 Hz（僅 a10 實驗組 TXT） |

## 預期收縮次數（依實驗目的）

| 實驗目的 | expected_count |
|----------|----------------|
| 裝置比對 | **3** |
| 刮腿毛 | **3** |
| 疲勞 | **10** |
| （其他／未列） | **3** |

> 疲勞分析固定抓 **10 次收縮**；裝置比對／刮腿毛為 **3 次**。

## 各實驗目的呼叫的函式

| 實驗目的 | 管線 |
|----------|------|
| 裝置比對（a09 / a10） | `build_feature_compare(Delsys CSV × ZE1 TXT；a10 實驗組 20–400 Hz 帶通)` |
| 裝置比對（ze2） | `build_feature_compare_ze2(Delsys CSV × ZE2 TXT)` |
| 刮腿毛 | `build_feature_compare_txt_pair(ZE1 TXT × ZE1 TXT)` |
| 疲勞 | `build_feature_compare(Delsys CSV × ZE1 TXT；expected_count=10)` |

## 輸出欄位說明（summary.csv）

- `rms_pearson_r` / `rms_icc` / `iemg_pearson_r` / `iemg_icc`：收縮區間一致性
- `ttri_rms_r` / `ttri_iemg_r`：TTRI 滑動窗序列 Pearson r
- `ref_count` / `exp_count`：對照組／實驗組偵測到的收縮段數
- `contraction_method` / `feature_method` / `expected_count`：本列實際使用的分析參數
- `fatigue_visible` / `fatigue_ref` / `fatigue_exp`：僅「疲勞」列——這一次能否看出疲勞（綜合／對照／實驗）

## 獨立匯出

重跑後會額外產生 **`analysis_results.xlsx`**（可單獨帶走）：
- 工作表 `總覽`：全列摘要（含一致性、疲勞可視）
- 工作表 `疲勞可視`：僅疲勞列 + 判定依據
- 工作表 `區間特徵`：每段收縮的對照／實驗特徵
- 工作表 `區間一致性`：各指標 Pearson r / ICC

Streamlit「特徵」分頁載入 Excel 清單分析後，也可直接下載同一格式。

## 疲勞可視性（僅 purpose=疲勞）

跨連續收縮看 **MPF／MDF 是否下降**（頻譜向低頻移動＝典型 EMG 疲勞訊號）；
RMS／AEMG 上升為輔助證據。詳細規則見 `FATIGUE_VISIBILITY.md`。

## 收縮區間修正

相對「第一段起點常停在 6.0 秒」的上一批，偵測多了兩步（`ze1_algo.py`）：

1. **起點前追**：門檻在 6 秒才生效時，若第一段當時已經高過門檻，起點往前追。最早不超過門檻前 3 秒，也不早於 3.0 秒。
2. **底噪重切**：0.25 秒 RMS 有八成以上時間貼在高位、且高低對比夠大時，改依 RMS 包絡重切（`rms_envelope`）。

受影響的列見同目錄 `INTERVAL_CHANGES.md`，並寫入 `analysis_results.pdf` 的「收縮區間調整」。

重跑指令：

```bash
python3 scripts/run_ze1_list_compare.py --xlsx <list.xlsx>
```
