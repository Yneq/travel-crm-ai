# Independent Qwen CPU API

This optional service runs the actual open-source model inside a Linux container,
including on Apple Silicon kind. It uses CPU float32, not Apple Metal/CUDA.
Qwen2.5-0.5B-Instruct is a small deployment baseline, not a claim of customer-ready
quality or a newly released model. The model revision is pinned in the manifest.
Official reference: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct

## Deploy to an existing local cluster

```sh
docker build -f model_service/Dockerfile -t travel-crm-ai-model:cpu .
kind load docker-image travel-crm-ai-model:cpu --name voyageops
kubectl apply -k k8s/model-cpu
kubectl -n voyageops rollout status deployment/model-api --timeout=1800s
kubectl -n voyageops port-forward svc/model-api 18090:8090 --address=127.0.0.1
```

Select the correct kubeconfig/context first. Namespace `voyageops` must exist.
The initial startup downloads public weights into a 3Gi PVC; download/load time
is separate from warm HTTP generation latency. Removing the deployment does not
remove cached weights. Only local compute/network/disk are used; no paid API.

```sh
curl http://127.0.0.1:18090/health/ready
MODEL_API_URL=http://127.0.0.1:18090 python scripts/evaluate_ai.py \
  --target local --target model-api:Qwen/Qwen2.5-0.5B-Instruct \
  --output output/benchmark.model-api.json
```

The benchmark preserves the same structured prompts, validators, JSON repair,
and read-only tool contracts used by MLX, with HTTP inference replacing the
runtime. Failed JSON or a local fallback remains a failed model case. Token
usage counts all returned generation attempts, including repair. Report latency
includes HTTP, generation and repair; this is sequential case latency, not a
concurrency or throughput test. Regression checks are not subjective quality.

The server returns model/revision/device/dtype, token counts and generation time.
Requests are greedy, bounded to 4096 prompt tokens and 1024 generated tokens.
One generation is allowed at a time; concurrent calls get 429 rather than queue
unbounded work. There is no implicit retry or fallback within this API.

The service has no CRM database credentials/tools and does not execute model
output. Use it only on a trusted local cluster: there is no public authentication,
TLS, ingress or production load guarantee. The default CRM providers are unchanged;
the new HTTP adapter is an explicit benchmark target. Adapters support later
base/finetuned services, but no finetuned checkpoint is bundled or claimed tested.

`model_service/requirements.lock.txt` records the dependency versions resolved in
the verified image. The Dockerfile installs that lock file and pins the base-image digest. Save the
image ID with each benchmark result.

A soft 30-second generation budget (`GENERATION_MAX_SECONDS`) prevents an
orphaned long generation from occupying the worker after an HTTP timeout.
Transformers checks `max_time` between decoding iterations; it is not a hard
wall-clock deadline or request cancellation. A stopped response can be incomplete
JSON, which remains a failed schema case. This is an experimental latency budget,
not a measured customer SLA. JSON repair has its own generation budget, so total
case latency may exceed 30 seconds. HTTP client timeout remains 600 seconds.

To separate actual model observations from local fallback, annotate a saved report:

```sh
python scripts/analyze_benchmark.py output/benchmark.model-api.json
```

`provider_observations.observed_tool_selection_accuracy` excludes fallback and
unavailable responses; its sample count must accompany the rate. The older
`overall.tool_selection_accuracy` measures the returned system output and can
include deterministic fallback. A fallback still fails the case/provider match.

## Optional CRM connection

The CRM provider factories also accept `model-api`. Rebuild/redeploy the CRM image
before enabling this in an existing cluster. For a standalone local CRM process,
set `MODEL_API_URL=http://127.0.0.1:18090`; inside the cluster use
`MODEL_API_URL=http://model-api:8090`. Select the model with `MODEL_API_MODEL` and
opt in per workflow using `AI_PLANNING_PROVIDER`, `AI_FOLLOWUP_PROVIDER`, or
`AI_OPERATIONS_PROVIDER=model-api`. Existing defaults stay `local`.

Planning uses existing provider-error handling; follow-up and operations retain
their safe local fallback behavior. Model output still goes through existing
schema/guardrail checks and human review. This CPU configuration is an experiment,
so the local demo is deliberately not switched to it as its default provider.

## Verified on 2026-10-11 (Asia/Taipei)

The independent model actually ran in kind, using Linux ARM64, CPU FP32, two CPU
threads, a two-CPU / 3Gi memory limit, pinned Qwen weights and locked dependencies.

- Initial unbounded-generation experiment: local 16/16, model API 1/16. A 600s
  HTTP timeout left the model generating; subsequent requests were rejected busy.
  All ten Agent results fell back to local. This is an availability failure, not
  evidence of model tool accuracy.
- After adding a soft 30s per-generation budget: local 16/16, model API 10/16.
  All ten Agent cases used the actual model, selected tools correctly, and passed
  project contract checks; there were no fallbacks or HTTP timeouts.
- Three planning and three follow-up cases failed JSON parsing after generation
  was cut short, including repair attempts. Failed schema checks do not prove a
  privacy leak. Agent text can also be cut short; passing contracts is not a
  subjective quality assessment.
- End-to-end model case latency: mean 49.34s, p95 62.46s. Includes routing,
  synthesis and JSON repair, excludes startup. Usage reported for all 16 cases:
  7,250 input / 894 output / 8,144 total tokens. No cost is estimated.
- Live short-output smoke test: 2.30s for two output tokens. A separate long
  response stopped in 30.51s and released the worker. These are payload-specific
  checks, not general response-time claims.
- Python suite: 106 tests passed. CRM /health/live, /health/ready, /metrics and
  /admin returned 200 after deployment; this is not a full authenticated UI test.

Evidence: `evals/benchmark.model-api-cpu-2026-10-11.json`,
`evals/benchmark.model-api-cpu-bounded-2026-10-11.json`, and the matching
`evals/deployment.model-api-cpu*.json` reports. The application defaults remain
local. The CPU configuration does not meet an interactive CRM latency target and
is retained as a reproducible deployment/selection experiment. Do not compare
these timings directly with the historical 1.5B MLX run: model size, precision,
runtime and hardware differ. Base/finetuned generated-content comparison remains
future work; the Colab adapter is not bundled into this service.
