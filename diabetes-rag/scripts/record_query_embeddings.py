#!/usr/bin/env python3
"""把 9/3 展示考古題用到的查詢字串，用真實 Gemini API 算出向量並存成
測試用的固定 fixture（`tests/data/demo_query_embeddings.json`）。

需要網路與 `GEMINI_API_KEY`。這是一次性的錄製步驟，只有在查詢字串要改、
或語料換 embedding 模型時才需要重跑——平常跑 `pytest` 完全不會用到網路，
只會讀這個檔案。

為什麼要錄下來：原本的飲食題端到端測試塞的是「跟自己相似度 = 1.0」的合成
向量，因此不論門檻設多少都會通過，2026-09-01 複驗才會發現「pytest 全綠但
展示題在真實情境下拿不到衛教內容」。錄真實向量之後，測試算的是真實 cosine
分數，門檻設錯就會紅燈。詳見 tests/data/README.md。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_retrieval.embedding import embed_query  # noqa: E402

# CLAUDE.md §1 指定的兩題展示考古題，搭配 LLM 組 Guardrail 會產生的
# `retrieval_queries`（與 eval/queries_hpa_gap.json、eval/queries.json 一致）。
QUERY_STRINGS = [
    # 第二題：飲食衛教題——本次修正的主角。
    "糖尿病 飲食原則",
    "糖尿病 均衡飲食",
    # 第一題：胰島素注射題，一併錄起來，讓兩題展示考古題都能離線重現。
    "胰島素 注射部位",
    "胰島素 皮膚 澱粉樣變性症",
]

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1] / "tests" / "data" / "demo_query_embeddings.json"
)
# 8 位小數對 cosine 的影響在 1e-7 等級，但能讓檔案小一半。
PRECISION = 8


def main() -> None:
    output = DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    recorded = {}
    for text in QUERY_STRINGS:
        vector = embed_query(text)
        recorded[text] = [round(x, PRECISION) for x in vector]
        print(f"  {text} -> {len(vector)} 維", file=sys.stderr)

    with open(output, "w", encoding="utf-8") as fh:
        json.dump(recorded, fh, ensure_ascii=False)
    print(f"wrote {len(recorded)} query embeddings -> {output}")


if __name__ == "__main__":
    main()
