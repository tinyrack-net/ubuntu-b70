import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def role_text(role: str) -> str:
    return "\n".join(
        path.read_text()
        for path in sorted((ROOT / "roles" / role).rglob("*"))
        if path.is_file()
    )


class RoleSeparationTests(unittest.TestCase):
    def test_inventory_contains_only_host_overrides(self):
        inventory = (ROOT / "inventories/group_vars/all/main.yml").read_text()
        self.assertNotIn("vllm_server_model:", inventory)
        self.assertNotIn("llama_server_model_file:", inventory)
        self.assertNotIn("llm_runtime_engine:", inventory)

    def test_llama_role_has_no_vllm_configuration(self):
        self.assertNotIn("vllm_", role_text("llama_server").lower())

    def test_vllm_role_has_no_llama_cpp_configuration(self):
        text = role_text("vllm_server").lower()
        self.assertNotIn("llama_model_", text)
        self.assertNotIn("llama_backend", text)

    def test_playbook_selects_roles_by_engine(self):
        playbook = (ROOT / "playbooks" / "setup.yml").read_text()
        self.assertIn("role: llama_server", playbook)
        self.assertIn("when: llm_runtime_engine == 'llama_cpp'", playbook)
        self.assertIn("role: vllm_server", playbook)
        self.assertIn("when: llm_runtime_engine == 'vllm'", playbook)
        self.assertIn("role: llm_runtime", playbook)

    def test_each_compose_uses_its_engine_name(self):
        llama = (ROOT / "roles/llama_server/templates/compose.yml.j2").read_text()
        vllm = (ROOT / "roles/vllm_server/templates/compose.yml.j2").read_text()
        self.assertIn("container_name: \"{{ llm_runtime_llama_container_name }}\"", llama)
        self.assertIn("{{ instance.name }}:", vllm)
        self.assertIn('container_name: "{{ instance.name }}"', vllm)

    def test_vllm_auto_tool_choice_uses_role_defaults(self):
        defaults = (ROOT / "roles/vllm_server/defaults/main.yml").read_text()
        compose = (ROOT / "roles/vllm_server/templates/compose.yml.j2").read_text()
        self.assertIn("vllm_server_enable_auto_tool_choice: true", defaults)
        self.assertIn("vllm_server_tool_call_parser: qwen3_xml", defaults)
        self.assertIn("vllm_server_reasoning_parser: qwen3", defaults)
        self.assertIn("--enable-auto-tool-choice", compose)
        self.assertIn('--tool-call-parser "{{ vllm_server_tool_call_parser }}"', compose)
        self.assertIn('--reasoning-parser "{{ vllm_server_reasoning_parser }}"', compose)

    def test_vllm_uses_benchmarked_xpu_throughput_defaults(self):
        defaults = (ROOT / "roles/vllm_server/defaults/main.yml").read_text()
        compose = (ROOT / "roles/vllm_server/templates/compose.yml.j2").read_text()
        self.assertIn("vllm_server_max_num_seqs: 4", defaults)
        self.assertIn("vllm_server_context_size: 118784", defaults)
        self.assertIn("vllm_server_enable_xpu_graph: false", defaults)
        self.assertIn("VLLM_XPU_ENABLE_XPU_GRAPH:", compose)
        self.assertIn("instance_xpu_graph | bool", compose)

    def test_vllm_uses_pinned_intel_mtp3_internal_dp2(self):
        defaults = (ROOT / "roles/vllm_server/defaults/main.yml").read_text()
        self.assertIn("intel/llm-scaler-vllm:0.21.0-b3.1@sha256:", defaults)
        self.assertIn("vllm_server_model: RedHatAI/Qwen3.8-27B-INT4", defaults)
        self.assertIn("num_speculative_tokens: 3", defaults)
        self.assertIn("device_selector: level_zero:0,1", defaults)
        self.assertIn("data_parallel_size: 2", defaults)
        self.assertIn("max_num_seqs: 4", defaults)
        self.assertNotIn("port: 8081", defaults)
        self.assertIn("vllm_server_enable_prefix_caching: false", defaults)

    def test_vllm_supports_multiple_xpu_instances_and_tensor_parallel(self):
        defaults = (ROOT / "roles/vllm_server/defaults/main.yml").read_text()
        compose = (ROOT / "roles/vllm_server/templates/compose.yml.j2").read_text()
        tasks = (ROOT / "roles/vllm_server/tasks/main.yml").read_text()
        self.assertIn("vllm_server_instances:", defaults)
        self.assertIn("for instance in vllm_server_instances", compose)
        self.assertIn("--tensor-parallel-size", compose)
        self.assertIn('loop: "{{ vllm_server_instances }}"', tasks)

    def test_vllm_instances_can_override_model_and_tuning(self):
        compose = (ROOT / "roles" / "vllm_server" / "templates" / "compose.yml.j2").read_text()
        tasks = role_text("vllm_server")
        for key in (
            "instance.model",
            "instance.image",
            "instance.model_revision",
            "instance.quantization",
            "instance.max_num_seqs",
            "instance.max_num_batched_tokens",
            "instance.data_parallel_size",
            "instance.kv_cache_dtype",
            "instance.enable_prefix_caching",
            "instance.attention_backend",
            "instance.speculative_config",
            "instance.enforce_eager",
            "instance.compilation_config",
            "instance.mamba_cache_dtype",
            "instance.mamba_ssm_cache_dtype",
            "instance.expected_image_id",
        ):
            self.assertIn(key, compose)
        self.assertIn("--data-parallel-size", compose)
        self.assertIn("--data-parallel-backend mp", compose)
        self.assertIn("--enforce-eager", compose)
        self.assertIn("--mamba-ssm-cache-dtype", compose)
        self.assertIn("Verify pinned local vLLM image IDs", tasks)
        self.assertIn("check_mode: false", tasks)

    def test_vllm_verifies_pinned_model_files(self):
        defaults = (ROOT / "roles" / "vllm_server" / "defaults" / "main.yml").read_text()
        tasks = role_text("vllm_server")
        self.assertIn("vllm_server_model_files:", defaults)
        self.assertIn("sha256sum", tasks)
        self.assertIn("vllm_server_model_files", tasks)

    def test_intel_compute_runtime_is_pinned_with_checksums(self):
        defaults = (ROOT / "roles" / "intel_gpu" / "defaults" / "main.yml").read_text()
        tasks = role_text("intel_gpu")
        self.assertIn("intel_gpu_compute_runtime_version: 26.18.38308.1-0", defaults)
        self.assertEqual(defaults.count("sha256:"), 6)
        self.assertIn("checksum: \"sha256:{{ item.sha256 }}\"", tasks)
        self.assertIn("intel_gpu_level_zero_version.stdout == intel_gpu_compute_runtime_version", tasks)

    def test_vllm_content_canary_restarts_only_after_repeated_failures(self):
        defaults = (ROOT / "roles" / "vllm_server" / "defaults" / "main.yml").read_text()
        canary = (ROOT / "roles" / "vllm_server" / "files" / "vllm_content_canary.py").read_text()
        self.assertIn("vllm_server_content_canary_failure_threshold: 2", defaults)
        self.assertIn('subprocess.run(["docker", "restart", args.container]', canary)
        self.assertIn("failures >= args.failure_threshold", canary)
        self.assertIn("canary_instance.name", role_text("vllm_server"))


if __name__ == "__main__":
    unittest.main()
