from __future__ import annotations

import html
import logging
import re
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

from ..ai_key_manager import ai_engine
from ..telegram_utils import safe_send_message

logger = logging.getLogger(__name__)


def markdown_to_telegram_html(text: str) -> str:
    """Converts AI markdown formatting into Telegram-supported HTML tags."""
    # Escape HTML special characters first to avoid injection / parse errors
    text = html.escape(text)

    # Convert headers (### Header -> <b>Header</b>)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Convert bold (**text** or __text__ -> <b>text</b>)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Convert italics (*text* or _text_ -> <i>text</i>)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)

    # Convert inline code (`code` -> <code>code</code>)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

    # Clean up bullet asterisks to neat bullet dots
    text = re.sub(r"^\s*[\*\-]\s+", "• ", text, flags=re.MULTILINE)

    return text.strip()


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
            "• <b>Direct Query:</b> <code>/aidoubt What is CUET?</code>\n"
            "• <b>Reply Query:</b> Reply to any quiz, question, or message with <code>/aidoubt</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Enforce precise formatting, emojis, bullet points, and zero filler text
    prompt = (
        "You are an expert academic tutor for Telegram students.\n"
        "Formatting Rules:\n"
        "- Use relevant emojis for every section and bullet point.\n"
        "- Structure answers in concise, high-yield bullet points.\n"
        "- Bold key terms using **term**.\n"
        "- Keep it brief, accurate, and under 200 words.\n"
        "- Do NOT include conversational conclusions (e.g. do not ask 'Would you like to know more?').\n\n"
    )

    if target_content:
        prompt += f"Context/Question Reference:\n\"\"\"{target_content}\"\"\"\n\n"
    if query_text:
        prompt += f"User Query:\n{query_text}\n"
    else:
        prompt += "Explain this question/concept, clarify the correct answer, and explain why other options are incorrect.\n"

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    status_msg = await safe_send_message(ctx, chat_id, "⚡ <i>Analyzing doubt...</i>", parse_mode=ParseMode.HTML)

    raw_response = await ai_engine.ask_fast(prompt)
    formatted_explanation = markdown_to_telegram_html(raw_response)

    final_text = f"💡 <b>Doubt Clarification:</b>\n\n{formatted_explanation}"
    if status_msg:
        try:
            await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except Exception:
            await status_msg.edit_text(raw_response)
    else:
        await safe_send_message(ctx, chat_id, final_text, parse_mode=ParseMode.HTML)


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["aidoubt", "doubt"], aidoubt_command))
