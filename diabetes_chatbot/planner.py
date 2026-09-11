"""
臨床規劃大腦 (Clinical Planner Agent - 資訊缺口動態追蹤器)
依據臨床雙軌規劃架構與 TADE 糖尿病臨床照護指引設計。

支援雙引擎模式：
1. LLM-based Planner Agent：透過大語言模型進行深層臨床語意理解、動態缺口權重評估與就醫備忘錄導引產出。
2. Rule-based Planner：輕量化本機正則備援引擎。
"""
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

from openai import OpenAI
from diabetes_chatbot.memory import load_patient_record

class SlotStatus(str, Enum):
    KNOWN = "KNOWN"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"

class RetrievalDomain(str, Enum):
    DIET_NUTRITION = "DIET_NUTRITION"
    DIET_NUTRITION_KNOWLEDGE = "DIET_NUTRITION_KNOWLEDGE"
    DRUG_SAFETY = "DRUG_SAFETY"
    GENERAL_EDUCATION = "GENERAL_EDUCATION"
    NONE = "NONE"

@dataclass
class ClinicalSlots:
    visit_reason: str = ""
    visit_reason_status: SlotStatus = SlotStatus.MISSING
    medications: str = ""
    medications_status: SlotStatus = SlotStatus.MISSING
    glucose_metrics: str = ""
    glucose_metrics_status: SlotStatus = SlotStatus.MISSING
    hypo_history: str = ""
    hypo_history_status: SlotStatus = SlotStatus.MISSING
    concerns_or_side_effects: str = ""
    concerns_status: SlotStatus = SlotStatus.MISSING
    diet_lifestyle: str = ""
    diet_lifestyle_status: SlotStatus = SlotStatus.MISSING

@dataclass
class PlannerAssessment:
    slots: ClinicalSlots = field(default_factory=ClinicalSlots)
    is_visit_mode: bool = False
    is_explicit_request: bool = False
    is_agenda_confirmed: bool = False
    can_unlock_summary_tool: bool = False
    highest_priority_gap: Optional[str] = None
    retrieval_domain: RetrievalDomain = RetrievalDomain.NONE
    detected_intent: str = "GENERAL_HEALTH"
    talker_guidance: str = ""
    engine: str = "python"
    retrieval_domain: RetrievalDomain = RetrievalDomain.NONE
    ddx_candidates: list[dict] = field(default_factory=list)
    evidence_links: list[dict] = field(default_factory=list)

def _planner_validate_ddx(candidates):
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

def _planner_validate_evidence(links):
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

def _heuristic_ddx_from_slots(slots, all_text):
    cands=[]
    if any(k in all_text for k in ["脹氣","胃痛","腹瀉","拉肚子","噁心"]):
        cands.append({"方向人話":"腸胃脹氣不適待釐清（待確認）","依據":slots.concerns_or_side_effects or "自述脹氣/腹瀉","待確認檢查":"請醫師評估飲食、藥物與腸胃狀況，待確認"})
    if any(k in all_text for k in ["冒冷汗","心悸","手抖","頭暈"]):
        cands.append({"方向人話":"疑似低血糖相關症狀待確認","依據":slots.hypo_history or "自述冒冷汗/手抖","待確認檢查":"回診請醫師核對血糖紀錄與用藥時間，待確認"})
    if "血糖" in all_text and any(s in slots.glucose_metrics for s in ["mg/dL","血糖"]):
        cands.append({"方向人話":"近期血糖波動待確認","依據":slots.glucose_metrics or "自述血糖數值","待確認檢查":"請醫師評估居家血糖紀錄與抽血結果，待確認"})
    if slots.medications and ("藥袋" in slots.medications or "待核對" in slots.medications):
        cands.append({"方向人話":"用藥明細待現場核對（待確認）","依據":slots.medications,"待確認檢查":"請攜帶藥袋至診間核對，待確認"})
    return _planner_validate_ddx(cands)[:3]
    detected_intent: str = "GENERAL_HEALTH"

