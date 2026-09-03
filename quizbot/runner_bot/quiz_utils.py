"""
Advance Quiz Bot — Open Source Project
This project was originally developed by Gagan (github.com/devgaganin).
Reference: https://t.me/advance_quiz_bot
The codebase has been reviewed and verified with the assistance of Claude AI.
"""

from __future__ import annotations

import random
from typing import Any, Optional

from quizbot.database import AuthChatRepository, BatchRepository, QuizRepository, get_db

# Telegram's official ID for group anonymous admin actions
ANONYMOUS_ADMIN_ID = 1087968824


def is_anonymous_admin(user_id: Optional[int], chat_id: Optional[int] = None) -> bool:
    """Return True if the user_id corresponds to an anonymous group administrator."""
    if user_id == ANONYMOUS_ADMIN_ID:
        return True
    if chat_id is not None and user_id == chat_id:
        return True
    return False


def shuffle_options(options: list[str], correct_id: int) -> tuple[list[str], int]:
    """Shuffle all options, remapping a single correct index."""
    paired = list(enumerate(options))
    random.shuffle(paired)
    indices, shuffled = zip(*paired)
    mapping = {orig: new for new, orig in enumerate(indices)}
    return list(shuffled), mapping[correct_id]


def shuffle_options_multi(
    options: list[str], correct_ids: list[int], count: Optional[int] = None
) -> tuple[list[str], list[int]]:
    """Shuffle options and remap a list of correct indices.

    `count` controls how many of the leading option positions get shuffled
    among themselves -- the rest keep their original position:
      - None or count <= 0        -> shuffle ALL options
      - count >= len(options)     -> shuffle ALL options
      - 0 < count < len(options)  -> only the first `count` positions are
                                     shuffled; the rest stay exactly where
                                     they were.
    """
    n = len(options)
    if count is None or count <= 0 or count >= n:
        paired = list(enumerate(options))
        random.shuffle(paired)
        indices, shuffled = zip(*paired)
        mapping = {orig: new for new, orig in enumerate(indices)}
        return list(shuffled), [mapping[c] for c in correct_ids]

    head_indices = list(range(count))
    random.shuffle(head_indices)
    new_order = head_indices + list(range(count, n))
    shuffled = [options[i] for i in new_order]
    mapping = {orig: new for new, orig in enumerate(new_order)}
    return shuffled, [mapping[c] for c in correct_ids]


def is_correct(user_options: Any, correct: Any) -> bool:
    """Multi-correct aware answer check.

    `correct` and `user_options` may each be a single int or a list of
    ints. For multi-correct questions the user must select EXACTLY the
    correct set -- any extra or missing pick counts as wrong.
    """
    if isinstance(correct, list):
        correct_set = set(correct)
        user_set = set(user_options) if isinstance(user_options, list) else {user_options}
        return user_set == correct_set
    if isinstance(user_options, list):
        return user_options == [correct]
    return user_options == correct


def get_section_for_question(sections: list[dict], q_idx: int) -> Optional[dict]:
    """Return the section dict that owns 0-based question index q_idx."""
    for sec in sections:
        start, end = sec["question_range"]
        if start - 1 <= q_idx < end:
            return sec
    return None


def section_marks(
    section: Optional[dict], global_correct_mark: float, global_neg_mark: float
) -> tuple[float, float]:
    """Return (correct_mark, neg_mark) for a section, falling back to globals."""
    if not section:
        return global_correct_mark, global_neg_mark
    return (
        section.get("correct_mark", global_correct_mark),
        section.get("neg_mark", global_neg_mark),
    )


async def check_batch_access(qid: str, chat_id: int, ctx=None, user_id: Optional[int] = None) -> dict:
    """Check whether chat_id (optionally via user_id's membership in an
    auth chat) has batch access to a paid quiz. Returns {has_access, batch}.
    """
    batch_repo = BatchRepository(get_db())
    try:
        has_direct = await batch_repo.check_access(qid, chat_id)
        batch = await batch_repo.info_for_quiz(qid)
        if has_direct:
            return {"has_access": True, "batch": batch}

        # Do not attempt chat member lookups for anonymous admin placeholders
        if ctx and batch and user_id and not is_anonymous_admin(user_id, chat_id):
            for ac_chat_id in batch.get("chats", []):
                try:
                    member = await ctx.bot.get_chat_member(ac_chat_id, user_id)
                    if member.status not in ("left", "kicked"):
                        return {"has_access": True, "batch": batch}
                except Exception:
                    pass
        return {"has_access": False, "batch": batch}
    except Exception:
        return {"has_access": False, "batch": None}


async def resolve_quiz_access(
    qid: str, quiz: dict, chat_id: int, chat_type: str, user_id: int, ctx=None
) -> tuple[bool, Optional[dict]]:
    """Decide whether this chat/user may run `quiz`.

    Returns (allowed, batch_info_or_None). When quiz is free, or the
    requesting chat is the quiz creator's own private chat, access is
    always allowed. For paid quizzes in groups, only the *group's* chat_id
    being directly authorised (via auth_chats or a batch) grants access --
    individual user membership never grants group-run rights.
    """
    creator_id = quiz.get("creator_id", chat_id)
    is_paid = quiz.get("quiz_type") == "paid"
    if not is_paid:
        return True, None
    if chat_id == creator_id and chat_type == "private":
        return True, None

    is_group = chat_type in ("group", "supergroup")
    is_anon = is_anonymous_admin(user_id, chat_id)

    # In private chat or non-anonymous personal check
    if not is_group and not is_anon:
        auth_repo = AuthChatRepository(get_db())
        auth_users = await auth_repo.get(creator_id)
        if user_id in auth_users:
            return True, None

    # In groups (or when acting anonymously), evaluate the chat's authorized access
    result = await check_batch_access(
        qid, chat_id, ctx=ctx, user_id=None if (is_group or is_anon) else user_id
    )
    return result["has_access"], result.get("batch")
