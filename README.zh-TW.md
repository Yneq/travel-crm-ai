# VoyageOps AI

[English](README.md) | **繁體中文**

VoyageOps AI 是一套 API-first 的高端旅遊 CRM 與營運管理平台，由原本的
Taipei Day Trip 訂購專案演進而來。系統先建立可靠的後端合約與營運資料模型，
再導入模型驅動的 AI 自動化。

## 目前完成範圍

- 使用 bcrypt 密碼雜湊與 JWT Bearer Token 的員工驗證
- `admin`、`advisor`、`finance` 角色與權限模型
- 會員資料、負責顧問與旅遊偏好管理
- 旅遊需求建立與完整生命週期管理
- 版本化行程與可計價的行程項目
- 不可變報價快照與報價核准流程
- 由報價快照產生可下載的繁體中文 PDF
- 具 Idempotency 保護的訂單建立與付款嘗試
- 具簽章驗證及防重放能力的付款 Webhook 與本機 MockPay Adapter
- 明確的訂單／付款狀態機與 Audit Trail
- LangGraph 旅遊規劃流程：需求摘要、缺漏偵測、草稿產生與 Guardrail
- AI 草稿須經人工審核，核准後才能建立可編輯行程
- 可選用 Gemini 3.8 Flash，透過 Pydantic Structured Output 與隱私 Allowlist
  控制輸出及傳送欄位；預設仍可使用本機規劃器
- 內部任務指派與狀態管理
- 營運提醒中心：偵測即將到期任務、待付款訂單與即將出發行程，並支援防重複與人工處理
- AI Follow-up Copilot：產生內部摘要、建議步驟與可編輯的旅客聯絡草稿；核准不會自動寄送
- 版本化通訊草稿：編輯後撤銷核准，並提供具 Idempotency 的本機 Mock Email
- 具版本的 6 案例 AI Regression Set：評估 Schema、Guardrail、隱私、危險營運宣稱與延遲
- CRM 寫入操作的 Audit Log
- Trips、Quotes、Orders、Payments、Documents、Reminders、AI Runs 與
  第三方 Integration Events 的資料庫結構
- 獨立 Background Worker：Redis 排程、MySQL 恢復、指數退避重試與 Dead Letter
- 使用 Docker Compose 建立本機 MySQL、Redis、API 與 Worker 環境
- `/docs` OpenAPI 文件
- `/admin` 瀏覽器營運管理介面

原始景點、訂購、付款與靜態前端程式仍保留在 repository，作為系統演進參考；
新的 `app.py` 只提供 VoyageOps API 與管理介面。

## REST API

### 身分驗證

| 操作 | Method | Endpoint |
|---|---:|---|
| 建立第一位管理員 | `POST` | `/api/auth/register` |
| 登入並取得 Bearer Token | `POST` | `/api/auth/login` |
| 取得目前登入員工 | `GET` | `/api/users/me` |
| 建立員工帳號（限管理員） | `POST` | `/api/staff-users` |

登入使用 `POST`，因為這個請求會提交帳號密碼並建立驗證結果。舊系統的 S3
Presigned URL 上傳保留 `PUT`，因為該請求是在寫入 URL 所指定的物件。

第一位管理員建立後，Bootstrap Registration 便會關閉。第一個帳號會取得
`admin` 角色，後續員工帳號只能由已登入的管理員建立。

### CRM 與營運流程

