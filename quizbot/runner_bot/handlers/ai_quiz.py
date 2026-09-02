from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, List
from telegram import Update
from telegram.constants import ParseMode, ChatAction, PollType
from telegram.ext import Application, CommandHandler, ContextTypes

from ..ai_key_manager import ai_engine
from ..telegram_utils import safe_send_message

logger = logging.getLogger(__name__)


async def _launch_ai_quiz(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, questions_data: List[dict], topic: str) -> None:
    """Helper used to send questions as real interactive Telegram Quiz Polls."""
    await safe_send_message(
        ctx,
        chat_id,
        f"🎯 <b>Interactive Quiz: {topic.title()}</b>\n<i>Answer the polls below:</i>",
        parse_mode=ParseMode.HTML,
    )

    for i, q in enumerate(questions_data, 1):
        q_text = f"Q{i}. {q.get('question', '').strip()}"
        options = [str(opt).strip() for opt in q.get("options", []) if str(opt).strip()]
        
        # Ensure Telegram poll limits: 1 to 300 chars for question, max 100 chars per option
        q_text = (q_text[:297] + "...") if len(q_text) > 300 else q_text
        options = [(opt[:97] + "...") if len(opt) > 100 else opt for opt in options][:10]

        cid = q.get("correct_option_id", 0)
        if not (0 <= cid < len(options)):
            cid = 0

        explanation = q.get("explanation", "").strip()
        explanation = (explanation[:197] + "...") if len(explanation) > 200 else explanation

        try:
            await ctx.bot.send_poll(
                chat_id=chat_id,
                question=q_text,
                options=options,
                type=PollType.QUIZ,
                correct_option_id=cid,
                explanation=explanation if explanation else None,
                is_anonymous=False,
            )
            # Small delay to keep questions strictly in order
            await asyncio.sleep(0.5)
        except Exception as err:
            logger.error("Failed to send poll %d: %s", i, err)


async def aiquiz_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /aiquiz <topic>: Generate 5 interactive Quiz Polls via AI engine."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    topic = " ".join(ctx.args).strip() if ctx.args else ""

    if not topic:
        await safe_send_message(
            ctx,
            chat_id,
            "💡 <b>How to use /aiquiz:</b>\n\n"
            "• <code>/aiquiz Polity Fundamental Rights</code>\n"
            "• <code>/aiquiz Modern History 1857 Revolt</code>\n"
            "• <code>/aiquiz Biology Photosynthesis</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    status_msg = await safe_send_message(
        ctx,
        chat_id,
        f"⚡ <i>Generating interactive quiz polls for:</i> <b>{topic}</b>...",
        parse_mode=ParseMode.HTML,
    )

    prompt = (
        f"You are an expert exam question creator.\n"
        f"Generate exactly 5 high-yield multiple-choice questions on: '{topic}'.\n"
        f"Rules for Telegram Polls:\n"
        f"1. Each question must have exactly 4 concise options (under 80 characters each).\n"
        f"2. Keep the question text under 250 characters.\n"
        f"3. Provide correct_option_id as an integer (0 for A, 1 for B, 2 for C, 3 for D).\n"
        f"4. Keep explanation under 150 characters.\n"
        f"5. Return ONLY a valid JSON array matching this format (no markdown blocks, no text outside JSON):\n"
        f"[\n"
        f"  {{\n"
        f'    "question": "Question text here?",\n'
        f'    "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        f'    "correct_option_id": 0,\n'
        f'    "explanation": "Brief explanation why correct."\n'
        f"  }}\n"
        f"]"
    )

    try:
        raw_output = await ai_engine.ask_fast(prompt)
        cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_output.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned_json)
        if not isinstance(data, list):
            raise ValueError("Output must be a list of questions.")
    except Exception as exc:
        logger.error("AI quiz generation error: %s", exc)
        err_text = f"❌ <b>Failed to generate quiz polls.</b>\nError: <code>{str(exc)[:100]}</code>"
        if status_msg:
            await status_msg.edit_text(err_text, parse_mode=ParseMode.HTML)
        else:
            await safe_send_message(ctx, chat_id, err_text, parse_mode=ParseMode.HTML)
        return

    if status_msg:
        try:
            await status_msg.delete()
        except Exception:
            pass

    await _launch_ai_quiz(ctx, chat_id, data, topic)


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["aiquiz", "quizgen"], aiquiz_command))
