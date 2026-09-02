"""
Advance Quiz Bot — Whitelist & Authorization Control
"""

from __future__ import annotations

from quizbot.database import UserRepository, get_db
from quizbot.shared import config


async def is_premium_user(user_id: int) -> bool:
    """Return True if the user is authorized to use the bot.
    
    Owners and Admins always have lifetime access.
    Other users must be manually granted access by the owner/admin.
    """
    if config.FREE_BOT:
        return True

    # 1. Owner always authorized
    if config.OWNER_ID and user_id == config.OWNER_ID:
        return True

    # 2. Admins always authorized
    if user_id in config.ADMIN_IDS:
        return True

    # 3. Check if user was granted access by owner
    repo = UserRepository(get_db())
    return await repo.is_premium(user_id)


async def grant_premium(user_id: int, days: int | None = 30) -> None:
    """Authorize a user for a given number of days (or permanent if None)."""
    repo = UserRepository(get_db())
    await repo.set_premium(user_id, days)


async def revoke_premium(user_id: int) -> None:
    """Revoke authorization from a user."""
    repo = UserRepository(get_db())
    await repo.revoke_premium(user_id)
