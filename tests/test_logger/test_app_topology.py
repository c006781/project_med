# tests/test_logger/test_app_topology.py

"""
Топология логгеров как в приложении и смена режимов через настройки.

Конфиг повторяет то, что AppLogger.get_default_config() строит из
config.msgpack: общие ключи + system_* / user_*. Логгеры создаются теми же
вызовами, что в app/utils/logger/logger.py и в декораторах сервисов.
"""

import logging
import os

import pytest

from tests.test_logger.conftest import make_config, read


@pytest.fixture
def app_cfg(log_dir):
    return make_config(
        log_dir,
        LOG_LEVEL='INFO', LOG_ARGS='False',
        enabled='True', console_enabled='True', file_enabled='True', use_timestamp='False',
        system_enabled='True', system_console_enabled='False',
        system_file_enabled='True', system_LEVEL='DEBUG',
        user_enabled='True', user_console_enabled='True',
        user_file_enabled='True', user_LEVEL='INFO',
    )


@pytest.fixture
def app(logger_cls, app_cfg):
    """Логгеры system, user и три «сервисных», как при импорте приложения."""
    logger_cls.default_config = app_cfg
    system = logger_cls.get_instance(name='system', use_name_in_filename=False, show_call_depth=True)
    user = logger_cls.get_instance(name='user', use_name_in_filename=False)
    services = [
        logger_cls.get_instance(name=f'svc{i}', enable_file_logging='system',
                                use_name_in_filename=False)
        for i in range(3)
    ]
    return logger_cls, system, user, services


@pytest.fixture
def log_file(log_dir):
    return os.path.join(log_dir, 'app.log')


# ---------------------------------------------------------------------------
# Состояние после старта
# ---------------------------------------------------------------------------

def test_startup_system(app):
    _, system, _, _ = app
    assert system.log_level == logging.DEBUG
    assert system.is_console_enabled() is False
    assert system.is_file_enabled() is True
    assert system.has_shared_handler() is False
    # аргумент конструктора enable_file_logging не передан → False,
    # файл включён только ключом system_file_enabled
    assert system._enable_file_logging is False


def test_startup_user_auto_shares_with_system(app):
    """user сам привязывается к system (одинаковый файл, auto_share по умолчанию)."""
    _, system, user, _ = app
    assert user.get_master_logger() is system
    assert user.file_handler is system.file_handler


@pytest.mark.xfail(strict=True, reason=(
    "BUG: при привязке к system user получает уровень мастера (DEBUG) "
    "вместо своего user_LEVEL=INFO"
))
def test_startup_user_level_is_own(app):
    _, _, user, _ = app
    assert user.log_level == logging.INFO


def test_startup_user_level_current_behavior(app):
    _, _, user, _ = app
    assert user.log_level == logging.DEBUG


def test_startup_services_take_system_flags(app):
    """Сервисные логгеры читают system_* через ссылку enable_file_logging='system'."""
    _, _, _, services = app
    for svc in services:
        assert svc.log_level == logging.DEBUG
        assert svc.is_console_enabled() is False
        assert svc.is_file_enabled() is True


BUG_NOT_SHARED = (
    "BUG: сервисные логгеры не привязываются к system: привязка проверяет "
    "system.effective_enable_file_logging() → аргумент конструктора (False). "
    "В итоге каждый логгер открывает свой RotatingFileHandler на тот же файл"
)


@pytest.mark.xfail(strict=True, reason=BUG_NOT_SHARED)
def test_startup_services_share_system_handler(app):
    _, system, _, services = app
    for svc in services:
        assert svc.file_handler is system.file_handler


def test_startup_services_have_own_handlers_on_same_file(app, log_file):
    """Как есть: N логгеров → N открытых обработчиков на один app.log."""
    _, system, _, services = app
    handlers = {id(lg.file_handler) for lg in [system] + services}
    assert len(handlers) == 1 + len(services)
    for svc in services:
        assert os.path.normcase(svc.file_handler.baseFilename) == os.path.normcase(log_file)


def test_startup_everyone_writes_to_one_file(app, log_file):
    _, system, user, services = app
    for lg in [system, user] + services:
        lg.info(f'from {lg.name}')
    content = read(log_file)
    for lg in [system, user] + services:
        assert f'[{lg.name}]' in content


# ---------------------------------------------------------------------------
# Смена режимов из настроек: reload_all_from_config
# ---------------------------------------------------------------------------

def _reload(app, app_cfg, **changes):
    logger_cls = app[0]
    logger_cls.reload_all_from_config(dict(app_cfg, **changes))


def test_settings_system_level(app, app_cfg):
    _, system, user, services = app
    _reload(app, app_cfg, system_LEVEL='ERROR')
    assert system.log_level == logging.ERROR
    assert all(s.log_level == logging.ERROR for s in services)
    assert user.log_level == logging.INFO  # после reload user берёт user_LEVEL


def test_settings_system_file_off_services_stop_writing(app, app_cfg, log_file):
    _, system, _, services = app
    _reload(app, app_cfg, system_file_enabled='False')
    open(log_file, 'w').close()
    system.info('system')
    for s in services:
        s.info('svc')
    assert read(log_file) == ''
    assert all(s.file_handler is None for s in services)


