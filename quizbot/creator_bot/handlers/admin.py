from __future__ import annotations

import asyncio
import logging
import platform
import sys
import time

from pyrogram import Client, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from quizbot.database import (
    AttemptRepository,
    QuizRepository,
    UserRepository,
    get_db,
)
from quizbot.shared import config
from quizbot.shared.utils import is_premium_user

logger = logging.getLogger(__name__)

OWNER_CONTACT_URL = "https://t.me/cuetchampion"
BOT_START_TIME = time.time()


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
        return str(owner_id) == str(user_id)
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

    creator_text = (
        "🛠 **Quiz Creator Bot — Command Reference**\n\n"
        "**Creation & Management:**\n"
        "• `/create` — Start interactive quiz creation\n"
        "• `/done` — Save and finish current quiz\n"
        "• `/cancel` — Cancel quiz creation in progress\n"
        "• `/myquizzes` — View and edit your quiz library\n"
        "• `/edit <quiz_id>` — Modify questions, options, and timer\n"
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

    # Ignore scorecard deep-links completely so students only receive their scorecards
    text_parts = (m.text or "").strip().split()
    if len(text_parts) > 1 and (
        text_parts[1].startswith("dmscore_") or text_parts[1].startswith("score_")
    ):
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


async def stats_cmd(c: Client, m: Message) -> None:
    """Handle /stats command — system and database breakdown."""
    user = m.from_user
    if not user or not _is_owner(user.id):
        return

    status_msg = await m.reply_text("📊 Gathering system and database statistics...")

    try:
        db = get_db()
        user_count = 0
        quiz_count = 0
        attempt_count = 0

        if db:
            user_repo = UserRepository(db)
            quiz_repo = QuizRepository(db)
            attempt_repo = AttemptRepository(db)

            if hasattr(user_repo, "count"):
                user_count = await user_repo.count()
            elif hasattr(user_repo, "get_all"):
                user_count = len(await user_repo.get_all())

            if hasattr(quiz_repo, "count"):
                quiz_count = await quiz_repo.count()
            elif hasattr(quiz_repo, "get_all"):
                quiz_count = len(await quiz_repo.get_all())

            if hasattr(attempt_repo, "count"):
                attempt_count = await attempt_repo.count()

        uptime_seconds = int(time.time() - BOT_START_TIME)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days else f"{hours}h {minutes}m {seconds}s"

        stats_text = (
            "📊 **System & Database Statistics**\n\n"
            "🤖 **Bot Engine Status:**\n"
            "• **Status:** 🟢 Online & Running\n"
            f"• **Uptime:** `{uptime_str}`\n"
            f"• **Python:** `{platform.python_version()}`\n"
            f"• **OS:** `{platform.system()} {platform.release()}`\n\n"
            "🗄️ **Database Metrics:**\n"
            f"• **Total Registered Users:** `{user_count}`\n"
            f"• **Total Quizzes Created:** `{quiz_count}`\n"
            f"• **Total Completed Attempts:** `{attempt_count}`\n"
            "• **Database Engine:** MongoDB Atlas"
        )

        await status_msg.edit_text(stats_text)
    except Exception as e:
        logger.exception("Failed to collect stats: %s", e)
        await status_msg.edit_text(f"❌ Error collecting statistics: {e}")


async def admin_panel_cmd(c: Client, m: Message) -> None:
    """Handle /admin command — owner dashboard."""
    user = m.from_user
    if not user or not _is_owner(user.id):
        return

    text = (
        "👑 **Owner Control Panel**\n\n"
        "Manage users, system status, and bot-wide announcements.\n\n"
        "**Available Commands:**\n"
        "• `/stats` — View live database & server status\n"
        "• `/auth <user_id> <days>` — Grant user access\n"
        "• `/removeuser <user_id>` — Revoke user access\n"
        "• `/broadcast <message>` — Send announcement to all users"
    )
    await m.reply_text(text)


async def broadcast_cmd(c: Client, m: Message) -> None:
    """Handle /broadcast <message> to send updates to all registered users."""
    user = m.from_user
    if not user:
        return

    if not _is_owner(user.id):
        await m.reply_text("🚫 This command is restricted to the bot owner.")
        return

    parts = m.text.split(None, 1)
    if len(parts) < 2:
        await m.reply_text(
            "📢 **Broadcast Usage:**\n\n"
            "• `/broadcast <your message here>`\n\n"
            "Example: `/broadcast Hello everyone, a new quiz has been posted!`"
        )
        return

    broadcast_text = parts[1].strip()
    db = get_db()
    if db is None:
        await m.reply_text("❌ Database not connected.")
        return

    status_msg = await m.reply_text("📢 Fetching users and preparing broadcast...")

    user_ids: set[int] = set()

    try:
        if hasattr(db, "users"):
            cursor = db.users.find({}, {"_id": 0, "user_id": 1, "id": 1})
            async for doc in cursor:
                uid = doc.get("user_id") or doc.get("id")
                if uid:
                    try:
                        user_ids.add(int(uid))
                    except (ValueError, TypeError):
                        pass

        if hasattr(db, "quizzes"):
            cursor = db.quizzes.find({}, {"_id": 0, "creator_id": 1})
            async for doc in cursor:
                cid = doc.get("creator_id")
                if cid:
                    try:
                        user_ids.add(int(cid))
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        logger.error("Error querying database during broadcast: %s", e)
        try:
            user_repo = UserRepository(db)
            if hasattr(user_repo, "get_all"):
                all_users = await user_repo.get_all()
                for u in all_users:
                    uid = u.get("user_id") or u.get("id")
                    if uid:
                        user_ids.add(int(uid))
        except Exception as inner_e:
            logger.error("Fallback repository query failed: %s", inner_e)

    if not user_ids:
        await status_msg.edit_text("⚠️ No registered users found in the database to broadcast to.")
        return

    await status_msg.edit_text(f"📢 Sending broadcast to **{len(user_ids)}** user(s)...")

    success = 0
    failed = 0
    blocked = 0

    for target_id in user_ids:
        try:
            await c.send_message(chat_id=target_id, text=broadcast_text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as send_err:
            err_str = str(send_err).lower()
            if "blocked" in err_str or "user_deactivated" in err_str:
                blocked += 1
            else:
                failed += 1

    summary_text = (
        f"📢 **Broadcast Complete**\n\n"
        f"👥 **Total Targets:** `{len(user_ids)}`\n"
        f"✅ **Delivered:** `{success}`\n"
        f"🚫 **Blocked/Deleted:** `{blocked}`\n"
        f"❌ **Failed:** `{failed}`"
    )
    await status_msg.edit_text(summary_text)


async def start_button_callbacks(c: Client, q: CallbackQuery) -> None:
    """Handle callback button clicks from the /start message."""
    data = q.data or ""
    await q.answer()

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
    app.add_handler(MessageHandler(stats_cmd, filters.command("stats") & filters.private))
    app.add_handler(MessageHandler(admin_panel_cmd, filters.command("admin") & filters.private))
    app.add_handler(MessageHandler(broadcast_cmd, filters.command("broadcast") & filters.private))
    app.add_handler(CallbackQueryHandler(start_button_callbacks, filters.regex(r"^cb_start_")))
    logger.info("Creator bot admin & gatekeeper handlers successfully registered.")
