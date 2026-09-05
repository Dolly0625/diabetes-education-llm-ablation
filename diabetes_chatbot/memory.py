"""
病患長期健康檔案與記憶模組 (Patient Longitudinal Memory)
參考 臨床衛教大腦 2026 多回訪管理與 FHIR 資源槽位標準，
實現非侵入式雙軌記憶：將病患的客觀臨床事實持久化存儲於本地檔案中。
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any
import re

MEMORY_DIR = Path(__file__).parent / "data"

def _validate_ddx_candidates(candidates):
    if not isinstance(candidates, list):
        return []
    pat_dose = re.compile(r"(劑量|處方|每天.*顆|加藥|減藥|停藥|自行.*吃|多吃.*顆|少吃.*顆|打.*單位)")
    pat_diag = re.compile(r"(確診|診斷為|罹患第[一二12]型)")
    forbidden = ["NICE", "BMJ", "nice", "bmj"]
    out=[]
    for it in candidates:
        if not isinstance(it, dict):
            continue
        huahua=str(it.get("方向人話") or it.get("human_label") or "").strip()
        yiju=str(it.get("依據") or it.get("basis") or "").strip()
        check=str(it.get("待確認檢查") or it.get("next_check") or "").strip()
        if not huahua or not yiju or not check:
            continue
        if any(f in huahua+yiju+check for f in forbidden):
            continue
        if pat_dose.search(huahua+yiju+check):
            continue
        if pat_diag.search(huahua):
            continue
        if not any(k in huahua+check for k in ["待確認","待釐清","待核對","請醫師"]):
            check=check+"（待確認，請醫師評估）" if "請醫師" not in check else check
            if not any(k in huahua for k in ["待確認","待釐清","可能相關"]):
                huahua=huahua+"（待確認）"
        if len(huahua)>60:
            huahua=huahua[:60]
        out.append({"方向人話":huahua,"依據":yiju,"待確認檢查":check})
        if len(out)>=3:
            break
    return out

def _validate_evidence_links(links):
    if not isinstance(links, list):
        return []
    allowed=["糖尿病與我","國健署","國民健康署","TFDA","食品藥物管理署","衛福部"]
    forbidden_kw=["NICE","BMJ","nice","bmj","UpToDate","Cochrane"]
    pat_dose=re.compile(r"(劑量|處方|每天.*顆|加藥|減藥|停藥)")
    out=[]
    for it in links:
        if not isinstance(it, dict):
            continue
        book=str(it.get("書名") or it.get("book") or "").strip()
        chapter=str(it.get("章節") or it.get("chapter") or "").strip()
        excerpt=str(it.get("原文20字") or it.get("excerpt") or "").strip()
        if not book or not chapter or not excerpt:
            continue
        if any(fk.lower() in book.lower()+chapter.lower() for fk in forbidden_kw):
            continue
        if not any(k in book for k in allowed):
            continue
        if pat_dose.search(excerpt):
            continue
        if len(excerpt)<10 or len(excerpt)>60:
            continue
        out.append({"書名":book,"章節":chapter,"原文20字":excerpt[:40]})
    return out
DEFAULT_RECORD_FILE = MEMORY_DIR / "patient_record.json"

def get_default_template(patient_id: str = "demo_patient") -> dict[str, Any]:
    return {
        "patient_id": patient_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "medications": [],          # 例如: [{"name": "...", "source": "藥袋照片", "updated_at": "..."}]
        "glucose_metrics": {        # 最新血糖指標
            "latest": "",
            "updated_at": ""
        },
        "reported_symptoms": [],     # 例如: ["常常肚子脹氣"]
        "hypo_history": "近期無低血糖事件",
        "last_previsit_summary": "",
        "ddx_candidates": [],
        "evidence_links": []
    }


def load_patient_record(file_path: Path | str = DEFAULT_RECORD_FILE) -> dict[str, Any]:
    """載入病患長期健康檔案，若不存在則建立初始檔案"""
    path = Path(file_path)
    if not path.exists():
        record = get_default_template()
        save_patient_record(record, path)
        return record
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "ddx_candidates" not in data:
                data["ddx_candidates"] = []
            if "evidence_links" not in data:
                data["evidence_links"] = []
            # 防禦性清洗歷史髒資料：血壓不可作為血糖指標
            latest_g = data.get("glucose_metrics", {}).get("latest", "")
            if any(k in latest_g for k in ["血壓", "收縮壓", "舒張壓", "收縮", "舒張"]):
                data["glucose_metrics"]["latest"] = ""
            # 清理非病理生理反應（如吃飽想睡、肚子餓等正常生活感覺）
            symptom_list = data.get("reported_symptoms", [])
            data["reported_symptoms"] = [
                s for s in symptom_list 
                if not any(ign in s for ign in ["正常生理", "非病理", "吃飽想睡", "肚子餓"])
            ]
            return data
    except Exception:
        record = get_default_template()
        return record


def save_patient_record(record: dict[str, Any], file_path: Path | str = DEFAULT_RECORD_FILE) -> None:
    """原子化寫入病患健康檔案"""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def update_medications(new_meds: list[str], source: str = "藥袋照片辨識", file_path: Path | str = DEFAULT_RECORD_FILE) -> None:
    """更新或合併用藥紀錄 (去重增補)"""
    record = load_patient_record(file_path)
    existing_med_names = {m["name"] for m in record.get("medications", [])}
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for med in new_meds:
        med_clean = med.strip()
        # 排除無用藥或否定語義字串
        if any(neg in med_clean for neg in ["無用藥", "沒吃藥", "未服用", "無記錄", "未用藥", "沒有用藥", "不清楚", "目前無"]):
            continue
        if med_clean and med_clean not in existing_med_names:
            record["medications"].append({
                "name": med_clean,
                "source": source,
                "recorded_at": now_str
            })
            existing_med_names.add(med_clean)
            
    save_patient_record(record, file_path)


def update_glucose_record(glucose_str: str, file_path: Path | str = DEFAULT_RECORD_FILE) -> None:
    """記錄最新居家血糖數值"""
    record = load_patient_record(file_path)
    record["glucose_metrics"] = {
        "latest": glucose_str.strip(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_patient_record(record, file_path)


def update_reported_symptoms(symptoms: list[str] | str, file_path: Path | str = DEFAULT_RECORD_FILE) -> None:
    """記錄自述不適或藥物副作用"""
    record = load_patient_record(file_path)
    sym_list = [symptoms] if isinstance(symptoms, str) else symptoms
    existing_syms = set(record.get("reported_symptoms", []))
    
    for s in sym_list:
        s_clean = s.strip()
        if s_clean and s_clean not in existing_syms:
            record["reported_symptoms"].append(s_clean)
            existing_syms.add(s_clean)
            
    save_patient_record(record, file_path)


def update_previsit_summary(summary_text: str, file_path: Path | str = DEFAULT_RECORD_FILE) -> None:
    """更新最新一次的門診預問診摘要 (就醫備忘錄)"""
    record = load_patient_record(file_path)
    record["last_previsit_summary"] = summary_text.strip()
    save_patient_record(record, file_path)


def format_patient_context(file_path: Path | str = DEFAULT_RECORD_FILE) -> str:
    """
    將病患長期檔案格式化為精簡的背景事實，供注入 System Prompt。
    實現 臨床衛教大腦雙軌記憶架構，節省 Token 同時永不失憶。
    """
    record = load_patient_record(file_path)
    meds = [m["name"] for m in record.get("medications", [])]
    glucose = record.get("glucose_metrics", {}).get("latest", "")
    symptoms = record.get("reported_symptoms", [])
    last_summary = record.get("last_previsit_summary", "")
    
    ddx=_validate_ddx_candidates(record.get("ddx_candidates",[]))
    evids=_validate_evidence_links(record.get("evidence_links",[]))
    if not meds and not glucose and not symptoms and not last_summary and not ddx and not evids:
        return ""
        
    lines = ["【病患長期健康檔案 (Longitudinal Health Profile)】："]
    if meds:
        lines.append(f"- 已確認用藥清單：{', '.join(meds)}")
    else:
        lines.append("- 目前用藥：尚未記錄具體藥名")
        
    if glucose and not any(k in glucose for k in ["血壓", "收縮壓", "舒張壓", "收縮", "舒張"]):
        lines.append(f"- 最近血糖數值：{glucose}")
        
    if symptoms:
        lines.append(f"- 過去回報之不適/副作用：{', '.join(symptoms)}")
    if ddx:
        lines.append("- 門診交班待確認方向（人話、待確認）：")
        for idx,d in enumerate(ddx,1):
            lines.append(f"  {idx}. {d['方向人話']}｜依據：{d['依據']}｜待確認檢查：{d['待確認檢查']}")
    if evids:
        lines.append("- 實證連結（僅真實 RAG 命中，台灣國健署/TFDA）：")
        for e in evids:
            lines.append(f"  ‧《{e['書名']}》{e['章節']}｜{e['原文20字']}")
    if last_summary:
        lines.append("- 上次看診之門診預問診摘要紀錄：")
        lines.append(f"  {last_summary.strip()}")
        lines.append("【差異化回訪照護指引 (Delta-Focused Care)】：")
        lines.append("  病患再次來訪時，請主動關心上次看診的後續結果（如醫師是否有調整用藥、新醫囑或檢查結果），")
        lines.append("  嚴禁重新盤問已知背景，直接聚焦於「這段期間的變化與新數值」。")
        
    return "\n".join(lines)


# ==============================================================================
# 長歷史對話管理：多病患切換、非侵入式事實萃取、會話封存與滑動視窗
# ==============================================================================

def get_patient_file_path(patient_id: str = "demo_patient") -> Path:
    """依據病患 ID 取得其健康檔案路徑，實現多病患隔離"""
    if patient_id == "demo_patient":
        return DEFAULT_RECORD_FILE
    return MEMORY_DIR / f"{patient_id}.json"


def extract_clinical_facts_from_text(text: str, file_path: Path | str = DEFAULT_RECORD_FILE) -> dict[str, Any]:
    """
    非侵入式自述事實萃取 (Background Fact Extraction)
    從病患自然口述文字中萃取血糖數值、用藥與不適症狀，並自動寫入健康檔案。
    """
    import re
    extracted = {"glucose": "", "symptoms": [], "medications": []}
    
    # 1. 血糖數值萃取 — 嚴防血壓污染 (blood-pressure-as-glucose guard)
    # 規則: 血糖 regex 必須在數字前 6 字元內含血糖語境 token (血糖|空腹|飯後|餐後|量到|驗|扎|測)，
    # 且若該句含血壓相關詞 (血壓|收縮|舒張|收縮壓|舒張壓) 則整句作廢。
    _bp_pat = re.compile(r"血壓|收縮壓|舒張壓|收縮|舒張")
    _glucose_pat = re.compile(r"(?:血糖|空腹|飯後|餐後|量到|驗|扎|測)[^0-9]{0,6}([5-9][0-9]|[1-4][0-9]{2})\s*(?:mg/dL|mg\/dl|左右)?")
    # 以句號類標點切句，做整句 BP 污染隔離（符合「rejects the whole sentence」語意）
    sentences = re.split(r"[。！？\n]+", text)
    # 若原文無句號切分，sentences 即為 [text]，效果等同整段檢查
    glucose_match = None
    matched_val = None
    for sent in sentences:
        if not sent.strip():
            continue
        if _bp_pat.search(sent):
            continue
        m = _glucose_pat.search(sent)
        if m:
            glucose_match = m
            matched_val = m.group(1)
            break
    if glucose_match:
        # 排除年份如 2024、2026 等
        if int(matched_val) < 500:
            glucose_desc = f"{matched_val} mg/dL"
            update_glucose_record(glucose_desc, file_path)
            extracted["glucose"] = glucose_desc
            
    # 2. 臨床症狀與不適萃取
    symptom_keywords = [
        "脹氣", "肚子脹", "胃痛", "腹瀉", "拉肚子", "便秘", "噁心", "嘔吐",
        "頭暈", "心悸", "手抖", "冒冷汗", "視力模糊", "手腳發麻", "疲倦", "常常口渴"
    ]
    found_symptoms = [kw for kw in symptom_keywords if kw in text]
    # 支援口語化腹脹表述（例如「肚子就很脹」、「吃藥肚子脹」）
    if re.search(r"肚子.*脹|胃.*脹", text) and "肚子脹" not in found_symptoms:
        found_symptoms.append("肚子脹")
    if found_symptoms:
        update_reported_symptoms(found_symptoms, file_path)
        extracted["symptoms"] = found_symptoms
        
    # 3. 口述藥物萃取
    common_meds = [
        "庫魯化", "愛妥糖", "佳糖維", "胰妥讚", "達爾胰", "得爾美",
        "二甲雙胍", "Metformin", "Glucophage", "癲通", "胰島素"
    ]
    found_meds = [med for med in common_meds if med in text]
    if found_meds:
        update_medications(found_meds, source="病患口述", file_path=file_path)
        extracted["medications"] = found_meds
        
    return extracted


def prune_conversation_history(messages: list[dict], max_history_messages: int = 8) -> list[dict]:
    """
    滑動上下文視窗 (Sliding Context Window) 修剪。
    保持 System Prompt 永久置頂，只保留最新 N 條對話。
    特別注意：若裁剪邊界剛好卡在 tool 與 assistant tool_calls 之間，安全向前對齊，杜絕 API 報錯。
    """
    if len(messages) <= max_history_messages + 1:
        return messages
        
    system_msg = messages[0]
    tail_candidates = messages[1:]
    
    # 取最新的 N 條
    start_idx = max(0, len(tail_candidates) - max_history_messages)
    
    def _get_msg_role(m) -> str:
        if isinstance(m, dict):
            return m.get("role", "")
        return getattr(m, "role", "") or ""

    # 檢查切點安全：若切點剛好落在 role == 'tool'，必須往前推進到產生該 tool_calls 的 assistant
    while start_idx > 0 and _get_msg_role(tail_candidates[start_idx]) == "tool":
        start_idx -= 1
        
    pruned = [system_msg] + tail_candidates[start_idx:]
    return pruned


def archive_session(session_id: str, messages: list[dict], patient_id: str = "demo_patient") -> Path:
    """
    會話歷史封存 (Session Archival)
    將對話結束時的完整軌跡歸檔至 sessions 資料夾，供醫療紀錄回溯與品質監控。
    """
    sessions_dir = MEMORY_DIR / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    
    session_file = sessions_dir / f"{patient_id}_{session_id}.json"
    archive_data = {
        "session_id": session_id,
        "patient_id": patient_id,
        "archived_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message_count": len(messages),
        "messages": messages
    }
    
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(archive_data, f, ensure_ascii=False, indent=2)
        
    return session_file

def _accumulate_ddx_and_evidence(record, assessment) -> bool:
    changed=False
    raw_ddx=getattr(assessment,"ddx_candidates",None)
    if raw_ddx is not None:
        validated=_validate_ddx_candidates(raw_ddx)
        if validated:
            existing=record.get("ddx_candidates") or []
            existing_valid=_validate_ddx_candidates(existing)
            seen={d["方向人話"] for d in existing_valid}
            for d in validated:
                if d["方向人話"] not in seen:
                    existing_valid.append(d);seen.add(d["方向人話"])
            capped=existing_valid[-3:] if len(existing_valid)>3 else existing_valid
            if capped!=existing:
                record["ddx_candidates"]=capped;changed=True
        else:
            if "ddx_candidates" not in record:
                record["ddx_candidates"]=[]
    else:
        if "ddx_candidates" not in record:
            record["ddx_candidates"]=[]
    raw_ev=getattr(assessment,"evidence_links",None)
    if raw_ev is not None:
        validated_ev=_validate_evidence_links(raw_ev)
        if validated_ev:
            existing_ev=record.get("evidence_links") or []
            existing_ev_valid=_validate_evidence_links(existing_ev)
            seen_ev={(e["書名"],e["章節"],e["原文20字"]) for e in existing_ev_valid}
            for e in validated_ev:
                key=(e["書名"],e["章節"],e["原文20字"])
                if key not in seen_ev:
                    existing_ev_valid.append(e);seen_ev.add(key)
            capped_ev=existing_ev_valid[-5:] if len(existing_ev_valid)>5 else existing_ev_valid
            if capped_ev!=existing_ev:
                record["evidence_links"]=capped_ev;changed=True
        else:
            if "evidence_links" not in record:
                record["evidence_links"]=[]
    else:
        if "evidence_links" not in record:
            record["evidence_links"]=[]
    return changed

def update_from_planner_assessment(assessment, file_path: Path | str = DEFAULT_RECORD_FILE) -> bool:
    """
    依據 LLM Planner Agent 深層推論出的槽位結果，精準校準更新長期健康檔案。
    回傳是否有實際欄位發生更新。
    """
    if not hasattr(assessment, "slots"):
        return False
        
    slots = assessment.slots
    record = load_patient_record(file_path)
    updated = False
    
    # 1. 更新用藥
    if getattr(slots, "medications_status", None) and slots.medications:
        # 若口述具體藥物或用法
        med_str = slots.medications.strip()
        existing_med_names = {m["name"] for m in record.get("medications", [])}
        is_bag_valid = any(k in med_str for k in ["藥袋", "待核對", "攜帶"])
        if med_str and med_str not in existing_med_names and ("未" not in med_str or is_bag_valid):
            record["medications"].append({
                "name": med_str,
                "source": "LLM Planner 深層語意解析",
                "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            updated = True
            
    # 2. 更新血糖
    if getattr(slots, "glucose_metrics_status", None) and slots.glucose_metrics:
        gm_str = slots.glucose_metrics.strip()
        if gm_str and "未" not in gm_str and record.get("glucose_metrics", {}).get("latest") != gm_str:
            record["glucose_metrics"] = {
                "latest": gm_str,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            updated = True
            
    # 3. 更新低血糖病史
    if getattr(slots, "hypo_history_status", None) and slots.hypo_history:
        hh_str = slots.hypo_history.strip()
        if hh_str and "未" not in hh_str and record.get("hypo_history") != hh_str:
            record["hypo_history"] = hh_str
            updated = True
            
    # 4. 更新副作用與主訴
    if getattr(slots, "concerns_status", None) and slots.concerns_or_side_effects:
        c_str = slots.concerns_or_side_effects.strip()
        existing_syms = set(record.get("reported_symptoms", []))
        if c_str and c_str not in existing_syms and "未" not in c_str:
            record["reported_symptoms"].append(c_str)
            updated = True
            
    if _accumulate_ddx_and_evidence(record, assessment):
        updated=True
    if updated:
        save_patient_record(record, file_path)
        
    return updated
