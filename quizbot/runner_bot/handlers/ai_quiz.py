from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode, PollType
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from ..ai_key_manager import ai_engine
from ..telegram_utils import safe_send_message

logger = logging.getLogger(__name__)

# Temporary in-memory session store: user_id -> wizard state
_WIZARD_SESSIONS: Dict[int, Dict[str, Any]] = {}


async def _launch_ai_quiz(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    questions_data: List[dict],
    topic: str,
    language: str = "English",
) -> None:
    """Helper used by /aiquiz and /pdfquiz to dispatch native Telegram Quiz Polls."""
    await safe_send_message(
        ctx,
        chat_id,
        f"🎯 <b>Interactive Quiz: {topic.title()}</b>\n"
        f"🌐 <i>Language: {language} • Questions: {len(questions_data)}</i>\n\n"
        f"<i>Tap your answer on the polls below:</i>",
        parse_mode=ParseMode.HTML,
    )

    for i, q in enumerate(questions_data, 1):
        q_text = f"Q{i}. {q.get('question', '').strip()}"
        raw_options = q.get("options", [])
        options = [str(opt).strip() for opt in raw_options if str(opt).strip()]

        # Enforce Telegram poll bounds: question <= 300 chars, option <= 100 chars
        q_text = (q_text[:297] + "...") if len(q_text) > 300 else q_text
        options = [(opt[:97] + "...") if len(opt) > 100 else opt for opt in options][:10]

        if len(options) < 2:
            continue

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
            # Stagger poll deliveries to preserve question order
            await asyncio.sleep(0.5)
        except Exception as err:
            logger.error("Failed to send quiz poll #%d: %s", i, err)


async def _generate_and_dispatch(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    topic: str,
    count: int,
    language: str,
    difficulty: str,
    status_msg=None,
) -> None:
    """Invokes the multi-engine AI pool with complete parameters and sends polls."""
    loading_text = (
        f"⚡ <i>Synthesizing {count} {difficulty} questions in <b>{language}</b> for:</i> "
        f"<b>{topic}</b>..."
    )
    if status_msg:
        try:
            await status_msg.edit_text(loading_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    lang_instructions = {
        "Hindi": "Generate the question, all 4 options, and the explanation completely in Hindi (Devanagari script).",
        "Hinglish": "Generate the question, options, and explanation in conversational Hinglish (Hindi written in Latin script).",
        "English": "Generate everything in standard, clear English.",
    }.get(language, "Generate in standard English.")

    prompt = (
        f"You are an expert academic exam creator.\n"
        f"Create exactly {count} multiple-choice questions on: '{topic}'.\n"
        f"Difficulty: {difficulty}.\n"
        f"Language Directive: {lang_instructions}\n\n"
        f"Strict Poll Rules:\n"
        f"1. Exactly 4 options per question (under 75 characters each).\n"
        f"2. Question text must be direct and under 240 characters.\n"
        f"3. Provide correct_option_id as an integer (0 for A, 1 for B, 2 for C, 3 for D).\n"
        f"4. Explanation must be under 140 characters.\n"
        f"5. Return ONLY a valid JSON array matching this exact format with NO markdown code fences:\n"
        f"[\n"
        f"  {{\n"
        f'    "question": "Question text here?",\n'
        f'    "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        f'    "correct_option_id": 0,\n'
        f'    "explanation": "Why this answer is correct."\n'
        f"  }}\n"
        f"]"
    )

    try:
        raw_output = await ai_engine.ask_fast(prompt)
        cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_output.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned_json)
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("Invalid question list received from engine.")
    except Exception as exc:
        logger.error("AI quiz generation error: %s", exc)
        err_msg = (
            f"❌ <b>Generation Failed</b>\n"
            f"Error: <code>{str(exc)[:100]}</code>\n\n"
            f"Please try again or pick a different topic."
        )
        if status_msg:
            await status_msg.edit_text(err_msg, parse_mode=ParseMode.HTML)
        else:
            await safe_send_message(ctx, chat_id, err_msg, parse_mode=ParseMode.HTML)
        return

    if status_msg:
        try:
            await status_msg.delete()
        except Exception:
            pass

    await _launch_ai_quiz(ctx, chat_id, data, topic, language)


