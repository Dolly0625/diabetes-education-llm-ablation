import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 將 diabetes-rag/src 加入模組搜尋路徑以引入真實 RAG 模組
RAG_SRC_DIR = Path(__file__).parent.parent / "diabetes-rag" / "src"
if str(RAG_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_SRC_DIR))

try:
    from rag_retrieval import EvidenceRetrievalTool
    _RAG_TOOL_INSTANCE = EvidenceRetrievalTool(source_id="tfda+hpa")
except Exception:
    _RAG_TOOL_INSTANCE = None

# 後備國健署手冊檔案路徑 (Fail-Safe 降級保底)
BOOK_PATH = Path(__file__).parent.parent / "diabetes-rag/src/rag_retrieval/data/hpa_dm_book.json"

# 飲食與餐點意圖關鍵詞清單（涵蓋常見食物、料理、用餐動態與營養代謝名詞）
DIET_INTENT_KEYWORDS = {
    # 用餐與行為
    "吃", "喝", "餐", "飲食", "早餐", "午餐", "晚餐", "宵夜", "下午茶", "點心", "便當", "菜單", "食物", "食品", "食材",
    # 常見食材與料理
    "飯", "麵", "米", "粥", "菜", "肉", "蛋", "豆", "魚", "奶", "水果",
    "麵包", "地瓜", "燕麥", "蔬果", "豆乾", "豆皮", "豆腐", "蘿蔔", "零食", "飲料",
    # 營養、烹調與代謝
    "澱粉", "醣", "糖類", "熱量", "卡路里", "大卡", "份量", "油炸", "油煎", "清蒸", "水煮",
    "高纖", "膳食纖維", "飽足感"
}

# 國健署手冊官方糖尿病飲食原則預設衛教內容（客觀指引，避免放任 LLM 自由臆測）
HPA_DIET_GUIDELINE_DEFAULT = (
    "【官方衛教指引 (國健署手冊 - 糖尿病飲食原則)】\n"
    "1. 均衡攝取六大類食物：以每餐攝取固定醣量和高纖、適量油脂等方式達到控制血糖目的。六大類包含全穀雜糧類 (主食類)、豆魚蛋肉類、乳品類、蔬菜類、水果類和油脂與堅果種子類。\n"
    "2. 定時定量攝取含醣類食物：醣類總量直接影響血糖變化，定時定量有助於血糖穩定。\n"
    "3. 儘量避免精緻糖類或加糖食物，以及油炸、高脂食品。\n"
    "4. 多選擇高纖及多樣化食物，如全穀雜糧、蔬菜，可增加飽足感並減緩醣類吸收。\n"
    "5. 選擇低油烹調方式：多採清蒸、水煮、清燉、涼拌等，少用油炸。"
)

def _is_diet_or_meal_query(keyword: str, user_raw_input: str = "", domain: object = "") -> bool:
    """確定性判定是否屬於飲食或餐點查詢意圖，支援臨床規劃大腦領域標籤（字串或 Enum）或語意概念判定"""
    domain_str = getattr(domain, "value", str(domain or "")).upper()
    if domain_str == "DIET_NUTRITION":
        return True
    combined = f"{keyword} {user_raw_input}".lower()
    return any(term in combined for term in DIET_INTENT_KEYWORDS)

DEFINITION_INTENT_KEYWORDS = {
    "成因", "形成", "原理", "是什麼", "怎麼形成", "為什麼", "定義", "怎麼來的"
}

def _is_definition_query(keyword: str, user_raw_input: str = "", domain: object = "") -> bool:
    """判定是否為糖尿病定義/成因/形成機制查詢；命中時需抑制圖譜 TREATS 雜訊，僅保留向量手冊軌"""
    domain_str = getattr(domain, "value", str(domain or "")).upper()
    if domain_str == "GENERAL_EDUCATION":
        return True
    combined = f"{keyword} {user_raw_input}".lower()
    return any(term in combined for term in DEFINITION_INTENT_KEYWORDS)