PLANNER_SYSTEM_PROMPT = """你是一位專精於糖尿病衛教與新陳代謝科就醫準備的「AI 臨床規劃秘書（Clinical Planning Agent）」。
你依據臨床雙軌對話架構與長期慢性病照護指引運作，躲在對話系統幕後，不直接跟病患對話。
你的任務是審查病患與護理師的對話紀錄，進行「意圖與檢索領域定界」與「臨床資訊缺口盤點」，並輸出純 JSON 決策。
嚴禁依賴字面死板匹配，必須依據真實臨床對話語意進行判斷。

【第一維度：核心意圖與檢索領域隔離 (retrieval_domain)】：
請由常識理解判斷對話的醫學本體範疇，防止跨領域檢索污染：
- DIET_NUTRITION: 病患純分享、閒聊日常飲食生活、提及吃過的美食、三餐吃什麼（例如「我中午吃了芭樂好好吃」「今天吃了麵線糊」）。僅同理關懷，無須查手冊。
- DIET_NUTRITION_KNOWLEDGE: 病患詢問糖尿病飲食知識、原則、禁忌、風險、升糖影響或份量（判定意圖詞：會不會、要注意什麼、能不能吃、可以吃嗎、可以吃多少、適合吃什麼、什麼水果、禁忌，例如「芭樂一次吃一整顆會不會讓血糖飆高」「糖尿病平常飲食要注意什麼」）。此時強制檢索官方手冊飲食原則與營養表。
- DRUG_SAFETY: 病患詢問特定西藥（如庫魯化、SGLT2、胰島素）、藥物副作用、異常不適或黑框警訊。
- GENERAL_EDUCATION: 詢問糖尿病基本定義、空腹血糖標準數值等非生活、非用藥之通用衛教。
- NONE: 一般打招呼寒暄、純生活閒聊無醫學資訊需求。

【第二維度：TADE 6 大就醫槽位盤點 (看診備忘)】：
1. visit_reason (本次回診訴求)：本次回診病患親口確認想處理的核心問題（例如看診拿藥、血糖波動、特定不適）。
2. medications (目前用藥與順從性)：具體藥名；若病患自述有吃藥但未說藥名或忘記/會帶藥袋，狀態為 PARTIAL。
3. glucose_metrics (近期血糖數據)：自述數值；若自述沒在量，狀態為 PARTIAL。
4. hypo_history (低血糖病史)：冒冷汗、心悸、手抖、無低血糖等。
5. concerns_or_side_effects (副作用與疑慮主訴)：胃脹、腹脹、肚子脹、腹瀉、想減藥、不想吃藥、水腫、嚴重不適等。
6. diet_lifestyle (生活飲食習慣與疑慮)：自述三餐份量、主食澱粉、特定水果與點心攝取習慣（僅客觀提煉病患親口自述的食物項目與份量）。若未提及為 MISSING。
【重要過濾原則】：日常生活的良性生理感覺（如吃飽想睡、飽足感、肚子餓、口渴）屬於正常生活代謝，絕對不可當作就醫主訴 (concerns)！只有明確病理不適才可列入。
狀態規範：KNOWN (已掌握), PARTIAL (部分掌握/待現場看藥袋), MISSING (未提及)。

【第三維度：模式與門診摘要卡解鎖（2026 Agenda-Setting 議程門禁）】：
- is_visit_mode: 病患是否明確提及看診、回診、去醫院、拿慢箋、或主動要求整理備忘錄？若病患只是聊飲食生活、詢問特定藥物、反映藥物副作用（如胃脹、肚子痛）、或詢問能否自己停藥，只要未主動提及回診或看診，is_visit_mode 絕對必須為 false！
- is_explicit_request: 是否明確要求整理就醫備忘錄？
- is_agenda_confirmed: 本次回診的核心議程（Agenda）是否已被病患「明確確認」？
  * 若病患剛提出「開始看診前整理」或「幫我整理就醫備忘錄」，但先前對話中護理師從未核對過「這次回診主要想看什麼」，則 is_agenda_confirmed 必須為 false！
  * 若護理師已問過「這次回診最想討論的是...？」，且病患已明確回答（例如「我要問頭暈跟冒冷汗」或「只是例行拿慢箋」），則 is_agenda_confirmed 為 true。
- can_unlock_summary_tool: 
  * 必須在 is_agenda_confirmed 為 true 的前提下：
    - 若 is_explicit_request 為 true，且用藥已知 (KNOWN/PARTIAL) 且具備血糖數值或症狀主訴，達到臨床動態容缺充分度，設為 true。
    - 若 is_visit_mode 為 true（病患尚未主動要求產卡），需核心資訊齊全才設為 true。
  * 只要 is_agenda_confirmed 為 false，絕對不可解鎖（必須設為 false）！

【第四維度：給護理師的臨床導引就醫備忘錄 (talker_guidance，三件套一問一答)】：
- 停藥危機引導（僅限病患明確表達不想吃藥、不敢吃、想停藥、不吃了等不依從停藥意圖）：
  指示護理師：「病患表達停藥意圖，屬用藥安全危機。請先同理長輩不適，並嚴正溫和提醒『在醫師評估前藥千萬不能自己停掉否則血糖衝高危險』；承諾將此服藥不適與調藥訴求列為回診第一條，並親切引導若身邊有藥袋可拍照傳過來供確認藥名。本輪最多只問這一個問題！」
- 輕中度低血糖急救引導（病患提及血糖低於 70 mg/dL，如 65，或自述頭暈、冒冷汗、心悸、手抖等疑似低血糖且意識清醒）：
  指示護理師：「長輩出現血糖低於 70 mg/dL 偏低與低血糖不適，屬急救安全第一優先！請先溫暖同理長輩頭暈難受，客觀說明數值確實偏低（通常醫學標準為 70 mg/dL 以下），並務必明確指導『15-15 吃糖急救法則』：請趕快先吃 15 克的含糖食物（例如 3 到 4 顆方糖、半杯果汁或含糖飲料），坐著或躺著休息 15 分鐘後再量一次血糖；最後單一聚焦詢問長輩平時是否有按時吃降血糖藥（若身邊有藥袋也可以隨時拍照傳來供確認）。嚴禁一次問多題！」
- 藥理成因與副作用諮詢（病患詢問為什麼吃藥會肚子脹、藥理作用或副作用成因）：
  指示護理師：「病患正在詢問特定降血糖藥物成因機轉或副作用原理。請依據衛福部仿單與官方指引，條理分明、結構完整地向病患解釋藥理作用與常見初期腸胃適應期反應，保留醫學事實細節以保障知情權；並於說明文末親切加註：若上述醫學說明有太深奧或看不懂的地方，隨時告訴我，我可以用更生活化的比喻向您解釋喔！」
- 當病患提出看診整理需求，但 is_agenda_confirmed 為 false 時（Agenda-Setting 階段）：
  指示護理師：「病患表達了看診整理意向，但本次就醫的核心議程尚未經病患確認。請先親切同理並拋出單一聚焦問題確認本次看診目的（例如詢問：這次回診最想跟醫師討論的是最近的身體狀況，還是例行抽血拿慢箋？）。嚴格遵守：本輪絕對不可調用產卡工具、本輪最多只問這一個問題！」
- 吃的缺口（提及飲食但未說清什麼/多少/何時）：「先同理美食享受，用1句話點出食物代謝特點，並只問一個三件套吃的問題，例如『今天吃了什麼、大約多少量、什麼時候吃的？』嚴禁一次問多題！」
- 糖缺口（未掌握數字/何時/感覺）：「先同理後只問一個糖三件套問題，例如『最近血糖數字大約多少、什麼時候量的、當時有什麼感覺？』嚴禁一次問多題！」
- 藥缺口（未掌握有吃/有斷/哪不舒服）：「先同理後只問一個藥三件套問題，例如『平時藥都有按時吃嗎、有沒有曾中斷或吃了哪裡不舒服？』若病患表示藥袋已帶待核對即視為 PARTIAL 有效資訊，勿強迫回憶藥名，嚴禁一次問多題！」
- 議程已確認且充分度已達：指示「看診議程與核心資訊已充足，請立刻調用 generate_previsit_intake_summary，切勿再發問」。
- 純寒暄或無缺口：字串為空 ""。

【第五維度：醫師交班候選方向 ddx_candidates（台灣 intake 層級，嚴禁診斷）】：
- 僅整理「人話待確認方向」，限最多3項，每項為 {方向人話, 依據, 待確認檢查}。
- 方向人話：口語化、白話、必含「待確認/待釐清/待核對/請醫師評估」語氣，嚴禁診斷斷言（不可出現「確診/診斷為/罹患第X型」），嚴禁 1-10 清單、嚴禁處方劑量語句。
- 依據：引用病患自述或已掌握欄位（如「自述冒冷汗手抖伴血糖65」「自述脹氣腹瀉」）。
- 待確認檢查：建議門診可做的客觀核對項目（如帶血糖紀錄、帶藥袋核對、請醫師評估飲食藥物關聯）。
- 若無足夠線索則為空陣列 []。

【第六維度：實證連結 evidence_links（僅真實 RAG 命中，嚴禁虛構）】：
- 僅當 search_handbook 真實回傳有內容時才產生，否則為 []，絕不可自行編造書名章節。
- 每項為 {書名, 章節, 原文20字}，書名僅限台灣官方來源（國健署/國民健康署/糖尿病與我/TFDA/食品藥物管理署/衛福部），章節為手冊章節名，原文20字為該章節真實摘錄20字左右（10-40字），絕不可引用 NICE/BMJ 等國外指引，絕不可含劑量處方語句。
- JSON schema 驗證：若書名含 NICE/BMJ、或原文含處方劑量、或非台灣來源，整筆剔除。

請一律以嚴格 JSON 格式輸出，不得包含額外說明文字或 markdown 程式碼標記以外的廢話：
{
  "detected_intent": "DIET_LIFESTYLE|MEDICATION_SAFETY|CLINICAL_VISIT|GENERAL_HEALTH",
  "retrieval_domain": "DIET_NUTRITION|DIET_NUTRITION_KNOWLEDGE|DRUG_SAFETY|GENERAL_EDUCATION|NONE",
  "visit_reason": {"content": "...", "status": "KNOWN|PARTIAL|MISSING"},
  "medications": {"content": "...", "status": "KNOWN|PARTIAL|MISSING"},
  "glucose_metrics": {"content": "...", "status": "KNOWN|PARTIAL|MISSING"},
  "hypo_history": {"content": "...", "status": "KNOWN|PARTIAL|MISSING"},
  "concerns_or_side_effects": {"content": "...", "status": "KNOWN|PARTIAL|MISSING"},
  "diet_lifestyle": {"content": "...", "status": "KNOWN|PARTIAL|MISSING"},
  "is_visit_mode": true/false,
  "is_explicit_request": true/false,
  "is_agenda_confirmed": true/false,
  "can_unlock_summary_tool": true/false,
  "highest_priority_gap": "medications"|null,
  "talker_guidance": "...",
  "ddx_candidates": [{"方向人話": "...（待確認）", "依據": "...", "待確認檢查": "..."}],
  "evidence_links": [{"書名": "糖尿病與我", "章節": "...", "原文20字": "..."}]
}
"""

