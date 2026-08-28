# ubuntu-b70

This repository provisions the `ubuntu-gpu` Ubuntu 26.04 LLM server.

- Keep every secret in the single encrypted `inventories/group_vars/all/vault.yml` file.
- Never commit `.vault_pass`, a plaintext private key, an API key, or a sudo password.
- Use the repository-first workflow: `make verify`, `make ping`, `make check`, then `make apply`.
- Do not manage the host firewall from this repository.
- Pin model revisions, model checksums, and container image digests.
- The primary inference backend is Intel SYCL. Vulkan is the explicit fallback.