def _is_irrelevant_graph_chunk(chunk, keyword: str, user_raw_input: str) -> bool:
    """
    在飲食/餐點意圖下，判定 chunk 是否屬於不直接相關的圖譜/藥物/ADR 警訊。
    """
    retriever_str = str(getattr(chunk, "retriever", "")).lower()
    source_str = str(getattr(chunk, "source", "")).lower()
    chunk_id_str = str(getattr(chunk, "chunk_id", "")).lower()
    content_str = str(getattr(chunk, "content", "")).lower()
    combined_query = f"{keyword} {user_raw_input}".lower()

    # 1. 類澱粉樣變性症（insulin amyloidosis）絕對過濾（除非使用者主動詢問該病名）
    if "insulin_amyloidosis" in source_str or "insulin_amyloidosis" in chunk_id_str:
        if "類澱粉" not in combined_query and "amyloidosis" not in combined_query:
            return True

    # 2. 移除所有圖譜 (graph) 檢索所得或 TFDA 藥品 ADR 警訊
    # 圖譜三元組資料庫現皆為 TFDA 藥品安全警訊與適應症，在純飲食情境下均為誤召回
    if "graph" in retriever_str or "tfda-risk" in source_str or "tfda-risk" in chunk_id_str:
        # 若使用者查詢未主動提及胰島素或注射，卻包含胰島素/注射警訊
        if ("胰島素" in content_str or "注射" in content_str) and ("胰島素" not in combined_query and "注射" not in combined_query):
            return True
        # 若使用者查詢未主動提及類澱粉或腫塊
        if ("類澱粉" in content_str or "腫塊" in content_str) and ("類澱粉" not in combined_query and "腫塊" not in combined_query):
            return True
        # 若為純飲食查詢，圖譜藥物警訊均屬不相關
        return True

    return False


def _fallback_search_book(keyword: str) -> str:
    """後備純文字手冊搜尋，確保任何情況下絕不拋出未捕捉例外"""
    if not BOOK_PATH.exists():
        return "官方手冊檔案暫時無法讀取。"
    try:
        with open(BOOK_PATH, encoding="utf-8") as f:
            chapters = json.load(f)
        terms = keyword.split()
        if len(terms) == 1 and len(keyword) >= 4:
            terms = [keyword[i:i+2] for i in range(0, len(keyword)-1)]
        best_chunk = ""
        max_score = 0
        for ch in chapters:
            content = ch.get("page_content", "")
            score = sum(content.count(t) for t in terms)
            if score > max_score:
                max_score = score
                best_chunk = content
        if max_score > 0:
            first_t = next((t for t in terms if t in best_chunk), "")
            idx = best_chunk.find(first_t) if first_t else 0
            start = max(0, idx - 30)
            end = min(len(best_chunk), idx + 350)
            return f"【官方衛教指引 (國健署手冊)】\n{best_chunk[start:end].strip()}"
    except Exception:
        pass
    return "手冊中未找到完全相符的章節。"


