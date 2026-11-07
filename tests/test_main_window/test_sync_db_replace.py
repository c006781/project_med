# tests/test_main_window/test_sync_db_replace.py
"""
Обмен файлом базы (``app.services.sync_service``): копии, замена, откат. Настоящие файлы во временной
папке, клиент Диска подменён, сеть не используется.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.exceptions.exceptions_all import (
    YandexDiskBackupError,
    YandexDiskError,
    YandexDiskTransferError,
)
from app.network.db_download import DbFreshness
from app.services import sync_service as ss
from tests.test_main_window.conftest import read_sqlite_value


# ---- число копий ----

@pytest.mark.parametrize('value, expected', [
    (5, 5),
    ('5', 5),
    (' 7 ', 7),
    (1, 1),
    (0, None),
    (-3, None),
    ('много', None),
    ('5.5', None),
    ('', None),
    (None, None),
    (True, None),
])
def test_parse_backup_count(value, expected):
    """Негодное значение и значения меньше 1 не становятся числом копий."""
    assert ss.parse_backup_count(value) == expected


# ---- уборка копий ----

def _copy_names(*stamps) -> list:
    """Имена копий clinic.db с такими метками."""
    return [f'clinic - 2026-11-0{stamp}.db' for stamp in stamps]


def _touch(folder, *names) -> None:
    """Создаёт пустые файлы."""
    for name in names:
        (folder / name).write_bytes(b'x')


def test_prune_keeps_newest_by_name_stamp(tmp_path):
    """Остаются самые новые по метке в имени."""
    names = _copy_names('1_10-00-00', '2_10-00-00', '3_10-00-00', '4_10-00-00')
    _touch(tmp_path, *names)
    removed = ss.prune_db_backups('/где-то/clinic.db', str(tmp_path), 2)
    assert sorted(os.path.basename(path) for path in removed) == names[:2]
    assert sorted(os.listdir(tmp_path)) == names[2:]


def test_prune_numbered_copies_of_one_second(tmp_path):
    """Копии одной секунды: номер в скобках новее копии без номера, порядок числовой."""
    plain = 'clinic - 2026-11-01_10-00-00.db'
    second = 'clinic - 2026-11-01_10-00-00 (2).db'
    tenth = 'clinic - 2026-11-01_10-00-00 (10).db'
    _touch(tmp_path, plain, second, tenth)
    ss.prune_db_backups('clinic.db', str(tmp_path), 1)
    assert os.listdir(tmp_path) == [tenth]


def test_prune_leaves_foreign_files(tmp_path):
    """Чужие файлы и копии других баз не удаляются, сколько бы их ни было."""
    mine = _copy_names('1_10-00-00', '2_10-00-00')
    foreign = [
        'clinic.db',
        'clinic - заметки.db',
        'clinic - 2026-11-01.db',
        'clinic - 2026-11-01_10-00-00.db.bak',
        'other - 2026-11-01_10-00-00.db',
        'clinic - 2026-11-01_10-00-00.sqlite',
        'отчёт.txt',
    ]
    _touch(tmp_path, *mine, *foreign)
    ss.prune_db_backups('clinic.db', str(tmp_path), 1)
    assert sorted(os.listdir(tmp_path)) == sorted([mine[1], *foreign])


def test_prune_does_not_touch_folder_with_copy_name(tmp_path):
    """Папка с именем копии не удаляется и не мешает."""
    (tmp_path / 'clinic - 2026-11-01_10-00-00.db').mkdir()
    _touch(tmp_path, *_copy_names('2_10-00-00', '3_10-00-00'))
    ss.prune_db_backups('clinic.db', str(tmp_path), 1)
    assert sorted(os.listdir(tmp_path)) == ['clinic - 2026-11-01_10-00-00.db', 'clinic - 2026-11-03_10-00-00.db']


def test_prune_regex_chars_in_db_name(tmp_path):
    """Имя базы со спецсимволами считается буквально."""
    _touch(tmp_path, 'a.b+c - 2026-11-01_10-00-00.db', 'a.b+c - 2026-11-02_10-00-00.db', 'axbbc - 2026-11-01_10-00-00.db')
    ss.prune_db_backups('a.b+c.db', str(tmp_path), 1)
    assert sorted(os.listdir(tmp_path)) == ['a.b+c - 2026-11-02_10-00-00.db', 'axbbc - 2026-11-01_10-00-00.db']


def test_prune_missing_folder_and_zero_keep(tmp_path):
    """Папки нет — пусто; число меньше 1 — ничего не удаляется."""
    assert ss.prune_db_backups('clinic.db', str(tmp_path / 'нет'), 3) == []
    _touch(tmp_path, *_copy_names('1_10-00-00'))
    assert ss.prune_db_backups('clinic.db', str(tmp_path), 0) == []
    assert len(os.listdir(tmp_path)) == 1


def test_prune_delete_failure_is_not_fatal(tmp_path, monkeypatch):
    """Копия занята: остальное продолжается, исключения нет."""
    names = _copy_names('1_10-00-00', '2_10-00-00', '3_10-00-00')
    _touch(tmp_path, *names)
    real_remove = os.remove

    def remove(path):
        if path.endswith(names[0]):
            raise PermissionError('занят')
        real_remove(path)

    monkeypatch.setattr(ss.os, 'remove', remove)
    removed = ss.prune_db_backups('clinic.db', str(tmp_path), 1)
    assert [os.path.basename(path) for path in removed] == [names[1]]


# ---- копия перед передачей ----

def test_backup_makes_copy_and_prunes(work_db, tmp_path):
    """Копия появляется, старые — по числу; это снимок базы, а не пустой файл."""
    backups = tmp_path / 'копии'
    backups.mkdir()
    _touch(backups, *_copy_names('1_10-00-00', '2_10-00-00', '3_10-00-00'))
    path = ss.backup_db_before_transfer(str(work_db), {'BACKUP_PATH': str(backups), 'BACKUP_COUNT': 2})
    assert read_sqlite_value(path) == 'local'
    assert len(os.listdir(backups)) == 2
    assert os.path.basename(path) in os.listdir(backups)


@pytest.mark.parametrize('count', ['непереводимая строка', 0, -1, None])
def test_backup_bad_count_deletes_nothing(work_db, tmp_path, count):
    """BACKUP_COUNT негоден: копия сделана, ничего не удалено."""
    backups = tmp_path / 'копии'
    backups.mkdir()
    names = _copy_names('1_10-00-00', '2_10-00-00', '3_10-00-00')
    _touch(backups, *names)
    ss.backup_db_before_transfer(str(work_db), {'BACKUP_PATH': str(backups), 'BACKUP_COUNT': count})
    assert set(names) < set(os.listdir(backups))
    assert len(os.listdir(backups)) == 4


def test_backup_no_local_nothing_pruned(tmp_path):
    """Рабочей базы нет: копии нет, старые копии на месте."""
    _touch(tmp_path, *_copy_names('1_10-00-00', '2_10-00-00'))
    path = ss.backup_db_before_transfer(str(tmp_path / 'clinic.db'), {'BACKUP_PATH': str(tmp_path), 'BACKUP_COUNT': 1})
    assert path is None
    assert len(os.listdir(tmp_path)) == 2


def test_backup_failure_raises(work_db, tmp_path):
    """Папку копий не создать: исключение, передачу начинать нельзя."""
    blocker = tmp_path / 'файл'
    blocker.write_bytes(b'x')
    with pytest.raises(YandexDiskBackupError):
        ss.backup_db_before_transfer(str(work_db), {'BACKUP_PATH': str(blocker / 'копии'), 'BACKUP_COUNT': 5})


def test_backup_empty_path_uses_default(work_db, tmp_path, monkeypatch):
    """Папка не задана: умолчание программы, относительно текущей папки."""
    monkeypatch.chdir(tmp_path)
    path = ss.backup_db_before_transfer(str(work_db), {'BACKUP_PATH': '', 'BACKUP_COUNT': 5})
    assert os.path.abspath(path).startswith(str(tmp_path / 'backups'))


# ---- временные файлы ----

def test_stale_parts_removed_only_for_this_db(tmp_path):
    """Убираются только недокачанные файлы этой базы."""
    local = tmp_path / 'clinic.db'
    _touch(
        tmp_path,
        'clinic.db',
        'clinic.db.download-abc.part',
        'clinic.db.download-previous.part',
        'other.db.download-abc.part',
        'clinic.db.part',
        'clinic.db-journal',
    )
    removed = ss.remove_stale_downloads(str(local))
    assert len(removed) == 2
    assert sorted(os.listdir(tmp_path)) == sorted([
        'clinic.db',
        'other.db.download-abc.part',
        'clinic.db.part',
        'clinic.db-journal',
    ])


def test_stale_parts_special_chars_in_path(tmp_path):
    """Спецсимволы glob в пути не мешают и не расширяют выбор."""
    folder = tmp_path / 'папка [1]'
    folder.mkdir()
    _touch(folder, 'clinic.db.download-1.part')
    assert len(ss.remove_stale_downloads(str(folder / 'clinic.db'))) == 1


# ---- замена ----

def _result(temp, local, freshness=DbFreshness.REMOTE_NEWER, warnings=()) -> SimpleNamespace:
    """Итог скачивания: настоящий по полям, которые нужны замене."""
    def discard():
        if os.path.exists(temp):
            os.remove(temp)
            return True
        return False

    return SimpleNamespace(
        temp_path       =   str(temp),                                  # временный
        local_path      =   str(local),                                 # рабочая
        discard         =   discard,                                    # отказ
        warnings        =   warnings,                                   # предупреждения
        needs_replace   =   freshness is not DbFreshness.SAME,          # нужна замена
        local_newer     =   freshness is DbFreshness.LOCAL_NEWER,       # локальная новее
        remote          =   SimpleNamespace(path='/clinic.db'),         # на Диске
    )


@pytest.fixture
def steps(monkeypatch):
    """Записывает закрытие и открытие базы вместо настоящих."""
    log = []
    import app.dependencies as deps
    monkeypatch.setattr(deps, 'close_db', lambda: log.append('close'))
    monkeypatch.setattr(ss, '_reopen_app_db', lambda: log.append('open'))
    return log


def test_install_order_and_cleanup(tmp_path, steps, monkeypatch):
    """Подключения закрыты до замены, журналы прежней убраны, открытие последним."""
    local = tmp_path / 'clinic.db'
    temp = tmp_path / 'clinic.db.download-1.part'
    local.write_bytes(b'old')
    temp.write_bytes(b'new')
    for suffix in ('-journal', '-wal', '-shm'):
        (tmp_path / f'clinic.db{suffix}').write_bytes(b'j')
    real_replace = os.replace

    def replace(src, dst):
        steps.append('replace')
        real_replace(src, dst)

    monkeypatch.setattr(ss.os, 'replace', replace)
    ss.install_checked_download(_result(temp, local))
    assert steps == ['close', 'replace', 'open']
    assert os.listdir(tmp_path) == ['clinic.db']
    assert local.read_bytes() == b'new'


def test_install_no_previous_local(tmp_path, steps):
    """Рабочей базы не было: файл просто появляется."""
    local = tmp_path / 'clinic.db'
    temp = tmp_path / 't.part'
    temp.write_bytes(b'new')
    ss.install_checked_download(_result(temp, local))
    assert local.read_bytes() == b'new'
    assert os.listdir(tmp_path) == ['clinic.db']


def test_install_replace_failure_keeps_old(tmp_path, steps, monkeypatch):
    """Windows, файл занят: рабочая база прежняя и открыта, временного нет, ошибка понятна."""
    local = tmp_path / 'clinic.db'
    temp = tmp_path / 't.part'
    local.write_bytes(b'old')
    temp.write_bytes(b'new')

    def replace(src, dst):
        raise PermissionError('файл занят')

    monkeypatch.setattr(ss.os, 'replace', replace)
    with pytest.raises(YandexDiskTransferError) as caught:
        ss.install_checked_download(_result(temp, local))
    assert 'файл занят' in str(caught.value)
    assert local.read_bytes() == b'old'
    assert os.listdir(tmp_path) == ['clinic.db']
    assert steps == ['close', 'open']


def test_install_partial_previous_never_replaces_work_db(tmp_path, steps, monkeypatch):
    """Нет места при копии прежней версии: неполная копия не попадает на место рабочей базы."""
    local = tmp_path / 'clinic.db'
    temp = tmp_path / 't.part'
    local.write_bytes(b'old')
    temp.write_bytes(b'new')

    def copy2(src, dst):
        with open(dst, 'wb') as file:
            file.write(b'o')
        raise OSError('нет места')

    monkeypatch.setattr(ss.shutil, 'copy2', copy2)
    with pytest.raises(YandexDiskTransferError):
        ss.install_checked_download(_result(temp, local))
    assert local.read_bytes() == b'old'
    assert os.listdir(tmp_path) == ['clinic.db']


def test_install_sidecar_failure_restores_old(tmp_path, steps, monkeypatch):
    """Журнал прежней базы не убрать: чужой журнал не применится, прежний файл возвращён."""
    local = tmp_path / 'clinic.db'
    temp = tmp_path / 't.part'
    local.write_bytes(b'old')
    temp.write_bytes(b'new')
    real_remove = ss._remove_db_sidecars
    calls = []

    def sidecars(path):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError('журнал занят')
        real_remove(path)

    monkeypatch.setattr(ss, '_remove_db_sidecars', sidecars)
    with pytest.raises(YandexDiskTransferError):
        ss.install_checked_download(_result(temp, local))
    assert local.read_bytes() == b'old'


def test_install_new_db_does_not_open_restores_old(tmp_path, monkeypatch):
    """Скачанная база не открылась: прежняя возвращена и открыта снова."""
    import app.dependencies as deps
    local = tmp_path / 'clinic.db'
    temp = tmp_path / 't.part'
    local.write_bytes(b'old')
    temp.write_bytes(b'new')
    opened = []

    def reopen():
        opened.append(local.read_bytes())
        if len(opened) == 1:
            raise RuntimeError('база новее программы')

    monkeypatch.setattr(deps, 'close_db', lambda: None)
    monkeypatch.setattr(ss, '_reopen_app_db', reopen)
    with pytest.raises(YandexDiskTransferError) as caught:
        ss.install_checked_download(_result(temp, local))
    assert 'рабочая база возвращена' in str(caught.value)
    assert opened == [b'new', b'old']
    assert local.read_bytes() == b'old'
    assert os.listdir(tmp_path) == ['clinic.db']


# ---- download_sync: командная строка ----

@pytest.fixture
def service(work_db, tmp_path, monkeypatch, steps):
    """Сервис без чтения настроек: рабочая база и папка копий — временные."""
    from app.config.config_manager.manager import AppConfigManager
    monkeypatch.setattr(
        AppConfigManager,
        'get_instance',
        classmethod(lambda cls, *a, **k: {'BACKUP_PATH': str(tmp_path / 'копии'), 'BACKUP_COUNT': 5}),
    )
    instance = ss.SyncService.__new__(ss.SyncService)
    instance.token = 't'
    instance.remote_path = 'Папка'
    instance.local_path = str(work_db)
    instance.logger = MagicMock()
    return instance


def test_download_sync_replaces_with_backup(service, work_db, tmp_path, disk, steps):
    """Диск новее: копия прежней, рабочая заменена; путь на Диске дополнен именем файла."""
    assert service.download_sync() == 0
    assert read_sqlite_value(work_db) == 'remote'
    [copy] = os.listdir(tmp_path / 'копии')
    assert read_sqlite_value(tmp_path / 'копии' / copy) == 'local'
    assert steps == ['close', 'open']
    assert disk.client.download.call_args.args[0].endswith('Папка/clinic.db')


def test_download_sync_backup_before_network(service, tmp_path, disk):
    """Копия делается до начала скачивания."""
    seen = []
    disk.on_download = lambda: seen.append(os.listdir(tmp_path / 'копии'))
    service.download_sync()
    assert len(seen[0]) == 1


def test_download_sync_broken_transfer_keeps_db(service, work_db, tmp_path, disk, steps):
    """Обрыв посередине: рабочая база цела, временного файла нет, замены не было."""
    before = work_db.read_bytes()
    disk.fail_after = 100
    with pytest.raises(YandexDiskError):
        service.download_sync()
    assert work_db.read_bytes() == before
    assert os.listdir(work_db.parent) == ['clinic.db']
    assert steps == []


def test_download_sync_backup_failure_stops_before_network(service, work_db, tmp_path, disk, monkeypatch):
    """Копия не удалась: скачивание не начинается."""
    def fail(*args):
        raise YandexDiskBackupError('нет места', local_path='clinic.db')
    monkeypatch.setattr(ss, 'backup_local_db', fail)
    with pytest.raises(YandexDiskBackupError):
        service.download_sync()
    disk.client.download.assert_not_called()


def test_download_sync_local_newer_refuses(service, work_db, disk, steps):
    """Локальная новее: спросить некого, база не заменена, сообщение об этом."""
    os.utime(work_db)
    from datetime import datetime, timedelta, timezone
    disk.client.get_meta.return_value.modified = datetime.now(timezone.utc) - timedelta(days=1)
    before = work_db.read_bytes()
    with pytest.raises(YandexDiskError) as caught:
        service.download_sync()
    assert 'база не заменена' in str(caught.value)
    assert work_db.read_bytes() == before
    assert os.listdir(work_db.parent) == ['clinic.db']
    assert steps == []


def test_download_sync_local_newer_with_overwrite(service, work_db, disk, steps):
    """Разрешено затирать: база заменена."""
    os.utime(work_db)
    from datetime import datetime, timedelta, timezone
    disk.client.get_meta.return_value.modified = datetime.now(timezone.utc) - timedelta(days=1)
    assert service.download_sync(overwrite_newer=True) == 0
    assert read_sqlite_value(work_db) == 'remote'


def test_download_sync_same_content_no_replace(service, work_db, disk, steps):
    """Содержимое совпало: замены нет, временного файла нет."""
    disk.content = work_db.read_bytes()
    import hashlib
    disk.client.get_meta.return_value.size = len(disk.content)
    disk.client.get_meta.return_value.md5 = hashlib.md5(disk.content).hexdigest()
    assert service.download_sync() == 0
    assert steps == []
    assert os.listdir(work_db.parent) == ['clinic.db']


def test_upload_sync_backup_first(service, tmp_path, disk):
    """Перед выгрузкой — копия рабочей базы."""
    disk.client.exists.return_value = True
    seen = []
    disk.client.upload.side_effect = lambda *a, **k: seen.append(os.listdir(tmp_path / 'копии'))
    assert service.upload_sync() == 0
    assert len(seen[0]) == 1
