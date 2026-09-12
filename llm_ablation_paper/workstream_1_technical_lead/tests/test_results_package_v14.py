# -*- coding: utf-8 -*-
"""PHASE M4.3 最終交付封裝驗證測試套件。

驗證項目：
1. results/v14 目錄完整性與 MANIFEST.sha256 校驗碼一致性。
2. summary.json、results.csv、main_table.md、main_table.tex 之 A–D 各組 N=12 且指標數字嚴格對齊。
3. 公開交付成果機密與個資掃描（零金鑰、零 COND-、零 raw_response、零內部絕對路徑）。
4. .gitignore 排除規則正確性（排除敏感產物，不影響 results/v14 與已追蹤檔案）。
"""

import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_V14_DIR = REPO_ROOT / "llm_ablation_paper" / "results" / "v14"


def test_results_v14_directory_and_manifest_integrity():
    """驗證 results/v14 目錄結構與 MANIFEST.sha256 校驗碼。"""
    assert RESULTS_V14_DIR.exists(), f"results/v14 目錄不存在: {RESULTS_V14_DIR}"
    assert RESULTS_V14_DIR.is_dir(), "results/v14 必須為目錄"

    expected_files = {
        "summary.json",
        "results.csv",
        "main_table.md",
        "main_table.tex",
        "failure_distribution.png",
        "RUN_REPORT.md",
        "MANIFEST.sha256",
    }
    actual_files = {p.name for p in RESULTS_V14_DIR.iterdir() if p.is_file()}
    assert expected_files.issubset(actual_files), f"缺少必要公開檔案: {expected_files - actual_files}"

    manifest_path = RESULTS_V14_DIR / "MANIFEST.sha256"
    assert manifest_path.exists(), "MANIFEST.sha256 不存在"

    manifest_lines = [
        line.strip()
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(manifest_lines) >= 6, "MANIFEST.sha256 條目不足"

    manifest_dict = {}
    for line in manifest_lines:
        parts = line.split(maxsplit=1)
        assert len(parts) == 2, f"MANIFEST.sha256 格式異常: {line}"
        sha256_hash, filename = parts[0], parts[1].strip()
        manifest_dict[filename] = sha256_hash

    # 驗證每個檔案之實際 SHA-256
    for filename, recorded_sha in manifest_dict.items():
        file_path = RESULTS_V14_DIR / filename
        assert file_path.exists(), f"MANIFEST 記載之檔案不存在: {filename}"
        calculated_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert calculated_sha == recorded_sha, (
            f"檔案 {filename} 校驗碼不符: 記錄值 {recorded_sha} vs 實際值 {calculated_sha}"
        )


def test_results_v14_data_alignment():
    """驗證 summary.json、results.csv、main_table.md、main_table.tex 數據嚴格對齊。"""
    # 1. 讀取 summary.json
    summary_path = RESULTS_V14_DIR / "summary.json"
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_by_group = summary_data["summary_by_group"]

    conditions = ["A", "B", "C", "D"]
    for c in conditions:
        assert c in summary_by_group, f"summary.json 缺少條件 {c}"
        group_data = summary_by_group[c]
        assert group_data["sample_size"] == 12, f"條件 {c} sample_size 必須為 12"
        assert group_data["programmatic_sample_size"] == 12, f"條件 {c} programmatic_sample_size 必須為 12"
        assert group_data["critical_failure_rate"] == 0.0, f"條件 {c} CFR 必須為 0.0"

    # 2. 讀取 results.csv
    csv_path = RESULTS_V14_DIR / "results.csv"
    with csv_path.open(encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 4, f"results.csv 行數必須為 4 (A–D)，實得 {len(reader)}"

    csv_data = {}
    for row in reader:
        c = row["Condition"]
        assert c in conditions, f"results.csv 出現未知條件: {c}"
        csv_data[c] = row
        assert int(row["N"]) == 12, f"results.csv 條件 {c} 之 N 必須為 12"
        assert row["Critical_Failure_Rate"] == "0.0%", f"results.csv 條件 {c} 之 CFR 必須為 0.0%"

    # 比對 CSV 與 summary.json 數值一致性
    for c in conditions:
        grp = summary_by_group[c]
        c_row = csv_data[c]
        assert float(c_row["Safety"]) == pytest.approx(grp["scores_mean"]["safety"], abs=1e-2)
        assert float(c_row["Tool_Use"]) == pytest.approx(grp["scores_mean"]["tool_use"], abs=1e-2)
        assert float(c_row["State_Consistency"]) == pytest.approx(grp["scores_mean"]["state_consistency"], abs=1e-2)
        assert float(c_row["Dialogue_Planning"]) == pytest.approx(grp["scores_mean"]["dialogue_planning"], abs=1e-2)
        assert float(c_row["Helpfulness"]) == pytest.approx(grp["scores_mean"]["helpfulness"], abs=1e-2)
        assert float(c_row["Avg_Questions_Per_Turn"]) == pytest.approx(grp["programmatic"]["avg_questions_per_turn"], abs=1e-2)
        assert float(c_row["Avg_Latency_ms"]) == pytest.approx(grp["programmatic"]["avg_latency_ms"], abs=1e-1)

    # 3. 讀取 main_table.md 並確認 A–D N=12
    md_path = RESULTS_V14_DIR / "main_table.md"
    md_text = md_path.read_text(encoding="utf-8")
    for c in conditions:
        pattern = rf"\|\s*{c}\s*\|\s*12\s*\|\s*0\.0%"
        assert re.search(pattern, md_text), f"main_table.md 中缺少條件 {c} (N=12, CFR 0.0%) 的對齊行"

    # 4. 讀取 main_table.tex 並確認 A–D N=12
    tex_path = RESULTS_V14_DIR / "main_table.tex"
    tex_text = tex_path.read_text(encoding="utf-8")
    for c in conditions:
        pattern = rf"(?:^|\n){c}\s*&\s*12\s*&\s*0\.0\\%"
        assert re.search(pattern, tex_text), f"main_table.tex 中缺少條件 {c} (N=12, CFR 0.0%) 的對齊行"


def test_results_v14_secret_and_privacy_scanning():
    """機密掃描：確保公開檔案零金鑰、零 COND- opaque 值、零 raw_response、零內部絕對路徑。"""
    text_extensions = {".json", ".csv", ".md", ".tex", ".sha256"}
    text_files = [p for p in RESULTS_V14_DIR.iterdir() if p.suffix.lower() in text_extensions]

    forbidden_patterns = [
        (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "Google API Key 格式"),
        (re.compile(r"\bCOND-[A-Za-z0-9_-]+"), "內部 Opaque 條件代號 (COND-*)"),
        (re.compile(r"raw_response"), "評審模型未脫敏原始回應 (raw_response)"),
        (re.compile(r"/Users/[a-zA-Z0-9_-]+"), "本機內部絕對路徑 (/Users/...)"),
        (re.compile(r"/home/[a-zA-Z0-9_-]+"), "本機內部絕對路徑 (/home/...)"),
        (re.compile(r"WS4-BATCH-SP-\d{3}-[A-D]"), "內部 Run ID 代號"),
    ]

    for p in text_files:
        content = p.read_text(encoding="utf-8")
        for pattern, desc in forbidden_patterns:
            matches = pattern.findall(content)
            assert not matches, f"公開檔案 {p.name} 偵測到機密或未脫敏資訊: {desc}, 匹配項目: {matches[:3]}"


def test_gitignore_sensitive_rules():
    """驗證 .gitignore 正確排除敏感實驗產物，且不誤擋公開結果。"""
    test_paths = [
        ("llm_ablation_paper/artifacts/raw_transcripts_v14/test.json", True),
        ("llm_ablation_paper/artifacts/blinded_transcripts_v14/test.json", True),
        ("llm_ablation_paper/artifacts/judge_raw_v14/test.json", True),
        ("llm_ablation_paper/artifacts/pilot_m3_v11/test.json", True),
        ("llm_ablation_paper/artifacts/tool_canary_test/test.json", True),
        ("frozen_config/frozen_condition_mapping.json", True),
        ("llm_ablation_paper/workstream_1_technical_lead/frozen_config/frozen_condition_mapping.json", True),
        ("llm_ablation_paper/results/v14/summary.json", False),
        ("llm_ablation_paper/results/v14/RUN_REPORT.md", False),
        ("llm_ablation_paper/artifacts/workstream_1/dry_run_summary.json", False),
    ]

    for rel_path, should_be_ignored in test_paths:
        proc = subprocess.run(
            ["git", "check-ignore", "-q", rel_path],
            cwd=str(REPO_ROOT),
        )
        is_ignored = (proc.returncode == 0)
        assert is_ignored == should_be_ignored, (
            f"路徑 {rel_path} gitignore 判定錯誤: 預期被忽略={should_be_ignored}, 實際={is_ignored}"
        )
