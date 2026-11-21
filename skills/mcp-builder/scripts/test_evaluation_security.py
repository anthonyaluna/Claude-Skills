import importlib
import importlib.util
import io
import re
import sys
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


if importlib.util.find_spec("anthropic") is None:
    anthropic_stub = types.ModuleType("anthropic")
    anthropic_stub.Anthropic = type("Anthropic", (), {})
    sys.modules["anthropic"] = anthropic_stub

connections_stub = types.ModuleType("connections")
connections_stub.create_connection = lambda **kwargs: None
sys.modules["connections"] = connections_stub

evaluation = importlib.import_module("evaluation")


class FakeToolUse:
    type = "tool_use"

    def __init__(self, name):
        self.id = "toolu_test"
        self.name = name
        self.input = {}


class FakeText:
    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)

    def create(self, **kwargs):
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


class FakeConnection:
    def __init__(self):
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return "read result"


class EvaluationToolPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_requires_explicit_allowlist(self):
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["evaluation.py", "evaluation.xml"]):
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as error:
                    await evaluation.main()

        self.assertEqual(error.exception.code, 2)
        self.assertIn("--allow-tool", stderr.getvalue())

    def test_only_explicitly_allowlisted_tools_are_exposed(self):
        tools = [
            {"name": "read_record", "input_schema": {}},
            {"name": "delete_record", "input_schema": {}},
        ]

        self.assertEqual(
            evaluation.select_allowlisted_tools(tools, ["read_record"]),
            [tools[0]],
        )

    def test_unknown_or_empty_allowlist_fails_closed(self):
        tools = [{"name": "read_record", "input_schema": {}}]

        with self.assertRaisesRegex(ValueError, "not advertised"):
            evaluation.select_allowlisted_tools(tools, ["missing_tool"])

        with self.assertRaisesRegex(ValueError, "at least one"):
            evaluation.select_allowlisted_tools(tools, [])

    def test_duplicate_selected_tool_names_fail_closed(self):
        tools = [
            {"name": "read_record", "input_schema": {"type": "object"}},
            {"name": "read_record", "input_schema": {"type": "object"}},
            {"name": "delete_record", "input_schema": {"type": "object"}},
        ]

        with self.assertRaisesRegex(ValueError, "duplicate advertised"):
            evaluation.select_allowlisted_tools(tools, ["read_record"])

    def test_unselected_duplicate_names_do_not_block_allowlisted_tool(self):
        tools = [
            {"name": "read_record", "input_schema": {"type": "object"}},
            {"name": "delete_record", "input_schema": {"type": "object"}},
            {"name": "delete_record", "input_schema": {"type": "object"}},
        ]

        self.assertEqual(
            evaluation.select_allowlisted_tools(tools, ["read_record"]),
            [tools[0]],
        )

    async def test_unallowlisted_model_tool_call_never_reaches_connection(self):
        client = FakeClient(
            [
                FakeResponse([FakeToolUse("delete_record")], "tool_use"),
                FakeResponse([FakeText("<response>ok</response>")], "end_turn"),
            ]
        )
        connection = FakeConnection()
        with self.assertRaisesRegex(PermissionError, "not allowlisted"):
            await evaluation.agent_loop(
                client=client,
                model="test-model",
                question="Read one record",
                tools=[{"name": "read_record", "input_schema": {}}],
                connection=connection,
                allowed_tool_names={"read_record"},
            )

        self.assertEqual(connection.calls, [])

    async def test_allowlisted_tool_call_still_works(self):
        client = FakeClient(
            [
                FakeResponse([FakeToolUse("read_record")], "tool_use"),
                FakeResponse([FakeText("<response>ok</response>")], "end_turn"),
            ]
        )
        connection = FakeConnection()
        result, metrics = await evaluation.agent_loop(
            client=client,
            model="test-model",
            question="Read one record",
            tools=[{"name": "read_record", "input_schema": {}}],
            connection=connection,
            allowed_tool_names={"read_record"},
        )

        self.assertEqual(result, "<response>ok</response>")
        self.assertEqual(connection.calls, [("read_record", {})])
        self.assertEqual(metrics["read_record"]["count"], 1)

    def test_documented_evaluation_commands_include_an_allowlist(self):
        reference = (
            Path(__file__).resolve().parents[1] / "reference" / "evaluation.md"
        ).read_text(encoding="utf-8")
        bash_blocks = re.findall(r"```bash\s*(.*?)```", reference, flags=re.DOTALL)
        evaluation_commands = [
            block for block in bash_blocks if "scripts/evaluation.py" in block
        ]

        self.assertTrue(evaluation_commands)
        for command in evaluation_commands:
            with self.subTest(command=command):
                self.assertIn("--allow-tool", command)


if __name__ == "__main__":
    unittest.main()
