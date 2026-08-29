import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANARY_PATH = ROOT / "roles" / "vllm_server" / "files" / "vllm_content_canary.py"
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("vllm_content_canary", CANARY_PATH)
CANARY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CANARY)


class VllmContentCanaryTests(unittest.TestCase):
    def test_marker_is_required_and_bang_only_output_is_rejected(self):
        self.assertTrue(CANARY.response_is_valid("B70_CANARY_OK", "B70_CANARY_OK"))
        self.assertFalse(CANARY.response_is_valid("!!!!!!!!!!!!!!!!", "B70_CANARY_OK"))
        self.assertFalse(CANARY.response_is_valid("unrelated output", "B70_CANARY_OK"))

    def test_failure_counter_resets_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "failures"
            self.assertEqual(CANARY.update_failure_count(state, True), 1)
            self.assertEqual(CANARY.update_failure_count(state, True), 2)
            self.assertEqual(CANARY.update_failure_count(state, False), 0)
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
