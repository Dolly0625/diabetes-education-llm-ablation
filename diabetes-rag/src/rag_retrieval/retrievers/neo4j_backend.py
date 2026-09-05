"""Neo4jGraphRetriever——`base.py` 的 `Retriever` protocol 的另一種實作，
資料來源是 Neo4j 而不是 graph.py 的記憶體字典。見 CLAUDE.md §10 與
`scripts/load_neo4j.py` 的匯入邏輯。

策略：Neo4j 只負責「儲存與讀回」29 條三元組；比對／多跳展開／評分完全
交給跟 `GraphRetriever` 一模一樣的邏輯處理（在內部建立一個 `GraphRetriever`
實例，把從 Neo4j 讀回的三元組交給它）。這是刻意的設計，不是偷懶：

在 Cypher 裡重新發明一次 `_match_count` 的雙向子字串比對、跳數展開與
`confidence * specificity * (0.9**hop)` 的評分公式，兩邊要逐位元完全一致
才能通過對拍測試——重寫一次演算法只是多一個地方會不小心跟原版不同步。
資料來源不同、比對邏輯共用，一樣能證明「同一介面、兩種後端」，而且行為
一致是透過建構方式保證的，不是靠巧合。

連線資訊一律吃環境變數：NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD。
"""
from __future__ import annotations

import os
from typing import Optional

from neo4j import GraphDatabase

from ..loaders import GraphEntityRecord, GraphTripleRecord
from .graph import GraphRetriever, GraphSearchResult


class Neo4jGraphRetriever:
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._uri = uri or self._require_env("NEO4J_URI")
        self._user = user or self._require_env("NEO4J_USER")
        self._password = password or self._require_env("NEO4J_PASSWORD")
        self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
        self._driver.verify_connectivity()
        self._inner = GraphRetriever(self._fetch_triples())

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"缺少環境變數 {name}")
        return value

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Neo4jGraphRetriever":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def search(self, queries: list[str], top_k: int = 10) -> GraphSearchResult:
        """跟 `GraphRetriever.search` 相同的簽章與回傳型別——直接委派給內部
        的記憶體檢索器，資料已經在 `__init__` 時從 Neo4j 讀回並重建過。
        """
        return self._inner.search(queries, top_k)

    def _fetch_triples(self) -> list[GraphTripleRecord]:
        # load_neo4j.py 完全照著資料本身建圖：關係型別是三元組實際的
        # relation（TREATS／CAUTION_FOR…），節點標籤是實體的 type
        # （Substance／Condition／Trigger／LabParameter），沒有共通的上層
        # 標籤可以拿來過濾。所以這裡對任何標籤／任何關係型別比對，用
        # type(r) 取回實際的關係型別名稱，靠 import_seq 還原匯入順序。
        query = """
        MATCH (s)-[r]->(o)
        RETURN r, s, o, type(r) AS relation_type
        ORDER BY r.import_seq
        """
        with self._driver.session() as session:
            records = list(session.run(query))

        triples: list[GraphTripleRecord] = []
        for rec in records:
            r, s, o = rec["r"], rec["s"], rec["o"]
            triples.append(
                GraphTripleRecord(
                    chunk_id=r["chunk_id"],
                    source=r["source"],
                    version=r["version"],
                    date=r["date"],
                    status=r["status"],
                    content=r["content"],
                    subject=GraphEntityRecord(
                        id=s["id"], type=s["type"], label=s["label"], code=s.get("code")
                    ),
                    subject_type=r["subject_type"],
                    relation=rec["relation_type"],
                    object=GraphEntityRecord(
                        id=o["id"], type=o["type"], label=o["label"], code=o.get("code")
                    ),
                    object_type=r["object_type"],
                    condition=r.get("condition"),
                    effect=r.get("effect"),
                    confidence=r.get("confidence"),
                    negation_checked=r.get("negation_checked"),
                    additional_sources=list(r.get("additional_sources") or []),
                )
            )
        return triples
