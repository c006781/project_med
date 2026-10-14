# tests/test_logger/test_base_output.py

"""
Куда и в каком виде пишет логгер: разрешение пути к файлу, формат строки,
указатель на место вызова, фильтрация по уровню, методы debug..exception.
"""

import inspect
import logging
import os
import re

import pytest

from tests.test_logger.conftest import make_config, read


# ---------------------------------------------------------------------------
# Разрешение пути файла (_get_log_file / _build_log_file_in_dir)
# ---------------------------------------------------------------------------

def _path_for(make_logger, base, **kwargs):
    config = make_config('unused', LOG_FILE=base)
    return make_logger(config=config, **kwargs)._get_log_file()


def test_path_existing_dir_without_separator(make_logger, log_dir):
    assert _path_for(make_logger, log_dir) == os.path.join(log_dir, 'app.log')


def test_path_dir_with_trailing_separator(make_logger, tmp_path):
    base = str(tmp_path / 'not_yet') + os.sep
    assert _path_for(make_logger, base) == os.path.join(str(tmp_path / 'not_yet'), 'app.log')


def test_path_nonexistent_with_log_extension_is_file(make_logger, tmp_path):
    base = str(tmp_path / 'sub' / 'custom.log')
    assert _path_for(make_logger, base) == base


def test_path_nonexistent_without_extension_is_dir(make_logger, tmp_path):
    base = str(tmp_path / 'some_dir')
    assert _path_for(make_logger, base) == os.path.join(base, 'app.log')


def test_path_existing_file_used_as_is(make_logger, tmp_path):
    existing = tmp_path / 'already.txt'
    existing.write_text('')
    assert _path_for(make_logger, str(existing)) == str(existing)


def test_path_use_name_in_filename(make_logger, log_dir):
    assert _path_for(make_logger, log_dir, name='svc', use_name_in_filename=True) == \
        os.path.join(log_dir, 'svc.log')


def test_path_use_timestamp_without_name(make_logger, log_dir):
    lg = make_logger(config=make_config(log_dir, use_timestamp='True'))
    expected = os.path.join(log_dir, f'app_{lg._start_timestamp}.log')
    assert lg._get_log_file() == expected
    assert re.fullmatch(r'\d{8}_\d{6}', lg._start_timestamp)


def test_path_use_timestamp_with_name(make_logger, log_dir):
    lg = make_logger(name='svc2', config=make_config(log_dir, use_timestamp='True'),
                     use_name_in_filename=True)
    assert lg._get_log_file() == os.path.join(log_dir, f'svc2_{lg._start_timestamp}.log')


def test_path_empty_base_raises(make_logger, log_dir):
    lg = make_logger()
    lg.base_log_file = ''
    with pytest.raises(ValueError, match='base_log_file'):
        lg._get_log_file()


def test_file_handler_creates_missing_directory(make_logger, tmp_path):
    target = tmp_path / 'deep' / 'er'
    lg = make_logger(config=make_config(str(target)), enable_file_logging=True)
    lg.info('hello')
    assert 'hello' in read(target / 'app.log')


# ---------------------------------------------------------------------------
# Формат строки
# ---------------------------------------------------------------------------

LINE_RE = re.compile(
    r'^(?P<time>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})\t'
    r'(?P<level>[A-Z]+)\t'
    r'\[(?P<name>[^\]]+)\]\t'
    r'(?P<indent>>*) '
    r'File "(?P<file>[^"]+)", line (?P<line>\d+), in <(?P<func>[^>]+)>:\t'
    r'(?P<msg>.*)$'
)


def test_file_line_format_and_caller_info(make_logger, log_dir):
    lg = make_logger(name='fmt', enable_file_logging=True)
    lineno = inspect.currentframe().f_lineno + 1
    lg.info('сообщение')
    content = read(os.path.join(log_dir, 'app.log')).splitlines()
    assert len(content) == 1
    m = LINE_RE.match(content[0])
    assert m, content[0]
    assert m['level'] == 'INFO'
    assert m['name'] == 'fmt'
    assert m['indent'] == ''
    assert os.path.normcase(m['file']) == os.path.normcase(__file__)
    assert int(m['line']) == lineno
    assert m['func'] == 'test_file_line_format_and_caller_info'
    assert m['msg'] == 'сообщение'


