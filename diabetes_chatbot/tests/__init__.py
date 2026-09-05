import sys
from pathlib import Path

# 將專案根目錄注入模組搜尋路徑
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
