# Provider benchmark report

## Data status

Partial-safe aggregation: missing values remain unavailable; client-observed TTFT is not server prefill timing.

## Run configuration

tb21-omp-electronhub-full-glm-5.2-dev-20260725-225552: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-212816: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-212924: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-213004: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-213612: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-214205: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-222507: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-kourier-full-qwen3.6-35b-20260727-224830: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-full-qwen3.6-35b-20260729-051711: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-full-qwen3.6-35b-20260729-162318: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-full-qwen3.6-35b-20260729-162754: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen-3.6-35b-20260727-222106: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen-3.6-35b-20260727-224525: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-20260727-224624: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-20260727-232628: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-20260728-005048: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-20260728-031827: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-20260728-033323: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-20260729-050330: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-213157: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-215435: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-220903: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-221242: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-221608: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-full-umans-glm-5.2-20260725-225552: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260727-222334: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260727-223200: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260728-040553: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260729-054017: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-glm-5.2-20260725-212816: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-smoke-umans-glm-5.2-20260725-212924: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-smoke-umans-glm-5.2-20260725-213004: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-smoke-umans-glm-5.2-20260725-213612: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-smoke-umans-glm-5.2-20260725-214205: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-smoke-umans-glm-5.2-20260725-222507: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-213157: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-215435: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-220903: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-221242: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-221608: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-232628: attempts=5, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260728-005048: attempts=1, retries=3, timeout multiplier=8.0, reasoning=True, max tokens=49152, context window=262144
tb21-omp-z-ai-full-glm-5.2-20260725-225552: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-z-ai-smoke-glm-5.2-20260725-212816: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-z-ai-smoke-glm-5.2-20260725-212924: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-z-ai-smoke-glm-5.2-20260725-213004: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-z-ai-smoke-glm-5.2-20260725-213612: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-z-ai-smoke-glm-5.2-20260725-214205: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable
tb21-omp-z-ai-smoke-glm-5.2-20260725-222507: attempts=1, retries=Unavailable, timeout multiplier=Unavailable, reasoning=Unavailable, max tokens=Unavailable, context window=Unavailable

## Provider summaries

### electronhub
- Requests: 1516
- Reported output tokens: 1252423
- Median client-observed TTFT: 6434.5 ms
- Weighted decode throughput: 353.27 reported tokens/s
- HTTP errors: 143

### kourier
- Requests: 4249
- Reported output tokens: 1926
- Median client-observed TTFT: 2723.0 ms
- Weighted decode throughput: 98.71 reported tokens/s
- HTTP errors: 343

### umans
- Requests: 10194
- Reported output tokens: 14723669
- Median client-observed TTFT: 2650.0 ms
- Weighted decode throughput: 289.46 reported tokens/s
- HTTP errors: 56

### z-ai
- Requests: 1670
- Reported output tokens: 1285849
- Median client-observed TTFT: 6847.0 ms
- Weighted decode throughput: 515.93 reported tokens/s
- HTTP errors: 0

## Run inventory

- tb21-omp-electronhub-full-glm-5.2-dev-20260725-225552 — electronhub; results 90/89
- tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-212816 — electronhub; results 0/3
- tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-212924 — electronhub; results 1/3
- tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-213004 — electronhub; results 4/3
- tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-213612 — electronhub; results 1/3
- tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-214205 — electronhub; results 4/3
- tb21-omp-electronhub-smoke-glm-5.2-dev-20260725-222507 — electronhub; results 4/3
- tb21-omp-kourier-full-qwen3.6-35b-20260727-224830 — kourier; results 13/89
- tb21-omp-kourier-full-qwen3.6-35b-20260729-051711 — kourier; results 90/89
- tb21-omp-kourier-full-qwen3.6-35b-20260729-162318 — kourier; results 1/89
- tb21-omp-kourier-full-qwen3.6-35b-20260729-162754 — kourier; results 1/89
- tb21-omp-kourier-smoke-qwen-3.6-35b-20260727-222106 — kourier; results 16/3
- tb21-omp-kourier-smoke-qwen-3.6-35b-20260727-224525 — kourier; results 1/3
- tb21-omp-kourier-smoke-qwen3.6-35b-20260727-224624 — kourier; results 2/3
- tb21-omp-kourier-smoke-qwen3.6-35b-20260727-232628 — kourier; results 14/3
- tb21-omp-kourier-smoke-qwen3.6-35b-20260728-005048 — kourier; results 4/3
- tb21-omp-kourier-smoke-qwen3.6-35b-20260728-031827 — kourier; results 4/3
- tb21-omp-kourier-smoke-qwen3.6-35b-20260728-033323 — kourier; results 3/3
- tb21-omp-kourier-smoke-qwen3.6-35b-20260729-050330 — kourier; results 1/3
- tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-213157 — kourier; results 16/3
- tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-215435 — kourier; results 16/3
- tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-220903 — kourier; results 5/3
- tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-221242 — kourier; results 15/3
- tb21-omp-kourier-smoke-qwen3.6-35b-a3b-20260727-221608 — kourier; results 16/3
- tb21-omp-umans-full-umans-glm-5.2-20260725-225552 — umans; results 84/89
- tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260727-222334 — umans; results 181/89
- tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260727-223200 — umans; results 9/89
- tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260728-040553 — umans; results 90/89
- tb21-omp-umans-full-umans-qwen3.6-35b-a3b-20260729-054017 — umans; results 86/89
- tb21-omp-umans-smoke-umans-glm-5.2-20260725-212816 — umans; results 0/3
- tb21-omp-umans-smoke-umans-glm-5.2-20260725-212924 — umans; results 1/3
- tb21-omp-umans-smoke-umans-glm-5.2-20260725-213004 — umans; results 4/3
- tb21-omp-umans-smoke-umans-glm-5.2-20260725-213612 — umans; results 1/3
- tb21-omp-umans-smoke-umans-glm-5.2-20260725-214205 — umans; results 4/3
- tb21-omp-umans-smoke-umans-glm-5.2-20260725-222507 — umans; results 4/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-213157 — umans; results 5/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-215435 — umans; results 16/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-220903 — umans; results 4/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-221242 — umans; results 4/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-221608 — umans; results 16/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260727-232628 — umans; results 2/3
- tb21-omp-umans-smoke-umans-qwen3.6-35b-a3b-20260728-005048 — umans; results 4/3
- tb21-omp-z-ai-full-glm-5.2-20260725-225552 — z-ai; results 86/89
- tb21-omp-z-ai-smoke-glm-5.2-20260725-212816 — z-ai; results 0/3
- tb21-omp-z-ai-smoke-glm-5.2-20260725-212924 — z-ai; results 1/3
- tb21-omp-z-ai-smoke-glm-5.2-20260725-213004 — z-ai; results 4/3
- tb21-omp-z-ai-smoke-glm-5.2-20260725-213612 — z-ai; results 1/3
- tb21-omp-z-ai-smoke-glm-5.2-20260725-214205 — z-ai; results 4/3
- tb21-omp-z-ai-smoke-glm-5.2-20260725-222507 — z-ai; results 4/3
