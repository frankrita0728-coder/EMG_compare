# 2609-09 資料命名與三項分析說明

## 分析結果（三項）

1. **裝置比對**（每個肌群各做）
   - `a09` vs Delsys
   - `a10` vs Delsys
   - `ZE2` vs Delsys  
   輸出：`data/pairing_results/2609-09/01_device_compare/`

2. **刮腿毛比對**
   - `a09`（刮毛前） vs Delsys
   - `a09`（刮腿毛後） vs Delsys  
   輸出：`data/pairing_results/2609-09/02_shave_compare/`

> 實務上「裝置比對」含 3 種子比對；「刮腿毛」含 2 條件。索引見 `STUDY_INDEX.md`。

## 建議資料夾

```
data/
  delsys/2609-09/
  txt/2609-09/          # ZE1（含 a09 / a10 / 刮腿毛）
  ZE2_txt/2609-09/
  pairing_results/2609-09/
```

## 檔名關鍵字

| 用途 | 檔名需含 |
|------|----------|
| ZE1 裝置 a09 | `a09` |
| ZE1 裝置 a10 | `a10` |
| ZE2 裝置（Delsys 參考） | `_with_ZE2_`（例：`…(Delsys)_with_ZE2_1.csv`） |
| ZE1 裝置（Delsys 參考） | `_with_a09_` / `_with_a10_` |
| 刮腿毛後 | `刮腿毛` / `刮腿毛後` / `去腿毛` / `shaved` |
| 刮毛前（可選） | `刮腿毛前` / `unshaved` |
| 肌群（固定四部位） | `左脛前肌` `右脛前肌` `左腓腸肌` `右腓腸肌` |
| 通道 | `Ch1` / `Ch2` / `ExgCh1` / `ExgCh2` |

Delsys 範例：
- a09 參考：`2609-09 frank左脛前肌(Delsys)_with_a09_1.csv`
- ZE2 參考：`2609-09 frank右腓腸肌(Delsys)_with_ZE2_1.csv`  

ZE1 範例：`..._(Frank 左脛前肌)_a09_...txt`、`..._a10_...txt`、`..._a09_刮腿毛後_...txt`

> **重要**：`ze2_vs_delsys` 只會選 `_with_ZE2_` 的 Delsys，不會拿 `_with_a09_` 去對 ZE2。

## 本機重跑

```powershell
python scripts/run_study_analyses.py --session 2609-09
```
