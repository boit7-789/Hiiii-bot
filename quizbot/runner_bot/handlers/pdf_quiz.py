from __future__ import annotations

import io
import json
import logging
import re
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

from ..ai_key_manager import ai_engine
from ..telegram_utils import safe_send_message
from .ai_quiz import _launch_ai_quiz

logger = logging.getLogger(__name__)


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract readable text from downloaded PDF bytes."""
    text_content = []
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages[:10]:  # Cap to first 10 pages for prompt safety
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
    except ImportError:
        try:
            import fitz  # PyMuPDF fallback
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc[:10]:
                text_content.append(page.get_text())
        except ImportError:
            logger.error("Neither pypdf nor PyMuPDF is installed.")
            return ""
    except Exception as e:
        logger.error("Error reading PDF: %s", e)
        return ""

    return "\n".join(text_content).strip()


async def pdfquiz_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pdfquiz: Generates quiz polls from a replied PDF document using ai_engine."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    reply_to = update.message.reply_to_message

    if not reply_to or not reply_to.document:
        await safe_send_message(
            ctx,
            chat_id,
            "💡 <b>How to use /pdfquiz:</b>\n\n"
            "Reply to any uploaded PDF document with <code>/pdfquiz</code> to automatically generate an interactive test.",
            parse_mode=ParseMode.HTML,
        )
        return

    doc = reply_to.document
    if not (doc.file_name and doc.file_name.lower().endswith(".pdf")) and doc.mime_type != "application/pdf":
        await safe_send_message(ctx, chat_id, "⚠️ The replied file must be a PDF document.")
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    status_msg = await safe_send_message(
        ctx,
        chat_id,
        "📄 <i>Downloading and reading PDF...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        file = await ctx.bot.get_file(doc.file_id)
        pdf_bytes = await file.download_as_bytearray()
        pdf_text = _extract_text_from_pdf(bytes(pdf_bytes))
    except Exception as exc:
        logger.error("Failed to download or parse PDF: %s", exc)
        await status_msg.edit_text(f"❌ Failed to read PDF file: `{str(exc)[:100]}`")
        return

    if not pdf_text or len(pdf_text) < 50:
        await status_msg.edit_text("❌ Could not extract enough text from this PDF. It might be scanned or image-only.")
        return

    await status_msg.edit_text("⚡ <i>Synthesizing quiz polls using multi-engine AI...</i>", parse_mode=ParseMode.HTML)

    prompt = (
        "You are an expert exam question creator.\n"
        "Generate exactly 5 high-yield multiple choice questions based strictly on the text provided.\n"
        "Rules for Telegram Polls:\n"
        "1. Each question must have exactly 4 concise options (under 80 characters each).\n"
        "2. Keep the question text under 250 characters.\n"
        "3. Provide correct_option_id as an integer (0 for A, 1 for B, 2 for C, 3 for D).\n"
        "4. Keep explanation under 150 characters.\n"
        "5. Return ONLY a valid JSON array matching this format (no markdown blocks, no text outside JSON):\n"
        "[\n"
        "  {\n"
        '    "question": "Question text here?",\n'
        '    "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        '    "correct_option_id": 0,\n'
        '    "explanation": "Brief explanation why correct."\n'
        "  }\n"
        "]\n\n"
        f"Source Material:\n{pdf_text[:3500]}"
    )

    try:
        raw_output = await ai_engine.ask_fast(prompt)
        cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_output.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned_json)
        if not isinstance(data, list):
            raise ValueError("Output must be a list of questions.")
    except Exception as exc:
        logger.error("AI quiz generation error: %s", exc)
        await status_msg.edit_text(f"❌ <b>Failed to generate quiz polls.</b>\nError: <code>{str(exc)[:100]}</code>", parse_mode=ParseMode.HTML)
        return

    try:
        await status_msg.delete()
    except Exception:
        pass

    topic_title = doc.file_name.replace(".pdf", "").replace("_", " ").title()
    await _launch_ai_quiz(ctx, chat_id, data, topic_title)


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["pdfquiz"], pdfquiz_command))
