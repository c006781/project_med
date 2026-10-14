# tests/test_logger/test_base_modes.py

"""
Переключение режимов отдельного логгера во время работы:
enable/disable, консоль, файл, уровень, reconfigure, reload_from_config.
"""

import logging
import os

import pytest

from tests.test_logger.conftest import make_config, read


def _own_handlers(lg):
    """Обработчики логгера без глобальных."""
    return [h for h in lg.logger.handlers if h not in type(lg)._global_handlers]


def _kinds(lg):
    """Множество типов обработчиков: {'console', 'file'}."""
    kinds = []
    for h in _own_handlers(lg):
        if h is lg.file_handler:
            kinds.append('file')
        elif h is lg.console_handler:
            kinds.append('console')
        else:
            kinds.append(type(h).__name__)
    return sorted(kinds)


@pytest.fixture
def make_file_logger(make_logger):
    """Фабрика логгера с файлом и консолью.

    Логгер создаётся внутри теста, а не в фикстуре: StreamHandler запоминает
    sys.stderr при создании, а pytest подменяет поток между setup и call.
    """
    return lambda: make_logger(name='modes', enable_file_logging=True)


@pytest.fixture
def log_file(log_dir):
    return os.path.join(log_dir, 'app.log')


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------

def test_initial_handlers(make_file_logger):
    file_logger = make_file_logger()
    assert _kinds(file_logger) == ['console', 'file']


def test_disable_removes_all_handlers_and_silences(make_file_logger, log_file, capsys):
    file_logger = make_file_logger()
    file_logger.disable()
    assert file_logger.is_enabled() is False
    assert _kinds(file_logger) == []
    assert file_logger.file_handler is None
    file_logger.info('нет')
    assert capsys.readouterr().err == ''
    assert read(log_file) == ''


def test_enable_after_disable_restores_handlers(make_file_logger, log_file, capsys):
    file_logger = make_file_logger()
    file_logger.disable()
    file_logger.enable()
    assert _kinds(file_logger) == ['console', 'file']
    file_logger.info('снова')
    assert 'снова' in capsys.readouterr().err
    assert 'снова' in read(log_file)


def test_enable_disable_repeated_does_not_duplicate_handlers(make_file_logger, log_file):
    file_logger = make_file_logger()
    for _ in range(5):
        file_logger.disable()
        file_logger.enable()
    assert _kinds(file_logger) == ['console', 'file']
    file_logger.info('один раз')
    assert read(log_file).count('один раз') == 1


def test_enable_when_already_enabled_is_noop(make_file_logger):
    file_logger = make_file_logger()
    before = list(file_logger.logger.handlers)
    file_logger.enable()
    assert file_logger.logger.handlers == before


# ---------------------------------------------------------------------------
# Консоль
# ---------------------------------------------------------------------------

def test_disable_console_keeps_file(make_file_logger, log_file, capsys):
    file_logger = make_file_logger()
    file_logger.disable_console()
    assert _kinds(file_logger) == ['file']
    file_logger.info('только файл')
    assert capsys.readouterr().err == ''
    assert 'только файл' in read(log_file)


def test_enable_console_back(make_file_logger, capsys):
    file_logger = make_file_logger()
    file_logger.disable_console()
    file_logger.enable_console()
    file_logger.info('консоль')
    assert 'консоль' in capsys.readouterr().err
    assert _kinds(file_logger) == ['console', 'file']


def test_console_toggle_while_disabled_applies_after_enable(make_file_logger, capsys):
    file_logger = make_file_logger()
    file_logger.disable()
    file_logger.disable_console()
    file_logger.enable()
    file_logger.info('x')
    assert capsys.readouterr().err == ''
    assert _kinds(file_logger) == ['file']


# ---------------------------------------------------------------------------
# Файл
# ---------------------------------------------------------------------------

def test_disable_file_keeps_console(make_file_logger, log_file, capsys):
    file_logger = make_file_logger()
    file_logger.disable_file()
    assert file_logger.is_file_enabled() is False
    assert file_logger.file_handler is None
    assert _kinds(file_logger) == ['console']
    file_logger.info('только консоль')
    assert 'только консоль' in capsys.readouterr().err
    assert 'только консоль' not in read(log_file)


def test_enable_file_back(make_file_logger, log_file):
    file_logger = make_file_logger()
    file_logger.disable_file()
    file_logger.enable_file()
    assert file_logger.is_file_enabled() is True
    file_logger.info('снова в файл')
    assert 'снова в файл' in read(log_file)
    assert _kinds(file_logger) == ['console', 'file']


def test_enable_file_back_repeatedly(make_file_logger, log_file):
    """R2: раньше enable_file() после disable_file() молча ничего не делал."""
    file_logger = make_file_logger()
    for _ in range(3):
        file_logger.disable_file()
        assert file_logger.file_handler is None
        file_logger.enable_file()
        assert file_logger.file_handler is not None
    file_logger.info('после трёх циклов')
    assert read(log_file).count('после трёх циклов') == 1


