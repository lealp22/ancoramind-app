"""Real CalDAV calendar provider (BL-7) behind the existing CalendarProvider Protocol.

Deliberately simple: a direct ``PUT``/``REPORT`` against the exact calendar
collection URL the operator configures — no WebDAV principal/calendar-home-set
discovery (``caldav`` package territory). This fits a single personal
calendar/account per deployment, consistent with AncoraMind being a personal
assistant for one owner (plus a small invited group via BL-24), not a
multi-tenant SaaS with per-user calendar accounts.

Known limitation: ``user_external_id`` (the Protocol's per-user parameter) is
accepted but ignored — there is no per-user account to resolve. One shared
calendar collection serves every AncoraMind user in this increment.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
from icalendar import Calendar, Event

from src.domain.calendar.models import CalendarEventCreate
from src.domain.calendar.provider import CalendarProvider, NoopCalendarProvider

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)

_CALDAV_NS = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}
_TIMEOUT_SECONDS = 10.0

_REPORT_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}" end="{end}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""


class CalendarProviderError(RuntimeError):
    """A CalDAV request failed; never carries the raw server response body."""

    def __init__(self, code: str):
        super().__init__(f"CalDAV provider error: {code}")
        self.code = code


class CaldavCalendarProvider:
    """CalendarProvider backed by one fixed CalDAV calendar collection."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, password)
        self._transport = transport
        """Test-only hook (``httpx.MockTransport``); ``None`` uses the real network."""

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, transport=self._transport)

    async def create_event(self, user_external_id: str, data: CalendarEventCreate) -> str:
        """PUT a new VEVENT; returns its UID as the provider event id.

        ``user_external_id`` is accepted for Protocol compatibility only —
        see the module limitation note.
        """
        del user_external_id
        uid = str(uuid.uuid4())
        ics_body = _build_ics(uid, data)
        url = f"{self._base_url}/{uid}.ics"
        try:
            async with self._client() as client:
                response = await client.put(
                    url,
                    content=ics_body,
                    headers={"Content-Type": "text/calendar; charset=utf-8"},
                    auth=self._auth,
                )
        except httpx.HTTPError as exc:
            raise CalendarProviderError("caldav_transport_failure") from exc
        if response.status_code not in (200, 201, 204):
            raise CalendarProviderError(f"caldav_put_rejected_{response.status_code}")
        return uid

    async def list_events(
        self, user_external_id: str, start: datetime, end: datetime
    ) -> list[dict[str, object]]:
        """CalDAV ``REPORT`` time-range query. No caller exists today (BL-7
        design note); implemented fully regardless so the Protocol stays
        satisfied for whenever one does.
        """
        del user_external_id
        body = _REPORT_BODY.format(start=_caldav_timestamp(start), end=_caldav_timestamp(end))
        try:
            async with self._client() as client:
                response = await client.request(
                    "REPORT",
                    self._base_url,
                    content=body,
                    headers={"Content-Type": "application/xml; charset=utf-8", "Depth": "1"},
                    auth=self._auth,
                )
        except httpx.HTTPError as exc:
            raise CalendarProviderError("caldav_transport_failure") from exc
        if response.status_code not in (200, 207):
            raise CalendarProviderError(f"caldav_report_rejected_{response.status_code}")
        return _parse_multistatus(response.text)


def _build_ics(uid: str, data: CalendarEventCreate) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//AncoraMind//CalDAV//")
    calendar.add("version", "2.0")
    event = Event()
    event.add("uid", uid)
    event.add("summary", data.title)
    event.add("dtstart", data.start_at)
    if data.end_at is not None:
        event.add("dtend", data.end_at)
    if data.description:
        event.add("description", data.description)
    if data.location:
        event.add("location", data.location)
    calendar.add_component(event)
    return bytes(calendar.to_ical())


def _caldav_timestamp(value: datetime) -> str:
    """Format a UTC-aware datetime as CalDAV's ``YYYYMMDDTHHMMSSZ``."""
    return value.strftime("%Y%m%dT%H%M%SZ")


def _parse_multistatus(xml_text: str) -> list[dict[str, object]]:
    """Parse a CalDAV REPORT multistatus response into event dicts.

    Rejects any DTD/entity declaration before handing the text to
    ``ElementTree`` — same zero-dependency entity-expansion guard already
    used for OOXML in ``document_office.py``, applied here because this XML
    comes from a remote (and here, untrusted-by-default) server.
    """
    if "<!ENTITY" in xml_text or "<!DOCTYPE" in xml_text:
        raise CalendarProviderError("caldav_xml_entity_rejected")
    try:
        root = ET.fromstring(xml_text)  # noqa: S314 - guarded above
    except ET.ParseError as exc:
        raise CalendarProviderError("caldav_report_malformed") from exc

    events: list[dict[str, object]] = []
    for calendar_data in root.findall(".//C:calendar-data", _CALDAV_NS):
        ics_text = calendar_data.text
        if not ics_text:
            continue
        try:
            parsed = Calendar.from_ical(ics_text)
        except ValueError:
            logger.warning("CalDAV response contained an unparsable VEVENT", exc_info=True)
            continue
        for component in parsed.walk("VEVENT"):
            events.append(_event_component_to_dict(component))
    return events


def _event_component_to_dict(component: Any) -> dict[str, object]:
    dtstart = component.get("dtstart")
    dtend = component.get("dtend")
    return {
        "uid": str(component.get("uid", "")),
        "summary": str(component.get("summary", "")),
        "start": dtstart.dt if dtstart is not None else None,
        "end": dtend.dt if dtend is not None else None,
        "description": str(component.get("description", "")) or None,
        "location": str(component.get("location", "")) or None,
    }


def create_calendar_provider(settings: Settings) -> CalendarProvider:
    """Resolve the configured calendar provider (BL-7).

    ``Settings.validate_calendar_provider_settings`` already fails closed
    at startup when ``calendar_provider == "caldav"`` lacks its required
    variables, so this never needs to re-check them.
    """
    if settings.calendar_provider == "caldav":
        return CaldavCalendarProvider(
            base_url=settings.calendar_caldav_base_url,
            username=settings.calendar_caldav_username,
            password=settings.calendar_caldav_password,
        )
    return NoopCalendarProvider()


__all__ = ["CalendarProviderError", "CaldavCalendarProvider", "create_calendar_provider"]
