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
    owner_id = getattr(config, "OWNER_ID", None) or getattr(config, "ADMIN_USER_ID", None)
    try:
        return int(owner_id) == user_id
    except (TypeError, ValueError):
        return False


async def runner_gatekeeper(update: Update, context) -> None:
    """1. Private DMs: Creator bot handles general commands. Runner only allows
       authorized users to play personal quizzes (/quiz <id>).
    2. Groups: Students can vote on polls freely. Gated commands are checked
       inside each handler via _require_admin / is_premium_user.
    """
    msg = update.effective_message
    user = update.effective_user

    # Handle Private DM restrictions
    if msg and msg.chat and msg.chat.type == ChatType.PRIVATE:
        if not user:
            raise ApplicationHandlerStop

        is_adm = _is_owner(user.id)
        is_auth = is_adm or await is_premium_user(user.id)

        # Drop unauthorized users entirely in DM (Creator Bot will show access card)
        if not is_auth:
            raise ApplicationHandlerStop

        text = (msg.text or "").strip()
        cmd = text.split()[0].lower() if text.startswith("/") else ""

        # Mute Creator-only commands so Runner Bot never duplicates responses
        creator_only_commands = {
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

        # Let Creator Bot handle bare /start in DM
        if cmd == "/start" and len(text.split()) == 1:
            raise ApplicationHandlerStop


def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(config.RUNNER_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Priority group -1 ensures this check runs before any command handlers
    app.add_handler(TypeHandler(Update, runner_gatekeeper), group=-1)

    handlers.register(app)
    return app