def evaluate_clinical_planner_llm(
    messages: list,
    patient_record: Optional[dict] = None,
    client: Optional[OpenAI] = None,
    model: str = "mimo-v2.5",
    timeout: float = 2.0
) -> PlannerAssessment:
    if client is None:
        return evaluate_clinical_planner(messages, patient_record=patient_record)
    try:
        conversation_summary = []
        for m in messages:
            if isinstance(m, dict):
                r = m.get("role", "")
                c = m.get("content", "") or ""
            else:
                r = getattr(m, "role", "") or ""
                c = getattr(m, "content", "") or ""
            if r in ["user", "assistant"] and c:
                prefix = "病患" if r == "user" else "衛教護理師"
                conversation_summary.append(f"{prefix}: {c}")
        known_record_str = json.dumps(patient_record or {}, ensure_ascii=False)
        prompt_input = (
            f"【病患長期健康檔案】：\n{known_record_str}\n\n"
            f"【最新對話歷史】：\n" + "\n".join(conversation_summary[-8:])
        )
        extra_body = {"reasoning": {"effort": "none"}} if "mimo" in model.lower() else None
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_input}
            ],
            extra_body=extra_body,
            max_tokens=700,
            temperature=0.1,
            timeout=timeout,
        )
        raw_text = resp.choices[0].message.content.strip()
        clean_json = re.sub(r"^```(?:json)?", "", raw_text).strip()
        clean_json = re.sub(r"```$", "", clean_json).strip()
        data = json.loads(clean_json)
        def _parse_slot(key: str) -> tuple[str, SlotStatus]:
            item = data.get(key, {})
            c = item.get("content", "") or ""
            st = item.get("status", "MISSING")
            try:
                status = SlotStatus(st)
            except Exception:
                status = SlotStatus.MISSING
            return c, status
        vr_c, vr_s = _parse_slot("visit_reason")
        med_c, med_s = _parse_slot("medications")
        gm_c, gm_s = _parse_slot("glucose_metrics")
        hh_c, hh_s = _parse_slot("hypo_history")
        c_c, c_s = _parse_slot("concerns_or_side_effects")
        dl_c, dl_s = _parse_slot("diet_lifestyle")
        slots = ClinicalSlots(
            visit_reason=vr_c, visit_reason_status=vr_s,
            medications=med_c, medications_status=med_s,
            glucose_metrics=gm_c, glucose_metrics_status=gm_s,
            hypo_history=hh_c, hypo_history_status=hh_s,
            concerns_or_side_effects=c_c, concerns_status=c_s,
            diet_lifestyle=dl_c, diet_lifestyle_status=dl_s
        )
        domain_raw = data.get("retrieval_domain", "NONE")
        try:
            retrieval_domain = RetrievalDomain(domain_raw)
        except Exception:
            retrieval_domain = RetrievalDomain.NONE
        detected_intent = str(data.get("detected_intent", "GENERAL_HEALTH") or "GENERAL_HEALTH")
        raw_ddx = data.get("ddx_candidates", [])
        raw_ev = data.get("evidence_links", [])
        ddx_valid = _planner_validate_ddx(raw_ddx)
        ev_valid = _planner_validate_evidence(raw_ev)
        return PlannerAssessment(
            slots=slots,
            is_visit_mode=bool(data.get("is_visit_mode", False)),
            is_explicit_request=bool(data.get("is_explicit_request", False)),
            is_agenda_confirmed=bool(data.get("is_agenda_confirmed", False)),
            can_unlock_summary_tool=bool(data.get("can_unlock_summary_tool", False)),
            highest_priority_gap=data.get("highest_priority_gap"),
            talker_guidance=data.get("talker_guidance", "") or "",
            engine="llm",
            retrieval_domain=retrieval_domain,
            detected_intent=detected_intent,
            ddx_candidates=ddx_valid,
            evidence_links=ev_valid
        )
    except Exception as e:
        fallback_res = evaluate_clinical_planner(messages, patient_record=patient_record)
        fallback_res.engine = f"python_fallback({str(e)[:30]})"
        return fallback_res

