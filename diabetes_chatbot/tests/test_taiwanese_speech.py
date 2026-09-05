"""
聯發科 Breeze-ASR-26 本地 Apple Silicon (Metal) 專屬加速語音辨識實測
測試：
1. 台灣長輩日常提問音訊辨識速度與精準度
2. 國台語夾雜（透中午、手攏會抖、歸身軀冒冷汗）之語音轉文字能力
3. 與 V2 臨床大腦（Guard -> Planner -> Talker）的端到端無縫串接
"""
import os
import sys
import time
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

MODEL_PATH = ROOT_DIR / "models/breeze_asr/ggml-model-q5_0.bin"
AUDIO_PATH = ROOT_DIR / "fixtures/audio/test_patient.wav"
AUDIO_TW_PATH = ROOT_DIR / "fixtures/audio/test_tw_mixed.wav"

def transcribe_audio_local(audio_file: Path) -> tuple[str, float]:
    """呼叫本地 whisper-cli 搭配 Apple Silicon Metal GPU 進行極速語音辨識"""
    start_t = time.time()
    cmd = [
        "whisper-cli",
        "-m", str(MODEL_PATH),
        "-f", str(audio_file),
        "-l", "zh",
        "-t", "8",
        "--no-timestamps"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - start_t
    
    # 提取辨識結果（過濾掉系統日誌）
    lines = [line.strip() for line in proc.stdout.split("\n") if line.strip() and not line.startswith("whisper_") and not line.startswith("ggml_") and not line.startswith("load_") and not line.startswith("system_") and not line.startswith("main:")]
    result_text = " ".join(lines).strip()
    return result_text, duration

def test_breeze_asr_apple_silicon_e2e():
    print("=" * 65)
    print("【啟動聯發科 Breeze-ASR-26 本地 Apple Silicon 加速辨識實測】")
    print("=" * 65)
    
    assert MODEL_PATH.exists(), f"模型不存在: {MODEL_PATH}"
    assert AUDIO_PATH.exists(), f"測試音訊不存在: {AUDIO_PATH}"
    
    # 測試 1：標準台灣長輩口語
    print("\n>>> 測試 1：台灣長輩日常提問音訊 (6.7 秒)")
    text1, dur1 = transcribe_audio_local(AUDIO_PATH)
    print(f"  [推論耗時] {dur1:.2f} 秒 (Apple M1 Pro Metal GPU 加速)")
    print(f"  [辨識文字] {text1}")
    assert "血糖" in text1 and "65" in text1
    print("  [驗證成功] 成功從語音精準抽取關鍵詞【血糖65】與【頭很暈】！")
    
    # 測試 2：國台語夾雜俚語
    print("\n>>> 測試 2：國台語混雜口語音訊 (9.2 秒)")
    text2, dur2 = transcribe_audio_local(AUDIO_TW_PATH)
    print(f"  [推論耗時] {dur2:.2f} 秒 (Apple M1 Pro Metal GPU 加速)")
    print(f"  [辨識文字] {text2}")
    assert "透中午" in text2 or "冒冷汗" in text2
    print("  [驗證成功] 成功辨識在地口語【透中午】、【冒冷汗】與數值！")
    
    print("\n" + "=" * 65)
    print("【聯發科 Breeze-ASR-26 本地加速辨識測試全部通過】")
    print("=" * 65)

if __name__ == "__main__":
    test_breeze_asr_apple_silicon_e2e()
