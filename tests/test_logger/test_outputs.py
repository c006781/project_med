# tests/test_logger/test_outputs.py

"""
Выводы-функции: add_output / add_global_output / CallableHandler.

Сценарий из жизни — отправка лога в Telegram-бот функцией вида ``send(text)``.
"""

import logging
import threading
import time

import pytest

from app.utils.logger.base_logger import CallableHandler
from tests.test_logger.conftest import make_config


@pytest.fixture
def lg(make_logger):
    return make_logger(name='out')


# ---------------------------------------------------------------------------
# Основное
# ---------------------------------------------------------------------------

def test_output_receives_formatted_line(lg):
    got = []
    lg.add_output(got.append)
    lg.info('в функцию')
    assert len(got) == 1
    line = got[0]
    assert '\tINFO\t[out]\t' in line
    assert 'in <test_output_receives_formatted_line>' in line
    assert line.endswith('в функцию')


def test_output_with_print(lg, capsys):
    lg.add_output(print)
    lg.warning('через print')
    assert 'через print' in capsys.readouterr().out


def test_output_level(lg):
    got = []
    lg.add_output(got.append, level='ERROR')
    lg.info('нет')
    lg.error('да')
    assert len(got) == 1 and got[0].endswith('да')


def test_output_level_as_int(lg):
    got = []
    lg.add_output(got.append, level=logging.WARNING)
    lg.info('нет')
    lg.warning('да')
    assert len(got) == 1


def test_logger_level_filters_before_output(make_logger, log_dir):
    lg = make_logger(config=make_config(log_dir, LOG_LEVEL='ERROR'))
    got = []
    lg.add_output(got.append)  # порог вывода NOTSET, но логгер — ERROR
    lg.warning('нет')
    assert got == []


def test_output_formatter_string_with_plain_message(lg):
    got = []
    lg.add_output(got.append, formatter='%(levelname)s|%(name)s|%(plain_message)s')
    lg.error('коротко')
    assert got == ['ERROR|out|коротко']


def test_output_formatter_object(lg):
    got = []
    lg.add_output(got.append, formatter=logging.Formatter('>> %(plain_message)s'))
    lg.info('x')
    assert got == ['>> x']


def test_plain_message_for_decorator_records(lg):
    got = []
    lg.add_output(got.append, formatter='%(plain_message)s')

    @lg.log_execution_time(description='задача')
    def job():
        pass

    job()
    assert got[0] == 'задача [Начало]'
    assert got[1].startswith('задача [Завершение:')


def test_plain_message_for_foreign_records(lg):
    """Записи не из методов логгера (напрямую в logging.Logger) тоже форматируются."""
    got = []
    lg.add_output(got.append, formatter='%(plain_message)s')
    lg.logger.warning('напрямую %s', 'в logging')
    assert got == ['напрямую в logging']


def test_exception_traceback_in_output(lg):
    got = []
    lg.add_output(got.append)
    try:
        raise KeyError('k')
    except KeyError:
        lg.exception('упало')
    assert 'Traceback' in got[0] and "KeyError: 'k'" in got[0]


def test_add_output_rejects_non_callable(lg):
    with pytest.raises(TypeError):
        lg.add_output('не функция')


# ---------------------------------------------------------------------------
# Жизненный цикл
# ---------------------------------------------------------------------------

def test_output_survives_rebuilds(lg, log_dir):
    got = []
    lg.add_output(got.append)
    lg.disable_console()
    lg.enable_file()
    lg.reconfigure(level='INFO', console_enabled=True)
    lg.reload_from_config(make_config(log_dir, file_enabled='True'))
    lg.info('после перестроений')
    assert got[-1].endswith('после перестроений')
    assert lg.logger.handlers.count(lg.get_outputs()[0]) == 1


def test_output_silent_when_logger_disabled(logger_cls, lg):
    got = []
    lg.add_output(got.append)
    lg.disable()
    lg.error('нет')
    lg.enable()
    logger_cls.add_disabled_logger('out')
    lg.error('нет')
    assert got == []


def test_only_output_no_console(lg, capsys):
    got = []
    lg.add_output(got.append)
    lg.disable_console()
    lg.info('только в функцию')
    assert capsys.readouterr().err == ''
    assert len(got) == 1


def test_remove_output_by_handler_and_func(lg):
    got = []
    h = lg.add_output(got.append)
    assert lg.get_outputs() == [h]
    assert lg.remove_output(h) is True
    lg.info('нет')
    assert got == []
    lg.add_output(got.append)
    lg.add_output(got.append)
    assert lg.remove_output(got.append) is True
    assert lg.get_outputs() == []
    assert lg.remove_output(got.append) is False


def test_outputs_are_per_logger(make_logger):
    a, b = make_logger(name='oa'), make_logger(name='ob')
    got = []
    a.add_output(got.append)
    b.info('от b')
    assert got == []


def test_output_on_slave_not_shared_with_master(make_logger, log_dir):
    master = make_logger(name='om', config=make_config(log_dir, file_enabled='True'),
                         enable_file_logging=True)
    slave = make_logger(name='os', enable_file_logging='om')
    got = []
    slave.add_output(got.append)
    master.info('мастер')
    slave.info('слейв')
    assert len(got) == 1 and got[0].endswith('слейв')


