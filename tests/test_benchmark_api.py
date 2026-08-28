import unittest
from pathlib import Path

from scripts.benchmark_api import (
    BenchmarkError,
    render_markdown,
    resolve_inventory_refs,
    summarize_results,
    validate_samples,
)


def sample(case="pp128", kind="prompt", repetition=1):
    return {
        "case": case,
        "kind": kind,
        "repetition": repetition,
        "requested_prompt_n": 128,
        "requested_generation_n": 1 if kind == "prompt" else 128,
        "wall_ms": 100.0 + repetition,
        "finish_reason": None,
        "prompt_n": 128,
        "cache_n": 0,
        "predicted_n": 1 if kind == "prompt" else 128,
        "prompt_ms": 50.0,
        "predicted_ms": 50.0,
        "prompt_tps": 40.0 + repetition,
        "predicted_tps": 20.0 + repetition,
    }


class BenchmarkApiTests(unittest.TestCase):
    def test_inventory_reference_is_resolved(self):
        inventory = {"llama_api_key": "{{ vault_llama_api_key }}", "vault_llama_api_key": "secret"}
        self.assertEqual(resolve_inventory_refs(inventory)["llama_api_key"], "secret")

    def test_summary_contains_statistics(self):
        summary = summarize_results([sample(repetition=1), sample(repetition=2)])
        self.assertEqual(summary[0]["samples"], 2)
        self.assertEqual(summary[0]["prompt_tps"]["mean"], 41.5)
        self.assertGreater(summary[0]["prompt_tps"]["stdev"], 0)

    def test_validation_rejects_cache_reuse(self):
        invalid = sample()
        invalid["cache_n"] = 12
        with self.assertRaises(BenchmarkError):
            validate_samples([invalid])

    def test_validation_rejects_short_generation(self):
        invalid = sample(case="tg128", kind="generation")
        invalid["predicted_n"] = 127
        with self.assertRaises(BenchmarkError):
            validate_samples([invalid])

    def test_prompt_case_allows_zero_one_token_generation_tps(self):
        prompt = sample()
        prompt["predicted_tps"] = 0
        validate_samples([prompt])

    def test_markdown_omits_samples_and_renders_summary(self):
        samples = [sample()]
        result = {
            "metadata": {
                "run_id": "20260828T000000Z",
                "git_sha": "abc123",
                "model_file": "model.gguf",
                "backend": "intel",
                "context_size": 65536,
                "parallel": 1,
            },
            "summary": summarize_results(samples),
            "samples": samples,
        }
        report = render_markdown(result, Path("20260828T000000Z-api.json"))
        self.assertIn("pp128", report)
        self.assertIn("41.00", report)
        self.assertNotIn("requested_prompt_n", report)


if __name__ == "__main__":
    unittest.main()
