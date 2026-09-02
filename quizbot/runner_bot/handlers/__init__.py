from __future__ import annotations

from telegram.ext import Application

from . import ai_quiz, mix, pdf_quiz, poll_quiz, quiz_play, reports, scheduling, setup_wizard, translation

_MODULES = (
    quiz_play,     # /start, /pause, /resume, /stop, /leaderboard, /slow, /fast, /normal, poll answers
    setup_wizard,  # qs_* quiz-setup wizard callbacks
    poll_quiz,     # /pollquiz, /pollstop
    mix,           # /mix
    ai_quiz,       # /aiquiz
    pdf_quiz,      # /pdfquiz
    reports,       # /html, /pdf, compare_ callback
    scheduling,    # /schedule, /viewschedule, /cancelschedule
    translation,   # /trans
)


def register(application: Application) -> None:
    """Register every handler module's commands/callbacks on `application`."""
    for module in _MODULES:
        module.register(application)