def test_set_formatter_applies_to_outputs(lg):
    got = []
    lg.add_output(got.append)
    lg.set_formatter(logging.Formatter('F:%(plain_message)s'))
    lg.info('x')
    assert got == ['F:x']


def test_close_closes_outputs(lg):
    h = lg.add_output(lambda text: None, background=True)
    lg.close()
    assert lg.get_outputs() == []
    assert not h._thread.is_alive()


# ---------------------------------------------------------------------------
# Защиты
# ---------------------------------------------------------------------------

def test_failing_output_does_not_break_logging(lg, capsys):
    good = []

    def broken(text):
        raise ConnectionError('сеть недоступна')

    lg.add_output(broken)
    lg.add_output(good.append)
    lg.error('всё равно доходит')
    assert len(good) == 1
    err = capsys.readouterr().err
    assert '--- Logging error ---' in err and 'ConnectionError' in err


def test_output_that_logs_itself_does_not_recurse(lg):
    calls = []

    def chatty(text):
        calls.append(text)
        lg.warning('вывод сам пишет в лог')

    lg.add_output(chatty)
    lg.info('исходное')
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Фоновая доставка
# ---------------------------------------------------------------------------

def test_background_does_not_block_and_delivers_in_order(lg):
    got = []
    release = threading.Event()

    def slow(text):
        release.wait(5)
        got.append(text)

    h = lg.add_output(slow, background=True, formatter='%(plain_message)s')
    started = time.perf_counter()
    for i in range(5):
        lg.info(f'm{i}')
    assert time.perf_counter() - started < 0.5  # не ждали медленную функцию
    release.set()
    assert h.flush(timeout=5) is True
    assert got == [f'm{i}' for i in range(5)]


def test_background_runs_in_other_thread(lg):
    threads = []
    h = lg.add_output(lambda text: threads.append(threading.current_thread().name),
                      background=True)
    lg.info('x')
    h.flush(timeout=5)
    assert threads and threads[0].startswith('LogOutput-')


def test_background_queue_overflow_drops(lg):
    release = threading.Event()
    h = lg.add_output(lambda text: release.wait(5), background=True, queue_size=2)
    for i in range(10):
        lg.info(f'm{i}')
    assert h.dropped >= 7  # 1 в работе + 2 в очереди
    release.set()
    h.flush(timeout=5)


def test_background_close_delivers_rest(lg):
    got = []
    h = lg.add_output(lambda text: (time.sleep(0.01), got.append(text)), background=True)
    for i in range(10):
        lg.info(f'm{i}')
    lg.remove_output(h)
    assert len(got) == 10
    assert not h._thread.is_alive()


def test_background_failing_output_keeps_worker_alive(lg, capsys):
    got = []

    def flaky(text):
        if 'плохо' in text:
            raise RuntimeError('x')
        got.append(text)

    h = lg.add_output(flaky, background=True)
    lg.info('плохо')
    lg.info('хорошо')
    h.flush(timeout=5)
    assert len(got) == 1 and got[0].endswith('хорошо')


# ---------------------------------------------------------------------------
# Глобальные выводы
# ---------------------------------------------------------------------------

def test_global_output_from_all_loggers(logger_cls, make_logger):
    a = make_logger(name='ga')
    got = []
    logger_cls.add_global_output(got.append, formatter='%(name)s:%(plain_message)s')
    b = make_logger(name='gb')
    a.info('1')
    b.info('2')
    assert got == ['ga:1', 'gb:2']


def test_global_output_respects_each_logger_level(logger_cls, make_logger, log_dir):
    quiet = make_logger(name='gq', config=make_config(log_dir, LOG_LEVEL='ERROR'))
    loud = make_logger(name='gl')
    got = []
    logger_cls.add_global_output(got.append, formatter='%(name)s')
    quiet.info('нет')
    loud.info('да')
    assert got == ['gl']


def test_remove_global_output(logger_cls, make_logger):
    lg = make_logger(name='gr')
    got = []
    h = logger_cls.add_global_output(got.append)
    assert logger_cls.remove_global_output(h) is True
    lg.info('нет')
    assert got == []
    assert logger_cls.remove_global_output(got.append) is False


def test_close_of_one_logger_keeps_global_output(logger_cls, make_logger):
    """close() одного логгера не закрывает общий вывод для остальных."""
    a, b = make_logger(name='gc1'), make_logger(name='gc2')
    got = []
    h = logger_cls.add_global_output(got.append, background=True)
    a.close()
    b.info('после close a')
    assert h.flush(timeout=5)
    assert any('после close a' in t for t in got)
    logger_cls.remove_global_output(h)


# ---------------------------------------------------------------------------
# CallableHandler напрямую (для проектов на голом logging)
# ---------------------------------------------------------------------------

def test_callable_handler_with_plain_logging():
    got = []
    log = logging.getLogger('plain.output.test')
    log.propagate = False
    h = CallableHandler(got.append, level='INFO')
    h.setFormatter(logging.Formatter('%(levelname)s:%(plain_message)s'))
    log.addHandler(h)
    try:
        log.setLevel(logging.DEBUG)
        log.debug('нет')
        log.info('да')
    finally:
        log.removeHandler(h)
        h.close()
    assert got == ['INFO:да']
    assert repr(h).startswith('<CallableHandler append (INFO)')