def test_enable_file_back_via_reconfigure_works(make_file_logger, log_file):
    file_logger = make_file_logger()
    """Обходной путь: reconfigure(file_enabled=True) включает файл обратно."""
    file_logger.disable_file()
    file_logger.reconfigure(file_enabled=True)
    file_logger.info('через reconfigure')
    assert 'через reconfigure' in read(log_file)


def test_enable_file_on_logger_created_without_file(make_logger, log_dir):
    lg = make_logger()
    assert lg.file_handler is None
    lg.enable_file()
    lg.info('появился файл')
    assert 'появился файл' in read(os.path.join(log_dir, 'app.log'))


def test_enable_file_logging_property(make_file_logger, log_file):
    file_logger = make_file_logger()
    assert file_logger.enable_file_logging is True
    file_logger.enable_file_logging = False
    assert file_logger.enable_file_logging is False
    assert file_logger.file_handler is None
    file_logger.enable_file_logging = True
    assert file_logger.file_handler is not None


def test_enable_file_logging_property_non_bool_warns(make_file_logger):
    file_logger = make_file_logger()
    with pytest.warns(DeprecationWarning):
        file_logger.enable_file_logging = 0
    assert file_logger.is_file_enabled() is False


def test_use_name_in_filename_setter_switches_file(make_file_logger, log_dir):
    file_logger = make_file_logger()
    file_logger.use_name_in_filename = True
    file_logger.info('по имени')
    assert 'по имени' in read(os.path.join(log_dir, 'modes.log'))
    assert 'по имени' not in read(os.path.join(log_dir, 'app.log'))


# ---------------------------------------------------------------------------
# Уровни
# ---------------------------------------------------------------------------

def test_reconfigure_level(make_file_logger, log_file):
    file_logger = make_file_logger()
    file_logger.reconfigure(level='ERROR')
    assert file_logger.log_level == logging.ERROR
    assert file_logger.get_level() == 'ERROR'
    file_logger.warning('скрыто')
    file_logger.error('видно')
    content = read(log_file)
    assert 'скрыто' not in content and 'видно' in content
    assert all(h.level == logging.ERROR for h in _own_handlers(file_logger))


def test_setlevel_changes_python_logger_only(make_file_logger):
    file_logger = make_file_logger()
    """setLevel() меняет только logging.Logger; self.log_level и get_level() не меняются."""
    file_logger.setLevel(logging.ERROR)
    assert file_logger.logger.level == logging.ERROR
    assert file_logger.log_level == logging.DEBUG
    assert file_logger.get_level() == 'DEBUG'


def test_separate_console_and_file_levels(make_file_logger, log_file, capsys):
    file_logger = make_file_logger()
    file_logger.set_console_level('ERROR')
    file_logger.set_file_level('INFO')
    file_logger.debug('d')
    file_logger.info('i')
    file_logger.error('e')
    err = capsys.readouterr().err
    content = read(log_file)
    assert '\tERROR\t' in err and '\tINFO\t' not in err
    assert '\tINFO\t' in content and '\tDEBUG\t' not in content


@pytest.mark.xfail(strict=True, reason=(
    "BUG: reconfigure(console_level=...) ставит уровень, затем _update_flags "
    "возвращает True и _update_handlers() пересоздаёт консоль с общим уровнем"
))
def test_reconfigure_console_level_via_flags(make_file_logger, capsys):
    file_logger = make_file_logger()
    file_logger.reconfigure(console_level='CRITICAL')
    file_logger.error('нет в консоли')
    assert capsys.readouterr().err == ''


def test_separate_levels_are_lost_after_rebuild(make_file_logger, capsys):
    file_logger = make_file_logger()
    """Отдельный уровень консоли сбрасывается при любом перестроении обработчиков."""
    file_logger.set_console_level('CRITICAL')
    file_logger.disable_file()  # перестроение
    file_logger.info('снова видно')
    assert 'снова видно' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# reconfigure: флаги и параметры файла
# ---------------------------------------------------------------------------

def test_reconfigure_flags(make_file_logger, capsys, log_file):
    file_logger = make_file_logger()
    file_logger.reconfigure(console_enabled=False)
    assert _kinds(file_logger) == ['file']
    file_logger.reconfigure(file_enabled='False', console_enabled='True')
    assert _kinds(file_logger) == ['console']
    file_logger.reconfigure(enabled=False)
    assert _kinds(file_logger) == []
    file_logger.reconfigure(enabled=True, file_enabled=True)
    assert _kinds(file_logger) == ['console', 'file']


def test_reconfigure_enable_file_logging_alias(make_file_logger):
    file_logger = make_file_logger()
    file_logger.reconfigure(enable_file_logging=False)
    assert file_logger.file_handler is None


