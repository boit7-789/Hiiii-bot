from __future__ import annotations

from telegram.ext import Application

from . import (
    ai_doubt,
    ai_quiz,
    mix,
    pdf_quiz,
    poll_quiz,
    quiz_play,
    reports,
    scheduling,
    setup_wizard,
    translation,
)

_MODULES = (
    quiz_play,
    setup_wizard,
    poll_quiz,
    mix,
    ai_quiz,
    pdf_quiz,
    reports,
    scheduling,
    translation,
    ai_doubt,
)


def register(application: Application) -> None:
    for module in _MODULES:
        module.register(application)
