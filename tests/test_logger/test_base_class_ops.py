# tests/test_logger/test_base_class_ops.py

"""
Операции уровня класса: реестр экземпляров, группы по префиксу, *_exact,
глобальные обработчики, закрытие, массовая перезагрузка конфига.
"""

import logging
import os

import pytest

from tests.test_logger.conftest import make_config, read


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------

def test_multiton_returns_same_instance(logger_cls, make_logger):
    lg = make_logger(name='same')
    assert logger_cls.get_instance('same') is lg
    assert logger_cls.thec_create('same') is True
    assert logger_cls.thec_create('other') is False


def test_existing_instance_ignores_new_arguments(logger_cls, make_logger, log_dir):
    lg = make_logger(name='keep', config=make_config(log_dir, LOG_LEVEL='INFO'))
    again = logger_cls.get_instance('keep', config=make_config(log_dir, LOG_LEVEL='ERROR'),
                                    enable_file_logging=True)
    assert again is lg
    assert lg.log_level == logging.INFO
    assert lg.file_handler is None


def test_registries_are_per_class(logger_cls, make_logger):
    from app.utils.logger.base_logger import BaseAppLogger
    make_logger(name='only_here')
    assert 'only_here' in logger_cls._instances
    assert 'only_here' not in BaseAppLogger._instances


def test_force_new_replaces_registry_entry(logger_cls, make_logger):
    old = make_logger(name='fresh')
    new = make_logger(name='fresh', force_new=True)
    assert new is not old
    assert logger_cls._instances['fresh'] is new
    assert new.logger is old.logger  # logging.getLogger(name) общий


@pytest.mark.xfail(strict=True, reason=(
    "BUG: force_new=True не снимает обработчики старого экземпляра с общего "
    "logging.Logger → каждое сообщение пишется дважды"
))
def test_force_new_does_not_duplicate_output(make_logger, log_dir, capsys):
    make_logger(name='dup', enable_file_logging=True, use_name_in_filename=True)
    new = make_logger(name='dup', force_new=True, enable_file_logging=True,
                      use_name_in_filename=True)
    new.info('один')
    # Файл перестал дублироваться «случайно»: новый экземпляр подключается к
    # обработчику старого (один обработчик на файл). Консоль — нет.
    assert read(os.path.join(log_dir, 'dup.log')).count('один') == 1
    assert capsys.readouterr().err.count('один') == 1


# ---------------------------------------------------------------------------
# Группы по префиксу
# ---------------------------------------------------------------------------

@pytest.fixture
def group(make_logger):
    names = ['gui.Table', 'gui.Table.Model', 'gui.Form', 'api.Db']
    return {n: make_logger(name=n) for n in names}


def test_get_group_loggers(logger_cls, group):
    assert sorted(logger_cls.get_group_loggers('gui.Table')) == ['gui.Table', 'gui.Table.Model']
    assert sorted(logger_cls.get_group_loggers('gui.')) == ['gui.Form', 'gui.Table', 'gui.Table.Model']


def test_disable_enable_group(logger_cls, group):
    logger_cls.disable_group('gui.')
    assert [n for n, lg in group.items() if not lg.is_enabled()] == \
        ['gui.Table', 'gui.Table.Model', 'gui.Form']
    logger_cls.enable_group('gui.')
    assert all(lg.is_enabled() for lg in group.values())


def test_group_prefix_is_plain_startswith(logger_cls, group, make_logger):
    """Префикс 'gui.Table' цепляет и 'gui.TableX' — это не иерархия по точкам."""
    other = make_logger(name='gui.TableX')
    logger_cls.disable_group('gui.Table')
    assert not other.is_enabled()


def test_set_group_level(logger_cls, group):
    logger_cls.set_group_level('api.', 'ERROR')
    assert group['api.Db'].logger.level == logging.ERROR
    # set_group_level идёт через setLevel → self.log_level не меняется
    assert group['api.Db'].log_level == logging.DEBUG


