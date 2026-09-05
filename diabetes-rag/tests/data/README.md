# 測試用的固定查詢向量（golden fixture）

`demo_query_embeddings.json` 是**真實** Gemini（`models/gemini-embedding-2`、
`task_type=RETRIEVAL_QUERY`、3072 維）對 9/3 展示考古題所用查詢字串算出來的
向量，逐字錄下來存進版控。

## 為什麼需要這個檔案

`tests/test_end_to_end.py` 原本的飲食題測試是**完全 mock** 過的：它塞一個
「跟自己 cosine 相似度 = 1.0」的合成向量進索引，所以不論
`DEFAULT_VECTOR_SIMILARITY_THRESHOLD` 設成多少，那個測試都一定會通過。
2026-09-01 的全面複驗因此才會出現「`pytest` 全綠、但展示考古題在真實情境
下拿不到任何一筆衛教內容」——測試綠燈完全沒有反映真實行為
（見 `../../02_MS2_demo/notes/2026-09-01_rag_system_report.md` §8.1）。

錄下真實的查詢向量之後，測試就能在**沒有網路、沒有 `GEMINI_API_KEY`** 的
情況下，跑完整條管線並算出**真實的 cosine 分數**——門檻、RRF 融合、
truncate 全部是真的。這個測試在門檻 0.78 的舊設定下會失敗，也就是說
它真的能抓到當初漏掉的那個 bug。

## 怎麼重新產生

只有在查詢字串要改、或語料換 embedding 模型時才需要重跑：

```bash
export GEMINI_API_KEY=...
python scripts/record_query_embeddings.py
```

向量存到小數點後 8 位，對 cosine 的影響在 1e-7 等級，不影響任何斷言。
