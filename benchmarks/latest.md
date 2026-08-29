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

- Run: `20260829T013648Z`
- Model: `Qwen3.8-27B`
- Context: 32768

| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |
| --- | ---: | ---: | ---: | ---: |
| pp128 | 740.11 | 0.00 | 172.95 | 0.00 |
| pp512 | 1306.85 | 0.00 | 391.78 | 0.00 |
| pp2048 | 1727.47 | 0.00 | 1185.55 | 0.00 |
| tg128 | 560.05 | 76.75 | 114.28 | 13.03 |
| tg256 | 498.93 | 76.82 | 128.27 | 13.02 |

| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |
| ---: | ---: | ---: | ---: |
| 1 | 5 | 68.68 | 347.69 |
| 2 | 10 | 135.53 | 351.88 |
| 4 | 20 | 234.95 | 495.68 |
