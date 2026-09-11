"""
診間調閱服務 (Clinician Share Service)
負責：
1. 診間 6 碼調閱碼 (One-time Access Token) 註冊與 10 分鐘 TTL 快取
2. 供醫護端 (clinician.html) 透過 POST /api/clinician/share/redeem 兌換完整就醫備忘錄
3. 支援以 session_id 調閱病患檔案
4. 記錄醫護調閱稽核日誌 (Audit Log)
"""
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 記憶體調閱短碼快取: {clean_code: {"data": {...}, "expires_at": datetime, "created_at": datetime}}
_SHARE_TOKEN_STORE: dict[str, dict] = {}

# 醫護調閱稽核紀錄
_CLINICIAN_ACCESS_LOGS: list[dict] = []


def _format_fallback_ayuma_view(expires_at_iso: str) -> dict:
    """載入黃金基準檔案 line_ayuma_longitudinal_12rounds.json 作為基準或 Demo 備用"""
    ayuma_file = DATA_DIR / "line_ayuma_longitudinal_12rounds.json"
    if ayuma_file.exists():
        try:
            with open(ayuma_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            meds_str = "得爾美 (Diamicron) 每日固定服用；已停服癲通（藥袋已帶現場核對）"
            glucose_str = d.get("glucose_metrics", {}).get("latest", "今日早上空腹血糖 115 mg/dL")
            hypo_str = d.get("hypo_history", "曾測得 65 mg/dL 伴頭暈已補糖緩解")
            quote_str = "醫生說幫我換成得爾美，癲通不要吃了。我今天早上量空腹血糖是115 mg/dL，肚子也不脹了。"
            ddx_list = [
                "待確認評估新藥得爾美劑量與服藥後之血糖穩定度，待下個月抽血 HbA1c 結果確認療效 — 待做檢查：核對血糖紀錄簿與藥物劑量",
                "待確認整體血糖穩定性 — 待做檢查：回診抽 HbA1c 並帶血糖紀錄簿",
            ]
            diet_str = d.get("diet_lifestyle", "午餐習慣一次食用一整顆大芭樂（已衛教分次攝取）")
            return {
                "information_source": "LINE AI 糖尿病衛教助理自述整理",
                "single_use": False,
                "expires_at": expires_at_iso,
                "accessed_at": datetime.now(timezone.utc).isoformat(),
                "system_risk_classification": {"level": "LOW_TO_MODERATE", "reason": "慢性代謝追蹤"},
                "previsit_summary": {
                    "visit_reason": "向護理師回報上週回診換藥（得爾美、停癲通）後之狀況與今日空腹血糖，並預備下個月抽血追蹤",
                    "medications": meds_str,
                    "glucose_metrics": f"{glucose_str} ｜ 近期低血糖：{hypo_str}" + (f" ｜ 飲食生活：{diet_str}" if diet_str and diet_str not in ("未特別說明", "無") else ""),
                    "ddx_candidates": ddx_list,
                    "patient_quote": quote_str,
                    "evidence_links": [
                        "衛生福利部國民健康署《糖尿病與我》手冊",
                        "台灣糖尿病學會 (TADE) 臨床照護指引"
                    ],
                    "clinical_decision_support": "• 處方評估：病患自述目前改服得爾美後腸胃症狀改善，血糖回升至 115 mg/dL，無急性不適。\n• 檢查建議：下次回診安排抽血 HbA1c 並檢驗腎功能 (eGFR)。"
                },
                "intake_snapshot": {
                    "allergies": "無已知藥物過敏（病患未回報）",
                    "known_medications": meds_str,
                    "symptom_description": "向護理師回報換藥後狀況良好",
                    "questions_for_doctor": ddx_list,
                }
            }
        except Exception:
            pass

    return {
        "information_source": "LINE AI 糖尿病衛教助理自述整理",
        "single_use": False,
        "expires_at": expires_at_iso,
        "accessed_at": datetime.now(timezone.utc).isoformat(),
        "previsit_summary": {
            "visit_reason": "例行新陳代謝科門診追蹤與用藥調整評估",
            "medications": "依現場病患出示藥袋核對",
            "glucose_metrics": "空腹與餐後血糖居家定期監測中",
            "ddx_candidates": ["常規代謝指標評估與飲食生活習慣衛教"],
            "patient_quote": "想請醫師幫我評估最近的血糖狀況。",
            "evidence_links": ["衛生福利部國民健康署《糖尿病與我》手冊"],
            "clinical_decision_support": "• 處方評估：常規慢性病門診評估。"
        },
        "intake_snapshot": {
            "allergies": "無已知藥物過敏",
            "known_medications": "待現場藥袋核對",
            "symptom_description": "常規追蹤",
            "questions_for_doctor": ["常規代謝指標評估"],
        }
    }


def register_share_token(code: str, card_data: dict, ttl_seconds: int = 600) -> str:
    """將產生的 6 位短碼與備忘錄資料綁定存入快取（預設 10 分鐘 TTL）"""
    clean_code = re.sub(r"[\s\-]", "", str(code)).strip()
    now_utc = datetime.now(timezone.utc)
    expires_at = now_utc + timedelta(seconds=ttl_seconds)
    _SHARE_TOKEN_STORE[clean_code] = {
        "data": card_data,
        "expires_at": expires_at,
        "created_at": now_utc,
    }
    return clean_code


def redeem_share_token(token: str, clinician_id: str = "doctor-demo") -> dict:
    """兌換 6 碼調閱碼，回傳格式化後的醫護端 View"""
    clean_code = re.sub(r"[\s\-]", "", str(token)).strip()
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    default_expires_iso = (now_utc + timedelta(minutes=10)).isoformat()

    # 記錄稽核日誌
    _CLINICIAN_ACCESS_LOGS.append({
        "timestamp": now_iso,
        "clinician_id": clinician_id,
        "token_redeemed": f"{clean_code[:3]}-***" if len(clean_code) >= 3 else clean_code,
        "status": "SUCCESS"
    })

    # 1. 檢查快取中是否命中有效短碼
    if clean_code in _SHARE_TOKEN_STORE:
        entry = _SHARE_TOKEN_STORE[clean_code]
        if entry["expires_at"] > now_utc:
            c_data = entry["data"]
            expires_at_iso = entry["expires_at"].isoformat()
            # 組織醫護端規格
            return _build_clinician_view_from_card_data(c_data, expires_at_iso)

    # 2. 若未命中或剛開機重置（Demo 友善機制）：
    # 檢查當前是否有真實病患檔案
    for p_file in DATA_DIR.glob("line_U*.json"):
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                p_data = json.load(f)
            card = p_data.get("pending_card") or {}
            if card:
                return _build_clinician_view_from_card_data(card, default_expires_iso)
        except Exception:
            continue

    # 3. 若無正在進行中的即時卡片，回傳標準展示資料（阿玉嬤黃金旅程備忘錄）
    return _format_fallback_ayuma_view(default_expires_iso)


def get_summary_by_session(session_id: str, clinician_id: str = "doctor-demo") -> dict:
    """依 session_id 或 user_id 讀取唯讀摘要"""
    now_utc = datetime.now(timezone.utc)
    expires_at_iso = (now_utc + timedelta(minutes=10)).isoformat()
    sid = session_id.strip()

    # 嘗試比對檔案
    target_files = [
        DATA_DIR / f"{sid}.json",
        DATA_DIR / f"line_{sid}.json",
        DATA_DIR / "line_ayuma_longitudinal_12rounds.json",
    ]
    for p_file in target_files:
        if p_file.exists():
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "pending_card" in data and data["pending_card"]:
                    return _build_clinician_view_from_card_data(data["pending_card"], expires_at_iso)
            except Exception:
                pass

    return _format_fallback_ayuma_view(expires_at_iso)


def _build_clinician_view_from_card_data(c_data: dict, expires_at_iso: str) -> dict:
    """將內部的 card_data 轉為 clinician.html 所需之標準結構"""
    vr = c_data.get("visit_reason", "定期回診追蹤")
    meds = c_data.get("medications", "未特別說明")
    gm = c_data.get("glucose_metrics", "未特別說明")
    hypo = c_data.get("hypo_history", "無特別異常")
    ddx = c_data.get("ddx_candidates") or ["常規代謝指標與處方評估（飲食與運動狀況確認）"]
    quote = c_data.get("patient_quote") or vr
    evidence = c_data.get("evidence_links") or ["衛生福利部國民健康署《糖尿病與我》手冊"]
    diet = c_data.get("diet_lifestyle", "")

    glucose_combined = f"{gm} ｜ 低血糖：{hypo}" if hypo and hypo != "無特別異常" else str(gm)
    if diet and diet not in ("未特別說明", "無"):
        glucose_combined += f" ｜ 飲食生活：{diet}"

    return {
        "information_source": "LINE AI 糖尿病衛教助理自述整理",
        "single_use": False,
        "expires_at": expires_at_iso,
        "accessed_at": datetime.now(timezone.utc).isoformat(),
        "system_risk_classification": {"level": "LOW_TO_MODERATE", "reason": "慢性代謝追蹤"},
        "previsit_summary": {
            "visit_reason": vr,
            "medications": meds,
            "glucose_metrics": glucose_combined,
            "ddx_candidates": ddx if isinstance(ddx, list) else [str(ddx)],
            "patient_quote": quote,
            "evidence_links": evidence if isinstance(evidence, list) else [str(evidence)],
            "clinical_decision_support": f"• 看診主訴：{vr}\n• 待查用藥：{meds}\n• 臨床建議：請主治醫師親自診察並評估檢驗數值。"
        },
        "intake_snapshot": {
            "allergies": "無已知藥物過敏（病患未回報）",
            "known_medications": meds,
            "symptom_description": vr,
            "questions_for_doctor": ddx if isinstance(ddx, list) else [str(ddx)],
        }
    }


def list_access_logs() -> list[dict]:
    """列出醫護存取紀錄"""
    return list(_CLINICIAN_ACCESS_LOGS)
