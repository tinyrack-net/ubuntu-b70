FROM vllm/vllm-openai-xpu@sha256:f01e24f6c7ff01f1e0662234255a1372297d1dbd89d003cf13c8fad3eab1ba4f

LABEL org.opencontainers.image.title="ubuntu-b70-qwen38-xpu"
LABEL org.opencontainers.image.source="https://github.com/SergiioB/intel-arc-pro-b70-inference-cookbook"
LABEL org.opencontainers.image.revision="7025ef443969bd5123169e7d34f18b89ef77becd"
LABEL net.tinyrack.ubuntu-b70.model="SergiioB/Qwen3.8-27B-GPTQ-Int4-sym-G128-MTP-BF16"

USER root
WORKDIR /opt/b70-patches

ADD --checksum=sha256:4d7a02c4ea10ca7c00dc89ad927fa3dafa747dbf0553d2adf24e30a3c53e9c14 \
  https://raw.githubusercontent.com/SergiioB/intel-arc-pro-b70-inference-cookbook/7025ef443969bd5123169e7d34f18b89ef77becd/patches/patch_mtp_nightly.py \
  patch_mtp_nightly.py
ADD --checksum=sha256:41d2f74e5fef1f074b76b5a90dd1016de437228431802cfb1fa7bd7ce4cc9b50 \
  https://raw.githubusercontent.com/SergiioB/intel-arc-pro-b70-inference-cookbook/7025ef443969bd5123169e7d34f18b89ef77becd/patches/patch_mtp_boundary.py \
  patch_mtp_boundary.py
ADD --checksum=sha256:8e4a3cbe5f424f308af74ff215d0fcb8d31f63ac3f07cf359ed2269956c3fc80 \
  https://raw.githubusercontent.com/SergiioB/intel-arc-pro-b70-inference-cookbook/7025ef443969bd5123169e7d34f18b89ef77becd/patches/patch_gdn_mixed_split_v5.py \
  patch_gdn_mixed_split_v5.py
ADD --checksum=sha256:ffae41926d5f05f4f38bb985301b5e572092441d06d6063c8820a63a39b8cefc \
  https://raw.githubusercontent.com/SergiioB/intel-arc-pro-b70-inference-cookbook/7025ef443969bd5123169e7d34f18b89ef77becd/windows/Qwen38-Docker-Standalone/patches/patch_draft_lmhead_int4.py \
  patch_draft_lmhead_int4.py
ADD --checksum=sha256:4df179c3e77fd7a248f9b9c0b60217c60caea14ebfd16b7860536fbff3b2a1e9 \
  https://raw.githubusercontent.com/SergiioB/intel-arc-pro-b70-inference-cookbook/7025ef443969bd5123169e7d34f18b89ef77becd/windows/Qwen38-Docker-Standalone/patches/patch_draft_mtp_int4.py \
  patch_draft_mtp_int4.py
ADD --checksum=sha256:37597260d92dc9fd15d7f546cc51645416baf600053ba219040b9b4016898727 \
  https://raw.githubusercontent.com/SergiioB/intel-arc-pro-b70-inference-cookbook/7025ef443969bd5123169e7d34f18b89ef77becd/patches/patch_vllm_worker_affinity.py \
  patch_vllm_worker_affinity.py

RUN python patch_mtp_nightly.py \
 && python patch_mtp_boundary.py \
 && python patch_gdn_mixed_split_v5.py \
 && python patch_draft_lmhead_int4.py \
 && python patch_draft_mtp_int4.py \
 && python patch_vllm_worker_affinity.py \
 && python -c 'from importlib.metadata import version; assert version("vllm").startswith("0.27.2rc1.dev77"); assert version("vllm-xpu-kernels") == "0.1.12.3"'

WORKDIR /workspace
