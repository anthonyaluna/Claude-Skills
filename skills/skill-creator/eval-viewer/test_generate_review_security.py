import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).with_name("generate_review.py")
SPEC = importlib.util.spec_from_file_location("generate_review", MODULE_PATH)
generate_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_review)


class GeneratedReviewSecurityTests(unittest.TestCase):
    def _mark_paths_as_links(self, *paths: Path):
        marked = {path.absolute() for path in paths}
        return patch.object(
            generate_review,
            "_is_link_or_reparse_point",
            side_effect=lambda path: path.absolute() in marked,
        )

    def test_reparse_point_attribute_is_rejected(self):
        path = Path("reparse-point")
        file_attributes = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        fake_stat = type(
            "FakeStat",
            (),
            {"st_mode": stat.S_IFREG, "st_file_attributes": file_attributes},
        )()

        with patch.object(Path, "lstat", return_value=fake_stat):
            is_link = generate_review._is_link_or_reparse_point(path)

        self.assertTrue(is_link)

    def test_workspace_path_rejects_paths_outside_the_selected_root(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            root.mkdir()
            external_path = Path(temporary_directory) / "secret.txt"

            safe_path = generate_review._safe_workspace_path(root, external_path)

        self.assertIsNone(safe_path)

    def test_open_rejects_a_file_replaced_between_check_and_open(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "workspace"
            root.mkdir()
            workspace_file = root / "result.txt"
            workspace_file.write_text("workspace", encoding="utf-8")
            external_file = base / "external.txt"
            external_file.write_text("external", encoding="utf-8")
            real_open = os.open

            def open_external_file(path, flags, mode=0o777):
                return real_open(external_file, flags, mode)

            with patch.object(generate_review.os, "open", side_effect=open_external_file):
                with self.assertRaises(OSError):
                    generate_review._open_workspace_file(
                        root, workspace_file, os.O_RDONLY
                    )

            self.assertEqual(external_file.read_text(encoding="utf-8"), "external")

    def test_open_rejects_a_linked_parent_added_between_check_and_open(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "workspace"
            linked_parent = root / "run"
            linked_parent.mkdir(parents=True)
            workspace_file = linked_parent / "result.txt"
            workspace_file.write_text("workspace", encoding="utf-8")
            external_file = base / "external.txt"
            external_file.write_text("external", encoding="utf-8")
            real_open = os.open
            real_is_link = generate_review._is_link_or_reparse_point
            link_checks = 0

            def mark_parent_after_first_check(path):
                nonlocal link_checks
                if path.absolute() == linked_parent.absolute():
                    link_checks += 1
                    return link_checks > 1
                return real_is_link(path)

            def open_external_file(path, flags, mode=0o777):
                return real_open(external_file, flags, mode)

            with (
                patch.object(
                    generate_review,
                    "_is_link_or_reparse_point",
                    side_effect=mark_parent_after_first_check,
                ),
                patch.object(generate_review.os, "open", side_effect=open_external_file),
            ):
                with self.assertRaises(OSError):
                    generate_review._open_workspace_file(
                        root, workspace_file, os.O_RDONLY
                    )

            self.assertEqual(external_file.read_text(encoding="utf-8"), "external")

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

    def test_run_discovery_does_not_follow_directory_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "workspace"
            root.mkdir()
            linked_run = root / "linked-run"
            (linked_run / "outputs").mkdir(parents=True)
            (linked_run / "outputs" / "result.txt").write_text(
                "secret", encoding="utf-8"
            )

            with self._mark_paths_as_links(linked_run):
                runs = generate_review.find_runs(root)

        self.assertEqual(runs, [])

    def test_run_does_not_embed_symlinked_output_or_metadata(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "workspace"
            run_dir = root / "run-1"
            (run_dir / "outputs").mkdir(parents=True)
            external_prompt = base / "external-prompt.json"
            external_prompt.write_text(
                json.dumps({"prompt": "outside prompt", "eval_id": 1}),
                encoding="utf-8",
            )
            external_output = base / "external-output.txt"
            external_output.write_text("outside output", encoding="utf-8")
            metadata_path = run_dir / "eval_metadata.json"
            grading_path = run_dir / "grading.json"
            output_path = run_dir / "outputs" / "result.txt"
            metadata_path.write_text(external_prompt.read_text(encoding="utf-8"))
            grading_path.write_text(external_prompt.read_text(encoding="utf-8"))
            output_path.write_text(external_output.read_text(encoding="utf-8"))

            with self._mark_paths_as_links(metadata_path, grading_path, output_path):
                run = generate_review.build_run(root, run_dir)

        self.assertEqual(run["prompt"], "(No prompt found)")
        self.assertIsNone(run["grading"])
        self.assertEqual(run["outputs"], [])

    def test_previous_iteration_does_not_read_symlinked_feedback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            workspace = base / "workspace"
            workspace.mkdir()
            external_feedback = base / "external-feedback.json"
            external_feedback.write_text(
                json.dumps(
                    {"reviews": [{"run_id": "run-1", "feedback": "outside secret"}]}
                ),
                encoding="utf-8",
            )
            feedback_path = workspace / "feedback.json"
            feedback_path.write_text(external_feedback.read_text(encoding="utf-8"))

            with self._mark_paths_as_links(feedback_path):
                previous = generate_review.load_previous_iteration(workspace)

        self.assertEqual(previous, {})

    def test_feedback_post_refuses_a_symlink_target(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            workspace = base / "workspace"
            workspace.mkdir()
            external_feedback = base / "external-feedback.json"
            external_feedback.write_text("original", encoding="utf-8")
            feedback_path = workspace / "feedback.json"
            feedback_path.write_text("original", encoding="utf-8")

            handler = generate_review.ReviewHandler.__new__(
                generate_review.ReviewHandler
            )
            handler.workspace = workspace
            handler.feedback_path = feedback_path
            body = b'{"reviews":[]}'
            handler.path = "/api/feedback"
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = io.BytesIO(body)
            handler.wfile = io.BytesIO()
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.send_error = Mock()

            with self._mark_paths_as_links(feedback_path):
                handler.do_POST()

            self.assertEqual(external_feedback.read_text(encoding="utf-8"), "original")
            self.assertEqual(feedback_path.read_text(encoding="utf-8"), "original")

        handler.send_error.assert_called_once_with(
            403, "Feedback path must not contain links"
        )

    def test_feedback_get_does_not_read_a_symlink_target(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory) / "workspace"
            workspace.mkdir()
            feedback_path = workspace / "feedback.json"
            feedback_path.write_text('{"reviews":[]}', encoding="utf-8")

            handler = generate_review.ReviewHandler.__new__(
                generate_review.ReviewHandler
            )
            handler.workspace = workspace
            handler.feedback_path = feedback_path
            handler.path = "/api/feedback"
            handler.wfile = io.BytesIO()
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()

            with self._mark_paths_as_links(feedback_path):
                handler.do_GET()

            response_body = handler.wfile.getvalue()

        self.assertEqual(response_body, b"{}")


if __name__ == "__main__":
    unittest.main()
