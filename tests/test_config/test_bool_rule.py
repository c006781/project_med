# tests/test_config/test_bool_rule.py
"""
Одно правило строк-флагов на всю программу ('on' — истина, 'off' — ложь) и умолчания копий базы.

Сверяются все читатели настроек: журналы, менеджер настроек, экран настроек. Экран создаётся
только как класс (статический метод), окна нет; файлы настроек — временные.
"""
import os

import msgpack
import pytest

from app.config.config_manager.manager import AppConfigManager
from app.utils.logger.base_logger import BaseAppLogger
from app.utils.logger.bool_strings import FALSE_STRINGS, TRUE_STRINGS, parse_bool_string, to_bool

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


# значение флага у всех читателей настроек; менеджер — без нераспознанных строк
def _readers(
    text : str,  # строка из файла настроек
) -> dict:
    """Возвращает значение строки у каждого читателя настроек."""
    from interfaces.gui.gui_window.pages.settings_page import SettingsPage

    return {
        'журналы'   : BaseAppLogger._to_bool(text),
        'менеджер'  : AppConfigManager._coerce_value(text, False),
        'экран'     : SettingsPage._to_bool(text),
        'общая'     : to_bool(text),
    }


@pytest.mark.parametrize('text', [*TRUE_STRINGS, 'ON', 'On', ' on ', 'True', 'YES'])
def test_true_strings_same_everywhere(text):
    """Строки «да» — истина у всех читателей настроек."""
    assert set(_readers(text).values()) == {True}


@pytest.mark.parametrize('text', [*FALSE_STRINGS, 'OFF', 'Off', ' off ', 'False', 'NO', '   '])
def test_false_strings_same_everywhere(text):
    """Строки «нет», включая пустую, — ложь у всех читателей настроек."""
    assert set(_readers(text).values()) == {False}


@pytest.mark.parametrize('text', ['нечто', 'да', 'нет', 'enabled', '2'])
def test_unknown_string_policy_per_reader(text):
    """Нераспознанная строка: журналы и экран — ложь, менеджер — как есть (не теряет значение)."""
    readers = _readers(text)
    assert readers['журналы'] is False
    assert readers['экран'] is False
    assert readers['общая'] is False
    assert readers['менеджер'] == text
    assert parse_bool_string(text) is None


@pytest.mark.parametrize('value, expected', [(True, True), (False, False), (1, True), (0, False), (None, False)])
def test_non_strings(value, expected):
    """Не строки — обычный bool у журналов и экрана; менеджер их не трогает."""
    from interfaces.gui.gui_window.pages.settings_page import SettingsPage

    assert BaseAppLogger._to_bool(value) is expected
    assert SettingsPage._to_bool(value) is expected
    assert AppConfigManager._coerce_value(value, False) is value


def test_rule_has_no_overlap():
    """Одна строка не может значить и «да», и «нет»."""
    assert not set(TRUE_STRINGS) & set(FALSE_STRINGS)


def test_bool_module_imports_nothing_from_app():
    """Модуль правила ничего не импортирует из проекта (пакет журналов переносится копированием)."""
    import ast
    import app.utils.logger.bool_strings as module

    with open(module.__file__, encoding='utf-8') as source:
        tree = ast.parse(source.read())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or '')
    assert names == ['typing']


@pytest.mark.parametrize('flag, expected', [('on', True), ('OFF', False), ('yes', True), ('no', False)])
def test_logger_constructor_flags_follow_rule(make_flag_logger, flag, expected):
    """Строка-флаг в аргументе логгера — флаг, а не имя другого логгера."""
    logger = make_flag_logger(flag)
    assert logger._enable_file_logging is expected
    assert logger._enable_file_logging_ref is None


def test_logger_constructor_name_stays_reference(make_flag_logger):
    """Нераспознанная строка в аргументе логгера остаётся именем другого логгера."""
    logger = make_flag_logger('system')
    assert logger._enable_file_logging is True
    assert logger._enable_file_logging_ref == 'system'


