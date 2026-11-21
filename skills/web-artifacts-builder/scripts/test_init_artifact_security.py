from pathlib import Path
import os
import shlex
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).with_name("init-artifact.sh")
BASH = shutil.which("bash")
WSL = shutil.which("wsl.exe")


@unittest.skipUnless(BASH or WSL, "requires bash")
class ProjectNameValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
        cls.validation_prefix = source.split("# Detect Node version", 1)[0]

    def run_validation(self, *args):
        argument_setup = "set -- " + " ".join(shlex.quote(arg) for arg in args) + "\n"
        script = (
            argument_setup
            + self.validation_prefix
            + 'printf "VALIDATION_ACCEPTED\\n"\n'
        )
        command = (
            [WSL, "--exec", "/bin/bash"]
            if os.name == "nt" and WSL
            else [BASH, "-c", script]
        )
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            input=script.encode("utf-8") if os.name == "nt" and WSL else None,
        )
        return subprocess.CompletedProcess(
            args=result.args,
            returncode=result.returncode,
            stdout=result.stdout.decode("utf-8", errors="replace"),
            stderr=result.stderr.decode("utf-8", errors="replace"),
        )

    def test_accepts_normal_project_name(self):
        result = self.run_validation("demo-app")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VALIDATION_ACCEPTED", result.stdout)

    def test_rejects_sed_program_payload_before_external_commands(self):
        payload = "demo/;w /tmp/daybreak-sed-pwned\nq\n#"
        result = self.run_validation(payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid project name:", result.stdout)
        self.assertNotIn("VALIDATION_ACCEPTED", result.stdout)

    def test_rejects_extra_arguments(self):
        result = self.run_validation("demo-app", "unexpected")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
