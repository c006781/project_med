# tests/test_logger/test_app_logger.py

"""
AppLogger — наследник BaseAppLogger, связанный с конфигурацией приложения.

Связь с конфигом: get_default_config() и reload_all_from_app_config() вызывают
app.config.config_manager.manager.get_config_env(), а модуль при импорте сразу
создаёт логгеры 'system' и 'user'.
"""

import os

import pytest

import app.utils.logger.logger as logger_module
from app.utils.logger.base_logger import BaseAppLogger
from app.utils.logger.logger import AppLogger


@pytest.fixture
def fake_env(monkeypatch):
    """Подменяет get_config_env в модуле логгера; возвращает изменяемый словарь."""
    env = {}
    monkeypatch.setattr(logger_module, 'get_config_env', lambda: dict(env))
    return env


# ---------------------------------------------------------------------------
# get_default_config
# ---------------------------------------------------------------------------

def test_defaults_when_config_empty(fake_env):
    cfg = AppLogger.get_default_config()
    assert cfg == {
        'LOG_LEVEL': 'INFO',
        'LOG_FILE': 'logs' + os.sep,
        'LOG_MAX_BYTES': 10 * 1024 * 1024,
        'LOG_BACKUP_COUNT': 5,
        'LOG_ARGS': False,
        'enabled': True,
        'console_enabled': True,
        'file_enabled': True,
        'use_timestamp': False,
    }


def test_log_dir_becomes_log_file_with_separator(fake_env):
    fake_env['LOG_DIR'] = os.path.join('.', 'my_logs')
    assert AppLogger.get_default_config()['LOG_FILE'] == os.path.join('.', 'my_logs') + os.sep


def test_log_dir_preferred_over_log_file(fake_env):
    fake_env.update(LOG_DIR='dir_a', LOG_FILE='dir_b')
    assert AppLogger.get_default_config()['LOG_FILE'] == 'dir_a' + os.sep


def test_log_file_fallback(fake_env):
    fake_env['LOG_FILE'] = 'legacy'
    assert AppLogger.get_default_config()['LOG_FILE'] == 'legacy' + os.sep


@pytest.mark.parametrize('value', ['logs/', 'logs\\', 'logs/app.log', 'LOGS/APP.LOG'])
def test_trailing_separator_or_log_extension_kept(fake_env, value):
    fake_env['LOG_DIR'] = value
    assert AppLogger.get_default_config()['LOG_FILE'] == value


def test_values_passed_as_is_without_conversion(fake_env):
    """Строки из msgpack не приводятся: это делает BaseAppLogger при чтении."""
    fake_env.update(LOG_LEVEL='DEBUG', LOG_MAX_BYTES='100', LOG_BACKUP_COUNT='2',
                    LOG_ARGS='True', enabled='False', console_enabled='False',
                    file_enabled='False', use_timestamp='True')
    cfg = AppLogger.get_default_config()
    assert cfg['LOG_MAX_BYTES'] == '100'
    assert cfg['enabled'] == 'False'
    assert cfg['LOG_ARGS'] == 'True'


def test_system_and_user_keys_passed_through(fake_env):
    fake_env.update(system_LEVEL='DEBUG', system_file_enabled='False',
                    user_console_enabled='True', user_anything='x')
    cfg = AppLogger.get_default_config()
    assert cfg['system_LEVEL'] == 'DEBUG'
    assert cfg['system_file_enabled'] == 'False'
    assert cfg['user_console_enabled'] == 'True'
    assert cfg['user_anything'] == 'x'


def test_other_keys_dropped(fake_env):
    """Ключи других логгеров и show_call_depth в конфиг логгера не попадают."""
    fake_env.update(YANDEX_TOKEN='secret', show_call_depth='True',
                    ConfigApplier_LEVEL='ERROR', database_local_path='x.db')
    cfg = AppLogger.get_default_config()
    for key in ('YANDEX_TOKEN', 'show_call_depth', 'ConfigApplier_LEVEL', 'database_local_path'):
        assert key not in cfg


@pytest.mark.xfail(strict=True, reason=(
    "BUG: show_call_depth есть на экране настроек и в ConfigApplier, но "
    "get_default_config() его отбрасывает → переключатель ни на что не влияет"
))
def test_show_call_depth_reaches_logger_config(fake_env):
    fake_env['show_call_depth'] = 'True'
    assert AppLogger.get_default_config().get('show_call_depth') == 'True'


def test_get_default_config_reads_config_every_call(monkeypatch):
    calls = []
    monkeypatch.setattr(logger_module, 'get_config_env', lambda: calls.append(1) or {})
    AppLogger.get_default_config()
    AppLogger.get_default_config()
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# reload_all_from_app_config
# ---------------------------------------------------------------------------

def test_reload_all_from_app_config_passes_raw_config(monkeypatch):
    """В reload уходит СЫРОЙ конфиг приложения, а не результат get_default_config()."""
    raw = {'LOG_DIR': 'x', 'system_LEVEL': 'ERROR'}
    monkeypatch.setattr(logger_module, 'get_config_env', lambda: dict(raw))
    seen = []
    monkeypatch.setattr(AppLogger, 'reload_all_from_config', classmethod(lambda cls, cfg: seen.append(cfg)))
    AppLogger.reload_all_from_app_config()
    assert seen == [raw]


# ---------------------------------------------------------------------------
# Побочные эффекты импорта
# ---------------------------------------------------------------------------

def test_import_creates_system_and_user():
    assert AppLogger.thec_create('system')
    assert AppLogger.thec_create('user')


def test_app_registry_separate_from_base():
    assert AppLogger._instances is not BaseAppLogger._instances
    assert 'system' not in BaseAppLogger._instances


def test_logger_module_depends_on_config_module():
    """Модуль логгера импортирует конфиг напрямую — источник циклических зависимостей."""
    assert logger_module.get_config_env.__module__ == 'app.config.config_manager.manager'


def test_exports():
    import app.utils.logger as pkg
    assert pkg.__all__ == ['AppLogger']
    assert pkg.AppLogger is AppLogger