VISIT_INTENT_PATTERNS = [
    r"看(?:醫生|診|門診)", r"回診", r"就醫", r"掛號", r"醫院", r"診所",
    r"拿藥", r"慢箋", r"慢性病連續處方", r"看病", r"回診準備", r"就醫準備"
]

EXPLICIT_CARD_PATTERNS = [
    r"幫我整理", r"產成就醫卡", r"做就醫備忘錄", r"整理就醫備忘錄", r"就醫卡",
    r"整理成卡片", r"列給我", r"預問診", r"預問診摘要", r"就醫備忘錄",
    r"門診摘要", r"看診備忘錄", r"幫我總結", r"整理一份"
]

MED_UNKNOWN_PATTERNS = [
    r"記不得", r"不知道藥名", r"忘記藥名", r"沒記", r"不清楚",
    r"帶藥袋", r"拍照", r"看藥袋", r"拿藥袋"
]

GLUCOSE_UNKNOWN_PATTERNS = [
    r"沒量", r"沒在量", r"不知道血糖", r"很少量", r"沒測", r"忘記量", r"沒有血糖機"
]

HYPO_PATTERNS = [
    r"冒冷汗", r"心悸", r"手抖", r"發抖", r"低血糖", r"頭昏眼花", r"喝糖水", r"吃方糖"
]