def test_settings_system_file_off_user_keeps_writing(app, app_cfg, log_file):
    """user_file_enabled=True → user продолжает писать через (закрытый) обработчик system."""
    _, system, user, _ = app
    _reload(app, app_cfg, system_file_enabled='False')
    assert system.file_handler is None
    assert user.file_handler is not None
    user.info('user пишет')
    assert '[user]' in read(log_file)


def test_settings_system_console_on(app, app_cfg, capsys):
    _, system, _, services = app
    _reload(app, app_cfg, system_console_enabled='True')
    # Обработчики пересоздаются внутри теста → привязаны к текущему stderr
    system.info('в консоль')
    services[0].info('svc в консоль')
    err = capsys.readouterr().err
    assert '[system]' in err and '[svc0]' in err


def test_settings_system_disabled(app, app_cfg, log_file, capsys):
    _, system, _, services = app
    _reload(app, app_cfg, system_enabled='False')
    open(log_file, 'w').close()
    system.info('нет')
    services[0].info('нет')
    assert read(log_file) == ''
    assert all(not s.is_enabled() for s in services)


def test_settings_reenable_system_after_disable(app, app_cfg, log_file):
    _, system, _, services = app
    _reload(app, app_cfg, system_enabled='False')
    _reload(app, app_cfg, system_enabled='True')
    services[0].info('вернулся')
    assert '[svc0]' in read(log_file)


def test_settings_log_dir_change_moves_everyone(app, app_cfg, tmp_path):
    _, system, user, services = app
    new_dir = str(tmp_path / 'new_logs')
    _reload(app, app_cfg, LOG_FILE=new_dir + os.sep)
    for lg in [system, user] + services:
        lg.info(f'moved {lg.name}')
    content = read(os.path.join(new_dir, 'app.log'))
    for lg in [system, user] + services:
        assert f'[{lg.name}]' in content


def test_no_handlers_means_silence(app, app_cfg, capsys):
    """R6: раньше WARNING+ уходили в stderr через logging.lastResort."""
    _, system, _, services = app
    _reload(app, app_cfg, system_file_enabled='False', system_console_enabled='False')
    services[0].error('должно молчать')
    assert capsys.readouterr().err == ''


# ---------------------------------------------------------------------------
# Связка с экраном настроек: ConfigApplier.apply_logging
# ---------------------------------------------------------------------------

class _FakeManager:
    def __init__(self, data):
        self._data = dict(data)

    def get_all(self):
        return dict(self._data)


def _applier(saved_config):
    from app.config.config_applier import ConfigApplier
    applier = ConfigApplier.__new__(ConfigApplier)
    applier.manager = _FakeManager(saved_config)
    applier.logger = logging.getLogger('test.ConfigApplier')
    return applier


@pytest.fixture
def applied(monkeypatch):
    """Подменяет конфиг, с которым логгеры «настроены сейчас»; возвращает изменяемый словарь."""
    from app.utils.logger.logger import AppLogger
    current = {}
    monkeypatch.setattr(AppLogger, 'current_app_config', classmethod(lambda cls: dict(current)))
    return current


@pytest.fixture
def reload_spy(monkeypatch):
    from app.utils.logger.logger import AppLogger
    calls = []
    # после развязки apply_logging передаёт новый конфиг в AppLogger.configure()
    monkeypatch.setattr(AppLogger, 'configure', classmethod(lambda cls, cfg: calls.append(dict(cfg))))
    return calls


def test_apply_logging_detects_change_against_applied_config(reload_spy, applied):
    applied.update(system_LEVEL='DEBUG')
    new = {'system_LEVEL': 'ERROR'}
    assert _applier(saved_config={}).apply_logging(new) is True
    assert reload_spy == [new]


def test_apply_logging_after_save_reloads_loggers(reload_spy, applied):
    """R1: менеджер уже сохранил новые значения — логгеры всё равно перенастраиваются."""
    applied.update(system_LEVEL='DEBUG')
    saved = {'system_LEVEL': 'ERROR'}
    assert _applier(saved).apply_logging({'system_LEVEL': 'ERROR'}) is True
    assert reload_spy == [{'system_LEVEL': 'ERROR'}]


def test_apply_logging_no_change_no_reconfigure(reload_spy, applied):
    applied.update(system_LEVEL='ERROR')
    assert _applier({}).apply_logging({'system_LEVEL': 'ERROR', 'YANDEX_TOKEN': 'x'}) is False
    assert reload_spy == []


def test_apply_logging_ignores_non_logging_keys(reload_spy, applied):
    applied.update(system_LEVEL='ERROR')
    assert _applier({}).apply_logging({'system_LEVEL': 'ERROR', 'database_local_path': 'new.db'}) is False


def test_apply_logging_with_real_logger_state(logger_cls, monkeypatch):
    """Без подмен: после configure() повторный apply_logging с теми же данными — False."""
    from app.utils.logger.logger import AppLogger

    class App(AppLogger):
        _instances = {}
        _app_config = None

    import app.config.config_applier as ca
    monkeypatch.setattr(ca, 'AppLogger', App)
    applier = _applier({})
    assert applier.apply_logging({'system_LEVEL': 'ERROR'}) is True
    assert App.current_app_config()['system_LEVEL'] == 'ERROR'
    assert applier.apply_logging({'system_LEVEL': 'ERROR'}) is False
