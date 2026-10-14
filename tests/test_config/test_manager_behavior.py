# tests/test_config/test_manager_behavior.py

"""
Поведение AppConfigManager / config.msgpack и ConfigApplier «как есть».

Известные проблемы — xfail(strict=True) (номера — app/config/IMPLEMENTATION.md §3.2, §3.3).
"""

import logging
import os

import msgpack
import pytest

import app.config.config_manager.manager as manager_module
from app.config.config_manager.manager import (
    AppConfigManager, BaseConfigManager, get_config_env,
)


@pytest.fixture
def cfg_path(config_sandbox):
    return str(config_sandbox / 'config.msgpack')


@pytest.fixture
def manager_log():
    """Записи логгера config.manager (через add_output: его консоль привязана к stderr импорта)."""
    got = []
    handler = manager_module._log.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    yield got
    manager_module._log.remove_output(handler)


@pytest.fixture
def env_ok(env_file):
    """.env с заполненными ключами — без перезаписей при чтении."""
    env_file.write_text("APP_CONFIG_PATH='config.msgpack'\nGITHUB_TOKEN='t'\n", encoding='utf-8')
    return env_file


# ---------------------------------------------------------------------------
# Загрузка и сохранение
# ---------------------------------------------------------------------------

def test_defaults_without_file(cfg_path):
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.config_exists is False
    assert m.get('LOG_LEVEL') == 'INFO'
    assert m.get('system_enabled') == 'False'           # умолчания — строки (M6)
    assert not os.path.exists(cfg_path)                 # файл не создаётся до save()


def test_save_and_reload(cfg_path):
    m = AppConfigManager.get_instance(config_path=cfg_path)
    m.set('YANDEX_TOKEN', 'abc')
    m.set('system_enabled', True)                       # экран настроек сохраняет bool (M6)
    m.save()
    again = AppConfigManager.get_instance(config_path=cfg_path, force_new=True)
    assert again.get('YANDEX_TOKEN') == 'abc'
    assert again.get('system_enabled') is True
    assert again.config_exists


def test_file_values_override_defaults_unknown_kept(cfg_path):
    with open(cfg_path, 'wb') as f:
        msgpack.pack({'LOG_LEVEL': 'DEBUG', 'custom_key': 1}, f)
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.get('LOG_LEVEL') == 'DEBUG'
    assert m.get('custom_key') == 1
    assert m.get('YANDEX_TOKEN') == '----'              # остальное — умолчания


def test_non_dict_file_recovered(cfg_path):
    """M1: файл-«не словарь» тоже считается повреждённым (раньше молча игнорировался)."""
    with open(cfg_path, 'wb') as f:
        msgpack.pack([1, 2, 3], f)
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.get('LOG_LEVEL') == 'INFO'
    assert 'не словарь' in m.broken_config_message
    assert os.path.exists(m.broken_config_backup)


BROKEN = b'\xc1 not msgpack'


def test_corrupted_file_recovered(cfg_path, manager_log):
    """M1: раньше исключение — приложение не запускалось."""
    with open(cfg_path, 'wb') as f:
        f.write(BROKEN)
    m = AppConfigManager.get_instance(config_path=cfg_path)

    # значения по умолчанию
    assert m.get('LOG_LEVEL') == 'INFO'
    # битый файл переименован и не изменён
    backup = m.broken_config_backup
    assert backup and os.path.basename(backup).startswith('config.msgpack.broken-')
    with open(backup, 'rb') as f:
        assert f.read() == BROKEN
    # создан новый файл со значениями по умолчанию
    with open(cfg_path, 'rb') as f:
        assert msgpack.unpack(f, raw=False)['LOG_LEVEL'] == 'INFO'
    # сообщение: где битый и что создан новый
    assert backup in m.broken_config_message
    assert 'Создан новый файл со значениями по умолчанию' in m.broken_config_message
    # сообщение — в лог уровнем ERROR (до настройки логирования — консоль)
    assert any(r.startswith('ERROR|Файл конфигурации повреждён') and backup in r for r in manager_log)


