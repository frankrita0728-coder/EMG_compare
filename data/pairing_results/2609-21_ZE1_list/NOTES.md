# 清單備註（重跑）

1. **第 15 列缺對照組**：右腓腸肌 a09 第 2 次只有實驗組 TXT，沒有 Delsys 對照 CSV → 未執行。
2. **第 17 列已修正**：對照組改為 `2609-09 frank右腓腸肌(Delsys)_with_a10_2.csv`（先前誤寫左脛前肌）。
3. **右腓腸肌 ZE2 Delsys**：清單 `with_ze2_` 對上實際檔名 `with_ZE2_`（大小寫）。
4. **門檻問題列**：詳見 `PROBLEM_THRESHOLDS.md`。曾缺段的 #6 / #8 / #27 / #37 已全部達標。
5. **疲勞可視性**：詳見 `FATIGUE_VISIBILITY.md`。依跨收縮 MPF/MDF 下降（及 RMS/AEMG 上升輔助）判定「這一次能否看出疲勞」。
6. **獨立匯出**：`analysis_results.xlsx` / `analysis_results.pdf`（總覽／收縮區間調整／裝置比對波形／疲勞可視／區間特徵）可單獨下載，不必翻 JSON 資料夾。
7. **收縮區間調整**：見 `INTERVAL_CHANGES.md`，並收在 PDF「收縮區間調整」。起點前追 39 側；底噪整段重切是第 20 列 ZE1、第 21 列 ZE1、第 29 列 Delsys（第 20 與第 29 是同一份左腓腸肌 a09）。第 22、23 列 a10 實驗組仍是 2 段，這次沒有改它們的時間。

分析配方見 `ANALYSIS_METHOD.md`：
- 裝置比對／刮腿毛：Schmitt + TTRI，預期 **3** 段
- 疲勞：Schmitt + TTRI，預期 **10** 段；並輸出疲勞可視性（是／弱／否）

## Schmitt 門檻調整（`ze1_algo.py`）

### Delsys
- `threshold_std_k`：4.0 → **3.0**
- 暖機改找較安靜的 32-bin 窗（`threshold_prefer_quiet`）
- 門檻啟動時間：3 s → **6 s**
- 第 37 列（右腓腸肌疲勞 2）因此可由 0 段 → **10/10**

### TXT / ZE2（`legacy_mv`）
- `threshold_std_k`：4.0 → **2.0**
- 同樣啟用 quiet warm-up + ready **6 s**
- 新增 `threshold_cap`：**0.05**（避免噪聲窗把 thr 拉到 0.1+）
- 第 6 列 ZE2：0 → **3/3**；第 8／27 列 TXT：2 → **3/3**
