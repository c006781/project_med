# tests/test_config/test_review_pass1.py

"""
Тесты исправлений проверки модуля конфигурации, проход 1 (2026-10-15).

Номера (G1, M7, AP2 …) — журнал проверок в ``app/config/IMPLEMENTATION.md`` §6.
"""

import logging
import os
import threading
import time

import msgpack
import pytest

import app.config.conf.getenv as getenv_module
import app.config.config_manager.manager as manager_module
from app.config.conf.getenv import get_getenv, save_env_file
from app.config.config_manager.manager import AppConfigManager, BaseConfigManager


@pytest.fixture
def cfg_path(config_sandbox):
    """Путь к config.msgpack во временной папке теста."""
    return str(config_sandbox / 'config.msgpack')


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------

def test_g1_writing_key_does_not_override_system_env(env_file, monkeypatch):
    """G1: дописывание ключа не подменяет переменные окружения системы значениями из .env."""
    env_file.write_text("APP_CONFIG_PATH='from_file.msgpack'\n", encoding='utf-8')
    monkeypatch.setenv('APP_CONFIG_PATH', 'from_system.msgpack')

    assert get_getenv('GITHUB_TOKEN', start_value='tok') == 'tok'      # ключ дописан
    assert 'GITHUB_TOKEN' in env_file.read_text(encoding='utf-8')
    assert os.environ['APP_CONFIG_PATH'] == 'from_system.msgpack'


def test_g1_save_env_file_puts_only_written_keys(env_file, monkeypatch):
    """G1: save_env_file кладёт в os.environ только записанные ключи."""
    env_file.write_text("OTHER='file'\n", encoding='utf-8')
    monkeypatch.setenv('OTHER', 'system')
    save_env_file({'NEW_KEY': 'v'}, dotenv_path=str(env_file))
    assert os.environ['NEW_KEY'] == 'v'
    assert os.environ['OTHER'] == 'system'


def test_g1_update_puts_new_value(env_file):
    """G1: if_update — новое значение попадает и в файл, и в os.environ."""
    env_file.write_text("GITHUB_TOKEN='old'\n", encoding='utf-8')
    save_env_file({'GITHUB_TOKEN': 'new'}, dotenv_path=str(env_file), if_update=True)
    assert os.environ['GITHUB_TOKEN'] == 'new'
    assert "GITHUB_TOKEN='new'" in env_file.read_text(encoding='utf-8')


def test_g2_set_key_failure_does_not_crash(env_file, monkeypatch, capsys):
    """G2: неуспех python-dotenv (ValueError) — предупреждение и умолчание, без падения."""
    env_file.write_text('', encoding='utf-8')
    monkeypatch.setattr(getenv_module, 'set_key', lambda **kw: (None, 'boom', None))
    assert get_getenv('GITHUB_TOKEN', start_value='def') == 'def'
    assert 'GITHUB_TOKEN' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# config.msgpack
# ---------------------------------------------------------------------------

def test_m7_explicit_empty_defaults_respected(cfg_path):
    """M7: defaults={} — пустые умолчания, а не умолчания класса."""
    class WithDefaults(BaseConfigManager):
        _defaults = {'a': 1}

    assert WithDefaults(cfg_path).get_all() == {'a': 1}
    assert WithDefaults(cfg_path, defaults={}).get_all() == {}


def test_m9_load_drops_keys_removed_from_file(cfg_path):
    """M9: load() строит значения заново — ключ, удалённый из файла, возвращается к умолчанию."""
    with open(cfg_path, 'wb') as f:
        msgpack.pack({'LOG_LEVEL': 'DEBUG', 'custom_key': 1}, f)
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.get('custom_key') == 1

    with open(cfg_path, 'wb') as f:
        msgpack.pack({}, f)
    m.set('YANDEX_TOKEN', 'unsaved')
    m.load()
    assert m.get('custom_key') is None
    assert m.get('LOG_LEVEL') == 'INFO'
    assert m.get('YANDEX_TOKEN') == '----'


def test_m10_broken_file_on_load_recovers_with_defaults(cfg_path):
    """M10: битый файл при load() — новый файл со значениями ПО УМОЛЧАНИЮ, не из памяти."""
    m = AppConfigManager.get_instance(config_path=cfg_path)
    m.set('YANDEX_TOKEN', 'in_memory')
    with open(cfg_path, 'wb') as f:
        f.write(b'\xc1\xc1\xc1')
    m.load()
    assert m.broken_config_message
    with open(cfg_path, 'rb') as f:
        assert msgpack.unpack(f)['YANDEX_TOKEN'] == '----'


