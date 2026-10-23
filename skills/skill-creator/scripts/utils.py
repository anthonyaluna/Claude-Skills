"""Shared utilities for skill-creator scripts."""

from functools import lru_cache
from pathlib import Path
import re
import subprocess



MIN_RESTRICTED_CLAUDE_VERSION = (2, 1, 248)


@lru_cache(maxsize=1)
def require_restricted_claude_cli() -> None:
    """Fail closed unless the local CLI supports restricted evaluation mode."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Claude Code CLI 2.1.248 or later is required for restricted evaluation."
        ) from exc

    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", output)
    if result.returncode != 0 or not match:
        raise RuntimeError(
            "Could not verify the Claude Code CLI version required for restricted evaluation."
        )

    version = tuple(map(int, match.groups()))
    if version < MIN_RESTRICTED_CLAUDE_VERSION:
        raise RuntimeError(
            f"Claude Code CLI {match.group(0)} is too old; "
            "version 2.1.248 or later is required for restricted evaluation."
        )


def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    """Parse a SKILL.md file, returning (name, description, full_content)."""
    content = (skill_path / "SKILL.md").read_text()
    lines = content.split("\n")

    if lines[0].strip() != "---":
        raise ValueError("SKILL.md missing frontmatter (no opening ---)")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("SKILL.md missing frontmatter (no closing ---)")

    name = ""
    description = ""
    frontmatter_lines = lines[1:end_idx]
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if line.startswith("name:"):
            name = line[len("name:"):].strip().strip('"').strip("'")
        elif line.startswith("description:"):
            value = line[len("description:"):].strip()
            # Handle YAML multiline indicators (>, |, >-, |-)
            if value in (">", "|", ">-", "|-"):
                continuation_lines: list[str] = []
                i += 1
                while i < len(frontmatter_lines) and (frontmatter_lines[i].startswith("  ") or frontmatter_lines[i].startswith("\t")):
                    continuation_lines.append(frontmatter_lines[i].strip())
                    i += 1
                description = " ".join(continuation_lines)
                continue
            else:
                description = value.strip('"').strip("'")
        i += 1

    return name, description, content
