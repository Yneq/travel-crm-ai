"""Compare base/QLoRA generations on identical synthetic held-out prompts.

Run only on an explicitly free CUDA runtime. No Hub upload or paid API.
"""
import argparse
import hashlib
import json
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_followup_adapter import load_records, evaluate_records
from services.mlx_provider import MlxRuntime


class CudaRuntime(MlxRuntime):
    def __init__(self, model_id, model, tokenizer, adapter_path, *, adapted, max_tokens):
        super().__init__(model_id, adapter_path=str(adapter_path) if adapted else None)
        self.name = f"hf-cuda:{model_id}"
        self.model = model
        self.tokenizer = tokenizer
        self.adapted = adapted
        self.max_tokens = max_tokens
        self.last_raw_output = None

    def generate(self, instruction, *, max_tokens=768):
        import torch
        inputs = self.tokenizer.apply_chat_template(
            [{'role': 'user', 'content': instruction}], tokenize=True,
            add_generation_prompt=True, return_dict=True, return_tensors='pt',
        ).to('cuda')
        count = inputs['input_ids'].shape[-1]
        if count > 4096:
            raise ValueError('Evaluation prompt exceeds 4096 tokens')
        with (nullcontext() if self.adapted else self.model.disable_adapter()):
            with torch.inference_mode():
                ids = self.model.generate(**inputs, do_sample=False,
                    max_new_tokens=min(max_tokens, self.max_tokens),
                    pad_token_id=self.tokenizer.eos_token_id)
        torch.cuda.synchronize()
        generated = ids[0][count:]
        previous = self.last_usage
        self.last_usage = SimpleNamespace(
            prompt_token_count=count + (previous.prompt_token_count if previous else 0),
            candidates_token_count=len(generated) + (previous.candidates_token_count if previous else 0),
            total_token_count=count + len(generated) + (previous.total_token_count if previous else 0))
        self.last_raw_output = self.tokenizer.decode(generated, skip_special_tokens=True)
        return self.last_raw_output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter-path', type=Path, required=True)
    parser.add_argument('--test-data', type=Path, default=ROOT/'finetune/followup/data/test.jsonl')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-tokens', type=int, default=512)
    args = parser.parse_args()
    if not 1 <= args.max_tokens <= 1024:
        parser.error('--max-tokens must be 1..1024')
    config_path = args.adapter_path/'adapter_config.json'
    if not config_path.is_file():
        parser.error('Trained PEFT adapter_config.json is required')
    records = load_records(args.test_data)
    import torch
    assert torch.cuda.is_available(), 'No free CUDA runtime; stop without upgrading.'
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import PeftModel
    config = json.loads(config_path.read_text())
    model_id = config['base_model_name_or_path']
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    base = AutoModelForCausalLM.from_pretrained(model_id, device_map={'': 0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=dtype,
            bnb_4bit_use_double_quant=True))
    model = PeftModel.from_pretrained(base, args.adapter_path).eval()
    model.config.use_cache = True
    runs = {}
    for label, adapted in [('base', False), ('adapted', True)]:
        provider = CudaRuntime(model_id, model, tokenizer, args.adapter_path,
                               adapted=adapted, max_tokens=args.max_tokens)
        provider.generate('只回答 OK。', max_tokens=8)  # warm-up excluded from case statistics
        runs[label] = evaluate_records(records, provider, include_outputs=True)
        print(label, runs[label]['metrics'], flush=True)
    report = {'task': 'synthetic_followup_json_generation',
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'runtime': 'transformers/peft CUDA',
        'gpu': torch.cuda.get_device_name(0), 'model_revision': getattr(base.config, '_commit_hash', None),
        'quantization': 'same NF4 4-bit backbone; adapter disabled/enabled',
        'compute_dtype': str(dtype), 'max_new_tokens': args.max_tokens,
        'test_sha256': hashlib.sha256(args.test_data.read_bytes()).hexdigest(),
        'adapter_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in args.adapter_path.glob('*') if p.suffix in ('.json', '.safetensors')},
        **runs,
        'limitations': ['Synthetic deterministic labels, not human-reviewed customer quality.',
            'Greedy generation and one JSON repair allowed identically for both variants.',
            'Latency includes generation, repair and validation; warm-up excluded; no throughput claim.',
            'Privacy checks only synthetic canaries; no general PII audit.',
            'Exact label match does not measure semantic usefulness.',
            'Cost not measured; no paid API or model upload.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('Saved comparison:', args.output, flush=True)


if __name__ == '__main__':
    main()
