"""Agent instruction assembly — loads modular prompt files.

Returns a list of strings for the Agno Agent `instructions` parameter.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def assemble_instructions() -> list[str]:
    """Assemble the agent instruction context as a list of strings.

    Each markdown file becomes one instruction block.
    Agno sends all blocks to the model as the system message.

    Order matters: later sections can override earlier context implicitly.
    """
    instructions: list[str] = []

    # Core identity and personality
    instructions.append(load_prompt("identity.md"))
    instructions.append(load_prompt("soul.md"))

    # Tool usage rules
    instructions.append(load_prompt("tool_contract.md"))

    # Channel-specific policies
    instructions.append(load_prompt("channels/telegram.md"))

    # Skills — add as domains are implemented
    instructions.append(load_prompt("skills/documents.md"))
    instructions.append(load_prompt("skills/vehicle_maintenance.md"))
    instructions.append(load_prompt("skills/todos.md"))

    return instructions