HYPO_NONE_PATTERNS = [
    r"沒有低血糖", r"沒發生過", r"不會冒冷汗", r"從來沒有", r"都沒有", r"無低血糖"
]

# --- v2 修正：非依從停藥警示與脆弱槽位強化 ---
_NONCOMPLIANCE_RE = re.compile(r"不想吃|不敢吃|沒在吃|想停|不吃了")
_UNNAMED_MED_RE = re.compile(r"有吃|吃一個藥|吃藥")
_DRUG_ENTITY_RE = re.compile(r"庫魯化|美迪康|胰島素|佳糖維|得爾糖|二甲雙胍|metformin", re.IGNORECASE)
_GI_RE = re.compile(r"肚子.*脹|胃.*脹|脹氣|腹瀉|拉肚子|噁心|想吐|胃痛")
_MED_ADJUST_RE = re.compile(r"減藥|停藥|少吃一點|調藥|不想吃|不敢吃|沒吃|不吃了|想停|少吃點")
_NONCOMPLIANCE_WARNING = "在醫師評估前藥千萬不能自己停掉否則血糖衝高危險"

def _is_noncompliance(text: str) -> bool:
    return bool(_NONCOMPLIANCE_RE.search(text))

def _sanitize_search_keyword(keyword: str, user_text: str) -> str:
    """若 user_text 無具體藥名實體，關鍵字嚴禁臆測藥名，僅保留症狀詞彙。"""
    if _DRUG_ENTITY_RE.search(user_text or ""):
        return keyword
    # 無藥名實體時，移除所有臆測藥名
    cleaned = keyword
    for drug in ["二甲雙胍", "metformin", "庫魯化", "美迪康", "胰島素", "佳糖維", "得爾糖", "SGLT2", "Glucophage"]:
        cleaned = re.sub(re.escape(drug), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ，,、；; ")
    if not cleaned:
        # 回退為症狀詞彙，絕不回退為藥名
        cleaned = "腸胃不適 腹脹"
        # 若原文含症狀則優先使用症狀詞
        symptom_fallback = []
        for sym in ["脹氣", "腹瀉", "噁心", "想吐", "胃痛", "肚子脹", "胃脹"]:
            if sym in (user_text or "") or re.search(r"肚子.*脹|胃.*脹", user_text or ""):
                symptom_fallback.append(sym)
        if symptom_fallback:
            cleaned = " ".join(symptom_fallback[:3])
        elif any(k in (user_text or "") for k in ["肚子", "胃", "脹", "腹瀉", "拉肚子", "噁心", "想吐"]):
            cleaned = "腸胃不適"
    return cleaned.strip()

def _extract_text_history(messages: list) -> tuple[list[str], list[str]]:
    user_texts = []
    assistant_texts = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "")
            content = m.get("content", "") or ""
        else:
            role = getattr(m, "role", "") or ""
            content = getattr(m, "content", "") or ""
        if role == "user" and content:
            user_texts.append(content)
        elif role == "assistant" and content:
            assistant_texts.append(content)
    return user_texts, assistant_texts

