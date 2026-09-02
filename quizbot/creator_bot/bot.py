from __future__ import annotations

import asyncio
import logging

from pyrogram import Client

from quizbot.shared import config

logger = logging.getLogger(__name__)


def build_client() -> Client:
    """Construct (but do not start) the Creator Bot's Pyrogram client."""
    return Client(
        "creator_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.CREATOR_BOT_TOKEN,
        in_memory=True,
        workers=50,
    )


async def run_creator_bot(stop_event: asyncio.Event | None = None) -> None:
    app = build_client()

    from .handlers import register

    register(app)

    await app.start()
    me = await app.get_me()
    logger.info("Creator Bot started as @%s", me.username)

    own_event = stop_event or asyncio.Event()
    try:
        await own_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Stopping Creator Bot...")
        await app.stop()
        logger.info("Creator Bot stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_creator_bot())
