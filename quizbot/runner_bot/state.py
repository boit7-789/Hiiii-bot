"""
Advance Quiz Bot — Runner Bot State Management
In-memory session handling, rate limiters, task trackers, and transient caches.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Temporary in-memory store for scorecard delivery (zero DB writes)
# Key: quiz_id (str) -> Value: {user_id (int): {qname, correct, wrong, score, total, time_str}}
temp_scorecards: dict[str, dict[int, dict]] = {}

# Pending settings for quiz creation / setup wizard
pending_quiz_settings: dict[int, dict[str, Any]] = {}

# Active AI provider fallback state & ongoing AI sessions
last_working_ai: dict[str, Any] = {}
AI_QUIZ_SESSIONS: dict[int, dict[str, Any]] = {}


class SessionManager:
    """Manages active running quiz sessions in chats."""

    def __init__(self) -> None:
        self.sessions: dict[int, dict[str, Any]] = {}

    def get(self, chat_id: int) -> Optional[dict[str, Any]]:
        return self.sessions.get(chat_id)

    async def create(self, chat_id: int, data: dict[str, Any]) -> dict[str, Any]:
        self.sessions[chat_id] = data
        return data

    async def update(self, chat_id: int, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        if chat_id in self.sessions:
            self.sessions[chat_id].update(data)
            return self.sessions[chat_id]
        return None

    async def delete(self, chat_id: int) -> Optional[dict[str, Any]]:
        return self.sessions.pop(chat_id, None)


class TaskManager:
    """Tracks background asyncio tasks for quiz timers and timeouts."""

    def __init__(self) -> None:
        self.tasks: dict[str, asyncio.Task] = {}

    def spawn(self, coro, name: str) -> asyncio.Task:
        self.cancel(name)
        task = asyncio.create_task(coro, name=name)
        self.tasks[name] = task

        def _cleanup(t: asyncio.Task):
            self.tasks.pop(name, None)

        task.add_done_callback(_cleanup)
        return task

    def cancel(self, name: str) -> None:
        task = self.tasks.pop(name, None)
        if task and not task.done():
            task.cancel()

    def cancel_all_for_chat(self, chat_id: int) -> None:
        prefix = f"quiz_{chat_id}_"
        matching_keys = [k for k in self.tasks if k.startswith(prefix)]
        for k in matching_keys:
            self.cancel(k)


class RateLimiter:
    """Simple rate-limiter to prevent command flooding."""

    def __init__(self, limit: int = 5, window_seconds: float = 3.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self.history: dict[int, list[float]] = {}

    async def check(self, user_id: int) -> bool:
        now = time.time()
        calls = self.history.setdefault(user_id, [])
        calls = [t for t in calls if now - t < self.window]
        if len(calls) >= self.limit:
            self.history[user_id] = calls
            return False
        calls.append(now)
        self.history[user_id] = calls
        return True


class TranslationManager:
    """Stores chat-specific live translation target language preferences."""

    def __init__(self) -> None:
        self._langs: dict[int, str] = {}

    def set_language(self, chat_id: int, lang_code: str) -> None:
        self._langs[chat_id] = lang_code.strip().lower()

    def get_language(self, chat_id: int) -> Optional[str]:
        return self._langs.get(chat_id)

    def remove_language(self, chat_id: int) -> None:
        self._langs.pop(chat_id, None)


# Singleton instances used across runner_bot handlers
session_mgr = SessionManager()
tasks = TaskManager()
rate_limiter = RateLimiter()
translation_mgr = TranslationManager()
channel_poll_tasks: dict[str, asyncio.Task] = {}