def search_handbook(keyword: str, user_raw_input: str = "", domain: str = "") -> str:
    """
    透過正式跨組契約調用 EvidenceRetrievalTool。
    執行雙軌混合檢索（TFDA 官方藥品風險溝通圖譜 + 國健署向量語意檢索 + RRF 融合）。
    針對飲食/餐點意圖進行安全過濾，移除不相關的圖譜 ADR 警訊。
    針對糖尿病定義/成因/形成機制查詢，抑制圖譜軌 TREATS 雜訊，僅保留向量手冊軌。
    """
    is_diet = _is_diet_or_meal_query(keyword, user_raw_input, domain=domain)
    is_definition = _is_definition_query(keyword, user_raw_input, domain=domain)

    if _RAG_TOOL_INSTANCE is None:
        fallback_res = _fallback_search_book(keyword)
        if "未找到完全相符" not in fallback_res and "無法讀取" not in fallback_res:
            return fallback_res
        if is_diet:
            return HPA_DIET_GUIDELINE_DEFAULT
        return "衛生福利部官方手冊與資料庫中暫未查得完全對應的專屬條目。建議民眾回診時諮詢專科醫師或衛教師，依個別情況給予專業指引。"

    try:
        req_id = f"req_{int(time.time() * 1000)}"
        now_iso = datetime.now(timezone.utc).astimezone().isoformat()
        raw_text = user_raw_input.strip() if user_raw_input.strip() else keyword.strip()
        
        # 語意向量檢索採用完整語意查詢，避免多次串行呼叫 Embedding API 造成延遲膨脹
        queries = [keyword.strip()]
            
        request_payload = {
            "request_id": req_id,
            "schema_version": "rag-v1",
            "user_raw_input": raw_text,
            "retrieval_queries": queries[:5],
            "guardrail_result": {
                "intent_tags": ["GENERAL_EDUCATION"],
                "risk_flags": [],
                "context_modifiers": {
                    "time_frame": "CURRENT",
                    "target_subject": "SELF",
                    "polarity": "AFFIRMATIVE",
                    "language": "zh-TW"
                },
                "router_status": "G_GENERAL_EDUCATION",
                "reason_codes": ["MEETS_SAFE_SCOPE"]
            },
            "language": "zh-TW",
            "timestamp": now_iso
        }
        
        resp = _RAG_TOOL_INSTANCE.retrieve(request_payload)
        
        valid_chunks = []
        if resp and resp.chunks:
            for chunk in resp.chunks:
                # 定義/成因查詢：圖譜 TREATS 對定義永遠是雜訊，丟棄 graph/TFDA-risk 軌，僅保留向量手冊
                if is_definition:
                    _retriever_str = str(getattr(chunk, "retriever", "")).lower()
                    _source_str = str(getattr(chunk, "source", "")).lower()
                    _chunk_id_str = str(getattr(chunk, "chunk_id", "")).lower()
                    if "graph" in _retriever_str or "tfda-risk" in _source_str or "tfda-risk" in _chunk_id_str:
                        continue
                # 飲食/餐點情境下過濾不相關圖譜與 ADR 警訊
                if is_diet and _is_irrelevant_graph_chunk(chunk, keyword, user_raw_input):
                    continue
                valid_chunks.append(chunk)

        if valid_chunks:
            evidence_blocks = []
            for i, chunk in enumerate(valid_chunks[:3]):
                source_id = chunk.source or chunk.chunk_id
                risk_lvl = chunk.evidence_risk_level or "LOW"
                content_text = chunk.content.strip()
                evidence_blocks.append(
                    f"【官方臨床證據 {i+1}｜來源：{source_id}｜風險標籤：{risk_lvl}】\n{content_text}"
                )
            return "\n\n".join(evidence_blocks)
        else:
            # 查無特定條目或已過濾不相關圖譜雜訊，平滑降級至後備手冊搜尋或客觀指引
            fallback_res = _fallback_search_book(keyword)
            if "未找到完全相符" not in fallback_res and "無法讀取" not in fallback_res:
                return fallback_res
            if is_diet:
                return HPA_DIET_GUIDELINE_DEFAULT
            return "衛生福利部官方手冊與資料庫中暫未查得完全對應的專屬條目。建議民眾回診時諮詢專科醫師或衛教師，依個別情況給予專業指引。"
            
    except Exception:
        # Fail-Safe: 任何未預期例外均退回本地手冊或客觀指引
        fallback_res = _fallback_search_book(keyword)
        if "未找到完全相符" not in fallback_res and "無法讀取" not in fallback_res:
            return fallback_res
        if is_diet:
            return HPA_DIET_GUIDELINE_DEFAULT
        return "衛生福利部官方手冊與資料庫中暫未查得完全對應的專屬條目。建議民眾回診時諮詢專科醫師或衛教師，依個別情況給予專業指引。"


def _to_clean_str(val, default: str = "未特別說明") -> str:
    """將輸入值安全轉為乾淨字串，支援 list/tuple 轉頓號分隔字串"""
    if val is None:
        return default
    if isinstance(val, (list, tuple)):
        clean_items = [str(x).strip() for x in val if str(x).strip()]
        return "、".join(clean_items) if clean_items else default
    s = str(val).strip()
    return s if s else default


