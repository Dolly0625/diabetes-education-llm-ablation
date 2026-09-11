"""
多模態藥袋感知模組 (Multimodal Perception Agent)
移植並復用專案既有的健保藥袋 QR Code 與 OCR 辨識能力 (MedicationBagOCRService)。
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional
from diabetes_chatbot.vendor.qr_ocr_service import MedicationBagOCRService

_service_instance: Optional[MedicationBagOCRService] = None

def get_ocr_service() -> MedicationBagOCRService:
    global _service_instance
    if _service_instance is None:
        _service_instance = MedicationBagOCRService()
    return _service_instance


def parse_medication_bag(image_path: str | Path) -> dict[str, Any]:
    """
    解析藥袋照片或處方箋
    回傳範例:
    {
        "success": True,
        "medications": ["癲通 長效膜衣錠 ２００毫克（卡巴氮平）"],
        "confidence": 0.95,
        "method": "QR Code 辨識", # 或 "文字光學辨識 (OCR)"
        "message": "成功從藥袋辨識出 1 項藥品"
    }
    """
    path = Path(image_path)
    if not path.exists():
        return {
            "success": False,
            "medications": [],
            "confidence": 0.0,
            "method": "none",
            "message": f"找不到圖片檔案：{image_path}"
        }
        
    try:
        with open(path, "rb") as f:
            image_bytes = f.read()
            
        service = get_ocr_service()
        result = service.extract(image_bytes)
        
        meds = result.get("meds") or []
        valid_meds = []
        for m in meds:
            m_clean = m.strip()
            if not m_clean or len(m_clean) < 2 or len(m_clean) > 150:
                continue
            if any(m_clean.startswith(prefix) for prefix in ("此圖片", "這張圖片", "[非藥袋", "非藥袋", "這並非", "這不是")):
                continue
            valid_meds.append(m_clean)
        
        qr_used = result.get("qr_used", False)
        vision_used = result.get("vision_used", False)
        confidence = result.get("confidence", 0.0)
        
        if qr_used:
            method = "QR Code 辨識"
        elif vision_used:
            method = "多模態視覺辨識 (Vision LLM)"
        else:
            method = "文字光學辨識 (OCR)"
            
        import logging
        logger = logging.getLogger("uvicorn.error")
        logger.info(f"[藥袋感知] 圖片分析完成 | 方法: {method} | 信心度: {confidence:.2f} | 原始解析: {meds} | 有效藥品: {valid_meds}")
        
        if valid_meds:
            return {
                "success": True,
                "medications": valid_meds,
                "confidence": confidence,
                "method": method,
                "message": f"成功透過 {method} 辨識出藥品"
            }
        else:
            return {
                "success": False,
                "medications": [],
                "confidence": confidence,
                "method": method,
                "message": "圖片中未偵測到清晰的藥品名稱或處方 QR Code"
            }
            
    except Exception as e:
        return {
            "success": False,
            "medications": [],
            "confidence": 0.0,
            "method": "error",
            "message": f"藥袋辨識發生異常：{str(e)}"
        }

# ==============================================================================
# 語音感知模組：聯發科 Breeze-ASR-26 (Apple Silicon Metal GPU 加速)
# ==============================================================================

def _clean_asr_hallucinations(text: str) -> str:
    """清洗語音辨識常見的括號非語音雜訊與重複幻覺"""
    import re
    if not text:
        return ""
    # 1. 移除各種括號內的背景雜音/非口語標記，如 (肚子餓)、（咳嗽）、[雜音] 等
    cleaned = re.sub(r"[\(（\[][^\)）\]]*?[\)）\]]", "", text).strip()
    if not cleaned:
        # 若清洗後空了，代表整句話都在括號內，此時拿掉括號保留內部內容
        cleaned = re.sub(r"[\(（\[\)）\]]", "", text).strip()

    # 2. 去除連續重複的疊詞（例如：肚子餓 肚子餓 肚子餓 -> 肚子餓）
    words = cleaned.split()
    if words:
        deduped = []
        for w in words:
            if not deduped or w != deduped[-1]:
                deduped.append(w)
        cleaned = "".join(deduped) if all(len(w) <= 4 for w in deduped) else " ".join(deduped)

    # 3. 針對字元級連續重複（例如：肚子餓肚子餓肚子餓 -> 肚子餓）
    cleaned = re.sub(r"(.{2,8}?)\1{2,}", r"\1", cleaned)
    return cleaned.strip()


def parse_taiwanese_audio(audio_path: str | Path) -> dict[str, Any]:
    """
    使用聯發科 Breeze-ASR-26 專屬模型解析台灣長輩國台語夾雜語音。
    支援 .wav, .m4a, .mp3 等格式。
    """
    import shutil
    import subprocess
    import time
    
    path = Path(audio_path)
    if not path.exists():
        return {
            "success": False,
            "text": "",
            "duration": 0.0,
            "message": f"找不到音訊檔案：{audio_path}"
        }
        
    model_path = Path(__file__).resolve().parent.parent / "models/breeze_asr/ggml-model-q5_0.bin"
    if not model_path.exists():
        return {
            "success": False,
            "text": "",
            "duration": 0.0,
            "message": f"未找到 Breeze-ASR-26 權重檔案：{model_path}"
        }
        
    whisper_bin = shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli"
    if not Path(whisper_bin).exists():
        return {
            "success": False,
            "text": "",
            "duration": 0.0,
            "message": "系統未安裝 whisper-cli，請執行 brew install whisper-cpp"
        }
        
    try:
        # 若非 16kHz WAV，透過 ffmpeg 自動轉檔至暫存 WAV
        run_wav = path
        temp_wav = None
        if path.suffix.lower() != ".wav":
            temp_wav = path.parent / f"_temp_{path.stem}.wav"
            conv_cmd = ["ffmpeg", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(temp_wav)]
            subprocess.run(conv_cmd, capture_output=True, check=True)
            run_wav = temp_wav

        start_t = time.time()
        cmd = [
            whisper_bin,
            "-m", str(model_path),
            "-f", str(run_wav),
            "-l", "zh",
            "-t", "8",
            "--no-timestamps",
            "-sns"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        duration = time.time() - start_t

        if temp_wav and temp_wav.exists():
            temp_wav.unlink()

        lines = [l.strip() for l in proc.stdout.split("\n") if l.strip() and not l.startswith("whisper_") and not l.startswith("ggml_") and not l.startswith("load_") and not l.startswith("system_") and not l.startswith("main:")]
        raw_text = " ".join(lines).strip()
        text = _clean_asr_hallucinations(raw_text)

        if text:
            return {
                "success": True,
                "text": text,
                "duration": duration,
                "engine": "MediaTek Breeze-ASR-26 (Apple Metal)",
                "message": "語音辨識成功"
            }
        else:
            return {
                "success": False,
                "text": "",
                "duration": duration,
                "engine": "MediaTek Breeze-ASR-26 (Apple Metal)",
                "message": "未能從語音中辨識出有效文字"
            }
    except Exception as e:
        return {
            "success": False,
            "text": "",
            "duration": 0.0,
            "message": f"語音辨識發生異常：{str(e)}"
        }
