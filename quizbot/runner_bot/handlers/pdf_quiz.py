from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from typing import Any, Dict, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from ..ai_key_manager import ai_engine
from ..telegram_utils import safe_send_message
from .ai_quiz import _launch_ai_quiz

logger = logging.getLogger(__name__)

# Temporary in-memory session cache: user_id -> wizard state & extracted pages
_PDF_WIZARD_SESSIONS: Dict[int, Dict[str, Any]] = {}


def _extract_pages_from_pdf(file_bytes: bytes) -> List[str]:
    """Extract page-by-page text content from downloaded PDF bytes."""
    pages: List[str] = []
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            txt = page.extract_text()
            if txt and len(txt.strip()) > 30:
                pages.append(txt.strip())
    except ImportError:
        try:
            import fitz  # PyMuPDF fallback
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                txt = page.get_text()
                if txt and len(txt.strip()) > 30:
                    pages.append(txt.strip())
        except ImportError:
            logger.error("Neither pypdf nor PyMuPDF is installed.")
    except Exception as exc:
        logger.error("Error reading PDF stream: %s", exc)

    return pages


def _prepare_smart_context(pages: List[str], mode: str) -> str:
    """Smart text sampler based on the selected coverage mode."""
    total_pages = len(pages)
    if total_pages == 0:
        return ""

    if mode == "intro":
        # Target first 3 pages
        selected = pages[:min(3, total_pages)]
        return "\n\n".join(selected)[:3500]

    if mode == "high_yield":
        # Concentrate on keywords: definition, principle, act, law, formula, whereas, result
        keywords = ("define", "definition", "article", "section", "law", "theory", "important", "formula", "function", "principle")
        yield_snippets = []
        for p in pages:
            for line in p.split("\n"):
                if any(kw in line.lower() for kw in keywords):
                    yield_snippets.append(line.strip())
        compiled = "\n".join(yield_snippets)
        if len(compiled) > 500:
            return compiled[:3500]
        # Fallback to balanced if not enough keyword triggers
        mode = "whole"

    if mode == "depth":
        # Target middle-to-end analytical pages
        start = max(0, total_pages // 3)
        selected = pages[start:start + 4]
        return "\n\n".join(selected)[:3500]

    # Default / "whole": Balanced sampling from start, middle, and end
    if total_pages <= 3:
        return "\n\n".join(pages)[:3500]

    # Sample uniformly across the whole document
    step = max(1, total_pages // 4)
    sampled = [pages[i] for i in range(0, total_pages, step)][:4]
    return "\n\n--- Next Section ---\n\n".join(sampled)[:3500]


async def _generate_and_dispatch_pdf_quiz(
    ctx: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    session: Dict[str, Any],
    status_msg=None,
) -> None:
    """Builds prompt using selected coverage mode and dispatches interactive polls."""
    doc_title = session["file_name"]
    count = session["count"]
    language = session["language"]
    mode = session["mode"]
    depth = session["depth"]

    loading_text = (
        f"⚡ <i>Synthesizing {count} questions across the document...</i>\n"
        f"📑 <b>File:</b> <code>{doc_title}</code>\n"
        f"🌐 <b>Language:</b> <code>{language}</code>"
    )
    if status_msg:
        try:
            await status_msg.edit_text(loading_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    context_material = _prepare_smart_context(session["pages"], mode)
    if not context_material:
        err = "❌ Unable to read content from this PDF (it may be scanned images only)."
        if status_msg:
            await status_msg.edit_text(err)
        else:
            await safe_send_message(ctx, chat_id, err)
        return

    lang_instructions = {
        "Hindi": "Generate the question, all 4 options, and the explanation completely in Hindi (Devanagari script).",
        "Hinglish": "Generate the question, options, and explanation in conversational Hinglish (Hindi written in Latin characters).",
        "English": "Generate everything in standard, clear English.",
    }.get(language, "Generate in standard English.")

    depth_directive = (
        "Focus on critical thinking, scenario analysis, and tricky distinction between options."
        if depth == "analytical"
        else "Focus on direct concept verification, key facts, and clear definitions."
    )

    prompt = (
        f"You are an expert exam paper creator.\n"
        f"Generate exactly {count} high-quality multiple choice questions strictly based on the text below.\n"
        f"Cognitive Focus: {depth_directive}\n"
        f"Language Directive: {lang_instructions}\n\n"
        f"Strict Poll Rules:\n"
        f"1. Exactly 4 concise options per question (under 75 characters each).\n"
        f"2. Direct question text under 240 characters.\n"
        f"3. Provide correct_option_id as an integer (0 for A, 1 for B, 2 for C, 3 for D).\n"
        f"4. Crisp explanation under 140 characters.\n"
        f"5. Return ONLY a valid JSON array matching this format (no markdown code blocks, no text outside JSON):\n"
        f"[\n"
        f"  {{\n"
        f'    "question": "Question text here?",\n'
        f'    "options": ["Option A", "Option B", "Option C", "Option D"],\n'
        f'    "correct_option_id": 0,\n'
        f'    "explanation": "Why this option is correct."\n'
        f"  }}\n"
        f"]\n\n"
        f"Document Material:\n{context_material}"
    )

    try:
        raw_output = await ai_engine.ask_fast(prompt)
        cleaned_json = re.sub(r"^```(?:json)?|```$", "", raw_output.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned_json)
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("Invalid format received from AI.")
    except Exception as exc:
        logger.error("PDF quiz generation failed: %s", exc)
        err_msg = f"❌ <b>Generation Failed</b>\nError: <code>{str(exc)[:100]}</code>"
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

    clean_title = doc_title.replace(".pdf", "").replace("_", " ").title()
    await _launch_ai_quiz(ctx, chat_id, data, clean_title, language)


async def pdfquiz_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pdfquiz: Initializes the multi-option wizard for a replied PDF."""
    if not update.message:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    reply_to = update.message.reply_to_message

    if not reply_to or not reply_to.document:
        await safe_send_message(
            ctx,
            chat_id,
            "💡 <b>How to use /pdfquiz:</b>\n\n"
            "Reply to any uploaded PDF document with <code>/pdfquiz</code> to launch the interactive exam generator.",
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
        "📄 <i>Downloading and scanning PDF pages...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        file = await ctx.bot.get_file(doc.file_id)
        pdf_bytes = await file.download_as_bytearray()
        pages = _extract_pages_from_pdf(bytes(pdf_bytes))
    except Exception as exc:
        logger.error("Failed to read PDF: %s", exc)
        await status_msg.edit_text(f"❌ Failed to process PDF: `{str(exc)[:100]}`")
        return

    if not pages:
        await status_msg.edit_text("❌ Could not extract readable text from this PDF. It may be scanned or encrypted.")
        return

    _PDF_WIZARD_SESSIONS[user_id] = {
        "file_name": doc.file_name,
        "pages": pages,
        "total_pages": len(pages),
        "chat_id": chat_id,
        "count": 5,
        "mode": "whole",
        "depth": "direct",
        "language": "English",
    }

    # Step 1: Question Count
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("3 Polls", callback_data=f"pdfq:cnt:3:{user_id}"),
            InlineKeyboardButton("5 Polls", callback_data=f"pdfq:cnt:5:{user_id}"),
            InlineKeyboardButton("10 Polls", callback_data=f"pdfq:cnt:10:{user_id}"),
        ],
        [
            InlineKeyboardButton("15 Polls", callback_data=f"pdfq:cnt:15:{user_id}"),
            InlineKeyboardButton("20 Polls", callback_data=f"pdfq:cnt:20:{user_id}"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data=f"pdfq:cancel:0:{user_id}")
        ],
    ])

    await status_msg.edit_text(
        f"⚙️ <b>PDF Quiz Wizard — Step 1/4</b>\n\n"
        f"📄 <b>Document:</b> <code>{doc.file_name}</code>\n"
        f"📑 <b>Pages Detected:</b> <code>{len(pages)}</code>\n\n"
        f"How many quiz polls would you like to generate?",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


async def pdf_wizard_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles step-by-step inline button transitions for PDF quiz creation."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 4 or parts[0] != "pdfq":
        return

    step, value, target_uid = parts[1], parts[2], int(parts[3])
    if query.from_user.id != target_uid:
        return

    if step == "cancel":
        _PDF_WIZARD_SESSIONS.pop(target_uid, None)
        await query.message.edit_text("❌ <i>PDF Quiz generation cancelled.</i>", parse_mode=ParseMode.HTML)
        return

    session = _PDF_WIZARD_SESSIONS.get(target_uid)
    if not session:
        await query.message.edit_text(
            "⚠️ <i>Session expired. Please reply with <code>/pdfquiz</code> again.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 1 -> Step 2: Smart Coverage Mode
    if step == "cnt":
        session["count"] = int(value)
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🌐 Whole Document (Even Spread)", callback_data=f"pdfq:mode:whole:{target_uid}"),
            ],
            [
                InlineKeyboardButton("🎯 High-Yield / Key Facts Only", callback_data=f"pdfq:mode:high_yield:{target_uid}"),
            ],
            [
                InlineKeyboardButton("📑 First Chapters / Basics", callback_data=f"pdfq:mode:intro:{target_uid}"),
                InlineKeyboardButton("🔬 In-Depth Concepts", callback_data=f"pdfq:mode:depth:{target_uid}"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data=f"pdfq:cancel:0:{target_uid}"),
            ],
        ])
        await query.message.edit_text(
            f"⚙️ <b>PDF Quiz Wizard — Step 2/4</b>\n\n"
            f"📄 <b>Document:</b> <code>{session['file_name']}</code>\n"
            f"📊 <b>Questions:</b> <code>{session['count']}</code>\n\n"
            f"Choose the <b>Coverage Intelligence</b> mode:",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 2 -> Step 3: Question Style / Depth
    if step == "mode":
        session["mode"] = value
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Direct Factual / Recall", callback_data=f"pdfq:depth:direct:{target_uid}"),
            ],
            [
                InlineKeyboardButton("🧠 Analytical / Tricky Concepts", callback_data=f"pdfq:depth:analytical:{target_uid}"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data=f"pdfq:cancel:0:{target_uid}"),
            ],
        ])
        await query.message.edit_text(
            f"⚙️ <b>PDF Quiz Wizard — Step 3/4</b>\n\n"
            f"📄 <b>Document:</b> <code>{session['file_name']}</code>\n"
            f"🎯 <b>Mode:</b> <code>{session['mode'].replace('_', ' ').title()}</code>\n\n"
            f"Select the <b>Question Style</b>:",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 3 -> Step 4: Language Selection
    if step == "depth":
        session["depth"] = value
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇬🇧 English", callback_data=f"pdfq:lang:English:{target_uid}"),
                InlineKeyboardButton("🇮🇳 हिन्दी (Hindi)", callback_data=f"pdfq:lang:Hindi:{target_uid}"),
            ],
            [
                InlineKeyboardButton("🔤 Hinglish", callback_data=f"pdfq:lang:Hinglish:{target_uid}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"pdfq:cancel:0:{target_uid}"),
            ],
        ])
        await query.message.edit_text(
            f"⚙️ <b>PDF Quiz Wizard — Step 4/4</b>\n\n"
            f"📄 <b>Document:</b> <code>{session['file_name']}</code>\n"
            f"📊 <b>Questions:</b> <code>{session['count']}</code>\n"
            f"🧠 <b>Style:</b> <code>{session['depth'].title()}</code>\n\n"
            f"Select the output language:",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
        return

    # Step 4 -> Launch Generation
    if step == "lang":
        session["language"] = value
        data = _PDF_WIZARD_SESSIONS.pop(target_uid, None)
        if not data:
            return

        await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        await _generate_and_dispatch_pdf_quiz(
            ctx=ctx,
            chat_id=query.message.chat_id,
            session=data,
            status_msg=query.message,
        )


def register(application: Application) -> None:
    application.add_handler(CommandHandler(["pdfquiz"], pdfquiz_command))
    application.add_handler(CallbackQueryHandler(pdf_wizard_callback, pattern=r"^pdfq:"))
