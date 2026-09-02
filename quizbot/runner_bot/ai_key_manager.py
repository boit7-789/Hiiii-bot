from __future__ import annotations

import itertools
import logging
from typing import List, Optional
from quizbot.shared import config

logger = logging.getLogger(__name__)

class AIKeyManager:
    """Manages round-robin rotation and fallback across multiple AI keys."""

    def __init__(self):
        self._keys: List[str] = self._load_keys()
        self._cycle = itertools.cycle(self._keys) if self._keys else None

    def _load_keys(self) -> List[str]:
        keys = []
        # Checks comma-separated list or individual variables
        raw = getattr(config, "GEMINI_API_KEYS", None) or getattr(config, "GEMINI_API_KEY", "")
        if isinstance(raw, str):
            keys = [k.strip() for k in raw.split(",") if k.strip()]
        elif isinstance(raw, list):
            keys = [str(k).strip() for k in raw if str(k).strip()]
        return keys

    def get_key(self) -> Optional[str]:
        """Returns the next available API key in round-robin sequence."""
        if not self._keys:
            self._keys = self._load_keys()
            self._cycle = itertools.cycle(self._keys) if self._keys else None
        if not self._cycle:
            return None
        return next(self._cycle)

    def get_all_keys(self) -> List[str]:
        return list(self._keys)

ai_key_pool = AIKeyManager()
