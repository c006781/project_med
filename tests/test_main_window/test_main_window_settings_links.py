# tests/test_main_window/test_main_window_settings_links.py
"""
Настройки, которые доходят до работы только через окно и зависимости: правило перенесённой записи,
флаг значений запросов, резервируемая папка копий, папка инструкций.

Окно не строится; база и сеть не используются.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.dependencies as deps
from app.config.config_manager.manager import AppConfigManager, DRAFT_MOVED_RULE_KEY
from app.updater import UpdateError, validate_manifest_path
from app.utils.drafts import MovedRule
from interfaces.gui.gui_window import main_window as mw
from interfaces.gui.gui_window.dialogs import instructions_dialog as dialog_module


def _use_rule(monkeypatch, value) -> None:
    """Подменяет настройки окна значением правила."""
    monkeypatch.setattr(
        AppConfigManager,
        'get_instance',
        classmethod(lambda cls, *a, **k: {DRAFT_MOVED_RULE_KEY: value, 'PHOTOS_STORAGE_PATH': 'photos'}),
    )


@pytest.mark.parametrize('value, expected', [
    ('delete', MovedRule.DELETE),
    ('keep', MovedRule.KEEP),
    ('нечто', MovedRule.DELETE),
    (None, MovedRule.DELETE),
])
def test_rule_from_settings(monkeypatch, value, expected):
    """Значение настройки становится правилом; неизвестное — умолчание."""
    _use_rule(monkeypatch, value)
    host = SimpleNamespace()
    assert mw.MainWindow._moved_rule_from_settings(host) is expected


def test_init_drafts_passes_rule(monkeypatch):
    """Хранилище создаётся с правилом из настроек."""
    import app.draft.integration as integration
    import interfaces.gui.gui_window.drafts_qt as dq
    _use_rule(monkeypatch, 'keep')
    create = MagicMock()
    monkeypatch.setattr(integration, 'create_app_drafts', create)
    monkeypatch.setattr(dq, 'DraftsQtBridge', MagicMock())
    host = SimpleNamespace(
        logger                      =   MagicMock(),                                        # журнал
        _moved_rule_from_settings   =   lambda: mw.MainWindow._moved_rule_from_settings(None),  # правило
    )
    mw.MainWindow._init_drafts(host)
    create.assert_called_once_with(MovedRule.KEEP)


def _settings_host(store) -> SimpleNamespace:
    """Заменитель окна для on_settings_changed: только черновики и журнал."""
    return SimpleNamespace(
        logger                      =   MagicMock(),                                        # журнал
        drafts                      =   SimpleNamespace(store=store),                       # черновики
        _moved_rule_from_settings   =   lambda: mw.MainWindow._moved_rule_from_settings(None),  # правило
        _find_all_photo_widgets     =   lambda: [],                                         # виджетов нет
    )


def test_settings_change_updates_rule(monkeypatch):
    """Смена настройки (блок 'drafts') меняет правило хранилища."""
    _use_rule(monkeypatch, 'keep')
    store = SimpleNamespace(moved_rule=MovedRule.DELETE)
    mw.MainWindow.on_settings_changed(_settings_host(store), changed_blocks={'drafts'})
    assert store.moved_rule is MovedRule.KEEP


def test_other_blocks_do_not_touch_rule(monkeypatch):
    """Другой блок настроек правило не трогает."""
    _use_rule(monkeypatch, 'keep')
    store = SimpleNamespace(moved_rule=MovedRule.DELETE)
    mw.MainWindow.on_settings_changed(_settings_host(store), changed_blocks={'logging_common'})
    assert store.moved_rule is MovedRule.DELETE


def test_no_drafts_is_not_an_error(monkeypatch):
    """Черновики не создались: смена настройки не падает."""
    _use_rule(monkeypatch, 'keep')
    host = _settings_host(None)
    host.drafts = None
    mw.MainWindow.on_settings_changed(host, changed_blocks={'drafts'})


# ---- флаг значений запросов ----

@pytest.mark.parametrize('value, expected', [
    (True, True),
    (False, False),
    ('on', True),
    ('off', False),
    ('нечто', False),
])
def test_log_sql_params_rule(monkeypatch, value, expected):
    """Нераспознанная строка не включает запись личных данных в журнал."""
    monkeypatch.setattr(
        deps,
        'get_config_env',
        lambda: {'database_local_path': 'clinic.db', 'LOG_SQL_PARAMS': value},
    )
    assert deps._db_settings()[2] is expected


def test_log_sql_params_no_key(monkeypatch):
    """Нет ключа — значения скрыты."""
    monkeypatch.setattr(deps, 'get_config_env', lambda: {'database_local_path': 'clinic.db'})
    assert deps._db_settings()[2] is False


# ---- манифест обновления ----

@pytest.mark.parametrize('path', ['backups/clinic.txt', 'parsers/backups/a.py'])
def test_manifest_cannot_write_into_backups(path):
    """Манифест обновления не может писать в папку копий базы."""
    with pytest.raises(UpdateError):
        validate_manifest_path(path)


# ---- папка инструкций ----

def test_docs_folder_is_project_docs():
    """Папка docs — в корне проекта, от положения кода."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    assert dialog_module.docs_folder() == os.path.join(root, 'docs')
    assert os.path.isdir(dialog_module.docs_folder())


def test_docs_folder_does_not_depend_on_cwd(monkeypatch, tmp_path):
    """Текущая папка другая: путь тот же."""
    expected = dialog_module.docs_folder()
    monkeypatch.chdir(tmp_path)
    assert dialog_module.docs_folder() == expected


def test_docs_folder_frozen_next_to_executable(monkeypatch, tmp_path):
    """Собранная программа: рядом с исполняемым файлом."""
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'app.exe'))
    assert dialog_module.docs_folder() == str(tmp_path / 'docs')


def test_dialog_finds_docs_from_other_cwd(qapp, monkeypatch, tmp_path):
    """Диалог показывает инструкции и из другой текущей папки."""
    docs = tmp_path / 'docs' / 'раздел'
    docs.mkdir(parents=True)
    (docs / 'инструкция.pdf').write_bytes(b'%PDF')
    (tmp_path / 'docs' / 'заметка.txt').write_bytes(b'x')
    monkeypatch.setattr(dialog_module, 'docs_folder', lambda: str(tmp_path / 'docs'))
    monkeypatch.chdir(tmp_path.parent)
    dialog = dialog_module.InstructionsDialog()
    assert dialog.tree.topLevelItemCount() == 1
    folder = dialog.tree.topLevelItem(0)
    assert folder.text(0) == 'раздел'
    assert folder.child(0).text(0) == 'инструкция.pdf'
