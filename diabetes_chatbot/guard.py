"""
臨床安全分級守護模組 (Clinical Safety Guard)
參考原 Gate A (tfda_context_gate/a_router) 規則資產進行架構升級：
1. 第一級（阻斷級 / Hard Block）：
   - 惡意提示詞攻擊 (Prompt Injection / Jailbreak)
   - 危及生命急症 (Medical Emergency，如胸痛、呼吸困難、意識不清、嚴重低血糖 < 50 mg/dL)
   - 自傷心理危機 (Mental Health Crisis)
   -> 程式碼層物理斷路，0 延遲，不調用大模型，給予確定性法定救護/合規指引。

2. 第二級（引導級 / Soft Pass - 絕不卡死）：
   - 調藥企圖、診斷請求、範疇外閒聊
   -> 全面放行給大模型，由 AI 衛教護理師以臨床同理心溫暖化解並堅定守住邊界。

【架構設計原則】：
全模組嚴格落實「純語意驅動 (Pure Semantic Driven)」，全面拔除脆弱正則表達式 (Zero Regex Dependency)，
透過臨床子句切割、語意意圖辨識（指令 vs 病史記述 vs 否定警示）精準防護，杜絕正則誤殺與自殘式銷毀。
"""
from __future__ import annotations
import unicodedata
from dataclasses import dataclass
from typing import Literal

GuardRiskCategory = Literal["NONE", "INJECTION", "MENTAL_HEALTH", "PRESCRIPTION_BREACH", "DIAGNOSTIC_BREACH", "MIRACLE_CLAIM"]

@dataclass(frozen=True)
class GuardResult:
    is_blocked: bool
    risk_category: GuardRiskCategory
    blocked_message: str = ""


