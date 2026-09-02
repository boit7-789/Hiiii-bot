from __future__ import annotations

import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from quizbot.database import UserRepository, get_db
from quizbot.shared import config
from quizbot.shared.utils import is_premium_user

logger = logging.getLogger(__name__)

OWNER_CONTACT_URL = "https://t.me/cuetchampion"


def _is_owner(user_id: int) -> bool:
    """Check if user ID matches configured owner."""
    owner_id = (
        getattr(config, "OWNER_ID", None)
        or getattr(config, "ADMIN_USER_ID", None)
        or getattr(config, "OWNER_USER_ID", None)
    )
    if not owner_id:
        return False
    try:
        return int(owner_id) == user_id
    except (TypeError, ValueError):
        return False


async def send_restricted_notice(c: Client, chat_id: int, user_id: int) -> None:
    """Send access restriction card."""
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Contact Owner for Access", url=OWNER_CONTACT_URL)]]
    )
    await c.send_message(
        chat_id=chat_id,
        text=(
            "🔒 **Access Restricted**\n\n"
            "This bot is private and requires manual authorization.\n\n"
            f"📋 **Your Telegram ID:** `{user_id}`\n\n"
            "Contact the owner below to request access."
        ),
        reply_markup=kb,
    )


async def send_help_reference(c: Client, chat_id: int, user_id: int) -> None:
    """Send both Creator and Runner references to the user."""
    is_adm = _is_owner(user_id)
    try:
        authorized = is_adm or await is_premium_user(user_id)
    except Exception as e:
        logger.error("Authorization check error in send_help_reference: %s", e)
        authorized = is_adm

    if not authorized:
        await send_restricted_notice(c, chat_id, user_id)
        return

    # Message 1: Creator Reference
    creator_text = (
        "🛠 **Quiz Creator Bot — Command Reference**\n\n"
        "**Creation & Management:**\n"
        "• `/create` — Start interactive quiz creation\n"
        "• `/done` — Save and finish current quiz\n"
        "• `/cancel` — Cancel quiz creation in progress\n"
        "• `/myquizzes` — View and edit your quiz library\n"
        "• `/edit` — Modify questions, options, and timer\n"
        "• `/import` — Import quiz files (TXT, JSON)\n"
        "• `/batch` — Group multiple quizzes into batches\n"
        "• `/limit` — Check daily command quota\n"
    )

    if is_adm:
        creator_text += (
            "\n👑 **Owner / Admin Controls:**\n"
            "• `/admin` — Control panel\n"
            "• `/auth <id> <days>` — Grant user access\n"
            "• `/removeuser <id>` — Revoke user access\n"
            "• `/broadcast <msg>` — Send announcement to all users\n"
            "• `/stats` — View system and database statistics\n"
        )

   # --- Message 2: Runner Reference ---
    runner_text = (
        "🎮 **Quiz Runner Bot — Command Reference**\n\n"
        "**Playing Quizzes (Groups & Channels):**\n"
        "• `/quiz <quiz_id>` — Launch a quiz\n"
        "• `/pause`, `/resume`, `/stop` — Control running quiz\n"
        "• `/slow`, `/fast`, `/normal` — Adjust question timer\n"
        "• `/leaderboard` — Show live mid-quiz leaderboard\n\n"
        "**Other Quiz Modes:**\n"
        "• `/pollquiz <quiz_id>`, `/pollstop` — Non-expiring poll mode\n"
        "• `/mix <count> <id1> <id2> ...` — Combine multiple quizzes\n"
        "• `/aiquiz <topic>` — AI-generated quiz\n"
        "• `/pdfquiz` — Reply to a PDF to generate a quiz\n\n"
        "**Reports & Settings:**\n"
        "• `/html`, `/pdf` — Toggle report generation\n"
        "• `/trans <lang>` — Live question translation\n"
        "• `/schedule`, `/viewschedule`, `/cancelschedule` — Schedule a quiz\n"
    )

    await c.send_message(chat_id=chat_id, text=creator_text)
    await asyncio.sleep(0.3)
    await c.send_message(chat_id=chat_id, text=runner_text)


async def start_cmd(c: Client, m: Message) -> None:
    """Handle /start in private chat."""
    user = m.from_user
    if user is None:
        return

    is_adm = _is_owner(user.id)
    try:
        authorized = is_adm or await is_premium_user(user.id)
    except Exception as e:
        logger.error("Authorization check error in start_cmd: %s", e)
        authorized = is_adm

    if not authorized:
        await send_restricted_notice(c, m.chat.id, user.id)
        return

    try:
        db = get_db()
        if db:
            user_repo = UserRepository(db)
            await user_repo.ensure_user(user.id, user.username or "", user.first_name or "")
    except Exception as e:
        logger.warning("Failed to track user in database: %s", e)

    welcome_text = (
        f"👑 **Welcome back, Owner {user.first_name}!**\n\n"
        "Your dual-engine quiz management and running system is active and online.\n\n"
        "💡 **Next Steps:**\n"
        "• Send `/help` to see all Creator, Runner, and Owner commands.\n"
        "• Use the quick buttons below to navigate your dashboard:"
        if is_adm
        else f"👋 **Welcome, {user.first_name}!**\n\n"
        "✨ **Authorized Member Access Granted**\n\n"
        "You have full access to create, organize, and host quizzes.\n\n"
        "💡 **Next Steps:**\n"
        "• Send `/help` anytime to view the complete command reference.\n"
        "• Use the quick buttons below to get started:"
    )

    buttons = [
        [
            InlineKeyboardButton("➕ Create Quiz", callback_data="cb_start_create"),
            InlineKeyboardButton("📚 My Quizzes", callback_data="cb_start_myquizzes"),
        ],
        [
            InlineKeyboardButton("📖 Commands & Help", callback_data="cb_start_help"),
        ],
    ]

    await m.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(buttons))


async def help_cmd(c: Client, m: Message) -> None:
    """Handle /help command directly."""
    user = m.from_user
    if user is None:
        return
    await send_help_reference(c, m.chat.id, user.id)


async def start_button_callbacks(c: Client, q: CallbackQuery) -> None:
    """Handle callback button clicks from the /start message."""
    data = q.data or ""
    await q.answer()

    # q.from_user is the person clicking the button
    user_id = q.from_user.id
    chat_id = q.message.chat.id if q.message else user_id

    if data == "cb_start_help":
        await send_help_reference(c, chat_id, user_id)
    elif data == "cb_start_create":
        await c.send_message(chat_id, "Send `/create` to begin building a quiz.")
    elif data == "cb_start_myquizzes":
        await c.send_message(chat_id, "Send `/myquizzes` to inspect your saved quizzes.")


def register(app: Client) -> None:
    app.add_handler(MessageHandler(start_cmd, filters.command("start") & filters.private))
    app.add_handler(MessageHandler(help_cmd, filters.command("help") & filters.private))
    app.add_handler(CallbackQueryHandler(start_button_callbacks, filters.regex(r"^cb_start_")))
    logger.info("Creator bot admin & gatekeeper handlers successfully registered.")
