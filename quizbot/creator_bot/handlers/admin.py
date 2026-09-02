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
    """Check if the given user ID matches the configured owner/admin ID."""
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


async def send_restricted_notice(m: Message, user_id: int) -> None:
    """Send access restriction card with an owner contact button."""
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Contact Owner for Access", url=OWNER_CONTACT_URL)]]
    )
    await m.reply_text(
        "🔒 **Access Restricted**\n\n"
        "This bot is private and requires manual authorization.\n\n"
        f"📋 **Your Telegram ID:** `{user_id}`\n\n"
        "Contact the owner below to request access.",
        reply_markup=kb,
    )


async def start_cmd(c: Client, m: Message) -> None:
    """Handle /start command in private chat."""
    user = m.from_user
    if user is None:
        return

    # 1. Authorization check
    is_adm = _is_owner(user.id)
    try:
        authorized = is_adm or await is_premium_user(user.id)
    except Exception as e:
        logger.error("Authorization check error in start_cmd: %s", e)
        authorized = is_adm

    if not authorized:
        await send_restricted_notice(m, user.id)
        return

    # 2. Record/verify user in the database
    try:
        db = get_db()
        if db:
            user_repo = UserRepository(db)
            await user_repo.ensure_user(user.id, user.username or "", user.first_name or "")
    except Exception as e:
        logger.warning("Failed to track user in database: %s", e)

    # 3. Dynamic Welcome Card
    if is_adm:
        welcome_text = (
            f"👑 **Welcome back, Owner {user.first_name}!**\n\n"
            "Your dual-engine quiz management and running system is active and online.\n\n"
            "💡 **Next Steps:**\n"
            "• Send `/help` to see all Creator, Runner, and Owner commands.\n"
            "• Use the quick buttons below to navigate your dashboard:"
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
    else:
        welcome_text = (
            f"👋 **Welcome, {user.first_name}!**\n\n"
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
    """Handle /help command in private chat."""
    user = m.from_user
    if user is None:
        return

    is_adm = _is_owner(user.id)
    try:
        authorized = is_adm or await is_premium_user(user.id)
    except Exception as e:
        logger.error("Authorization check error in help_cmd: %s", e)
        authorized = is_adm

    if not authorized:
        await send_restricted_notice(m, user.id)
        return

    # Message 1: Creator Engine Reference
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
        "• `/limit` — Check your daily command quota\n"
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

    # Message 2: Runner Engine Reference
    runner_text = (
        "🎮 **Quiz Runner Bot — Command Reference**\n\n"
        "**Playing Quizzes (Groups & Channels):**\n"
        "• `/start <quiz_id>` — Launch a quiz\n"
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

    await m.reply_text(creator_text)
    await asyncio.sleep(0.3)
    await m.reply_text(runner_text)


async def start_button_callbacks(c: Client, q: CallbackQuery) -> None:
    """Handle callback button clicks from the /start message."""
    data = q.data or ""
    await q.answer()

    if data == "cb_start_help":
        if q.message:
            await help_cmd(c, q.message)
    elif data == "cb_start_create":
        await q.message.reply_text("Send `/create` to begin building a quiz.")
    elif data == "cb_start_myquizzes":
        await q.message.reply_text("Send `/myquizzes` to inspect your saved quizzes.")


def register(app: Client) -> None:
    """Properly register all handlers wrapped in their Pyrogram handler types."""
    app.add_handler(MessageHandler(start_cmd, filters.command("start") & filters.private))
    app.add_handler(MessageHandler(help_cmd, filters.command("help") & filters.private))
    app.add_handler(CallbackQueryHandler(start_button_callbacks, filters.regex(r"^cb_start_")))
    logger.info("Creator bot admin & gatekeeper handlers successfully registered.")
