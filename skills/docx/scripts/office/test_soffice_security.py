import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
SOFFICE_MODULES = (
    REPO_ROOT / "skills/docx/scripts/office/soffice.py",
    REPO_ROOT / "skills/pptx/scripts/office/soffice.py",
    REPO_ROOT / "skills/xlsx/scripts/office/soffice.py",
)


def load_module(index, path):
    spec = importlib.util.spec_from_file_location(f"soffice_test_{index}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShimPathSecurityTests(unittest.TestCase):
    def test_shim_uses_private_directory_and_ignores_legacy_path(self):
        for index, module_path in enumerate(SOFFICE_MODULES):
            with self.subTest(module=module_path):
                with tempfile.TemporaryDirectory() as temp_root:
                    legacy_shim = Path(temp_root) / "lo_socket_shim.so"
                    legacy_shim.write_bytes(b"untrusted legacy shim")
                    module = load_module(index, module_path)

                    def fake_compile(args, **kwargs):
                        output_path = Path(args[args.index("-o") + 1])
                        output_path.write_bytes(b"test shim")
                        return subprocess.CompletedProcess(args, 0)

                    with patch.object(
                        module.tempfile, "gettempdir", return_value=temp_root
                    ), patch.object(
                        module.subprocess, "run", side_effect=fake_compile
                    ) as compile_call:
                        shim_path = module._ensure_shim()
                        self.addCleanup(module._SHIM_TEMP_DIR.cleanup)
                        self.assertEqual(module._ensure_shim(), shim_path)

                    self.assertEqual(compile_call.call_count, 1)
                    self.assertNotEqual(shim_path, legacy_shim)
                    self.assertEqual(shim_path.read_bytes(), b"test shim")
                    self.assertEqual(legacy_shim.read_bytes(), b"untrusted legacy shim")
                    self.assertEqual(shim_path.parent.parent, Path(temp_root))
                    self.assertFalse(shim_path.with_suffix(".c").exists())
                    if os.name != "nt":
                        self.assertEqual(
                            stat.S_IMODE(shim_path.parent.stat().st_mode), 0o700
                        )

    def test_concurrent_shim_initialization_compiles_once(self):
        for index, module_path in enumerate(SOFFICE_MODULES):
            with self.subTest(module=module_path):
                with tempfile.TemporaryDirectory() as temp_root:
                    module = load_module(index + 10, module_path)
                    compile_started = threading.Event()
                    second_compile_started = threading.Event()
                    second_attempt_started = threading.Event()
                    allow_compile_to_finish = threading.Event()
                    compile_calls = []
                    results = []
                    errors = []

                    def fake_compile(args, **kwargs):
                        compile_calls.append(args)
                        if len(compile_calls) == 1:
                            compile_started.set()
                            allow_compile_to_finish.wait(timeout=5)
                        else:
                            second_compile_started.set()
                        output_path = Path(args[args.index("-o") + 1])
                        output_path.write_bytes(b"test shim")
                        return subprocess.CompletedProcess(args, 0)

                    def initialize():
                        try:
                            results.append(module._ensure_shim())
                        except Exception as error:
                            errors.append(error)

                    def initialize_second():
                        second_attempt_started.set()
                        initialize()

                    with patch.object(
                        module.tempfile, "gettempdir", return_value=temp_root
                    ), patch.object(
                        module.subprocess, "run", side_effect=fake_compile
                    ):
                        first = threading.Thread(target=initialize)
                        second = threading.Thread(target=initialize_second)
                        first.start()
                        self.assertTrue(compile_started.wait(timeout=5))
                        second.start()
                        self.assertTrue(second_attempt_started.wait(timeout=5))
                        self.assertFalse(second_compile_started.wait(timeout=0.5))
                        allow_compile_to_finish.set()
                        first.join(timeout=5)
                        second.join(timeout=5)

                    if module._SHIM_TEMP_DIR is not None:
                        self.addCleanup(module._SHIM_TEMP_DIR.cleanup)
                    self.assertFalse(first.is_alive())
                    self.assertFalse(second.is_alive())
                    self.assertFalse(errors, errors)
                    self.assertEqual(len(compile_calls), 1)
                    self.assertEqual(len(results), 2)
                    self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
