import unittest

from scripts.benchmark_long_context import (
    TARGET_CONTEXT,
    collapsed_output,
    distribute_filler,
    marker_prompt_cases,
    parse_kv_cache_tokens,
    probe_quality_ok,
    prometheus_metric,
    reasoning_delta,
    result_passes,
    runtime_mode,
)


class BenchmarkLongContextTests(unittest.TestCase):
    def test_distribute_filler_places_needle(self):
        self.assertEqual(distribute_filler(9, "front"), (0, 9))
        self.assertEqual(distribute_filler(9, "middle"), (4, 5))
        self.assertEqual(distribute_filler(9, "end"), (9, 0))

    def test_marker_prompt_cases_include_boundaries_and_acceptance(self):
        self.assertEqual(
            marker_prompt_cases(69_632),
            (4_096, 8_192, 16_384, 24_576, 32_768, 49_152, 65_536, 69_376),
        )

    def test_collapsed_output_detects_repeated_token_failures(self):
        self.assertTrue(collapsed_output("!!!!!!!!"))
        self.assertTrue(collapsed_output("bad bad bad bad"))
        self.assertFalse(collapsed_output("B70_NEEDLE_24576_END_1"))

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

    def test_probe_quality_rejects_reasoning_and_nonfinite_output(self):
        row = {
            "ok": True, "marker_ok": True, "finite_logprobs": True,
            "collapsed_output": False, "think_tag_visible": False,
            "reasoning_content_present": False,
        }
        self.assertTrue(probe_quality_ok(row))
        row["reasoning_content_present"] = True
        self.assertFalse(probe_quality_ok(row))

    def test_runtime_mode_records_graph_and_compile_controls(self):
        values = {
            "vllm_server_enable_xpu_graph": True,
            "vllm_server_instances": [{
                "name": "vllm-server", "enable_xpu_graph": False,
                "mamba_cache_dtype": "auto",
            }],
        }
        mode = runtime_mode(values, "vllm-server")
        self.assertFalse(mode["xpu_graph_enabled"])
        self.assertFalse(mode["enforce_eager"])
        self.assertEqual(mode["compilation_config"], "")

    def test_result_requires_cache_stability_and_all_workloads(self):
        row = {
            "ok": True, "marker_ok": True,
            "finite_logprobs": True, "collapsed_output": False,
            "think_tag_visible": False, "reasoning_content_present": False,
        }
        result = {
            "metadata": {
                "kv_cache_tokens_per_rank": [TARGET_CONTEXT, TARGET_CONTEXT],
                "container_before": {"restart_count": 0},
                "container_after": {"restart_count": 0, "oom_killed": False},
            },
            "marker_cases": [row],
            "acceptance_case": {
                "ok": True, "marker_ok": True,
                "finite_logprobs": True, "collapsed_output": False,
                "think_tag_visible": False, "reasoning_content_present": False,
                "prompt_tokens": 130816, "output_tokens": 256,
            },
            "long_c2_rounds": [[row, row], [row, row]],
            "mixed_c8": [row] * 8,
        }
        self.assertTrue(result_passes(result))
        result["metadata"]["kv_cache_tokens_per_rank"][0] = TARGET_CONTEXT - 1
        self.assertFalse(result_passes(result))


if __name__ == "__main__":
    unittest.main()
