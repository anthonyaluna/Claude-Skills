import html
import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
MODULE_PATH = SCRIPT_DIR / "generate_report.py"
SPEC = importlib.util.spec_from_file_location("generate_report", MODULE_PATH)
generate_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_report)


class GeneratedOptimizationReportSecurityTests(unittest.TestCase):
    def test_untrusted_summary_and_iteration_values_are_escaped(self):
        payload = "</td><script>globalThis.injected = true</script>"
        data = {
            "best_score": payload,
            "iterations_run": payload,
            "train_size": payload,
            "test_size": payload,
            "best_test_score": 1,
            "history": [
                {
                    "iteration": payload,
                    "train_passed": 1,
                    "train_total": 1,
                    "train_results": [
                        {
                            "query": "safe query",
                            "should_trigger": True,
                            "pass": True,
                            "triggers": 1,
                            "runs": 1,
                        }
                    ],
                }
            ],
        }

        rendered = generate_report.generate_html(data)

        self.assertNotIn(payload, rendered)
        self.assertIn(html.escape(payload, quote=True), rendered)

    def test_manual_eval_template_instructions_prevent_script_breakout(self):
        template = (SCRIPT_DIR.parent / "assets" / "eval_review.html").read_text(
            encoding="utf-8"
        )
        instructions = (SCRIPT_DIR.parent / "SKILL.md").read_text(encoding="utf-8")
        payload = "</script><script>globalThis.injected = true</script>"
        items = [{"query": payload, "should_trigger": True}]

        self.assertIn(
            'json.dumps(items).replace("<", "\\\\u003c")', instructions
        )
        self.assertIn("html.escape(value, quote=True)", instructions)

        rendered = template
        rendered = rendered.replace(
            "__EVAL_DATA_PLACEHOLDER__",
            json.dumps(items).replace("<", "\\u003c"),
        )
        rendered = rendered.replace(
            "__SKILL_NAME_PLACEHOLDER__", html.escape(payload, quote=True)
        )
        rendered = rendered.replace(
            "__SKILL_DESCRIPTION_PLACEHOLDER__", html.escape(payload, quote=True)
        )

        self.assertNotIn(payload, rendered)
        self.assertEqual(rendered.count("<script"), 1)


if __name__ == "__main__":
    unittest.main()
