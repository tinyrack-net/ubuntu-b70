import unittest

from scripts.benchmark_openai import (
    CONCURRENCY_LEVELS,
    benchmark_environment,
    parse_prometheus,
    percentile,
    render_comparison,
    resolve_refs,
    stats,
    summarize,
)


class BenchmarkOpenAITests(unittest.TestCase):
    def test_default_concurrency_covers_dp2_capacity(self):
        self.assertEqual(CONCURRENCY_LEVELS, (1, 2, 4, 8))

    def test_resolve_refs(self):
        self.assertEqual(resolve_refs({"key": "{{ vault_key }}", "vault_key": "secret"})["key"], "secret")

    def test_resolve_refs_recurses_into_instance_mappings(self):
        values = {
            "llm_runtime_port": 8080,
            "llm_runtime_vllm_container_name": "vllm-server",
            "vllm_server_instances": [{
                "name": "{{ llm_runtime_vllm_container_name }}",
                "port": "{{ llm_runtime_port }}",
            }],
        }
        self.assertEqual(
            resolve_refs(values)["vllm_server_instances"],
            [{"name": "vllm-server", "port": 8080}],
        )

    def test_percentile_interpolates(self):
        self.assertEqual(percentile([1, 2, 3], 50), 2)
        self.assertAlmostEqual(percentile([1, 2], 95), 1.95)

    def test_stats_and_summary(self):
        rows = [{"case": "tg128", **{name: value for name in ("prompt_tps", "decode_tps", "ttft_ms", "tpot_ms", "e2e_ms")}} for value in (10.0, 20.0)]
        summary = summarize(rows)
        self.assertEqual(summary[0]["n"], 2)
        self.assertEqual(summary[0]["decode_tps"]["median"], 15.0)

    def test_comparison_contains_throughput(self):
        metric = {"median": 12.0}
        result = {
            "metadata": {"engine": "vllm", "run_id": "run", "model": "model", "context_size": 32768},
            "summary": [{"case": "tg128", "prompt_tps": metric, "decode_tps": metric, "ttft_ms": metric, "tpot_ms": metric}],
            "concurrency": [{"concurrency": 4, "requests": 20, "output_tps": 48.0, "ttft_ms": metric}],
        }
        report = render_comparison([result])
        self.assertIn("Aggregate output tok/s", report)
        self.assertIn("| 4 | 20 | 48.00 |", report)

    def test_parse_prometheus_keeps_speculative_metrics(self):
        payload = """
# HELP vllm:spec_decode_num_drafts Number of drafts
vllm:spec_decode_num_drafts{model_name="qwen"} 20
vllm:spec_decode_num_accepted_tokens{model_name="qwen"} 15
vllm:num_requests_running 1
"""
        self.assertEqual(
            parse_prometheus(payload),
            {
                "vllm:spec_decode_num_drafts": 20.0,
                "vllm:spec_decode_num_accepted_tokens": 15.0,
            },
        )

    def test_environment_records_per_instance_tuning(self):
        inv = {
            "vllm_server_image": "default@sha256:one",
            "vllm_server_max_num_seqs": 4,
            "vllm_server_max_num_batched_tokens": 2048,
            "vllm_server_gpu_memory_utilization": 0.92,
            "vllm_server_enable_prefix_caching": True,
            "vllm_server_enable_xpu_graph": True,
            "vllm_server_instances": [{
                "name": "candidate", "port": 8081, "device_selector": "level_zero:1",
                "image": "nightly@sha256:two", "max_num_batched_tokens": 4096,
                "enable_prefix_caching": False, "enable_xpu_graph": False,
            }],
        }
        environment = benchmark_environment("test", inv)
        self.assertEqual(environment["max_num_batched_tokens"], 4096)
        self.assertFalse(environment["prefix_caching_enabled"])

    def test_environment_records_internal_data_parallelism(self):
        inv = {
            "vllm_server_image": "intel@sha256:one",
            "vllm_server_model": "model",
            "vllm_server_model_revision": "revision",
            "vllm_server_max_num_seqs": 2,
            "vllm_server_max_num_batched_tokens": 2048,
            "vllm_server_enable_prefix_caching": False,
            "vllm_server_gpu_memory_utilization": "0.92",
            "vllm_benchmark_concurrency_levels": [1, 2, 4, 8],
            "vllm_server_instances": [{
                "name": "vllm-server", "port": 8080,
                "device_selector": "level_zero:0,1",
                "tensor_parallel_size": 1, "data_parallel_size": 2,
            }],
        }
        environment = benchmark_environment("dp2", inv)
        self.assertEqual(environment["topology"], "data_parallel")
        self.assertEqual(environment["gpu_count"], 2)
        self.assertEqual(environment["instances"][0]["data_parallel_size"], 2)
        self.assertTrue(environment["xpu_graph_enabled"])
        self.assertEqual(environment["instances"][0]["image"], "intel@sha256:one")
        self.assertEqual(environment["benchmark"]["concurrency_levels"], [1, 2, 4, 8])


if __name__ == "__main__":
    unittest.main()