def test_corrupted_file_rename_fails_original_kept(cfg_path, monkeypatch):
    """Не удалось переименовать — битый файл не затирается новым."""
    with open(cfg_path, 'wb') as f:
        f.write(BROKEN)
    monkeypatch.setattr(manager_module.os, 'replace', lambda *a: (_ for _ in ()).throw(PermissionError('занято')))
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.get('LOG_LEVEL') == 'INFO'
    assert m.broken_config_backup is None
    assert 'файл не тронут' in m.broken_config_message
    with open(cfg_path, 'rb') as f:
        assert f.read() == BROKEN


def test_healthy_file_no_message(cfg_path):
    m = AppConfigManager.get_instance(config_path=cfg_path)
    m.save()
    again = AppConfigManager.get_instance(config_path=cfg_path, force_new=True)
    assert again.broken_config_backup is None and again.broken_config_message is None


def test_failed_save_keeps_previous_file(cfg_path, monkeypatch):
    """M2: раньше файл обнулялся до записи — сбой посередине портил конфиг."""
    m = AppConfigManager.get_instance(config_path=cfg_path)
    m.set('YANDEX_TOKEN', 'первый')
    m.save()

    def boom(obj, stream, **kwargs):
        stream.write(b'\x81')          # успели записать начало
        raise OSError('диск переполнен')

    monkeypatch.setattr(manager_module.msgpack, 'pack', boom)
    m.set('YANDEX_TOKEN', 'второй')
    with pytest.raises(OSError):
        m.save()
    monkeypatch.undo()
    with open(cfg_path, 'rb') as f:
        assert msgpack.unpack(f, raw=False)['YANDEX_TOKEN'] == 'первый'
    assert not os.path.exists(cfg_path + '.tmp')          # временный файл убран


def test_save_creates_parent_dirs(config_sandbox):
    path = str(config_sandbox / 'deep' / 'er' / 'c.msgpack')
    m = AppConfigManager.get_instance(config_path=path)
    m.save()
    assert os.path.exists(path)


def test_set_update_reset_get_all_copy(cfg_path):
    m = AppConfigManager.get_instance(config_path=cfg_path)
    m.set('a', 1)
    m.update({'b': 2, 'LOG_LEVEL': 'ERROR'})
    snapshot = m.get_all()
    snapshot['a'] = 999
    assert m.get('a') == 1                               # копия
    m.reset_to_defaults()
    assert m.get('a') is None and m.get('LOG_LEVEL') == 'INFO'


def test_load_rereads_file(cfg_path):
    m = AppConfigManager.get_instance(config_path=cfg_path)
    with open(cfg_path, 'wb') as f:
        msgpack.pack({'LOG_LEVEL': 'CRITICAL'}, f)
    assert m.get('LOG_LEVEL') == 'INFO'
    assert m.load()['LOG_LEVEL'] == 'CRITICAL'


# ---------------------------------------------------------------------------
# Реестр и get_config_env
# ---------------------------------------------------------------------------

def test_multiton_by_path(cfg_path, config_sandbox):
    a = AppConfigManager.get_instance(config_path=cfg_path)
    assert AppConfigManager.get_instance(config_path=cfg_path) is a
    other = AppConfigManager.get_instance(config_path=str(config_sandbox / 'other.msgpack'))
    assert other is not a
    assert AppConfigManager.get_instance(config_path=cfg_path, force_new=True) is not a


def test_create_if_missing(cfg_path):
    m = AppConfigManager.get_instance(config_path=cfg_path, create_if_missing=True)
    assert m.config_exists


def test_get_instance_without_path_takes_path_from_env(env_file, config_sandbox):
    env_file.write_text("APP_CONFIG_PATH='from_env.msgpack'\nGITHUB_TOKEN='t'\n", encoding='utf-8')
    m = AppConfigManager.get_instance()
    assert m._config_path == 'from_env.msgpack'


