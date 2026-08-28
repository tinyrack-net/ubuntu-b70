import tempfile
import unittest
from pathlib import Path

from scripts.role_defaults import read_defaults


class RoleDefaultsTests(unittest.TestCase):
    def test_reads_scalars_lists_and_folded_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.yml"
            path.write_text('---\nengine: vllm\nport: 8080\nratio: "0.92"\nitems:\n  - 1\n  - two\nimage: >-\n  repo/image@sha256:abc\n')
            values = read_defaults(path)
        self.assertEqual(values["engine"], "vllm")
        self.assertEqual(values["port"], 8080)
        self.assertEqual(values["ratio"], "0.92")
        self.assertEqual(values["items"], [1, "two"])
        self.assertEqual(values["image"], "repo/image@sha256:abc")


if __name__ == "__main__":
    unittest.main()