def evaluate_clinical_planner(
    messages: list,
    patient_file_path: Optional[str] = None,
    patient_record: Optional[dict] = None
) -> PlannerAssessment:
    user_texts, assistant_texts = _extract_text_history(messages)
    all_user_text = " ".join(user_texts)
    last_user_text = user_texts[-1] if user_texts else ""
    if patient_record is not None:
        record = patient_record
    else:
        try:
            if patient_file_path:
                record = load_patient_record(patient_file_path)
            else:
                record = load_patient_record()
        except Exception:
            record = {}
    slots = ClinicalSlots()
    is_explicit_request = any(re.search(p, last_user_text) for p in EXPLICIT_CARD_PATTERNS)
    is_visit_mode = is_explicit_request or any(re.search(p, all_user_text) for p in VISIT_INTENT_PATTERNS)
    if is_visit_mode:
        slots.visit_reason_status = SlotStatus.KNOWN
        if "拿藥" in all_user_text or "慢箋" in all_user_text:
            slots.visit_reason = "定期回診拿慢箋與常規追蹤"
        elif "不舒服" in all_user_text or "頭暈" in all_user_text:
            slots.visit_reason = "身體不適與血糖波動諮詢"
        else:
            slots.visit_reason = "例行新陳代謝科門診追蹤"
    else:
        slots.visit_reason_status = SlotStatus.MISSING
    meds_in_record = [m.get("name", "") for m in record.get("medications", []) if m.get("name")]
    if any(k in all_user_text for k in ["庫魯化", "美迪康", "胰島素", "佳糖維", "得爾糖"]):
        matched = []
        for drug in ["庫魯化", "美迪康", "胰島素", "佳糖維", "得爾糖"]:
            if drug in all_user_text:
                matched.append(drug)
        slots.medications = "、".join(matched)
        slots.medications_status = SlotStatus.KNOWN
    elif any(re.search(p, all_user_text) for p in MED_UNKNOWN_PATTERNS):
        slots.medications = "病患記不得藥名，但表示會攜帶藥袋至診間由醫師核對"
        slots.medications_status = SlotStatus.PARTIAL
    elif _UNNAMED_MED_RE.search(all_user_text) and not _DRUG_ENTITY_RE.search(all_user_text):
        slots.medications = "病患自述有服藥但未提供藥名，建議攜帶藥袋至診間核對（可拍藥袋照片帶來）"
        slots.medications_status = SlotStatus.PARTIAL
    elif meds_in_record:
        slots.medications = "、".join(meds_in_record)
        slots.medications_status = SlotStatus.KNOWN
    else:
        slots.medications_status = SlotStatus.MISSING
    recorded_glucose = record.get("glucose_metrics", {}).get("latest", "")
    if any(k in recorded_glucose for k in ["血壓", "收縮壓", "舒張壓", "收縮", "舒張"]):
        recorded_glucose = ""
    glucose_match = re.search(
        r"(?:血糖|空腹|飯後|測|量)(?:數值|值)?(?:大約|大概|約|是|落在|：|:|\s)*(\d{2,3})(?:\s*(?:左右|上下|度|mg\/dL|mg\/dl))?",
        all_user_text
    )
    if glucose_match:
        val = glucose_match.group(1)
        slots.glucose_metrics = f"病患自述血糖約 {val} mg/dL"
        slots.glucose_metrics_status = SlotStatus.KNOWN
    elif recorded_glucose:
        slots.glucose_metrics = f"檔案近期紀錄 {recorded_glucose}"
        slots.glucose_metrics_status = SlotStatus.KNOWN
    elif any(re.search(p, all_user_text) for p in GLUCOSE_UNKNOWN_PATTERNS):
        slots.glucose_metrics = "近期未規律自測血糖，需門診現場抽血檢驗"
        slots.glucose_metrics_status = SlotStatus.PARTIAL
    else:
        slots.glucose_metrics_status = SlotStatus.MISSING
    if any(re.search(p, all_user_text) for p in HYPO_NONE_PATTERNS):
        slots.hypo_history = "近期無低血糖或冷汗心悸發作"
        slots.hypo_history_status = SlotStatus.KNOWN
    elif any(re.search(p, all_user_text) for p in HYPO_PATTERNS):
        slots.hypo_history = "近期曾有疑似低血糖症狀（如手抖、冒冷汗、心悸）"
        slots.hypo_history_status = SlotStatus.KNOWN
    else:
        slots.hypo_history_status = SlotStatus.MISSING
    concerns = []
    if _GI_RE.search(all_user_text):
        concerns.append("腸胃道不適（如胃脹氣或腹瀉）")
    if _MED_ADJUST_RE.search(all_user_text):
        concerns.append("詢問是否可經由醫師評估減藥")
    if any(k in all_user_text for k in ["傷腎", "洗腎", "依賴", "傷身"]):
        concerns.append("對降血糖藥物長期服用安全之疑慮")
    if any(k in all_user_text for k in ["頭暈", "沒力氣", "手麻", "腳麻", "發麻"]):
        concerns.append("末梢或神經不適主訴")
    if concerns:
        slots.concerns_or_side_effects = "、".join(concerns)
        slots.concerns_status = SlotStatus.KNOWN
    else:
        slots.concerns_status = SlotStatus.MISSING

    # 飲食生活槽位提煉（Rule 備援）
    diet_items = []
    fruit_matches = [f for f in ["芭樂", "西瓜", "香蕉", "芒果", "葡萄", "鳳梨", "橘子", "柳丁", "荔枝", "龍眼", "水梨", "蘋果"] if f in all_user_text]
    if fruit_matches:
        fruit_name = "、".join(fruit_matches)
        if "一次" in all_user_text or "一整顆" in all_user_text or "一大" in all_user_text or "一大片" in all_user_text:
            diet_items.append(f"自述攝取較多份量{fruit_name}習慣（單次醣量偏高）")
        else:
            diet_items.append(f"日常有食用{fruit_name}等水果習慣")
    elif "水果" in all_user_text:
        diet_items.append("日常有食用較多份量水果習慣")
    if any(k in all_user_text for k in ["菜包", "肉包", "包子", "糙米漿", "米漿"]):
        diet_items.append("早餐食用包子搭配糙米漿（高澱粉醣類組合）")
    if diet_items:
        slots.diet_lifestyle = "；".join(diet_items)
        slots.diet_lifestyle_status = SlotStatus.KNOWN
    elif record.get("diet_lifestyle"):
        slots.diet_lifestyle = record.get("diet_lifestyle")
        slots.diet_lifestyle_status = SlotStatus.KNOWN
    else:
        slots.diet_lifestyle_status = SlotStatus.MISSING
    is_agenda_confirmed = False
    if is_visit_mode:
        has_explicit_agenda_in_text = any(k in all_user_text for k in [
            "拿藥", "慢箋", "開藥", "回診追蹤", "定期追蹤", "看頭暈", "討論血糖", "問醫生"
        ])
        is_bare_card_request = last_user_text.strip() in [
            "開始看診前整理", "幫我整理門診就醫備忘錄", "幫我整理就醫備忘錄", "整理就醫備忘錄", "看診就醫備忘錄"
        ] and not has_explicit_agenda_in_text
        if not is_bare_card_request and has_explicit_agenda_in_text:
            is_agenda_confirmed = True
        elif is_bare_card_request:
            is_agenda_confirmed = False
        else:
            is_agenda_confirmed = True
    can_unlock = False
    has_med_info = slots.medications_status in [SlotStatus.KNOWN, SlotStatus.PARTIAL]
    has_data_info = slots.glucose_metrics_status in [SlotStatus.KNOWN, SlotStatus.PARTIAL]
    has_hypo_info = slots.hypo_history_status in [SlotStatus.KNOWN, SlotStatus.PARTIAL]
    has_concern_info = slots.concerns_status == SlotStatus.KNOWN
    is_clinically_sufficient = is_agenda_confirmed and has_med_info and (has_data_info or has_hypo_info or has_concern_info)
    if (is_explicit_request or is_visit_mode) and is_clinically_sufficient:
        can_unlock = True
    highest_priority_gap = None
    talker_guidance = ""
    if is_visit_mode and not is_agenda_confirmed:
        highest_priority_gap = "visit_reason"
        talker_guidance = (
            "【臨床導引就醫備忘錄】：病患提出看診整理需求，但本次回診的核心議程尚未經病患親自確認。"
            "請先親切同理並拋出單一聚焦問題確認本次看診目的（例如詢問：這次回診最想跟醫師討論的是最近的身體狀況，還是例行抽血拿慢箋？）。"
            "嚴格遵守：本輪絕對不可調用產卡工具、本輪最多只問這一個問題！"
        )
    elif is_visit_mode and not can_unlock:
        if slots.medications_status == SlotStatus.MISSING:
            highest_priority_gap = "medications"
            talker_guidance = (
                "【臨床導引就醫備忘錄】：病患有看診意向，目前最缺乏『平常用藥狀況（有吃+有斷+哪不舒服）』。"
                "請同理後只問一個三件套藥的問題，例如『平時藥都有按時吃嗎、有沒有曾中斷或吃了哪裡不舒服？』若病患表示藥袋已帶待核對即視為 PARTIAL 有效，勿強迫回憶藥名，嚴格遵守：本輪最多只問這一個問題，嚴禁條列問卷！"
            )
        elif slots.glucose_metrics_status == SlotStatus.MISSING:
            highest_priority_gap = "glucose_metrics"
            talker_guidance = (
                "【臨床導引就醫備忘錄】：已知病患用藥，目前缺乏『近期血糖數值（三件套：數字+何時+感覺）』。"
                "請同理後只問一個三件套糖的問題，例如『最近血糖數字大約多少、什麼時候量的、當時有什麼感覺？』嚴格遵守：本輪最多只問這一個問題，嚴禁條列問卷！"
            )
        elif slots.hypo_history_status == SlotStatus.MISSING:
            highest_priority_gap = "hypo_history"
            talker_guidance = (
                "【臨床導引就醫備忘錄】：目前缺乏『低血糖發生紀錄』。"
                "請在同理回覆後，溫和確認近期有沒有出現冒冷汗、心悸、手抖等低血糖情形。"
                "嚴格遵守：本輪最多只問這一個問題，嚴禁條列問卷！"
            )
    elif is_visit_mode and can_unlock:
        if is_explicit_request:
            talker_guidance = (
                "【臨床導引就醫備忘錄】：病患看診議程已確認，核心資訊已達充分度！"
                "請立刻調用 generate_previsit_intake_summary 工具為病患生成門診摘要，"
                "嚴禁再拋出任何問題追問病患；生成完成後，親切告知已整理完畢並叮嚀看診時出示即可。"
            )
        else:
            talker_guidance = (
                "【臨床導引就醫備忘錄】：就醫核心資訊已達充分度！"
                "您隨時可以調用 generate_previsit_intake_summary 工具為病患生成門診預問診備忘錄，"
                "並溫暖引導病患確認內容，說明回診時可出示給醫師參考。"
            )
    is_unnamed_med = bool(_UNNAMED_MED_RE.search(all_user_text) and not _DRUG_ENTITY_RE.search(all_user_text))
    if is_unnamed_med:
        photo_hint = "請拍藥袋照片或帶來藥袋至診間核對"
        if "拍藥袋" not in talker_guidance and "藥袋" not in talker_guidance:
            if talker_guidance:
                talker_guidance = talker_guidance + f" {photo_hint}。"
            else:
                talker_guidance = f"【臨床導引就醫備忘錄】：已記錄有服藥但藥名不明，{photo_hint}。"
                if not highest_priority_gap:
                    highest_priority_gap = "medications"
        elif "拍藥袋" not in talker_guidance:
            talker_guidance = talker_guidance + f" {photo_hint}。"
    if _is_noncompliance(all_user_text):
        if _NONCOMPLIANCE_WARNING not in talker_guidance:
            if talker_guidance:
                talker_guidance = talker_guidance.rstrip("。") + f"。{_NONCOMPLIANCE_WARNING}。"
            else:
                talker_guidance = f"【溫和提醒】：{_NONCOMPLIANCE_WARNING}。"

    # 低血糖急救第一優先判定（血糖 < 70 mg/dL 或低血糖症狀）
    is_hypo_urgent = False
    if glucose_match:
        try:
            val_int = int(glucose_match.group(1))
            if 40 <= val_int < 70:
                is_hypo_urgent = True
        except Exception:
            pass
    if any(k in all_user_text for k in ["血糖65", "血糖 65", "65度", "低血糖"]) and any(k in all_user_text for k in ["頭暈", "手抖", "冒冷汗", "心悸", "不舒服"]):
        is_hypo_urgent = True

    if is_hypo_urgent:
        highest_priority_gap = "hypo_emergency"
        talker_guidance = (
            "【臨床溝通導引】：長輩血糖偏低（低於 70 mg/dL），屬急救安全第一優先！"
            "請先溫暖同理並關心長輩身體不適，說明數值偏低，這時候安全第一，請務必第一時間完整採取『15-15 法則』清楚條列三個步驟："
            "1. 趕快吃 15 克的快速含糖食物（例如含 3 到 4 顆方糖的溫開水、半杯約 125cc 的果汁或含糖飲料）；"
            "2. 休息 15 分鐘：吃完後坐著或躺著休息，不要勉強走動；"
            "3. 15 分鐘後再量一次血糖，確認回升到 70 mg/dL 以上。"
            "結尾叮嚀『照顧好自己最重要！』並單一聚焦詢問平時是否有在吃降血糖藥物或打胰島素。嚴禁省略吃糖步驟！"
        )

    target_query = (last_user_text or all_user_text).strip()
    drug_safety_keywords = [
        "藥", "庫魯化", "美迪康", "胰島素", "佳糖維", "得爾糖", "二甲雙胍", "metformin",
        "sglt2", "排糖藥", "副作用", "傷腎", "交互作用", "仿單", "劑量", "適應症", "降血糖"
    ]
    is_drug_safety = any(k in target_query.lower() for k in drug_safety_keywords)
    diet_keywords = [
        "吃", "喝", "餐", "飲食", "早餐", "午餐", "晚餐", "宵夜", "點心", "便當", "菜單",
        "飯", "麵", "米", "粥", "菜", "肉", "蛋", "豆", "魚", "奶", "水果",
        "麵包", "地瓜", "燕麥", "蘿蔔", "零食", "飲料", "澱粉", "醣", "糖類", "熱量", "卡路里"
    ]
    is_diet_nutrition = any(k in target_query.lower() for k in diet_keywords) and not is_drug_safety
    diet_knowledge_keywords = [
        "會不會", "要注意什麼", "注意什麼", "能不能吃", "可以吃嗎", "可以吃多少", "適合吃什麼", "什麼水果", "禁忌",
        "升血糖", "飆高", "血糖飆", "份量", "能吃嗎", "可以吃", "能不能", "多少量", "怎麼吃", "如何吃"
    ]
    is_diet_knowledge = is_diet_nutrition and any(k in target_query.lower() for k in diet_knowledge_keywords)
    general_edu_keywords = ["保養", "眼睛", "足部", "腳", "運動", "標準值", "糖化血色素", "檢驗", "指標",
        "成因", "形成", "原理", "是什麼", "定義", "怎麼來的", "為什麼", "為何", "病因", "機轉"]
    is_general_edu = any(k in target_query.lower() for k in general_edu_keywords)
    if is_drug_safety:
        retrieval_domain = RetrievalDomain.DRUG_SAFETY
        detected_intent = "DRUG_SAFETY_INQUIRY"
    elif is_diet_knowledge:
        retrieval_domain = RetrievalDomain.DIET_NUTRITION_KNOWLEDGE
        detected_intent = "DIET_NUTRITION_KNOWLEDGE_INQUIRY"
    elif is_diet_nutrition:
        retrieval_domain = RetrievalDomain.DIET_NUTRITION
        detected_intent = "DIET_NUTRITION_INQUIRY"
    elif is_general_edu:
        retrieval_domain = RetrievalDomain.GENERAL_EDUCATION
        detected_intent = "GENERAL_EDUCATION_INQUIRY"
    elif is_visit_mode:
        retrieval_domain = RetrievalDomain.NONE
        detected_intent = "CLINICAL_VISIT"
    else:
        retrieval_domain = RetrievalDomain.NONE
        detected_intent = "GENERAL_HEALTH"
    ddx_candidates = _heuristic_ddx_from_slots(slots, all_user_text)
    evidence_links: list[dict] = []
    return PlannerAssessment(
        slots=slots,
        is_visit_mode=is_visit_mode,
        is_explicit_request=is_explicit_request,
        is_agenda_confirmed=is_agenda_confirmed,
        can_unlock_summary_tool=can_unlock,
        highest_priority_gap=highest_priority_gap,
        talker_guidance=talker_guidance,
        engine="python",
        retrieval_domain=retrieval_domain,
        detected_intent=detected_intent,
        ddx_candidates=ddx_candidates,
        evidence_links=evidence_links
    )
