# Latest API TPS benchmark

- Run: `20260828T034312Z`
- Git: `23c88bb9a26925ef4ce93d199ab5fbde0d2c3f7c`
- Model: `Qwen3.8-27B-UD-Q4_K_M.gguf`
- Backend/context/parallel: `intel` / `65536` / `1`
- Raw result: [`20260828T034312Z-api.json`](results/20260828T034312Z-api.json)

| Case | Kind | N | Prompt t/s mean | Decode t/s mean | Wall ms median |
|---|---:|---:|---:|---:|---:|
| pp128 | prompt | 5 | 215.86 | 0.00 | 600.15 |
| pp512 | prompt | 5 | 602.92 | 0.00 | 857.05 |
| pp2048 | prompt | 5 | 685.09 | 0.00 | 3001.55 |
| tg128 | generation | 5 | 112.60 | 20.84 | 6669.31 |
| tg256 | generation | 5 | 112.57 | 20.76 | 12859.46 |
| chat128 | chat | 3 | 84.80 | 20.82 | 7366.67 |

Synthetic cases disable prompt caching. Chat cases use the OpenAI-compatible route and report actual generated token counts.
