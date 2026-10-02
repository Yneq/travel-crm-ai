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
It also compares the base model and trained adapter on the same 12 held-out
synthetic examples, writing `output/followup-adapter-comparison.json` with
schema, human-review, privacy, unsafe-claim, exact-label-match, latency, and
reported token counts. Compare those two columns before making any claim about
the adapter. Training examples and this test set are disjoint, but their labels
share the same deterministic template source.
The base model is the same 4-bit Qwen used in the checked-in benchmark. MLX-LM
documents that LoRA training on a quantized model is QLoRA.

For an optional **free Colab CUDA GPU**, use
[`notebooks/colab_qlora_followup.ipynb`](../../notebooks/colab_qlora_followup.ipynb).
If the latest branch has not been pushed to GitHub, the notebook asks you to
select the local `travel-crm-ai-mac-stages.bundle` file and imports it into its
temporary runtime. This uses Hugging Face's original
`Qwen/Qwen2.5-1.5B-Instruct`, not the MLX checkpoint; adapters from the two
runtimes are not interchangeable. The notebook stops if no CUDA GPU is
available, installs only optional CUDA dependencies, and calls
`scripts/train_followup_cuda.py`. It compares held-out loss before and after
30 QLoRA steps and writes a local report. Do not select a paid Colab plan or
purchase compute units for this exercise. Free GPU allocation is not
guaranteed. No adapter is pushed to a model hub.
