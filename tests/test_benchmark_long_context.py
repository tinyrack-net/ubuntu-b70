import unittest

from scripts.benchmark_long_context import (
    TARGET_CONTEXT,
    distribute_filler,
    parse_kv_cache_tokens,
    prometheus_metric,
    reasoning_delta,
    result_passes,
)


class BenchmarkLongContextTests(unittest.TestCase):
    def test_distribute_filler_places_needle(self):
        self.assertEqual(distribute_filler(9, "front"), (0, 9))
        self.assertEqual(distribute_filler(9, "middle"), (4, 5))
        self.assertEqual(distribute_filler(9, "end"), (9, 0))

    def test_parse_kv_cache_tokens_uses_latest_ranks(self):
        logs = "\n".join((
            "GPU KV cache size: 98,304 tokens",
            "GPU KV cache size: 196,608 tokens",
            "GPU KV cache size: 196,608 tokens",
        ))
        self.assertEqual(parse_kv_cache_tokens(logs, 2), [196608, 196608])

    def test_prometheus_metric_sums_labels(self):
        payload = "\n".join((
            'vllm:num_preemptions_total{model_name="qwen",engine="0"} 2',
            'vllm:num_preemptions_total{model_name="qwen",engine="1"} 3',
        ))
        self.assertEqual(prometheus_metric(payload, "vllm:num_preemptions_total"), 5)

    def test_reasoning_delta_accepts_vllm_wire_names(self):
        self.assertEqual(reasoning_delta({"reasoning": "new"}), "new")
        self.assertEqual(reasoning_delta({"reasoning_content": "legacy"}), "legacy")

    def test_result_requires_cache_stability_and_all_workloads(self):
        row = {"ok": True, "marker_ok": True}
        result = {
            "metadata": {
                "kv_cache_tokens_per_rank": [TARGET_CONTEXT, TARGET_CONTEXT],
                "container_before": {"restart_count": 0},
                "container_after": {"restart_count": 0, "oom_killed": False},
            },
            "marker_cases": [row],
            "acceptance_case": {
                "ok": True, "prompt_tokens": 130816, "output_tokens": 256,
            },
            "long_c2_rounds": [[row, row], [row, row]],
            "mixed_c8": [row] * 8,
        }
        self.assertTrue(result_passes(result))
        result["metadata"]["kv_cache_tokens_per_rank"][0] = TARGET_CONTEXT - 1
        self.assertFalse(result_passes(result))


if __name__ == "__main__":
    unittest.main()
