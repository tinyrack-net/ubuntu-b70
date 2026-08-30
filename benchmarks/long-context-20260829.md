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

## 96K auto KV 후속 실험 (2026-08-30)

FP8을 사용하지 않고 `max-model-len=98304`, KV cache `auto`, MTP3, DP2, XPU Graph로
다시 시험했다. 두 rank 모두 health와 checksum 검증을 통과했고 GPU별 KV cache는
120,149 tokens였다. 컨테이너 restart와 OOM은 0, preemption도 0이었으므로 메모리
용량만 보면 GPU당 96K 요청 한 건을 수용할 수 있었다.

그러나 기능 검증에서는 96K로 기동한 경우 정확한 4K, 8K, 16K marker는 회수했지만
24K, 28K, 30K, 32K 입력부터 출력이 `!` 반복으로 붕괴했다. 사고 비활성화는 tokenizer가
요구하는 `chat_template_kwargs.enable_thinking=false`로 적용했으며, `/tokenize`와 실제
요청에도 같은 template 옵션을 사용해 토큰 수를 일치시켰다.

같은 이미지·모델·MTP3·DP2를 `max-model-len=32768`로 롤백한 뒤 정확히 16K와 24K
입력을 재시험하자 둘 다 marker를 정상 반환했다. 따라서 이 현상은 기존 32K 운영의
원래 결함이 아니라 96K max model length가 Intel XPU의 장문 실행 경로에 유발한
회귀다. 96K 후보는 승격하지 않았고 운영은 32768/auto KV로 복구했다.

전체 후보 결과는
[`results/20260829T151926Z-vllm-long-context.json`](results/20260829T151926Z-vllm-long-context.json)에
보존했다. 이 전체 실행은 template 옵션 차이로 prompt가 목표보다 40토큰 작았으며,
이후 정확한 토큰 수로 실행한 임계점 진단과 32K 롤백 비교가 위 결론을 확정했다.

## 무성능회귀 장문 후속 실험 (2026-08-30)

공식 b3.1 이미지에서 context를 40,960으로 올리고 정확한 marker와 token logprob를
5회 반복 검증했다. GPU별 KV cache는 103,975 tokens였고 OOM, restart, preemption은
없었지만 전체 30건 중 4건이 `!` 반복과 비유한 logprob로 붕괴했다. 길이별 성공은
4K 5/5, 8K 5/5, 16K 5/5, 24K 3/5, 32K 3/5, 40,704 5/5였다. 따라서 메모리 부족이
아니라 입력 shape와 DP rank에 따라 비결정적으로 발생하는 실행 경로 오염으로 판정했다.

최초 실패 길이 24K에서 focused diagnostic을 수행했다. batch token 1,024와 4,096은
각각 5/5였지만 기본 2,048의 전체 반복에서 실패가 있었고, MTP off도 4/5로 실패했다.
반면 XPU Graph off와 eager는 각각 5/5였다. 표본 수가 작은 진단 결과이지만 MTP가
원인은 아니며 compiled/graph 경로가 주요 조건이라는 upstream 보고와 일치한다. Graph
off와 eager는 무성능회귀 조건을 만족하지 않으므로 운영 후보로 승격하지 않았다.

공식 runtime digest를 기반으로 다음 수정만 포함한 로컬 이미지를 재현 가능하게 빌드했다.

- 이미지 ID: `sha256:e12217bc7ccaca465eaa42d5a7005ed7bb4daab3328aa75c9d290ae2a17e9394`
- patched GDN artifact SHA-256: `da716e1aec0533aaaf54425517fb7287bb1baa7860c6606420bf9eb08c0ca291`
- llm-scaler GDN hardening commit: `15f634da32f21d457ec4340026b2b7f048ed2e02`
- XPU kernels base commit: `3cab97a`
- causal-state OOB backport patch SHA-256:
  `90bbb4876d6f6c6359e64b02d869874a9d132a3ed5ec4baa98034510a0192ec0`

XPU wheel 전체 대신 독립적으로 로드되는 `libgdn_attn_kernels_xe_2.so` 타깃만 빌드해
공식 패키지 위에 교체했다. Ansible은 로컬 태그뿐 아니라 image ID까지 확인하고 불일치
시 시작을 거부한다. custom ESIMD와 `_xpu_C` import smoke test도 통과했다.

수정 이미지를 context 69,632, auto KV, MTP3, DP2, XPU Graph로 배포하자 GPU별 KV
cache는 114,892 tokens였고 최대 길이 기준 1.65x였다. 그러나 marker 40건 중 7건이
붕괴했다: 4K 1건, 8K 1건, 32K 3건, 48K 1건, 69,376 1건이다. 모든 실패는
`finish_reason=length`, 64 output tokens, marker 불일치, 반복 출력, 비유한 logprob였고
OOM, restart, preemption은 없었다. 따라서 적용한 GDN hardening/OOB 수정만으로는
compiled XPU 경로의 오염을 해결하지 못했다. 원시 결과는
[`results/20260830T045020Z-vllm-long-context-probe.json`](results/20260830T045020Z-vllm-long-context-probe.json)에
보존했다.

계획한 원본 `Qwen/Qwen3.8-27B` online `sym_int4` 대조는 immutable revision
`1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`의 BF16 shard가 51.75 GiB인 반면 호스트
여유가 11 GiB뿐이라 수행할 수 없었다. 실패 이미지를 재현 가능하게 보존해야 하고,
이를 삭제해 확보 가능한 11.95 GiB를 더해도 원본 다운로드 공간에 미달한다. 따라서
compressed-tensors 체크포인트의 기여는 이번 실험만으로 완전히 배제할 수 없지만,
공식/수정 커널 모두에서 Graph off와 eager가 정상화된 점은 XPU compiled 경로가 더
강한 원인임을 지지한다.

후보는 탈락했고 운영은 공식 b3.1, context 32,768, auto KV, MTP3, DP2, XPU Graph로
롤백했다. 롤백 후 60초 C8 soak는 38건 성공, bad content 0, API 오류 0, required tool
call 정상, OOM false, restart 0으로 통과했다. content canary 서비스도 exit 0이었다.
soak 결과는
[`results/20260830T050000Z-vllm-rollback-after-gdn-c8-soak.json`](results/20260830T050000Z-vllm-rollback-after-gdn-c8-soak.json)에
보존했다. 정확성 게이트에서 탈락했으므로 C1/C8 성능 비교와 96K/112,640 확장은
수행하지 않았다.
