# ubuntu-b70 LLM server

`ubuntu-gpu`(Ubuntu 26.04, Intel Arc Pro B70)을 재현 가능한 OpenAI 호환 LLM 서버로 구성한다.
모델별 정적 Compose 프로필이 image digest/ID, 모델 revision과 체크섬, vLLM 실행 인자를
소유한다. 현재 제공하는 프로필은 `qwen-3.8-27b`, `gemma-4-12b`, `gemma-4-31b`다.
Gemma 4 12B는 두 GPU의 DP2, 나머지는 GPU0의 TP1 OpenAI 호환 API로 배치한다.

## 최초 설정

`.vault_pass`와 암호화된 Vault는 초기 부트스트랩에서 생성된다. `.vault_pass`는 절대 커밋하지 않는다.
sudo 비밀번호를 입력할 때만 다음 명령을 사용한다.

```bash
ansible-vault edit inventories/group_vars/all/vault.yml
```

`vault_ubuntu_gpu_become_password`의 빈 문자열을 실제 sudo 비밀번호로 바꾼다.

Beszel Agent를 `https://monitor.winetree94.com`에 등록하려면 같은 Vault에 Hub의
Universal Token을 추가한다. ED25519 공개키는 비밀이 아니므로 공통 변수에 고정한다.

```yaml
vault_beszel_universal_token: <Settings / Tokens의 Universal Token>
```

## 실행

```bash
make install-tools
make install-requirements
make models
make apply MODEL=qwen-3.8-27b
```

`make apply`는 MODEL을 반드시 요구하며 내부에서 `verify → ping → check → apply → test-api`를
순서대로 실행한다. 모델과 image를 현재 서비스를 유지한 채 먼저 다운로드·검증하고, 새 API가
정상화되지 않으면 이전 Compose를 자동 복원한다.

API 주소는 `http://10.132.247.37:8080/v1`이다. Bearer token은 Vault의
`vault_llm_api_key`이며, 평문 확인이 필요하면 `ansible-vault view`를 사용한다.

## 운영 설정

- `qwen-3.8-27b`: Intel llm-scaler 0.26.0-b1과 RedHat INT4 체크포인트 기반,
  context 110592, DP2, rank당 max sequences 4(전체 C8), batch 2048, MTP3,
  XPU Graph OFF, auto KV, text-only. 별도 `model_mtp.safetensors`를 사용해 두 rank의
  동시 기동 메모리 피크를 제한하며, 32GiB 보조 swap과 swappiness 10을 유지한다.
- `gemma-4-31b`: Intel llm-scaler b3.1 기반에 upstream Gemma 4 MTP embedding 수정만
  고정 적용, Google QAT W4A16, context 32768, TP1, max sequences 1,
  assistant MTP4, XPU Graph, FP8 KV, text-only
- `gemma-4-12b`: Intel llm-scaler b3.1 기반에 Gemma 4 Unified MTP와 XPU attention
  descale 수정을 고정 적용, Google 원본을 online symmetric INT4 group 32로 양자화, context 131072, DP2,
  rank당 max sequences 4(전체 C8), assistant MTP6, XPU Graph, auto KV, image 4/audio 1/video 1
- `vllm-server`/8080 API에는 5분 주기의 content canary가 적용된다. Qwen과 Gemma 4 12B의
  GPU 두 장은 DP2로 독립 실행하며, TP2는 collective 비용 때문에 사용하지 않는다.
- Beszel Agent 0.18.8은 outbound WebSocket으로 Hub에 연결하며 CPU, RAM, disk, network,
  Docker 컨테이너와 B70 두 장의 utilization, VRAM, temperature, power를 수집한다.
  SSH listener는 비활성화하며 vLLM TPS와 TTFT는 기존 API benchmark로 측정한다.
- vLLM Compose service와 컨테이너 이름은 `vllm-server`, llama.cpp는
  `llama-server`를 사용한다.
- `vllm_server`와 `llama_server` role은 엔진별 task와 Compose 구성을 독립적으로
  관리하며, `llm_runtime_engine` 값에 따라 playbook이 하나만 실행한다.
- vLLM 메모리 설정은 사용할 프로필의 `compose.yml`에서 조정한다.
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
make benchmark-api MODEL=qwen-3.8-27b
```

비교 실험은 canonical suite를 바꾸지 않고 candidate ID와 matrix filter를 extra-vars로
전달한다. 선택한 candidate ID, case, 동시성 및 반복 수는 manifest에 기록된다.

```bash
make benchmark-api MODEL=qwen-3.8-27b BENCHMARK_ARGS='-e benchmark_candidate_id=example -e benchmark_case_ids=[pp512-tg256] -e benchmark_concurrency_levels=[1] -e benchmark_round_count=5'
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
make test-api MODEL=qwen-3.8-27b
```
