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
本機已保存訓練報告；adapter 壓縮檔雖在 Colab runtime 建立，內建瀏覽器下載尚未
驗證成功，不能把報告中的暫存 `adapter_path` 當成已保存的本機模型。

## 2026-10-11：獨立 CPU 模型 API 與 kind 部署

Qwen2.5-0.5B-Instruct 已實際部署在 Kubernetes Pod，使用 Linux ARM64 CPU／FP32。
首次完整比較因 HTTP 超時後仍生成而連鎖忙碌失敗：local 16/16、模型 API 1/16。
加入每次生成 30 秒的軟上限後重跑，模型 API 10/16、local 16/16；10 個 Agent
案例皆由指定模型完成，無 fallback，工具選擇 10/10。其餘 6 題因 JSON 截斷失敗。

平均每題 49.34 秒、p95 62.46 秒，包含多次生成與 JSON 修復；不是吞吐量測試。
因此保留 local 預設，不採用此 CPU 配置做互動 CRM 的主模型。這項結果證明
部署、評測與失敗處理流程；不證明主觀回答品質、GPU 精度效能或成本優勢。
不同模型大小與精度的舊 MLX 數據不能當作推論引擎效能的直接比較。
詳見 [模型 API 實測與限制](MODEL_API.md)。

## 2026-10-13：Base／QLoRA 的生成內容比較

免費 Colab T4 重新訓練 30 steps，使用同一 NF4 backbone 關閉／開啟 adapter，
以相同 12 個 held-out 合成提示、greedy decoding、512-token 上限比較。
新一輪 test loss 為 1.8404 → 1.0216；與 10/10 的舊實驗分開保存。

| 指標 | Base | Adapter |
|---|---:|---:|
| JSON schema | 12/12 | 12/12 |
| 人審旗標／既有關鍵詞／有限 canary 檢查 | 12/12 | 12/12 |
| 完整 deterministic label match | 0/12 | 0/12 |
| 平均每題延遲（含驗證／可能修復） | 8.29 秒 | 6.62 秒 |
| 輸出 tokens（全部 12 題） | 1,598 | 1,038 |

輸出較短伴隨延遲降低，不能宣稱推論引擎加速或客戶品質提升。內容檢視發現
adapter 的第 6–8 題聲稱「目前收到您的付款通知」，提示只提供待付款且尚待確認
的資訊。這個無根據的事件說法沒有被現有關鍵詞檢查捕捉。此檢視是事後助理
分析，不是全面自動化評分或人工標註。結論是**不採用此 adapter 作為已證明
改善品質的模型，維持 local 預設**。模型輸出仍須人工審核。

生成報告含每題 expected／actual 輸出、tokens、延遲、model revision、資料與
adapter hashes：`evals/followup-generation.colab-t4-2026-10-13.json`。
訓練報告：`evals/finetune.colab-t4-2026-10-13.json`；內容檢視另存
`evals/followup-generation.content-review-2026-10-13.json`。本次新 adapter 已取回
本機並校驗權重 hashes；10/10 的舊 adapter 並未恢復。權重不推送 GitHub。

這項實驗已完成生成比較，仍不能證明真實客戶品質、全面隱私安全或生產效能。
它和 CPU 0.5B 的 16-case benchmark 有不同模型、硬體、精度與測試集，不能直接
比較速度／準確率。HF PEFT adapter 未轉換成 MLX 格式，也未載入 K8s 的 0.5B 服務。
