# VoyageOps 模型選型紀錄（本機評測）

這份紀錄回答一個具體問題：對目前的 CRM 行程規劃、後續聯絡草稿與唯讀營運問答，
是否值得把預設的 deterministic provider 換成 Mac 本機的 Qwen 1.5B 4-bit？
資料來源是 [`evals/benchmark.mlx-m1.json`](../evals/benchmark.mlx-m1.json)。
這份歷史報告的 Privacy 指標只檢查提示中的測試聯絡資料；目前評測程式也會檢查模型
回覆，並在新報告標示 `privacy_check` 定義。要用新版隱私指標比較兩者，需在可使用
Metal 的 Mac 上重新執行 MLX 評測。這是測試資料中 email／電話的完全相符檢查，
不是通用個資偵測。

| 設定 | 通過案例 | Schema | Guardrail | Privacy | 工具選擇 | 平均延遲／案例 | P95 延遲 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Deterministic local | 16/16 | 100% | 100% | 100% | 10/10 | 2.54 ms | 6.59 ms |
| Qwen2.5-1.5B-Instruct-4bit，MLX | 15/16 | 93.75% | 93.75% | 93.75% | 10/10 | 4,563.49 ms | 14,889.61 ms |

在這 16 個固定案例上，Qwen 的工具選擇全對，但有一個後續聯絡草稿在一次 JSON 修復重試後
仍無法解析。評測把失敗案例的 Schema、Guardrail 與 Privacy 都記為未通過，所以上表的
93.75% **不代表觀察到個資外洩**。MLX 的延遲包含首次模型載入與修復重試；這是單次
M1 16 GB 執行，不是服務吞吐量或穩定的硬體對照測試。

**目前決策：**保留 deterministic provider 作為預設與安全回退。Qwen/MLX 保持為可選的
本機實驗設定，暫不以這份評測宣稱它能取代現有服務。這個選擇反映目前任務的正確性與
回應速度需求；如果後續出現 deterministic 規則無法處理的開放式需求，再用新增的真實
匿名化案例重新比較。

Token 用量只記錄 provider 實際回報的數字：這次 Qwen/MLX 共回報輸入 5,789、輸出
3,308 個 token；deterministic provider 沒有 token 用量，標為 `unavailable`。
本機推論沒有雲端 API 費用，但目前沒有量測 Mac 電力、硬體攤提或服務成本，不能推算
每次請求的成本。Gemini 沒有納入此表，因為這份已提交報告沒有實際 Gemini 結果。

下一個有意義的比較是跑 `scripts/train_followup_mlx.sh`：它會在 Apple Silicon 上做小型
量化 LoRA 練習，並把基礎模型與 adapter 對 12 筆保留的合成案例的結果寫入
`output/followup-adapter-comparison.json`。那份資料只驗證訓練流程；要判斷客戶場景的
改善，仍需獨立、人工審核且合法去識別的任務樣本。

2026-10-10 已在免費 Colab Tesla T4 完成 30 步 Hugging Face QLoRA 合成資料練習，
並保存[完整報告](../evals/finetune.colab-t4-2026-10-10.json)。模型為
`Qwen/Qwen2.5-1.5B-Instruct`，NF4 4-bit、LoRA rank 8；train／valid／test
各有 60／12／12 筆。保留測試集 loss 從 **1.8404 降至 1.0163**，train loss
為 1.3266。報告保留程式 commit、各資料 split 的 SHA-256 與套件版本，
Notebook 輸出也保留完整數字。

這驗證了資料準備、量化模型載入、LoRA 訓練與保留集 loss 比較的流程。
標籤仍來自同一套 deterministic 合成模板，因此 loss 下降只能反映對這批標籤的
擬合；尚未比較 adapter 生成內容的 Schema／Guardrail／任務品質，不能據此改變
目前模型選型。報告的 `precision` 是程式選擇的計算 dtype，此實驗沒有比較
不同精度的效能。全程未購買 Colab 方案或 compute units；成本沒有估算。
