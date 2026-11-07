# tests/test_main_window/test_main_window_update_check.py
"""
Проверка обновлений при запуске окна: настройка, переменная для проверочных запусков, тишина.

Сеть не используется: ``is_github_reachable`` и ``check_for_updates`` подменены. Окно не строится:
методы вызываются на заменителе.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

import app.updater
from app.config.config_manager.manager import AppConfigManager, UPDATE_CHECK_ON_START_KEY
from interfaces.gui.gui_window import main_window as mw


# заменитель окна: только то, что читают методы проверки
def _host() -> SimpleNamespace:
    """
    Создаёт заменитель окна с подменённым модулем обновлений и журналом.

    Returns:
        (SimpleNamespace) Заменитель окна.

    Example:
        >>> _host().updater.check_for_updates.called
        False
    """
    return SimpleNamespace(
        logger  =   MagicMock(),    # журнал
        updater =   MagicMock(),    # модуль обновлений
    )


@pytest.fixture
def forbid_reachable(monkeypatch):
    """Падает при любом обращении к проверке доступности GitHub."""
    def fail(*args, **kwargs):
        raise AssertionError('is_github_reachable вызван')
    monkeypatch.setattr(app.updater, 'is_github_reachable', fail)
    monkeypatch.setattr(app.updater.urllib.request, 'urlopen', fail)


def _use_config(monkeypatch, values: dict) -> None:
    """Подменяет настройки окна словарём."""
    monkeypatch.setattr(AppConfigManager, 'get_instance', classmethod(lambda cls, *a, **k: values))
    monkeypatch.delenv(mw.NO_UPDATE_CHECK_ENV, raising=False)


def test_default_is_on():
    """Умолчание менеджера: проверять, как раньше."""
    assert AppConfigManager.default_of(UPDATE_CHECK_ON_START_KEY) is True


def test_setting_off_means_no_network(monkeypatch, forbid_reachable):
    """Настройка выключена — нет ни is_github_reachable, ни check_for_updates."""
    _use_config(monkeypatch, {UPDATE_CHECK_ON_START_KEY: False})
    host = _host()
    mw.MainWindow._delayed_check_updates(host)
    host.updater.check_for_updates.assert_not_called()


def test_env_turns_off_whatever_setting(monkeypatch, forbid_reachable):
    """Переменная проверочного запуска главнее включённой настройки."""
    _use_config(monkeypatch, {UPDATE_CHECK_ON_START_KEY: True})
    monkeypatch.setenv(mw.NO_UPDATE_CHECK_ENV, '1')
    host = _host()
    mw.MainWindow._delayed_check_updates(host)
    host.updater.check_for_updates.assert_not_called()


def test_setting_on_checks_without_reachable_in_window_thread(monkeypatch, forbid_reachable):
    """Настройка включена: проверка идёт через поток модуля, окно не обращается к GitHub само."""
    _use_config(monkeypatch, {UPDATE_CHECK_ON_START_KEY: True})
    host = _host()
    mw.MainWindow._delayed_check_updates(host)
    host.updater.check_for_updates.assert_called_once_with()
    assert host._auto_check is True


def test_updater_missing_is_not_an_error(monkeypatch):
    """Модуль обновлений не создался: проверка молча пропускается."""
    _use_config(monkeypatch, {UPDATE_CHECK_ON_START_KEY: True})
    host = SimpleNamespace(logger=MagicMock())
    mw.MainWindow._delayed_check_updates(host)
    assert not hasattr(host, '_auto_check')


@pytest.mark.parametrize('value, expected', [
    (True, True),
    (False, False),
    ('on', True),
    ('off', False),
    ('нечто', False),
])
def test_setting_values(value, expected):
    """Строки из старого файла — общим правилом; незнакомая строка выключает сеть."""
    assert mw.startup_update_check_enabled(
        {UPDATE_CHECK_ON_START_KEY: value},
        environ =   {},
    ) is expected


def test_no_key_keeps_checking():
    """Нет ключа — проверять."""
    assert mw.startup_update_check_enabled({}, environ={}) is True


def test_env_falsy_value_does_not_turn_off():
    """Значение '0' переменной проверку не выключает."""
    assert mw.startup_update_check_enabled(
        {UPDATE_CHECK_ON_START_KEY: True},
        environ =   {mw.NO_UPDATE_CHECK_ENV: '0'},
    ) is True


def test_auto_check_error_is_silent(monkeypatch):
    """Ошибка автоматической проверки — только журнал, флаг сброшен."""
    warning = MagicMock()
    monkeypatch.setattr(QMessageBox, 'warning', warning)
    host = _host()
    host._auto_check = True
    mw.MainWindow._on_update_error(host, 'нет связи')
    warning.assert_not_called()
    assert host._auto_check is False
    assert 'нет связи' in host.logger.info.call_args.args[0]


def test_manual_check_error_is_shown(monkeypatch):
    """Ошибка ручной проверки показывается."""
    warning = MagicMock()
    monkeypatch.setattr(QMessageBox, 'warning', warning)
    host = _host()
    host._auto_check = False
    mw.MainWindow._on_update_error(host, 'нет связи')
    assert 'нет связи' in warning.call_args.args[2]
