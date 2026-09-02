from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    ApplicationBuilder,
    TypeHandler,
)

from quizbot.shared import config
from quizbot.shared.utils import is_premium_user
from . import handlers

logger = logging.getLogger(__name__)


async def private_chat_guard(update: Update, context) -> None:
    """Blocks unauthorized users from interacting with the Runner Bot in private DMs.
    Groups and supergroups remain untouched so quizzes can still run there."""
    msg = update.effective_message
    user = update.effective_user

    # If it's a private chat, verify authorization
    if msg and msg.chat and msg.chat.type == ChatType.PRIVATE:
        if user and not await is_premium_user(user.id):
            # Stop handling this update immediately (silences all commands in DM)
            raise ApplicationHandlerStop


from telegram.ext import ApplicationHandlerStop


def build_application() -> Application:
    """Construct the Runner Bot's python-telegram-bot Application."""
    app = (
        ApplicationBuilder()
        .token(config.RUNNER_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Group -1 runs BEFORE any command handlers (0)
    # This immediately drops unauthorized commands in private chats
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
