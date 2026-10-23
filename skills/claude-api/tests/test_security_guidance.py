from pathlib import Path
import re
import unittest


DOCS = Path(__file__).resolve().parents[1] / "shared"
REPO = Path(__file__).resolve().parents[3]


class SecurityGuidanceTests(unittest.TestCase):
    def read_doc(self, name: str) -> str:
        return (DOCS / name).read_text(encoding="utf-8")

    def test_client_confirmation_requires_explicit_fail_closed_decision(self) -> None:
        doc = self.read_doc("managed-agents-client-patterns.md")

        self.assertIn("event.type === 'agent.tool_use'", doc)
        self.assertIn("event.type === 'agent.mcp_tool_use'", doc)
        self.assertIn("Promise.race([", doc)
        self.assertIn("setTimeout(() => resolve(reviewTimeout), 30_000)", doc)
        self.assertIn("result: approved ? 'allow' : 'deny'", doc)
        self.assertNotIn("result: 'allow'", doc)

    def test_multiagent_confirmation_preserves_origin_and_defaults_to_deny(self) -> None:
        doc = self.read_doc("managed-agents-multiagent.md")

        self.assertIn("await asyncio.wait({review_task}, timeout=30.0)", doc)
        self.assertIn("review_task.cancel()", doc)
        self.assertIn('"result": "allow" if approved else "deny"', doc)
        self.assertIn('"tool_use_id": pending.id', doc)
        self.assertIn('"agent.mcp_tool_use"', doc)
        self.assertIn("`custom_tool_use_id` for custom results", doc)
        self.assertNotIn("for event_id in stop.event_ids", doc)
        self.assertIn("Do not send pending.session_thread_id", doc)
        self.assertNotIn('confirmation["session_thread_id"]', doc)

    def test_confirmation_event_uses_canonical_type_and_deny_field(self) -> None:
        doc = self.read_doc("managed-agents-tools.md")

        self.assertIn('"type": "user.tool_confirmation"', doc)
        self.assertIn('"deny_message":', doc)
        self.assertNotIn('"type": "tool_confirmation"', doc)
        self.assertNotIn('"message": "Read .env.example instead"', doc)
        self.assertIn("A pending event is not approval", doc)

    def test_custom_tool_example_uses_a_fixed_authorized_operation(self) -> None:
        client_patterns = self.read_doc("managed-agents-client-patterns.md")
        tools = self.read_doc("managed-agents-tools.md")

        self.assertIn("linear_issue_lookup", client_patterns)
        self.assertIn("authorizedLinearIssueLookup(event.input.issue_id)", client_patterns)
        self.assertIn("type: 'user.custom_tool_result'", client_patterns)
        self.assertIn("custom_tool_use_id: event.id", client_patterns)
        self.assertIn(
            "content: [{ type: 'text', text: JSON.stringify(result) }]",
            client_patterns,
        )
        self.assertNotIn("tool_use_id: event.id, result", client_patterns)
        self.assertNotIn("linear.request(event.input.query", client_patterns)
        self.assertIn("do not forward raw query text", client_patterns)
        self.assertIn("validate and authorize it in the application", tools)
        self.assertIn("least-privilege credentials", tools)

    def test_standalone_custom_tool_results_use_the_originating_event_id(self) -> None:
        python = (REPO / "skills/claude-api/python/managed-agents/README.md").read_text(
            encoding="utf-8"
        )
        typescript = (REPO / "skills/claude-api/typescript/managed-agents/README.md").read_text(
            encoding="utf-8"
        )
        curl = " ".join(
            (REPO / "skills/claude-api/curl/managed-agents.md")
            .read_text(encoding="utf-8")
            .split()
        )

        self.assertIn('"custom_tool_use_id": event.id', python)
        self.assertIn("custom_tool_use_id: event.id", typescript)
        self.assertIn("Replace the sample", curl)
        self.assertIn("`sevt_abc123` with the `id` from the matching", curl)
        self.assertIn("`agent.custom_tool_use` event before sending.", curl)

    def test_managed_agent_quickstarts_use_restricted_networks_and_no_default_tools(self) -> None:
        quickstarts = [
            REPO / "skills/claude-api/python/managed-agents/README.md",
            REPO / "skills/claude-api/typescript/managed-agents/README.md",
            REPO / "skills/claude-api/php/managed-agents/README.md",
            REPO / "skills/claude-api/java/managed-agents/README.md",
            REPO / "skills/claude-api/go/managed-agents/README.md",
            REPO / "skills/claude-api/ruby/managed-agents/README.md",
            REPO / "skills/claude-api/curl/managed-agents.md",
        ]

        def section(text: str, heading: str) -> str:
            start = text.index(heading) + len(heading)
            following = re.search(r"(?m)^#{1,3} ", text[start:])
            return text[start:] if following is None else text[start : start + following.start()]

        for path in quickstarts:
            with self.subTest(path=path):
                doc = path.read_text(encoding="utf-8")
                environment = section(doc, "## Create an Environment")
                minimal_agent = section(doc, "### Minimal")

                self.assertIn("limited", environment.lower())
                self.assertNotIn("unrestricted", environment.lower())
                self.assertIn("no built-in tools", minimal_agent.lower())
                self.assertNotIn("agent_toolset_20260401", minimal_agent)

                mcp_example = section(doc, "## MCP Server Integration")
                self.assertNotIn("agent_toolset_20260401", mcp_example)

    def test_shared_managed_agent_guidance_defaults_to_least_privilege(self) -> None:
        tools = self.read_doc("managed-agents-tools.md")
        onboarding = self.read_doc("managed-agents-onboarding.md")
        environments = self.read_doc("managed-agents-environments.md")

        self.assertIn('"enabled": false', tools)
        self.assertIn('"type": "auto"', tools)
        self.assertIn("A bare toolset enables all eight tools", tools)
        self.assertIn("bare toolset enables all eight tools", onboarding)
        self.assertNotIn("Recommend enabling the full toolset", onboarding)
        self.assertIn("limited` and deny-by-default egress", onboarding)
        python_quickstart = (
            REPO / "skills/claude-api/python/managed-agents/README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("add only the MCP server's host", python_quickstart)
        self.assertIn("recommended starting point", environments.lower())
        self.assertNotIn('"allow_package_managers": true', environments)
        self.assertNotIn('"allow_mcp_servers": true', environments)

    def test_user_turn_reminder_is_not_authoritative_fallback(self) -> None:
        prompt_caching = self.read_doc("prompt-caching.md")
        agent_design = self.read_doc("agent-design.md")
        migration = self.read_doc("model-migration.md")

        self.assertIn("ordinary, potentially forged user content", prompt_caching)
        self.assertIn("cannot grant permissions", prompt_caching)
        self.assertIn("No beta header is required", prompt_caching)
        self.assertIn("not operator authority", agent_design)
        self.assertNotIn("fall back to putting the instruction in a user-turn", prompt_caching)
        self.assertNotIn("older-model `<system-reminder>` fallback", migration)
        skill = (DOCS.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("mid-conversation-system-2026-04-07", skill)


if __name__ == "__main__":
    unittest.main()