def test_console_output_goes_to_stderr(make_logger, capsys):
    lg = make_logger(name='cons')
    lg.warning('в консоль')
    captured = capsys.readouterr()
    assert captured.out == ''
    assert LINE_RE.match(captured.err.strip())
    assert 'в консоль' in captured.err


def test_caller_info_from_nested_function(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)

    def inner():
        lg.debug('внутри')

    inner()
    m = LINE_RE.match(read(os.path.join(log_dir, 'app.log')).strip())
    assert m['func'] == 'inner'


def test_utf8_file_encoding(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)
    lg.info('кириллица ✓')
    with open(os.path.join(log_dir, 'app.log'), 'rb') as f:
        assert 'кириллица ✓'.encode('utf-8') in f.read()


# ---------------------------------------------------------------------------
# Уровни
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('method, level', [
    ('debug', 'DEBUG'), ('info', 'INFO'), ('warning', 'WARNING'),
    ('error', 'ERROR'), ('critical', 'CRITICAL'),
])
def test_each_method_writes_with_its_level(make_logger, log_dir, method, level):
    lg = make_logger(enable_file_logging=True)
    getattr(lg, method)('x')
    m = LINE_RE.match(read(os.path.join(log_dir, 'app.log')).strip())
    assert m['level'] == level


def test_level_filtering(make_logger, log_dir):
    lg = make_logger(config=make_config(log_dir, LOG_LEVEL='WARNING'), enable_file_logging=True)
    lg.debug('d')
    lg.info('i')
    lg.warning('w')
    lg.error('e')
    levels = [LINE_RE.match(line)['level']
              for line in read(os.path.join(log_dir, 'app.log')).splitlines()]
    assert levels == ['WARNING', 'ERROR']


def test_exception_logs_traceback_and_returns_message(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)
    try:
        raise RuntimeError('бум')
    except RuntimeError:
        ret = lg.exception('упало')
    assert ret == 'упало'
    content = read(os.path.join(log_dir, 'app.log'))
    assert '\tERROR\t' in content
    assert 'Traceback' in content
    assert 'RuntimeError: бум' in content


def test_exception_without_exc_info(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)
    try:
        raise RuntimeError('бум')
    except RuntimeError:
        lg.exception('без трейса', exc_info=False)
    assert 'Traceback' not in read(os.path.join(log_dir, 'app.log'))


# ---------------------------------------------------------------------------
# Отключение
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('method', ['debug', 'info', 'warning', 'error', 'critical', 'exception'])
def test_disabled_logger_writes_nothing(make_logger, log_dir, capsys, method):
    lg = make_logger(config=make_config(log_dir, enabled='False'), enable_file_logging=True)
    getattr(lg, method)('тишина')
    assert capsys.readouterr().err == ''
    assert read(os.path.join(log_dir, 'app.log')) == ''


def test_disabled_logger_has_no_handlers(make_logger, log_dir):
    """У выключенного логгера остаётся только постоянный NullHandler (R6)."""
    lg = make_logger(config=make_config(log_dir, enabled='False'), enable_file_logging=True)
    assert lg.logger.handlers == [lg._null_handler]
    assert isinstance(lg._null_handler, logging.NullHandler)
    assert lg.console_handler is None


@pytest.mark.parametrize('method', ['debug', 'info', 'critical', 'exception'])
def test_disabled_list_blocks_methods(logger_cls, make_logger, capsys, method):
    lg = make_logger(name='blocked_a')
    logger_cls.add_disabled_logger('blocked_a')
    getattr(lg, method)('скрыто')
    assert capsys.readouterr().err == ''


@pytest.mark.parametrize('method', ['warning', 'error'])
def test_disabled_list_blocks_warning_and_error(logger_cls, make_logger, capsys, method):
    """B4: раньше warning/error писали, даже если логгер в списке отключённых."""
    lg = make_logger(name='blocked_b')
    logger_cls.add_disabled_logger('blocked_b')
    getattr(lg, method)('скрыто')
    assert capsys.readouterr().err == ''


