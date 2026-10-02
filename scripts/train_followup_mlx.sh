#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_ID="${MLX_MODEL_ID:-mlx-community/Qwen2.5-1.5B-Instruct-4bit}"
DATA_DIR="${MLX_DATA_DIR:-finetune/followup/data}"
ADAPTER_DIR="${MLX_ADAPTER_DIR:-output/followup-adapters}"
export HF_HOME="${HF_HOME:-output/hf-cache}"

test -f "$DATA_DIR/train.jsonl"
test -f "$DATA_DIR/valid.jsonl"
test -f "$DATA_DIR/test.jsonl"
mkdir -p "$ADAPTER_DIR" "$HF_HOME"

.venv/bin/mlx_lm.lora \
  --model "$MODEL_ID" \
  --train \
  --data "$DATA_DIR" \
  --adapter-path "$ADAPTER_DIR" \
  --iters 30 \
  --batch-size 1 \
  --num-layers 4 \
  --mask-prompt \
  --max-seq-length 1024 \
  --steps-per-report 5 \
  --steps-per-eval 10 \
  --val-batches 4 \
  --save-every 30

.venv/bin/mlx_lm.lora \
  --model "$MODEL_ID" \
  --data "$DATA_DIR" \
  --adapter-path "$ADAPTER_DIR" \
  --test \
  --test-batches -1
