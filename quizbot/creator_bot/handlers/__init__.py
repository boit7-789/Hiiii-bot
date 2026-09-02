from __future__ import annotations

import logging
from pyrogram import Client

logger = logging.getLogger(__name__)

# Complete list matching all files in your folder
ALL_HANDLERS = [
    "admin",
    "quiz_creation",
    "quiz_management",
    "quiz_editing",
    "batches",
    "file_import",
    "auth",
    "payments",
    "ai_keys",
    "inline",
]


def register(app: Client) -> None:
    for name in ALL_HANDLERS:
        try:
            mod = __import__(f"quizbot.creator_bot.handlers.{name}", fromlist=[name])
            if hasattr(mod, "register"):
                mod.register(app)
                logger.info("Successfully registered: %s handler", name)
            else:
                logger.warning("Module %s has no register() function", name)
        except Exception as e:
            logger.error("Failed to register %s handler: %s", name, e, exc_info=True)


register_all_handlers = register
