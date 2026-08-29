# 단일 요청 TPS 조사 결과 (2026-08-28)

## 결론

운영 체크포인트 `abihsoro/Qwen3.8-27B-AWQ-INT4`를 유지하고
`max-num-seqs=4`, context 32768, KV cache `auto`, XPU Graph를 사용한다.
`RedHatAI/Qwen3.8-27B-INT4`는 MTP 비활성 상태에서 유의미한 TPS 이득이 없었고,
MTP 활성 상태는 vLLM XPU v0.28.0 엔진을 중단시켰다. 조사 결과에 따른 체크포인트나
KV cache 변경은 운영 기본값에 반영하지 않았다.

## 고정 조건

- 이미지: `vllm/vllm-openai-xpu:v0.28.0@sha256:d3e9c5f146a8251c7489107e6353cf512fcd1bf14a16cab17148125a62a537c8`
- 후보 revision: `2fb0debc365fb6c1683d7d3ad7722470919627a8`
- 후보 `model.safetensors`: `f078f51aed0c1dba613c1759487004ee06aba1a290606b6be125f59ab710959e`
- 후보 `model_mtp.safetensors`: `1d8268aa85ace093a561e3e7b63b9d390dac1cd55a90cd55b5ec509c3c9da9fe`
- GPU1, port 8081, context 32768, `max-num-seqs=4`, XPU Graph
- C1은 5개 요청을 3라운드, C2/C4는 각각 10/20개 요청을 3라운드 실행한 median이다.
- tg128/tg256은 각각 5회 측정한 decode TPS median이다.

## 측정 결과

| 구성 | tg128 | tg256 | C1 TPS | C1 변화 | C4 TPS | C4 변화 | C4 TTFT | TTFT 변화 | 판정 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 현재 체크포인트, KV auto | 32.719 | 32.611 | 31.275 | 기준 | 105.273 | 기준 | 1107.96 ms | 기준 | 유지 |
| RedHat INT4, MTP off, KV auto | 32.728 | 32.617 | 31.305 | +0.097% | 105.048 | -0.214% | 1081.32 ms | -2.404% | 실질 이득 없음 |
| RedHat INT4, MTP off, KV fp8 | 32.409 | 32.268 | 30.889 | -1.233% | 104.009 | -1.201% | 1098.67 ms | -0.839% | 탈락 |
| RedHat INT4, MTP 1 | - | - | - | - | - | - | - | - | 엔진 중단, 탈락 |
| RedHat INT4, MTP 2/3 | - | - | - | - | - | - | - | - | 공통 실패 경로로 미실행 |
| RedHat INT4, Triton attention | - | - | - | - | - | - | - | - | XPU가 무시하고 FlashAttention 선택 |

원시 결과:

- 현재 체크포인트: `results/20260828T131345Z-vllm-openai.json`
- RedHat MTP off / KV auto: `results/20260828T134649Z-vllm-openai.json`
- RedHat MTP off / KV fp8: `results/20260828T140158Z-vllm-openai.json`

## 실패 및 기능 검증

MTP 1은 첫 warm-up 요청에서
`vllm/v1/worker/mamba_utils.py::_populate_metadata`가 XPU state pointer를 정수 배열에
기록하는 과정에서 `ValueError: Overflow when unpacking long long`으로 EngineCore를
종료했다. speculative token 수와 무관한 공통 초기 요청 경로이므로 MTP 2/3은 같은
장애를 반복하지 않았다. acceptance metric을 만들기 전에 엔진이 종료되어 MTP 출력
동등성 및 acceptance length는 측정할 수 없었고, 선정 조건에 따라 즉시 탈락시켰다.

`VLLM_ATTENTION_BACKEND=TRITON_ATTN`은 컨테이너 환경에 반영됐지만 XPU 런타임은
`AttentionBackendEnum.FLASH_ATTN`, FlashAttention v2를 선택했다. 실제 backend가
기준 구성과 같아 중복 벤치마크를 생략했다.

MTP-off 후보는 health, `/v1/models`, 한국어, 코드, required tool call, 장문 context
요청을 처리했다. 다만 장문 응답 본문에 thinking 과정이 노출됐으며, 체크포인트 교체를
정당화할 성능 이득도 없었다. 모든 완료된 성능 측정에서 OOM, 컨테이너 재시작은 없었다.
실험 중 GPU0 운영 컨테이너의 시작 시각은 `2026-08-28T08:56:06.742898693Z`로
유지되어 재시작되지 않았다.

## 선정 판정

후보 MTP-off는 수치상 C1이 0.097% 높고 C4/TTFT 허용 기준을 만족하지만, 반복 측정
노이즈 수준의 차이이며 tg128/tg256도 사실상 동일하다. FP8은 KV 용량을 116,825에서
207,530 tokens로 늘렸지만 C1과 C4 TPS를 모두 낮췄다. 따라서 합격 후보 없음으로
판정하고 현재 체크포인트를 유지한다. MTP는 vLLM XPU의 pointer overflow가 수정된
버전에서 다시 평가한다.
