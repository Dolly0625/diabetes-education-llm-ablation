# 糖尿病衛教助理（獨立包）

LINE 糖尿病衛教與看診前整理助理，詳見 [`diabetes_chatbot/README.md`](diabetes_chatbot/README.md)。

```bash
pip install -r requirements.txt
cp .env.example .env   # 填 GEMINI_API_KEY 或 OPENCODE_API_KEY
python3 -m uvicorn diabetes_chatbot.server.app:app --host 0.0.0.0 --port 8000
```
