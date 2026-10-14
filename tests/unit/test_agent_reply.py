"""Presentation partition validation; neither field carries consent authority."""

import pytest
from pydantic import ValidationError

from src.domain.interactions.reply import AgentReply


def test_reply_preserves_both_fields_when_there_is_no_core_block() -> None:
    reply = AgentReply(answer=" Consulta. ", proposal_text=" Propuesta. ")
    assert reply.text() == "Consulta.\n\nPropuesta."
    assert AgentReply(answer="", proposal_text="").text() == ""


@pytest.mark.parametrize(
    "content",
    [
        {},
        {"answer": "Hola"},
        {"answer": "Hola", "proposal_text": None},
        {"answer": 1, "proposal_text": ""},
        {"answer": "Hola", "proposal_text": "", "confirmed": True},
    ],
)
def test_reply_rejects_missing_fields_coercion_and_invented_authority(content) -> None:
    with pytest.raises(ValidationError):
        AgentReply.model_validate(content)
