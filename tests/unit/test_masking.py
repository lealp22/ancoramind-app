"""Unit tests for the shared sensitive-identifier detectors (ADR-007)."""

from __future__ import annotations

import pytest

from src.observability.masking import detect_sensitive, mask_sensitive


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("tarjeta 4539 1488 0343 6467", "card"),
        ("tarjeta 4539-1488-0343-6467", "card"),
        ("mi DNI es 12345678Z", "dni"),
        ("dni 12345678-Z", "dni"),
        ("NIE X1234567L", "nie"),
        ("IBAN ES91 2100 0418 4502 0005 1332", "iban"),
        ("matrícula 1234 BCD", "plate"),
        ("matrícula M-1234-AB", "plate"),
        ("bastidor WVWZZZ1JZXW000001", "vin"),
        ("escribe a persona@example.com", "email"),
        ("llama al +34 612 345 678", "phone"),
        ("ref 12345678", "number"),
        ("ref 123456789012", "phone"),
        ("clave tvly-abcdef1234567890", "token"),
        ("token ghp_abcdefghijklmnop1234", "token"),
        ("cabecera eyJhbGciOiJIUzI1NiJ9abc", "token"),
    ],
)
def test_detects_valid_identifiers(text: str, kind: str) -> None:
    assert kind in detect_sensitive(text)


@pytest.mark.parametrize(
    "text",
    [
        "tarjeta 4539 1488 0343 6468",  # Luhn inválido
        "dni 12345678A",  # letra de control incorrecta
        "NIE X1234567A",  # letra de control incorrecta
        "IBAN ES00 2100 0418 4502 0005 1332",  # módulo 97 inválido
        "matrícula 1234 AEI",  # vocales no válidas en matrículas actuales
        "bastidor IIIIIIIIIIIIIIIII",  # sin dígitos ni I/O/Q válidos
    ],
)
def test_ignores_invalid_identifiers(text: str) -> None:
    kinds = detect_sensitive(text)
    assert not kinds & {"card", "dni", "nie", "iban", "plate", "vin"}


@pytest.mark.parametrize(
    "text",
    [
        "qué es la inflación",
        "historia de la Revolución Francesa en 1789",
        "tiempo en Madrid mañana",
        "qué pasó el 11 de septiembre de 2001",
        "precio del iPhone 15 Pro Max en 2024",
        "población de España 48 millones",
        "ley 40/2015 de régimen jurídico",
        "Real Decreto 1090/2015",
        "qué significa la sigla ABS en coches",
        "Python 3.12 novedades",
    ],
)
def test_everyday_spanish_text_has_no_false_positives(text: str) -> None:
    assert detect_sensitive(text) == frozenset()


def test_mask_replaces_with_typed_markers_without_digits() -> None:
    masked = mask_sensitive("DNI 12345678Z, correo a@b.es, tarjeta 4539 1488 0343 6467")

    assert "[DNI]" in masked
    assert "[EMAIL]" in masked
    assert "[TARJETA]" in masked
    assert not any(ch.isdigit() for ch in masked)


def test_mask_leaves_clean_text_unchanged() -> None:
    assert mask_sensitive("qué es la inflación") == "qué es la inflación"
