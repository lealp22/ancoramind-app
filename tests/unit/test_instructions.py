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

    def test_readable_dates_keep_precision_and_document_ids_are_explicit_only(self):
        text = "\n".join(assemble_instructions())
        assert "`YYYY-MM-DD HH:MM`" in text
        assert "retain non-zero seconds" in text
        assert "Midnight in an event or reminder still has a time" in text
        assert "not document UUIDs in normal replies" in text
        assert "only when the user explicitly requests that ID" in text
        assert "never use a filename as authorization" in text
        assert "If documents share a filename" in text
        assert "never permits\n  exposing internal user IDs" in text

    def test_returns_list_of_strings(self):
        """Should return a list of strings."""
        instructions = assemble_instructions()
        assert isinstance(instructions, list)
        # identity + soul + tool_contract + telegram + documents + vehicles
        # + calendar + todos + web search + export
        assert len(instructions) == 10
        assert all(isinstance(item, str) for item in instructions)

    def test_vehicle_skill_loaded(self):
        """The vehicles skill (registration + maintenance) should be included."""
        instructions = assemble_instructions()
        assert any("Vehicle Registration" in block for block in instructions)

    def test_document_skill_loaded(self):
        """The document skill must describe the Core-side ingestion, not a tool."""
        instructions = assemble_instructions()
        assert any("Adjuntos archivados antes de este turno" in block for block in instructions)

    def test_no_prompt_asks_the_agent_to_call_the_unregistered_ingestion_tool(self):
        """The Agent catalog has no ``analyze_document`` (commit 83b557e): a prompt that
        orders it makes the model blame a missing tool or end its run badly."""
        text = "\n".join(assemble_instructions())
        assert "MUST call `analyze_document`" not in text
        assert "`analyze_document` confirms" not in text
        assert "`get_document`, `analyze_document`" not in text

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

    def test_calendar_skill_loaded(self):
        """specs/023 T6.5: the calendar skill was written but never wired in
        until now — regression guard."""
        instructions = assemble_instructions()
        assert any("Skill — Calendar" in block for block in instructions)

    def test_web_search_skill_loaded(self):
        """The web-search policy must be visible to the conversational Agent."""
        instructions = assemble_instructions()
        assert any("Búsqueda web pública" in block for block in instructions)

    def test_export_skill_loaded(self):
        """BL-38 Fase 3: the export_document skill must be visible to the Agent."""
        instructions = assemble_instructions()
        assert any("Export to PDF" in block for block in instructions)

    def test_attachments_are_framed_as_data_not_instructions(self):
        """BL-39: attachment-derived data remains untrusted even after ingestion."""
        prompt_text = "\n".join(assemble_instructions())
        assert "images and files the user attaches directly" in prompt_text

    def test_document_extraction_skill_not_in_main_agent_instructions(self):
        """document_extraction.md is loaded by the separate extraction call
        (src/agent/document_extraction.py), not by the main agent (T6.5)."""
        prompt_text = "\n".join(assemble_instructions())
        assert "Document extraction — untrusted input" not in prompt_text

    def test_tool_catalogs_are_not_duplicated_in_prompt_text(self):
        """Tool schemas, not Markdown inventories, are the capability source of truth."""
        prompt_text = "\n".join(assemble_instructions())

        assert "## Available Tools" not in prompt_text
        assert "delete_document" not in prompt_text

    def test_confirmation_is_owned_by_core_not_the_agent(self):
        prompt_text = "\n".join(assemble_instructions())
        assert "`execute_*` tools are not available" in prompt_text
        assert "the Core validates human consent before the Agent" in prompt_text
        assert "Call `execute_" not in prompt_text
        assert "Use `execute_" not in prompt_text

    def test_proposal_presentation_is_partitioned_and_discard_is_respected(self):
        prompt_text = "\n".join(assemble_instructions())
        assert "`answer` and `proposal_text`" in prompt_text
        assert "The Core replaces only `proposal_text`" in prompt_text
        assert "calling `present_reply`" in prompt_text
        assert "Call required domain tools and wait for their results first" in prompt_text
        assert "Both arguments cannot be empty" in prompt_text
        assert "otherwise discards it" in prompt_text
        assert "both strings may be empty" not in prompt_text
        assert (
            "Do not offer to re-propose a discarded action unless the user asks anew" in prompt_text
        )
        assert "Any statement about pending proposals" in prompt_text
        assert 'Ask for "Sí"' not in prompt_text
        assert "ask for explicit confirmation" not in prompt_text
        assert "Approved WRITE_TRIVIAL tools execute and audit immediately" in prompt_text

    def test_prompt_has_no_accidental_source_line_number(self):
        """A copied source-line prefix is noise, not a model instruction."""
        assert "77 |     descriptions" not in "\n".join(assemble_instructions())

    def test_terminal_tool_prompt_is_versioned_and_requires_real_domain_work(self):
        prompt = load_prompt("skills/presentation.md")
        assert "`list_todo_lists`" in prompt
        assert "`list_todo_items`" in prompt
        assert '`propose_todo_list(name="Casa")`' in prompt
        assert "never in the same batch as another tool" in prompt
        assert "no later background work" in prompt
