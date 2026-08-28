from ansible.module_utils.common.text.converters import to_bytes
from ansible.plugins.become.sudo import DOCUMENTATION
from ansible.plugins.become.sudo import BecomeModule as SudoBecomeModule


class BecomeModule(SudoBecomeModule):
    name = "sudo_wrapped"

    def check_password_prompt(self, b_output: bytes) -> bool:
        """Accept sudoers wrappers around Ansible's password prompt."""
        if self.prompt:
            b_prompt = to_bytes(self.prompt).strip()
            return any(b_prompt in line.strip() for line in b_output.splitlines())
        return False
