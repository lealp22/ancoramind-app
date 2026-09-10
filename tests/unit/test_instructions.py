"""Unit tests for instruction assembly."""

import pytest

from src.agent.instructions import assemble_instructions, load_prompt


class TestLoadPrompt:
    """Tests for loading individual prompt files."""

    def test_loads_identity(self):
        """Should load identity.md."""
        content = load_prompt("identity.md")
        assert "AncoraMind" in content
        assert len(content) > 0

    def test_loads_soul(self):
        """Should load soul.md."""
        content = load_prompt("soul.md")
        # .lower() comparison — note: "ai" is lowercase after lower()
        assert "personal ai assistant" in content.lower()
        assert len(content) > 0

    def test_loads_tool_contract(self):
        """Should load tool_contract.md."""
        content = load_prompt("tool_contract.md")
        assert "Tool" in content
        assert len(content) > 0

    def test_loads_telegram_channel(self):
        """Should load channels/telegram.md."""
        content = load_prompt("channels/telegram.md")
        assert "Telegram" in content
        assert len(content) > 0

    def test_missing_file_raises(self):
        """Should raise FileNotFoundError for non-existent prompt."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent.md")


class TestAssembleInstructions:
    """Tests for assembling the full instruction context."""

    def test_returns_list_of_strings(self):
        """Should return a list of strings."""
        instructions = assemble_instructions()
        assert isinstance(instructions, list)
        # identity + soul + tool_contract + telegram + documents + vehicles + todos
        assert len(instructions) == 7
        assert all(isinstance(item, str) for item in instructions)

    def test_vehicle_skill_loaded(self):
        """The vehicles skill (registration + maintenance) should be included."""
        instructions = assemble_instructions()
        assert any("Vehicle Registration" in block for block in instructions)

    def test_document_skill_loaded(self):
        """The document ingestion contract should be included."""
        instructions = assemble_instructions()
        assert any(
            "MUST call `analyze_document` exactly once" in block
            for block in instructions
        )

    def test_identity_is_first(self):
        """Identity block should be first."""
        instructions = assemble_instructions()
        assert "AncoraMind" in instructions[0]

    def test_soul_is_second(self):
        """Soul block should be second."""
        instructions = assemble_instructions()
        assert "personal ai assistant" in instructions[1].lower()

    def test_no_empty_blocks(self):
        """No instruction block should be empty."""
        instructions = assemble_instructions()
        for block in instructions:
            assert len(block.strip()) > 0, "Empty block found in instructions"

    def test_todos_skill_loaded(self):
        """The todos skill (lists + items) should be included."""
        instructions = assemble_instructions()
        assert any("Todo Lists" in block for block in instructions)
