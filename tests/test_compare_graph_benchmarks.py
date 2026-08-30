import unittest

from scripts.compare_graph_benchmarks import classify, compare, percent_change


def benchmark(graph: bool, scale: float = 1.0):
    return {
        "metadata": {
            "context_size": 32768,
            "model": "Qwen3.8-27B",
            "environment": {"instances": [{"xpu_graph_enabled": graph}]},
        },
        "summary": [
            {"case": "pp128", "prompt_tps": {"median": 100 * scale}},
            {"case": "tg128", "decode_tps": {"median": 80 * scale}},
        ],
        "concurrency": [
            {
                "concurrency": concurrency,
                "output_tps": 70 * concurrency * scale,
                "ttft_ms": {"median": 100 / scale},
                "tpot_ms": {"median": 10 / scale},
            }
            for concurrency in (1, 8)
        ],
    }


class CompareGraphBenchmarksTests(unittest.TestCase):
    def test_percent_change(self):
        self.assertAlmostEqual(percent_change(95, 100), -5)

    def test_compare_uses_median_across_runs(self):
        result = compare(
            [benchmark(True, 1.0), benchmark(True, 1.2)],
            [benchmark(False, 1.0), benchmark(False, 1.1)],
        )
        self.assertEqual(result["graph_on_runs"], 2)
        self.assertEqual(result["graph_off_runs"], 2)
        self.assertAlmostEqual(result["graph_on"]["c8_output_tps"], 616)
        self.assertEqual(result["classification"], "no_material_regression")

    def test_classification_rejects_large_tps_loss(self):
        changes = {
            "c1_output_tps": -20,
            "c8_output_tps": -18,
            "c1_ttft_ms": 5,
            "c8_ttft_ms": 5,
        }
        self.assertEqual(classify(changes), "unsuitable")


if __name__ == "__main__":
    unittest.main()