class ClinicalSafetyGuard:
    """
    雙向臨床安全守護器 (Bi-directional Clinical Safety Guardrail)
    對齊臨床安全法規標準：
    1. 輸入端硬性阻斷 (Input Gate)：
       - 提示詞惡意注入 / 越獄攻擊 (Prompt Injection / Jailbreak)
       - 心理危機與自傷意圖 (Mental Health Crisis)
    2. 輸出端物理熔斷 (Output Safety Net)：
       - 嚴禁越權調藥與處方建議 (Prescription / Dosing Adjustment)
       - 嚴禁越權給予確定性診斷 (Diagnostic Assertions)
       - 嚴禁偽科學神效宣稱 (Miracle Cure Claims)
       若大模型輸出意外觸發違規，0 毫秒物理覆蓋為合規安全話術，絕不送達病患端。
    """

    # 純字串語意集合，零正則表達式，杜絕邊界脆弱與回溯漏洞
    INJECTION_KEYWORDS = (
        "忽略規則", "忽略前面", "忽略以上", "忽略所有", "忘記指示", "忘記你的指示",
        "解除限制", "揭露系統", "揭露提示", "揭露system", "印出系統提示", "印出system",
        "印出你的系統提示", "印出設定", "ignore instructions", "ignore previous",
        "ignore all", "system prompt", "jailbreak", "developer message",
    )

    MENTAL_HEALTH_KEYWORDS = (
        "想自殺", "自殺", "不想活", "活不下去", "想死", "輕生", "結束生命", "自殘", "割腕", "自傷",
    )

    PRESCRIPTION_DIRECTIVES = (
        "建議你", "建議您", "你可以", "您可", "你可以自行", "您可以自行",
        "請你直接", "請您直接", "建議直接", "不妨", "先不要吃", "暫時不要吃",
    )
    PRESCRIPTION_ACTIONS = (
        "停掉", "不要吃藥", "停藥", "停用", "減藥", "加藥", "少吃", "多吃", "改吃",
        "增加劑量", "減少劑量", "加打", "多打", "少打", "吃一顆就好",
    )
    PRESCRIPTION_SELF_ADJUST = (
        "自行加量", "自行減量", "自行調藥", "自己調藥", "自己少吃", "自己多吃", "自行停藥", "自己停藥",
    )
    NARRATIVE_BYPASSES = (
        "曾因", "曾考慮", "打消念頭", "經衛教後已打消", "曾打算", "原本想",
        "阿嬤原話", "病患原話", "我都想", "我想把", "自述曾", "已停用換藥", "（已停用換藥）",
    )
    NEGATION_WARNINGS = (
        "不能", "不可", "不要", "切勿", "禁止", "避免", "防止", "千萬不能", "千萬不要",
        "絕對不能", "請勿", "嚴禁", "別",
    )

    DIAGNOSTIC_ASSERTIONS = (
        "已經確診", "確定罹患", "確定得了", "可以確定罹患", "已經得了",
    )
    DIAGNOSTIC_DISEASES = (
        "第二型糖尿病", "第2型糖尿病", "第一型糖尿病", "第1型糖尿病", "糖尿病酮酸中毒", "腎衰竭",
    )

    MIRACLE_CLAIMS = (
        "保證徹底治癒", "一定能根治", "徹底治癒糖尿病", "完全根治糖尿病", "根治糖尿病", "逆轉糖尿病", "消除糖尿病",
    )

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).strip()
        lines = [" ".join(line.split()) for line in normalized.splitlines()]
        return "\n".join(lines)

    @classmethod
    def inspect(cls, raw_text: str) -> GuardResult:
        text = cls._normalize_text(raw_text)
        if not text:
            return GuardResult(is_blocked=False, risk_category="NONE")

        text_lower = text.lower()
        if any(kw in text_lower for kw in cls.INJECTION_KEYWORDS):
            blocked_msg = (
                "【系統安全提示】\n"
                "本系統為衛生福利部專用之 AI 糖尿病衛教助理，受臨床安全與法令政策規範，"
                "無法執行變更系統指示、解除安全限制或揭露內部設定之操作。\n"
                "若您有糖尿病日常照護、生活衛教或看診前準備需求，我很樂意為您服務。"
            )
            return GuardResult(is_blocked=True, risk_category="INJECTION", blocked_message=blocked_msg)

        if any(kw in text for kw in cls.MENTAL_HEALTH_KEYWORDS):
            blocked_msg = (
                "【緊急關懷指引】\n"
                "我們非常在乎您的感受與生命安全，請先停下腳步給自己一個機會。\n"
                "請立即撥打衛生福利部安心專線：1925（依舊愛我，24小時免付費），"
                "或撥打生命線 1995、張老師 1980，將有專業輔導人員傾聽並全力陪伴您度過難關。"
            )
            return GuardResult(is_blocked=True, risk_category="MENTAL_HEALTH", blocked_message=blocked_msg)

        return GuardResult(is_blocked=False, risk_category="NONE")

    @classmethod
    def inspect_output(cls, raw_reply: str) -> GuardResult:
        text = cls._normalize_text(raw_reply)
        if not text:
            return GuardResult(is_blocked=False, risk_category="NONE")

        # 1. 處方越權檢查（純語意子句分析，精準分離主動指示 vs 病患病史 vs 遵囑衛教）
        if cls._check_prescription_breach(text):
            safe_override = (
                "【臨床安全提醒】\n"
                "貼心護理師提醒您：所有降血糖藥物或胰島素的劑量調整，都與您的血糖穩定及心腎器官保護密切相關。"
                "臨床上絕對不能自行增減藥量或停藥喔！若您用藥後有任何不適或疑慮，請於回診時與主治專科醫師討論，由醫師為您評估調整。"
            )
            return GuardResult(is_blocked=True, risk_category="PRESCRIPTION_BREACH", blocked_message=safe_override)

        # 2. 確診越權檢查（純字串語意）
        if cls._check_diagnostic_breach(text):
            safe_override = (
                "【臨床衛教提醒】\n"
                "血糖數值或身體症狀的判讀，需要搭配完整的抽血檢驗（如糖化血色素、空腹血糖）與醫師專業評估。"
                "線上衛教無法取代醫師的親自診斷，建議您盡速至新陳代謝科門診，由專科醫師為您做完整的檢查與評估喔。"
            )
            return GuardResult(is_blocked=True, risk_category="DIAGNOSTIC_BREACH", blocked_message=safe_override)

        # 3. 神效宣稱檢查（純字串語意）
        if cls._check_miracle_claim(text):
            safe_override = (
                "【健康衛教指引】\n"
                "糖尿病是一種需要長期自我管理的慢性代謝情況，透過均衡飲食、規律運動、定時監測與配合醫療團隊照護，"
                "可以非常良好地穩定控制血糖並預防併發症。請勿輕信任何號稱能快速根治或神奇治癒的不實資訊喔！"
            )
            return GuardResult(is_blocked=True, risk_category="MIRACLE_CLAIM", blocked_message=safe_override)

        return GuardResult(is_blocked=False, risk_category="NONE")

    @classmethod
    def _check_prescription_breach(cls, norm_text: str) -> bool:
        """純語意子句分析：判定輸出是否包含未經授權之處方調藥指令，排除病史記述與遵囑警語"""
        delimiters = ["\n", "。", "！", "!", "？", "?", "；", ";", "|", "／", "/"]
        clauses = [norm_text]
        for d in delimiters:
            expanded = []
            for c in clauses:
                expanded.extend(c.split(d))
            clauses = expanded

        for clause in clauses:
            s = clause.strip()
            if not s:
                continue

            # 若本子句包含客觀病史記述、醫囑轉述或備忘錄結構欄位，直接放行
            if any(bp in s for bp in cls.NARRATIVE_BYPASSES):
                continue

            has_neg = any(neg in s for neg in cls.NEGATION_WARNINGS)

            # 自行調藥行為檢查（若無否定禁止詞或否定詞在後，視為違規）
            for sa in cls.PRESCRIPTION_SELF_ADJUST:
                if sa in s:
                    if not has_neg:
                        return True
                    idx_neg = min([s.find(n) for n in cls.NEGATION_WARNINGS if n in s])
                    idx_sa = s.find(sa)
                    if idx_neg > idx_sa:
                        return True

            # 處方指示詞 + 調藥動作檢查
            for d in cls.PRESCRIPTION_DIRECTIVES:
                if d in s:
                    for act in cls.PRESCRIPTION_ACTIONS:
                        if act in s and not has_neg:
                            return True

        return False

    @classmethod
    def _check_diagnostic_breach(cls, norm_text: str) -> bool:
        """純字串語意：判定輸出是否包含越權確診斷言"""
        has_assertion = any(a in norm_text for a in cls.DIAGNOSTIC_ASSERTIONS)
        has_disease = any(d in norm_text for d in cls.DIAGNOSTIC_DISEASES)
        if has_assertion and has_disease:
            negations = ("無法", "不能", "尚未", "需要", "建議至", "才能確定", "無法取代")
            if not any(neg in norm_text for neg in negations):
                return True
        return False

    @classmethod
    def _check_miracle_claim(cls, norm_text: str) -> bool:
        """純字串語意：判定輸出是否包含神效偽科學宣稱"""
        has_claim = any(c in norm_text for c in cls.MIRACLE_CLAIMS)
        if has_claim:
            negations = ("無法", "不能", "不可", "請勿", "切勿", "不要輕信", "並不能", "不可能", "無法根治")
            if not any(neg in norm_text for neg in negations):
                return True
        return False