def test_get_instance_without_path_reads_env_once(env_ok, monkeypatch):
    """E6: путь к конфигу читается из .env один раз (раньше — при каждом вызове)."""
    calls = []
    real = manager_module._old_get_config_env
    monkeypatch.setattr(manager_module, '_old_get_config_env', lambda *a, **k: calls.append(1) or real(*a, **k))
    for _ in range(3):
        AppConfigManager.get_instance()
    assert len(calls) == 1
    AppConfigManager.reset_default_config_path()
    AppConfigManager.get_instance()
    assert len(calls) == 2


def test_get_config_env_returns_copy(env_ok):
    cfg = get_config_env()
    cfg['LOG_LEVEL'] = 'X'
    assert get_config_env()['LOG_LEVEL'] == 'INFO'


# ---------------------------------------------------------------------------
# Слушатели save()
# ---------------------------------------------------------------------------

def test_listeners_called_on_save(cfg_path):
    calls = []
    AppConfigManager.add_change_listener(lambda: calls.append(1))
    AppConfigManager.get_instance(config_path=cfg_path).save()
    assert calls == [1]


def test_listener_add_twice_and_remove(cfg_path):
    calls = []
    cb = lambda: calls.append(1)   # noqa: E731
    AppConfigManager.add_change_listener(cb)
    AppConfigManager.add_change_listener(cb)
    AppConfigManager.get_instance(config_path=cfg_path).save()
    AppConfigManager.remove_change_listener(cb)
    AppConfigManager.get_instance(config_path=cfg_path).save()
    assert calls == [1]


def test_failing_listener_logged_others_run(cfg_path, capsys, manager_log):
    """M5: ошибка слушателя — в лог с traceback (раньше print в stdout); остальные вызываются."""
    calls = []

    def bad():
        raise RuntimeError('сломался')

    AppConfigManager.add_change_listener(bad)
    AppConfigManager.add_change_listener(lambda: calls.append(1))
    AppConfigManager.get_instance(config_path=cfg_path).save()
    assert calls == [1]
    assert 'Ошибка в слушателе конфигурации' not in capsys.readouterr().out
    assert any(r.startswith('ERROR|Ошибка в слушателе конфигурации') and 'сломался' in r
               for r in manager_log)


def test_listeners_shared_by_all_managers(cfg_path, config_sandbox):
    """M3: список слушателей общий для всех менеджеров и путей."""
    calls = []
    AppConfigManager.add_change_listener(lambda: calls.append(1))
    AppConfigManager.get_instance(config_path=str(config_sandbox / 'x.msgpack')).save()
    assert calls == [1]
    assert AppConfigManager._listeners is BaseConfigManager._listeners


def test_listeners_of_dropped_objects_removed(cfg_path):
    """M3: раньше слушатели-методы держали объекты вечно (6 → 11 в приложении)."""
    import gc

    class Service:
        reloads = 0

        def __init__(self):
            AppConfigManager.add_change_listener(self.reload)

        def reload(self):
            Service.reloads += 1

    Service()
    gc.collect()
    AppConfigManager.get_instance(config_path=cfg_path).save()
    assert Service.reloads == 0


# ---------------------------------------------------------------------------
# ConfigApplier
# ---------------------------------------------------------------------------

class _Manager:
    """Заглушка менеджера: get() отдаёт «сохранённые» значения."""

    def __init__(self, data):
        self.data = dict(data)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_all(self):
        return dict(self.data)


class _Sync:
    token = remote_path = local_path = None


@pytest.fixture
def applier(monkeypatch):
    import app.config.config_applier as ca
    sync, photo, reloads = _Sync(), type('P', (), {})(), []
    photo._ensure_storage_exists = lambda: None
    monkeypatch.setattr(ca, 'get_sync_service', lambda: sync)
    monkeypatch.setattr(ca, 'get_photo_service', lambda: photo)
    monkeypatch.setattr(ca, '_SERVICE_PROVIDERS', [lambda: type('S', (), {'reload_config': lambda self: reloads.append(1)})()])
    import app.dependencies as deps
    monkeypatch.setattr(deps, 'clear_services_cache', lambda: None, raising=False)

    def make(saved):
        a = ca.ConfigApplier.__new__(ca.ConfigApplier)
        a.manager = _Manager(saved)
        a.logger = logging.getLogger('test.applier')
        return a
    return make, sync, photo, reloads


