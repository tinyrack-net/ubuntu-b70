# LLM engine benchmark

Client-observed OpenAI streaming results; values are medians unless noted.

## llama_cpp

- Run: `20260828T040452Z`
- Model: `/models/Qwen3.8-27B-UD-Q4_K_M.gguf`
- Context: 65536

| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |
| --- | ---: | ---: | ---: | ---: |
| pp128 | 560.67 | 0.00 | 228.30 | 0.00 |
| pp512 | 2205.17 | 0.00 | 232.18 | 0.00 |
| pp2048 | 8756.30 | 0.00 | 233.89 | 0.00 |
| tg128 | 138.00 | 21.12 | 463.76 | 47.35 |
| tg256 | 133.30 | 20.90 | 480.13 | 47.84 |

| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |
| ---: | ---: | ---: | ---: |
| 1 | 5 | 19.90 | 238.57 |
| 2 | 10 | 20.19 | 12893.35 |
| 4 | 20 | 20.19 | 38236.56 |

## vllm

- Run: `20260828T085955Z`
- Model: `Qwen3.8-27B`
- Context: 32768

| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |
| --- | ---: | ---: | ---: | ---: |
| pp128 | 919.65 | 0.00 | 139.18 | 0.00 |
| pp512 | 1855.24 | 0.00 | 275.97 | 0.00 |
| pp2048 | 8911.03 | 0.00 | 229.83 | 0.00 |
| tg128 | 733.92 | 32.73 | 87.20 | 30.55 |
| tg256 | 742.12 | 32.76 | 86.24 | 30.52 |

| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |
| ---: | ---: | ---: | ---: |
| 1 | 5 | 31.40 | 279.37 |
| 2 | 10 | 62.27 | 279.89 |
| 4 | 20 | 116.15 | 349.68 |
| 8 | 40 | 208.23 | 627.69 |
| 16 | 80 | 344.80 | 1272.30 |
