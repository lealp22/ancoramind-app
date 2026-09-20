"""Deterministic Telegram commands resolved before any Agent execution (BL-28).

Telegram commands are control input, not conversation. AncoraMind interprets
them itself, so the probabilistic layer never decides a control action and no
inference budget is spent on them (AGENTS.md §2.2/§2.3). The replies are module
constants: untrusted text never travels through this path, and a command never
reaches the model nor drags the chat history into a provider call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SESSION_PREFIX = "tg:ancoramind"
"""Prefix of the conversation session id used by the governed processor."""

_COMMAND_PATTERN = re.compile(r"^/([A-Za-z0-9_]{1,32})(?:@([A-Za-z0-9_]{1,32}))?$")
"""Telegram's own command grammar: ``/name`` or ``/name@botusername``."""

_SESSION_RESET_COMMANDS = frozenset({"new"})
_HELP_COMMANDS = frozenset({"help", "start"})
_SUPPORTED_COMMANDS = _SESSION_RESET_COMMANDS | _HELP_COMMANDS

BOT_COMMAND_MENU: tuple[tuple[str, str], ...] = (
    ("new", "Empezar una conversación nueva"),
    ("help", "Ver los comandos disponibles"),
)
"""Telegram autocomplete menu, registered with ``setMyCommands`` (BL-28).

Single source of truth with :func:`handle_telegram_command`: a test asserts that
every advertised command is actually handled.
"""

HELP_REPLY = (
    "ℹ️ Comandos disponibles\n"
    "\n"
    "/new — empieza una conversación nueva: dejo de tener en cuenta el hilo\n"
    "anterior, pero conservo tu memoria (notas, documentos, vehículos,\n"
    "recordatorios y listas).\n"
    "/help — muestra esta ayuda."
)

NEW_SESSION_REPLY = (
    "🆕 Conversación nueva.\n"
    "\n"
    "Ya no tengo en cuenta el hilo anterior. Tu memoria sigue intacta: notas,\n"
    "documentos, vehículos, recordatorios y listas."
)

UNSUPPORTED_COMMAND_REPLY = (
    "🤖 Ese comando no está disponible.\n" "\n" "Escribe /help para ver qué puedo hacer."
)


@dataclass(frozen=True)
class TelegramCommand:
    """One parsed bot command, resolved from Telegram text only."""

    name: str
    """Normalized command name without the leading slash (lowercase)."""

    raw: str
    """The command token exactly as received, for audit purposes."""


@dataclass(frozen=True)
class CommandHandling:
    """Deterministic outcome of a supported command."""

    reply_text: str
    """Fixed Spanish reply; never built from untrusted content."""

    resets_session: bool
    """Whether the chat's conversation history must start over."""


def parse_telegram_command(
    text: str | None,
    *,
    bot_username: str | None = None,
) -> TelegramCommand | None:
    """Return the command carried by ``text``, or None when it is conversation.

    Only the first whitespace-delimited token is considered and it must match
    Telegram's command grammar, so ordinary text such as ``/home/user/file`` is
    left to the Agent. When ``bot_username`` is known, a command addressed to a
    different bot is conversation as well.
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    token = stripped.split(maxsplit=1)[0]
    match = _COMMAND_PATTERN.match(token)
    if match is None:
        return None

    name = match.group(1).lower()
    addressed_bot = match.group(2)
    if (
        addressed_bot is not None
        and bot_username
        and addressed_bot.lower() != bot_username.lstrip("@").lower()
    ):
        return None
    return TelegramCommand(name=name, raw=token)


def handle_telegram_command(command: TelegramCommand) -> CommandHandling:
    """Map a parsed command to its fixed reply and session effect."""
    if command.name in _SESSION_RESET_COMMANDS:
        return CommandHandling(reply_text=NEW_SESSION_REPLY, resets_session=True)
    if command.name in _HELP_COMMANDS:
        return CommandHandling(reply_text=HELP_REPLY, resets_session=False)
    return CommandHandling(reply_text=UNSUPPORTED_COMMAND_REPLY, resets_session=False)


def telemetry_label(command: TelegramCommand) -> str:
    """Bounded label for the metadata-only allowlist (never free-form text)."""
    return command.name if command.name in _SUPPORTED_COMMANDS else "unsupported"


def default_session_id(chat_id: int) -> str:
    """Conversation session used before any ``/new`` in a chat."""
    return f"{SESSION_PREFIX}:{chat_id}"


def next_session_id(chat_id: int, current: str | None) -> str:
    """Return the session that replaces ``current`` after a ``/new``.

    Generations are append-only numbers derived from the stored session string,
    so the durable claim keeps replays idempotent and an abandoned conversation
    can never be resumed by a later run.
    """
    prefix = f"{SESSION_PREFIX}:{chat_id}:"
    generation = 0
    if isinstance(current, str) and current.startswith(prefix):
        suffix = current[len(prefix) :]
        if suffix.isdigit():
            generation = int(suffix)
    return f"{prefix}{generation + 1}"
