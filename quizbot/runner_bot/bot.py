from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    TypeHandler,
)

from quizbot.shared import config
from quizbot.shared.utils import is_premium_user
from . import handlers

logger = logging.getLogger(__name__)


async def private_chat_guard(update: Update, context) -> None:
    """Controls Runner Bot access in private DMs:
    1. Unauthorized users are completely ignored.
    2. Creator Bot commands (/help, /create, etc.) are ignored by the Runner Bot
       so the Creator Bot handles them cleanly without duplicate replies.
    3. Quiz execution commands (/start <quiz_id>, /stop, /pause, poll answers)
       are permitted in DM for you/authorized users.
    """
    msg = update.effective_message
    user = update.effective_user

    # If it's a private chat
    if msg and msg.chat and msg.chat.type == ChatType.PRIVATE:
        # Step A: Drop updates entirely if the user is unauthorized
        if not user or not await is_premium_user(user.id):
            raise ApplicationHandlerStop

        # Step B: If it's a bare /start or Creator command, let Creator Bot answer it
        text = (msg.text or "").strip()
        cmd = text.split()[0].lower() if text.startswith("/") else ""

        # Plain /start (without a quiz ID) or /help belong strictly to Creator Bot
        if cmd == "/start" and len(text.split()) == 1:
            raise ApplicationHandlerStop

        creator_only_commands = {
            "/help",
            "/create",
            "/done",
            "/cancel",
            "/myquizzes",
            "/edit",
            "/import",
            "/batch",
            "/admin",
            "/limit",
            "/auth",
            "/removeuser",
            "/broadcast",
            "/stats",
        }
        if cmd in creator_only_commands:
            raise ApplicationHandlerStop


def build_application() -> Application:
    """Construct the Runner Bot application."""
    app = (
        ApplicationBuilder()
        .token(config.RUNNER_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Priority group -1 ensures this check runs before any command handlers
    app.add_handler(TypeHandler(Update, private_chat_guard), group=-1)

    handlers.register(app)
    return app


async def run_runner_bot(stop_event: asyncio.Event | None = None) -> None:
    app = build_application()

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Runner Bot polling started.")

    own_event = stop_event or asyncio.Event()
    try:
        await own_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Stopping Runner Bot...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Runner Bot stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_runner_bot())
