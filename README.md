# ubuntu-b70 LLM server

`ubuntu-gpu`(Ubuntu 26.04, Intel Arc Pro B70)을 재현 가능한 OpenAI 호환 LLM 서버로 구성한다.
기본 엔진은 Intel `llm-scaler-vllm` 이미지이며, 모델은
`SergiioB/Qwen3.8-27B-GPTQ-Int4-sym-G128-MTP-BF16` 체크포인트다. 두 B70을 vLLM
내부 DP2로 묶은 단일 MTP3 API를 배치하며 이미지 digest, 모델 revision과 체크섬을 모두
고정한다.

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

- 기본 엔진: Intel vLLM XPU, context 131072, 내부 data parallel 2, rank별 max
  sequences 4(전체 동시성 8), MTP3, XPU Graph 비활성화, FP8 KV, prefix caching
  비활성화, 최대 1MP 이미지 1장
- `vllm-server`/8080 단일 API가 GPU0·GPU1에 요청을 분산하며 5분 주기의 content
  canary가 적용된다. vLLM의 DP queue 기반 내부 load balancer를 사용하므로 별도의
  프록시는 필요하지 않다.
- vLLM Compose service와 컨테이너 이름은 `vllm-server`, llama.cpp는
  `llama-server`를 사용한다.
- `vllm_server`와 `llama_server` role은 엔진별 task와 Compose 구성을 독립적으로
  관리하며, `llm_runtime_engine` 값에 따라 playbook이 하나만 실행한다.
- vLLM 메모리 실패 시 `inventories/host_vars/ubuntu-gpu.yml`에
  `vllm_server_context_size: 16384`를 설정한다.
- llama.cpp로 롤백하려면 같은 파일에 `llm_runtime_engine: llama_cpp`를 설정한다. pinned
  GGUF 모델은 롤백 적용 시 다시 다운로드하며 Intel SYCL 설정은 그대로 유지된다.
- llama.cpp의 SYCL 런타임 문제 시 같은 파일에 `llama_server_backend: vulkan`을 설정한다.
- 방화벽과 TLS는 이 저장소에서 관리하지 않는다.

## API TPS 벤치마크

컨테이너에 포함된 표준 `vllm bench serve`로 고정된 random dataset의 prompt 처리,
token generation, TTFT, TPOT, ITL, E2E latency와 aggregate throughput을 측정한다.
표준 suite는 [`benchmarks/suite.yml`](benchmarks/suite.yml)에 있으며 seed, 입력·출력 길이,
동시성, 반복 수와 percentile을 모두 고정한다. 각 workload·동시성 shape는 DP rank와
실행 경로를 준비하기 위해 측정 전에 한 번 선행 실행한다. API 키는 컨테이너의 secret
파일에서만 읽으며 결과에 저장하지 않는다.

```bash
make benchmark-api
```

정식 실행은 깨끗한 Git commit에서만 허용된다. 측정 중 content canary를 멈추고 같은
Compose 구성을 loopback 전용 포트로 재기동하여 외부 트래픽을 격리한다. 완료 또는 실패
후에는 운영 Compose와 canary를 자동 복구한다. 강제 중단 등으로 복구되지 않았다면 다음
명령을 실행한다.

```bash
make benchmark-restore
```

결과는 `benchmarks/runs/<UTC>-<commit>/` 아래에 저장한다. `raw/`에는 vLLM 상세 원본,
`summary.json`에는 metric별 mean·median·min·max·CV, `manifest.json`에는 Git·suite·OS·GPU·
container image·모델 checksum·공개 benchmark argv와 복구 상태를 기록한다. 요청 실패, 비유한 metric, 출력 길이
불일치 또는 세 번 측정한 output TPS의 CV가 5%를 초과하면 실행은 실패한다. 실패한 원본과
`failure.json`도 삭제하지 않는다.

라이브 API와 한국어·reasoning 비노출·도구 호출·streaming 회귀는 digest가 고정된 Hurl
컨테이너로 검증한다. Vault API 키는 임시 `0600` 변수 파일로만 전달하고 종료 시 삭제한다.

```bash
make test-api
```