def test_m10_flags_reset_after_good_load(cfg_path):
    """M10: после успешной перезагрузки флаги битого файла сбрасываются."""
    with open(cfg_path, 'wb') as f:
        f.write(b'\xc1')
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.broken_config_backup
    m.load()                                   # файл уже восстановлен
    assert m.broken_config_backup is None
    assert m.broken_config_message is None


def test_m11_two_breaks_same_second_both_kept(cfg_path, monkeypatch):
    """M11: две поломки в одну секунду — две разные копии."""
    monkeypatch.setattr(manager_module.time, 'strftime', lambda fmt: '20261015_120000')
    backups = []
    for content in (b'\xc1first', b'\xc1second'):
        with open(cfg_path, 'wb') as f:
            f.write(content)
        m = AppConfigManager.get_instance(config_path=cfg_path, force_new=True)
        backups.append(m.broken_config_backup)
    assert len(set(backups)) == 2
    assert [open(b, 'rb').read() for b in backups] == [b'\xc1first', b'\xc1second']


def test_m12_unique_temp_files_and_no_leftovers(cfg_path, monkeypatch):
    """M12: временный файл уникальный (не общий '<путь>.tmp') и не остаётся после save()."""
    # (до M12a spy стоял на tempfile.mkstemp; теперь имя строится в save() — смотрим,
    #  ЧТО подменяет конфиг через os.replace)
    names = []
    real_replace = manager_module.os.replace

    def spy(src, dst):
        names.append(os.path.abspath(src))
        return real_replace(src, dst)

    monkeypatch.setattr(manager_module.os, 'replace', spy)
    m = AppConfigManager.get_instance(config_path=cfg_path)
    m.save()
    m.save()
    assert len(set(names)) == 2
    assert f'{cfg_path}.tmp' not in names
    assert os.path.dirname(names[0]) == os.path.dirname(os.path.abspath(cfg_path))
    assert sorted(os.listdir(os.path.dirname(cfg_path))) == ['config.msgpack']


def test_m13_get_instance_thread_safe(cfg_path, monkeypatch):
    """M13: параллельные get_instance для одного пути — один экземпляр."""
    real_load = BaseConfigManager._load

    def slow_load(self):
        time.sleep(0.02)                       # окно для гонки
        real_load(self)

    monkeypatch.setattr(BaseConfigManager, '_load', slow_load)
    got, barrier = [], threading.Barrier(8)

    def worker():
        barrier.wait()
        got.append(AppConfigManager.get_instance(config_path=cfg_path))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(m) for m in got}) == 1


# ---------------------------------------------------------------------------
# ConfigApplier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('key', ['LOG_ARGS', 'enabled', 'console_enabled', 'file_enabled'])
def test_ap2_logging_common_keys_detected(key):
    """AP2: LOG_ARGS и общие флаги — тоже изменения логирования."""
    from app.config.config_applier import ConfigApplier
    assert ConfigApplier.get_changed_blocks({key: 'False'}, {key: 'True'}) == {'logging_common'}


def test_ap2_apply_logging_reacts_to_log_args(monkeypatch):
    """AP2: смена LOG_ARGS применяется (AppLogger.configure вызывается)."""
    import app.config.config_applier as ca
    calls = []
    monkeypatch.setattr(ca.AppLogger, 'current_app_config', classmethod(lambda cls: {'LOG_ARGS': 'False'}))
    monkeypatch.setattr(ca.AppLogger, 'configure', classmethod(lambda cls, cfg: calls.append(cfg)))
    a = ca.ConfigApplier.__new__(ca.ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    assert a.apply_logging({'LOG_ARGS': 'True'}) is True
    assert calls == [{'LOG_ARGS': 'True'}]


def test_ap3_failing_service_does_not_stop_others(monkeypatch, caplog):
    """AP3: сбой reload_config одного сервиса не мешает перезагрузить остальные."""
    import app.config.config_applier as ca
    reloaded = []

    def bad():
        raise RuntimeError('db locked')

    good = type('S', (), {'reload_config': lambda self: reloaded.append(1)})()

    def bad_provider():
        return type('B', (), {'reload_config': lambda self: bad()})()

    monkeypatch.setattr(ca, '_SERVICE_PROVIDERS', [bad_provider, lambda: good])
    a = ca.ConfigApplier.__new__(ca.ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    with caplog.at_level(logging.ERROR, logger='test.applier'):
        assert a.apply_database({'database_local_path': 'b'}, {'database_local_path': 'a'}) is True
    assert reloaded == [1]
    assert 'db locked' in caplog.text
