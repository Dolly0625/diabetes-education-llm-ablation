"""將 bronze_triples_retrievable.json 的 29 條可檢索三元組匯入 Neo4j。

只做一件事：把 loaders.load_graph_triples() 已經正規化過的三元組寫進 Neo4j，
讓 Neo4jGraphRetriever 之後可以讀回來，交給跟 GraphRetriever 完全相同的
比對／排序邏輯處理——這是保證兩個後端行為一致（對拍測試會過）最直接的
做法，而不是在 Cypher 裡重新發明一次比對演算法。

圖的形狀完全照著資料本身，不額外加抽象層：

* 節點標籤就是實體的 `type`（Substance／Condition／Trigger／LabParameter），
  資料裡有哪幾種就建哪幾種，沒有共通的上層標籤。
* 關係型別就是三元組的 `relation`（TREATS／CAUTION_FOR／INDUCES…），不是塞
  進一個通用型別底下當屬性。
* Cypher 的節點標籤與關係型別都不能用 $參數 帶入，只能組進查詢字串本身，
  所以拼接前一律先用白名單正則檢查（只允許英數字與底線）。`relation` 另外
  也留一份當屬性，供除錯用。

節點依「正規化後的 label + type」合併（MERGE），跟 graph.py 判斷兩個實體
是不是同一個概念的邏輯一致——直接 import 它的 `_normalise_label`，不另外
刻一份，避免兩邊定義漂移。刻意不依 `id` 合併：id 是上游逐三元組指派的，
同一個概念在不同三元組裡幾乎都是不同的 id（例如「急性腎損傷」在 8 筆三元
組裡有 8 個不同 id），依 id 合併等於每筆三元組的 subject／object 都各自變成
獨立節點，匯出來是一堆互不相連的孤島，跟 GraphRetriever 實際依 label 走的
多跳路徑對不上。合併後節點的 id／label／code 保留第一次建立它那筆三元組的
值（`ON CREATE SET` 只在建立當下寫入一次）。

連線資訊一律吃環境變數，不寫死：
    NEO4J_URI       例如 bolt://localhost:7687
    NEO4J_USER      例如 neo4j
    NEO4J_PASSWORD

用法：
    python scripts/load_neo4j.py
"""
from __future__ import annotations

import os
import re

from neo4j import GraphDatabase

from rag_retrieval.loaders import GraphTripleRecord, load_graph_triples
from rag_retrieval.retrievers.graph import _normalise_label

# 白名單：relation 值只能是大寫字母／數字／底線組成，確認安全後才會被拼進
# Cypher 查詢字串當關係型別使用（Cypher 的關係型別無法參數化）。
_RELATION_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# 白名單：type 值（Substance／Condition／Trigger／LabParameter…）只能是英文
# 字母／數字／底線組成，確認安全後才會被拼進 Cypher 當節點標籤使用。
_LABEL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"缺少環境變數 {name}，連線資訊不可寫死在程式裡")
    return value


def _check_label(label: str) -> str:
    if not _LABEL_NAME_RE.match(label):
        raise ValueError(f"type 值 {label!r} 不符合預期格式，拒絕用來組 Cypher 節點標籤")
    return label


def _entity_labels(triples: list[GraphTripleRecord]) -> list[str]:
    """這批資料實際用到的節點標籤，直接從三元組推導出來——不寫死清單，
    上游哪天多出 Symptom／Intervention 這類 EntityType 也不用改這裡。"""
    labels = {t.subject_type for t in triples} | {t.object_type for t in triples}
    return sorted(_check_label(label) for label in labels)


def main() -> None:
    uri = _env("NEO4J_URI")
    user = _env("NEO4J_USER")
    password = _env("NEO4J_PASSWORD")

    triples = load_graph_triples()
    labels = _entity_labels(triples)
    print(f"從 loaders.load_graph_triples() 讀到 {len(triples)} 條三元組，開始匯入 Neo4j…")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            session.execute_write(_clear_graph, labels)
            session.execute_write(_ensure_constraints, labels)
            for seq, t in enumerate(triples):
                session.execute_write(_import_triple, seq, t)
        print(f"匯入完成：{len(triples)} 條三元組，節點標籤 {labels}（依正規化 label + type 合併）。")
    finally:
        driver.close()


def _clear_graph(tx, labels: list[str]) -> None:
    # 逐個標籤清除，範圍剛好是這批資料會建立的節點，不會動到資料庫裡的其他
    # 東西。（若先前匯入過、而這次資料不再包含的標籤，需自行清理。）
    for label in labels:
        tx.run(f"MATCH (n:`{label}`) DETACH DELETE n")


def _ensure_constraints(tx, labels: list[str]) -> None:
    # Neo4j 的約束綁在單一標籤上，所以每個標籤各建一條。合併鍵是
    # label_key + type，id 只在建立當下寫入一次，因此仍然唯一——這條約束是
    # 「沒有意外重複寫入」的安全網。
    for label in labels:
        tx.run(
            f"CREATE CONSTRAINT entity_id_{label.lower()} IF NOT EXISTS "
            f"FOR (e:`{label}`) REQUIRE e.id IS UNIQUE"
        )


def _import_triple(tx, seq: int, t: GraphTripleRecord) -> None:
    if not _RELATION_NAME_RE.match(t.relation):
        raise ValueError(
            f"relation 值 {t.relation!r} 不符合預期格式，拒絕用來組 Cypher 關係型別"
        )
    subj_label = _check_label(t.subject_type)
    obj_label = _check_label(t.object_type)

    # 標籤與關係型別都經過上面的白名單檢查才拼進查詢字串。
    query = f"""
        MERGE (s:`{subj_label}` {{label_key: $subj_label_key, type: $subj_type}})
          ON CREATE SET s.id = $subj_id, s.label = $subj_label, s.code = $subj_code
        MERGE (o:`{obj_label}` {{label_key: $obj_label_key, type: $obj_type}})
          ON CREATE SET o.id = $obj_id, o.label = $obj_label, o.code = $obj_code
        CREATE (s)-[r:`{t.relation}` {{
            import_seq: $seq,
            chunk_id: $chunk_id,
            source: $source,
            version: $version,
            date: $date,
            status: $status,
            content: $content,
            relation: $relation,
            subject_type: $subj_type,
            object_type: $obj_type,
            condition: $condition,
            effect: $effect,
            confidence: $confidence,
            negation_checked: $negation_checked,
            additional_sources: $additional_sources
        }}]->(o)
        """
    tx.run(
        query,
        seq=seq,
        chunk_id=t.chunk_id,
        source=t.source,
        version=t.version,
        date=t.date,
        status=t.status,
        content=t.content,
        relation=t.relation,
        subj_id=t.subject.id,
        subj_type=t.subject_type,
        subj_label=t.subject.label,
        subj_label_key=_normalise_label(t.subject.label),
        subj_code=t.subject.code,
        obj_id=t.object.id,
        obj_type=t.object_type,
        obj_label=t.object.label,
        obj_label_key=_normalise_label(t.object.label),
        obj_code=t.object.code,
        condition=t.condition,
        effect=t.effect,
        confidence=t.confidence,
        negation_checked=t.negation_checked,
        additional_sources=list(t.additional_sources),
    )


if __name__ == "__main__":
    main()