def _format_glucose_section(
    glucose_metrics: str,
    hypo_history: str,
    glucose_range=None,
    side_effects_or_concerns: str = "",
) -> str:
    """糖線三數字：最近/最低/平常 + 不適故事/低血糖史"""
    if glucose_range and isinstance(glucose_range, dict):
        recent = glucose_range.get("recent")
        lowest = glucose_range.get("lowest")
        usual = glucose_range.get("usual")
        story = glucose_range.get("story", "")
        parts = []
        if recent:
            parts.append(f"最近 {recent}")
        if lowest:
            parts.append(f"最低 {lowest}")
        if usual:
            parts.append(f"平常 {usual}")
        base = " / ".join(parts) if parts else _to_clean_str(glucose_metrics)
        if story:
            return f"{base}；不適故事：{story}" if base else story
        hypo_clean = _to_clean_str(hypo_history, default="")
        if hypo_clean and hypo_clean not in ("近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "", "無", "無低血糖事件"):
            if "無低血糖" not in hypo_clean and "未提及" not in hypo_clean and hypo_clean != "無":
                return f"{base}；低血糖史：{hypo_clean}"
        return base
    elif glucose_range is not None:
        if not isinstance(glucose_range, dict):
            s = str(glucose_range).strip()
            if s:
                return s
    gm = _to_clean_str(glucose_metrics)
    hypo = _to_clean_str(hypo_history, default="")
    if hypo and hypo not in ("近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "", "無", "無低血糖事件"):
        if "無低血糖" not in hypo and "未提及" not in hypo and hypo != "無":
            return f"{gm}；低血糖史：{hypo}"
    return gm


def _normalize_ddx_list(
    ddx_candidates,
    side_effects_or_concerns: str = "",
    hypo_history: str = "",
) -> list:
    if ddx_candidates:
        normalized = []
        for item in ddx_candidates:
            if isinstance(item, dict):
                label = (
                    item.get("label")
                    or item.get("direction")
                    or item.get("text")
                    or item.get("title")
                    or str(item.get("value", "") if item.get("value") else "")
                    or ""
                )
                if not label:
                    for k, v in item.items():
                        if k not in ("check", "exam", "待做檢查", "action", "next_step"):
                            label = str(v)
                            break
                check = (
                    item.get("check")
                    or item.get("exam")
                    or item.get("待做檢查")
                    or item.get("action")
                    or item.get("next_step")
                    or ""
                )
                label = str(label).strip()
                check = str(check).strip()
                if not label:
                    continue
                if "待確認" not in label:
                    label = f"待確認{label}"
                if "待做檢查" not in label and not check:
                    check = "回診與醫師討論並視需要安排檢查"
                if check:
                    if "待做檢查" in label:
                        normalized.append(label)
                    else:
                        normalized.append(f"{label} — 待做檢查：{check}")
                else:
                    normalized.append(label)
            else:
                s = str(item).strip()
                if not s:
                    continue
                if "待確認" not in s:
                    s = f"待確認{s}"
                if "待做檢查" not in s:
                    s = f"{s} — 待做檢查：回診與醫師討論"
                normalized.append(s)
        normalized = [n for n in normalized if n.strip()]
        if len(normalized) == 1:
            normalized.append("待確認整體血糖穩定性 — 待做檢查：回診抽 HbA1c 並帶血糖紀錄")
        if len(normalized) >= 2:
            return normalized[:3]
        if len(normalized) == 0:
            pass
        else:
            return normalized[:3]
    fallback = []
    if hypo_history and hypo_history.strip() not in ("近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "", "無", "無低血糖事件", "近期無低血糖或冷汗心悸發作"):
        if "無低血糖" not in hypo_history and "未提及" not in hypo_history and hypo_history.strip() != "無":
            fallback.append(f"待確認低血糖症狀與血糖偏低的關聯 — 待做檢查：回診抽 HbA1c、檢視近期血糖紀錄與飲食時間（自述：{hypo_history}）")
    if side_effects_or_concerns and side_effects_or_concerns.strip() not in ("無特別異常", "無", "", "未特別說明", "無特別異常"):
        if side_effects_or_concerns.strip() not in (hypo_history or ""):
            fallback.append(f"待確認用藥後不適感受的相關性 — 待做檢查：回診與醫師討論不適時間與藥袋紀錄（自述：{side_effects_or_concerns}）")
    if len(fallback) < 2:
        fallback.append("待確認飲食與血糖波動的關聯 — 待做檢查：回診提供近期飲食與血糖日誌請醫師評估")
    if len(fallback) < 2:
        fallback.append("待確認整體用藥順從性與血糖控制 — 待做檢查：回診攜藥袋核對並討論是否需轉衛教")
    return fallback[:3]


def _format_evidence_lines(evidence_links) -> list:
    if not evidence_links:
        return []
    lines = []
    for item in evidence_links:
        if isinstance(item, dict):
            text = (
                item.get("text")
                or item.get("title")
                or item.get("source")
                or item.get("citation")
                or ""
            )
            url = item.get("url") or item.get("link") or ""
            text = str(text).strip()
            if not text:
                continue
            if url:
                lines.append(f"{text}（{url}）")
            else:
                lines.append(text)
        else:
            s = str(item).strip()
            if s:
                lines.append(s)
    return lines


def _format_patient_quote(patient_quote) -> str:
    if patient_quote and str(patient_quote).strip():
        return str(patient_quote).strip()
    return "（尚未記錄原話）"


def generate_previsit_intake_summary(
    visit_reason: str = "門診定期追蹤",
    medications: str = "未特別說明",
    glucose_metrics: str = "未特別說明",
    hypo_history: str = "近期未提及或無發生",
    side_effects_or_concerns: str = "無特別異常",
    ddx_candidates=None,
    evidence_links=None,
    patient_quote=None,
    glucose_range=None,
) -> str:
    meds_display = _to_clean_str(medications)
    if "藥袋" not in meds_display:
        meds_with_bag = f"{meds_display}（藥袋已帶待核對）"
    else:
        meds_with_bag = meds_display
    glucose_section = _format_glucose_section(glucose_metrics, hypo_history, glucose_range, side_effects_or_concerns)
    ddx_list = _normalize_ddx_list(ddx_candidates, side_effects_or_concerns, hypo_history)
    evidence_lines = _format_evidence_lines(evidence_links)
    quote_text = _format_patient_quote(patient_quote)
    lines = []
    lines.append("")
    lines.append("=" * 50)
    lines.append("【新陳代謝科 門診預問診摘要 (Pre-visit Intake Summary)】")
    lines.append("自述整理僅供參考非診斷｜亦可作為衛生福利部「就醫準備備忘錄」出示")
    lines.append("=" * 50)
    lines.append(f"① 主訴一句話：{visit_reason}")
    lines.append(f"② 用藥現況：{meds_with_bag}")
    lines.append(f"③ 糖線三數字：{glucose_section}")
    lines.append("④ 待確認方向（請醫師評估 2-3 條，每條含待做檢查）：")
    for item in ddx_list:
        lines.append(f"  • {item}")
    lines.append(f"⑤ 阿嬤原話（不潤飾）：「{quote_text}」")
    if evidence_lines:
        lines.append("⑥ 出處小字（僅 RAG 真查到才印：國健署/TFDA 人話）：")
        for ev in evidence_lines:
            lines.append(f"  • {ev}")
    lines.append("⑦ 醫師空白欄：□抽 HbA1c  □聊調藥  □轉衛教")
    lines.append("=" * 50)
    lines.append("說明：本摘要由 AI 糖尿病衛教助理依病患自述整理，僅供看診輔助溝通；所有藥物調整與臨床決策均由主治醫師親自診察確認。")
    return "\n".join(lines)

# 保持向後相容別名
generate_visit_summary = generate_previsit_intake_summary


# 工具 Schema 定義
TOOL_SEARCH_HANDBOOK = {
    "type": "function",
    "function": {
        "name": "search_handbook",
        "description": "查詢衛生福利部國民健康署《糖尿病與我》手冊與 TFDA 官方藥品安全指引。僅在病患詢問特定西藥名稱（如庫魯化、SGLT2）、藥物副作用/不良反應、血糖診斷數值標準、或糖尿病定義/成因/形成機制時調用。長輩分享日常飲食、家常菜、吃喝點心時，請直接以專業護理師常識親切同理與關心份量，嚴禁調用此工具！",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "提煉出的專業臨床關鍵字，例如：SGLT2抑制劑、空腹血糖標準、二甲雙胍"}
            },
            "required": ["keyword"]
        }
    }
}

