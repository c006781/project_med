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


def test_force_reopen_closes_stream_and_touches_file(handler, tmp_path):
    """force_reopen() закрывает поток; _open() открывает файл, но результат не сохраняется.

    Поток остаётся None до следующей записи. Watchdog вызывает это для всех
    файловых обработчиков каждые 5 секунд.
    """
    _emit(handler, 'x')
    handler._last_check = 0
    handler.force_reopen()
    assert handler._last_check > 0
    assert handler.stream is None
    assert os.path.exists(tmp_path / 'h.log')
    _emit(handler, 'y')
    assert read(tmp_path / 'h.log') == 'x\ny\n'


def test_reopen_if_needed_only_when_missing(handler, tmp_path):
    _emit(handler, 'x')
    stream = handler.stream
    handler.reopen_if_needed()
    assert handler.stream is stream


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
    """PermissionError: 5 попыток с паузой 0.2 c, печать 'подход N провал' в stdout."""
    sleeps, calls = [], []
    monkeypatch.setattr('time.sleep', lambda s: sleeps.append(s))
    monkeypatch.setattr(handler, 'handleError', lambda record: calls.append(record))
    monkeypatch.setattr(logging.handlers.RotatingFileHandler, 'emit',
                        lambda self, record: (_ for _ in ()).throw(PermissionError('locked')))
    _emit(handler, 'x')
    assert sleeps == [0.2] * 4
    assert len(calls) == 1
    assert capsys.readouterr().out.count('провал') == 4
