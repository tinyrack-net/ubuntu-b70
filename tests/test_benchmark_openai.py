import unittest

from scripts.benchmark_openai import percentile, render_comparison, resolve_refs, stats, summarize


class BenchmarkOpenAITests(unittest.TestCase):
    def test_resolve_refs(self):
        self.assertEqual(resolve_refs({"key": "{{ vault_key }}", "vault_key": "secret"})["key"], "secret")

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


if __name__ == "__main__":
    unittest.main()
