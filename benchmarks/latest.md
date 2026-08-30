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

- Run: `20260830T094217Z`
- Model: `Qwen3.8-27B`
- Context: 118784

| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |
| --- | ---: | ---: | ---: | ---: |
| pp128 | 659.37 | 0.00 | 194.13 | 0.00 |
| pp512 | 1285.81 | 0.00 | 398.19 | 0.00 |
| pp2048 | 1680.03 | 0.00 | 1219.02 | 0.00 |
| tg128 | 330.36 | 66.24 | 193.73 | 15.10 |
| tg256 | 562.92 | 63.56 | 113.69 | 15.73 |

| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |
| ---: | ---: | ---: | ---: |
| 1 | 5 | 59.15 | 357.78 |
| 2 | 10 | 111.20 | 393.59 |
| 4 | 20 | 203.72 | 456.68 |
| 8 | 40 | 361.83 | 958.08 |
