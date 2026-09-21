# data/ 資料夾結構（整理後）

```
data/
  delsys/2609-09/      # Delsys CSV（_with_a09_ / _with_ZE2_）
  txt/2609-09/         # ZE1 TXT
  ZE2_txt/2609-09/     # ZE2 TXT（本 session 量測）
  ZE2_txt/2608/        # 舊 session（校準等）
  pairing_results/
    ANALYSIS_PLAN.md       # 分析規格與檔名規則
    如何同步到本機.md       # 本機 ↔ 雲端
    本機整理還原.md         # 本機混亂時重來
    2609-09/               # 分析輸出（唯一結果夾）
```

## 規則

1. **量測檔只放 session 子資料夾**（例如 `2609-09/`），不要散落在 `delsys/` / `txt/` / `ZE2_txt/` 根目錄。
2. **ZE2 比對**用 Delsys：`…(Delsys)_with_ZE2_1.csv`
3. **a09 比對**用 Delsys：`…(Delsys)_with_a09_1.csv`
4. **分析結果**只看 `pairing_results/2609-09/`，不要在根目錄再放一份。

## 本機很亂時

見 `pairing_results/本機整理還原.md`，或執行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\recover_local.ps1
```
