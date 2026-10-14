# tests/test_logger/test_app_logger.py

"""
AppLogger — наследник BaseAppLogger, получающий конфиг приложения через configure().

После развязки (2026-10-14) модуль логгера конфиг не читает: его передаёт
app.config.logging_setup.setup_logging() из точки входа.
"""

import ast
import os
import subprocess
import sys

import pytest

import app.utils.logger.logger as logger_module
from app.utils.logger.base_logger import BaseAppLogger
from app.utils.logger.logger import AppLogger
from tests.test_logger.conftest import read

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app_cls(logger_cls):
    """Изолированный подкласс AppLogger: свой реестр и своё состояние configure().

    logger_cls подключён ради восстановления общего классового состояния BaseAppLogger.
    """
    class IsolatedApp(AppLogger):
        _instances = {}
        _app_config = None

    yield IsolatedApp

    for inst in list(IsolatedApp._instances.values()):
        for handler in inst.logger.handlers[:]:
            handler.close()
            inst.logger.removeHandler(handler)
    IsolatedApp._instances.clear()


# ---------------------------------------------------------------------------
# build_logger_config — преобразование конфига приложения
# ---------------------------------------------------------------------------

def test_build_defaults_from_empty():
    assert AppLogger.build_logger_config({}) == {
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


def test_build_log_dir_becomes_log_file_with_separator():
    cfg = AppLogger.build_logger_config({'LOG_DIR': os.path.join('.', 'my_logs')})
    assert cfg['LOG_FILE'] == os.path.join('.', 'my_logs') + os.sep


def test_build_log_dir_preferred_over_log_file():
    assert AppLogger.build_logger_config({'LOG_DIR': 'a', 'LOG_FILE': 'b'})['LOG_FILE'] == 'a' + os.sep


def test_build_log_file_fallback():
    assert AppLogger.build_logger_config({'LOG_FILE': 'legacy'})['LOG_FILE'] == 'legacy' + os.sep


@pytest.mark.parametrize('value', ['logs/', 'logs\\', 'logs/app.log', 'LOGS/APP.LOG'])
def test_build_trailing_separator_or_log_extension_kept(value):
    assert AppLogger.build_logger_config({'LOG_DIR': value})['LOG_FILE'] == value


def test_build_values_passed_as_is():
    """Строки из msgpack не приводятся: это делает BaseAppLogger при чтении."""
    cfg = AppLogger.build_logger_config({
        'LOG_LEVEL': 'DEBUG', 'LOG_MAX_BYTES': '100', 'LOG_ARGS': 'True', 'enabled': 'False'})
    assert cfg['LOG_MAX_BYTES'] == '100'
    assert cfg['enabled'] == 'False'
    assert cfg['LOG_ARGS'] == 'True'


def test_build_system_and_user_keys_passed_through():
    cfg = AppLogger.build_logger_config({
        'system_LEVEL': 'DEBUG', 'system_file_enabled': 'False', 'user_anything': 'x'})
    assert cfg['system_LEVEL'] == 'DEBUG'
    assert cfg['system_file_enabled'] == 'False'
    assert cfg['user_anything'] == 'x'


def test_build_other_keys_dropped():
    cfg = AppLogger.build_logger_config({
        'YANDEX_TOKEN': 'secret',
        'ConfigApplier_LEVEL': 'ERROR', 'database_local_path': 'x.db'})
    for key in ('YANDEX_TOKEN', 'ConfigApplier_LEVEL', 'database_local_path'):
        assert key not in cfg


def test_build_does_not_mutate_input():
    src = {'LOG_DIR': 'logs'}
    AppLogger.build_logger_config(src)
    assert src == {'LOG_DIR': 'logs'}


def test_show_call_depth_reaches_logger_config():
    """R5: раньше ключ отбрасывался и ни на что не влиял."""
    assert AppLogger.build_logger_config({'show_call_depth': 'True'}).get('show_call_depth') == 'True'
    assert 'show_call_depth' not in AppLogger.build_logger_config({})


# ---------------------------------------------------------------------------
# До configure(): безопасные значения по умолчанию
# ---------------------------------------------------------------------------

def test_unconfigured_state(app_cls):
    assert app_cls.is_configured() is False
    cfg = app_cls.get_default_config()
    assert cfg['file_enabled'] is False
    assert cfg['console_enabled'] is True
    assert cfg['LOG_LEVEL'] == 'INFO'


def test_unconfigured_logger_console_only(app_cls, capsys):
    lg = app_cls.get_instance('early')
    assert lg.file_handler is None
    lg.info('до настройки')
    assert 'до настройки' in capsys.readouterr().err


def test_unconfigured_slave_of_system_has_no_file(app_cls):
    app_cls.get_instance('system')
    svc = app_cls.get_instance('svc', enable_file_logging='system')
    assert svc.file_handler is None


# ---------------------------------------------------------------------------
# configure()
# ---------------------------------------------------------------------------

def _app_config(log_dir, **overrides):
    cfg = {
        'LOG_DIR': log_dir, 'LOG_LEVEL': 'INFO',
        'system_enabled': 'True', 'system_console_enabled': 'False',
        'system_file_enabled': 'True', 'system_LEVEL': 'DEBUG',
        'user_enabled': 'True', 'user_console_enabled': 'True',
        'user_file_enabled': 'True', 'user_LEVEL': 'INFO',
    }
    cfg.update(overrides)
    return cfg


def test_configure_marks_configured_and_copies(app_cls, log_dir):
    src = _app_config(log_dir)
    app_cls.configure(src)
    assert app_cls.is_configured() is True
    src['LOG_LEVEL'] = 'CRITICAL'
    assert app_cls.get_default_config()['LOG_LEVEL'] == 'INFO'


def test_configure_applies_to_loggers_created_after(app_cls, log_dir):
    app_cls.configure(_app_config(log_dir))
    system = app_cls.get_instance('system')
    assert system.get_level() == 'DEBUG'
    assert system.is_console_enabled() is False
    assert system.file_handler is not None
    system.info('после настройки')
    assert 'после настройки' in read(os.path.join(log_dir, 'app.log'))


def test_configure_reconfigures_loggers_created_before(app_cls, log_dir):
    """Главный сценарий старта: логгеры созданы импортами, конфиг пришёл позже."""
    system = app_cls.get_instance('system')
    svc = app_cls.get_instance('svc', enable_file_logging='system')
    assert system.file_handler is None and svc.file_handler is None

    app_cls.configure(_app_config(log_dir))

    assert system.get_level() == 'DEBUG'
    assert svc.get_level() == 'DEBUG'
    assert svc.is_console_enabled() is False
    svc.debug('первая запись старта')
    assert 'первая запись старта' in read(os.path.join(log_dir, 'app.log'))


def test_configure_same_log_file_for_before_and_after(app_cls, log_dir):
    """LOG_FILE у перенастроенных и новых логгеров совпадает (важно для автопривязки)."""
    before = app_cls.get_instance('before')
    app_cls.configure(_app_config(log_dir))
    after = app_cls.get_instance('after')
    assert before.base_log_file == after.base_log_file == log_dir + os.sep


def test_configure_keeps_personal_keys(app_cls, log_dir):
    lg = app_cls.get_instance('ConfigApplier')
    app_cls.configure(_app_config(log_dir, ConfigApplier_LEVEL='ERROR'))
    assert lg.get_level() == 'ERROR'


def test_configure_again_applies_new_values(app_cls, log_dir):
    system = app_cls.get_instance('system')
    app_cls.configure(_app_config(log_dir))
    app_cls.configure(_app_config(log_dir, system_LEVEL='ERROR', system_file_enabled='False'))
    assert system.get_level() == 'ERROR'
    assert system.file_handler is None


def test_reload_all_from_app_config_reapplies_last(app_cls, log_dir):
    system = app_cls.get_instance('system')
    app_cls.configure(_app_config(log_dir, system_LEVEL='ERROR'))
    system.reconfigure(level='DEBUG')
    app_cls.reload_all_from_app_config()
    assert system.get_level() == 'ERROR'


def test_reload_all_from_app_config_unconfigured_uses_defaults(app_cls):
    lg = app_cls.get_instance('x')
    lg.reconfigure(level='DEBUG')
    app_cls.reload_all_from_app_config()
    assert lg.get_level() == 'INFO'


def test_reset_configuration(app_cls, log_dir):
    lg = app_cls.get_instance('system')
    app_cls.configure(_app_config(log_dir))
    app_cls.reset_configuration()
    assert app_cls.is_configured() is False
    assert lg.file_handler is not None  # существующие логгеры не трогаются


def test_configure_does_not_touch_other_class(app_cls, log_dir):
    app_cls.configure(_app_config(log_dir))
    assert AppLogger._app_config is not app_cls._app_config


# ---------------------------------------------------------------------------
# Развязка с конфигом: модуль логгера не зависит от app.config
# ---------------------------------------------------------------------------

def _imported_modules(path):
    tree = ast.parse(open(path, encoding='utf-8').read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize('module', ['logger.py', 'base_logger.py', '__init__.py'])
def test_logger_package_does_not_import_config(module):
    path = os.path.join(PROJECT_ROOT, 'app', 'utils', 'logger', module)
    assert not any(m.startswith('app.config') for m in _imported_modules(path))


def test_import_logger_does_not_load_config():
    """Чистый процесс: импорт логгера не подтягивает app.config и не трогает .env."""
    code = (
        "import sys, app.utils.logger as l;"
        "print(any(m.startswith('app.config') for m in sys.modules));"
        "print(l.AppLogger.is_configured())"
    )
    out = subprocess.run(
        [sys.executable, '-c', code], cwd=PROJECT_ROOT, capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': PROJECT_ROOT}, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ['False', 'False']


# ---------------------------------------------------------------------------
# Побочные эффекты импорта, которые остались
# ---------------------------------------------------------------------------

def test_import_creates_system_and_user():
    assert AppLogger.thec_create('system')
    assert AppLogger.thec_create('user')


def test_app_registry_separate_from_base():
    assert AppLogger._instances is not BaseAppLogger._instances
    assert 'system' not in BaseAppLogger._instances


def test_exports():
    import app.utils.logger as pkg
    assert pkg.__all__ == ['AppLogger']
    assert pkg.AppLogger is AppLogger
    assert logger_module.AppLogger is AppLogger


def test_show_call_depth_applied_by_configure(app_cls, log_dir):
    """R5: show_call_depth из конфига приложения доходит до логгеров."""
    lg = app_cls.get_instance('depth')
    app_cls.configure({'LOG_DIR': log_dir, 'show_call_depth': 'True'})
    assert lg._show_call_depth is True
    app_cls.configure({'LOG_DIR': log_dir, 'show_call_depth': 'False'})
    assert lg._show_call_depth is False
