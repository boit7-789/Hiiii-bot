from __future__ import annotations

import logging
from pyrogram import Client

logger = logging.getLogger(__name__)


def register(app: Client) -> None:
    try:
        from . import admin
        admin.register(app)
        logger.info("Registered: admin handler")
    except Exception as e:
        logger.error("Failed to register admin handler: %s", e)

    # Register remaining handlers safely
    for name in ("quiz_creation", "auth", "batches", "file_import", "payments"):
        try:
            mod = __import__(f"quizbot.creator_bot.handlers.{name}", fromlist=[name])
            if hasattr(mod, "register"):
                mod.register(app)
                logger.info("Registered: %s handler", name)
        except Exception as e:
            logger.warning("Optional handler skipped (%s): %s", name, e)


register_all_handlers = register
