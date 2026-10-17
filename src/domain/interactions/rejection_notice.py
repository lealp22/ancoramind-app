"""Fixed, non-enumerating access notice policy (BL-52); never grants admission."""

from src.domain.interactions.models import InteractionStatus, NormalizedTelegramUpdate

ACCESS_DENIED_REPLY = (
    "🔒 Tu acceso no está activo. Contacta con quien te invitó o con el administrador."
)
ACCESS_DENIED_RESPONSE_KIND = "access_denied_notice"
NOTICE_COOLDOWN_SECONDS = 300
NOTICE_GLOBAL_PER_MINUTE = 20
NOTICE_MAX_PENDING = 20
NOTICE_TTL_SECONDS = 300


def permits_access_notice(
    update: NormalizedTelegramUpdate, status: InteractionStatus, reason: str | None
) -> bool:
    """Only authenticated private new messages with complete identity qualify.

    Authentication belongs to the webhook adapter. Callbacks, edits, groups,
    unsupported updates and rate-limit rejections must never trigger a notice.
    Telegram private user chats have the same positive chat and sender ID.
    """
    return (
        status is InteractionStatus.REJECTED
        and reason == "user_not_allowlisted"
        and update.update_type == "message"
        and update.chat_type == "private"
        and update.telegram_user_id is not None
        and update.telegram_user_id > 0
        and update.chat_id == update.telegram_user_id
        and update.message_id is not None
        and update.message_id > 0
    )
