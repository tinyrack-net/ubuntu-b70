FROM intel/llm-scaler-vllm:0.21.0-b3.1@sha256:032916bd9264da44cab3e99092ffaf12331072ec51c3b380cbbe5fd98eb0254b AS patched

USER root
WORKDIR /opt/gemma4-patch

RUN --mount=type=bind,source=llm-base-proposer-gemma4.patch,target=/tmp/llm-base-proposer-gemma4.patch,readonly \
    patch --batch --forward -p1 -d /opt/venv/lib/python3.12/site-packages \
      < /tmp/llm-base-proposer-gemma4.patch \
 && python -c 'p="/opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py"; compile(open(p).read(), p, "exec")' \
 && touch --date=@0 \
      /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py

FROM intel/llm-scaler-vllm:0.21.0-b3.1@sha256:032916bd9264da44cab3e99092ffaf12331072ec51c3b380cbbe5fd98eb0254b

LABEL org.opencontainers.image.title="ubuntu-b70-gemma4-xpu"
LABEL org.opencontainers.image.source="https://github.com/vllm-project/vllm"
LABEL net.tinyrack.ubuntu-b70.patch="gemma4-mtp-target-embedding"

USER root
COPY --from=patched --chown=root:root --chmod=0644 \
  /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py \
  /opt/venv/lib/python3.12/site-packages/vllm/v1/spec_decode/llm_base_proposer.py

WORKDIR /workspace
