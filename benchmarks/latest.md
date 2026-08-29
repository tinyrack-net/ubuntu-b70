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

- Run: `20260829T034121Z`
- Model: `Qwen3.8-27B`
- Context: 32768

| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |
| --- | ---: | ---: | ---: | ---: |
| pp128 | 660.57 | 0.00 | 193.77 | 0.00 |
| pp512 | 1282.91 | 0.00 | 399.09 | 0.00 |
| pp2048 | 1684.62 | 0.00 | 1215.70 | 0.00 |
| tg128 | 470.27 | 77.20 | 136.09 | 12.95 |
| tg256 | 452.23 | 77.17 | 141.52 | 12.96 |

| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |
| ---: | ---: | ---: | ---: |
| 1 | 5 | 68.81 | 382.19 |
| 2 | 10 | 136.14 | 350.74 |
| 4 | 20 | 227.45 | 469.00 |
| 8 | 40 | 376.74 | 984.07 |
