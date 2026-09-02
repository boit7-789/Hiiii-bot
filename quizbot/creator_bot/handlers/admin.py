"""
Advance Quiz Bot — Open Source Project
This project was originally developed by Gagan (github.com/devgaganin).
Reference: https://t.me/advance_quiz_bot
The codebase has been reviewed and verified with the assistance of Claude AI.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from quizbot.database import UserRepository, get_db
from quizbot.shared import config

from .. import state
from ..ratelimit import ratelimit

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return (
        user_id == config.OWNER_ID
        or user_id in config.ADMIN_IDS
    )


@ratelimit("default")
async def limit_cmd(c: Client, m: Message) -> None:
    """/limit -- show rate-limit status for the user."""
    user = m.from_user
    if user is None:
        return

    # Check if user is Owner or Admin
    if is_admin(user.id):
        await m.reply(
            "👑 **Admin / Owner Status:**\n\n"
            "✨ **Unlimited Access Active**\n"
            "• All command rate limits are disabled for you.\n"
            "• You have unrestricted creation and execution limits."
        )
        return

    status = state.get_rate_limit_status(user.id)
    default_cfg = config.CREATOR_RATE_LIMIT_DEFAULT
    create_cfg = config.CREATOR_RATE_LIMIT_CREATE
    strict_cfg = config.CREATOR_RATE_LIMIT_STRICT

    lines = [
        "**Your command limits:**",
        "",
        f"- General commands ({default_cfg[0]} / {default_cfg[1] // 60} min): "
        f"{status['default_used']}/{default_cfg[0]} used, {status['default_left']} left",
        f"- /create + /done ({create_cfg[0]} / {create_cfg[1] // 60} min): "
        f"{status['create_used']}/{create_cfg[0]} used, {status['create_left']} left",
        f"- Heavier commands (/myquizzes, /edit) ({strict_cfg[0]} / {strict_cfg[1] // 60} min): "
        f"{status['strict_used']}/{strict_cfg[0]} used, {status['strict_left']} left",
    ]
    await m.reply("\n".join(lines))


async def broadcast_cmd(c: Client, m: Message) -> None:
    """/broadcast <message> -- (admin only) broadcast to all bot users."""
    if m.from_user is None or not is_admin(m.from_user.id):
        return

    reply = m.reply_to_message
    text = m.text.partition(" ")[2].strip() if not reply else ""

    if not reply and not text:
        await m.reply("Usage: `/broadcast <message>` or reply to a message with `/broadcast`")
        return

    repo = UserRepository(get_db())
    user_ids = await repo.get_all_user_ids()
    total = len(user_ids)
    sent = 0
    failed = 0

    status_msg = await m.reply(f"Broadcasting to {total} users...")

    for uid in user_ids:
        try:
            if reply:
                await reply.copy(uid)
            else:
                await c.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(f"Broadcast complete.\nSent: {sent}\nFailed/Blocked: {failed}")


async def stats_cmd(c: Client, m: Message) -> None:
    """/stats -- (admin only) display basic bot statistics."""
    if m.from_user is None or not is_admin(m.from_user.id):
        return

    repo = UserRepository(get_db())
    total_users = await repo.count_users()
    premium_users = await repo.count_premium_users()

    text = (
        "📊 **Bot Statistics**\n\n"
        f"• Total Users: {total_users}\n"
        f"• Premium Users: {premium_users}\n"
    )
    await m.reply(text)


def register(app: Client) -> None:
    app.on_message(filters.command("limit") & filters.private)(limit_cmd)
    app.on_message(filters.command("broadcast") & filters.private)(broadcast_cmd)
    app.on_message(filters.command("stats") & filters.private)(stats_cmd)
