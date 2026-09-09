"""Notifications — outbound delivery channels (Telegram, BL-5/specs/010).

Channel layer: knows how to reach the user (Bot API) but not the domain.
The domain depends on the ReminderNotifier Protocol, never on this package.
"""
