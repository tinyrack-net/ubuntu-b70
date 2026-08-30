# ubuntu-b70 LLM server

`ubuntu-gpu`(Ubuntu 26.04, Intel Arc Pro B70)을 재현 가능한 OpenAI 호환 LLM 서버로 구성한다.
기본 엔진은 Intel `llm-scaler-vllm` 이미지이며, 모델은
`RedHatAI/Qwen3.8-27B-INT4` 텍스트 전용 체크포인트다. 두 B70을 vLLM 내부 DP2로
묶은 단일 MTP3 API를 배치하며 이미지 digest, 모델 revision과 체크섬을 모두 고정한다.

## 최초 설정

`.vault_pass`와 암호화된 Vault는 초기 부트스트랩에서 생성된다. `.vault_pass`는 절대 커밋하지 않는다.
sudo 비밀번호를 입력할 때만 다음 명령을 사용한다.

```bash
ansible-vault edit inventories/group_vars/all/vault.yml
```

`vault_ubuntu_gpu_become_password`의 빈 문자열을 실제 sudo 비밀번호로 바꾼다.

## 실행

```bash
make install-tools
make install-requirements
make verify
make ping
make check
make apply
```

API 주소는 `http://10.132.247.37:8080/v1`이다. Bearer token은 Vault의
`vault_llm_api_key`이며, 평문 확인이 필요하면 `ansible-vault view`를 사용한다.

## 운영 설정

- 기본 엔진: Intel vLLM XPU, context 118784, 내부 data parallel 2, rank별 max
  sequences 4(전체 동시성 8), MTP3, XPU Graph 비활성화, auto KV, prefix caching
  비활성화
- `vllm-server`/8080 단일 API가 GPU0·GPU1에 요청을 분산하며 5분 주기의 content
  canary가 적용된다. vLLM의 DP queue 기반 내부 load balancer를 사용하므로 별도의
  프록시는 필요하지 않다.
- vLLM Compose service와 컨테이너 이름은 `vllm-server`, llama.cpp는
  `llama-server`를 사용한다.
- `vllm_server`와 `llama_server` role은 엔진별 task와 Compose 구성을 독립적으로
  관리하며, `llm_runtime_engine` 값에 따라 playbook이 하나만 실행한다.
- vLLM 메모리 실패 시 `inventories/host_vars/ubuntu-gpu.yml`에
  `vllm_server_context_size: 16384`를 설정한다.
- llama.cpp로 롤백하려면 같은 파일에 `llm_runtime_engine: llama_cpp`를 설정한다. 기존
  GGUF 모델과 Intel SYCL 설정은 그대로 보존된다.
- llama.cpp의 SYCL 런타임 문제 시 같은 파일에 `llama_server_backend: vulkan`을 설정한다.
- 방화벽과 TLS는 이 저장소에서 관리하지 않는다.

## API TPS 벤치마크

실행 중인 엔진을 중단하지 않고 공통 OpenAI streaming API로 prompt 처리, token
generation, 동시성 1/2/4 성능을 측정한다. API 키는 `ansible-inventory`에서
메모리로만 읽으며 출력이나 결과 파일에 저장하지 않는다.

```bash
make benchmark-api
```

결과는 `benchmarks/results/<UTC timestamp>-<engine>-openai.json`과
`benchmarks/latest.md`에 저장된다. 128/512/2048-token prompt와 128/256-token
generation을 각각 5회 측정하고, 동시성별 aggregate output tokens/s도 기록한다.

인스턴스별 모델·revision·양자화·speculative decoding·KV cache·attention backend
override를 사용하는 비교 실험은 `benchmarks/profiles/`의 profile을 적용한다. 2026-08-28
단일 요청 TPS 조사 결과와 운영 권고안은
[`benchmarks/single-tps-20260828.md`](benchmarks/single-tps-20260828.md)에 기록되어 있다.
Intel runtime, XPU Graph, batching, prefix caching, MTP 1/2/3 및 2-GPU replica까지 확장한
최신 조사 결과는 [`benchmarks/b70-tuning-20260829.md`](benchmarks/b70-tuning-20260829.md)에
기록되어 있다.

128K context 후보는 FP8 KV로 메모리 용량은 확보했지만 Intel MTP3에서 출력이 `!`로
붕괴해 탈락했다. 당시 운영 기본값과 상세 결과는
[`benchmarks/long-context-20260829.md`](benchmarks/long-context-20260829.md)에 기록되어 있다.
96K/auto KV 후보도 메모리는 충분했지만 24K 이상 입력에서 같은 출력 붕괴가 발생했고,
32K 설정으로 롤백하면 동일 24K 입력이 정상화되어 운영 승격에서 제외했다.
GDN hardening과 causal-state OOB backport를 적용한 고정 로컬 이미지도 69,632 context
반복 검증에서 같은 비유한 logprob/출력 붕괴가 발생해 탈락했다. 후속 Graph ON/OFF
대조 실험에서는 Graph OFF가 auto KV로 118,784 context까지 marker, 장문 C2 및 혼합
C8을 OOM/restart/preemption 없이 처리했다. 단일 decode TPS는 Graph ON보다 약 19%
낮지만 장문 안정성을 우선해 118,784/Graph OFF를 운영 기본값으로 선택했다. 상세 결과는
[`benchmarks/graph-off-20260830.md`](benchmarks/graph-off-20260830.md)에 기록되어 있다.
