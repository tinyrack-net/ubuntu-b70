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
    def test_llama_role_has_no_vllm_configuration(self):
        self.assertNotIn("vllm_", role_text("llama_server").lower())

    def test_vllm_role_has_no_llama_cpp_configuration(self):
        text = role_text("vllm_server").lower()
        self.assertNotIn("llama_model_", text)
        self.assertNotIn("llama_backend", text)

    def test_playbook_selects_roles_by_engine(self):
        playbook = (ROOT / "playbooks" / "setup.yml").read_text()
        self.assertIn("role: llama_server", playbook)
        self.assertIn("when: llm_engine == 'llama_cpp'", playbook)
        self.assertIn("role: vllm_server", playbook)
        self.assertIn("when: llm_engine == 'vllm'", playbook)
        self.assertIn("role: llm_runtime", playbook)

    def test_each_compose_uses_its_engine_name(self):
        llama = (ROOT / "roles/llama_server/templates/compose.yml.j2").read_text()
        vllm = (ROOT / "roles/vllm_server/templates/compose.yml.j2").read_text()
        self.assertIn("container_name: \"{{ llama_container_name }}\"", llama)
        self.assertIn("vllm-server:", vllm)
        self.assertIn("container_name: \"{{ vllm_container_name }}\"", vllm)


if __name__ == "__main__":
    unittest.main()