def test_get_changed_blocks():
    from app.config.config_applier import ConfigApplier
    old = {'database_local_path': 'a.db', 'system_LEVEL': 'DEBUG', 'BACKUP_COUNT': 1}
    new = {'database_local_path': 'b.db', 'system_LEVEL': 'DEBUG', 'BACKUP_COUNT': 2}
    assert ConfigApplier.get_changed_blocks(old, new) == {'database', 'sync', 'backup'}
    assert ConfigApplier.get_changed_blocks(old, dict(old)) == set()


@pytest.mark.parametrize('method, key', [
    ('apply_database', 'database_local_path'),
    ('apply_photos_storage', 'PHOTOS_STORAGE_PATH'),
    ('apply_backup', 'BACKUP_PATH'),
])
def test_apply_after_save_does_nothing_current(applier, method, key):
    """A1, как есть: менеджер уже сохранил новое значение → «изменений нет»."""
    make, *_ = applier
    new = {key: 'new'}
    assert getattr(make(saved=new), method)(new) is False


@pytest.mark.xfail(strict=True, reason=(
    "A1: apply_* сравнивают с уже сохранённым менеджером (как R1 у логирования) — "
    "после сохранения изменения не применяются"
))
@pytest.mark.parametrize('method, key', [
    ('apply_database', 'database_local_path'),
    ('apply_photos_storage', 'PHOTOS_STORAGE_PATH'),
    ('apply_backup', 'BACKUP_PATH'),
])
def test_apply_after_save_applies(applier, method, key):
    make, *_ = applier
    new = {key: 'new'}
    assert getattr(make(saved=new), method)(new) is True


def test_apply_database_before_save_reloads_services(applier):
    make, _, _, reloads = applier
    assert make(saved={'database_local_path': 'old.db'}).apply_database({'database_local_path': 'new.db'}) is True
    assert reloads == [1]


def test_apply_sync_swapped_tuple_current(applier):
    """A2, как есть: при видимом изменении токена в sync_service.token попадает True."""
    make, sync, _, _ = applier
    make(saved={'YANDEX_TOKEN': 'old'}).apply_sync({'YANDEX_TOKEN': 'new'})
    assert sync.token is True


@pytest.mark.xfail(strict=True, reason=(
    "A2: _thec_update_key_config возвращает (changed, value), а apply_sync распаковывает "
    "как (value, changed) — в токен записывается True"
))
def test_apply_sync_sets_new_token(applier):
    make, sync, _, _ = applier
    make(saved={'YANDEX_TOKEN': 'old'}).apply_sync({'YANDEX_TOKEN': 'new'})
    assert sync.token == 'new'


def test_apply_photos_sets_private_attr(applier):
    """A3, как есть: путь к фото пишется в приватный атрибут сервиса."""
    make, _, photo, _ = applier
    make(saved={'PHOTOS_STORAGE_PATH': 'a'}).apply_photos_storage({'PHOTOS_STORAGE_PATH': 'b'})
    assert photo._storage_path == 'b'


def test_listener_of_live_object_called_and_removable(cfg_path):
    calls = []

    class Service:
        def reload(self):
            calls.append(1)

    s = Service()
    AppConfigManager.add_change_listener(s.reload)
    AppConfigManager.add_change_listener(s.reload)      # дубль не добавляется
    AppConfigManager.get_instance(config_path=cfg_path).save()
    AppConfigManager.remove_change_listener(s.reload)
    AppConfigManager.get_instance(config_path=cfg_path).save()
    assert calls == [1]