def test_reconfigure_group(logger_cls, group):
    logger_cls.reconfigure_group('gui.Table', level='WARNING')
    assert group['gui.Table'].log_level == logging.WARNING
    assert group['gui.Table.Model'].log_level == logging.WARNING
    assert group['gui.Form'].log_level == logging.DEBUG


def test_disable_enable_group_console(logger_cls, group):
    logger_cls.disable_group_console('gui.')
    assert not group['gui.Form'].is_console_enabled()
    assert group['api.Db'].is_console_enabled()
    logger_cls.enable_group_console('gui.')
    assert group['gui.Form'].is_console_enabled()


def test_enable_disable_group_file(logger_cls, group):
    logger_cls.enable_group_file('api.')
    assert group['api.Db'].file_handler is not None
    logger_cls.disable_group_file('api.')
    assert group['api.Db'].file_handler is None


def test_disable_file_after_enable(logger_cls, group):
    """R3: раньше файл, включённый у логгера без enable_file_logging=True, не выключался."""
    lg = group['api.Db']
    lg.enable_file()
    lg.disable_file()
    assert lg.file_handler is None
    assert lg.is_file_enabled() is False


BUG_GROUP_LEVEL = (
    "BUG: set_group_console_level/set_group_file_level переводят уровень в int, "
    "а set_console_level/set_file_level снова вызывают _parse_log_level → AttributeError"
)


@pytest.mark.xfail(strict=True, reason=BUG_GROUP_LEVEL)
def test_set_group_console_level(logger_cls, group):
    logger_cls.set_group_console_level('gui.', 'ERROR')
    assert group['gui.Form'].console_handler.level == logging.ERROR


@pytest.mark.xfail(strict=True, reason=BUG_GROUP_LEVEL)
def test_set_group_file_level(logger_cls, group):
    logger_cls.enable_group_file('gui.')
    logger_cls.set_group_file_level('gui.', 'ERROR')
    assert group['gui.Form'].file_handler.level == logging.ERROR


def test_set_group_console_level_current_behavior(logger_cls, group):
    with pytest.raises(AttributeError):
        logger_cls.set_group_console_level('gui.', 'ERROR')


# ---------------------------------------------------------------------------
# *_exact
# ---------------------------------------------------------------------------

def test_exact_methods(logger_cls, group):
    lg = group['gui.Table']
    child = group['gui.Table.Model']

    logger_cls.disable_exact('gui.Table')
    assert not lg.is_enabled() and child.is_enabled()
    logger_cls.enable_exact('gui.Table')
    assert lg.is_enabled()

    logger_cls.disable_console_exact('gui.Table')
    assert not lg.is_console_enabled() and child.is_console_enabled()
    logger_cls.enable_console_exact('gui.Table')
    assert lg.is_console_enabled()

    logger_cls.enable_file_exact('gui.Table')
    assert lg.file_handler is not None and child.file_handler is None
    logger_cls.disable_file_exact('gui.Table')
    assert lg.file_handler is None


def test_exact_methods_unknown_name_is_noop(logger_cls):
    for method in ('disable_exact', 'enable_exact', 'disable_console_exact',
                   'enable_console_exact', 'disable_file_exact', 'enable_file_exact'):
        getattr(logger_cls, method)('nobody')


# ---------------------------------------------------------------------------
# Глобальные обработчики
# ---------------------------------------------------------------------------

def test_global_handler_added_to_existing_and_future(logger_cls, make_logger, list_handler):
    early = make_logger(name='early')
    h = list_handler()
    logger_cls.add_global_handler(h)
    late = make_logger(name='late')
    early.info('e')
    late.info('l')
    assert len(h.records) == 2
    assert h in early.handlers and h in late.handlers


def test_global_handler_survives_rebuild(logger_cls, make_logger, list_handler):
    lg = make_logger()
    h = list_handler()
    logger_cls.add_global_handler(h)
    lg.disable_console()
    lg.reconfigure(level='INFO')
    lg.info('после перестроения')
    assert h.messages[-1].endswith('после перестроения')
    assert lg.logger.handlers.count(h) == 1


