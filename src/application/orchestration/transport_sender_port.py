"""
Transport sender aliases for orchestration layer.
"""

from src.application.ports.telegram_port import NullTelegramClient, TelegramClientPort

__all__ = ["NullTelegramClient", "TelegramClientPort"]
