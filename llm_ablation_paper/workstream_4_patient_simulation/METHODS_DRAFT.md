# 模擬病患與角色扮演設定（草稿）

本研究以十二份已驗收的合成病患 profile 建立可重跑的多輪壓力測試環境，而非招募真人病患或進行臨床驗證。profiles 涵蓋日常飲食、藥物副作用、自行停藥或調藥意圖、亞急性低血糖、回診前資訊整理，以及多輪事實矛盾或更正六類情境，每類兩名病患。每份 profile 固定記錄 persona、已知事實、隱藏事實、揭露規則、病患目標、風險觸發條件及六輪上限；同一份原始 profile 不因 A、B、C、D 任一條件的初步表現而更換、重寫或補充。

Patient Agent 依既有 prompt 模擬台灣長輩自然口語，僅可陳述 known facts 與已按規則解鎖的 hidden facts，且不提供醫療診斷、處方或劑量調整。隱藏資訊採 direct-question-only 原則：助理未直接詢問對應主題時，病患不得主動補充；FACT_CONTRADICTION 情境則只在 profile 指定的 correction turn 更正先前陳述。每輪 Agent 都必須輸出結構化 JSON，包含病患話語、是否結束、終止原因、本輪新揭露欄位與支持證據，使 runner 不以自由文字臆測病患意圖。

每一條軌跡將同一位 profile 分別置於 A、B、C、D，依序形成「病患訊息、系統回覆、下一輪病患訊息」的交替對話。Talker、Planner、Patient Agent 與 Judge 的模型及溫度依研究協議固定；每條對話最多六輪。為避免跨條件記憶污染，runner 為每條軌跡配置唯一 run ID、user ID、獨立 temporary state directory，並透過 WS1 Harness 的 subprocess 介面執行。每完成一輪便以原子寫入保存 WS4 checkpoint；重新執行時僅從最後一個完整 checkpoint 繼續。暫時性 API 錯誤最多採 1、2、4、8 秒的指數退避，仍失敗則保留 ERROR 與 retry metadata，不靜默刪除樣本。

軌跡只可由 PATIENT_GOAL_MET、MAX_TURNS、COMMON_INPUT_BLOCK 或 ERROR 結束。輸入被共同 Input Guard 攔截時，記錄為 COMMON_INPUT_BLOCK，並依研究協議與主要 A–D 效果估計分開處理。於正式 prompt、工具 schema 與 commit 指紋完成凍結前，本工作流僅使用 deterministic fake model 完成一位 profile × 四條件 dry run 與離線測試；48 條正式軌跡由技術主持人驗收並執行。故本流程能支持指定模擬情境中的可重跑系統壓力測試，但不支持真人病患表現、臨床安全率或醫療有效性主張。
