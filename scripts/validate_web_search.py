"""Manual local validation of the governed web-search tool (specs/025, no Telegram).

Run from the repository root with ``TAVILY_API_KEY`` in ``.env``::

    python -m scripts.validate_web_search          # offline policy/error checks
    python -m scripts.validate_web_search --live   # + one real Tavily search (1 credit)

Exercises the real ``search_web`` tool and ``WebSearchService``, not the Agent.
Rejection checks use a counting stub, so they never reach Tavily. Error checks use
an invalid key, which Tavily rejects without charging. Only ``--live`` spends one
credit. The API key is never printed, and the run fails if it, the query or a
snippet shows up in captured logs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime

from agno.run import RunContext

import src.agent.tools.web_search as web_tool
from src.config import Settings
from src.domain.web_search.models import WebSearchOutcome, WebSearchRequest
from src.domain.web_search.service import WebSearchService

LIVE_QUERY = "¿Qué es la inflación?"
SENSITIVE_QUERIES = {
    "DNI": "dni 12345678Z",
    "tarjeta": "tarjeta 4539 1488 0343 6467",
    "email": "contacta persona@example.com",
    "teléfono": "llama al +34 612 345 678",
    "matrícula": "matrícula 1234 BCD",
    "IBAN": "IBAN ES91 2100 0418 4502 0005 1332",
}
REJECTION_MESSAGE = "No puedo enviar posibles datos personales o sensibles"
UNAVAILABLE_MESSAGE = "La búsqueda web no está disponible ahora"
NOT_CONFIGURED_MESSAGE = "La búsqueda web no está configurada"


class _CountingPort:
    """Provider stub: records calls and returns nothing."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, request: WebSearchRequest) -> WebSearchOutcome:
        self.calls += 1
        return WebSearchOutcome(provider="stub", results=(), retrieved_at=datetime.now(tz=UTC))


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


class _Report:
    def __init__(self) -> None:
        self.failures = 0
        self.output: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        self.failures += 0 if ok else 1
        line = f"[{'OK' if ok else 'FALLO'}] {label}" + (f" — {detail}" if detail else "")
        self.output.append(line)
        print(line)

    def note(self, text: str) -> None:
        self.output.append(text)
        print(text)


def _run_context() -> RunContext:
    return RunContext(run_id="validate-web", session_id="validate:web", user_id="validate-user")


def _records(reply: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    payload = json.loads(reply.split("\n", 1)[1])
    return payload, payload["records"]


async def _check_rejections(settings: Settings, report: _Report) -> None:
    report.note("\n== Rechazo local de datos sensibles (sin llamar a Tavily) ==")
    port = _CountingPort()
    web_tool._service = WebSearchService(port, max_results=5, cache_ttl_seconds=0)
    for label, query in SENSITIVE_QUERIES.items():
        reply = await web_tool.search_web(_run_context(), query)
        report.check(REJECTION_MESSAGE in reply, f"{label} rechazado con mensaje controlado")
    report.check(
        port.calls == 0, "ninguna consulta sensible llegó al proveedor", f"llamadas={port.calls}"
    )
    reply = await web_tool.search_web(_run_context(), "   ")
    report.check("qué término o tema público" in reply, "consulta vacía rechazada")
    reply = await web_tool.search_web(_run_context(), "x" * 301)
    report.check("demasiado larga" in reply, "consulta de más de 300 caracteres rechazada")
    report.check(port.calls == 0, "vacía y larga tampoco llegaron al proveedor")


async def _check_controlled_errors(settings: Settings, report: _Report) -> None:
    report.note("\n== Errores controlados (clave inválida: Tavily no cobra) ==")
    bad_key = "tvly-invalid-validation-key"
    bad = settings.model_copy(update={"tavily_api_key": bad_key})
    web_tool.configure_web_search(bad)
    reply = await web_tool.search_web(_run_context(), "qué es la inflación")
    report.check(UNAVAILABLE_MESSAGE in reply, "HTTP 401 → mensaje controlado")
    report.check(
        not any(token in reply for token in ("401", "tavily", bad_key)),
        "el mensaje no filtra proveedor, código ni clave",
    )

    fast = bad.model_copy(update={"web_search_timeout_seconds": 0.001})
    web_tool.configure_web_search(fast)
    reply = await web_tool.search_web(_run_context(), "qué es la inflación")
    report.check(UNAVAILABLE_MESSAGE in reply, "timeout/transporte → mensaje controlado")

    web_tool._service = None
    reply = await web_tool.search_web(_run_context(), "qué es la inflación")
    report.check(NOT_CONFIGURED_MESSAGE in reply, "servicio sin configurar → mensaje controlado")


async def _check_live(settings: Settings, report: _Report) -> str:
    report.note("\n== Búsqueda real (consume 1 crédito de Tavily) ==")
    web_tool.configure_web_search(settings)
    reply = await web_tool.search_web(_run_context(), LIVE_QUERY)
    payload, records = _records(reply)

    report.check(payload.get("trust") == "untrusted_data", "resultados marcados untrusted_data")
    report.check(
        1 <= len(records) <= settings.web_search_max_results,
        "número de fuentes dentro del límite",
        f"{len(records)} fuentes",
    )
    report.check(len(records) >= 3, "al menos 3 fuentes (criterio de la spec)")
    report.check(
        all(str(r["url"]).startswith("https://") for r in records), "todas las URLs son https"
    )
    report.check(all(r["source"] == "public_web" for r in records), "origen public_web")
    report.check(all(r["retrieved_at"] for r in records), "fecha de consulta presente")
    for index, record in enumerate(records, start=1):
        report.note(f"    {index}. {str(record['title'])[:70]} — {record['url']}")

    service = web_tool._get_service()
    cached = await service.search(LIVE_QUERY)
    report.check(
        cached.cache_hit, "segunda consulta idéntica sale de la caché (sin gastar crédito)"
    )
    report.note(f"    créditos informados por Tavily: {cached.credits}")
    return " ".join(str(r["content"]) for r in records)


async def main(live: bool) -> int:
    # Windows consoles default to cp1252, which cannot print the report's accents/arrows.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    settings = Settings()
    if not settings.tavily_api_key.strip():
        print("TAVILY_API_KEY no está en .env; no hay nada que validar.", file=sys.stderr)
        return 2
    report = _Report()
    capture = _LogCapture()
    logging.getLogger().addHandler(capture)
    logging.getLogger().setLevel(logging.DEBUG)

    await _check_rejections(settings, report)
    await _check_controlled_errors(settings, report)
    snippets = await _check_live(settings, report) if live else ""
    if not live:
        report.note("\n(Búsqueda real omitida: usa --live para ejecutarla.)")

    report.note("\n== Privacidad en logs ==")
    logged = "\n".join(capture.lines)
    printed = "\n".join(report.output)
    secret_free = settings.tavily_api_key not in logged and settings.tavily_api_key not in printed
    report.check(secret_free, "la clave de Tavily no aparece en logs ni en esta salida")
    report.check(
        LIVE_QUERY not in logged and "persona@example.com" not in logged,
        "ninguna consulta aparece en los logs capturados",
        f"{len(capture.lines)} líneas",
    )
    if snippets:
        report.check(snippets[:60] not in logged, "los snippets no aparecen en los logs capturados")

    failed = f"{report.failures} comprobaciones fallidas"
    print(f"\n{'TODO CORRECTO' if report.failures == 0 else failed}")
    return 0 if report.failures == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="ejecuta una búsqueda real (1 crédito)")
    raise SystemExit(asyncio.run(main(parser.parse_args().live)))
