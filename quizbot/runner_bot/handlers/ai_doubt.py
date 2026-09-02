from __future__ import annotations

import logging
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

from ..ai_key_manager import ai_key_pool
from ..telegram_utils import safe_send_message

logger = logging.getLogger(__name__)


async def call_ai_with_fallback(prompt: str) -> str:
    """Calls Gemini rotating through keys on 429/failures."""
    keys = ai_key_pool.get_all_keys()
    if not keys:
        return "⚠️ No AI API keys configured. Set GEMINI_API_KEYS in config."

    last_error = ""
    for api_key in keys:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = str(e)
            logger.warning("API key failed, switching to next key. Error: %s", e)
            continue

    return f"❌ All AI API keys exhausted or rate-limited. Error: {last_error[:100]}"


async def aidoubt_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /aidoubt: Answer questions or clarify replied messages."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    reply_to = update.message.reply_to_message
    query_text = " ".join(ctx.args).strip() if ctx.args else ""

    target_content = ""
    if reply_to:
        if reply_to.text:
            target_content = reply_to.text
        elif reply_to.caption:
            target_content = reply_to.caption
        elif reply_to.poll:
            poll_opts = "\n".join([f"- {opt.text}" for opt in reply_to.poll.options])
            target_content = f"Question: {reply_to.poll.question}\nOptions:\n{poll_opts}"

    if not query_text and not target_content:
        await safe_send_message(
            ctx,
            chat_id,
            "💡 <b>How to use /aidoubt:</b>\n\n"
            "• <b>Direct Query:</b> <code>/aidoubt Explain Newton's Third Law</code>\n"
            "• <b>Reply Query:</b> Reply to any question, poll, or message with <code>/aidoubt</code> or <code>/aidoubt why is option B correct?</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    prompt = (
        "You are an expert academic tutor helping a student in a study group.\n"
        "Explain clearly, accurately, and concisely (under 250 words).\n\n"
    )
    if target_content:
        prompt += f"Context/Question Reference:\n\"\"\"{target_content}\"\"\"\n\n"
    if query_text:
        prompt += f"Student's Doubt:\n{query_text}\n"
    else:
        prompt += "Explain this question/concept, clarify the correct answer, and explain why other options are incorrect.\n"

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    status_msg = await safe_send_message(ctx, chat_id, "🤔 <i>Thinking...</i>", parse_mode=ParseMode.HTML)

    explanation = await call_ai_with_fallback(prompt)

    final_text = f"💡 <b>Doubt Clarification:</b>\n\n{explanation}"
    if status_msg:
        try:
            await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except Exception:
            await status_msg.edit_text(final_text)
    else:
        await safe_send_message(ctx, chat_id, final_text, parse_mode=ParseMode.HTML)


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["aidoubt", "doubt"], aidoubt_command))
