import json
import os
import re
import secrets
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
    if "DIET_NUTRITION" in domain_str:
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
    diet_lifestyle: str = None,
) -> str:
    """糖線與生活飲食：最近/最低/平常 + 不適故事/低血糖史 + 飲食記錄"""
    diet_clean = _to_clean_str(diet_lifestyle, default="")
    diet_suffix = f"；飲食生活：{diet_clean}" if (diet_clean and diet_clean not in ("未特別說明", "無")) else ""

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
            res = f"{base}；不適故事：{story}" if base else story
        else:
            hypo_clean = _to_clean_str(hypo_history, default="")
            if hypo_clean and hypo_clean not in ("近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "", "無", "無低血糖事件"):
                if "無低血糖" not in hypo_clean and "未提及" not in hypo_clean and hypo_clean != "無":
                    res = f"{base}；低血糖史：{hypo_clean}"
                else:
                    res = base
            else:
                res = base
        return f"{res}{diet_suffix}" if diet_suffix and "飲食生活" not in res else res
    elif glucose_range is not None:
        if not isinstance(glucose_range, dict):
            s = str(glucose_range).strip()
            if s:
                return f"{s}{diet_suffix}" if diet_suffix and "飲食生活" not in s else s
    gm = _to_clean_str(glucose_metrics)
    hypo = _to_clean_str(hypo_history, default="")
    if hypo and hypo not in ("近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "", "無", "無低血糖事件"):
        if "無低血糖" not in hypo and "未提及" not in hypo and hypo != "無":
            base_str = f"{gm}；低血糖史：{hypo}"
            return f"{base_str}{diet_suffix}" if diet_suffix and "飲食生活" not in base_str else base_str
    return f"{gm}{diet_suffix}" if diet_suffix and "飲食生活" not in gm else gm


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
                if not any(label.startswith(p) for p in ("待確認", "待釐清", "待評估", "待追蹤", "待討論")):
                    label = f"待確認{label}"
                if "待做檢查" not in label and not check:
                    check = "回診抽 HbA1c，核對血糖紀錄簿與藥物劑量"
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
                if not any(s.startswith(p) for p in ("待確認", "待釐清", "待評估", "待追蹤", "待討論")):
                    s = f"待確認{s}"
                if "待做檢查" not in s:
                    s = f"{s} — 待做檢查：核對血糖紀錄簿與藥物劑量"
                normalized.append(s)
        normalized = [n for n in normalized if n.strip()]
        if len(normalized) == 1:
            normalized.append("待確認整體血糖穩定性 — 待做檢查：回診抽 HbA1c 並帶血糖紀錄簿")
        if len(normalized) >= 2:
            return _diversify_ddx_checks(normalized[:3])
        if len(normalized) == 0:
            pass
        else:
            return _diversify_ddx_checks(normalized[:3])
    fallback = []
    if hypo_history and hypo_history.strip() not in ("近期未提及或無發生", "近期無低血糖事件", "無特別異常", "未特別說明", "", "無", "無低血糖事件", "近期無低血糖或冷汗心悸發作"):
        if "無低血糖" not in hypo_history and "未提及" not in hypo_history and hypo_history.strip() != "無":
            fallback.append(f"待確認低血糖症狀與血糖偏低的關聯 — 待做檢查：回診抽 HbA1c、核對血糖紀錄簿與藥物劑量（自述：{hypo_history}）")
    if side_effects_or_concerns and side_effects_or_concerns.strip() not in ("無特別異常", "無", "", "未特別說明", "無特別異常"):
        if side_effects_or_concerns.strip() not in (hypo_history or ""):
            fallback.append(f"待確認用藥後不適感受的相關性 — 待做檢查：回診與醫師討論不適時間與藥袋紀錄，評估更換腸胃友善劑型（自述：{side_effects_or_concerns}）")
    if len(fallback) < 2:
        fallback.append("待確認飲食與血糖波動的關聯 — 待做檢查：轉介新陳代謝科營養諮詢，評估水果與醣類份量")
    if len(fallback) < 2:
        fallback.append("待確認整體用藥順從性與血糖控制 — 待做檢查：回診攜藥袋核對並評估是否需轉衛教")
    return _diversify_ddx_checks(fallback[:3])


def _diversify_ddx_checks(ddx_items: list) -> list:
    """若多條待確認方向的待做檢查完全相同，依各條主題智慧分化具體檢查項目，嚴禁兩條印同一句"""
    if not ddx_items:
        return []
    parsed = []
    for item in ddx_items:
        s_item = str(item).strip()
        if " — 待做檢查：" in s_item:
            d, c = s_item.split(" — 待做檢查：", 1)
            parsed.append({"dir": d.strip(), "check": c.strip()})
        elif "待做檢查：" in s_item:
            d, c = s_item.split("待做檢查：", 1)
            parsed.append({"dir": d.rstrip(" —-").strip(), "check": c.strip()})
        else:
            parsed.append({"dir": s_item, "check": ""})

    used_checks = set()
    result = []
    for idx, p in enumerate(parsed):
        d_text = p["dir"]
        c_text = p["check"]
        dl = d_text.lower()

        needs_diff = not c_text or (c_text in used_checks) or (c_text == "核對血糖紀錄簿與藥物劑量" and idx > 0)

        if needs_diff:
            if any(k in dl for k in ["低血糖", "血糖偏低", "65", "70", "頭暈", "冷汗", "心悸", "冒汗"]):
                candidate = "抽 HbA1c 與檢視近週血糖紀錄簿"
            elif any(k in dl for k in ["腸胃", "胃", "脹", "腹", "便秘", "腹瀉", "噁心", "吃不下", "胃逆", "消化"]):
                candidate = "攜藥袋現場核對，請醫師評估腸胃友善劑型"
            elif any(k in dl for k in ["調藥", "調整", "劑量", "加藥", "減藥", "停藥"]):
                candidate = "請醫師全面評估降血糖藥物劑量與肝腎功能"
            elif any(k in dl for k in ["飲食", "芭樂", "水果", "澱粉", "包子", "米漿", "糖分", "熱量", "生活"]):
                candidate = "轉介新陳代謝科營養諮詢，評估水果與醣類份量"
            else:
                candidate = "回診攜帶藥袋至診間核對，評估慢性病連續處方箋"

            if candidate in used_checks:
                if "抽" not in " ".join(used_checks):
                    candidate = "回診抽血檢驗 HbA1c 並檢核空腹血糖數值"
                elif "藥袋" not in " ".join(used_checks):
                    candidate = "現場攜帶完整藥袋與處方明細，請醫師逐一比對"
                elif "營養" not in " ".join(used_checks):
                    candidate = "轉介個別化衛教諮詢，檢核飲食與服藥時機"
                else:
                    candidate = f"與主治專科醫師討論臨床處置方針（項目 {idx+1}）"

            c_text = candidate

        used_checks.add(c_text)
        result.append(f"{d_text} — 待做檢查：{c_text}")

    return result


def _clean_evidence_human_source(source_or_url: str) -> str:
    """將 URL 或雜訊轉為官方來源人話名，只印來源名不印網址"""
    s = str(source_or_url).strip()
    if not s:
        return ""
    # 去除括號內的網址，如 衛生福利部國民健康署（https://www.hpa.gov.tw）
    s = re.sub(r"[（\(]https?://[^\s\)]+[）\)]", "", s).strip()
    sl = s.lower()
    if "hpa.gov.tw" in sl or "國民健康署" in s or "國健署" in s:
        return "衛生福利部國民健康署《糖尿病與我》手冊"
    elif "fda.gov.tw" in sl or "tfda" in sl or "仿單" in s:
        return "衛生福利部食品藥物管理署 (TFDA) 官方藥品仿單"
    elif "tade.org.tw" in sl or "糖尿病衛教學會" in s:
        return "社團法人中華民國糖尿病衛教學會 (TADE) 臨床指引"
    elif "mohw.gov.tw" in sl or "衛福部" in s or "衛生福利部" in s:
        return "衛生福利部臨床照護指引"
    elif s.startswith("http://") or s.startswith("https://"):
        return "衛生福利部國民健康署《糖尿病與我》手冊"
    s = re.sub(r"https?://\S+", "", s).strip()
    return s if s else "衛生福利部國民健康署《糖尿病與我》手冊"


def _format_evidence_lines(evidence_links) -> list:
    if not evidence_links:
        return []
    lines = []
    for item in evidence_links:
        if isinstance(item, dict):
            raw_text = (
                item.get("text")
                or item.get("title")
                or item.get("source")
                or item.get("citation")
                or ""
            )
            raw_url = item.get("url") or item.get("link") or ""
            combined = f"{raw_text} {raw_url}".strip()
            human_name = _clean_evidence_human_source(combined if combined else str(item))
            if human_name and human_name not in lines:
                lines.append(human_name)
        else:
            human_name = _clean_evidence_human_source(str(item))
            if human_name and human_name not in lines:
                lines.append(human_name)
    return lines


STOP_MED_WORDS = {"換藥", "藥物", "藥品", "吃藥", "降血糖藥", "西藥", "藥袋", "規則", "目前"}


def _extract_discontinued_keywords(s: str) -> set:
    """從藥物字串中提取所有停用標記關聯之藥名與成分關鍵字"""
    if not s:
        return set()
    disc = set()
    # 模式 1: 藥名（已停用換藥）或（已停用）或（停藥）
    for m in re.finditer(r"([A-Za-z\u4e00-\u9fa5]{2,15}?)(?:\s*\d+[^\(（]*?)?[（\(](?:已停用換藥|已停用|已停服|停藥)[）\)]", s):
        name = re.sub(r"[\d\s]+", "", m.group(1)).strip()
        if len(name) >= 2 and name not in STOP_MED_WORDS:
            disc.add(name)
    # 模式 2: 已停服XX, 已停用XX, 停用XX, 停藥XX, 不要吃XX
    for m in re.finditer(r"(?:已停服|已停用|停服|停用|停藥|換掉|不要吃|不吃|停吃)\s*([A-Za-z\u4e00-\u9fa5]{2,10})", s):
        name = m.group(1).strip()
        if len(name) >= 2 and name not in STOP_MED_WORDS:
            disc.add(name)
    # 模式 3: XX已停用, XX已停服, XX不要吃
    for m in re.finditer(r"([A-Za-z\u4e00-\u9fa5]{2,10})\s*(?:已停服|已停用|停服|停用|停藥|不要吃了|不要吃|不吃了)", s):
        name = m.group(1).strip()
        name = re.sub(r"^(?:自述|目前|已|並|且|要|說|幫我|把)", "", name).strip()
        name = re.sub(r"已$", "", name).strip()
        if len(name) >= 2 and name not in STOP_MED_WORDS:
            disc.add(name)

    alias_groups = [
        {"癲通", "卡巴氮平", "tegretol", "carbamazepine"},
        {"庫魯化", "二甲雙胍", "metformin", "glucophage"},
        {"得爾美", "diamicron", "gliclazide"},
        {"佳糖維", "januvia", "sitagliptin"},
        {"愛妥糖", "actos", "pioglitazone"},
    ]
    expanded = set(disc)
    for k in disc:
        kl = k.lower()
        for grp in alias_groups:
            if any(len(kl) >= 2 and (member.lower() in kl or kl in member.lower()) for member in grp):
                expanded.update(grp)
    return expanded


def _format_medications_for_display(med_text: str) -> str:
    """文字卡與 Flex 卡用藥顯示層停用調和：
    1. 現行用藥清單只呈現未停用藥品；
    2. 停用藥若呈現必須帶（已停用換藥）標註；
    3. 同一張卡的任何位置，停用藥只以停用身份出現一次；
    4. 長串英文學名摺疊為清爽短格式。
    """
    if not med_text or not str(med_text).strip():
        return "未特別說明"
    s = str(med_text).strip()
    if s in ("未特別說明", "無", "無特別異常"):
        return "未特別說明"

    expanded_disc = _extract_discontinued_keywords(s)
    has_bag_note = ("藥袋" in s or "現場" in s or "核對" in s)

    s_norm = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    s_norm = re.sub(r"其他降血糖藥物建議攜帶完整藥袋至現場核對[；;，,\s]*", "", s_norm)
    s_norm = re.sub(r"建議攜帶完整藥袋至現場核對[；;，,\s]*", "", s_norm)
    s_norm = re.sub(r"（藥袋已帶待現場核對）|（藥袋已帶待核對）", "", s_norm)

    raw_tokens = re.split(r"[;；，,\n|、]+", s_norm)
    active_tokens = []
    disc_candidates = []
    seen_active = set()

    for tok in raw_tokens:
        tok = tok.strip()
        if not tok:
            continue
        tok = re.sub(r"^(?:目前持有|藥袋已辨識|目前用藥|服藥規則|自述目前服用|目前服藥)[：:\s]*", "", tok).strip()
        tok = re.sub(r"藥袋$", "", tok).strip()
        if not tok:
            continue

        has_zh = bool(re.search(r"[\u4e00-\u9fa5]", tok))
        tok_lower = tok.lower()
        is_disc = any(dk.lower() in tok_lower for dk in expanded_disc)

        m_dose = re.search(r"(\d+(?:\.\d+)?\s*(?:毫克|mg|公克|g|微克|mcg))", tok, re.IGNORECASE)
        dose_str = m_dose.group(1).replace(" ", "") if m_dose else ""

        zh_name = re.sub(r"[（\(].*?[）\)]", "", tok)
        zh_name = re.sub(r"[A-Za-z*./\-]+", "", zh_name)
        if dose_str:
            zh_name = zh_name.replace(dose_str, "")
        zh_name = re.sub(r"\d+", "", zh_name).strip()
        zh_name = re.sub(r"^(?:已停服|已停用|停用|停服|停藥)", "", zh_name).strip()
        zh_name = re.sub(r"\s+", "", zh_name)

        if is_disc:
            if has_zh and zh_name and len(zh_name) >= 2 and zh_name not in STOP_MED_WORDS:
                short_disc = f"{zh_name} {dose_str}".strip() if dose_str else zh_name
                disc_candidates.append((short_disc, dose_str, tok))
        else:
            if has_zh and zh_name and len(zh_name) >= 2 and zh_name not in STOP_MED_WORDS:
                short_act = f"{zh_name} {dose_str}".strip() if dose_str else zh_name
                core_key = zh_name[:2]
                if core_key not in seen_active:
                    seen_active.add(core_key)
                    active_tokens.append(short_act)
            elif any(k in tok for k in ["服藥規律", "規律服藥", "按時服藥"]):
                if "服藥規律" not in active_tokens:
                    active_tokens.append("服藥規律")

    disc_items = []
    seen_disc_core = set()
    disc_candidates.sort(key=lambda x: (len(x[1]) > 0, len(x[0])), reverse=True)
    for short_name, dose, orig in disc_candidates:
        core = re.sub(r"\d.*", "", short_name)[:2]
        if core and core not in seen_disc_core:
            seen_disc_core.add(core)
            clean_short = short_name.replace("已停用", "").replace("已停服", "").strip()
            disc_items.append(f"{clean_short}（已停用換藥）")

    display_parts = []
    if active_tokens:
        display_parts.append("、".join(active_tokens))
    if disc_items:
        display_parts.append("；".join(disc_items))
    display_res = "；".join(display_parts) if (active_tokens and disc_items) else (display_parts[0] if display_parts else "未特別說明")
    if has_bag_note and "（藥袋" not in display_res:
        display_res = f"{display_res} （藥袋已帶待現場核對）"
    return display_res


def _format_medications_for_data(med_text: str) -> str:
    """QR payload 資料層停用調和：保留完整藥袋全名與學名，但嚴格標註（已停用換藥），全卡只出現一次"""
    if not med_text or not str(med_text).strip():
        return "未特別說明"
    s = str(med_text).strip()
    if s in ("未特別說明", "無", "無特別異常"):
        return "未特別說明"

    expanded_disc = _extract_discontinued_keywords(s)
    data_res = s
    if expanded_disc:
        for dk in expanded_disc:
            data_res = re.sub(rf"(?:[，,、\s]*已停服{dk}[，,、\s]*)", "，", data_res)
            data_res = re.sub(rf"(?:[，,、\s]*已停用{dk}[，,、\s]*)", "，", data_res)
            data_res = re.sub(rf"(?:[，,、\s]*{dk}已停用[，,、\s]*)", "，", data_res)
            data_res = re.sub(rf"(?:[，,、\s]*{dk}不要吃[，,、\s]*)", "，", data_res)
        data_res = re.sub(r"^[，,、\s;；]+|[，,、\s;；]+$", "", data_res)
        data_res = re.sub(r"[，,]{2,}", "，", data_res)

        if "藥袋已辨識" in data_res:
            bag_idx = data_res.index("藥袋已辨識")
            pre_part = data_res[:bag_idx]
            bag_part = data_res[bag_idx:]
            if any(k.lower() in bag_part.lower() for k in expanded_disc) and "（已停用換藥）" not in bag_part:
                bag_part = f"{bag_part.rstrip()}（已停用換藥）"
            data_res = pre_part + bag_part
        elif any(k.lower() in data_res.lower() for k in expanded_disc) and "（已停用換藥）" not in data_res:
            data_res = f"{data_res}（已停用換藥）"

    if "藥袋" not in data_res:
        data_res = f"{data_res}（藥袋已帶待核對）"
    return data_res


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
    diet_lifestyle: str = None,
) -> str:
    meds_with_bag = _format_medications_for_display(medications)
    glucose_section = _format_glucose_section(glucose_metrics, hypo_history, glucose_range, side_effects_or_concerns, diet_lifestyle=diet_lifestyle)
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
    lines.append(f"③ 糖線與生活飲食：{glucose_section}")
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
                "diet_lifestyle": {"type": "string", "description": "病患自述之日常飲食與生活習慣記錄（例如自述攝取特定水果份量、外食或正餐習慣等），若未提及請填「未特別說明」"},
                "ddx_candidates": {"type": "array", "items": {"type": "string"}, "description": "待確認方向 2-3 條人話，每條含待做檢查，僅用待確認語氣禁止確診字眼"},
                "evidence_links": {"type": "array", "items": {"type": "string"}, "description": "RAG 真查到才提供的出處（國健署/TFDA 人話），無則留空不可捏造頁碼"},
                "patient_quote": {"type": "string", "description": "阿嬤原話不潤飾，保留病患原句"},
                "glucose_range": {"type": "string", "description": "最高/最低/平常三數字與不適故事，僅能使用病患對話中實際自述的數值與情節；嚴禁使用本說明中的任何示例數值、星期或時間長度；病患未提及請留空"}
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
    share_code: str = None,
    diet_lifestyle: str = None,
) -> dict:
    meds_with_bag = _format_medications_for_display(medications)
    glucose_section = _format_glucose_section(glucose_metrics, hypo_history, glucose_range, side_effects_or_concerns, diet_lifestyle=diet_lifestyle)
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
                {"type": "text", "text": "③ 糖線與生活飲食", "weight": "bold", "color": "#0D47A1", "size": "md"},
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

    # 格式化 6 位診間調閱短碼
    if not share_code:
        share_code = f"{secrets.randbelow(1_000_000):06d}"
    clean_code = re.sub(r"[\s\-]", "", str(share_code)).strip()
    if len(clean_code) == 6:
        display_code = f"{clean_code[:3]} - {clean_code[3:]}"
    else:
        display_code = str(share_code)

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
            "spacing": "md",
            "paddingAll": "16px",
            "backgroundColor": "#F4F6FA",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#194B8F",
                    "cornerRadius": "10px",
                    "paddingAll": "12px",
                    "contents": [
                        {
                            "type": "text",
                            "text": "【醫師診間調閱碼】",
                            "color": "#BBDEFB",
                            "size": "xs",
                            "align": "center",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": display_code,
                            "color": "#FFFFFF",
                            "size": "xxl",
                            "align": "center",
                            "weight": "bold",
                            "margin": "xs"
                        },
                        {
                            "type": "text",
                            "text": "（有效期限 10 分鐘，出示給醫師輸入即可）",
                            "color": "#E3F2FD",
                            "size": "xxs",
                            "align": "center",
                            "margin": "xs"
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": "請於看診時出示本卡片或提供上方調閱碼給醫護人員",
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
    diet_lifestyle: str = None,
) -> str:
    # 診間 QR Code 維持精簡糖線三數字（不重複內嵌飲食文字，節省容量提高掃描成功率）
    glucose_section = _format_glucose_section(glucose_metrics, hypo_history, glucose_range, side_effects_or_concerns)
    ddx_list = _normalize_ddx_list(ddx_candidates, side_effects_or_concerns, hypo_history)
    evidence_lines = _format_evidence_lines(evidence_links)
    quote_text = _format_patient_quote(patient_quote)
    ddx_str = " | ".join(ddx_list)
    ev_str = " | ".join(evidence_lines) if evidence_lines else "無"
    meds_with_bag = _format_medications_for_data(medications)
    vr_str = _to_clean_str(visit_reason)
    gm_str = _to_clean_str(glucose_metrics)
    hypo_str = _to_clean_str(hypo_history, default="近期未提及")
    se_str = _to_clean_str(side_effects_or_concerns, default="無")
    
    # 飲食生活欄位：僅在有具體自述時附加於末端鍵值，未填或無則不附加
    diet_clean = str(diet_lifestyle or "").strip()
    diet_part = ""
    if diet_clean and diet_clean not in ("未特別說明", "無", "未提供", "待查"):
        diet_part = f"|飲食生活:{diet_clean}"

    qr = (
        f"TFDA-INTAKE-V2|主訴一句話:{vr_str}|用藥現況:{meds_with_bag}|"
        f"糖線三數字:{glucose_section}|待確認方向:{ddx_str}|阿嬤原話:{quote_text}|"
        f"出處小字:{ev_str}|醫師空白欄:□抽 HbA1c □聊調藥 □轉衛教"
        f"|血糖:{gm_str}|低血糖:{hypo_str}|主訴:{se_str}{diet_part}"
    )
    return qr
