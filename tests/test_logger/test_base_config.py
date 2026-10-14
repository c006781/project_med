# tests/test_logger/test_base_config.py

"""
Чтение конфигурации логгером: обязательные ключи, приоритеты префиксов,
приведение типов, влияние параметров get_instance().
"""

import logging
import os

import pytest

from app.utils.logger.base_logger import BaseAppLogger
from tests.test_logger.conftest import make_config


# ---------------------------------------------------------------------------
# _parse_log_level / _to_bool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('DEBUG', logging.DEBUG),
    ('info', logging.INFO),
    ('Warning', logging.WARNING),
    ('ERROR', logging.ERROR),
    ('critical', logging.CRITICAL),
])
def test_parse_log_level_case_insensitive(raw, expected):
    assert BaseAppLogger._parse_log_level(raw) == expected
    assert BaseAppLogger.parse_log_level(raw) == expected


def test_parse_log_level_unknown_raises():
    with pytest.raises(ValueError, match='Неизвестный уровень'):
        BaseAppLogger._parse_log_level('TRACE')


def test_parse_log_level_int_is_not_supported():
    """Числовой уровень не принимается: у int нет .upper()."""
    with pytest.raises(AttributeError):
        BaseAppLogger._parse_log_level(logging.INFO)


@pytest.mark.parametrize('raw, expected', [
    ('True', True), ('true', True), ('1', True), ('yes', True),
    ('False', False), ('false', False), ('0', False), ('no', False), ('', False),
    ('on', False),  # 'on' не распознаётся как истина
    (True, True), (False, False), (1, True), (0, False), (None, False),
])
def test_to_bool(raw, expected):
    assert BaseAppLogger._to_bool(raw) is expected


# ---------------------------------------------------------------------------
# Обязательные ключи
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('missing', ['LOG_LEVEL', 'LOG_FILE', 'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT'])
def test_missing_required_key_raises(make_logger, log_dir, missing):
    config = make_config(log_dir)
    del config[missing]
    with pytest.raises(ValueError, match='Отсутствует обязательный ключ'):
        make_logger(config=config)


@pytest.mark.parametrize('prefix', ['LOG_', ''])
def test_required_keys_accept_prefix_variants(make_logger, log_dir, prefix):
    config = {
        f'{prefix}LEVEL': 'INFO',
        f'{prefix}FILE': log_dir + os.sep,
        f'{prefix}MAX_BYTES': 100,
        f'{prefix}BACKUP_COUNT': 1,
    }
    lg = make_logger(config=config)
    assert lg.log_level == logging.INFO


def test_required_keys_accept_name_prefix(make_logger, log_dir):
    config = {
        'mylog_LEVEL': 'ERROR',
        'mylog_FILE': log_dir + os.sep,
        'mylog_MAX_BYTES': 100,
        'mylog_BACKUP_COUNT': 1,
    }
    lg = make_logger(name='mylog', config=config)
    assert lg.log_level == logging.ERROR


def test_log_dir_alone_is_rejected_by_validation(make_logger, log_dir):
    """LOG_DIR не считается вариантом FILE при валидации (хотя _init_config_load его читает).

    AppLogger обходит это, переписывая LOG_DIR в LOG_FILE в get_default_config().
    """
    config = make_config(log_dir)
    del config['LOG_FILE']
    config['LOG_DIR'] = log_dir
    with pytest.raises(ValueError, match="'FILE'"):
        make_logger(config=config)


# ---------------------------------------------------------------------------
# Приоритет ключей: {name}_KEY > LOG_KEY > KEY > default
# ---------------------------------------------------------------------------

def test_priority_name_prefix_over_log_prefix_over_plain(make_logger, log_dir):
    config = make_config(log_dir, LEVEL='CRITICAL', LOG_LEVEL='ERROR', p1_LEVEL='WARNING')
    assert make_logger(name='p1', config=config).log_level == logging.WARNING

    config = make_config(log_dir, LEVEL='CRITICAL', LOG_LEVEL='ERROR')
    assert make_logger(name='p2', config=config).log_level == logging.ERROR

    config = make_config(log_dir, LEVEL='CRITICAL')
    del config['LOG_LEVEL']
    assert make_logger(name='p3', config=config).log_level == logging.CRITICAL


def test_flags_default_values(make_logger):
    lg = make_logger()
    assert lg.is_enabled() is True
    assert lg.is_console_enabled() is True
    assert lg.use_timestamp is False
    assert lg.log_args is False
    assert lg._show_call_depth is False
    # enable_file_logging по умолчанию False и в конфиге нет file_enabled
    assert lg.is_file_enabled() is False
    assert lg.file_handler is None


def test_flags_read_from_config_strings(make_logger, log_dir):
    config = make_config(
        log_dir,
        enabled='True', console_enabled='False', file_enabled='True',
        use_timestamp='1', LOG_ARGS='yes', show_call_depth='true',
    )
    lg = make_logger(config=config)
    assert lg.is_enabled() is True
    assert lg.is_console_enabled() is False
    assert lg.is_file_enabled() is True
    assert lg.use_timestamp is True
    assert lg.log_args is True
    assert lg._show_call_depth is True


