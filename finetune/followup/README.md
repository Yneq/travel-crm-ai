# Synthetic follow-up fine-tuning exercise

Run `python scripts/build_followup_dataset.py` to regenerate the checked-in
`data/{train,valid,test}.jsonl` files and their SHA-256 manifest. The 84
examples are synthetic, balanced across three reminder types, and contain no
real traveler contact data. The label is the existing deterministic
`LocalFollowUpProvider` output. Prompts use the same instruction builder as the
MLX follow-up provider; train, validation, and test prompts are distinct. The
16-case AI regression fixtures are kept separate from this training set.

The dataset is deliberately small. It verifies the path from a task-specific
dataset through quantized LoRA training and held-out loss evaluation; it cannot
establish improved customer-facing quality. Compare the resulting adapter
against the existing benchmark before using it in a service.

On an Apple Silicon Mac, install `requirements-mlx-train.txt` into `.venv`, then
run `bash scripts/train_followup_mlx.sh`. It trains for 30 iterations with batch
size 1, masks the user prompt in the loss, and writes the adapter under ignored
`output/followup-adapters`. The script then evaluates loss on `test.jsonl`.
The base model is the same 4-bit Qwen used in the checked-in benchmark. MLX-LM
documents that LoRA training on a quantized model is QLoRA.
