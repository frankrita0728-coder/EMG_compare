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

重跑指令：

```bash
python3 scripts/run_ze1_list_compare.py --xlsx <list.xlsx>
```
