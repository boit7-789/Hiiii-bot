from __future__ import annotations

import logging
from pyrogram import Client

from . import admin, auth, batches, file_import, payments, quiz_creation, quiz_editor

logger = logging.getLogger(__name__)


def register(app: Client) -> None:
    admin.register(app)
    auth.register(app)
    batches.register(app)
    file_import.register(app)
    payments.register(app)
    quiz_creation.register(app)
    quiz_editor.register(app)
    logger.info("Creator bot handlers successfully registered.")


# Backward compatibility alias
register_all_handlers = register