| 資源 | Method | Endpoint |
|---|---:|---|
| 會員列表／建立會員 | `GET`, `POST` | `/api/members` |
| 會員資料 | `GET`, `PATCH` | `/api/members/{member_id}` |
| 旅遊需求列表／建立需求 | `GET`, `POST` | `/api/travel-requests` |
| 旅遊需求 | `GET`, `PATCH` | `/api/travel-requests/{request_id}` |
| 任務列表／建立任務 | `GET`, `POST` | `/api/tasks` |
| 任務 | `PATCH` | `/api/tasks/{task_id}` |
| 行程列表 | `GET` | `/api/trips` |
| 行程 | `GET`, `PATCH` | `/api/trips/{trip_id}` |
| 由需求建立行程 | `POST` | `/api/travel-requests/{request_id}/trips` |
| 建立行程項目 | `POST` | `/api/trips/{trip_id}/items` |
| 行程項目 | `PATCH`, `DELETE` | `/api/trip-items/{item_id}` |
| 報價列表 | `GET` | `/api/quotes` |
| 建立報價快照 | `POST` | `/api/trips/{trip_id}/quotes` |
| 報價 | `GET`, `PATCH` | `/api/quotes/{quote_id}` |
| 下載已核准報價 PDF | `GET` | `/api/quotes/{quote_id}/documents/proposal.pdf` |
| 由已核准報價建立訂單 | `POST` | `/api/quotes/{quote_id}/orders` |
| 訂單列表 | `GET` | `/api/orders` |
| 訂單 | `GET` | `/api/orders/{order_id}` |
| 發起付款 | `POST` | `/api/orders/{order_id}/payments` |
| 付款紀錄 | `GET` | `/api/orders/{order_id}/payments` |
| 模擬 MockPay 結果（限本機管理員） | `POST` | `/api/payments/{payment_id}/simulate` |
| 付款 Webhook | `POST` | `/api/webhooks/payments/{provider}` |
| 產生 AI 行程草稿 | `POST` | `/api/travel-requests/{request_id}/ai-plans` |
| AI 規劃歷史 | `GET` | `/api/travel-requests/{request_id}/ai-plans` |
| AI 規劃結果 | `GET` | `/api/ai-plans/{run_id}` |
| 核准或退回 AI 草稿 | `POST` | `/api/ai-plans/{run_id}/review` |
| 營運提醒列表 | `GET` | `/api/reminders` |
| 掃描目前營運風險 | `POST` | `/api/reminders/scan` |
| 將提醒標記為已處理或略過 | `PATCH` | `/api/reminders/{reminder_id}` |
| 產生 AI 跟進草稿 | `POST` | `/api/reminders/{reminder_id}/ai-draft` |
| 核准或退回跟進草稿 | `POST` | `/api/reminders/{reminder_id}/ai-draft/review` |
| 背景工作紀錄 | `GET` | `/api/operations/jobs` |
| Worker 與 Queue 狀態 | `GET` | `/api/operations/worker/status` |
| 重新排程 Dead Letter（限管理員） | `POST` | `/api/operations/jobs/{job_id}/retry` |
| 通訊草稿列表 | `GET` | `/api/communication-drafts` |
| 由已核准 AI 輸出建立可編輯草稿 | `POST` | `/api/reminders/{reminder_id}/communication-draft` |
| 編輯通訊內容並撤銷舊核准 | `PATCH` | `/api/communication-drafts/{draft_id}` |
| 核准通訊草稿 | `POST` | `/api/communication-drafts/{draft_id}/approve` |
| 執行具 Idempotency 的 Mock Send | `POST` | `/api/communication-drafts/{draft_id}/send` |

寫入 CRM 資料需要 `admin` 或 `advisor` 角色。已登入的 `finance` 使用者可以
讀取 CRM 資料，但不能修改。

## Workflow 規則

旅遊需求使用明確的狀態機：

```text
new → qualified → planning → proposal_ready → client_review
                                                ↓
                                             approved → booked → completed
```

支援的階段可以轉換為 `cancelled`；例如 `new → booked` 這種不合法的跳轉會
回傳 HTTP `409 Conflict`。任務同樣使用受控的 `open`、`in_progress`、
`completed` 與 `cancelled` 狀態轉換。

行程必須經過 `draft → review → confirmed`。報價使用
`draft → pending_approval → approved/rejected`，且只有 `admin` 或 `finance`
可以核准或退回。建立報價時，系統會將當下行程項目複製到 `quote_items`，
因此後續編輯行程只會建立新版本，不會改寫歷史報價。

建立訂單或付款時必須提供 `Idempotency-Key` Header。重送相同 Key 會取得原本
的 Resource；不同 Key 也不能替同一報價建立第二張訂單。同一筆訂單一次只能有
一個處理中的付款，付款失敗後可使用新的 Key 安全重試。