TOOL_GENERATE_PREVISIT_SUMMARY = {
    "type": "function",
    "function": {
        "name": "generate_previsit_intake_summary",
        "description": "產出新陳代謝科門診預問診摘要（就醫備忘錄）台灣 7 欄醫師交班就醫備忘錄。當已經了解病患就醫訴求、用藥狀況與有無低血糖/不適，準備正式整理門診重點時使用。切勿在剛提到看診、尚未了解用藥與症狀前過早呼叫。",
        "parameters": {
            "type": "object",
            "properties": {
                "visit_reason": {"type": "string", "description": "本次門診的核心訴求，例如：定期回診拿慢箋、想諮詢是否調整劑量、為了解決特定不適"},
                "medications": {"type": "string", "description": "目前固定服用的降血糖藥物或胰島素，以及服藥規律性（若記不得請寫「病患自述記不得藥名，建議攜帶藥袋至現場核對」）"},
                "glucose_metrics": {"type": "string", "description": "近期居家空腹/餐後血糖範圍，或最近一季 HbA1c 數據"},
                "hypo_history": {"type": "string", "description": "近一個月有無低血糖事件（冒冷汗、心悸、手抖、頭暈等），若無請寫「近期無低血糖事件」"},
                "side_effects_or_concerns": {"type": "string", "description": "服藥後有無不適（如脹氣腹瀉），或足部麻木/視力變化等併發症警訊"},
                "ddx_candidates": {"type": "array", "items": {"type": "string"}, "description": "待確認方向 2-3 條人話，每條含待做檢查，僅用待確認語氣禁止確診字眼"},
                "evidence_links": {"type": "array", "items": {"type": "string"}, "description": "RAG 真查到才提供的出處（國健署/TFDA 人話），無則留空不可捏造頁碼"},
                "patient_quote": {"type": "string", "description": "阿嬤原話不潤飾，保留病患原句"},
                "glucose_range": {"type": "string", "description": "糖線三數字：最高/最低/平常與不適故事，例如：最高180 最低65 平常110 週三晨空腹65暈10分鐘3顆糖緩解"}
            },
            "required": ["visit_reason", "medications", "glucose_metrics", "hypo_history", "side_effects_or_concerns"]
        }
    }
}
TOOL_GENERATE_VISIT_SUMMARY = TOOL_GENERATE_PREVISIT_SUMMARY

