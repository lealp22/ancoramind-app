"""Text UX only: parsing must never be mistaken for authenticated consent."""

from uuid import UUID

import pytest

from src.domain.interactions.consent_intent import ConsentIntent, parse_consent_intent

PROPOSAL_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.mark.parametrize("text", ["Sí", "sí", "SI", "Sí.", "¡Sí!", " Si "])
def test_isolated_yes_is_an_unbound_intent(text: str) -> None:
    assert parse_consent_intent(text) == ConsentIntent(proposal_id=None)


@pytest.mark.parametrize(
    "text",
    [
        f"Sí {PROPOSAL_ID}",
        f"si {str(PROPOSAL_ID).upper()}",
        f"¡Sí {PROPOSAL_ID}!",
    ],
)
def test_explicit_id_is_only_a_candidate_intent(text: str) -> None:
    assert parse_consent_intent(text) == ConsentIntent(proposal_id=PROPOSAL_ID)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "Sí, ejecuta todo",
        "Sí y borra la lista",
        "Dijo: Sí",
        "«Sí»",
        "\"Sí\"",
        "Sí\nSí",
        "Sí\t",
        f"Sí {PROPOSAL_ID} y otra",
        f"Sí {PROPOSAL_ID} {PROPOSAL_ID}",
        "Sí 1234",
        f"Sí {str(PROPOSAL_ID).replace('-', '')}",
        "Sí." * 100,
        # Unicode case-folding look-alikes of "i"/"s" must not read as a "Sí".
        "Sı",
        "Sİ",
        "ſi",
        "Ki",
    ],
)
def test_quotes_extra_content_and_bad_identifiers_are_not_intents(text: str | None) -> None:
    assert parse_consent_intent(text) is None
