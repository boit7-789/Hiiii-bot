from __future__ import annotations

import logging
from pyrogram import Client

logger = logging.getLogger(__name__)


def register(app: Client) -> None:
    """Safely register all available Creator Bot handlers."""
    # 1. Core Gatekeeper & Admin (Handles /start and access restriction)
    try:
        from . import admin
        admin.register(app)
        logger.info("Registered: admin handler")
    except Exception as e:
        logger.error("Failed to register admin handler: %s", e)

    # 2. Quiz Creation
    try:
        from . import quiz_creation
        quiz_creation.register(app)
        logger.info("Registered: quiz_creation handler")
    except Exception as e:
        logger.warning("Failed to register quiz_creation: %s", e)

    # 3. Authentication & Whitelist
    try:
        from . import auth
        auth.register(app)
        logger.info("Registered: auth handler")
    except Exception as e:
        logger.warning("Failed to register auth: %s", e)

    # 4. Batches
    try:
        from . import batches
        batches.register(app)
        logger.info("Registered: batches handler")
    except Exception as e:
        logger.warning("Failed to register batches: %s", e)

    # 5. File Import
    try:
        from . import file_import
        file_import.register(app)
        logger.info("Registered: file_import handler")
    except Exception as e:
        logger.warning("Failed to register file_import: %s", e)

    # 6. Payments
    try:
        from . import payments
        payments.register(app)
        logger.info("Registered: payments handler")
    except Exception as e:
        logger.warning("Failed to register payments: %s", e)

    # 7. Quiz Editor (optional / conditional)
    try:
        from . import quiz_editor
        quiz_editor.register(app)
        logger.info("Registered: quiz_editor handler")
    except Exception as e:
        logger.warning("Skipped quiz_editor (not present or circular import): %s", e)

    logger.info("Creator bot handler registration complete.")


register_all_handlers = register
