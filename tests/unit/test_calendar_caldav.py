"""Unit tests for the real CalDAV calendar provider (BL-7)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from src.agent.calendar_caldav import (
    CaldavCalendarProvider,
    CalendarProviderError,
    create_calendar_provider,
)
from src.config import Settings
from src.domain.calendar.models import CalendarEventCreate
from src.domain.calendar.provider import NoopCalendarProvider


def _provider(handler) -> CaldavCalendarProvider:
    return CaldavCalendarProvider(
        base_url="https://caldav.example.com/calendars/me/personal",
        username="me",
        password="secret",
        transport=httpx.MockTransport(handler),
    )


def _event() -> CalendarEventCreate:
    return CalendarEventCreate(
        title="Dentista",
        start_at=datetime(2026, 10, 10, 17, 30, tzinfo=UTC),
        end_at=datetime(2026, 10, 10, 18, 0, tzinfo=UTC),
        description="Revisión anual",
        location="Clínica Centro",
    )


class TestCreateEvent:
    async def test_puts_an_ical_vevent_with_basic_auth(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(201)

        provider = _provider(handler)

        uid = await provider.create_event("ignored", _event())

        assert len(requests) == 1
        request = requests[0]
        assert request.method == "PUT"
        assert str(request.url) == (
            f"https://caldav.example.com/calendars/me/personal/{uid}.ics"
        )
        assert request.headers["content-type"] == "text/calendar; charset=utf-8"
        assert "authorization" in request.headers
        body = request.read().decode()
        assert "SUMMARY:Dentista" in body
        assert "DTSTART:20261010T173000Z" in body
        assert "DESCRIPTION:Revisión anual" in body
        assert "LOCATION:Clínica Centro" in body
        assert f"UID:{uid}" in body

    async def test_never_sends_the_literal_user_external_id_anywhere(self) -> None:
        """BL-7 limitation: single shared account, user_external_id is ignored."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert "secret-user-id" not in str(request.url)
            assert b"secret-user-id" not in request.read()
            return httpx.Response(201)

        provider = _provider(handler)
        await provider.create_event("secret-user-id", _event())

    @pytest.mark.parametrize("status", [400, 401, 403, 500, 503])
    async def test_rejects_on_non_success_status_without_leaking_the_body(
        self, status: int
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text="server internals, stack trace, etc.")

        provider = _provider(handler)

        with pytest.raises(CalendarProviderError) as exc_info:
            await provider.create_event("ignored", _event())
        assert "server internals" not in str(exc_info.value)
        assert str(status) in exc_info.value.code

    async def test_transport_failure_is_mapped_without_a_raw_httpx_exception(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down")

        provider = _provider(handler)

        with pytest.raises(CalendarProviderError, match="caldav_transport_failure"):
            await provider.create_event("ignored", _event())


_MULTISTATUS_TWO_EVENTS = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:response>
    <D:href>/calendars/me/personal/one.ics</D:href>
    <D:propstat>
      <D:prop>
        <C:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:one
SUMMARY:Reunion equipo
DTSTART:20261010T090000Z
DTEND:20261010T100000Z
END:VEVENT
END:VCALENDAR
</C:calendar-data>
      </D:prop>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/calendars/me/personal/two.ics</D:href>
    <D:propstat>
      <D:prop>
        <C:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:two
SUMMARY:Dentista
DTSTART:20261010T173000Z
DTEND:20261010T180000Z
LOCATION:Clinica Centro
END:VEVENT
END:VCALENDAR
</C:calendar-data>
      </D:prop>
    </D:propstat>
  </D:response>
</D:multistatus>"""


class TestListEvents:
    async def test_parses_a_multistatus_response_into_event_dicts(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(207, text=_MULTISTATUS_TWO_EVENTS)

        provider = _provider(handler)

        events = await provider.list_events(
            "ignored",
            datetime(2026, 10, 10, 0, 0, tzinfo=UTC),
            datetime(2026, 10, 11, 0, 0, tzinfo=UTC),
        )

        assert len(requests) == 1
        assert requests[0].method == "REPORT"
        assert requests[0].headers["depth"] == "1"
        assert len(events) == 2
        assert events[0]["uid"] == "one"
        assert events[0]["summary"] == "Reunion equipo"
        assert events[1]["uid"] == "two"
        assert events[1]["location"] == "Clinica Centro"

    async def test_time_range_is_formatted_as_caldav_utc_timestamps(self) -> None:
        captured: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request.read().decode())
            return httpx.Response(207, text="<D:multistatus xmlns:D='DAV:'/>")

        provider = _provider(handler)
        await provider.list_events(
            "ignored",
            datetime(2026, 10, 10, 0, 0, tzinfo=UTC),
            datetime(2026, 10, 11, 0, 0, tzinfo=UTC),
        )

        assert 'start="20261010T000000Z"' in captured[0]
        assert 'end="20261011T000000Z"' in captured[0]

    async def test_rejects_a_response_declaring_an_xml_entity(self) -> None:
        """Entity-expansion guard against a compromised/malicious server —
        same zero-dependency technique already used for OOXML."""
        malicious = (
            '<?xml version="1.0"?><!DOCTYPE D:multistatus '
            '[<!ENTITY lol "lol">]><D:multistatus xmlns:D="DAV:">&lol;</D:multistatus>'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(207, text=malicious)

        provider = _provider(handler)

        with pytest.raises(CalendarProviderError, match="caldav_xml_entity_rejected"):
            await provider.list_events(
                "ignored",
                datetime(2026, 10, 10, tzinfo=UTC),
                datetime(2026, 10, 11, tzinfo=UTC),
            )

    async def test_malformed_xml_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(207, text="not xml at all <<<")

        provider = _provider(handler)

        with pytest.raises(CalendarProviderError, match="caldav_report_malformed"):
            await provider.list_events(
                "ignored",
                datetime(2026, 10, 10, tzinfo=UTC),
                datetime(2026, 10, 11, tzinfo=UTC),
            )

    async def test_non_success_status_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        provider = _provider(handler)

        with pytest.raises(CalendarProviderError, match="caldav_report_rejected_404"):
            await provider.list_events(
                "ignored",
                datetime(2026, 10, 10, tzinfo=UTC),
                datetime(2026, 10, 11, tzinfo=UTC),
            )


class TestCreateCalendarProviderFactory:
    def test_defaults_to_noop(self) -> None:
        provider = create_calendar_provider(Settings())
        assert isinstance(provider, NoopCalendarProvider)

    def test_returns_caldav_provider_when_configured(self) -> None:
        settings = Settings(
            calendar_provider="caldav",
            calendar_caldav_base_url="https://caldav.example.com/cal",
            calendar_caldav_username="me",
            calendar_caldav_password="secret",
        )
        provider = create_calendar_provider(settings)
        assert isinstance(provider, CaldavCalendarProvider)


class TestSettingsValidation:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"calendar_caldav_username": "me", "calendar_caldav_password": "secret"},
            {"calendar_caldav_base_url": "https://x", "calendar_caldav_password": "secret"},
            {"calendar_caldav_base_url": "https://x", "calendar_caldav_username": "me"},
        ],
    )
    def test_caldav_provider_requires_all_three_variables(
        self, overrides: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError, match="CALENDAR_PROVIDER=caldav requires"):
            Settings(calendar_provider="caldav", **overrides)

    def test_unknown_provider_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="CALENDAR_PROVIDER"):
            Settings(calendar_provider="google")
