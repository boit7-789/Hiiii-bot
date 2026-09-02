"""
Advance Quiz Bot — Open Source Project
Admin, Start, Help, and Limit Handlers
"""

from __future__ import annotations

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from quizbot.database import QuizRepository, UserRepository, get_db
from quizbot.shared import config
from .. import keyboards, state

logger = logging.getLogger(__name__)


def _is_owner(uid: int) -> bool:
    return uid == config.OWNER_ID or (config.ADMIN_IDS and uid in config.ADMIN_IDS)


async def start_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if user is None:
        return

    logger.info("Received /start from user_id: %s", user.id)

    # Track user in database safely
    try:
        user_repo = UserRepository(get_db())
        await user_repo.ensure_user(user.id, user.username or "", user.first_name or "")
    except Exception as e:
        logger.warning("Failed to record user in db: %s", e)

    text = (
        f"👋 Hello, **{user.first_name}**!\n\n"
        "Welcome to the **Advance Quiz Bot** Creator panel.\n\n"
        "Use the menu buttons below to get started:"
    )
    kb = keyboards.start_menu_keyboard(is_admin=_is_owner(user.id))
    await m.reply(text, reply_markup=kb)


async def help_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if user is None:
        return

    text = (
        "📚 **Quiz Creator Bot Commands:**\n\n"
        "• /create — Start interactive quiz creation\n"
        "• /done — Finish and save a quiz in progress\n"
        "• /cancel — Cancel current quiz creation\n"
        "• /myquizzes — View and manage your created quizzes\n"
        "• /edit — Edit an existing quiz\n"
        "• /import — Import questions from files\n"
        "• /batch — Manage quiz batches\n"
        "• /limit — Check your command quota\n"
    )
    if _is_owner(user.id):
        text += (
            "\n👑 **Owner / Admin Commands:**\n"
            "• /admin — Open admin control panel\n"
            "• /auth <id> <days> — Grant access\n"
            "• /removeuser <id> — Revoke access\n"
            "• /broadcast — Broadcast message to users\n"
            "• /stats — View bot statistics\n"
        )
    await m.reply(text)


async def limit_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if user is None:
        return

    if _is_owner(user.id):
        await m.reply(
            "👑 **Admin / Owner Status:**\n\n"
            "✨ **Unlimited Access Active**\n"
            "• All command rate limits are bypassed.\n"
            "• Unrestricted quiz creation and execution."
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


async def admin_panel_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if user is None or not _is_owner(user.id):
        await m.reply("⛔ This command is restricted to the Bot Owner and Admins.")
        return

    buttons = [
        [
            InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_help"),
        ],
        [
            InlineKeyboardButton("🔒 Close", callback_data="admin_close"),
        ],
    ]
    await m.reply(
        "🛠 **Admin Control Panel**\n\nChoose an action from the buttons below:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_callback(c: Client, cq: CallbackQuery) -> None:
    user = cq.from_user
    if user is None or not _is_owner(user.id):
        await cq.answer("Owner only.", show_alert=True)
        return

    data = cq.data
    if data == "admin_stats":
        repo = UserRepository(get_db())
        quiz_repo = QuizRepository(get_db())
        total_users = await repo.count_users()
        premium_users = await repo.count_premium_users()
        total_quizzes = await quiz_repo.count_all()

        text = (
            "📊 **Live System Statistics**\n\n"
            f"• **Total Registered Users:** `{total_users}`\n"
            f"• **Authorized / Premium Users:** `{premium_users}`\n"
            f"• **Total Quizzes Created:** `{total_quizzes}`\n"
        )
        await cq.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")],
            ]),
        )
        await cq.answer()

    elif data == "admin_broadcast_help":
        text = (
            "📢 **Broadcast Instructions:**\n\n"
            "To send a broadcast to all users, use:\n"
            "`/broadcast <your message>`\n\n"
            "Or reply directly to any text, photo, or document message with `/broadcast`."
        )
        await cq.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")],
            ]),
        )
        await cq.answer()

    elif data == "admin_back":
        buttons = [
            [
                InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats"),
                InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_help"),
            ],
            [
                InlineKeyboardButton("🔒 Close", callback_data="admin_close"),
            ],
        ]
        await cq.message.edit_text(
            "🛠 **Admin Control Panel**\n\nChoose an action from the buttons below:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        await cq.answer()

    elif data == "admin_close":
        await cq.message.delete()
        await cq.answer()


async def broadcast_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if user is None or not _is_owner(user.id):
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
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status_msg.edit_text(f"Broadcast complete.\nSent: {sent}\nFailed/Blocked: {failed}")


async def stats_cmd(c: Client, m: Message, *args, **kwargs) -> None:
    user = m.from_user
    if user is None or not _is_owner(user.id):
        return

    repo = UserRepository(get_db())
    quiz_repo = QuizRepository(get_db())
    total_users = await repo.count_users()
    premium_users = await repo.count_premium_users()
    total_quizzes = await quiz_repo.count_all()

    text = (
        "📊 **Bot Statistics**\n\n"
        f"• Total Users: {total_users}\n"
        f"• Premium Users: {premium_users}\n"
        f"• Total Quizzes: {total_quizzes}\n"
    )
    await m.reply(text)


def register(app: Client) -> None:
    app.on_message(filters.command("start") & filters.private)(start_cmd)
    app.on_message(filters.command("help") & filters.private)(help_cmd)
    app.on_message(filters.command("limit") & filters.private)(limit_cmd)
    app.on_message(filters.command("admin") & filters.private)(admin_panel_cmd)
    app.on_message(filters.command("broadcast") & filters.private)(broadcast_cmd)
    app.on_message(filters.command("stats") & filters.private)(stats_cmd)
    app.on_callback_query(filters.regex(r"^admin_"))(admin_callback)
