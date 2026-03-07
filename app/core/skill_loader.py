from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Skill:
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    instructions: str = ""
    source_path: str = ""

    def to_tool_definition(self) -> dict:
        """Convert this skill into a tool definition for the LLM."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_request": {
                            "type": "string",
                            "description": "The user's request or instructions for this skill, in natural language",
                        }
                    },
                    "required": ["user_request"],
                },
            },
        }


def parse_skill(file_path: Path) -> Skill:
    """Parse a Markdown skill file with YAML frontmatter."""
    text = file_path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise ValueError(f"Skill file {file_path} missing YAML frontmatter")

    _, frontmatter_raw, *body_parts = text.split("---", 2)
    meta = yaml.safe_load(frontmatter_raw)
    body = "---".join(body_parts).strip()

    return Skill(
        name=meta["name"],
        description=meta.get("description", ""),
        tools=meta.get("tools", []),
        instructions=body,
        source_path=str(file_path),
    )


def load_skills(skills_dir: str | None = None) -> dict[str, Skill]:
    """Scan the skills directory and return a dict of name -> Skill."""
    if skills_dir is None:
        skills_dir = os.path.join(os.path.dirname(__file__), "..", "..", "skills")
    skills_dir = os.path.abspath(skills_dir)

    skills: dict[str, Skill] = {}
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        return skills

    for md_file in skills_path.glob("*.md"):
        try:
            skill = parse_skill(md_file)
            skills[skill.name] = skill
        except Exception as e:
            print(f"Warning: failed to load skill from {md_file}: {e}")

    return skills
