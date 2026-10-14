# tests/test_logger/test_stress.py

"""
Нагрузка и граничные случаи: потоки, смена настроек во время записи, ротация
общего файла, необычные сообщения, генераторы под декоратором.
"""

import glob
import logging
import os
import re
import threading

import pytest

from tests.test_logger.conftest import make_config, read

LINE_RE = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}\t[A-Z]+\t\[[^\]]+\]\t>* File ".+", line \d+, in <.+>:\t.*$')


def _all_lines(log_dir, pattern='app.log*'):
    lines = []
    for path in glob.glob(os.path.join(log_dir, pattern)):
        lines.extend(read(path).splitlines())
    return lines


# ---------------------------------------------------------------------------
# Потоки
# ---------------------------------------------------------------------------

def test_many_threads_one_shared_file(make_logger, log_dir):
    """8 потоков × 4 логгера (один общий файл) × 150 записей: ничего не потеряно и не перемешано."""
    master = make_logger(name='tm', config=make_config(log_dir, file_enabled='True', console_enabled='False'),
                         enable_file_logging=True)
    loggers = [master] + [
        make_logger(name=f'ts{i}', config=make_config(log_dir, console_enabled='False'),
                    enable_file_logging='tm')
        for i in range(3)
    ]
    assert all(lg.file_handler is master.file_handler for lg in loggers)
    errors = []

    def worker(n):
        try:
            for k in range(150):
                loggers[k % 4].info(f'поток{n}-{k}')
        except Exception as e:  # pragma: no cover - должно быть пусто
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    lines = _all_lines(log_dir)
    assert len(lines) == 8 * 150
    assert all(LINE_RE.match(l) for l in lines)
    got = {l.rsplit('\t', 1)[-1] for l in lines}
    assert got == {f'поток{n}-{k}' for n in range(8) for k in range(150)}


def test_reconfigure_while_logging(make_logger, log_dir):
    """Смена уровня/консоли/файла во время записи из других потоков — без исключений.

    Только корректность. Под непрерывной записью из нескольких потоков каждое
    перестроение ждёт блокировок сотни миллисекунд (блокировки Python не честные) —
    см. IMPLEMENTATION.md §9, поэтому итераций немного.
    """
    import time
    lg = make_logger(name='rc', config=make_config(log_dir, file_enabled='True', console_enabled='False'),
                     enable_file_logging=True)
    stop = threading.Event()
    errors = []

    def writer():
        try:
            while not stop.is_set():
                lg.info('запись')
                time.sleep(0)  # отдать GIL, как реальный код между записями
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(3)]
    for t in threads:
        t.start()
    try:
        for i in range(6):
            lg.reconfigure(level='DEBUG' if i % 2 else 'ERROR')
            lg.disable_file()
            lg.enable_file()
    finally:
        stop.set()
        for t in threads:
            t.join()

    assert errors == []
    assert all(LINE_RE.match(l) for l in _all_lines(log_dir))


def test_get_instance_race_returns_one_object(logger_cls, log_dir):
    """Одновременный get_instance с одним именем из многих потоков — один объект."""
    logger_cls.default_config = make_config(log_dir)
    results = []
    barrier = threading.Barrier(10)

    def worker():
        barrier.wait()
        results.append(logger_cls.get_instance('race'))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(r) for r in results}) == 1


# ---------------------------------------------------------------------------
# Ротация общего файла
# ---------------------------------------------------------------------------

def test_rotation_of_shared_file(make_logger, log_dir, capsys):
    """Несколько логгеров через один обработчик: ротация без ошибок и потерь сверх backupCount."""
    cfg = make_config(log_dir, file_enabled='True', console_enabled='False',
                      LOG_MAX_BYTES=2000, LOG_BACKUP_COUNT=50)
    master = make_logger(name='rm', config=cfg, enable_file_logging=True)
    slaves = [make_logger(name=f'rs{i}', config=cfg, enable_file_logging='rm') for i in range(3)]
    for k in range(200):
        (master, *slaves)[k % 4].info(f'запись {k:03d}')

    files = glob.glob(os.path.join(log_dir, 'app.log*'))
    assert len(files) > 5                         # ротация была
    assert 'Logging error' not in capsys.readouterr().err
    lines = _all_lines(log_dir)
    assert len(lines) == 200                      # backupCount с запасом — ничего не потеряно


# ---------------------------------------------------------------------------
# Необычные сообщения
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('message, expected', [
    (123, '123'),
    (None, 'None'),
    ({'k': 1}, "{'k': 1}"),
    ('100% готово', '100% готово'),          # % без аргументов не ломает форматирование
    ('скобки {x}', 'скобки {x}'),
    ('эмодзи ✓ 🚀', 'эмодзи ✓ 🚀'),
])
def test_unusual_messages(make_logger, log_dir, message, expected):
    lg = make_logger(enable_file_logging=True)
    lg.info(message)
    assert read(os.path.join(log_dir, 'app.log')).rstrip('\n').endswith('\t' + expected)


def test_multiline_message(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)
    lg.info('первая\nвторая')
    content = read(os.path.join(log_dir, 'app.log'))
    assert content.endswith('первая\nвторая\n')


def test_very_long_message(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)
    long_text = 'я' * 100_000
    lg.info(long_text)
    assert long_text in read(os.path.join(log_dir, 'app.log'))


# ---------------------------------------------------------------------------
# Декоратор: особые функции
# ---------------------------------------------------------------------------

def test_decorator_on_generator_measures_creation_only(make_logger, log_dir):
    """Генератор: декоратор замеряет только создание генератора, не его перебор."""
    lg = make_logger(enable_file_logging=True)

    @lg.log_execution_time()
    def gen():
        yield 1
        yield 2

    g = gen()
    lines_after_call = len(read(os.path.join(log_dir, 'app.log')).splitlines())
    assert list(g) == [1, 2]
    assert lines_after_call == 2  # [Начало] и [Завершение] записаны до перебора


def test_decorator_recursive_function(make_logger, log_dir):
    lg = make_logger(enable_file_logging=True)

    @lg.log_execution_time(show_depth=True)
    def fact(n):
        return 1 if n <= 1 else n * fact(n - 1)

    assert fact(5) == 120
    lines = read(os.path.join(log_dir, 'app.log')).splitlines()
    depths = [len(re.search(r'\]\t(>*) File', l).group(1)) for l in lines]
    assert depths == [1, 2, 3, 4, 5, 5, 4, 3, 2, 1]


def test_decorated_method_keeps_identity(make_logger):
    lg = make_logger()

    class C:
        @lg.log_execution_time()
        def m(self):
            return self

    c = C()
    assert c.m() is c
    assert C.m.__name__ == 'm'
