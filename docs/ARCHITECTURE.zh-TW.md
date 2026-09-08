# VoyageOps AI 系統架構

[English](ARCHITECTURE.md)

VoyageOps AI 是一套 API-first 高端旅遊 CRM Prototype，重點是展示後端系統如何
安全地加入 AI 協作，同時避免模型未經人工核准就修改商業資料或執行外部動作。

## 執行元件

```text
瀏覽器 Admin UI
       |
       v
FastAPI REST API -----> MySQL（System of Record）
       |                    - CRM 與行程資料
       |                    - 不可變報價快照
       |                    - AI Run 與 Proposal
       |                    - Audit 與 Job Ledger
       |
       +--------------> Redis（排程喚醒索引）
       |                         |
       |                         v
       |                  Background Worker
       |
       +--------------> Local／Gemini AI Provider Boundary
       |
       +--------------> MockPay／Mock Email Adapter
                         （僅限本機、Fail-closed）
```

MySQL 是權威資料來源。Redis 只保存可重建的排程資訊；即使 Redis 資料遺失，
Worker 仍可從 MySQL 的持久化 Job Ledger 恢復可執行工作。

## 重要流程

### 報價到付款

```text
行程 -> 不可變報價快照 -> 人工核准 -> Idempotent 訂單
     -> 付款嘗試 -> 簽章且防重放的 Webhook -> 狀態轉換
```

Repository 使用本機 MockPay Adapter，展示 Provider Contract、Webhook 驗證、
Idempotency 與 Audit 流程，但不會連線到正式金流。

### AI 行程規劃

```text
旅遊需求 -> LangGraph Workflow -> Structured Draft + Guardrails
         -> 人工審核 -> 可編輯行程
```

只有 Allowlist 欄位可通過 Provider Boundary；模型輸出必須符合 Pydantic Schema，
也不能直接發布行程。

### CRM Operations Agent

```text
使用者需求 -> Intent Routing -> 唯讀工具 -> 回答 + Trace
                                      |
                                      v
                              選擇性寫入 Proposal
                                      |
                          指派 + SLA + 人工審核
                                      |
                              原子化 Task + Audit 寫入
```

Agent 工具本身維持唯讀。需要寫入 CRM 時，只能建立具版本與到期時間的 Proposal；
合格審核者核准後，Repository 才會建立 Task。過期、來源已變更或重複執行都會被拒絕。

### 營運提醒與通訊

```text
排程掃描 -> 防重複提醒 -> AI 跟進建議
         -> 人工核准的可編輯草稿 -> Maker-checker 核准
         -> Idempotent 本機 Mock Email 收據
```

Proposal SLA 也接入相同排程：即將超時的待審提案會產生 High 或 Urgent 提醒，
並以穩定 Deduplication Key 防止重複建立。

## 可靠性與安全邊界

- Resource-oriented REST Endpoint 與明確狀態機會拒絕不合法轉換。
- Idempotency Key 保護訂單、付款、Job、草稿與寄送流程。
- JWT 授權會重新查詢員工目前的角色與啟用狀態。
- Audit API 會遞迴遮蔽 Credentials 與 Secrets。
- Request Middleware 提供 Correlation ID、處理時間、Structured Log 與
  Route-level Prometheus Counter。
- `/health/live` 檢查 Process；`/health/ready` 檢查 MySQL 與 Redis。
- 外部金流與寄信預設停用，狀態由 `/api/operations/integrations/status` 明確揭露。

## Production 邊界

這是作品集等級的本機 Prototype，不是已正式營運的旅遊平台。正式上線仍需要真實
Provider Adapter、環境別 Secret Management、Infrastructure Monitoring／Alert、
資料保存與隱私審查、備份及部署強化。這些會明確列為邊界，不宣稱為既有正式經驗。
