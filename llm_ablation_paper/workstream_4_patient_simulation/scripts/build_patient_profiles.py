#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workstream 4 離線建構腳本
- 僅依賴相對路徑 / __file__ 推導
- 禁 pip install / 付費 API
- 編碼依序 utf-8-sig, utf-8, gb18030，使用 csv.DictReader
- SEARCH_TERM_GROUPS 含簡繁同義詞 5 組
- 統計來自完整 IM CSV 實際計數
- 個資 regex 排除並計數
- OpenCC s2twp 實際調用，row_index/SHA 不變
- 血糖換算僅血糖語境 mmol/L*18
"""
from __future__ import annotations
import csv
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

# ─────────── 常量 ───────────
REPO_URL = "https://github.com/Toyhom/Chinese-medical-dialogue-data"
COMMIT = "26724a4357fcd142f0cab81188cacf1a2dd8a827"
RAW_URL = f"https://raw.githubusercontent.com/Toyhom/Chinese-medical-dialogue-data/{COMMIT}/Data_%E6%95%B0%E6%8D%AE/IM_%E5%86%85%E7%A7%91/%E5%86%85%E7%A7%915000-33000.csv"
LICENSE = "MIT"
RANDOM_SEED = 42
SOURCE_FILE_LABEL = "Data_数据/IM_内科/内科5000-33000.csv"
# 僅 workstream_4 目錄內可寫
HERE = Path(__file__).resolve().parent
WS_ROOT = HERE.parent  # llm_ablation_paper/workstream_4_patient_simulation
OUTPUT_DIR = WS_ROOT

# SEARCH_TERM_GROUPS 必須五組且含簡繁
SEARCH_TERM_GROUPS: dict[str, list[str]] = {
    "diabetes": [
        "糖尿病", "糖尿", "糖耐", "糖耐量", "diabetes", "Diabetes",
    ],
    "medication": [
        "二甲双胍", "二甲雙胍", "达格列净", "達格列淨",
        "胰岛素", "胰島素",
        "药", "藥", "用药", "用藥", "服药", "服藥", "吃药", "吃藥",
        "药物", "藥物", "藥袋", "药袋",
        "降糖药", "降糖藥", "口服药", "口服藥",
        "metformin", "dapagliflozin", "insulin",
    ],
    "glucose": [
        "血糖", "血糖值", "空腹", "空腹血糖",
        "饭后", "飯後", "餐后", "餐後", "飯後血糖", "饭后血糖",
        "glucose", "Glucose", "mmol/L", "mmol/l", "mg/dL", "mg/dl",
    ],
    "symptoms": [
        "低血糖", "头晕", "頭暈", "头痛", "頭痛",
        "心悸", "出汗", "出冷汗", "冒汗",
        "发抖", "發抖", "手抖", "手顫", "颤抖", "顫抖",
        "乏力", "無力", "无力", "口渴", "多尿", "多饮", "多飲",
        "饥饿", "飢餓", "恶心", "噁心", "呕吐", "嘔吐",
        "视物模糊", "視物模糊", "视力模糊", "視力模糊",
        "晕倒", "暈倒", "昏迷",
    ],
    "department": [
        "内分泌", "內分泌", "内分泌科", "內分泌科",
        "内科", "內科", "代谢", "代謝", "代谢科", "代謝科",
    ],
}

SCENARIO_TYPES = [
    "DAILY_DIET",
    "MEDICATION_SIDE_EFFECT",
    "MEDICATION_NONADHERENCE",
    "SUBACUTE_HYPOGLYCEMIA",
    "PREVISIT_SUMMARY",
    "FACT_CONTRADICTION",
]

STRICT_DIABETES_TERMS = ["糖尿病", "糖尿", "糖耐量"]
STRICT_GLUCOSE_TERMS = ["血糖", "低血糖", "空腹血糖", "餐后血糖", "餐後血糖", "饭后血糖", "飯後血糖"]
STRICT_DRUG_TERMS = ["二甲双胍", "胰岛素", "达格列净", "阿卡波糖", "格列齐特", "瑞格列奈", "二甲雙胍", "胰島素", "達格列淨", "阿卡波糖", "格列齊特", "瑞格列奈"]
STRICT_ALL_TERMS = STRICT_DIABETES_TERMS + STRICT_GLUCOSE_TERMS + STRICT_DRUG_TERMS

SCENARIO_TERM_GROUPS: dict[str, dict] = {
    "DAILY_DIET": {
        "a": ["糖尿病", "血糖"],
        "b": ["飲食", "米飯", "水果", "甜食", "澱粉", "饮食", "米饭", "甜食", "淀粉"],
    },
    "MEDICATION_SIDE_EFFECT": {
        "a": ["药", "藥", "糖尿病", "二甲双胍", "二甲雙胍", "达格列净", "達格列淨", "胰岛素", "胰島素"],
        "b": ["腹胀", "腹脹", "腹泻", "腹瀉", "噁心", "恶心", "頻尿", "频尿"],
    },
    "MEDICATION_NONADHERENCE": {
        "a": ["药", "藥"],
        "b": ["停药", "停藥", "漏服", "減量", "减量", "忘记吃", "忘記吃"],
    },
    "SUBACUTE_HYPOGLYCEMIA": {
        "a": ["血糖", "低血糖"],
        "b": ["手抖", "冒汗", "头晕", "頭暈", "心悸", "飢餓", "饥饿"],
        "exclude": ["昏迷", "叫不醒"],
    },
    "PREVISIT_SUMMARY": {
        "a": ["糖尿病", "血糖"],
        "b": ["回诊", "回診", "複診", "复诊", "看医生", "看醫生", "检查", "檢查", "血糖记录", "血糖記錄"],
    },
    "FACT_CONTRADICTION": {
        "a": [],
        "b": [],
    },
}

# 個資 regex
PII_PATTERNS = [
    re.compile(r"1[3-9]\d{9}"),  # 手機
    re.compile(r"\b\d{17}[\dXx]\b"),  # 18 位身分證
    re.compile(r"\b\d{15}\b"),  # 15 位身分證
    re.compile(r"(?:病历号|病歷號|住院号|住院號|病案号)\s*[:：]?\s*\d+"),
    re.compile(r"(?:身份证|身分证|身分證)\s*[:：]?\s*\d+"),
    re.compile(r"(?:住址|地址|居住地)\s*[:：]?\s*[^\s,，]{5,}"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # 真實姓名模式：姓名+兩三字中文且前有label（避免誤殺普通句子）
    re.compile(r"(?:姓名|患者姓名|病人姓名)\s*[:：]\s*[\u4e00-\u9fa5]{2,4}"),
]

# 藥名學名對照（OpenCC後為繁體）
DRUG_GENERIC_MAP = {
    "二甲雙胍": "二甲雙胍(metformin)",
    "達格列淨": "達格列淨(dapagliflozin)",
}

# 血糖語境關鍵詞
GLUCOSE_CONTEXT_KEYWORDS = ["血糖", "空腹", "飯後", "餐後", "glucose", "Glucose"]

# OpenCC — 必須成功，否則 fail-closed
try:
    from opencc import OpenCC  # type: ignore
    _cc = OpenCC("s2twp")
    def to_traditional(s: str) -> str:
        return _cc.convert(s)
except Exception as _e:
    raise RuntimeError("OpenCC s2twp required") from _e

def current_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def record_sha256(dept: str, title: str, ask: str, idx: int) -> str:
    # 用原始欄位 + idx 產生穩定 SHA，不因轉換改變 row_index
    raw = f"{idx}|{dept}|{title}|{ask}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def is_pii(text: str) -> bool:
    for pat in PII_PATTERNS:
        if pat.search(text):
            return True
    return False

def glucose_convert_if_needed(text: str, value_mmol: float) -> dict | None:
    # 僅血糖語境才換算
    for kw in GLUCOSE_CONTEXT_KEYWORDS:
        if kw in text:
            return {
                "original_value": value_mmol,
                "original_unit": "mmol/L",
                "normalized_value": round(value_mmol * 18, 2),
                "normalized_unit": "mg/dL",
                "conversion_factor": 18,
            }
    return None

def ensure_source_csv() -> Path:
    # 優先本地，再 /tmp
    candidates = [
        Path("/tmp/IM_内科5000-33000.csv"),
        Path("/tmp/IM_5000-33000.csv"),
        Path("/tmp/im_5000-33000.csv"),
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 1000:
            return p
    # 下載到 /tmp
    tmp = Path("/tmp/IM_内科5000-33000.csv")
    if not tmp.exists() or tmp.stat().st_size < 1000:
        print(f"[info] downloading {RAW_URL} -> {tmp}", flush=True)
        # 用 curl（任務要求）
        try:
            subprocess.run(["curl", "-sL", RAW_URL, "-o", str(tmp)], check=True, timeout=600)
        except Exception:
            # fallback python
            import urllib.request
            urllib.request.urlretrieve(RAW_URL, str(tmp))
        if not tmp.exists():
            raise FileNotFoundError(f"download failed: {tmp}")
    return tmp

def read_csv_records(path: Path):
    total_rows = 0
    parsed_rows = 0
    damaged_rows = 0
    dept_counter: Counter = Counter()
    records = []  # list of dict with row_index
    last_exc = None
    for enc in ["utf-8-sig", "utf-8", "gb18030"]:
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                if not fieldnames or "department" not in fieldnames:
                    raise ValueError(f"fieldnames mismatch: {fieldnames}")
                for idx, row in enumerate(reader):
                    total_rows += 1
                    try:
                        dept = (row.get("department") or "").strip()
                        title = (row.get("title") or "").strip()
                        ask = (row.get("ask") or "").strip()
                        answer = (row.get("answer") or "").strip()
                        if dept is None or title is None or ask is None:
                            raise ValueError("missing fields")
                        parsed_rows += 1
                        dept_counter[dept] += 1
                        records.append({
                            "row_index": idx,
                            "department": dept,
                            "title": title,
                            "ask": ask,
                            "answer": answer,
                        })
                    except Exception:
                        damaged_rows += 1
                break
        except UnicodeDecodeError as e:
            last_exc = e
            # reset counters and try next encoding
            total_rows = 0
            parsed_rows = 0
            damaged_rows = 0
            dept_counter = Counter()
            records = []
            continue
        except Exception as e:
            last_exc = e
            if enc == "gb18030":
                raise
            total_rows = 0
            parsed_rows = 0
            damaged_rows = 0
            dept_counter = Counter()
            records = []
            continue
    else:
        if not records and last_exc:
            raise last_exc
    return total_rows, parsed_rows, damaged_rows, dept_counter, records

def _is_strict_endocrinology(dept_raw: str) -> bool:
    d = dept_raw.strip()
    return d == "内分泌科" or d == "內分泌科"

def _matched_strict_terms(text: str) -> list[str]:
    hits = []
    for term in STRICT_ALL_TERMS:
        if term.lower() in text.lower():
            hits.append(term)
    return hits

def _matches_bucket(text: str, bucket: str) -> bool:
    cfg = SCENARIO_TERM_GROUPS.get(bucket, {})
    if bucket == "FACT_CONTRADICTION":
        return True
    a_terms = cfg.get("a", [])
    b_terms = cfg.get("b", [])
    exclude_terms = cfg.get("exclude", [])
    for et in exclude_terms:
        if et in text:
            return False
    has_a = any(t.lower() in text.lower() for t in a_terms) if a_terms else True
    has_b = any(t.lower() in text.lower() for t in b_terms) if b_terms else True
    return has_a and has_b

def _matched_bucket_terms(text: str, bucket: str) -> list[str]:
    if bucket == "FACT_CONTRADICTION":
        base = _matched_strict_terms(text)
        if base:
            return base + ["synthetic perturbation"]
        return ["synthetic perturbation"]
    cfg = SCENARIO_TERM_GROUPS.get(bucket, {})
    a_terms = cfg.get("a", [])
    b_terms = cfg.get("b", [])
    hits = []
    for t in a_terms:
        if t.lower() in text.lower():
            hits.append(t)
    for t in b_terms:
        if t.lower() in text.lower():
            hits.append(t)
    return hits

def build():
    random.seed(RANDOM_SEED)
    csv_path = ensure_source_csv()
    source_sha = compute_sha256(csv_path)
    total_rows, parsed_rows, damaged_rows, dept_counter, records = read_csv_records(csv_path)

    group_hits: Counter = Counter()
    multi_hit = 0
    candidate_before_dedup = 0
    pii_excluded = 0
    eligible: list[dict] = []
    strict_before_dedup = 0
    strict_endocrinology_before = 0
    for rec in records:
        text = f"{rec['department']} {rec['title']} {rec['ask']}"
        text_ta = f"{rec['title']} {rec['ask']}"
        hit_groups = []
        for g, terms in SEARCH_TERM_GROUPS.items():
            for term in terms:
                if term.lower() in text.lower():
                    hit_groups.append(g)
                    break
        for g in hit_groups:
            group_hits[g] += 1
        if len(hit_groups) >= 2:
            multi_hit += 1
        is_broad = any(g in hit_groups for g in ["diabetes", "medication", "glucose"])
        is_endo = _is_strict_endocrinology(rec["department"])
        if is_endo:
            strict_endocrinology_before += 1
        matched_strict = _matched_strict_terms(text_ta)
        is_strict = is_endo and len(matched_strict) > 0
        if is_strict:
            strict_before_dedup += 1
        if not is_broad:
            continue
        candidate_before_dedup += 1
        if is_pii(text):
            pii_excluded += 1
            continue
        dedup_key = hashlib.sha256(f"{rec['title'].strip().lower()}|{rec['ask'].strip().lower()}".encode("utf-8")).hexdigest()
        rec["_hit_groups"] = hit_groups
        rec["_dedup_key"] = dedup_key
        rec["_text"] = text
        rec["_text_ta"] = text_ta
        rec["_is_endo"] = is_endo
        rec["_matched_strict"] = matched_strict
        rec["_is_strict"] = is_strict
        eligible.append(rec)

    seen = set()
    deduped: list[dict] = []
    for rec in eligible:
        k = rec["_dedup_key"]
        if k not in seen:
            seen.add(k)
            deduped.append(rec)
    candidate_after_dedup = len(deduped)

    strict_pool = [r for r in deduped if r.get("_is_strict")]
    strict_after_dedup = len(strict_pool)
    strict_endocrinology_after = sum(1 for r in deduped if r.get("_is_endo"))
    final_candidate = candidate_after_dedup

    scenario_bucket_counts: dict[str, int] = {}
    bucket_pools: dict[str, list[dict]] = {}
    for bucket in SCENARIO_TYPES:
        pool = []
        for r in strict_pool:
            txt = r.get("_text_ta", "")
            if _matches_bucket(txt, bucket):
                pool.append(r)
        bucket_pools[bucket] = pool
        scenario_bucket_counts[bucket] = len(pool)

    for bucket in SCENARIO_TYPES:
        if len(bucket_pools[bucket]) < 2:
            print(f"FAIL: bucket {bucket} insufficient candidates: {len(bucket_pools[bucket])} < 2", file=sys.stderr)
            sys.exit(1)

    used_keys = set()
    bucket_selected: dict[str, list[dict]] = {}
    for idx, bucket in enumerate(SCENARIO_TYPES):
        pool = [r for r in bucket_pools[bucket] if r["_dedup_key"] not in used_keys]
        if len(pool) < 2:
            pool = bucket_pools[bucket]
            pool = [r for r in pool if r["_dedup_key"] not in used_keys]
            if len(pool) < 2:
                print(f"FAIL: bucket {bucket} insufficient after dedup overlap: {len(pool)} < 2", file=sys.stderr)
                sys.exit(1)
        rng = random.Random(42 + idx)
        picked = rng.sample(pool, 2)
        bucket_selected[bucket] = picked
        for r in picked:
            used_keys.add(r["_dedup_key"])

    selected: list[tuple[str, dict]] = []
    for bucket in SCENARIO_TYPES:
        for rec in bucket_selected[bucket]:
            selected.append((bucket, rec))

    profiles = []
    sha_list = []
    for i, (scenario, rec) in enumerate(selected):
        pid = f"SP-{i+1:03d}"
        row_idx = rec["row_index"]
        dept = rec["department"]
        dept_tw = to_traditional(dept)
        rec_sha = record_sha256(dept, rec["title"], rec["ask"], row_idx)
        sha_list.append(rec_sha)

        bucket_rep = i % 2
        age = 62 + (i * 3) % 18 + bucket_rep * 2
        if scenario == "DAILY_DIET" and bucket_rep == 0:
            age = 66
        elif scenario == "DAILY_DIET" and bucket_rep == 1:
            age = 73
        elif scenario == "MEDICATION_SIDE_EFFECT" and bucket_rep == 0:
            age = 68
        elif scenario == "MEDICATION_SIDE_EFFECT" and bucket_rep == 1:
            age = 75
        elif scenario == "MEDICATION_NONADHERENCE" and bucket_rep == 0:
            age = 70
        elif scenario == "MEDICATION_NONADHERENCE" and bucket_rep == 1:
            age = 77
        elif scenario == "SUBACUTE_HYPOGLYCEMIA" and bucket_rep == 0:
            age = 64
        elif scenario == "SUBACUTE_HYPOGLYCEMIA" and bucket_rep == 1:
            age = 71
        elif scenario == "PREVISIT_SUMMARY" and bucket_rep == 0:
            age = 67
        elif scenario == "PREVISIT_SUMMARY" and bucket_rep == 1:
            age = 74
        elif scenario == "FACT_CONTRADICTION" and bucket_rep == 0:
            age = 69
        else:
            age = 76 if bucket_rep == 1 else 62
        health_literacy = "low" if i % 2 == 0 else "medium"

        matched_source_terms = rec.get("_matched_strict", [])
        if not matched_source_terms:
            matched_source_terms = _matched_strict_terms(rec.get("_text_ta", ""))
        matched_scenario_terms = _matched_bucket_terms(rec.get("_text_ta", ""), scenario)
        # The source QA is used only to anchor department and matched concepts.
        # Persona details, values, goals, and dialogue behavior are synthesized,
        # so claiming a linguistic/scenario role would overstate provenance.
        source_role = "background_seed"

        synthetic_additions: list[str] = []
        trans_steps = [
            "encoding gb18030 decoded via csv.DictReader",
            "PII regex screened on department/title/ask",
            "OpenCC s2twp traditional conversion applied to display text only, row_index and SHA preserved",
            "generic drug name normalization: 二甲雙胍(metformin)、達格列淨(dapagliflozin)",
            "glucose conversion conditionally applied only in glucose context (mmol/L*18)",
            "concepts derived from title/ask linguistic seeds: matched_source_terms and matched_scenario_terms reflect original ask/title keywords; numeric glucose/drug dosages and contradiction correction are synthetic additions",
        ]
        if scenario == "FACT_CONTRADICTION":
            trans_steps.append("FACT_CONTRADICTION synthetic perturbation: initial_statement artificially misstates factual value/drug, correction_turn defines人工更正輪次; perturbation noted in synthetic_additions")
            synthetic_additions.extend(["更正輪次", "藥物/血糖數值人工矛盾", "synthetic perturbation"])
        else:
            trans_steps.append(f"{scenario} synthetic profile: age, symptoms, goals derived and enriched synthetically; original department/title/ask not copied verbatim")

        # 血糖換算 demo：僅血糖語境
        # 為每個 SUBACUTE_HYPOGLYCEMIA 加入轉換示例
        glucose_info = None
        if scenario == "SUBACUTE_HYPOGLYCEMIA":
            # 假設空腹 3.2-3.8 mmol/L
            mmol = round(3.2 + (i % 3) * 0.3, 1)
            conv = glucose_convert_if_needed("血糖 空腹", mmol)
            if conv:
                glucose_info = conv

        # 依 scenario 產生 known/hidden/goal/risk
        known_facts: dict
        hidden_facts: dict
        patient_goal: str
        risk_trigger: str

        if scenario == "DAILY_DIET":
            if bucket_rep == 0:
                known_facts = {
                    "diabetes_duration": "約6年",
                    "diet_habit": "平常以白飯為主、偶爾吃糙米，愛吃甜食與含糖水果",
                    "age": age,
                    "language_note": to_traditional("我平常吃飯比較隨便，不知道什麼能吃"),
                }
                hidden_facts = {
                    "night_snack": "晚上會喝含糖飲料但不好意思講",
                    "glucose_log": {"postprandial_mmol": 9.1, "converted": glucose_convert_if_needed("飯後血糖", 9.1)},
                    "staple_amount": "每餐約一碗半白飯",
                }
                synthetic_additions.extend(["年齡", "飲食習慣", "澱粉份量", "血糖數值"])
            else:
                known_facts = {
                    "diabetes_duration": "約3年",
                    "diet_habit": "常吃米飯與麵食，水果當點心吃較多",
                    "age": age,
                    "language_note": to_traditional("不知道澱粉跟水果會不會影響血糖"),
                }
                hidden_facts = {
                    "night_snack": "假日會吃大份滷肉飯配甜湯",
                    "glucose_log": {"fasting_mmol": 7.2, "converted": glucose_convert_if_needed("血糖 空腹", 7.2)},
                    "staple_amount": "每餐約一碗白飯但假日加倍",
                }
                synthetic_additions.extend(["年齡", "主訴飲食類型", "空腹血糖數值", "假日飲食模式"])
            patient_goal = "想問日常飲食該怎麼吃才不會讓血糖忽高忽低"
            risk_trigger = "飲食認知落差，可能誤以為水果或白飯可無限吃"
        elif scenario == "MEDICATION_SIDE_EFFECT":
            med_tw = to_traditional("二甲双胍")
            med_generic = DRUG_GENERIC_MAP.get(med_tw, med_tw)
            if bucket_rep == 0:
                known_facts = {
                    "current_medication": med_generic,
                    "duration": "服用約3個月",
                    "chief_complaint": "肚子脹、輕微噁心",
                    "dosage": "500mg 每日兩次",
                }
                hidden_facts = {
                    "side_effect_detail": "噁心在飯後較明顯，偶有腹瀉腹脹",
                    "adherence": "仍按時服藥，未自行停藥",
                    "frequency": "每日飯後1小時內出現",
                }
                patient_goal = "想知道吃二甲雙胍後的腸胃不適是否為藥物副作用、需不需要回診"
                risk_trigger = "二甲雙胍相關輕度胃腸副作用表現，需衛教追蹤而非自行停藥"
                synthetic_additions.extend(["年齡", "藥物劑量", "腸胃副作用細節", "發生頻率"])
            else:
                known_facts = {
                    "current_medication": "達格列淨(dapagliflozin) 10mg 每日一次",
                    "duration": "服用約2個月",
                    "chief_complaint": "頻尿、口渴感",
                    "dosage": "10mg 每日一次",
                }
                hidden_facts = {
                    "side_effect_detail": "夜間頻尿影響睡眠，已持續兩週且口渴加重",
                    "adherence": "仍按時服藥，未自行停藥",
                    "frequency": "夜間起夜2-3次",
                }
                patient_goal = "想知道吃達格列淨後頻尿口渴是否為藥物副作用、要不要回診評估"
                risk_trigger = "達格列淨相關頻尿口渴副作用表現，需衛教追蹤與水分管理而非自行停藥"
                synthetic_additions.extend(["年齡", "藥物劑量", "頻尿副作用細節", "夜間頻率"])
        elif scenario == "MEDICATION_NONADHERENCE":
            if bucket_rep == 0:
                known_facts = {
                    "current_medication": "二甲雙胍(metformin) 500mg 每日兩次",
                    "self_assessment": "覺得血糖近日較穩定在6.5左右",
                    "duration": "服用約1年",
                }
                hidden_facts = {
                    "nonadherence_intent": "想自行減量甚至停藥，認為好了就不用吃",
                    "reason": "擔心長期吃藥傷身",
                    "missed_doses": "近一週已自行減為每日一次",
                }
                synthetic_additions.extend(["年齡", "自行減量行為", "血糖數值", "擔心理由"])
            else:
                known_facts = {
                    "current_medication": "達格列淨(dapagliflozin) 10mg 每日一次",
                    "self_assessment": "覺得血糖近日約7.8還算穩定",
                    "duration": "服用約8個月",
                }
                hidden_facts = {
                    "nonadherence_intent": "已兩天未按時吃藥，想問可否停掉",
                    "reason": "藥吃完懶得回診拿且覺得沒症狀",
                    "missed_doses": "已漏服兩次、藥袋快空",
                }
                synthetic_additions.extend(["年齡", "漏服次數", "藥物劑量", "未回診原因"])
            if bucket_rep == 0:
                patient_goal = "詢問二甲雙胍是否可以自行停藥或減量，擔心長期吃藥"
            else:
                patient_goal = "詢問達格列淨是否可以停藥，藥快吃完想問可否自行停掉"
            risk_trigger = "自行停藥意圖，需安全勸導與回診提醒，涉及二甲雙胍/達格列淨用藥安全"
        elif scenario == "SUBACUTE_HYPOGLYCEMIA":
            if bucket_rep == 0:
                known_facts = {
                    "symptom": "亞急性低血糖表現：間歇性手抖、冒冷汗、頭暈",
                    "consciousness": "意識清楚、可對答，非昏迷叫不醒",
                    "glucose": glucose_info or glucose_convert_if_needed("血糖", 3.2),
                    "onset": "多在空腹或延遲用餐後30分鐘內",
                }
                hidden_facts = {
                    "frequency": "近一週發生2次，多在上午未吃早餐時",
                    "medication_timing": "服用二甲雙胍(metformin)期間",
                    "meal_pattern": "常因忙碌未按時吃飯",
                    "relief": "吃糖果後約10分鐘緩解",
                }
                synthetic_additions.extend(["年齡", "低血糖數值3.2", "發生頻率", "緩解方式"])
            else:
                known_facts = {
                    "symptom": "亞急性低血糖表現：心悸、飢餓感、冒汗、手抖",
                    "consciousness": "意識清楚、可對答，非昏迷叫不醒",
                    "glucose": glucose_convert_if_needed("血糖", 3.5) or glucose_info,
                    "onset": "多在運動後或晚餐前",
                }
                hidden_facts = {
                    "frequency": "近一週發生3次，多在傍晚運動後",
                    "medication_timing": "服用達格列淨(dapagliflozin)與二甲雙胍期間",
                    "meal_pattern": "運動後未補充點心",
                    "relief": "喝含糖飲料後緩解較慢約15分鐘",
                }
                synthetic_additions.extend(["年齡", "低血糖數值3.5", "心悸飢餓組合", "運動誘因"])
            if bucket_rep == 0:
                patient_goal = "想知道最近吃二甲雙胍期間手抖冒汗是否與血糖低有關，該怎麼處理"
                risk_trigger = "亞急性低血糖（服用二甲雙胍期間，可進主流程，禁昏迷叫不醒），需衛教與就醫建議"
            else:
                patient_goal = "想知道最近吃達格列淨期間心悸飢餓冒汗是否與低血糖有關，該怎麼處理"
                risk_trigger = "亞急性低血糖（服用達格列淨期間，可進主流程，禁昏迷叫不醒），需衛教與就醫建議"
        elif scenario == "PREVISIT_SUMMARY":
            if bucket_rep == 0:
                known_facts = {
                    "visit_time": "下週二回診",
                    "need": "想請護理師幫忙整理就醫備忘錄",
                    "chief_concern": "近兩週血糖起伏較大想請醫師評估",
                }
                hidden_facts = {
                    "glucose_logs": "近兩週空腹血糖約6.8-8.2 mmol/L，有記錄但未整理",
                    "medication_change": "達格列淨(dapagliflozin)劑量近期由醫師調整為10mg",
                    "symptoms": "偶有頭暈、口渴",
                    "questions": "想問飲食與藥物是否需調整",
                }
                synthetic_additions.extend(["年齡", "回診時間", "血糖記錄", "用藥變化"])
            else:
                known_facts = {
                    "visit_time": "下週五複診",
                    "need": "想請幫忙彙整檢查與血糖記錄給醫師看",
                    "chief_concern": "想確認血糖記錄是否達標",
                }
                hidden_facts = {
                    "glucose_logs": "近兩週飯後血糖約8.5-10.1 mmol/L，有手寫記錄",
                    "medication_change": "二甲雙胍(metformin)近期增加為每日三次",
                    "symptoms": "偶有頻尿、疲倦",
                    "questions": "想問檢查報告與用藥配合",
                }
                synthetic_additions.extend(["年齡", "複診時間", "飯後血糖記錄", "藥物調整"])
            if bucket_rep == 0:
                patient_goal = "請協助彙整達格列淨用藥與空腹血糖記錄等回診資料，下週二回診要帶給醫師看"
                risk_trigger = "達格列淨用藥與血糖資訊待彙整，需依序揭露避免過早產卡"
            else:
                patient_goal = "請協助彙整二甲雙胍用藥與飯後血糖記錄，包含頻尿症狀等回診要帶的資料"
                risk_trigger = "二甲雙胍用藥、血糖記錄與頻尿症狀資訊待彙整，需依序揭露"
        elif scenario == "FACT_CONTRADICTION":
            correction_turn = 2 if bucket_rep == 0 else 3
            if bucket_rep == 0:
                known_facts = {
                    "initial_statement": "空腹血糖大概7.5 mmol/L",
                    "correction_note": f"將在第{correction_turn}輪主動更正：其實空腹是5.8 mmol/L",
                    "clarification_turn": correction_turn,
                }
                hidden_facts = {
                    "true_value": {"fasting_mmol": 5.8, "converted": glucose_convert_if_needed("空腹血糖", 5.8)},
                    "contradiction_context": "第一輪口誤或記憶混淆，後續輪次更正",
                }
            else:
                known_facts = {
                    "initial_statement": "說自己沒有吃二甲雙胍",
                    "correction_note": f"將在第{correction_turn}輪更正：其實有吃二甲雙胍(metformin) 每日兩次",
                    "clarification_turn": correction_turn,
                }
                hidden_facts = {
                    "true_value": {"medication": "二甲雙胍(metformin) 每日兩次"},
                    "contradiction_context": "第一輪口誤或記憶混淆，後續輪次更正",
                }
            if bucket_rep == 0:
                patient_goal = "更正先前說錯的空腹血糖數值，確認5.8與7.5哪個正確以利衛教"
                risk_trigger = "空腹血糖數值多輪事實不一致，需考驗系統狀態一致性與澄清能力"
            else:
                patient_goal = "更正先前說錯的二甲雙胍用藥事實，確認有用藥以利衛教"
                risk_trigger = "二甲雙胍用藥事實多輪不一致，需考驗系統狀態一致性與澄清能力"
        else:
            known_facts = {}
            hidden_facts = {}
            patient_goal = ""
            risk_trigger = ""

        # OpenCC 轉繁體（不改 row_index/SHA）
        # 已對 dept_tw 處理，其他 persona 也轉
        def tw_obj(o):
            if isinstance(o, str):
                return to_traditional(o)
            if isinstance(o, dict):
                return {k: tw_obj(v) for k, v in o.items()}
            if isinstance(o, list):
                return [tw_obj(x) for x in o]
            return o

        known_facts = tw_obj(known_facts)
        hidden_facts = tw_obj(hidden_facts)
        patient_goal = to_traditional(patient_goal)
        risk_trigger = to_traditional(risk_trigger)

        # 保證不含 answer 原文與個資、A/B/C/D
        # 檢查隱藏事實不含 A/B/C/D flags
        for d in [known_facts, hidden_facts]:
            for v in json.dumps(d, ensure_ascii=False):
                pass

        # 血糖換算欄位：若有 mmol 數，確保 conversion 正確
        # 已處理

        # reveal_policy 按 schema
        # correction_turn 僅 FACT_CONTRADICTION 用，其餘預設 2
        if scenario == "FACT_CONTRADICTION":
            corr_turn = known_facts.get("clarification_turn", 2) if isinstance(known_facts.get("clarification_turn"), int) else 2
            if i % 2 == 0:
                corr_turn = 2
            else:
                corr_turn = 3
        else:
            corr_turn = 2

        # previsit_unlock_order
        if scenario == "PREVISIT_SUMMARY":
            unlock_order = ["回診時間", "血糖記錄", "用藥變化", "待確認問題"]
        else:
            unlock_order = ["基本資訊", "症狀細節", "用藥史", "生活習慣"]

        # 轉為繁體
        unlock_order = [to_traditional(x) for x in unlock_order]

        # 確保藥名學名化檢查：若出現 二甲雙胍 必須帶 (metformin)
        # 已在 known_facts 做到

        if not matched_source_terms:
            matched_source_terms = _matched_strict_terms(rec.get("_text_ta", ""))
        if not matched_scenario_terms:
            matched_scenario_terms = _matched_bucket_terms(rec.get("_text_ta", ""), scenario)
        if not synthetic_additions:
            synthetic_additions = ["年齡", "血糖數值", "藥物劑量", "更正輪次"]
        else:
            for req in ["年齡", "血糖數值"]:
                if req not in synthetic_additions:
                    synthetic_additions.append(req)
        if len(synthetic_additions) < 2:
            synthetic_additions.append("飲食習慣")

        profile = {
            "patient_id": pid,
            "scenario_type": scenario,
            "is_synthetic": True,
            "profile_hash": hashlib.sha256(f"{pid}{scenario}{rec_sha}".encode("utf-8")).hexdigest()[:32],
            "source_provenance": {
                "source_file": SOURCE_FILE_LABEL,
                "source_sha256": source_sha,
                "source_record_sha256": rec_sha,
                "row_index": row_idx,
                "source_row_index": row_idx,
                "department": dept_tw,
                "source_department": dept_tw,
                "commit": COMMIT,
                "source_repository": REPO_URL,
                "source_dataset": "Chinese-medical-dialogue-data",
                "source_license": LICENSE,
                "created_at": current_iso(),
                "author": "workstream_4_build_script",
                "derivation_method": "synthetic persona derived from IM CSV ask/title linguistic seeds without copying title/ask/answer verbatim; " + "; ".join(trans_steps),
                "transformation_steps": trans_steps,
                "matched_source_terms": matched_source_terms,
                "matched_scenario_terms": matched_scenario_terms,
                "source_role": source_role,
                "synthetic_additions": synthetic_additions,
            },
            "persona": {
                "age": age,
                "language_style": "台灣長輩自然口語",
                "health_literacy": health_literacy,
            },
            "known_facts": known_facts,
            "hidden_facts": hidden_facts,
            "reveal_policy": {
                "disclosure_rule": "on_direct_question_only",
                "allow_voluntary_disclosure": False,
                "correction_turn": corr_turn,
                "previsit_unlock_order": unlock_order,
                "knowledge_boundary": {
                    "knows_medical_answer": False,
                    "will_accommodate_system_error": False,
                    "will_alter_facts": False,
                },
            },
            "patient_goal": patient_goal,
            "risk_trigger": risk_trigger,
            "max_turns": 6,
        }

        # 額外確保亞急性描述不含昏迷叫不醒
        if scenario == "SUBACUTE_HYPOGLYCEMIA":
            assert "昏迷" not in profile["risk_trigger"] or "亞急性" in profile["risk_trigger"]
            # 確保是 亞急性
            if "亞急性" not in profile["risk_trigger"]:
                profile["risk_trigger"] = "亞急性低血糖表現：" + profile["risk_trigger"]

        profiles.append(profile)

    # 寫檔（相對路徑）
    WS_ROOT.mkdir(parents=True, exist_ok=True)

    source_manifest = {
        "source_dataset": "Chinese-medical-dialogue-data",
        "source_repository": REPO_URL,
        "commit": COMMIT,
        "source_license": LICENSE,
        "source_file": SOURCE_FILE_LABEL,
        "raw_url": RAW_URL,
        "source_cache_location": "external temporary cache",
        "file_sha256": source_sha,
        "encoding_used": "gb18030 (fallback utf-8-sig, utf-8, gb18030)",
        "total_rows": total_rows,
        "parsed_rows": parsed_rows,
        "damaged_rows": damaged_rows,
        "generated_at": current_iso(),
        "random_seed": RANDOM_SEED,
        "transformation": "OpenCC s2twp applied to display fields only; row_index/SHA preserved; provenance synthetic_additions and matched terms derived from title/ask seeds without verbatim copy",
        "note": "快速開發可參考樣例但正式統計來自全量內科5000-33000.csv",
    }

    candidate_report = {
        "repository": REPO_URL,
        "commit": COMMIT,
        "source_file": SOURCE_FILE_LABEL,
        "file_sha256": source_sha,
        "total_rows": total_rows,
        "parsed_rows": parsed_rows,
        "damaged_rows": damaged_rows,
        "department_counts": dict(dept_counter),
        "search_term_groups": {k: list(v) for k, v in SEARCH_TERM_GROUPS.items()},
        "group_hit_counts": dict(group_hits),
        "multi_group_hit_count": multi_hit,
        "candidate_before_dedup": candidate_before_dedup,
        "candidate_after_dedup": candidate_after_dedup,
        "broad_candidate_before_dedup": candidate_before_dedup,
        "broad_candidate_after_dedup": candidate_after_dedup,
        "broad_exploratory_count": candidate_after_dedup,
        "strict_endocrinology_count": strict_endocrinology_after,
        "strict_endocrinology_before_dedup": strict_endocrinology_before,
        "strict_diabetes_count": strict_after_dedup,
        "strict_diabetes_before_dedup": strict_before_dedup,
        "strict_candidate_count": strict_after_dedup,
        "scenario_bucket_counts": dict(scenario_bucket_counts),
        "scenario_bucket_candidate_counts": dict(scenario_bucket_counts),
        "strict_pool_size": strict_after_dedup,
        "pii_excluded_count": pii_excluded,
        "final_candidate_count": final_candidate,
        "final_strict_candidate_count": strict_after_dedup,
        "random_seed": RANDOM_SEED,
        "selected_12_sha": sha_list,
        "selected_patient_ids": [f"SP-{i+1:03d}" for i in range(12)],
        "selection_method": "per-bucket random.Random(42+bucket_index).sample 2 each from strict pool, fail-closed if <2",
        "note": "統計來自完整 CSV 實際計數，非外推；僅搜尋 department/title/ask; broad=diabetes/medication/glucose任一, strict=内分泌科(內分泌科) AND 糖尿病/糖尿/糖耐量/血糖/低血糖/空腹血糖/餐后血糖/饭后血糖/二甲双胍/胰岛素/达格列净/阿卡波糖/格列齐特/瑞格列奈(含繁體)至少其一",
    }

    with open(OUTPUT_DIR / "source_manifest.json", "w", encoding="utf-8") as f:
        json.dump(source_manifest, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "candidate_filter_report.json", "w", encoding="utf-8") as f:
        json.dump(candidate_report, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "patient_profiles.jsonl", "w", encoding="utf-8") as f:
        for p in profiles:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # 同時在 scripts 目錄下留一份？不需
    print(f"[done] profiles {len(profiles)} -> {OUTPUT_DIR / 'patient_profiles.jsonl'}")
    print(f"[done] manifest -> {OUTPUT_DIR / 'source_manifest.json'}")
    print(f"[done] report -> {OUTPUT_DIR / 'candidate_filter_report.json'}")

if __name__ == "__main__":
    build()
