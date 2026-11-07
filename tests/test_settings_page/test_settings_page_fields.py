# tests/test_settings_page/test_settings_page_fields.py
"""
Новые поля экрана настроек: папка документов Word, значения запросов в журнал, правило перенесённой записи.
"""
from unittest.mock import MagicMock

import pytest

from app.config.config_applier import ConfigApplier, ServiceHooks
from app.config.config_manager import (
    DRAFT_MOVED_RULE_KEY,
    DRAFT_MOVED_RULE_VALUES,
    WORD_DOCUMENTS_PATH_KEY,
    draft_moved_rule_value,
)
from app.config.config_manager.manager import AppConfigManager
from app.utils.drafts._model import MovedRule
from interfaces.gui.gui_window.pages import settings_page as sp


def test_word_folder_loaded_and_saved(page):
    """Поле показывает настройку, сохраняет без пробелов по краям."""
    page.config_manager[WORD_DOCUMENTS_PATH_KEY] = '/документы/word'
    page._load_settings()
    assert page.word_path_edit.text() == '/документы/word'
    page.word_path_edit.setText(' /другая папка ')
    page._sawe_new_config()
    assert page.config_manager[WORD_DOCUMENTS_PATH_KEY] == '/другая папка'


def test_word_folder_empty_stays_empty(page):
    """Пусто — допустимое значение: импорт спросит папку."""
    page._load_settings()
    assert page.word_path_edit.text() == ''
    page._sawe_new_config()
    assert page.config_manager[WORD_DOCUMENTS_PATH_KEY] == ''


def test_word_folder_browse(page, monkeypatch):
    """Кнопка «Обзор» записывает выбранную папку; отмена поле не меняет."""
    monkeypatch.setattr(sp.QFileDialog, 'getExistingDirectory', staticmethod(lambda *args: '/выбрана'))
    page.word_path_btn.click()
    assert page.word_path_edit.text() == '/выбрана'
    monkeypatch.setattr(sp.QFileDialog, 'getExistingDirectory', staticmethod(lambda *args: ''))
    page.word_path_btn.click()
    assert page.word_path_edit.text() == '/выбрана'


def test_sql_params_off_by_default_with_warning(page):
    """По умолчанию выключено; рядом пояснение про личные данные."""
    page._load_settings()
    assert not page.log_sql_params_check.isChecked()
    assert 'личные данные' in page.log_sql_params_hint.text()


def test_sql_params_saved_as_bool(page):
    """Переключатель сохраняет настоящий bool."""
    page._load_settings()
    page.log_sql_params_check.setChecked(True)
    page._sawe_new_config()
    assert page.config_manager['LOG_SQL_PARAMS'] is True


@pytest.mark.parametrize('saved, shown', [('on', True), ('off', False), ('нечто', False), (True, True)])
def test_sql_params_load_follows_rule(page, saved, shown):
    """Флажок читает строки по единому правилу; нераспознанная — выключено (личные данные скрыты)."""
    page.config_manager['LOG_SQL_PARAMS'] = saved
    page._load_settings()
    assert page.log_sql_params_check.isChecked() is shown


def test_sql_params_change_reopens_database(page):
    """Смена переключателя — блок базы: применитель переоткрывает базу и перезагружает сервисы."""
    page._load_settings()
    old = dict(page.config_manager)
    page.log_sql_params_check.setChecked(True)
    page._sawe_new_config()
    new = dict(page.config_manager)
    assert 'database' in ConfigApplier.get_changed_blocks(old, new)

    service = MagicMock()
    reopen = MagicMock()
    applier = ConfigApplier(
        services = ServiceHooks(
            service_providers   =   lambda: [lambda: service],  # один сервис
            photo_service       =   MagicMock(),                # не нужен
            sync_service        =   MagicMock(),                # не нужен
            reopen_database     =   reopen,                     # общая база
        ),
    )
    blocks = applier.apply_changes(old, new)
    assert 'database' in blocks
    reopen.assert_called_once()
    service.reload_config.assert_called_once()
    assert applier.errors == {}


def test_moved_rule_default_delete(page):
    """По умолчанию правило delete: так решил владелец."""
    page._load_settings()
    assert AppConfigManager.default_of(DRAFT_MOVED_RULE_KEY) == 'delete'
    assert page.draft_moved_rule_combo.currentData() == 'delete'
    assert page.draft_moved_rule_hint.text()


def test_moved_rule_saved(page):
    """Выбранное правило сохраняется строкой."""
    page.draft_moved_rule_combo.setCurrentIndex(
        page.draft_moved_rule_combo.findData('keep'),
    )
    page._sawe_new_config()
    assert page.config_manager[DRAFT_MOVED_RULE_KEY] == 'keep'


def test_moved_rule_unknown_value_shows_default(page):
    """Неизвестное значение файла: показывается delete."""
    page.draft_moved_rule_combo.setCurrentIndex(1)
    page.config_manager[DRAFT_MOVED_RULE_KEY] = 'нечто'
    page._load_settings()
    assert page.draft_moved_rule_combo.currentData() == 'delete'


def test_moved_rule_values_match_enum():
    """Значения настройки — ровно значения правила черновиков (настройки от них не зависят, сверяет тест)."""
    assert set(DRAFT_MOVED_RULE_VALUES) == {rule.value for rule in MovedRule}


@pytest.mark.parametrize('value, expected', [
    ('delete', 'delete'), ('keep', 'keep'), ('нечто', 'delete'), (None, 'delete'), ('', 'delete'),
])
def test_draft_moved_rule_value(value, expected):
    """Значение для черновиков всегда допустимо: ``MovedRule(...)`` не упадёт при запуске окна."""
    assert draft_moved_rule_value(value) == expected
    assert MovedRule(draft_moved_rule_value(value)).value == expected


def test_moved_rule_change_reported_to_window(page):
    """Смена правила — отдельный блок: окно узнает о ней; прочие блоки не затронуты."""
    page._load_settings()
    old = dict(page.config_manager)
    page.draft_moved_rule_combo.setCurrentIndex(
        page.draft_moved_rule_combo.findData('keep'),
    )
    page._sawe_new_config()
    new = dict(page.config_manager)
    assert ConfigApplier.get_changed_blocks(old, new) == {'drafts'}
    applier = ConfigApplier()
    assert applier.apply_changes(old, new) == {'drafts'}
    assert applier.errors == {}


def test_save_without_changes_changes_no_block(page):
    """Сохранение без правок: блоков нет, база не переоткрывается."""
    page._load_settings()
    old = dict(page.config_manager)
    page._sawe_new_config()
    assert ConfigApplier.get_changed_blocks(old, dict(page.config_manager)) == set()
