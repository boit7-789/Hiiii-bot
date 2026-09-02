from __future__ import annotations

import json
import logging
import re
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

from ..ai_key_manager import ai_engine
from ..telegram_utils import safe_send_message

logger = logging.getLogger(__name__)


async def aiquiz_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /aiquiz <topic>: Generate 5 MCQs using the multi-engine pool."""
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
            "• <code>/aiquiz Photosynthesis and Plant Biology</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    status_msg = await safe_send_message(
        ctx,
        chat_id,
        f"⚡ <i>Generating questions for:</i> <b>{topic}</b>...",
        parse_mode=ParseMode.HTML,
    )

    prompt = (
        f"You are a professional competitive exam question creator.\n"
        f"Generate exactly 5 high-quality multiple choice questions on the topic: '{topic}'.\n"
        f"Rules:\n"
        f"1. Each question must have exactly 4 options.\n"
        f"2. Provide correct_option_id as an integer (0 for A, 1 for B, 2 for C, 3 for D).\n"
        f"3. Keep the explanation crisp and under 35 words.\n"
        f"4. Respond with ONLY a valid JSON array. Do not include markdown code fences or conversational text.\n\n"
        f"Format:\n"
        f"[\n"
        f"  {{\n"
        f'    "question": "Question text here?",\n'
        f'    "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        f'    "correct_option_id": 0,\n'
        f'    "explanation": "Why this option is correct."\n'
        f"  }}\n"
        f"]"
    )

    try:
        raw_output = await ai_engine.ask_fast(prompt)
        cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_output.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned_json)
        if not isinstance(data, list):
            raise ValueError("Parsed output is not a JSON list.")
    except Exception as exc:
        logger.error("AI quiz generation failed: %s", exc)
        err_text = f"❌ <b>Failed to generate questions.</b>\nError: <code>{str(exc)[:100]}</code>"
        if status_msg:
            await status_msg.edit_text(err_text, parse_mode=ParseMode.HTML)
        else:
            await safe_send_message(ctx, chat_id, err_text, parse_mode=ParseMode.HTML)
        return

    lines = [f"🎯 <b>AI Generated Quiz: {topic.title()}</b>\n"]
    for i, q in enumerate(data, 1):
        q_text = q.get("question", "")
        options = q.get("options", [])
        cid = q.get("correct_option_id", 0)
        exp = q.get("explanation", "")

        lines.append(f"<b>Q{i}. {q_text}</b>")
        for idx, opt in enumerate(options):
            marker = "✅" if idx == cid else "•"
            lines.append(f"  {marker} {opt}")
        if exp:
            lines.append(f"  💡 <i>{exp}</i>")
        lines.append("")

    final_text = "\n".join(lines).strip()

    if status_msg:
        try:
            await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except Exception:
            await status_msg.edit_text(final_text)
    else:
        await safe_send_message(ctx, chat_id, final_text, parse_mode=ParseMode.HTML)


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["aiquiz", "quizgen"], aiquiz_command))
