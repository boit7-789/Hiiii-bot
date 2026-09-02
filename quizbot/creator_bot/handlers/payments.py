"""
Advance Quiz Bot — Payments Handler Placeholder
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message


@Client.on_message(filters.command(["pay", "plans", "buy"]) & filters.private)
async def manual_payment_cmd(client: Client, message: Message) -> None:
    await message.reply(
        "🔒 **Manual Authorization Mode**\n\n"
        "Contact the bot owner directly to obtain access."
    )


def register(app: Client) -> None:
    pass
