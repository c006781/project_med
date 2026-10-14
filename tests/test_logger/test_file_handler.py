# tests/test_logger/test_file_handler.py

"""
RobustRotatingFileHandler: восстановление удалённого файла и ротация.
"""

import logging
import os

import pytest

from app.utils.logger.base_logger import RobustRotatingFileHandler
from tests.test_logger.conftest import read


@pytest.fixture
def handler(tmp_path):
    h = RobustRotatingFileHandler(str(tmp_path / 'h.log'), maxBytes=0, backupCount=0, encoding='utf-8')
    h.setFormatter(logging.Formatter('%(message)s'))
    yield h
    h.close()


def _emit(h, msg):
    h.emit(logging.LogRecord('t', logging.INFO, __file__, 1, msg, None, None))


def test_writes_lines(handler, tmp_path):
    _emit(handler, 'a')
    _emit(handler, 'b')
    assert read(tmp_path / 'h.log') == 'a\nb\n'


def test_recreates_deleted_file_after_check_interval(handler, tmp_path):
    path = tmp_path / 'h.log'
    _emit(handler, 'до')
    handler.stream.close()
    handler.stream = None
    os.remove(path)
    handler._last_check = 0  # интервал проверки прошёл
    _emit(handler, 'после')
    assert read(path) == 'после\n'


def test_check_interval_is_one_second(handler):
    assert handler._check_interval == 1.0


def test_recreates_deleted_directory(handler, tmp_path):
    handler.stream.close() if handler.stream else None
    handler.stream = None
    os.remove(tmp_path / 'h.log') if os.path.exists(tmp_path / 'h.log') else None
    handler._reopen()
    assert os.path.exists(tmp_path / 'h.log')


def test_force_reopen_reopens_stream(handler, tmp_path):
    """force_reopen() закрывает и сразу открывает поток заново.

    До 2026-10-14 результат _open() выбрасывался и поток оставался None до
    следующей записи (файл открывался дважды).
    """
    _emit(handler, 'x')
    old_stream = handler.stream
    handler._last_check = 0
    handler.force_reopen()
    assert handler._last_check > 0
    assert handler.stream is not None and handler.stream is not old_stream
    assert old_stream.closed
    assert os.path.exists(tmp_path / 'h.log')
    _emit(handler, 'y')
    assert read(tmp_path / 'h.log') == 'x\ny\n'


def test_reopen_if_needed_only_when_missing(handler, tmp_path):
    _emit(handler, 'x')
    stream = handler.stream
    assert handler.reopen_if_needed() is False
    assert handler.stream is stream
    handler.stream.close()
    handler.stream = None
    os.remove(tmp_path / 'h.log')
    assert handler.reopen_if_needed() is True
    assert os.path.exists(tmp_path / 'h.log')


def test_rotation(tmp_path):
    h = RobustRotatingFileHandler(str(tmp_path / 'r.log'), maxBytes=50, backupCount=2, encoding='utf-8')
    h.setFormatter(logging.Formatter('%(message)s'))
    try:
        for i in range(20):
            _emit(h, f'line {i:02d} ' + 'x' * 10)
    finally:
        h.close()
    files = sorted(os.listdir(tmp_path))
    assert files == ['r.log', 'r.log.1', 'r.log.2']


def test_other_errors_go_to_handle_error(handler, monkeypatch):
    calls = []
    monkeypatch.setattr(handler, 'handleError', lambda record: calls.append(record))
    monkeypatch.setattr(logging.handlers.RotatingFileHandler, 'emit',
                        lambda self, record: (_ for _ in ()).throw(RuntimeError('x')))
    _emit(handler, 'x')
    assert len(calls) == 1


def test_permission_error_retries_then_handle_error(handler, monkeypatch, capsys):
    """PermissionError: MAX_RETRIES попыток с паузой RETRY_DELAY, 'подход N провал' в stderr.

    До 2026-10-14 было 5 попыток по 0,2 с (до 0,8 с подвисания на запись).
    """
    sleeps, calls = [], []
    monkeypatch.setattr('time.sleep', lambda s: sleeps.append(s))
    monkeypatch.setattr(handler, 'handleError', lambda record: calls.append(record))
    monkeypatch.setattr(logging.handlers.RotatingFileHandler, 'emit',
                        lambda self, record: (_ for _ in ()).throw(PermissionError('locked')))
    _emit(handler, 'x')
    assert handler.MAX_RETRIES == 3 and handler.RETRY_DELAY == 0.05
    assert sleeps == [0.05] * 2
    assert len(calls) == 1
    out = capsys.readouterr()
    assert out.err.count('провал') == 2
    assert out.out == ''


def test_retry_pause_releases_lock(handler, monkeypatch):
    """P4: во время паузы перед повторной попыткой блокировка обработчика свободна."""
    import threading
    free_during_pause = []

    def try_lock(got):
        # RLock отпускается только тем потоком, который его взял
        ok = handler._lock.acquire(blocking=False)
        if ok:
            handler._lock.release()
        got.append(ok)

    def fake_sleep(sec):
        got = []
        t = threading.Thread(target=try_lock, args=(got,))
        t.start()
        t.join()
        free_during_pause.append(got[0])

    monkeypatch.setattr('time.sleep', fake_sleep)
    monkeypatch.setattr(handler, 'handleError', lambda record: None)
    monkeypatch.setattr(logging.handlers.RotatingFileHandler, 'emit',
                        lambda self, record: (_ for _ in ()).throw(PermissionError('locked')))
    _emit(handler, 'x')
    assert free_during_pause and all(free_during_pause)


def test_retry_then_success(handler, monkeypatch, tmp_path):
    """Вторая попытка удаётся — запись не теряется."""
    attempts = []
    real_emit = logging.handlers.RotatingFileHandler.emit

    def flaky(self, record):
        attempts.append(1)
        if len(attempts) == 1:
            raise PermissionError('занято')
        real_emit(self, record)

    monkeypatch.setattr('time.sleep', lambda s: None)
    monkeypatch.setattr(logging.handlers.RotatingFileHandler, 'emit', flaky)
    _emit(handler, 'дошло')
    assert len(attempts) == 2
    assert read(tmp_path / 'h.log') == 'дошло\n'
