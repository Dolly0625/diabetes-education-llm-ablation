import json
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "chat_logs.jsonl"

def log_turn(user_msg: str, bot_msg: str, latency: float, tool_used: str = "none"):
    """將單輪對話記錄與效能數據寫入日誌"""
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latency_sec": round(latency, 2),
        "tool_used": tool_used,
        "user": user_msg,
        "assistant": bot_msg,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
