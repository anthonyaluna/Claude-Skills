import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
XLSX_SCRIPT = REPO_ROOT / "skills/xlsx/scripts/recalc.py"
DOCX_SCRIPT = REPO_ROOT / "skills/docx/scripts/accept_changes.py"
XLSX_SCRIPT_URI = (
    "vnd.sun.star.script:Standard.Module1.RecalculateAndSave?"
    "language=Basic&location=application"
)
DOCX_SCRIPT_URI = (
    "vnd.sun.star.script:Standard.Module1.AcceptAllTrackedChanges?"
    "language=Basic&location=application"
)


def load_script(name, path):
    office_package = ModuleType("office")
    office_package.__path__ = []
    soffice_module = ModuleType("office.soffice")
    soffice_module.get_soffice_env = lambda: {}
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {"office": office_package, "office.soffice": soffice_module},
    ):
        spec.loader.exec_module(module)
    return module


def profile_flag(profile_dir):
    return f"-env:UserInstallation={profile_dir.as_uri()}"


class LibreOfficeMacroProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xlsx = load_script("macro_profile_xlsx", XLSX_SCRIPT)
        cls.docx = load_script("macro_profile_docx", DOCX_SCRIPT)

    def test_setup_rejects_nonempty_profile_before_launching_libreoffice(self):
        setup_cases = (
            (self.xlsx, "setup_libreoffice_macro", "RecalculateAndSave"),
            (self.docx, "_setup_libreoffice_macro", "AcceptAllTrackedChanges"),
        )
        for module, setup_name, entrypoint in setup_cases:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as profile:
                    profile_dir = Path(profile)
                    macro_file = (
                        profile_dir / "user" / "basic" / "Standard" / "Module1.xba"
                    )
                    macro_file.parent.mkdir(parents=True)
                    malicious_macro = (
                        f'Sub {entrypoint}()\n    Shell("untrusted")\nEnd Sub\n'
                    )
                    macro_file.write_text(malicious_macro)

                    with patch.object(
                        module.subprocess, "run"
                    ) as run, patch.object(module, "get_soffice_env", return_value={}):
                        self.assertFalse(getattr(module, setup_name)(profile_dir))
                        run.assert_not_called()

                    self.assertEqual(macro_file.read_text(), malicious_macro)

    def test_xlsx_recalc_uses_private_profile_for_setup_and_macro(self):
        with tempfile.TemporaryDirectory() as work_dir:
            workbook_path = Path(work_dir) / "input.xlsx"
            from openpyxl import Workbook

            Workbook().save(workbook_path)

            real_temp_directory = tempfile.TemporaryDirectory
            profiles = []
            calls = []

            def tracked_temp_directory(*args, **kwargs):
                profile = real_temp_directory(*args, **kwargs)
                profiles.append(Path(profile.name))
                return profile

            def fake_run(command, **kwargs):
                profile_dir = profiles[-1]
                self.assertIn(profile_flag(profile_dir), command)
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(profile_dir.stat().st_mode), 0o700)
                macro_file = (
                    profile_dir / "user" / "basic" / "Standard" / "Module1.xba"
                )
                if "--terminate_after_init" in command:
                    self.assertFalse(macro_file.exists())
                else:
                    self.assertEqual(
                        macro_file.read_text(), self.xlsx.RECALCULATE_MACRO
                    )
                calls.append((list(command), profile_dir))
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(
                self.xlsx.tempfile,
                "TemporaryDirectory",
                side_effect=tracked_temp_directory,
            ), patch.object(
                self.xlsx.subprocess, "run", side_effect=fake_run
            ), patch.object(
                self.xlsx, "get_soffice_env", return_value={}
            ), patch.object(
                self.xlsx.platform, "system", return_value="Linux"
            ):
                first_result = self.xlsx.recalc(str(workbook_path))
                second_result = self.xlsx.recalc(str(workbook_path))

            self.assertEqual(first_result["status"], "success")
            self.assertEqual(first_result["total_formulas"], 0)
            self.assertEqual(second_result["status"], "success")
            self.assertEqual(len(profiles), 2)
            self.assertNotEqual(profiles[0], profiles[1])
            self.assertEqual(len(calls), 4)
            self.assertEqual(calls[0][1], calls[1][1])
            self.assertEqual(calls[2][1], calls[3][1])
            self.assertFalse(profiles[0].exists())
            self.assertFalse(profiles[1].exists())

            for call_index in (1, 3):
                command, profile_dir = calls[call_index]
                soffice_index = command.index("soffice")
                self.assertEqual(
                    command[soffice_index:],
                    [
                        "soffice",
                        "--headless",
                        profile_flag(profile_dir),
                        "--norestore",
                        XLSX_SCRIPT_URI,
                        str(workbook_path.absolute()),
                    ],
                )

    def test_docx_accept_changes_uses_private_profile_and_preserves_copy(self):
        with tempfile.TemporaryDirectory() as work_dir:
            input_path = Path(work_dir) / "input.docx"
            output_path = Path(work_dir) / "output" / "accepted.docx"
            input_path.write_bytes(b"mock docx input")

            real_temp_directory = tempfile.TemporaryDirectory
            profiles = []
            calls = []

            def tracked_temp_directory(*args, **kwargs):
                profile = real_temp_directory(*args, **kwargs)
                profiles.append(Path(profile.name))
                return profile

            def fake_run(command, **kwargs):
                profile_dir = profiles[-1]
                self.assertIn(profile_flag(profile_dir), command)
                if os.name != "nt":
                    self.assertEqual(stat.S_IMODE(profile_dir.stat().st_mode), 0o700)
                macro_file = (
                    profile_dir / "user" / "basic" / "Standard" / "Module1.xba"
                )
                if "--terminate_after_init" in command:
                    self.assertFalse(macro_file.exists())
                else:
                    self.assertEqual(
                        macro_file.read_text(), self.docx.ACCEPT_CHANGES_MACRO
                    )
                calls.append((list(command), profile_dir))
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(
                self.docx.tempfile,
                "TemporaryDirectory",
                side_effect=tracked_temp_directory,
            ), patch.object(
                self.docx.subprocess, "run", side_effect=fake_run
            ), patch.object(self.docx, "get_soffice_env", return_value={}):
                _, message = self.docx.accept_changes(
                    str(input_path), str(output_path)
                )

            self.assertIn("Successfully accepted all tracked changes", message)
            self.assertEqual(output_path.read_bytes(), input_path.read_bytes())
            self.assertEqual(len(profiles), 1)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][1], calls[1][1])
            self.assertFalse(profiles[0].exists())
            self.assertTrue(any("--terminate_after_init" in cmd for cmd, _ in calls))
            macro_calls = [call for call, _ in calls if DOCX_SCRIPT_URI in call]
            self.assertEqual(len(macro_calls), 1)
            command = macro_calls[0]
            self.assertEqual(
                command,
                [
                    "soffice",
                    "--headless",
                    profile_flag(profiles[0]),
                    "--norestore",
                    DOCX_SCRIPT_URI,
                    str(output_path.absolute()),
                ],
            )


if __name__ == "__main__":
    unittest.main()
