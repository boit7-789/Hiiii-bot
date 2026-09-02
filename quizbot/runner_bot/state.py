"""
Advance Quiz Bot — Runner Bot State Management
In-memory session handling, rate limiters, task trackers, and transient caches.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Iterator, MutableMapping, Optional

logger = logging.getLogger(__name__)


class ExpiringScorecardCache(MutableMapping[str, Dict[int, dict]]):
    """
    In-memory dictionary-like cache that automatically purges scorecard
    sessions after a defined Time-To-Live (TTL). Prevents RAM growth on long uptimes.
    """

    def __init__(self, ttl_seconds: float = 7200.0) -> None:  # Default: 2 hours
        self.ttl = ttl_seconds
        # Structure: {quiz_id: {"created_at": float, "data": {user_id: scorecard_dict}}}
        self._store: dict[str, dict[str, Any]] = {}

    def prune(self) -> int:
        """Removes all expired quiz scorecard records. Returns count of deleted entries."""
        now = time.time()
        expired_keys = [
            qid for qid, item in self._store.items()
            if now - item.get("created_at", 0) > self.ttl
        ]
        for qid in expired_keys:
            self._store.pop(qid, None)
        return len(expired_keys)

    def __getitem__(self, key: str) -> Dict[int, dict]:
        self.prune()
        if key not in self._store:
            raise KeyError(key)
        item = self._store[key]
        if time.time() - item["created_at"] > self.ttl:
            del self._store[key]
            raise KeyError(key)
        return item["data"]

    def __setitem__(self, key: str, value: Dict[int, dict]) -> None:
        self.prune()
        self._store[key] = {
            "created_at": time.time(),
            "data": value,
        }

    def __delitem__(self, key: str) -> None:
        del self._store[key]

    def __iter__(self) -> Iterator[str]:
        self.prune()
        return iter(self._store)

    def __len__(self) -> int:
        self.prune()
        return len(self._store)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


# Temporary in-memory store for scorecard delivery with 2-hour auto-TTL
temp_scorecards = ExpiringScorecardCache(ttl_seconds=7200.0)

# Pending settings for quiz creation / setup wizard
pending_quiz_settings: dict[int, dict[str, Any]] = {}

# AI & Special Handler Session Stores
last_working_ai: dict[str, Any] = {}
AI_QUIZ_SESSIONS: dict[int, dict[str, Any]] = {}
PDF_QUIZ_SESSIONS: dict[int, dict[str, Any]] = {}
MIX_QUIZ_SESSIONS: dict[int, dict[str, Any]] = {}
POLL_QUIZ_SESSIONS: dict[int, dict[str, Any]] = {}
SCHEDULE_QUIZ_SESSIONS: dict[int, dict[str, Any]] = {}


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
