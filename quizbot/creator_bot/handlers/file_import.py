"""
Advance Quiz Bot — File Import Handler
Supports importing quizzes via document uploads (.txt, .json).
"""

from __future__ import annotations

import json
import logging
from io import BytesIO

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

from quizbot.database import QuizRepository, get_db
from quizbot.shared import config
from quizbot.shared.utils import is_premium_user

logger = logging.getLogger(__name__)


def _is_owner_or_admin(user_id: int) -> bool:
    owner_id = (
        getattr(config, "OWNER_ID", None)
        or getattr(config, "ADMIN_USER_ID", None)
        or getattr(config, "OWNER_USER_ID", None)
    )
    if not owner_id:
        return False
    try:
        return str(owner_id) == str(user_id)
    except (TypeError, ValueError):
        return False


async def process_uploaded_file(c: Client, m: Message) -> list[dict] | None:
    """Helper used by quiz_creation to parse uploaded files into question lists."""
    if not m.document:
        return None

    fname = (m.document.file_name or "").lower()
    if not (fname.endswith(".txt") or fname.endswith(".json")):
        return None

    try:
        file_bytes = await c.download_media(m, in_memory=True)
        raw_data = bytes(file_bytes.getbuffer()).decode("utf-8")

        if fname.endswith(".json"):
            data = json.loads(raw_data)
            return data if isinstance(data, list) else data.get("questions", [])

        from .quiz_creation import parse_question_block
        parsed = []
        for block in raw_data.strip().split("\n\n"):
            if not block.strip():
                continue
            q = parse_question_block(block)
            if q:
                parsed.append(q)
        return parsed or None
    except Exception as e:
        logger.error("process_uploaded_file error: %s", e)
        return None


async def import_command(c: Client, m: Message) -> None:
    """Handle /import command."""
    uid = m.from_user.id
    is_owner = _is_owner_or_admin(uid)

    if not is_owner:
        try:
            if not await is_premium_user(uid):
                await m.reply_text("🔒 Premium required to import quizzes: /pay")
                return
        except Exception as e:
            logger.error("Premium check error in import_command: %s", e)
            await m.reply_text("🔒 Premium required to import quizzes: /pay")
            return

    target_msg = m.reply_to_message if m.reply_to_message and m.reply_to_message.document else None
    doc_msg = target_msg or (m if m.document else None)

    if not doc_msg:
        await m.reply_text(
            "📂 **Quiz File Importer**\n\n"
            "To import a quiz from a file:\n"
            "1. Upload a **.txt** or **.json** file containing questions.\n"
            "2. Send or reply to that file with `/import`.\n\n"
            "**Supported Text Format:**\n"
            "```text\n"
            "What is the capital of France?\n"
            "Berlin\n"
            "Madrid\n"
            "Paris ✅\n"
            "Rome\n"
            "Ex: Paris is the capital and largest city of France.\n"
            "```"
        )
        return

    doc = doc_msg.document
    if not (doc.file_name.endswith(".txt") or doc.file_name.endswith(".json")):
        await m.reply_text("⚠️ Please provide a valid **.txt** or **.json** file.")
        return

    status_msg = await m.reply_text("⏳ Downloading and parsing file...")

    try:
        parsed_questions = await process_uploaded_file(c, doc_msg)
        if not parsed_questions:
            await status_msg.edit_text("❌ No valid questions found in this file.")
            return

        db = get_db()
        repo = QuizRepository(db)
        quiz_name = doc.file_name.rsplit(".", 1)[0].replace("_", " ")

        created_quiz = await repo.create(
            creator_id=uid,
            quiz_name=quiz_name,
            questions=parsed_questions,
            timer=30,
            quiz_type="free",
        )

        qid = created_quiz.get("qid") or created_quiz.get("question_set_id", "Unknown")

        await status_msg.edit_text(
            f"✅ **Import Successful!**\n\n"
            f"🏷️ **Name:** {quiz_name}\n"
            f"❓ **Questions:** {len(parsed_questions)}\n"
            f"🆔 **Quiz ID:** `{qid}`\n\n"
            f"Use `/quiz {qid}` in groups to play, or `/edit {qid}` to make changes."
        )
    except Exception as e:
        logger.exception("Failed to import file: %s", e)
        await status_msg.edit_text(f"❌ Error processing file: {e}")


def register(app: Client) -> None:
    app.add_handler(MessageHandler(import_command, filters.command("import") & filters.private))
