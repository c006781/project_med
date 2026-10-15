# interfaces/gui/gui_window/drafts_qt.py

"""
Переходник (совместимость): мост сигналов и диалоги черновиков перенесены в переносимый
пакет ``app/utils/drafts_qt`` (``bridge.py``, ``dialogs.py``) 2026-10-16 — в них нет
ничего от приложения. Старые импорты из этого модуля продолжают работать.

Пример:
    >>> from interfaces.gui.gui_window.drafts_qt import DraftsQtBridge, make_confirmations
"""

from app.utils.drafts_qt.bridge import DraftsQtBridge  # noqa: F401
from app.utils.drafts_qt.dialogs import (  # noqa: F401
    ask_on_close, ask_save_target, describe_nodes, make_confirmations,
)

__all__ = ['DraftsQtBridge', 'ask_on_close', 'ask_save_target', 'describe_nodes',
           'make_confirmations']