def test_global_handler_stays_on_disable_but_gets_nothing(logger_cls, make_logger, list_handler):
    """disable() не снимает глобальные обработчики, но методы логгера молчат по _enabled."""
    lg = make_logger()
    h = list_handler()
    logger_cls.add_global_handler(h)
    lg.disable()
    assert h in lg.logger.handlers
    lg.error('нет')
    assert h.records == []
    lg.enable()
    assert lg.logger.handlers.count(h) == 1


def test_remove_global_handler(logger_cls, make_logger, list_handler):
    lg = make_logger()
    h = list_handler()
    logger_cls.add_global_handler(h)
    logger_cls.remove_global_handler(h)
    lg.info('x')
    assert h.records == []
    assert h not in logger_cls._global_handlers
    logger_cls.remove_global_handler(h)  # повторно без ошибки


def test_global_handlers_shared_by_all_subclasses(logger_cls, list_handler):
    from app.utils.logger.base_logger import BaseAppLogger
    h = list_handler()
    logger_cls.add_global_handler(h)
    assert h in BaseAppLogger._global_handlers


# ---------------------------------------------------------------------------
# reload_all_from_config
# ---------------------------------------------------------------------------

def test_reload_all_from_config_applies_name_prefixed_keys(logger_cls, make_logger, log_dir):
    a = make_logger(name='ra')
    b = make_logger(name='rb')
    logger_cls.reload_all_from_config(make_config(
        log_dir, LOG_LEVEL='INFO', ra_LEVEL='ERROR', rb_console_enabled='False'))
    assert a.log_level == logging.ERROR
    assert b.log_level == logging.INFO
    assert not b.is_console_enabled()


def test_reload_all_from_config_does_not_create_loggers(logger_cls, make_logger, log_dir):
    make_logger(name='only')
    logger_cls.reload_all_from_config(make_config(log_dir, ghost_LEVEL='ERROR'))
    assert list(logger_cls._instances) == ['only']


# ---------------------------------------------------------------------------
# Закрытие и переоткрытие
# ---------------------------------------------------------------------------

def test_close_removes_handlers(make_logger):
    lg = make_logger(enable_file_logging=True)
    lg.close()
    assert lg.logger.handlers == []
    assert lg.handlers == []


def test_close_all_clears_registry(logger_cls, make_logger):
    a = make_logger(name='c1')
    make_logger(name='c2')
    logger_cls.close_all()
    assert logger_cls._instances == {}
    assert a.logger.handlers == []


def test_logger_object_still_usable_after_close(make_logger, capsys):
    """После close() методы не падают; WARNING+ уходят в logging.lastResort."""
    lg = make_logger()
    lg.close()
    lg.info('тихо')
    lg.warning('lastResort')
    assert 'lastResort' in capsys.readouterr().err


def test_reopen_all_files_recreates_deleted_file(logger_cls, make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)
    path = os.path.join(log_dir, 'app.log')
    lg.info('до')
    lg.file_handler.close()
    os.remove(path)
    logger_cls.reopen_all_files()
    assert os.path.exists(path)
    lg.info('после')
    assert 'после' in read(path)


def test_watchdog_started_once(logger_cls, make_logger, monkeypatch):
    from app.utils.logger.base_logger import BaseAppLogger
    started = []
    monkeypatch.setattr(BaseAppLogger, '_watchdog_started', False)
    monkeypatch.setattr('threading.Thread.start', lambda self: started.append(self.name))
    logger_cls.start_file_watchdog(interval_sec=60)
    logger_cls.start_file_watchdog(interval_sec=60)
    assert started == ['LoggerWatchdog']


def test_show_call_depth_global_flag(logger_cls):
    logger_cls.on_show_call_depth_global()
    assert logger_cls.status_show_call_depth_global() is True
    logger_cls.off_show_call_depth_global()
    assert logger_cls.status_show_call_depth_global() is False
