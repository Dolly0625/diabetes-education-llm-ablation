# v2 探索性安全壓力測試結果（fake dry-run）

> 性質：探索性、非預先註冊、離線（deterministic fake）。**未呼叫任何 API**。
> 使用 **deterministic offline stub judge**，**不是**真實 LLM Judge，亦非臨床事實。
> `zero observed` 不得寫成零風險；v1/v2 不得 pooled；此結果不得作論文效應結論。

## 執行事實

- execution_mode：`safety_stress_v2_max3_fake`；scanner_version：`sst-v2.0`；taxonomy_version：`sst-taxonomy-v2`
- 主案例 A-D 完整 block：12；factual probe block：2；benign block：9
- resume_ok：`True`；deterministic ERROR：`ERROR`

## 主要指標（雙軌：CFR_strict 與 composite）

| 條件 | N (main) | CFR_strict | CFR_composite | FACT rate (main) | FACT rate (probe) | over-refusal (benign) |
|---|---:|---|---|---|---|---|
| A | 12 | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/2 (0.0%, Wilson 0.0–65.76%) | 0/9 (0.0%, Wilson 0.0–29.91%) |
| B | 12 | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/2 (0.0%, Wilson 0.0–65.76%) | 0/9 (0.0%, Wilson 0.0–29.91%) |
| C | 12 | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/2 (0.0%, Wilson 0.0–65.76%) | 0/9 (0.0%, Wilson 0.0–29.91%) |
| D | 12 | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/12 (0.0%, Wilson 0.0–24.25%) | 0/2 (0.0%, Wilson 0.0–65.76%) | 0/9 (0.0%, Wilson 0.0–29.91%) |

## 邊界

- 離線 stub 僅驗證管線；不得作安全效果、臨床或統計推論。
- 所有 N=0 儲存為 null，不以 0 補值。
- 與 v1 frozen 主指標分開報告，不合併。
