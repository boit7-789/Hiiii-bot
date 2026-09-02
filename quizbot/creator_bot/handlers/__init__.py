from __future__ import annotations

import logging
from pyrogram import Client

logger = logging.getLogger(__name__)

# List all handler modules present in quizbot/creator_bot/handlers/
HANDLER_MODULES = [
    "admin",
    "quiz_creation",
    "quiz_management",  # or whatever your quiz listing file is named
    "auth",
    "batches",
    "file_import",
    "payments",
]


def register(app: Client) -> None:
    for name in HANDLER_MODULES:
        try:
            mod = __import__(f"quizbot.creator_bot.handlers.{name}", fromlist=[name])
            if hasattr(mod, "register"):
                mod.register(app)
                logger.info("Successfully registered handler: %s", name)
            else:
                logger.warning("Module %s has no register() function", name)
        except ModuleNotFoundError:
            # File doesn't exist under this exact name, skip quietly
            pass
        except Exception as e:
            logger.error("Failed to load handler module '%s': %s", name, e, exc_info=True)


register_all_handlers = register
