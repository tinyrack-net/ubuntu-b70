# 128K context 실험 결과 (2026-08-29)

## 결론

`RedHatAI/Qwen3.8-27B-INT4`, Intel MTP3, 내부 DP2에서 context 131072와 FP8 KV를
시험했으나 출력 정확성 검증에 실패했다. 운영은 context 32768, KV cache `auto`,
rank별 `max-num-seqs=4`의 기존 C8 구성으로 롤백했다.

## 후보와 메모리

- 이미지: `intel/llm-scaler-vllm:0.21.0-b3.1@sha256:032916bd9264da44cab3e99092ffaf12331072ec51c3b380cbbe5fd98eb0254b`
- 모델 revision: `2fb0debc365fb6c1683d7d3ad7722470919627a8`
- 후보: context 131072, FP8 KV, MTP3, DP2, rank별 C4, XPU Graph
- 기동 결과: health와 모델 API 정상, OOM 및 재시작 없음
- GPU별 KV cache: 227,651 tokens, 최대 길이 131072 기준 1.74x

따라서 메모리상으로는 GPU당 128K 요청 한 건, DP2 전체 C2가 가능했다.

## 탈락 사유

FP8 KV 후보에서 temperature 0의 짧은 `Reply exactly TEST_OK` 요청부터 정상 문장 대신
`reasoning` delta에 `!`만 반복한 뒤 `finish_reason=length`로 종료됐다. 일반 content는
생성되지 않았다. 장문 probe 동안 OOM, 컨테이너 재시작 및 preemption은 없었지만 같은
출력 붕괴가 발생했으므로 장문 정확성, C2 및 혼합 C8을 합격으로 인정할 수 없다.

최초 장문 검증기는 이 Intel vLLM 버전의 streaming 필드명 `reasoning`을 기존
`reasoning_content`로만 읽어 결과를 `no output`으로 기록했다. 검증기는 두 필드명을
모두 지원하도록 수정했다. 실패 당시 원시 결과는
[`results/20260829T142801Z-vllm-long-context.json`](results/20260829T142801Z-vllm-long-context.json)에
보존했다.

기능 게이트에서 탈락했으므로 후보의 짧은 C8 TPS 비교는 수행하지 않았다.

## 롤백 검증

- 운영 명령: context 32768, KV cache `auto`, MTP3, DP2
- GPU별 KV cache: 98,304 tokens
- health와 인증 모델 API 정상
- temperature 0 한국어 canary: `ROLLBACK_OK`
- auto tool choice: `search_web`와 JSON arguments 정상
- 컨테이너: running, OOM false, restart count 0
- 수정된 60초 C8 soak: 85건 정상, bad content 0, API 오류 0, tool call 정상

롤백 soak 원시 결과는
[`results/20260829T144300Z-vllm-rollback-c8-soak.json`](results/20260829T144300Z-vllm-rollback-c8-soak.json)에
보존했다. reasoning parser 환경에서 장문 exact-marker prompt가 출력 예산을 전부 사고에
사용하지 않도록 해당 stress case에는 `/no_think`를 명시했다.

현재 Intel 이미지와 MTP3 조합에서는 generic FP8 KV를 사용한 128K 승격이 안전하지
않다. 후속 실험은 동적 scale을 사용하는 KV 형식이나 해당 경로가 수정된 고정 이미지가
확보된 뒤 별도 후보로 진행해야 한다.