def test_reconfigure_moves_file(make_file_logger, tmp_path, log_file):
    file_logger = make_file_logger()
    new_dir = tmp_path / 'moved'
    file_logger.reconfigure(base_log_FILE=str(new_dir) + os.sep)
    file_logger.info('в новом месте')
    assert 'в новом месте' in read(new_dir / 'app.log')
    assert 'в новом месте' not in read(log_file)


def test_reconfigure_rotation_params(make_file_logger):
    file_logger = make_file_logger()
    file_logger.reconfigure(log_MAX_BYTES='1234', log_BACKUP_COUNT=3)
    assert file_logger.log_max_bytes == 1234
    assert file_logger.file_handler.maxBytes == 1234
    assert file_logger.file_handler.backupCount == 3


def test_reconfigure_use_timestamp(make_file_logger, log_dir):
    file_logger = make_file_logger()
    file_logger.reconfigure(use_timestamp='True')
    file_logger.info('ts')
    expected = os.path.join(log_dir, f'app_{file_logger._start_timestamp}.log')
    assert 'ts' in read(expected)


def test_reconfigure_args_and_depth_flags(make_file_logger):
    file_logger = make_file_logger()
    file_logger.reconfigure(log_ARGS=True, show_call_depth='True')
    assert file_logger.log_args is True
    assert file_logger._show_call_depth is True


def test_reconfigure_unknown_keys_ignored(make_file_logger):
    file_logger = make_file_logger()
    file_logger.reconfigure(something_else=1)
    assert _kinds(file_logger) == ['console', 'file']


# ---------------------------------------------------------------------------
# reload_from_config / apply_config_from_dict
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('method', ['reload_from_config', 'apply_config_from_dict'])
def test_reload_changes_level(make_file_logger, log_dir, method):
    file_logger = make_file_logger()
    getattr(file_logger, method)(make_config(log_dir, LOG_LEVEL='ERROR', file_enabled='True'))
    assert file_logger.log_level == logging.ERROR
    assert all(h.level == logging.ERROR for h in _own_handlers(file_logger))


@pytest.mark.parametrize('method', ['reload_from_config', 'apply_config_from_dict'])
def test_reload_changes_flags(make_file_logger, log_dir, method, capsys, log_file):
    file_logger = make_file_logger()
    getattr(file_logger, method)(
        make_config(log_dir, console_enabled='False', file_enabled='True'))
    file_logger.info('файл')
    assert capsys.readouterr().err == ''
    assert 'файл' in read(log_file)

    getattr(file_logger, method)(
        make_config(log_dir, console_enabled='True', file_enabled='False'))
    assert _kinds(file_logger) == ['console']


def test_reload_without_file_enabled_key_keeps_init_param(make_file_logger, log_dir):
    file_logger = make_file_logger()
    """file_enabled отсутствует в конфиге → берётся аргумент конструктора (enable_file_logging)."""
    file_logger.reload_from_config(make_config(log_dir))
    assert file_logger.is_file_enabled() is True


def test_reload_name_specific_keys(make_file_logger, log_dir):
    file_logger = make_file_logger()
    file_logger.reload_from_config(
        make_config(log_dir, LOG_LEVEL='DEBUG', modes_LEVEL='CRITICAL', file_enabled='True'))
    assert file_logger.log_level == logging.CRITICAL


def test_reload_disable_then_enable(make_file_logger, log_dir, log_file):
    file_logger = make_file_logger()
    file_logger.reload_from_config(make_config(log_dir, enabled='False', file_enabled='True'))
    assert _kinds(file_logger) == []
    file_logger.reload_from_config(make_config(log_dir, enabled='True', file_enabled='True'))
    file_logger.info('вернулся')
    assert 'вернулся' in read(log_file)


def test_reload_moves_file(make_file_logger, tmp_path):
    file_logger = make_file_logger()
    new_dir = tmp_path / 'other'
    file_logger.reload_from_config(
        make_config(str(new_dir), file_enabled='True'))
    file_logger.info('перенос')
    assert 'перенос' in read(new_dir / 'app.log')


# ---------------------------------------------------------------------------
# Форматтер
# ---------------------------------------------------------------------------

def test_set_formatter_applies_to_all_handlers(make_file_logger, log_file):
    file_logger = make_file_logger()
    fmt = logging.Formatter('CUSTOM %(message)s')
    file_logger.set_formatter(fmt)
    assert all(h.formatter is fmt for h in _own_handlers(file_logger))
    file_logger.info('x')
    assert read(log_file).startswith('CUSTOM ')


def test_custom_formatter_lost_after_rebuild(make_file_logger, log_file):
    file_logger = make_file_logger()
    """set_formatter сохраняется в self.formatter и переживает перестроение."""
    fmt = logging.Formatter('CUSTOM %(message)s')
    file_logger.set_formatter(fmt)
    file_logger.disable()
    file_logger.enable()
    assert file_logger.console_handler.formatter is fmt
    assert file_logger.file_handler.formatter is fmt