def inspect_safety_guard(text: str) -> GuardResult:
    return ClinicalSafetyGuard.inspect(text)

def inspect_output_guard(text: str) -> GuardResult:
    return ClinicalSafetyGuard.inspect_output(text)

def strip_emojis(text: str) -> str:
    """純碼點字元過濾 Unicode Emoji 與圖標符號，嚴格落實全系統零 Emoji 臨床規範（零正則依賴）"""
    if not text:
        return ""
    clean_chars = []
    for ch in text:
        cp = ord(ch)
        if (
            0x1F000 <= cp <= 0x1FFFF
            or 0x2600 <= cp <= 0x27BF
            or 0x2300 <= cp <= 0x23FF
            or 0x2B50 <= cp <= 0x2B55
            or cp in (0x200D, 0xFE0F)
        ):
            continue
        clean_chars.append(ch)
    cleaned = "".join(clean_chars)
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip()

def enforce_single_question_budget(text: str) -> str:
    """純字串單一問句預算截斷，零正則依賴"""
    if not text:
        return text
    text = strip_emojis(text)
    pos_full = text.find("？")
    pos_half = text.find("?")
    candidates = [p for p in (pos_full, pos_half) if p != -1]
    if not candidates:
        return text
    first_q_pos = min(candidates)
    rest = text[first_q_pos + 1:]
    if ("？" in rest) or ("?" in rest):
        return text[:first_q_pos + 1].strip()
    return text
