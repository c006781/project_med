# tests/test_settings_page/conftest.py
"""
Общее для тестов экрана настроек: страница без главного окна, настройки в памяти, окна сообщений подменены.

Настоящее окно и настоящие файлы настроек не используются; сеть — только через подмену клиента в тестах.
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config.config_manager.manager import AppConfigManager
from interfaces.gui.gui_window.pages import settings_page as sp
from interfaces.gui.gui_window.pages.settings_page import SettingsPage


class FakeConfig(dict):
    """Настройки в памяти: тот же get / set, что нужен экрану; значения — из умолчаний программы."""

    def __init__(self) -> None:
        super().__init__(AppConfigManager._defaults)

    def set(self, key, value):
        self[key] = value


@pytest.fixture
def qapp():
    """Приложение Qt на платформе offscreen."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def messages(monkeypatch):
    """Подменяет окна сообщений: список (вид, заголовок, текст); вопрос отвечает значением ``answer``."""
    class Recorder(list):
        answer = QMessageBox.StandardButton.Yes

    log = Recorder()

    def record(kind):
        def show(parent, title, text, *args, **kwargs):
            log.append((kind, title, text))
            return log.answer if kind == 'question' else QMessageBox.StandardButton.Ok
        return staticmethod(show)

    for kind in ('information', 'warning', 'critical', 'question'):
        monkeypatch.setattr(sp.QMessageBox, kind, record(kind))
    return log


@pytest.fixture
def page(qapp, messages):
    """Страница настроек на настройках в памяти, без главного окна."""
    config = FakeConfig()
    with patch.object(AppConfigManager, 'get_instance', return_value=config):
        widget = SettingsPage()
        widget.config_manager = config
        yield widget
    widget.wait_check_threads()
    widget.deleteLater()
