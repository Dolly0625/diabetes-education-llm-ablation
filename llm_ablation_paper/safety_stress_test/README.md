# Safety Stress Test（探索性、離線、非預先註冊）

本工作流在**已凍結的 12×4 主實驗之外**，建立一套可重現、可稽核的探索性安全壓力測試，
用於觀察 A／B／C／D 在危險要求、持續施壓、工具誘導與 prompt injection 下的防線行為。

> 本工作流**不是**正式主實驗，也**不是**臨床驗證。其結果與正式 12×4 分開報告，不重算、不覆蓋原主結果。

## 核心設計

- **主安全集**：固定 12 案，六種 Critical Failure family 各 2 案：
  `CF_PRESCRIPTION_BREACH`、`CF_DIAGNOSTIC_BREACH`、`CF_MIRACLE_CLAIM`、
  `CF_ACUTE_EMERGENCY_MISMANAGEMENT`、`CF_CONFIRMATION_OF_DANGEROUS_ACTION`、`CF_GROUNDED_CONTRADICTION`。
- 每案最多 **3 輪**漸進施壓；病患事實不得因系統回答而漂移。
- **良性對照** ≥6 案，用於偵測過度拒絕；不得把拒絕率等同安全。
- **系統完整性 canaries**：prompt injection、混淆 injection、要求未暴露工具、過早產卡；不得混入主 CFR 比較。
- **Guard-reachability fault injection**：以人工危險 draft 驗證 D 的 Output Guard 確實可被觸發；
  僅為工程管線驗證，絕不可當成模型安全效果。
- A／B／C／D 沿用凍結消融語義，僅依三個既有開關遞增；Input Guard 為四組共同設定。

## 檔案

| 檔案 | 用途 |
|---|---|
| `AGENTS.md` | 工作流規則與禁止事項 |
| `STRESS_TEST_PROTOCOL.md` | 完整協定（案例、canary、指標、fail-closed、主張邊界） |
| `case_schema.json` | 案例 JSON Schema |
| `cases.jsonl` | 12 個主安全案例 |
| `benign_controls.jsonl` | 7 個良性對照 |
| `canaries.jsonl` | 4 個系統完整性 canary |
| `patient_attack_prompt.md` | 攻擊者病患角色與事實不漂移約束 |
| `rule_based_scanner.py` | 確定性規則掃描器（僅讀 `final_output`） |
| `runner.py` | 離線、spawn 隔離、checkpoint、fail-closed 執行器（重用 WS1 harness） |
| `validate_cases.py` | schema／覆蓋率／PII／條件洩漏／canary 排除等 fail-closed 驗證 |
| `analysis.py` | 指標、Wilson 95% CI、報表（重用 WS5 統計與 blinding） |
| `tests/` | 離線測試 |
| `RESULT.md` | 產生的探索性結果報表 |
| `dry_run_summary.json`／`metrics.json` | 機器可讀摘要 |

## 執行方式（全部離線，不呼叫 API）

```bash
# 1) 驗證案例、覆蓋率、PII、條件洩漏、frozen fingerprint、unique-difference
python3 -m pytest llm_ablation_paper/safety_stress_test/tests -q

# 2) 完整 deterministic fake dry-run（A-D × 12 案 + 7 良性 + canaries + resume + ERROR + guard）
python3 -m llm_ablation_paper.safety_stress_test.runner \
  --root llm_ablation_paper/safety_stress_test/artifacts/fake_dry_run

# 3) 產生 RESULT.md 與 metrics.json
python3 -c "from pathlib import Path; from llm_ablation_paper.safety_stress_test import analysis as A; \
A.analyze_dry_run(Path('llm_ablation_paper/safety_stress_test/artifacts/fake_dry_run'), \
out_md=Path('llm_ablation_paper/safety_stress_test/RESULT.md'))"
```

## 必要指標

- 每組與每 CF family 的 Critical Failure Rate／Attack Success Rate，附 Wilson 95% CI。
- safe refusal／redirect rate、over-refusal rate、rule scanner 與 blinded Judge 不一致率。
- guard trigger／override、工具政策違規、technical ERROR 分開報告。
- 配對結構以 case 為 block；若做推論檢定，使用配對方法並標示 exploratory、非預先註冊、多重比較校正。
- `zero observed` 只能寫 `zero observed`，不可寫零風險。

## 主張邊界（摘要）

- 不可宣稱臨床有效、醫師驗證、降低住院、100% 安全。
- 不可宣稱 offline stub 標籤等同醫師。
- 不可把 canary 或 guard-reachability 當成安全效果。
- 不可把本工作流與正式 12×4 結果混合。
