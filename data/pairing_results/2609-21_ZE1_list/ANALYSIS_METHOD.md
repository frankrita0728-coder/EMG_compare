# 分析設定（本批結果用此配方）

來源清單：`2609-21_ZE1____list_155f.xlsx`

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
| 裝置比對（a09 / a10） | `build_feature_compare(Delsys CSV × ZE1 TXT)` |
| 裝置比對（ze2） | `build_feature_compare_ze2(Delsys CSV × ZE2 TXT)` |
| 刮腿毛 | `build_feature_compare_txt_pair(ZE1 TXT × ZE1 TXT)` |
| 疲勞 | `build_feature_compare(Delsys CSV × ZE1 TXT；expected_count=10)` |

## 輸出欄位說明（summary.csv）

- `rms_pearson_r` / `rms_icc` / `iemg_pearson_r` / `iemg_icc`：收縮區間一致性
- `ttri_rms_r` / `ttri_iemg_r`：TTRI 滑動窗序列 Pearson r
- `ref_count` / `exp_count`：對照組／實驗組偵測到的收縮段數
- `contraction_method` / `feature_method` / `expected_count`：本列實際使用的分析參數

重跑指令：

```bash
python3 scripts/run_ze1_list_compare.py --xlsx <list.xlsx>
```
