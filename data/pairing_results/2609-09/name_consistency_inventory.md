# 名稱一致性一對一配對清單

- Delsys：1　ZE1：1　ZE2：6
- 肌群部位：2　一對一可比對：1

> 規則：每個 Delsys CSV 最多配 **1 個 ZE1**、**1 個 ZE2**。 ZE1 需同受試者／肌肉／側，且場次碼（如 a09）相同； ZE2 無場次碼時只要同受試者／肌肉／側即可與 Delsys 一對一比對。

## 全肌群部位總表

| 狀態 | 受試者 | 肌肉 | 側 | 通道建議 | Delsys | ZE1（建議Ch） | ZE2（建議Ch） |
|------|--------|------|----|----------|--------|---------------|---------------|
| 待補 Delsys | Frank | 脛前肌 | 右 | 右脛前肌 → ZE1 Ch2／ZE2 Ch1 | `—` | `—` | `09-09_11-27-57_319_Ch1(frank右脛前肌).txt; 09-09_11-30-01_689_Ch1(frank右脛前肌).txt` |
| complete | Frank | 脛前肌 | 左 | 左脛前肌 → ZE1 Ch1／ZE2 Ch2 | `2609-09 frank左脛前肌(Delsys)_with_a09_1.csv` | `09-09_09-41-19_786_ExgCh2Data_(Frank 左脛前肌)_a09_褲XL_1.txt` | `09-03_11-44-33_364_Ch2(Frank 左脛前肌).txt` |

## 一對一可比對組合（Delsys ↔ ZE1 / ZE2）

| 狀態 | 完整度 | 受試者 | 肌肉 | 側 | 場次 | 日期 | Delsys | ZE1 | ZE2 | 備註 |
|------|--------|--------|------|----|------|------|--------|-----|-----|------|
| 可比對 | complete | Frank | 脛前肌 | 左 | a09 | 09-09 | `2609-09 frank左脛前肌(Delsys)_with_a09_1.csv` | `09-09_09-41-19_786_ExgCh2Data_(Frank 左脛前肌)_a09_褲XL_1.txt` | `09-03_11-44-33_364_Ch2(Frank 左脛前肌).txt` | ZE1一對一 score=140（Frank / 脛前肌 / 左 / a09 / 09-09 / #1｜建議ZE1 Ch1）；ZE2一對一 score=115（Frank / 脛前肌 / 左｜建議ZE2 Ch2） |

## 待補 Delsys CSV 才能完整比對

- **Frank 右脛前肌**：請放入對應 Delsys CSV；目前 ZE2 建議檔 `09-09_11-27-57_319_Ch1(frank右脛前肌).txt; 09-09_11-30-01_689_Ch1(frank右脛前肌).txt`

## Delsys ↔ ZE1 建議分數

- score=148｜`2609-09 frank左脛前肌(Delsys)_with_a09_1.csv` ↔ `09-09_09-41-19_786_ExgCh2Data_(Frank 左脛前肌)_a09_褲XL_1.txt`｜Frank / 脛前肌 / 左 / a09 / 09-09 / #1

## Delsys ↔ ZE2／三方建議

- [complete] score=258｜D:`2609-09 frank左脛前肌(Delsys)_with_a09_1.csv` × ZE1:`09-09_09-41-19_786_ExgCh2Data_(Frank 左脛前肌)_a09_褲XL_1.txt` × ZE2:`09-09_11-27-57_319_Ch1(frank右脛前肌).txt`｜左脛前肌 → ZE1 Ch1／ZE2 Ch2
