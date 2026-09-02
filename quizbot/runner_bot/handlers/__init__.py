from __future__ import annotations

from telegram.ext import Application

from . import ai_quiz, mix, pdf_quiz, poll_quiz, quiz_play, scheduling, setup_wizard

_MODULES = (
    quiz_play,     # Core quiz engine (/start <id>, /stop, polls)
    setup_wizard,  # Quiz setup wizard callbacks
    poll_quiz,     # /pollquiz, /pollstop
    mix,           # /mix
    ai_quiz,       # /aiquiz
    pdf_quiz,      # /pdfquiz
    scheduling,    # /schedule
)


def register(application: Application) -> None:
    """Register every handler module's commands/callbacks on application."""
    for module in _MODULES:
        module.register(application)
