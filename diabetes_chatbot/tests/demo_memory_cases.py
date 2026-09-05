"""
長期記憶存放內容展示案例 (Longitudinal Memory Showcase Cases)
示範三種臨床情境下，長期健康檔案 (patient_record.json) 的真實內容與演變
"""
import json
import tempfile
from pathlib import Path

from diabetes_chatbot.memory import (
    load_patient_record,
    update_medications,
    update_previsit_summary,
    extract_clinical_facts_from_text,
    format_patient_context
)

def run_showcase():
    with tempfile.TemporaryDirectory() as tmpdir:
        patient_file = Path(tmpdir) / "showcase_patient.json"
        
        print("=" * 70)
        print("【初始狀態：全新病患建檔】")
        print("=" * 70)
        init_record = load_patient_record(patient_file)
        print("長期記憶檔案內容 (JSON)：")
        print(json.dumps(init_record, ensure_ascii=False, indent=2))
        print("\n動態注入護理師大腦的背景文字：")
        print(repr(format_patient_context(patient_file)))
        
        print("\n" + "=" * 70)
        print("【案例一：病患上傳健保藥袋照片，QR Code 解析成功】")
        print("情境：病患拍下藥袋照片，解析出兩筆藥品名稱")
        print("=" * 70)
        scanned_meds = [
            "癲通 長效膜衣錠 ２００毫克（卡巴氮平）",
            "TEGRETOL CR.FC * tab 200 mg (Carbamazepine)"
        ]
        update_medications(scanned_meds, source="藥袋辨識(QR Code 辨識)", file_path=patient_file)
        
        rec1 = load_patient_record(patient_file)
        print("長期記憶檔案內容 (JSON)：")
        print(json.dumps(rec1, ensure_ascii=False, indent=2))
        print("\n動態注入護理師大腦的背景文字：")
        print(format_patient_context(patient_file))
        
        print("\n" + "=" * 70)
        print("【案例二：病患自然聊天，口述血糖數值、不適症狀與新用藥】")
        print("情境：病患說「我早上空腹血糖大概 135，最近肚子常脹氣，我每天吃庫魯化」")
        print("=" * 70)
        chat_text = "護理師好，我早上空腹血糖大概 135，最近吃完晚餐肚子很常脹氣，我每天有在吃庫魯化。"
        facts = extract_clinical_facts_from_text(chat_text, file_path=patient_file)
        print("背景自動萃取出的客觀事實：", facts)
        
        rec2 = load_patient_record(patient_file)
        print("\n長期記憶檔案內容 (JSON)：")
        print(json.dumps(rec2, ensure_ascii=False, indent=2))
        print("\n動態注入護理師大腦的背景文字：")
        print(format_patient_context(patient_file))
        
        print("\n" + "=" * 70)
        print("【案例三：產出新陳代謝科門診預問診摘要（就醫備忘錄）並存檔】")
        print("情境：護理師為病患整理好回診重點，系統自動將卡片持久化保存")
        print("=" * 70)
        sample_summary = (
            "【新陳代謝科 門診預問診摘要 (Pre-visit Intake Summary)】\n"
            "1. 本次回診核心訴求：定期回診拿慢箋，想諮詢肚子脹氣問題\n"
            "2. 目前用藥與順從性：庫魯化、癲通（病患按時服用）\n"
            "3. 近期血糖控制情況：空腹血糖約 135 mg/dL\n"
            "4. 急性低血糖事件評估：近期無低血糖事件\n"
            "5. 藥物副作用與併發警訊：反應服藥後偶有脹氣困擾"
        )
        update_previsit_summary(sample_summary, file_path=patient_file)
        
        rec3 = load_patient_record(patient_file)
        print("長期記憶檔案內容 (JSON)：")
        print(json.dumps(rec3, ensure_ascii=False, indent=2))
        print("\n動態注入護理師大腦的背景文字：")
        print(format_patient_context(patient_file))

if __name__ == "__main__":
    run_showcase()
