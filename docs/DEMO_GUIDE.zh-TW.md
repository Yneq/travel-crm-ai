# VoyageOps AI 面試展示指南

建議展示時間：7～10 分鐘。先講後端商業流程，再講 AI；不要把它介紹成單純的
聊天機器人。

## 1. 開場（30 秒）

> VoyageOps AI 是我把原本 Taipei Day Trip 專案重新設計成 API-first 旅遊 CRM
> 的作品。系統涵蓋會員、需求、行程、報價、訂單、付款、提醒、內部工作流程與
> Audit Log；AI 放在受控的 Provider Boundary 後面，所有重要寫入都需要人工審核。

## 2. 後端流程（2～3 分鐘）

依序展示會員、旅遊需求、行程、報價與訂單。說明三個設計選擇：

1. 報價使用不可變 Snapshot，避免後續修改行程時改到已送客戶的版本。
2. 訂單與付款使用 Idempotency Key，避免重送造成重複交易。
3. 狀態機拒絕不合法跳轉，並把重要變更寫入 Audit Log。

## 3. AI Agent 與 Human-in-the-loop（2～3 分鐘）

在 AI Copilot 輸入營運問題，展示 Tool Trace。強調 Agent 工具只有讀取權限；
若要求建立任務，系統產生 Proposal，而不是直接寫資料庫。

再展示 Proposal Review Queue：搜尋、狀態篩選、負責人、批次分流、24 小時 SLA、
過期保護，以及核准後才原子化建立 Task 與 Audit Log。

## 4. Reliability（1～2 分鐘）

展示營運提醒、Worker／Queue 狀態與 Integration Status。可以這樣說：

> MySQL 保存持久化 Job Ledger，Redis 只負責排程喚醒，因此 Redis 資料可以重建。
> Worker 支援 Lease、Exponential Backoff 和 Dead Letter。金流與 Email 目前是本機
> Mock Adapter，而且 Fail-closed；我不會把 Prototype 說成已串接正式供應商。

接著開 `/docs`、`/health/ready` 或 `/metrics`，說明 API Contract、Dependency
Readiness、Request ID、Latency 與自動測試。

## 5. 收尾（30 秒）

> 這個專案主要證明我能把 FastAPI、MySQL、Redis、Docker、背景工作、REST API、
> 測試與 AI Agent 組成可維護的系統。AI 負責建議與編排；權限、驗證、交易、
> Idempotency、Audit 和最終寫入仍由後端控制。

## 常見追問

### 這算 TDD 嗎？

不是每一個功能都嚴格先寫測試，所以不應宣稱完整 TDD。較準確的說法是：核心
Contract、狀態機、安全邊界與 Regression 行為都有自動測試；部分新功能採用
Test-first，整體是持續增加 Regression Coverage 的開發方式。

### AI 為什麼不能直接寫 CRM？

模型輸出具有不確定性。讀取錯誤只影響回答，但寫入錯誤會建立任務、改變營運狀態，
甚至導致對外動作。因此先轉成可追蹤、會過期、可指派的 Proposal，再由人核准。

### 為什麼 Redis 不是唯一 Queue？

若 Redis 是唯一紀錄，排程資料遺失後難以復原。這裡以 MySQL Job Ledger 保存狀態、
嘗試次數、Lease 與錯誤；Redis Sorted Set 只加速找出到期工作。

### 是否已串接正式金流或 Email？

沒有。專案實作的是 Provider Interface、Mock Adapter、Webhook／Idempotency／Audit
等整合邊界。正式 Adapter 需要供應商帳號、Credentials、法遵與部署環境，不能
把 Mock 測試宣稱為 Production Integration。
