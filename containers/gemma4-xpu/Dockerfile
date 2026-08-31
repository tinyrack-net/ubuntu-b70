FROM intel/llm-scaler-vllm:0.21.0-b3.1@sha256:032916bd9264da44cab3e99092ffaf12331072ec51c3b380cbbe5fd98eb0254b AS patched

USER root
WORKDIR /opt/gemma4-patch

RUN --mount=type=bind,source=llm-base-proposer-gemma4.patch,target=/tmp/llm-base-proposer-gemma4.patch,readonly \
    patch --batch --forward -p1 -d /opt/venv/lib/python3.12/site-packages \
      < /tmp/llm-base-proposer-gemma4.patch \
 && python -c 'p="/opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py"; compile(open(p).read(), p, "exec")' \
 && touch --date=@0 \
      /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py

RUN --mount=type=bind,source=gemma4-unified-mtp.patch,target=/tmp/gemma4-unified-mtp.patch,readonly \
    patch --batch --forward -p1 -d /opt/venv/lib/python3.12/site-packages \
      < /tmp/gemma4-unified-mtp.patch \
 && python -m py_compile \
      /opt/venv/lib/python3.12/site-packages/vllm/config/speculative.py \
      /opt/venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_mtp.py \
      /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/config.py \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/__init__.py \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/gemma4_unified.py \
 && touch --date=@0 \
      /opt/venv/lib/python3.12/site-packages/vllm/config/speculative.py \
      /opt/venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_mtp.py \
      /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/config.py \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/__init__.py \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/gemma4_unified.py

RUN --mount=type=bind,source=xpu-flash-attn-descale.patch,target=/tmp/xpu-flash-attn-descale.patch,readonly \
    patch --batch --forward -p1 -d /opt/venv/lib/python3.12/site-packages \
      < /tmp/xpu-flash-attn-descale.patch \
 && python -m py_compile \
      /opt/venv/lib/python3.12/site-packages/vllm_xpu_kernels/flash_attn_interface.py \
 && touch --date=@0 \
      /opt/venv/lib/python3.12/site-packages/vllm_xpu_kernels/flash_attn_interface.py

RUN --mount=type=bind,source=gemma4-unified-mm.patch,target=/tmp/gemma4-unified-mm.patch,readonly \
    patch --batch --forward -p1 -d /opt/venv/lib/python3.12/site-packages \
      < /tmp/gemma4-unified-mm.patch \
 && python -m py_compile \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/gemma4_unified.py \
 && touch --date=@0 \
      /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/gemma4_unified.py

FROM intel/llm-scaler-vllm:0.21.0-b3.1@sha256:032916bd9264da44cab3e99092ffaf12331072ec51c3b380cbbe5fd98eb0254b

LABEL org.opencontainers.image.title="ubuntu-b70-gemma4-xpu"
LABEL org.opencontainers.image.source="https://github.com/vllm-project/vllm"
LABEL net.tinyrack.ubuntu-b70.patch="gemma4-mtp-target-embedding"
LABEL net.tinyrack.ubuntu-b70.gemma4-unified-mtp="vllm-pr-44429-minimal"
LABEL net.tinyrack.ubuntu-b70.xpu-flash-attn-descale="intel-llm-scaler-issue-532"

USER root
COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py \
  /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py

COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/config/speculative.py \
  /opt/venv/lib/python3.12/site-packages/vllm/config/speculative.py

COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_mtp.py \
  /opt/venv/lib/python3.12/site-packages/vllm/model_executor/models/gemma4_mtp.py

COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/config.py \
  /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/config.py

COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/__init__.py \
  /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/__init__.py

COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/gemma4_unified.py \
  /opt/venv/lib/python3.12/site-packages/vllm/transformers_utils/configs/gemma4_unified.py

COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm_xpu_kernels/flash_attn_interface.py \
  /opt/venv/lib/python3.12/site-packages/vllm_xpu_kernels/flash_attn_interface.py

WORKDIR /workspace
