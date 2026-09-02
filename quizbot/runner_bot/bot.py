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


def _is_owner(user_id: int) -> bool:
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


async def runner_gatekeeper(update: Update, context) -> None:
    """1. In DMs: Creator Bot handles management and bare /start.
       Runner Bot processes /quiz, DM scorecards, or active poll interactions for authorized users.
    2. In Groups: Students can participate in polls freely.
    """
    msg = update.effective_message
    user = update.effective_user

    # Handle private DM restrictions
    if msg and msg.chat and msg.chat.type == ChatType.PRIVATE:
        if not user:
            raise ApplicationHandlerStop

        text = (msg.text or "").strip()
        parts = text.split()
        cmd = parts[0].lower() if parts else ""

        # Allow ANY student to receive their individual scorecard in DM without auth checks
        if cmd == "/start" and len(parts) > 1 and parts[1].startswith("dmscore_"):
            return

        is_adm = _is_owner(user.id)
        try:
            is_auth = is_adm or await is_premium_user(user.id)
        except Exception:
            is_auth = is_adm

        # Mute Runner Bot completely for unauthorized users in DMs for standard commands
        if not is_auth:
            raise ApplicationHandlerStop

        # Let Creator Bot handle bare /start
        if cmd == "/start" and len(parts) == 1:
            raise ApplicationHandlerStop

        # Creator Bot-only commands (prevent duplicate replies)
        creator_commands = {
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
        if cmd in creator_commands:
            raise ApplicationHandlerStop


def build_application() -> Application:
    """Construct the Runner Bot application instance."""
    # Use RUNNER_BOT_TOKEN if defined, fallback to BOT_TOKEN
    token = getattr(config, "RUNNER_BOT_TOKEN", None) or getattr(config, "BOT_TOKEN", None)
    if not token:
        raise ValueError("Neither RUNNER_BOT_TOKEN nor BOT_TOKEN is configured.")

    app = (
        ApplicationBuilder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )

    # Priority group -1 ensures the gatekeeper executes before any command handler
    app.add_handler(TypeHandler(Update, runner_gatekeeper), group=-1)

    # Register all runner handlers (quiz_play, scheduling, etc.)
    handlers.register(app)
    return app


async def run_runner_bot(stop_event: asyncio.Event | None = None) -> None:
    """Main runner bot entrypoint invoked by run.py."""
    app = build_application()

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Runner Bot polling started successfully.")

    own_event = stop_event or asyncio.Event()
    try:
        await own_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Stopping Runner Bot...")
        if app.updater and app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Runner Bot stopped cleanly.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_runner_bot())
