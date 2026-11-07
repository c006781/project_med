# tests/test_main_window/conftest.py
"""
Общее для тестов главного окна: заменитель окна из настоящих миксинов, окна сообщений подменены.

Настоящее окно здесь не строится (оно пишет журналы, открывает базу, ставит таймеры): запуск
настоящего окна — только в подпроцессе, ``test_main_window_startup.py``. Сеть не используется.
"""
import os
from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox, QProgressBar, QWidget

from interfaces.gui.gui_window import main_window as mw


class WindowHost(QWidget, mw.SyncMixin, mw.UpdateMixin):
    """
    Заменитель окна: настоящий виджет и настоящие миксины Диска и обновлений.

    Порядок базовых классов тот же, что у ``MainWindow``. Методы окна, нужные миксинам, взяты у
    самого ``MainWindow``; черновиков и страниц нет, пока тест их не задаст.

    Attributes:
        logger       : (MagicMock) Журнал.
        progress_bar : (QProgressBar) Полоса прогресса.
    """

    _resolve_unsaved_before_exit = mw.MainWindow._resolve_unsaved_before_exit
    _old_pages_with_changes = mw.MainWindow._old_pages_with_changes
    _confirm_old_pages_loss = mw.MainWindow._confirm_old_pages_loss

    def __init__(self) -> None:
        super().__init__()
        self.logger = MagicMock()
        self.progress_bar = QProgressBar()
        self.update_progress_dialog = None


class Messages(list):
    """Записи окон сообщений: (вид, заголовок, текст); ``answer`` — ответ на вопрос."""

    answer = QMessageBox.StandardButton.Yes

    def texts(self, kind: str) -> List[Tuple[str, str]]:
        """Заголовки и тексты окон этого вида."""
        return [(title, text) for shown, title, text in self if shown == kind]


@pytest.fixture
def qapp() -> QApplication:
    """Приложение Qt на платформе offscreen."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def messages(monkeypatch) -> Messages:
    """Подменяет окна сообщений: они записываются, а не показываются."""
    log = Messages()

    def record(kind: str) -> Any:
        def show(parent, title, text, *args, **kwargs):
            log.append((kind, title, text))
            return log.answer if kind == 'question' else QMessageBox.StandardButton.Ok
        return staticmethod(show)

    for kind in ('question', 'warning', 'information', 'critical'):
        monkeypatch.setattr(QMessageBox, kind, record(kind))
    return log


@pytest.fixture
def host(qapp) -> WindowHost:
    """Заменитель окна; окно ожидания установки закрывается после теста."""
    window = WindowHost()
    yield window
    window._close_update_progress()
