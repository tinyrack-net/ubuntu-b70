# syntax=docker/dockerfile:1.7
FROM intel/omix@sha256:2d1ac94121bf8fe7d58692738765492e340a1fce27f171a0f90afc4ce3568ad4 AS builder

ARG LLM_SCALER_RELEASE_COMMIT=ac33a74106976dbdd7dccc73a02f403e3cf8edb1
ARG LLM_SCALER_GDN_COMMIT=15f634da32f21d457ec4340026b2b7f048ed2e02
ARG LLM_SCALER_GDN_PARENT=0a7c2c6098d949de7cde2ccad2f081a9eb2b75c1
ARG XPU_KERNELS_COMMIT=3cab97a
ARG INTEL_KERNEL_PATCH_SHA256=43552678c6bc0d06bd86afe26797b2d4aa0c444eb659e140eba803818d513b75
ARG GDN_HARDENING_DIFF_SHA256=da2c5178735b67c7248fe6933f970b3bdec79af6155ec0be75615553378bd766
ARG GDN_OOB_PATCH_SHA256

ENV VIRTUAL_ENV=/opt/buildenv \
    PATH=/root/.local/bin:/opt/buildenv/bin:${PATH} \
    VLLM_TARGET_DEVICE=xpu \
    MAX_JOBS=2
SHELL ["bash", "-c"]

COPY gdn-oob-backport.patch /tmp/gdn-oob-backport.patch

RUN apt-get update -y && apt-get install -y --no-install-recommends \
        git python3-dev python3-venv python3-pip ninja-build cmake pkg-config && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv ${VIRTUAL_ENV} && \
    pip install --upgrade pip wheel 'setuptools<80' build cmake ninja packaging psutil regex scipy && \
    pip install torch==2.11.0+xpu --index-url https://download.pytorch.org/whl/xpu

RUN set -eo pipefail && \
    test "$(sha256sum /tmp/gdn-oob-backport.patch | cut -d' ' -f1)" = "${GDN_OOB_PATCH_SHA256}" && \
    git clone --filter=blob:none https://github.com/intel/llm-scaler.git /src/llm-scaler && \
    cd /src/llm-scaler && \
    git fetch origin "${LLM_SCALER_RELEASE_COMMIT}" "${LLM_SCALER_GDN_COMMIT}" && \
    test "$(git rev-parse ${LLM_SCALER_RELEASE_COMMIT}^{commit})" = "${LLM_SCALER_RELEASE_COMMIT}" && \
    test "$(git rev-parse ${LLM_SCALER_GDN_COMMIT}^{commit})" = "${LLM_SCALER_GDN_COMMIT}" && \
    git show "${LLM_SCALER_RELEASE_COMMIT}:vllm/patches/vllm_xpu_kernels.patch" > /tmp/intel-xpu.patch && \
    test "$(sha256sum /tmp/intel-xpu.patch | cut -d' ' -f1)" = "${INTEL_KERNEL_PATCH_SHA256}" && \
    test "$(git diff ${LLM_SCALER_GDN_PARENT} ${LLM_SCALER_GDN_COMMIT} -- vllm/custom-esimd-kernels-vllm | sha256sum | cut -d' ' -f1)" = "${GDN_HARDENING_DIFF_SHA256}" && \
    git checkout --detach "${LLM_SCALER_GDN_COMMIT}"

RUN set -eo pipefail && source /opt/intel/oneapi/setvars.sh --force && \
    cd /src/llm-scaler/vllm/custom-esimd-kernels-vllm && \
    TORCH_XPU_ARCH_LIST=bmg-g21 MAX_JOBS=1 python setup.py bdist_wheel && \
    mkdir -p /wheels && cp dist/*.whl /wheels/

RUN set -eo pipefail && source /opt/intel/oneapi/setvars.sh --force && \
    git clone https://github.com/vllm-project/vllm-xpu-kernels.git /src/vllm-xpu-kernels && \
    cd /src/vllm-xpu-kernels && \
    git checkout "${XPU_KERNELS_COMMIT}" && \
    git apply /tmp/intel-xpu.patch && \
    git apply /tmp/gdn-oob-backport.patch && \
    export CMAKE_PREFIX_PATH="$(python -c 'import site; print(site.getsitepackages()[0])'):${CMAKE_PREFIX_PATH:-}" && \
    cmake -S . -B build/gdn -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DVLLM_TARGET_DEVICE=xpu \
      -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain.cmake \
      -DVLLM_PYTHON_EXECUTABLE=/opt/buildenv/bin/python \
      -DVLLM_PYTHON_PATH="$(python -c 'import sys; print(":".join(sys.path))')" \
      -DBUILD_SYCL_TLA_KERNELS=ON \
      -DVLLM_XPU_ENABLE_XE2=ON \
      -DVLLM_XPU_ENABLE_XE_DEFAULT=OFF \
      -DBASIC_KERNELS_ENABLED=OFF \
      -DFA2_KERNELS_ENABLED=OFF \
      -DMOE_KERNELS_ENABLED=OFF \
      -DGDN_KERNELS_ENABLED=ON \
      -DMQA_LOGITS_KERNELS_ENABLED=OFF \
      -DXPU_SPECIFIC_KERNELS_ENABLED=OFF \
      -DXPUMEM_ALLOCATOR_ENABLED=OFF \
      -DFETCHCONTENT_BASE_DIR=/src/vllm-xpu-kernels/.deps \
      -DCMAKE_C_COMPILER="$(command -v icx)" \
      -DCMAKE_CXX_COMPILER="$(command -v icpx)" && \
    cmake --build build/gdn -j="${MAX_JOBS}" --target=gdn_attn_kernels_xe_2 && \
    mkdir -p /gdn-artifact && \
    cp build/gdn/libgdn_attn_kernels_xe_2.so /gdn-artifact/

FROM intel/llm-scaler-vllm:0.21.0-b3.1@sha256:032916bd9264da44cab3e99092ffaf12331072ec51c3b380cbbe5fd98eb0254b
COPY --from=builder /wheels /tmp/gdn-wheels
COPY --from=builder /gdn-artifact/libgdn_attn_kernels_xe_2.so \
    /opt/venv/lib/python3.12/site-packages/vllm_xpu_kernels/libgdn_attn_kernels_xe_2.so
RUN pip install --no-deps --force-reinstall \
        /tmp/gdn-wheels/custom_esimd_kernels_vllm-*.whl && \
    rm -rf /tmp/gdn-wheels
LABEL org.opencontainers.image.source="https://github.com/intel/llm-scaler" \
      io.tinyrack.llm-scaler-gdn-commit="15f634da32f21d457ec4340026b2b7f048ed2e02" \
      io.tinyrack.xpu-kernels-base-commit="3cab97a"
