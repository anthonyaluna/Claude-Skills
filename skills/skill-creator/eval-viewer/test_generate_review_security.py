import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("generate_review.py")
SPEC = importlib.util.spec_from_file_location("generate_review", MODULE_PATH)
generate_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_review)


class GeneratedReviewSecurityTests(unittest.TestCase):
    def test_workspace_text_cannot_close_the_embedded_script_element(self):
        payload = "</script><script>globalThis.injected = true</script>"
        runs = [
            {
                "id": "run-1",
                "prompt": payload,
                "outputs": [
                    {"name": "result.txt", "type": "text", "content": payload}
                ],
                "grading": None,
            }
        ]

        html = generate_review.generate_html(runs, "example-skill")

        self.assertNotIn(payload, html)
        self.assertIn(r"\u003c/script>", html)

    def test_oversized_output_is_not_embedded(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "large.xlsx"
            output_path.write_bytes(
                b"x" * (generate_review.MAX_OUTPUT_FILE_BYTES + 1)
            )

            output = generate_review.embed_file(output_path)

        self.assertEqual(output["type"], "error")
        self.assertNotIn("data_b64", output)
        self.assertIn("inline review limit", output["content"])

    def test_workspace_byte_and_file_budgets_bound_output_embedding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "result.txt"
            output_path.write_text("too large for this budget", encoding="utf-8")
            budget = {"remaining_bytes": 4, "remaining_files": 1}

            output = generate_review.embed_file(output_path, budget)

        self.assertEqual(output["type"], "error")
        self.assertEqual(budget, {"remaining_bytes": 0, "remaining_files": 0})

    def test_run_file_limit_reports_omitted_outputs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dir = root / "run"
            outputs_dir = run_dir / "outputs"
            outputs_dir.mkdir(parents=True)
            (outputs_dir / "one.txt").write_text("one", encoding="utf-8")
            (outputs_dir / "two.txt").write_text("two", encoding="utf-8")

            with patch.object(generate_review, "MAX_OUTPUT_FILES_PER_RUN", 1):
                run = generate_review.build_run(
                    root,
                    run_dir,
                    {"remaining_bytes": 100, "remaining_files": 10},
                )

        self.assertEqual(len(run["outputs"]), 2)
        self.assertEqual(run["outputs"][-1]["name"], "Additional outputs omitted")


if __name__ == "__main__":
    unittest.main()
