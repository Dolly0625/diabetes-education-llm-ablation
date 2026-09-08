"""test_real_artifact_integration — 10項真實產物覆蓋，缺檔即 fail 不 skip。"""
import csv
import hashlib
import importlib.util
import json
import sys
from functools import lru_cache
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = WS / "scripts" / "validate_profiles.py"
SCHEMA_PATH = WS / "profile_schema.json"
PROFILES_PATH = WS / "patient_profiles.jsonl"
MANIFEST_PATH = WS / "source_manifest.json"
REPORT_PATH = WS / "candidate_filter_report.json"
BUILDER_PATH = WS / "scripts" / "build_patient_profiles.py"

spec = importlib.util.spec_from_file_location("validate_profiles", VALIDATOR_PATH)
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)

builder_spec = importlib.util.spec_from_file_location("build_patient_profiles_for_integration", BUILDER_PATH)
builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(builder)


def _load_profiles():
    assert PROFILES_PATH.exists(), f"缺真實檔 {PROFILES_PATH} -> fail-closed"
    profiles = []
    for line in PROFILES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            profiles.append(json.loads(line))
    return profiles


def _source_csv_path():
    candidates = [
        Path("/tmp/IM_内科5000-33000.csv"),
        Path("/tmp/IM_5000-33000.csv"),
        Path("/tmp/im_5000-33000.csv"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 1000:
            return candidate
    raise AssertionError("FAIL: 原始 CSV 不存在，無法回查 department/title/ask")


@lru_cache(maxsize=1)
def _load_source_records():
    _, _, _, _, records = builder.read_csv_records(_source_csv_path())
    return {record["row_index"]: record for record in records}


def _raw_record_for(profile):
    provenance = profile.get("source_provenance", {})
    row_index = provenance.get("source_row_index", provenance.get("row_index"))
    assert isinstance(row_index, int), f"{profile.get('patient_id')} source_row_index 須為 int"
    records = _load_source_records()
    assert row_index in records, f"{profile.get('patient_id')} row_index {row_index} 不在原始 CSV"
    return records[row_index]


def test_01_all_endocrinology():
    profiles = _load_profiles()
    assert len(profiles) == 12, f"需12筆 got {len(profiles)}"
    for p in profiles:
        record = _raw_record_for(p)
        assert builder._is_strict_endocrinology(record["department"]), f"{p.get('patient_id')} 原始 department 非內分泌科: {record['department']!r}"


def test_02_all_hit_strict():
    profiles = _load_profiles()
    for p in profiles:
        record = _raw_record_for(p)
        raw_text = f"{record['title']} {record['ask']}"
        recomputed = builder._matched_strict_terms(raw_text)
        prov = p.get("source_provenance", {})
        stored = prov.get("matched_source_terms", [])
        assert recomputed, f"{p.get('patient_id')} 原始 title/ask 未命中 strict terms"
        assert sorted(recomputed) == sorted(stored), f"{p.get('patient_id')} matched_source_terms 不一致: raw={recomputed}, stored={stored}"


def test_03_bucket_terms():
    profiles = _load_profiles()
    for p in profiles:
        scen = p.get("scenario_type")
        assert scen in builder.SCENARIO_TYPES, f"未知 scenario {scen}"
        record = _raw_record_for(p)
        raw_text = f"{record['title']} {record['ask']}"
        assert builder._matches_bucket(raw_text, scen), f"{p.get('patient_id')} 原始 title/ask 不符合 {scen} bucket"
        recomputed = builder._matched_bucket_terms(raw_text, scen)
        prov = p.get("source_provenance", {})
        stored = prov.get("matched_scenario_terms", [])
        assert sorted(recomputed) == sorted(stored), f"{p.get('patient_id')} matched_scenario_terms 不一致: raw={recomputed}, stored={stored}"


def test_04_source_record_sha256_consistency():
    profiles = _load_profiles()
    assert REPORT_PATH.exists(), f"缺 {REPORT_PATH}"
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    file_sha = report.get("file_sha256") or report.get("file_sha") or ""
    for p in profiles:
        prov = p.get("source_provenance", {})
        record = _raw_record_for(p)
        idx = prov.get("row_index")
        expected_sha = builder.record_sha256(record["department"], record["title"], record["ask"], idx)
        assert prov.get("source_sha256") == file_sha, f"{p.get('patient_id')} source_sha256 與 report 不一致"
        assert (prov.get("department") or "").replace("内", "內") == record["department"].replace("内", "內"), f"{p.get('patient_id')} department 與原始 CSV 不一致"
        assert prov.get("source_record_sha256") == expected_sha, f"{p.get('patient_id')} source_record_sha256 不一致"


def test_05_matched_source_terms_nonempty():
    profiles = _load_profiles()
    for p in profiles:
        prov = p.get("source_provenance", {})
        terms = prov.get("matched_source_terms")
        assert isinstance(terms, list) and len(terms) >= 1, f"{p.get('patient_id')} matched_source_terms 須非空 array"
        for t in terms:
            assert isinstance(t, str) and t.strip(), f"{p.get('patient_id')} matched_source_terms 元素須非空字串 got {t!r}"


def test_06_synthetic_additions_nonempty_and_distinct():
    profiles = _load_profiles()
    for p in profiles:
        prov = p.get("source_provenance", {})
        adds = prov.get("synthetic_additions")
        assert isinstance(adds, list) and len(adds) >= 1, f"{p.get('patient_id')} synthetic_additions 須非空"
        for t in adds:
            assert isinstance(t, str) and t.strip(), f"{p.get('patient_id')} synthetic_additions 元素須非空字串"
        known = p.get("known_facts", {})
        known_keys = set(known.keys()) if isinstance(known, dict) else set()
        for term in adds:
            assert term not in known_keys, f"{p.get('patient_id')} synthetic_additions '{term}' 須與 known_facts 區分 (不可同 key)"


def test_07_opencc_missing_builder_fail_closed():
    saved = sys.modules.get("opencc")
    try:
        sys.modules["opencc"] = None
        # 強制重新載入 builder
        if "build_patient_profiles" in sys.modules:
            del sys.modules["build_patient_profiles"]
        spec2 = importlib.util.spec_from_file_location("build_patient_profiles", BUILDER_PATH)
        mod = importlib.util.module_from_spec(spec2)
        raised = False
        try:
            spec2.loader.exec_module(mod)
        except RuntimeError:
            raised = True
        except Exception as e:
            # 若 builder 以其他 Exception 拋出亦視為 fail-closed，但須為 RuntimeError
            if isinstance(e, RuntimeError):
                raised = True
            else:
                assert False, f"builder 在 OpenCC 缺失時應拋 RuntimeError，實際拋 {type(e).__name__}: {e}"
        assert raised, "builder 在 sys.modules['opencc']=None 時須 RuntimeError fail-closed (OpenCC 缺失)"
    finally:
        if saved is not None:
            sys.modules["opencc"] = saved
        else:
            sys.modules.pop("opencc", None)
        if "build_patient_profiles" in sys.modules:
            del sys.modules["build_patient_profiles"]


def test_08_manifest_report_no_absolute_path():
    for path in [MANIFEST_PATH, REPORT_PATH]:
        assert path.exists(), f"缺 {path}"
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        dump = json.dumps(data, ensure_ascii=False)
        assert "/tmp" not in dump, f"{path.name} 不可含 /tmp 絕對路徑"
        assert "/Users" not in dump, f"{path.name} 不可含 /Users 絕對路徑"
        # ^/ 絕對路徑：掃 json dump 中任何字串值以 / 開頭
        for _, val in vp._scan_strings(data):
            assert not (isinstance(val, str) and val.startswith("/") and not val.startswith("https://") and not val.startswith("http://")), f"{path.name} 欄位含絕對路徑 {val!r} (禁 ^/)"


def test_09_real_jsonl_passes_validator():
    assert SCHEMA_PATH.exists(), f"缺 {SCHEMA_PATH}"
    assert PROFILES_PATH.exists(), f"缺 {PROFILES_PATH}"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    profiles = _load_profiles()
    errs = vp.validate_all(profiles, schema)
    # 也檢查 manifest 路徑
    ws_dir = WS
    manifest_errs = vp.check_manifest_paths(ws_dir)
    errs.extend(manifest_errs)
    assert errs == [], f"真實 jsonl 應全過 validator，實際錯誤: {errs[:20]}"


def test_10_goal_facts_not_contradictory():
    profiles = _load_profiles()
    for p in profiles:
        goal = p.get("patient_goal", "")
        risk = p.get("risk_trigger", "")
        known = json.dumps(p.get("known_facts", {}), ensure_ascii=False)
        hidden = json.dumps(p.get("hidden_facts", {}), ensure_ascii=False)
        combined_goal = f"{goal} {risk}"
        # FACT_CONTRADICTION 的 initial_statement 與 hidden true_value 可不一致 (設計為更正), 其他情境不應矛盾
        if p.get("scenario_type") == "FACT_CONTRADICTION":
            assert "更正" in combined_goal or "澄清" in combined_goal or "correction" in combined_goal.lower(), f"{p.get('patient_id')} FACT_CONTRADICTION goal 應含更正語意"
            continue
        # 檢查 goal 與 known/hidden 是否矛盾：例如 hidden 有夜間低血糖但 goal 完全無關? 這裡簡單檢查 medication / side effect 已在 validator 處理，此處額外檢查 goal 非空且與 facts 有語意連結
        assert goal.strip(), f"{p.get('patient_id')} patient_goal 不可空"
        assert risk.strip(), f"{p.get('patient_id')} risk_trigger 不可空"
        # 若 known 有 current_medication，goal/risk 至少含藥名之一 (與 validator 一致，作為回歸)
        if "current_medication" in known:
            assert any(kw in combined_goal for kw in ["達格列淨", "二甲雙胍", "胰島素"]), f"{p.get('patient_id')} goal/risk 應呼應 current_medication，got {combined_goal!r}"
        # 副作用呼應
        for kw in ["頻尿", "腹脹", "腹瀉"]:
            if kw in hidden:
                if kw == "頻尿":
                    assert "頻尿" in combined_goal or "尿" in combined_goal, f"{p.get('patient_id')} hidden 含 {kw} 但 goal/risk 未呼應"
                else:
                    assert kw in combined_goal or "腸胃" in combined_goal, f"{p.get('patient_id')} hidden 含 {kw} 但 goal/risk 未呼應"
