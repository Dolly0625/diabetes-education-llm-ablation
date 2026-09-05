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
"""
from __future__ import annotations
import re
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

    _INJECTION_RE = re.compile(
        r"忽略(?:前面|以上|所有)?規則|忘記(?:你的)?指示|解除限制|揭露(?:系統|提示|system prompt)|"
        r"印出(?:你的)?(?:system prompt|系統提示詞|設定)|"
        r"ignore\s+(?:all\s+)?(?:previous|prior|以上)?\s*instructions?|system\s+prompt|"
        r"jailbreak|developer\s+message",
        re.IGNORECASE,
    )

    _MENTAL_HEALTH_RE = re.compile(
        r"想自殺|自殺|不想活|活不下去|想死|輕生|結束生命|自殘|割腕|自傷",
        re.IGNORECASE,
    )

    _PRESCRIPTION_BREACH_RE = re.compile(
        r"(?:停藥|停用|不要吃藥|把.*?藥停掉|減藥|加藥|"
        r"改吃[一二兩半\d]+顆|少吃[一二兩半\d]+顆|多吃[一二兩半\d]+顆|吃[一二兩半\d]+顆就好|每天改吃[一二兩半\d]+顆|"
        r"自行加量|自行減量|自己少吃|自己多吃|自己停藥|自己調藥|增加劑量|減少劑量|加打[一二兩半\d]+單位|多打[一二兩半\d]+單位|少打[一二兩半\d]+單位)",
        re.IGNORECASE,
    )

    _DIAGNOSTIC_BREACH_RE = re.compile(
        r"(?:你已經|您已經|你可以確定|確定)?(?:罹患|確診|得了)(?:了)?(?:第[一二12]型糖尿病|糖尿病酮酸中毒|腎衰竭)",
        re.IGNORECASE,
    )

    _MIRACLE_CLAIM_RE = re.compile(
        r"(?:保證|一定能|完全|徹底|快速)?(?:根治|治癒|逆轉|消除)糖尿病",
        re.IGNORECASE,
    )

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).strip()
        return re.sub(r"\s+", " ", normalized)

    @classmethod
    def inspect(cls, raw_text: str) -> GuardResult:
        text = cls._normalize_text(raw_text)
        if not text:
            return GuardResult(is_blocked=False, risk_category="NONE")
        if cls._INJECTION_RE.search(text):
            blocked_msg = (
                "【系統安全提示】\n"
                "本系統為衛生福利部專用之 AI 糖尿病衛教助理，受臨床安全與法令政策規範，"
                "無法執行變更系統指示、解除安全限制或揭露內部設定之操作。\n"
                "若您有糖尿病日常照護、生活衛教或看診前準備需求，我很樂意為您服務。"
            )
            return GuardResult(is_blocked=True, risk_category="INJECTION", blocked_message=blocked_msg)
        if cls._MENTAL_HEALTH_RE.search(text):
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
        if cls._PRESCRIPTION_BREACH_RE.search(text):
            safe_override = (
                "【臨床安全提醒】\n"
                "貼心護理師提醒您：所有降血糖藥物或胰島素的劑量調整，都與您的血糖穩定及心腎器官保護密切相關。"
                "臨床上絕對不能自行增減藥量或停藥喔！若您用藥後有任何不適或疑慮，請於回診時與主治專科醫師討論，由醫師為您評估調整。"
            )
            return GuardResult(is_blocked=True, risk_category="PRESCRIPTION_BREACH", blocked_message=safe_override)
        if cls._DIAGNOSTIC_BREACH_RE.search(text):
            safe_override = (
                "【臨床衛教提醒】\n"
                "血糖數值或身體症狀的判讀，需要搭配完整的抽血檢驗（如糖化血色素、空腹血糖）與醫師專業評估。"
                "線上衛教無法取代醫師的親自診斷，建議您盡速至新陳代謝科門診，由專科醫師為您做完整的檢查與評估喔。"
            )
            return GuardResult(is_blocked=True, risk_category="DIAGNOSTIC_BREACH", blocked_message=safe_override)
        if cls._MIRACLE_CLAIM_RE.search(text):
            safe_override = (
                "【健康衛教指引】\n"
                "糖尿病是一種需要長期自我管理的慢性代謝情況，透過均衡飲食、規律運動、定時監測與配合醫療團隊照護，"
                "可以非常良好地穩定控制血糖並預防併發症。請勿輕信任何號稱能快速根治或神奇治癒的不實資訊喔！"
            )
            return GuardResult(is_blocked=True, risk_category="MIRACLE_CLAIM", blocked_message=safe_override)
        return GuardResult(is_blocked=False, risk_category="NONE")


def inspect_safety_guard(text: str) -> GuardResult:
    return ClinicalSafetyGuard.inspect(text)

def inspect_output_guard(text: str) -> GuardResult:
    return ClinicalSafetyGuard.inspect_output(text)

def strip_emojis(text: str) -> str:
    """物理過濾所有 Unicode Emoji 與符號圖標，嚴格落實全系統零 Emoji 臨床規範"""
    if not text:
        return ""
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\u200d\ufe0f]",
        flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub("", text)
    # 清理可能殘留的雙空格
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned.strip()

def enforce_single_question_budget(text: str) -> str:
    if not text:
        return text
    text = strip_emojis(text)
    q_matches = list(re.finditer(r"[？\?]", text))
    if len(q_matches) <= 1:
        return text
    first_q_end = q_matches[0].end()
    return text[:first_q_end].strip()
