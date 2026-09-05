import json
import os
import warnings
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

warnings.filterwarnings("ignore")

# 1. 讀取設定與建立 Client
load_dotenv(Path(__file__).parent.parent / ".env")
client = OpenAI(
    api_key=os.getenv("OPENCODE_API_KEY"),
    base_url=os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1")
)

# 2. 真正的「翻書小函式」
BOOK_PATH = Path(__file__).parent.parent / "diabetes-rag/src/rag_retrieval/data/hpa_dm_book.json"

def search_handbook(query: str) -> str:
    """在國健署手冊中搜尋關鍵字段落"""
    if not BOOK_PATH.exists():
        return "衛教手冊檔案不存在。"
    
    with open(BOOK_PATH, encoding="utf-8") as f:
        chapters = json.load(f)
    
    # 拆解關鍵字並在手冊中比對
    keywords = query.split()
    for ch in chapters:
        content = ch.get("page_content", "")
        # 如果關鍵字出現在章節內容中
        if any(k in content for k in keywords):
            # 擷取含有關鍵字的周邊文字（約 350 字）
            idx = content.find(keywords[0]) if keywords[0] in content else 0
            start = max(0, idx - 50)
            end = min(len(content), idx + 300)
            return content[start:end]
            
    return "手冊中未找到完全相符的段落。"

# 3. 定義 Tool 說明書
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_handbook",
            "description": "查詢衛生福利部國民健康署《糖尿病與我》手冊。當需要確認診斷標準、血糖數值定義、飲食指引等具體醫學依據時使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "提煉出的搜尋關鍵字"
                    }
                },
                "required": ["keyword"]
            }
        }
    }
]

# 4. 病人提問
patient_question = "我健檢報告出來，空腹血糖寫 115，醫生說有點高但不是糖尿病，這到底是什麼意思啊？"

messages = [
    {"role": "system", "content": "你是一位溫暖專業的糖尿病衛教護理師。如果需要查詢確切標準，請使用 search_handbook。查到資料後請用口語、親切自然的人話回答，不要長篇大論，不使用表情符號，嚴禁罐頭免責聲明。"},
    {"role": "user", "content": patient_question}
]

print("=" * 60)
print(f"【病人提問】\n{patient_question}")
print("=" * 60)

# 第一步：讓模型決定要不要翻書
resp = client.chat.completions.create(
    model="mimo-v2.5",
    messages=messages,
    tools=tools,
    temperature=0.2,
)

msg = resp.choices[0].message

if msg.tool_calls:
    tool_call = msg.tool_calls[0]
    args = json.loads(tool_call.function.arguments)
    keyword = args.get("keyword", "")
    print(f"\n[動作 1] 模型決定翻書，關鍵字：【{keyword}】")
    
    # 第二步：真正翻開書本找出段落
    book_evidence = search_handbook(keyword)
    print(f"\n[動作 2] 手冊翻到的官方文字證據：\n---\n{book_evidence.strip()}\n---")
    
    # 第三步：把翻到的官方依據交給模型
    messages.append(msg)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": book_evidence
    })
    
    final_resp = client.chat.completions.create(
        model="mimo-v2.5",
        messages=messages,
        temperature=0.5,
    )
    
    print(f"\n[動作 3] 衛教護理師根據手冊給出的最終回答：\n{final_resp.choices[0].message.content.strip()}")

print("=" * 60)