async def aiquiz_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /aiquiz <topic>: Opens the configuration wizard."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    topic = " ".join(ctx.args).strip() if ctx.args else ""

    if not topic:
        await safe_send_message(
            ctx,
            chat_id,
            "💡 <b>How to use /aiquiz:</b>\n\n"
            "• <code>/aiquiz Indian Polity</code>\n"
            "• <code>/aiquiz Modern History 1857 Revolt</code>\n"
            "• <code>/aiquiz Photosynthesis and Plant Cells</code>\n\n"
            "<i>Type the command followed by any subject or chapter name!</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    _WIZARD_SESSIONS[user_id] = {
        "topic": topic,
        "chat_id": chat_id,
        "count": 5,
        "language": "English",
        "difficulty": "Moderate",
    }

    # Step 1: Select Question Count
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("3 Polls", callback_data=f"aiqw:cnt:3:{user_id}"),
            InlineKeyboardButton("5 Polls", callback_data=f"aiqw:cnt:5:{user_id}"),
            InlineKeyboardButton("10 Polls", callback_data=f"aiqw:cnt:10:{user_id}"),
        ],
        [
            InlineKeyboardButton("15 Polls", callback_data=f"aiqw:cnt:15:{user_id}"),
            InlineKeyboardButton("20 Polls", callback_data=f"aiqw:cnt:20:{user_id}"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data=f"aiqw:cancel:0:{user_id}")
        ],
    ])

    await safe_send_message(
        ctx,
        chat_id,
        f"⚙️ <b>AI Quiz Setup — Step 1/3</b>\n\n"
        f"📌 <b>Topic:</b> <code>{topic}</code>\n\n"
        f"How many quiz polls would you like to generate?",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


async def wizard_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the multi-step configuration callbacks for /aiquiz."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 4 or parts[0] != "aiqw":
        return

    step, value, target_uid = parts[1], parts[2], int(parts[3])
    if query.from_user.id != target_uid:
        return

    if step == "cancel":
        _WIZARD_SESSIONS.pop(target_uid, None)
        await query.message.edit_text("❌ <i>Quiz generation cancelled.</i>", parse_mode=ParseMode.HTML)
        return

    session = _WIZARD_SESSIONS.get(target_uid)
    if not session:
        await query.message.edit_text(
            "⚠️ <i>Session expired. Please run <code>/aiquiz &lt;topic&gt;</code> again.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 1 -> Step 2: Language Selection
    if step == "cnt":
        session["count"] = int(value)
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇬🇧 English", callback_data=f"aiqw:lang:English:{target_uid}"),
                InlineKeyboardButton("🇮🇳 हिन्दी (Hindi)", callback_data=f"aiqw:lang:Hindi:{target_uid}"),
            ],
            [
                InlineKeyboardButton("🔤 Hinglish", callback_data=f"aiqw:lang:Hinglish:{target_uid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"aiqw:cancel:0:{target_uid}"),
            ],
        ])
        await query.message.edit_text(
            f"⚙️ <b>AI Quiz Setup — Step 2/3</b>\n\n"
            f"📌 <b>Topic:</b> <code>{session['topic']}</code>\n"
            f"📊 <b>Questions:</b> <code>{session['count']}</code>\n\n"
            f"Select the language for the questions:",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 2 -> Step 3: Difficulty Selection
    if step == "lang":
        session["language"] = value
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Easy (Basic)", callback_data=f"aiqw:diff:Easy:{target_uid}"),
                InlineKeyboardButton("🟡 Moderate (Standard)", callback_data=f"aiqw:diff:Moderate:{target_uid}"),
            ],
            [
                InlineKeyboardButton("🔴 Hard (Exam Level)", callback_data=f"aiqw:diff:Hard:{target_uid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"aiqw:cancel:0:{target_uid}"),
            ],
        ])
        await query.message.edit_text(
            f"⚙️ <b>AI Quiz Setup — Step 3/3</b>\n\n"
            f"📌 <b>Topic:</b> <code>{session['topic']}</code>\n"
            f"📊 <b>Questions:</b> <code>{session['count']}</code>\n"
            f"🌐 <b>Language:</b> <code>{session['language']}</code>\n\n"
            f"Select the difficulty level:",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 3 -> Launch Generation
    if step == "diff":
        session["difficulty"] = value
        data = _WIZARD_SESSIONS.pop(target_uid, None)
        if not data:
            return

        await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        await _generate_and_dispatch(
            ctx=ctx,
            chat_id=query.message.chat_id,
            topic=data["topic"],
            count=data["count"],
            language=data["language"],
            difficulty=data["difficulty"],
            status_msg=query.message,
        )


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["aiquiz", "quizgen"], aiquiz_command))
    application.add_handler(CallbackQueryHandler(wizard_callback, pattern=r"^aiqw:"))
