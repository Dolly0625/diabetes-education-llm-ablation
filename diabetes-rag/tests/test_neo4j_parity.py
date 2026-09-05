"""對拍測試：`Neo4jGraphRetriever` 對 `eval/queries.json` 裡 10 題 graph 查詢
回傳的候選，必須跟記憶體版 `GraphRetriever` 完全一致（chunk_id 集合與排序）。

沒裝 `neo4j` 驅動、或連不上 Neo4j 時整個檔案要 skip，不能讓 pytest 變紅——
其他人的環境沒有 Neo4j。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("neo4j")

from rag_retrieval.loaders import load_graph_triples
from rag_retrieval.retrievers.graph import GraphRetriever
from rag_retrieval.retrievers.neo4j_backend import Neo4jGraphRetriever

# 釘死這 10 個 query_id，不要用「track == graph 全部抓」——eval/queries.json
# 之後會被 Boundary C 擴充到 40 題（只新增、不刪改），釘死 id 才不會讓對拍
# 範圍被之後新增的負向題悄悄改變。
_GRAPH_QUERY_IDS = [f"g{n:02d}" for n in range(1, 11)]
_EVAL_QUERIES_PATH = Path(__file__).resolve().parents[1] / "eval" / "queries.json"


def _load_graph_queries() -> list[dict]:
    with _EVAL_QUERIES_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    by_id = {q["query_id"]: q for q in data}
    missing = [qid for qid in _GRAPH_QUERY_IDS if qid not in by_id]
    assert not missing, f"eval/queries.json 少了預期的 query_id：{missing}"
    return [by_id[qid] for qid in _GRAPH_QUERY_IDS]


@pytest.fixture(scope="module")
def neo4j_retriever():
    try:
        retriever = Neo4jGraphRetriever()
    except Exception as exc:  # noqa: BLE001 —— 沒裝/沒連上 Neo4j 一律 skip
        pytest.skip(f"連不上 Neo4j，跳過對拍測試：{exc}")
    else:
        yield retriever
        retriever.close()


@pytest.fixture(scope="module")
def memory_retriever() -> GraphRetriever:
    return GraphRetriever(load_graph_triples())


@pytest.mark.parametrize(
    "query", _load_graph_queries(), ids=[q["query_id"] for q in _load_graph_queries()]
)
def test_neo4j_matches_memory_backend(query, neo4j_retriever, memory_retriever):
    queries = query["retrieval_queries"]

    neo4j_result = neo4j_retriever.search(queries)
    memory_result = memory_retriever.search(queries)

    neo4j_ids = [c.chunk_id for c in neo4j_result.candidates]
    memory_ids = [c.chunk_id for c in memory_result.candidates]

    assert neo4j_ids == memory_ids, (
        f"{query['query_id']} 對拍失敗：\n"
        f"  neo4j  = {neo4j_ids}\n"
        f"  memory = {memory_ids}"
    )
    assert neo4j_result.graph_path_status == memory_result.graph_path_status
