"""
Advance Quiz Bot — Manual Payment / Access Info Handler
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from quizbot.shared.utils import is_premium_user

OWNER_CONTACT_URL = "https://t.me/cuetchampion"


async def manual_payment_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if not user:
        return

    if await is_premium_user(user.id):
        await m.reply(
            "✅ **You are already an authorized user!**\n\n"
            "You have full access to all bot features."
        )
        return

    text = (
        "🔒 **Private / Whitelist-Only Bot**\n\n"
        "Automated payments are disabled. Access is granted manually by the owner.\n\n"
        f"📋 **Your Telegram User ID:** `{user.id}`\n\n"
        "Click the button below to contact the owner directly and send your User ID to get access."
    )
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Contact Owner", url=OWNER_CONTACT_URL)]]
    )
    await m.reply(text, reply_markup=kb)


def register(app: Client) -> None:
    app.on_message(filters.command(["pay", "plans", "buy"]) & filters.private)(manual_payment_cmd)
