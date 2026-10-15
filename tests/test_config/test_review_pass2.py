# tests/test_config/test_review_pass2.py

"""
Тесты исправлений проверки модуля конфигурации, проход 2 (2026-10-15).

Номера (M12a, AP4 …) — журнал проверок в ``app/config/IMPLEMENTATION.md`` §6.
"""

import ast
import logging
import os
import stat
import sys

import pytest

from app.config.config_manager.manager import AppConfigManager


@pytest.fixture
def cfg_path(config_sandbox):
    """Путь к config.msgpack во временной папке теста."""
    return str(config_sandbox / 'config.msgpack')


@pytest.mark.skipif(sys.platform == 'win32', reason='права POSIX')
def test_m12a_saved_file_permissions_follow_umask(cfg_path):
    """M12a: config.msgpack получает права по umask, а не 0600 от mkstemp."""
    old = os.umask(0o022)
    try:
        AppConfigManager.get_instance(config_path=cfg_path).save()
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(cfg_path).st_mode) == 0o644


def test_m12a_save_does_not_use_mkstemp():
    """M12a (переносимо): save() не вызывает tempfile.mkstemp (права 0600)."""
    import app.config.config_manager.manager as manager_module
    tree = ast.parse(open(manager_module.__file__, encoding='utf-8').read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == 'mkstemp']
    assert calls == []


def test_ap2a_old_blocks_not_executed():
    """AP2a: прежний словарь блоков — комментарий, а не неиспользуемая переменная."""
    import app.config.config_applier as ca
    import inspect
    func = inspect.unwrap(ca.ConfigApplier.get_changed_blocks)
    assert "_old_blocks" not in func.__code__.co_varnames


def test_d2_doc_example_matches_behavior():
    """D2: пример в описании get_changed_blocks совпадает с реальным результатом."""
    from app.config.config_applier import ConfigApplier
    old = {'database_local_path': './clinic.db', 'PHOTOS_STORAGE_PATH': './photos'}
    new = {'database_local_path': './clinic_new.db', 'PHOTOS_STORAGE_PATH': './photos'}
    assert ConfigApplier.get_changed_blocks(old, new) == {'database', 'sync'}
    assert "{'database', 'sync'}" in ConfigApplier.get_changed_blocks.__doc__


def _bare_applier():
    """ConfigApplier без __init__ (без менеджера и сервисов) с обычным логгером."""
    import app.config.config_applier as ca
    a = ca.ConfigApplier.__new__(ca.ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    return a


def test_ap4_failing_block_does_not_stop_others(monkeypatch, caplog):
    """AP4: сбой блока photos — sync и backup всё равно применяются, ошибка в errors."""
    a = _bare_applier()
    applied = []

    def photos_fail(new, old=None):
        raise OSError('диск Z: недоступен')

    monkeypatch.setattr(a, 'apply_photos_storage', photos_fail)
    monkeypatch.setattr(a, 'apply_sync', lambda new, old=None: applied.append('sync'))
    monkeypatch.setattr(a, 'apply_backup', lambda new, old=None: applied.append('backup'))
    old = {'PHOTOS_STORAGE_PATH': 'a', 'YANDEX_TOKEN': 'x', 'BACKUP_COUNT': 1}
    new = {'PHOTOS_STORAGE_PATH': 'b', 'YANDEX_TOKEN': 'y', 'BACKUP_COUNT': 2}
    with caplog.at_level(logging.ERROR, logger='test.applier'):
        blocks = a.apply_changes(old, new)
    assert blocks == {'photos', 'sync', 'backup'}
    assert applied == ['sync', 'backup']
    assert list(a.errors) == ['photos'] and isinstance(a.errors['photos'], OSError)
    assert 'диск Z' in caplog.text


def test_ap4_errors_reset_between_calls(monkeypatch):
    """AP4: errors относятся только к последнему вызову."""
    a = _bare_applier()
    a.errors = {'photos': OSError('старое')}
    assert a.apply_changes({}, {}) == set()
    assert a.errors == {}


def test_ap4_full_config_forced_isolated(monkeypatch):
    """AP4: apply_full_config без снимка — тоже по блокам, сбой не прерывает остальные."""
    a = _bare_applier()
    applied = []

    def boom(new, old=None):
        raise RuntimeError('db')

    monkeypatch.setattr(a, 'apply_logging', lambda new: applied.append('logging'))
    monkeypatch.setattr(a, 'apply_database', boom)
    for name in ('apply_photos_storage', 'apply_sync', 'apply_backup'):
        monkeypatch.setattr(a, name, lambda new, old=None, n=name: applied.append(n))
    a.apply_full_config({})
    assert applied == ['logging', 'apply_photos_storage', 'apply_sync', 'apply_backup']
    assert list(a.errors) == ['database']


def test_ap5_applier_logger_writes_to_file(monkeypatch):
    """AP5: логгер ConfigApplier пишет в файл system (ошибки видны в exe без консоли)."""
    import app.config.config_applier as ca
    seen = {}

    def fake_get_instance(*args, **kwargs):
        seen.setdefault('calls', []).append((args, kwargs))
        return logging.getLogger('test.applier')

    monkeypatch.setattr(ca, 'AppConfigManager', type('M', (), {'get_instance': staticmethod(lambda: None)}))
    monkeypatch.setattr(ca.AppLogger, 'get_instance', staticmethod(fake_get_instance))
    ca.ConfigApplier()
    (args, kwargs), =[c for c in seen['calls'] if c[0][:1] == ('config_applier',)]
    assert kwargs.get('enable_file_logging') == 'system'


def test_settings_page_reports_partial_apply():
    """AP4: экран настроек показывает предупреждение, если блоки применились не все."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    text = open(os.path.join(root, 'interfaces/gui/gui_window/pages/settings_page.py'),
                encoding='utf-8').read()
    assert 'if applier.errors:' in text