def generate_line_flex_bubble(
    visit_reason: str,
    medications: str,
    glucose_metrics: str,
    hypo_history: str,
    side_effects_or_concerns: str,
    patient_id: str = "病友",
    ddx_candidates=None,
    evidence_links=None,
    patient_quote=None,
    glucose_range=None,
) -> dict:
    meds_display = _to_clean_str(medications)
    if "藥袋" not in meds_display:
        meds_with_bag = f"{meds_display}（藥袋已帶待核對）"
    else:
        meds_with_bag = meds_display
    glucose_section = _format_glucose_section(glucose_metrics, hypo_history, glucose_range, side_effects_or_concerns)
    ddx_list = _normalize_ddx_list(ddx_candidates, side_effects_or_concerns, hypo_history)
    evidence_lines = _format_evidence_lines(evidence_links)
    quote_text = _format_patient_quote(patient_quote)
    ddx_join = "\n".join([f"• {d}" for d in ddx_list])
    body_contents = [
        {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "① 主訴一句話", "weight": "bold", "color": "#0D47A1", "size": "md"},
                {"type": "text", "text": visit_reason, "wrap": True, "size": "sm", "color": "#333333"}
            ]
        },
        {"type": "separator"},
        {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "② 用藥現況", "weight": "bold", "color": "#0D47A1", "size": "md"},
                {"type": "text", "text": meds_with_bag, "wrap": True, "size": "sm", "color": "#333333"}
            ]
        },
        {"type": "separator"},
        {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "③ 糖線三數字", "weight": "bold", "color": "#0D47A1", "size": "md"},
                {"type": "text", "text": glucose_section, "wrap": True, "size": "sm", "color": "#333333"}
            ]
        },
        {"type": "separator"},
        {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#FFF9C4",
            "cornerRadius": "8px",
            "paddingAll": "10px",
            "contents": [
                {"type": "text", "text": "④ 待確認方向", "weight": "bold", "color": "#F57F17", "size": "md"},
                {"type": "text", "text": ddx_join, "wrap": True, "size": "sm", "color": "#333333", "margin": "sm"}
            ]
        },
        {"type": "separator"},
        {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "⑤ 阿嬤原話", "weight": "bold", "color": "#0D47A1", "size": "md"},
                {"type": "text", "text": f"「{quote_text}」", "wrap": True, "size": "sm", "color": "#333333", "style": "italic"}
            ]
        },
    ]
    if evidence_lines:
        body_contents.append({"type": "separator"})
        ev_join = "\n".join([f"• {e}" for e in evidence_lines])
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "⑥ 出處小字", "weight": "bold", "color": "#616161", "size": "xs"},
                {"type": "text", "text": ev_join, "wrap": True, "size": "xxs", "color": "#616161", "margin": "sm"}
            ]
        })
    body_contents.append({"type": "separator"})
    body_contents.append({
        "type": "box",
        "layout": "vertical",
        "contents": [
            {"type": "text", "text": "⑦ 醫師空白欄", "weight": "bold", "color": "#0D47A1", "size": "md"},
            {"type": "text", "text": "□抽 HbA1c  □聊調藥  □轉衛教", "wrap": True, "size": "sm", "color": "#333333"}
        ]
    })
    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0D47A1",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "新陳代謝科 門診預問診就醫備忘錄",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "xl"
                },
                {
                    "type": "text",
                    "text": "自述整理僅供參考非診斷｜衛生福利部 AI 衛教助理",
                    "color": "#BBDEFB",
                    "size": "xs",
                    "margin": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "20px",
            "contents": body_contents
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": "請於看診時直接出示本卡片或 QR Code 給醫護人員",
                    "align": "center",
                    "size": "xs",
                    "color": "#666666"
                },
                {
                    "type": "text",
                    "text": "僅供看診溝通輔助，用藥處方由主治醫師親自診察確認",
                    "align": "center",
                    "size": "xxs",
                    "color": "#999999"
                }
            ]
        }
    }