`MockPay` 是本機整合 Adapter，不是真實金流。Webhook 使用 HMAC-SHA256
`X-Webhook-Signature` 驗證簽章，依 Provider Event ID 防止重複處理，並忽略
付款成功後才抵達的過期失敗事件。未來可替換成真實 Provider，同時維持既有的
訂單與付款 API Contract。

營運提醒掃描會把可信任的 CRM 狀態轉成內部待辦：24 小時內到期的任務、建立
超過 24 小時仍待付款的訂單，以及 14 天內出發且已核准或預訂的旅程。每筆提醒
都有唯一 Deduplication Key，重複掃描不會重複建立。系統不會自動聯絡旅客；
必須由 `admin` 或 `advisor` 人工選擇「已處理」或「略過」，並將結果寫入 Audit Trail。

## AI 旅遊規劃流程

LangGraph 規劃流程包含四個明確節點：

```text
prepare_privacy_safe_context → identify_missing_information
→ generate_structured_plan → quality_guardrail
```

每次結果都會先儲存為 `awaiting_review`。人工核准後，系統才會在同一筆資料庫
Transaction 中建立一般行程並把建議項目寫入 `trip_items`；退回則不會修改 CRM
或行程資料。兩種操作都不會自動建立報價、訂單或付款。

預設的 `local-planner` 是 Deterministic，不會呼叫外部 LLM，也不會宣稱價格、
選擇供應商或檢查庫存。它提供可安全測試的本機流程與 Provider Boundary，未來
替換模型時不必改動審核 API。送入 AI 的 Context 會排除會員 Email 與電話，
只保留規劃行程所需資料。

### 啟用 Gemini 免費額度 Provider

在 Google AI Studio 建立 Gemini Developer API Key，然後把以下設定放入專案
`.env`；請勿提交真實 Key：

```dotenv
AI_PLANNING_PROVIDER=gemini
GEMINI_API_KEY=replace-with-your-key
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash-lite
AI_PROVIDER_TIMEOUT_MS=20000
AI_PROVIDER_MAX_RETRIES=2
AI_PROVIDER_MAX_OUTPUT_TOKENS=8192
```

只重建 API Service 即可套用環境設定：

```bash
docker compose up -d --no-build --force-recreate api
```

Provider 每次嘗試只送出一個 Structured Output 請求。遇到暫時性的 `429` 或
`5xx` 時，最多以 Exponential Backoff 重試兩次。Primary Model 是
`gemini-3.8-flash`；若重試後仍失敗，或輸出無法通過結構驗證，則改用
`gemini-3.5-flash-lite`，並記錄實際產生草稿的模型。

隱私 Allowlist 只會傳送旅客姓名／等級／Locale、行程資訊與旅遊偏好，不會傳送
Email 或電話。免費額度可能允許 Google 使用提交內容改善產品，因此測試時不可
使用真實客戶資料，上線前也必須重新檢查資料處理條款。

## AI Follow-up Copilot

待處理的提醒可以產生一份具 Idempotency 保護的跟進草稿，內容包含內部摘要、
建議步驟，以及可由顧問修改的旅客聯絡文字。本機 Provider 的輸出可重現；設定
`AI_FOLLOWUP_PROVIDER=gemini` 時會使用 Gemini Structured Output。若未設定此
變數，則會沿用 `AI_PLANNING_PROVIDER`。

送到外部模型的 Allowlist 只包含會員姓名、等級、語系，以及提醒類型、原因、
嚴重度和建議動作；不包含 Email、電話、完整付款紀錄或無關的 CRM 備註。所有
輸出都標示 `requires_human_review`。核准只代表草稿可供顧問使用，不會寄送 Email、
SMS 或任何其他旅客通知。外部模型重試後仍無法使用時，流程會產生清楚標示的
本機 Fallback 草稿，避免營運工作完全中斷。

## 通訊草稿核准流程

已核准的 AI Follow-up 可以建立另一份獨立版本化的通訊草稿：

