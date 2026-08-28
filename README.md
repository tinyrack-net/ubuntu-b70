# ubuntu-b70 LLM server

`ubuntu-gpu`(Ubuntu 26.04, Intel Arc Pro B70)을 재현 가능한 llama.cpp 서버로 구성한다.
기본 모델은 `unsloth/Qwen3.8-27B-GGUF`의 `UD-Q4_K_M`이며 비전 입력을 지원한다.

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
`vault_llama_api_key`이며, 평문 확인이 필요하면 `ansible-vault view`를 사용한다.

## 운영 설정

- 기본 backend: Intel SYCL
- 기본 context: 65536, parallel 1
- 메모리 실패 시 `inventories/host_vars/ubuntu-gpu.yml`에 `llama_context_size: 32768`, 이후 `16384`를 설정한다.
- SYCL 런타임 문제 시 같은 파일에 `llama_backend: vulkan`을 설정한다.
- 방화벽과 TLS는 이 저장소에서 관리하지 않는다.

## API TPS 벤치마크

실행 중인 서버를 중단하지 않고 현재 SYCL/64K/parallel 1 구성의 prompt 처리와
token generation 성능을 측정한다. API 키는 `ansible-inventory`에서 메모리로만
읽으며 출력이나 결과 파일에 저장하지 않는다.

```bash
make benchmark-api
```

결과는 `benchmarks/results/<UTC timestamp>-api.json`과 `benchmarks/latest.md`에
저장된다. synthetic 요청은 prompt cache를 끄고 정확한 토큰 길이로 5회씩,
실제 chat 요청은 3회 측정한다. 실행 중에는 단일 server slot을 벤치마크가 점유한다.