def generate_clinic_qr_payload(
    visit_reason: str,
    medications: str,
    glucose_metrics: str,
    hypo_history: str,
    side_effects_or_concerns: str,
    ddx_candidates=None,
    evidence_links=None,
    patient_quote=None,
    glucose_range=None,
) -> str:
    glucose_section = _format_glucose_section(glucose_metrics, hypo_history, glucose_range, side_effects_or_concerns)
    ddx_list = _normalize_ddx_list(ddx_candidates, side_effects_or_concerns, hypo_history)
    evidence_lines = _format_evidence_lines(evidence_links)
    quote_text = _format_patient_quote(patient_quote)
    ddx_str = " | ".join(ddx_list)
    ev_str = " | ".join(evidence_lines) if evidence_lines else "無"
    meds_str = _to_clean_str(medications)
    vr_str = _to_clean_str(visit_reason)
    gm_str = _to_clean_str(glucose_metrics)
    hypo_str = _to_clean_str(hypo_history, default="近期未提及")
    se_str = _to_clean_str(side_effects_or_concerns, default="無")
    qr = (
        f"TFDA-INTAKE-V2|主訴一句話:{vr_str}|用藥現況:{meds_str}（藥袋已帶待核對）|"
        f"糖線三數字:{glucose_section}|待確認方向:{ddx_str}|阿嬤原話:{quote_text}|"
        f"出處小字:{ev_str}|醫師空白欄:□抽 HbA1c □聊調藥 □轉衛教"
        f"|血糖:{gm_str}|低血糖:{hypo_str}|主訴:{se_str}"
    )
    return qr