```text
AI 輸出核准 → 可編輯通訊草稿 → 寄送核准 → Mock Send
```

修改主旨或內容會增加版本並撤銷先前的寄送核准。`draft` 不能直接寄送，`sent`
紀錄也不能再編輯。Mock Send 必須提供 `Idempotency-Key`；重送相同 Key 會取得
原結果，不同 Key 也不能讓同一草稿寄送兩次。`MockEmailProvider` 不會建立任何
網路連線，只保存本機模擬收據，也不會使用真實 Email 地址。

## AI Regression Evaluation

執行不會呼叫外部 API、可重現的本機 Baseline：

```bash
python scripts/evaluate_ai.py --provider local --output output/ai-eval-local.json
```

Repository 內的 [`evals/baseline.local.json`](evals/baseline.local.json) 保存第一份
結果：**6/6 案例通過**，Schema、Guardrail、Privacy 與明確 Claim Safety 檢查皆為
100%。Fixtures 包含 3 個行程規劃與 3 個 Follow-up 情境。這個結果只證明已定義的
Contract，不代表主觀行程品質、即時供應商資訊或 Production Network 效能。

Gemini 評估會呼叫外部服務，因此必須明確加入 Opt-in 參數：

```bash
python scripts/evaluate_ai.py --provider gemini --allow-live-api \
  --output output/ai-eval-gemini.json
```

## Background Worker 與 Retry Queue

`worker` Service 會依設定的時間區段建立一筆具 Idempotency 保護的提醒掃描工作。
MySQL `integration_events` 是持久化 Job Ledger；Redis Sorted Set 只保存執行時間。
Worker 啟動及輪詢時會從 MySQL 恢復已到期的 `scheduled` 或 `retrying` 工作，
因此 Redis 重啟不會讓工作的 Source of Truth 消失。

Worker Claim 工作時會取得 Processing Lease；如果 Worker 在完成前停止，租約逾時
會把工作轉回 `retrying`，避免永遠卡在 `processing`。

失敗工作使用有上限的 Exponential Backoff。超過 `WORKER_MAX_ATTEMPTS` 後會進入
`dead_letter`，必須由已登入的管理員重新排程。Worker 寫入 Reminder Audit Log
時使用空的 System Actor，不會冒充任何員工帳號。

## 本機執行

若要在容器外執行 API，先複製環境設定範例：

```bash
cp .env.example .env
```

啟動完整本機環境：

```bash
docker compose up --build
```

系統會建立 `travel_crm` MySQL Database、依序套用 SQL Migrations，並啟動
Redis、FastAPI Service 與 Background Worker。如果 Docker Hub 暫時連線逾時，但本機已有 API Image，
可以使用 `docker compose up -d --no-build`。

Docker Compose 在開發環境使用 Uvicorn Reload Mode，Python 程式變更後會自動
載入；Production Deployment 應關閉 `--reload`。

- API：<http://localhost:8080>
- Admin Dashboard：<http://localhost:8080/admin>
- Swagger UI：<http://localhost:8080/docs>
- Health Check：<http://localhost:8080/health>

Migration Runner 會把每個檔案的 Checksum 寫入 `schema_migrations`，因此既有
Volume 可直接取得新 Migration，不需要刪除本機資料。只有刻意重設所有資料時，
才應移除專案 Volume。

## 測試

```bash
python -m unittest discover -v tests
```

目前測試涵蓋 REST Route Contract、Health／OpenAPI、密碼雜湊、JWT Round Trip、
前端驗證 Endpoint、Payment Provider、PDF 產生、Schema Invariant，以及合法與
不合法的 Workflow Transition。提醒測試另外涵蓋規則輸出、防重複 Schema、
API 暴露與人工審核的終止狀態。

目前共通過 **45 項自動測試**。

## 下一階段

1. 擴充 Evaluation Fixtures，並比較不同 Model／Prompt 版本
2. 加入角色分離的核准政策與通訊 Template 歷史
3. 正式通訊／Payment Provider Adapter、Monitoring 與 Secret Management
