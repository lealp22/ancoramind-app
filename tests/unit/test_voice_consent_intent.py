"""V22/V23: phrase classification is neither channel evidence nor permission."""

import pytest

from src.domain.interactions.consent_intent import parse_consent_intent
from src.domain.speech.consent import VoiceConsentIntent, parse_voice_consent_intent


@pytest.mark.parametrize("text", ["Sí", "si", "SI", "Sí.", "¡Sí!", " Si "])
def test_v22_isolated_yes(text):
    assert parse_voice_consent_intent(text) is VoiceConsentIntent.CONFIRM


@pytest.mark.parametrize("text", ["No", "no", "NO", "No.", "¡No!", " No "])
def test_v22_isolated_no(text):
    assert parse_voice_consent_intent(text) is VoiceConsentIntent.DISCARD


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        " ",
        "dijo sí",
        "sí y borra",
        "«Sí»",
        '"Sí"',
        "no sé",
        "/new",
        "/help",
        "Sí\n",
        "Sí\t",
        "No\nNo",
        "Sí!!",
        "No...",
        "Sí,",
        "Sí\u200b",
        "Sí aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "consent:confirm:fake",
        "Sí." * 100,
    ],
)
def test_v23_extra_content_is_never_a_consent_intent(text):
    assert parse_voice_consent_intent(text) is None


def test_voice_parser_does_not_change_written_consent_ux():
    assert parse_consent_intent("No") is None
    assert parse_consent_intent("Sí aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") is not None
    assert parse_voice_consent_intent("Sí aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee") is None