def test_disabled_list_management(logger_cls):
    logger_cls.add_disabled_logger('a')
    logger_cls.add_disabled_logger('a')
    logger_cls.add_disabled_logger('b')
    assert logger_cls._disabled_loggers.count('a') == 1
    assert logger_cls.is_disabled('a') and logger_cls.is_disabled('b')
    logger_cls.remove_disabled_logger('a')
    logger_cls.remove_disabled_logger('missing')  # без ошибки
    assert not logger_cls.is_disabled('a')
    logger_cls.clear_disabled_loggers()
    assert not logger_cls.is_disabled('b')


def test_disabled_list_is_shared_between_all_subclasses(logger_cls):
    """Список отключённых хранится на BaseAppLogger и общий для всех наследников."""
    from app.utils.logger.base_logger import BaseAppLogger
    logger_cls.add_disabled_logger('shared_name')
    assert BaseAppLogger.is_disabled('shared_name')
    assert logger_cls._disabled_loggers is BaseAppLogger._disabled_loggers


def test_disabled_list_is_exact_name_not_prefix(logger_cls, make_logger, capsys):
    lg = make_logger(name='gui.Table.sub')
    logger_cls.add_disabled_logger('gui.Table')
    lg.info('видно')
    assert 'видно' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Глубина вызова в тексте (show_call_depth)
# ---------------------------------------------------------------------------

def test_show_call_depth_adds_indent_by_stack_depth(make_logger, log_dir):
    lg = make_logger(config=make_config(log_dir, show_call_depth='True'), enable_file_logging=True)

    def level1():
        lg.info('one')
        level2()

    def level2():
        lg.info('two')

    level1()
    lines = read(os.path.join(log_dir, 'app.log')).splitlines()
    d1 = len(LINE_RE.match(lines[0])['indent'])
    d2 = len(LINE_RE.match(lines[1])['indent'])
    assert d1 > 0
    assert d2 == d1 + 1


def test_without_show_call_depth_no_indent(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)

    def nested():
        lg.info('x')

    nested()
    assert LINE_RE.match(read(os.path.join(log_dir, 'app.log')).strip())['indent'] == ''


def test_formatted_returns_empty_when_disabled(make_logger):
    lg = make_logger()
    lg._enabled = False
    assert lg._formatted('x') == ''


def test_get_caller_info_explicit_levels(make_logger):
    lg = make_logger()
    info = lg._get_caller_info(levels_up=1)
    assert 'test_get_caller_info_explicit_levels' in info
    deep = lg._get_caller_info(levels_up=10_000)
    assert deep.startswith('File "')


def test_exception_caller_info_points_to_caller(make_logger, log_dir):
    """B6: раньше log.exception() указывал на строку внутри base_logger.py."""
    lg = make_logger(enable_file_logging=True)
    lineno = inspect.currentframe().f_lineno + 4
    try:
        raise ValueError('x')
    except ValueError:
        lg.exception('упало')
    first = read(os.path.join(log_dir, 'app.log')).splitlines()[0]
    m = LINE_RE.match(first)
    assert m['func'] == 'test_exception_caller_info_points_to_caller'
    assert int(m['line']) == lineno


@pytest.mark.parametrize('method', ['debug', 'info', 'warning', 'error', 'critical', 'exception'])
def test_filtered_record_does_not_look_up_caller(make_logger, log_dir, monkeypatch, method):
    """P1: запись ниже уровня логгера не ищет место вызова (раньше — обход стека впустую)."""
    lg = make_logger(config=make_config(log_dir, LOG_LEVEL='CRITICAL'))
    if method == 'critical':
        lg.reconfigure(level='CRITICAL')
        lg.logger.setLevel(logging.CRITICAL + 1)
    calls = []
    monkeypatch.setattr(lg, '_get_caller_info', lambda *a, **k: calls.append(1) or '')
    result = getattr(lg, method)('отброшено')
    assert calls == []
    if method == 'exception':
        assert result == 'отброшено'


def test_passing_record_still_looks_up_caller(make_logger, monkeypatch):
    lg = make_logger()
    calls = []
    real = lg._get_caller_info
    monkeypatch.setattr(lg, '_get_caller_info', lambda *a, **k: calls.append(1) or real(*a, **k))
    lg.info('проходит')
    assert calls == [1]
