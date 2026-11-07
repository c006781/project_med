# tests/test_linux_gui/test_linux_gui_update_keep.py
"""
Экран настроек: как хранить старые копии кода при автообновлении Linux (app/updater.py).

Страница создаётся на платформе offscreen; настройки — временный менеджер, файл настроек не пишется.
"""
import os
from unittest.mock import patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from app.config.config_manager.manager import AppConfigManager
from interfaces.gui.gui_window.pages.settings_page import SettingsPage


class _FakeConfig(dict):
    """Настройки в памяти: тот же get / set, что нужен экрану, значения — из умолчаний программы."""

    def __init__(self) -> None:
        super().__init__(AppConfigManager._defaults)

    def set(self, key, value):
        self[key] = value


@pytest.fixture
def page():
    QApplication.instance() or QApplication([])
    config = _FakeConfig()
    with patch.object(AppConfigManager, 'get_instance', return_value=config):
        widget = SettingsPage()
        widget.config_manager = config
        yield widget
    widget.deleteLater()


def test_default_is_by_count_three(page):
    """Решение владельца: сейчас по количеству, 3 копии; поле дней выключено."""
    page._load_settings()
    assert page.update_keep_mode_combo.currentData() == 'count'
    assert page.update_keep_count_spin.value() == 3
    assert page.update_keep_count_spin.isEnabled()
    assert not page.update_keep_days_spin.isEnabled()


def test_mode_switch_enables_matching_field(page):
    """Способ «по времени» включает поле дней и выключает поле количества."""
    page._load_settings()
    page.update_keep_mode_combo.setCurrentIndex(
        page.update_keep_mode_combo.findData('days'),
    )
    assert page.update_keep_days_spin.isEnabled()
    assert not page.update_keep_count_spin.isEnabled()


def test_load_shows_saved_days(page):
    """Сохранённый способ и значения показываются при открытии экрана."""
    page.config_manager['UPDATE_BACKUP_KEEP_MODE'] = 'days'
    page.config_manager['UPDATE_BACKUP_KEEP_DAYS'] = 7
    page._load_settings()
    assert page.update_keep_mode_combo.currentData() == 'days'
    assert page.update_keep_days_spin.value() == 7


def test_unknown_saved_mode_falls_back_to_first(page):
    """Неизвестный способ в настройках не ломает экран: показывается «по количеству»."""
    page.config_manager['UPDATE_BACKUP_KEEP_MODE'] = 'что-то'
    page._load_settings()
    assert page.update_keep_mode_combo.currentData() == 'count'


def test_save_writes_selected_values(page):
    """Сохранение пишет выбранный способ и оба значения."""
    page._load_settings()
    page.update_keep_mode_combo.setCurrentIndex(
        page.update_keep_mode_combo.findData('days'),
    )
    page.update_keep_days_spin.setValue(14)
    page.update_keep_count_spin.setValue(5)
    page._sawe_new_config()
    assert page.config_manager['UPDATE_BACKUP_KEEP_MODE'] == 'days'
    assert page.config_manager['UPDATE_BACKUP_KEEP_DAYS'] == 14
    assert page.config_manager['UPDATE_BACKUP_KEEP_COUNT'] == 5
