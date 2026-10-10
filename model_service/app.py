"""Single-worker, bounded CPU inference API for local Kubernetes experiments."""
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL = os.getenv("MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
REVISION = os.getenv("MODEL_REVISION", "7ae557604adf67be50417f59c2c2f167def9a775")
GENERATION_MAX_SECONDS = float(os.getenv("GENERATION_MAX_SECONDS", "30"))
if not 1 <= GENERATION_MAX_SECONDS <= 300:
    raise ValueError("GENERATION_MAX_SECONDS must be between 1 and 300")
lock = threading.Lock()
runtime = {}


@asynccontextmanager
async def lifespan(app):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.set_num_threads(int(os.getenv("CPU_THREADS", "2")))
    started = time.perf_counter()
    runtime["tokenizer"] = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
    runtime["model"] = AutoModelForCausalLM.from_pretrained(
        MODEL, revision=REVISION, torch_dtype=torch.float32,
        use_safetensors=True, trust_remote_code=False,
    ).to("cpu").eval()
    runtime["load_ms"] = round((time.perf_counter() - started) * 1000, 2)
    yield
    runtime.clear()


app = FastAPI(title="VoyageOps CPU Model API", lifespan=lifespan)


class GenerationRequest(BaseModel):
    model: str
    instruction: str = Field(min_length=1, max_length=24000)
    max_tokens: int = Field(default=256, ge=1, le=1024)


@app.get("/health/ready")
def ready():
    if "model" not in runtime:
        raise HTTPException(503, "Model not loaded")
    return {"status": "ready", "model": MODEL, "revision": REVISION,
            "device": "cpu", "dtype": "float32", "load_ms": runtime["load_ms"],
            "generation_budget_seconds": GENERATION_MAX_SECONDS, "busy": lock.locked()}


@app.post("/v1/generate")
def generate(request: GenerationRequest):
    if request.model != MODEL:
        raise HTTPException(400, "Requested model is not served")
    if not lock.acquire(blocking=False):
        raise HTTPException(429, "Model busy; retry later")
    try:
        import torch
        tokenizer = runtime["tokenizer"]
        inputs = tokenizer.apply_chat_template(
            [{"role": "user", "content": request.instruction}],
            add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt",
        )
        prompt_tokens = inputs["input_ids"].shape[-1]
        if prompt_tokens > 4096:
            raise HTTPException(413, "Prompt exceeds 4096 tokens")
        started = time.perf_counter()
        with torch.inference_mode():
            ids = runtime["model"].generate(**inputs, max_new_tokens=request.max_tokens,
                                             do_sample=False, max_time=GENERATION_MAX_SECONDS)
        generated = ids[0][prompt_tokens:]
        return {"provider": "model-api", "model": MODEL, "revision": REVISION,
                "device": "cpu", "dtype": "float32",
                "text": tokenizer.decode(generated, skip_special_tokens=True),
                "usage": {"input_tokens": prompt_tokens, "output_tokens": len(generated),
                          "total_tokens": prompt_tokens + len(generated)},
                "generation_budget_seconds": GENERATION_MAX_SECONDS,
                "generation_ms": round((time.perf_counter() - started) * 1000, 2)}
    finally:
        lock.release()
