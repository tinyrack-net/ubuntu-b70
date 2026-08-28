# ubuntu-b70 LLM server

`ubuntu-gpu`(Ubuntu 26.04, Intel Arc Pro B70)을 재현 가능한 OpenAI 호환 LLM 서버로 구성한다.
기본 엔진은 공식 `vllm/vllm-openai-xpu` 이미지이며, 모델은 단일 B70에 맞춘
`abihsoro/Qwen3.8-27B-AWQ-INT4` 텍스트 전용 체크포인트다. 이미지 digest와 모델
revision을 모두 고정한다.

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

- 기본 엔진: vLLM XPU, context 32768, max sequences 4
- vLLM Compose service와 컨테이너 이름은 `vllm-server`, llama.cpp는
  `llama-server`를 사용한다.
- `vllm_server`와 `llama_server` role은 엔진별 task와 Compose 구성을 독립적으로
  관리하며, `llm_engine` 값에 따라 playbook이 하나만 실행한다.
- vLLM 메모리 실패 시 `inventories/host_vars/ubuntu-gpu.yml`에
  `vllm_context_size: 16384`를 설정한다.
- llama.cpp로 롤백하려면 같은 파일에 `llm_engine: llama_cpp`를 설정한다. 기존
  GGUF 모델과 Intel SYCL 설정은 그대로 보존된다.
- llama.cpp의 SYCL 런타임 문제 시 같은 파일에 `llama_backend: vulkan`을 설정한다.
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
