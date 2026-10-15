# app/utils/drafts_qt/__init__.py

"""
Таблицы Qt (PySide6) поверх черновиков ``drafts`` — переносимый пакет.

Зависимости: PySide6 и пакет ``drafts`` (лежит рядом, в том же родительском пакете,
или установлен как пакет верхнего уровня ``drafts``). Код приложения не используется:
данные — через ``RowSource``, сохранение — через переданную функцию.

Пример:
    >>> from app.utils.drafts_qt import Column, DraftTableModel
    >>> model = DraftTableModel(store, 'patient', [Column('last_name', 'Фамилия')])
"""

from .model import DEFAULT_COLORS, Column, DraftTableModel, NodeRole, StatusRole
from .bridge import DraftsQtBridge
from .dialogs import ask_on_close, ask_save_target, describe_nodes, make_confirmations
from .page import DraftTablePage, RowSource

__all__ = ['DEFAULT_COLORS', 'Column', 'DraftTableModel', 'NodeRole', 'StatusRole',
           'DraftTablePage', 'RowSource', 'DraftsQtBridge', 'ask_on_close', 'ask_save_target',
           'describe_nodes', 'make_confirmations']