def test_name_specific_flags_override_common(make_logger, log_dir):
    config = make_config(log_dir, console_enabled='True', fl_console_enabled='False')
    lg = make_logger(name='fl', config=config)
    assert lg.is_console_enabled() is False


def test_max_bytes_and_backup_count_converted_to_int(make_logger, log_dir):
    config = make_config(log_dir, LOG_MAX_BYTES='2048', LOG_BACKUP_COUNT='7')
    lg = make_logger(config=config)
    assert lg.log_max_bytes == 2048
    assert lg.log_backup_count == 7


def test_bad_int_raises_value_error(make_logger, log_dir):
    config = make_config(log_dir, LOG_MAX_BYTES='много')
    with pytest.raises(ValueError):
        make_logger(config=config)


# ---------------------------------------------------------------------------
# Параметры get_instance() против конфига
# ---------------------------------------------------------------------------

def test_enable_file_logging_param_used_when_config_has_no_flag(make_logger):
    lg = make_logger(enable_file_logging=True)
    assert lg.is_file_enabled() is True
    assert lg.file_handler is not None


def test_enable_file_logging_param_ignored_when_config_has_flag(make_logger, log_dir):
    """Ключ file_enabled в конфиге сильнее аргумента enable_file_logging."""
    config = make_config(log_dir, file_enabled='False')
    lg = make_logger(config=config, enable_file_logging=True)
    assert lg.is_file_enabled() is False


@pytest.mark.parametrize('value, expected', [('true', True), ('FALSE', False)])
def test_enable_file_logging_bool_strings(make_logger, value, expected):
    lg = make_logger(enable_file_logging=value)
    assert lg.is_file_enabled() is expected


def test_use_name_in_filename_param(make_logger, log_dir):
    lg = make_logger(name='named', enable_file_logging=True, use_name_in_filename=True)
    assert lg.use_name_in_filename is True
    assert lg._get_log_file() == os.path.join(log_dir, 'named.log')


@pytest.mark.xfail(strict=True, reason=(
    "BUG: аргумент show_call_depth в get_instance()/__init__ затирается значением "
    "из конфига (по умолчанию False) в _apply_config()"
))
def test_show_call_depth_param_is_respected(make_logger):
    lg = make_logger(show_call_depth=True)
    assert lg._show_call_depth is True


def test_config_none_uses_get_default_config(logger_cls, log_dir, unique_name):
    logger_cls.default_config = make_config(log_dir, LOG_LEVEL='WARNING')
    lg = logger_cls.get_instance(name=unique_name())
    assert lg.log_level == logging.WARNING


def test_base_get_default_config_not_overridden_raises():
    class Raw(BaseAppLogger):
        _instances = {}

    with pytest.raises(RuntimeError, match='get_default_config'):
        Raw.get_default_config()


def test_config_as_name_copies_settings_of_other_logger(make_logger, log_dir):
    src = make_logger(
        name='src_cfg',
        config=make_config(log_dir, LOG_LEVEL='ERROR', console_enabled='False',
                           LOG_MAX_BYTES=4096, LOG_BACKUP_COUNT=2, LOG_ARGS='True'),
    )
    dst = make_logger(name='dst_cfg', config='src_cfg')
    assert dst.log_level == logging.ERROR
    assert dst.is_console_enabled() is False
    assert dst.log_max_bytes == 4096
    assert dst.log_backup_count == 2
    assert dst.log_args is True
    assert dst.base_log_file == src.base_log_file


def test_config_as_unknown_name_falls_back_to_default(logger_cls, log_dir, capsys):
    logger_cls.default_config = make_config(log_dir, LOG_LEVEL='CRITICAL')
    lg = logger_cls.get_instance(name='orphan_cfg', config='no_such_logger')
    assert lg.log_level == logging.CRITICAL
    assert "references unknown config 'no_such_logger'" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Снимки состояния
# ---------------------------------------------------------------------------

def test_get_config_and_dump_config(make_logger, log_dir):
    lg = make_logger(name='snap', config=make_config(log_dir, LOG_LEVEL='INFO'))
    cfg = lg.get_config()
    assert cfg == {
        'level': 'INFO',
        'base_log_FILE': log_dir + os.sep,
        'log_MAX_BYTES': 10 * 1024 * 1024,
        'log_BACKUP_COUNT': 5,
        'log_ARGS': False,
        'enabled': True,
        'console_enabled': True,
        'file_enabled': False,
        'use_name_in_filename': False,
        'use_timestamp': False,
    }
    dump = lg.dump_config()
    assert dump['name'] == 'snap'
    assert dump['level'] == 'INFO'
    assert dump['log_FILE'] == os.path.join(log_dir, 'app.log')
    assert lg.get_level() == 'INFO'
