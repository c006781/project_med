# tests/test_settings_page/test_settings_page_values.py
"""
Типы значений настроек на экране: сохранённое — нужных типов, негодные значения файла не роняют экран.
"""
import pytest

from app.config.config_manager.manager import AppConfigManager


def test_every_field_is_bound_once(page):
    """Настройка привязана к одному полю: таблицы не пересекаются."""
    tables = (
        page._text_fields,
        page._int_fields,
        page._flag_fields,
        page._level_fields,
        page._choice_fields,
    )
    keys = [key for table in tables for key, _widget in table]
    assert len(keys) == len(set(keys))


def test_saved_values_have_types_of_defaults(page):
    """После сохранения значения всех полей — того же типа, что умолчания программы."""
    page._load_settings()
    page._sawe_new_config()
    tables = (
        page._text_fields,
        page._int_fields,
        page._flag_fields,
        page._level_fields,
        page._choice_fields,
    )
    for table in tables:
        for key, _widget in table:
            default = AppConfigManager.default_of(key)
            assert type(page.config_manager[key]) is type(default), key


def test_saved_values_from_old_strings_become_typed(page):
    """Строки старого файла, дошедшие до экрана, при сохранении становятся нужных типов."""
    page.config_manager.update(
        {
            'BACKUP_COUNT'  : '7',
            'LOG_MAX_BYTES' : '2048',
            'use_timestamp' : 'on',
            'user_enabled'  : 'off',
        },
    )
    page._load_settings()
    page._sawe_new_config()
    assert page.config_manager['BACKUP_COUNT'] == 7
    assert page.config_manager['LOG_MAX_BYTES'] == 2048
    assert page.config_manager['use_timestamp'] is True
    assert page.config_manager['user_enabled'] is False


@pytest.mark.parametrize('key, spin, bad', [
    ('BACKUP_COUNT', 'backup_count_spin', 'много'),
    ('LOG_MAX_BYTES', 'log_max_bytes_spin', '10 МБ'),
    ('LOG_BACKUP_COUNT', 'log_backup_count_spin', None),
    ('UPDATE_BACKUP_KEEP_DAYS', 'update_keep_days_spin', ''),
])
def test_bad_number_shows_default(page, key, spin, bad):
    """Не число в настройках: экран открывается, в поле — умолчание; файл не меняется до сохранения."""
    page.config_manager[key] = bad
    page._load_settings()
    assert getattr(page, spin).value() == AppConfigManager.default_of(key)
    assert page.config_manager[key] == bad


@pytest.mark.parametrize('value, shown', [(10 ** 12, 100), (-5, 1), (0, 1), (7.9, 7), (True, 1)])
def test_number_is_clamped(page, value, shown):
    """Число вне границ поля (даже больше int Qt) приводится к границам."""
    page.config_manager['BACKUP_COUNT'] = value
    page._load_settings()
    assert page.backup_count_spin.value() == shown


@pytest.mark.parametrize('saved, shown', [('INFO', 'INFO'), ('debug', 'DEBUG'), (' Error ', 'ERROR'), ('???', 'DEBUG'), (None, 'DEBUG'), (5, 'DEBUG')])
def test_level_field(page, saved, shown):
    """Уровень журнала: регистр не важен; неизвестный — умолчание, а не прежнее значение поля."""
    page.user_level_combo.setCurrentText('CRITICAL')
    page.config_manager['user_LEVEL'] = saved
    page._load_settings()
    assert page.user_level_combo.currentText() == shown


@pytest.mark.parametrize('key, edit', [('PHOTOS_STORAGE_PATH', 'photos_path_edit'), ('YANDEX_TOKEN', 'token_edit')])
def test_text_not_string_does_not_break(page, key, edit):
    """Текстовая настройка другого типа показывается текстом; None — пусто."""
    page.config_manager[key] = 123
    page._load_settings()
    assert getattr(page, edit).text() == '123'
    page.config_manager[key] = None
    page._load_settings()
    assert getattr(page, edit).text() == ''


def test_text_saved_without_spaces(page):
    """Пробелы вокруг токена и путей (следствие вставки) не сохраняются."""
    page.token_edit.setText('  y0_токен\n')
    page.db_path_edit.setText(' ./другая.db ')
    page._sawe_new_config()
    assert page.config_manager['YANDEX_TOKEN'] == 'y0_токен'
    assert page.config_manager['database_local_path'] == './другая.db'


@pytest.mark.parametrize('typed', ['', '   '])
def test_empty_backup_path_becomes_default(page, typed):
    """Пустая папка копий: сохраняется и показывается умолчание."""
    page.backup_path_edit.setText(typed)
    page._sawe_new_config()
    expected = AppConfigManager.default_of('BACKUP_PATH')
    assert page.config_manager['BACKUP_PATH'] == expected
    assert page.backup_path_edit.text() == expected


def test_backup_fields_show_defaults(page):
    """Без файла настроек: поля копий базы показывают умолчания программы."""
    page._load_settings()
    assert page.backup_path_edit.text() == AppConfigManager.default_of('BACKUP_PATH')
    assert page.backup_count_spin.value() == AppConfigManager.default_of('BACKUP_COUNT')


def test_flag_fields_follow_rule(page):
    """Флажки экрана разбирают строки по единому правилу."""
    page.config_manager['user_file_enabled'] = 'on'
    page.config_manager['system_file_enabled'] = 'off'
    page._load_settings()
    assert page.user_file_check.isChecked()
    assert not page.system_file_check.isChecked()


def test_real_manager_round_trip(qapp, messages, tmp_path):
    """Настоящий менеджер: значения экрана сохраняются в файл и читаются теми же типами."""
    from unittest.mock import patch

    from interfaces.gui.gui_window.pages.settings_page import SettingsPage

    manager = AppConfigManager(str(tmp_path / 'настройки.msgpack'))
    with patch.object(AppConfigManager, 'get_instance', return_value=manager):
        page = SettingsPage()
        page.backup_count_spin.setValue(9)
        page.user_file_check.setChecked(True)
        page._sawe_new_config()
        manager.save()
        reread = AppConfigManager(str(tmp_path / 'настройки.msgpack'))
        assert reread.get('BACKUP_COUNT') == 9
        assert reread.get('user_file_enabled') is True
        page.deleteLater()
