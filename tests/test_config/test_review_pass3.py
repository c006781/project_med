# tests/test_config/test_review_pass3.py

"""
Тесты исправлений проверки модуля конфигурации, проход 3 (2026-10-15).

Номера (M15, AP3a) — журнал проверок в ``app/config/IMPLEMENTATION.md`` §6.
"""

import builtins
import logging
import os

import msgpack
import pytest

import app.config.config_manager.manager as manager_module
from app.config.config_manager.manager import AppConfigManager


@pytest.fixture
def cfg_path(config_sandbox):
    """Путь к config.msgpack во временной папке теста."""
    return str(config_sandbox / 'config.msgpack')


def _deny_open(monkeypatch, path):
    """Подменяет open: чтение ``path`` — PermissionError (файл заблокирован)."""
    real_open = builtins.open
    target = os.path.abspath(path)

    def fake_open(file, mode='r', *args, **kwargs):
        if isinstance(file, str) and os.path.abspath(file) == target and 'r' in mode:
            raise PermissionError(13, 'Процесс не может получить доступ к файлу')
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', fake_open)


def test_m15_unreadable_file_not_renamed(cfg_path, monkeypatch):
    """M15: файл не читается (заблокирован) — НЕ переименовывается и не перезаписывается."""
    with open(cfg_path, 'wb') as f:
        msgpack.pack({'LOG_LEVEL': 'DEBUG'}, f)
    _deny_open(monkeypatch, cfg_path)

    m = AppConfigManager.get_instance(config_path=cfg_path)
    monkeypatch.undo()

    assert m.broken_config_backup is None
    assert 'Не удалось прочитать' in m.broken_config_message
    assert m.get('LOG_LEVEL') == 'INFO'                      # умолчания в памяти
    assert os.listdir(os.path.dirname(cfg_path)) == ['config.msgpack']
    with open(cfg_path, 'rb') as f:
        assert msgpack.unpack(f) == {'LOG_LEVEL': 'DEBUG'}  # файл цел


def test_m15_message_logged(cfg_path, monkeypatch):
    """M15: о нечитаемом файле сообщается в лог (ERROR) с путём."""
    got = []
    handler = manager_module._log.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    try:
        with open(cfg_path, 'wb') as f:
            msgpack.pack({}, f)
        _deny_open(monkeypatch, cfg_path)
        AppConfigManager.get_instance(config_path=cfg_path)
        monkeypatch.undo()
    finally:
        manager_module._log.remove_output(handler)
    assert any(line.startswith('ERROR|Не удалось прочитать') and 'config.msgpack' in line
               for line in got)


def test_m1_garbage_still_recovered(cfg_path):
    """M1 не сломан: мусор в файле — по-прежнему восстановление с копией."""
    with open(cfg_path, 'wb') as f:
        f.write(b'\xc1\xc1')
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.broken_config_backup and os.path.exists(m.broken_config_backup)


def test_ap3a_database_failure_reaches_errors(monkeypatch):
    """AP3a: сбой перезагрузки сервиса попадает в applier.errors (экран предупредит)."""
    import app.config.config_applier as ca
    reloaded = []

    def broken():
        def fail(self):
            raise RuntimeError('db locked')
        return type('B', (), {'reload_config': fail})()

    monkeypatch.setattr(ca, '_SERVICE_PROVIDERS',
                        [broken, lambda: type('S', (), {'reload_config': lambda self: reloaded.append(1)})()])
    monkeypatch.setattr(ca, 'get_sync_service', lambda: type('Y', (), {})())
    a = ca.ConfigApplier.__new__(ca.ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    blocks = a.apply_changes({'database_local_path': 'a'}, {'database_local_path': 'b'})
    assert 'database' in blocks
    assert reloaded == [1]                                   # остальные перезагружены
    assert 'database' in a.errors and 'db locked' in str(a.errors['database'])


def test_m10a_main_window_captures_message_before_settings_load():
    """
    M10a: отложенное окно не читает broken_config_message в момент показа.

    Экран настроек при входе вызывает load(), который сбрасывает сообщение (M10);
    раньше окно «Конфигурация восстановлена» выходило с пустым текстом.
    """
    import ast
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tree = ast.parse(open(os.path.join(root, 'interfaces/gui/gui_window/main_window.py'),
                          encoding='utf-8').read())
    lambdas = [n for n in ast.walk(tree) if isinstance(n, ast.Lambda)]
    late_reads = [n for lam in lambdas for n in ast.walk(lam)
                  if isinstance(n, ast.Attribute) and n.attr == 'broken_config_message']
    assert late_reads == []
