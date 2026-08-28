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

- Run: `20260828T060716Z`
- Model: `Qwen3.8-27B`
- Context: 32768

| Case | Prompt tok/s | Decode tok/s | TTFT ms | TPOT ms |
| --- | ---: | ---: | ---: | ---: |
| pp128 | 917.21 | 0.00 | 139.55 | 0.00 |
| pp512 | 1704.83 | 0.00 | 300.32 | 0.00 |
| pp2048 | 7566.10 | 0.00 | 270.68 | 0.00 |
| tg128 | 758.59 | 33.56 | 84.37 | 29.80 |
| tg256 | 759.58 | 33.46 | 84.26 | 29.89 |

| Concurrency | Requests | Aggregate output tok/s | Median TTFT ms |
| ---: | ---: | ---: | ---: |
| 1 | 5 | 32.11 | 282.29 |
| 2 | 10 | 60.19 | 423.22 |
| 4 | 20 | 108.11 | 1068.11 |
| 8 | 40 | 177.95 | 1520.42 |