@pytest.fixture
def make_flag_logger(tmp_path):
    """Создаёт логгер с заданной строкой ``enable_file_logging``; после теста закрывает его."""
    created = []

    def make(flag):
        logger = BaseAppLogger(
            name                =   f'flag_{len(created)}_{flag}',   # своё имя у каждого
            config              =   {                                # файл журнала — временный
                'LOG_LEVEL'         : 'INFO',
                'LOG_FILE'          : str(tmp_path / 'flag.log'),
                'LOG_MAX_BYTES'     : 1024,
                'LOG_BACKUP_COUNT'  : 1,
            },
            enable_file_logging =   flag,                            # проверяемая строка
        )
        created.append(logger)
        return logger

    yield make
    for logger in created:
        logger.close()


# --- файл настроек -----------------------------------------------------------------------

# файл настроек с заданными значениями
def _write_config(
    path   : str,   # куда записать
    values : dict,  # значения
) -> None:
    """Записывает файл настроек MessagePack."""
    with open(path, 'wb') as stream:
        msgpack.pack(
            values,     # значения
            stream,     # файл
        )


@pytest.mark.parametrize('saved, expected', [('on', True), ('off', False), ('', False)])
def test_manager_reads_flags_from_old_file(tmp_path, saved, expected):
    """Строки старого файла становятся флагами, в том числе 'off' у ключа, который по умолчанию False."""
    path = str(tmp_path / 'config.msgpack')
    _write_config(
        path,                                                       # файл
        {'LOG_SQL_PARAMS': saved, 'use_timestamp': saved},          # значения
    )
    manager = AppConfigManager(path)
    assert manager.get('LOG_SQL_PARAMS') is expected
    assert manager.get('use_timestamp') is expected


def test_backup_defaults(tmp_path):
    """Без файла: папка копий — в корне программы, число копий — целое."""
    manager = AppConfigManager(str(tmp_path / 'нет.msgpack'))
    assert manager.get('BACKUP_PATH') == os.path.join('.', 'backups')
    assert manager.get('BACKUP_COUNT') == 5 and type(manager.get('BACKUP_COUNT')) is int


@pytest.mark.parametrize('saved, expected', [('7', 7), (' 12 ', 12), (9, 9)])
def test_backup_count_type_is_coerced(tmp_path, saved, expected):
    """Число копий из старого файла переводится в целое."""
    path = str(tmp_path / 'config.msgpack')
    _write_config(
        path,                       # файл
        {'BACKUP_COUNT': saved},    # значения
    )
    value = AppConfigManager(path).get('BACKUP_COUNT')
    assert value == expected and type(value) is int


def test_backup_count_unparseable_kept(tmp_path):
    """Непереводимое число копий остаётся как есть, как у других чисел (читатель решает сам)."""
    path = str(tmp_path / 'config.msgpack')
    _write_config(
        path,                         # файл
        {'BACKUP_COUNT': 'много'},    # значения
    )
    assert AppConfigManager(path).get('BACKUP_COUNT') == 'много'


@pytest.mark.parametrize('saved', ['', '   '])
def test_empty_backup_path_from_old_file_means_default(tmp_path, saved):
    """Прежний экран сохранял пустую папку копий: такое значение — «не задано», берётся умолчание."""
    path = str(tmp_path / 'config.msgpack')
    _write_config(
        path,                       # файл
        {'BACKUP_PATH': saved},     # значения
    )
    assert AppConfigManager(path).get('BACKUP_PATH') == os.path.join('.', 'backups')


def test_saved_backup_path_kept(tmp_path):
    """Заданная папка копий не заменяется умолчанием."""
    path = str(tmp_path / 'config.msgpack')
    _write_config(
        path,                                # файл
        {'BACKUP_PATH': '/данные/копии'},    # значения
    )
    assert AppConfigManager(path).get('BACKUP_PATH') == '/данные/копии'


def test_empty_other_path_is_not_replaced(tmp_path):
    """Пустое значение других настроек остаётся пустым: правило только у перечисленных ключей."""
    path = str(tmp_path / 'config.msgpack')
    _write_config(
        path,                               # файл
        {'PHOTOS_STORAGE_PATH': ''},        # значения
    )
    assert AppConfigManager(path).get('PHOTOS_STORAGE_PATH') == ''


def test_default_of():
    """Умолчание ключа берётся без файла; нет умолчания — запасное значение."""
    assert AppConfigManager.default_of('BACKUP_COUNT') == 5
    assert AppConfigManager.default_of('НЕТ') is None
    assert AppConfigManager.default_of('НЕТ', fallback=7) == 7
