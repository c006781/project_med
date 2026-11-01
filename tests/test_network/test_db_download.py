# tests/test_network/test_db_download.py

"""
Тесты безопасного скачивания базы с Яндекс.Диска (``app.network.db_download``, ТД-1) и
исключений Яндекс.Диска (``app.exceptions`` ``YandexDisk*Error``).

Сеть не нужна: клиент ``yadisk.YaDisk`` подменяется (фикстура ``disk``); «файл на Диске» —
байты в памяти, ``download`` пишет их в путь, который ему передали. Все файлы — в
``tmp_path``.
"""

import doctest
import hashlib
import inspect
import os
import pickle
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QTimer
from yadisk.exceptions import (
    PathNotFoundError,
    UnauthorizedError,
    YaDiskConnectionError,
)

import app.exceptions as exceptions_package
import app.network as network_package
import app.network.db_download as db_module
import app.network.ya_dop as ya_module
from app.exceptions import (
    SyncError,
    YandexDiskBackupError,
    YandexDiskConnectionError,
    YandexDiskError,
    YandexDiskNotAFileError,
    YandexDiskNotFoundError,
    YandexDiskTokenError,
    YandexDiskTransferError,
    YandexDiskVerifyError,
)
from app.network.db_download import (
    CheckedDownload,
    DbFreshness,
    LocalFileInfo,
    RemoteFileInfo,
    backup_local_db,
    compare_freshness,
    file_md5,
    local_file_info,
    sqlite_file_problem,
    yadisk_download_db_checked,
    yadisk_remote_file_info,
    yadisk_server_response,
)
from app.network.thread_network import CheckedDownloadThread, DownloadThread, UploadThread


# ---------------------------------------------------------------------------
# Помощники
# ---------------------------------------------------------------------------

def _make_db(
    path  : str,          # куда записать базу
    value : str,          # значение в таблице (отличает базы друг от друга)
) -> bytes:
    """Создаёт базу SQLite с одной строкой ``value``; возвращает её байты."""
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE t (v TEXT)')
        connection.execute('INSERT INTO t VALUES (?)', (value,))
    connection.close()
    with open(path, 'rb') as file:
        return file.read()


def _db_bytes(
    tmp_path : Any,   # папка теста
    value    : str,   # значение в таблице
) -> bytes:
    """Байты исправной базы SQLite (создаётся во вспомогательной папке)."""
    folder = tmp_path / 'source'
    folder.mkdir(exist_ok=True)
    return _make_db(
        str(folder / f'{value}.db'),    # файл-источник
        value,                          # значение
    )


def _read_value(
    path : str,   # база
) -> str:
    """Значение из таблицы ``t`` базы."""
    connection = sqlite3.connect(path)
    try:
        return connection.execute('SELECT v FROM t').fetchone()[0]
    finally:
        connection.close()


def _md5(data: bytes) -> str:
    """MD5 байтов."""
    return hashlib.md5(data).hexdigest()


def _set_mtime(
    path   : str,        # файл
    moment : datetime,   # новая дата изменения
) -> None:
    """Ставит дату изменения файла."""
    stamp = moment.timestamp()
    os.utime(path, (stamp, stamp))


NOW = datetime.now(timezone.utc)


class FakeDisk:
    """
    Подменённый Яндекс.Диск: один файл ``content`` с метаданными ``meta``.

    ``download`` пишет ``written`` (по умолчанию — ``content``) в переданный путь; если задан
    ``fail_after`` — пишет только первые ``fail_after`` байт и бросает ``fail_with``.
    """

    def __init__(
        self,
        content : bytes,   # файл на Диске
    ) -> None:
        self.content = content
        self.written: Optional[bytes] = None
        self.fail_after: Optional[int] = None
        self.fail_with: BaseException = YaDiskConnectionError('Connection reset by peer')
        self.download_paths: List[str] = []
        self.client = MagicMock(name='YaDisk')
        self.client.check_token.return_value = True
        self.client.get_meta.return_value = SimpleNamespace(
            type        =   'file',                 # файл
            size        =   len(content),           # размер
            md5         =   _md5(content).upper(),  # регистр Диска не важен
            modified    =   NOW,                    # дата на Диске
        )
        self.client.download.side_effect = self._download

    def _download(
        self,
        src_path          : str,                       # путь на Диске
        dst_path          : str,                       # локальный путь
        progress_callback : Optional[Callable] = None,  # прогресс
    ) -> None:
        """Пишет байты файла (или их часть с ошибкой) в ``dst_path``."""
        self.download_paths.append(dst_path)
        data = self.content if self.written is None else self.written
        with open(dst_path, 'wb') as file:
            if self.fail_after is not None:
                file.write(data[:self.fail_after])
                file.flush()
                raise self.fail_with
            if progress_callback:
                progress_callback(len(data) // 2, len(data))
            file.write(data)
            if progress_callback:
                progress_callback(len(data), len(data))


@pytest.fixture
def work(tmp_path):
    """Папка с рабочей базой ``clinic.db`` (значение 'local', изменена час назад)."""
    folder = tmp_path / 'work'
    folder.mkdir()
    local = folder / 'clinic.db'
    _make_db(str(local), 'local')
    _set_mtime(str(local), NOW - timedelta(hours=1))
    return local


@pytest.fixture
def remote_bytes(tmp_path):
    """Байты базы «на Диске» (значение 'remote')."""
    return _db_bytes(tmp_path, 'remote')


@pytest.fixture
def disk(remote_bytes):
    """Подменённый клиент Яндекс.Диска с базой ``remote_bytes``."""
    fake = FakeDisk(remote_bytes)
    with patch.object(ya_module.yadisk, 'YaDisk', return_value=fake.client):
        yield fake


def _folder_files(folder: Any) -> List[str]:
    """Имена файлов в папке (по алфавиту)."""
    return sorted(os.listdir(folder))


def _download(
    work       : Any,                  # рабочая база
    backup_dir : Optional[str] = None, # папка копий
    **kwargs   : Any,                  # прочие параметры
) -> CheckedDownload:
    """Вызов безопасного скачивания с путями теста."""
    return yadisk_download_db_checked(
        ya_token        =   'token',            # токен
        ya_file_path    =   'Папка\\clinic.db', # путь на Диске (с '\\' — нормализуется)
        local_db_path   =   str(work),          # рабочая база
        backup_dir      =   backup_dir,         # копия
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Успешное скачивание
# ---------------------------------------------------------------------------

def test_success_temp_file_verified_work_db_untouched(disk, work, remote_bytes):
    """Успех: временный файл рядом — копия Диска; рабочая база не изменена."""
    before = work.read_bytes()
    result = _download(work)
    assert work.read_bytes() == before
    assert os.path.dirname(result.temp_path) == str(work.parent)
    assert os.path.basename(result.temp_path).startswith('clinic.db.download-')
    assert result.temp_path.endswith('.part')
    with open(result.temp_path, 'rb') as file:
        assert file.read() == remote_bytes
    assert _read_value(result.temp_path) == 'remote'
    assert result.remote.path == 'Папка/clinic.db'
    assert result.remote.md5 == _md5(remote_bytes)
    assert result.downloaded.size == len(remote_bytes)
    assert result.downloaded.md5 == _md5(remote_bytes)
    assert result.local.md5 == _md5(before)
    assert result.freshness is DbFreshness.REMOTE_NEWER
    assert result.needs_replace and not result.local_newer
    assert result.backup_path is None
    assert result.warnings == ()
    disk.client.download.assert_called_once()
    assert disk.client.download.call_args.args[0] == 'Папка/clinic.db'
    disk.client.close.assert_called_once()


def test_success_then_replace_like_window(disk, work):
    """Сценарий окна: os.replace временного поверх рабочей — рабочая становится базой Диска."""
    result = _download(work)
    os.replace(result.temp_path, result.local_path)
    assert _read_value(str(work)) == 'remote'
    assert result.discard() is False # файла уже нет — повторно безопасно


def test_progress_callback_called(disk, work, remote_bytes):
    """Прогресс передаётся библиотеке и доходит до вызывающего."""
    calls = []
    _download(
        work,
        progress_callback   =   lambda done, total: calls.append((done, total)),  # прогресс
    )
    assert calls[-1] == (len(remote_bytes), len(remote_bytes))


def test_discard_removes_temp(disk, work):
    """discard удаляет временный файл; второй вызов — False."""
    result = _download(work)
    assert result.discard() is True
    assert not os.path.exists(result.temp_path)
    assert result.discard() is False
    assert _folder_files(work.parent) == ['clinic.db']


def test_no_local_db_folder_created(disk, tmp_path):
    """Рабочей базы нет (и папки нет) — папка создаётся, NO_LOCAL, копии нет."""
    target = tmp_path / 'new' / 'deep' / 'clinic.db'
    result = _download(target, backup_dir=str(tmp_path / 'backup'))
    assert result.freshness is DbFreshness.NO_LOCAL
    assert result.local is None
    assert result.backup_path is None
    assert not (tmp_path / 'backup').exists()
    assert os.path.isfile(result.temp_path)
    assert not target.exists()


def test_disk_without_size_and_md5_warns(disk, work):
    """Диск не сообщил размер и MD5 — проверки пропущены, предупреждения есть."""
    disk.client.get_meta.return_value = SimpleNamespace(
        type        =   'file',     # файл
        size        =   None,       # нет размера
        md5         =   None,       # нет MD5
        modified    =   NOW,        # дата
    )
    result = _download(work)
    assert any('размер' in text for text in result.warnings)
    assert any('MD5' in text for text in result.warnings)


# ---------------------------------------------------------------------------
# Прерванное скачивание — рабочая база не тронута
# ---------------------------------------------------------------------------

def test_interrupted_download_keeps_work_db(disk, work):
    """Обрыв сети посередине: YandexDiskTransferError, рабочая база цела, временного нет."""
    before = work.read_bytes()
    disk.fail_after = 100
    with pytest.raises(YandexDiskTransferError) as info:
        _download(work)
    exc = info.value
    assert work.read_bytes() == before
    assert _read_value(str(work)) == 'local'
    assert _folder_files(work.parent) == ['clinic.db']
    assert not os.path.exists(disk.download_paths[0])
    assert disk.download_paths[0] != str(work)
    assert isinstance(exc.original, YaDiskConnectionError)
    assert 'связь прервалась' in exc.reason
    assert exc.remote_path == 'Папка/clinic.db'
    assert exc.local_path == disk.download_paths[0]
    assert exc.server_response == 'Connection reset by peer'
    assert 'Исходная ошибка: yadisk.exceptions.YaDiskConnectionError' in exc.log_text()
    disk.client.close.assert_called_once()


def test_interrupted_by_local_write_error(disk, work):
    """Ошибка записи временного файла (нет места) — TransferError с причиной записи."""
    disk.fail_after = 10
    disk.fail_with = OSError(28, 'No space left on device')
    with pytest.raises(YandexDiskTransferError) as info:
        _download(work)
    assert 'ошибка записи' in info.value.reason
    assert info.value.server_response is None
    assert _folder_files(work.parent) == ['clinic.db']


def test_cancel_from_progress_callback(disk, work):
    """Исключение в колбэке прогресса прерывает скачивание (отмена, И-1)."""
    class Cancelled(Exception):
        pass

    def cancel(done, total):
        raise Cancelled('отмена')

    with pytest.raises(YandexDiskTransferError) as info:
        _download(work, progress_callback=cancel)
    assert isinstance(info.value.original, Cancelled)
    assert _folder_files(work.parent) == ['clinic.db']


def test_download_server_error_mid_transfer(disk, work):
    """Ошибка сервера (файл удалили во время скачивания) — исключение, временного нет."""
    disk.fail_after = 0
    disk.fail_with = PathNotFoundError('DiskNotFoundError', 'Resource not found.')
    with pytest.raises(YandexDiskNotFoundError):
        _download(work)
    assert _folder_files(work.parent) == ['clinic.db']


# ---------------------------------------------------------------------------
# Проверка скачанного: размер, MD5, SQLite (И-2)
# ---------------------------------------------------------------------------

def test_verify_size_mismatch(disk, work, remote_bytes):
    """Скачано меньше, чем на Диске (без ошибки библиотеки) — VerifyError 'size'."""
    before = work.read_bytes()
    disk.written = remote_bytes[:len(remote_bytes) // 2]
    with pytest.raises(YandexDiskVerifyError) as info:
        _download(work)
    exc = info.value
    assert (exc.check, exc.expected, exc.actual) == ('size', len(remote_bytes), len(remote_bytes) // 2)
    assert exc.code == 5016
    assert 'не полностью' in str(exc)
    assert work.read_bytes() == before
    assert _folder_files(work.parent) == ['clinic.db']


def test_verify_md5_mismatch(disk, work, remote_bytes):
    """Тот же размер, другое содержимое — VerifyError 'md5'."""
    damaged = bytearray(remote_bytes)
    damaged[-1] ^= 0xFF
    disk.written = bytes(damaged)
    with pytest.raises(YandexDiskVerifyError) as info:
        _download(work)
    assert info.value.check == 'md5'
    assert info.value.expected == _md5(remote_bytes)
    assert info.value.actual == _md5(bytes(damaged))
    assert _folder_files(work.parent) == ['clinic.db']


def _meta_for(
    disk : FakeDisk,   # подменённый Диск
    data : bytes,      # что «лежит на Диске»
) -> None:
    """Подставляет файл и метаданные Диска под ``data``."""
    disk.content = data
    disk.client.get_meta.return_value = SimpleNamespace(
        type        =   'file',         # файл
        size        =   len(data),      # размер
        md5         =   _md5(data),     # MD5
        modified    =   NOW,            # дата
    )


def test_verify_not_sqlite(disk, work):
    """Размер и MD5 сошлись, но это не база SQLite — VerifyError 'sqlite'."""
    _meta_for(disk, b'<html>not a database</html>' * 10)
    with pytest.raises(YandexDiskVerifyError) as info:
        _download(work)
    assert info.value.check == 'sqlite'
    assert 'заголовка' in info.value.actual
    assert _folder_files(work.parent) == ['clinic.db']


def test_verify_corrupted_sqlite(disk, work, remote_bytes):
    """Заголовок SQLite есть, содержимое испорчено — VerifyError 'sqlite'."""
    damaged = remote_bytes[:100] + b'\x00' * 50 + b'\xff' * (len(remote_bytes) - 150)
    _meta_for(disk, damaged)
    with pytest.raises(YandexDiskVerifyError) as info:
        _download(work)
    assert info.value.check == 'sqlite'
    assert _folder_files(work.parent) == ['clinic.db']


def test_sqlite_file_problem_ok_and_readonly(tmp_path):
    """Исправная база (путь с кириллицей) — None; проверка файл не меняет и журнал не создаёт."""
    folder = tmp_path / 'Папка с базой'
    folder.mkdir()
    path = folder / 'база.db'
    _make_db(str(path), 'x')
    before = (path.read_bytes(), os.stat(path).st_mtime_ns)
    assert sqlite_file_problem(str(path)) is None
    assert (path.read_bytes(), os.stat(path).st_mtime_ns) == before
    assert _folder_files(folder) == ['база.db']


def test_sqlite_file_problem_empty_file(tmp_path):
    """Пустой файл — не база."""
    path = tmp_path / 'empty.db'
    path.write_bytes(b'')
    assert 'заголовка' in sqlite_file_problem(str(path))


# ---------------------------------------------------------------------------
# Какая база новее (И-3)
# ---------------------------------------------------------------------------

def test_local_newer_warns(disk, work):
    """Локальная изменена позже файла на Диске — LOCAL_NEWER и предупреждение первым."""
    _set_mtime(str(work), NOW + timedelta(hours=1))
    result = _download(work)
    assert result.freshness is DbFreshness.LOCAL_NEWER
    assert result.local_newer
    assert result.needs_replace # решение — за вызывающим
    assert 'затрёт локальные изменения' in result.warnings[0]
    assert os.path.isfile(result.temp_path)
    assert _read_value(str(work)) == 'local'


def test_same_content_not_newer_even_if_mtime_later(disk, work, remote_bytes):
    """Содержимое совпало (база скачана раньше и не правилась) — SAME, хотя дата позже."""
    work.write_bytes(remote_bytes)
    _set_mtime(str(work), NOW + timedelta(hours=1))
    result = _download(work)
    assert result.freshness is DbFreshness.SAME
    assert not result.needs_replace
    assert not result.local_newer
    assert result.warnings == ()


def test_unknown_when_disk_has_no_date(disk, work, remote_bytes):
    """Диск не сообщил дату — UNKNOWN и предупреждение."""
    disk.client.get_meta.return_value = SimpleNamespace(
        type        =   'file',                 # файл
        size        =   len(remote_bytes),      # размер
        md5         =   _md5(remote_bytes),     # MD5
        modified    =   None,                   # даты нет
    )
    result = _download(work)
    assert result.freshness is DbFreshness.UNKNOWN
    assert 'дату' in result.warnings[0]


@pytest.mark.parametrize(
    'local_md5, local_shift, remote_md5, remote_date, expected',
    [
        ('a', timedelta(hours=1), 'b', NOW, DbFreshness.LOCAL_NEWER),
        ('a', -timedelta(hours=1), 'b', NOW, DbFreshness.REMOTE_NEWER),
        ('a', timedelta(0), 'b', NOW, DbFreshness.REMOTE_NEWER),          # равные даты
        ('a', timedelta(hours=1), 'A', NOW, DbFreshness.SAME),            # регистр MD5
        ('a', timedelta(hours=1), None, NOW, DbFreshness.LOCAL_NEWER),    # без MD5 — по дате
        ('a', timedelta(hours=1), 'b', None, DbFreshness.UNKNOWN),
        ('a', timedelta(hours=1), 'b', NOW.replace(tzinfo=None), DbFreshness.LOCAL_NEWER),  # без пояса — UTC
    ],
)
def test_compare_freshness_table(local_md5, local_shift, remote_md5, remote_date, expected):
    """Таблица сравнения баз."""
    local = LocalFileInfo('clinic.db', 1, local_md5, NOW + local_shift)
    remote = RemoteFileInfo('/clinic.db', 1, remote_md5, remote_date)
    assert compare_freshness(local, remote) is expected


def test_compare_freshness_no_local():
    """Локальной нет — NO_LOCAL."""
    assert compare_freshness(None, RemoteFileInfo('/a', 1, 'x', NOW)) is DbFreshness.NO_LOCAL


def test_compare_freshness_timezones():
    """Даты в разных поясах сравниваются как моменты времени."""
    plus3 = timezone(timedelta(hours=3))
    local = LocalFileInfo('a', 1, 'a', datetime(2026, 1, 1, 12, 30, tzinfo=plus3)) # 09:30 UTC
    remote = RemoteFileInfo('/a', 1, 'b', datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
    assert compare_freshness(local, remote) is DbFreshness.REMOTE_NEWER


def test_local_file_info(tmp_path):
    """Сведения о файле: размер, MD5, дата в UTC."""
    path = tmp_path / 'a.bin'
    path.write_bytes(b'abc')
    info = local_file_info(str(path))
    assert (info.size, info.md5) == (3, _md5(b'abc'))
    assert info.modified.tzinfo is timezone.utc
    assert local_file_info(str(tmp_path)) is None # папка — не файл


def test_file_md5_small_chunks(tmp_path):
    """MD5 по блокам равен MD5 целиком."""
    path = tmp_path / 'a.bin'
    data = os.urandom(10_000)
    path.write_bytes(data)
    assert file_md5(str(path), chunk_size=7) == _md5(data)


# ---------------------------------------------------------------------------
# Резервная копия (И-4)
# ---------------------------------------------------------------------------

def test_backup_made_with_download(disk, work, tmp_path):
    """backup_dir задан — копия рабочей базы в папке (создаётся), по имени с меткой."""
    backup_dir = tmp_path / 'backup' / 'db'
    result = _download(work, backup_dir=str(backup_dir))
    assert result.backup_path is not None
    assert os.path.dirname(result.backup_path) == str(backup_dir)
    name = os.path.basename(result.backup_path)
    assert name.startswith('clinic - ') and name.endswith('.db')
    assert _read_value(result.backup_path) == 'local'
    assert _read_value(str(work)) == 'local'


def test_backup_never_overwrites(work, tmp_path):
    """Две копии подряд (в ту же секунду) — разные файлы, обе целы."""
    backup_dir = str(tmp_path / 'backup')
    first = backup_local_db(str(work), backup_dir)
    second = backup_local_db(str(work), backup_dir)
    assert first != second
    assert _read_value(first) == _read_value(second) == 'local'
    assert len(os.listdir(backup_dir)) == 2


def test_backup_consistent_with_open_wal_connection(tmp_path):
    """База открыта в режиме WAL, свежие данные — в -wal: копия их содержит."""
    path = tmp_path / 'clinic.db'
    connection = sqlite3.connect(str(path))
    try:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA wal_autocheckpoint=0')
        connection.execute('CREATE TABLE t (v TEXT)')
        connection.execute("INSERT INTO t VALUES ('wal')")
        connection.commit()
        copy = backup_local_db(str(path), str(tmp_path / 'backup'))
    finally:
        connection.close()
    assert _read_value(copy) == 'wal'


def test_backup_non_sqlite_copied_as_is(disk, tmp_path):
    """Рабочая база — не SQLite: копия побайтно, предупреждение в итоге."""
    folder = tmp_path / 'work'
    folder.mkdir()
    local = folder / 'clinic.db'
    local.write_bytes(b'broken database bytes')
    _set_mtime(str(local), NOW - timedelta(hours=1))
    result = _download(local, backup_dir=str(tmp_path / 'backup'))
    with open(result.backup_path, 'rb') as file:
        assert file.read() == b'broken database bytes'
    assert any('побайтно' in text for text in result.warnings)


def test_backup_corrupted_sqlite_copied_as_is(tmp_path):
    """Заголовок SQLite есть, база испорчена — копия побайтно, без ошибки."""
    path = tmp_path / 'clinic.db'
    data = b'SQLite format 3\x00' + b'\xff' * 2000
    path.write_bytes(data)
    copy = backup_local_db(str(path), str(tmp_path / 'backup'))
    with open(copy, 'rb') as file:
        assert file.read() == data


def test_backup_failure_raises_and_cleans(disk, work, tmp_path):
    """Папку копий не создать (на её месте файл) — BackupError, временный удалён."""
    blocker = tmp_path / 'backup'
    blocker.write_bytes(b'file, not folder')
    with pytest.raises(YandexDiskBackupError) as info:
        _download(work, backup_dir=str(blocker))
    exc = info.value
    assert exc.code == 5017
    assert exc.local_path == str(work)
    assert exc.details['папка копий'] == str(blocker)
    assert isinstance(exc.original, OSError)
    assert _folder_files(work.parent) == ['clinic.db']
    assert _read_value(str(work)) == 'local'


def test_backup_no_local_returns_none(tmp_path):
    """Рабочей базы нет — копии нет, папка не создаётся."""
    assert backup_local_db(str(tmp_path / 'none.db'), str(tmp_path / 'backup')) is None
    assert not (tmp_path / 'backup').exists()


# ---------------------------------------------------------------------------
# Токен и сведения о файле на Диске
# ---------------------------------------------------------------------------

def test_invalid_token(disk, work):
    """Токен недействителен — YandexDiskTokenError, скачивания нет."""
    disk.client.check_token.return_value = False
    with pytest.raises(YandexDiskTokenError) as info:
        _download(work)
    assert info.value.code == 5011
    disk.client.download.assert_not_called()
    disk.client.close.assert_called_once()
    assert _folder_files(work.parent) == ['clinic.db']


def test_no_network_on_token_check(disk, work):
    """Нет сети при проверке токена — YandexDiskConnectionError с исходной ошибкой."""
    disk.client.check_token.side_effect = YaDiskConnectionError('нет сети')
    with pytest.raises(YandexDiskConnectionError) as info:
        _download(work)
    assert info.value.operation == 'проверка токена'
    assert isinstance(info.value.original, YaDiskConnectionError)


def test_remote_not_found(disk, work):
    """Файла на Диске нет — NotFoundError с ответом сервера."""
    disk.client.get_meta.side_effect = PathNotFoundError('DiskNotFoundError', 'Resource not found.')
    with pytest.raises(YandexDiskNotFoundError) as info:
        _download(work)
    exc = info.value
    assert exc.code == 5013
    assert exc.server_response == 'DiskNotFoundError; Resource not found.'
    assert 'ответ сервера=DiskNotFoundError' in exc.log_text()
    disk.client.download.assert_not_called()


def test_remote_is_folder(disk, work):
    """По пути — папка — NotAFileError."""
    disk.client.get_meta.return_value = SimpleNamespace(type='dir', size=None, md5=None, modified=NOW)
    with pytest.raises(YandexDiskNotAFileError) as info:
        _download(work)
    assert info.value.details['тип ресурса'] == 'dir'
    disk.client.download.assert_not_called()


def test_meta_unauthorized(disk, work):
    """get_meta: токен не принят — TokenError."""
    disk.client.get_meta.side_effect = UnauthorizedError('UnauthorizedError', 'Unauthorized')
    with pytest.raises(YandexDiskTokenError):
        _download(work)


def test_meta_no_network(disk, work):
    """get_meta: нет сети — ConnectionError (до скачивания)."""
    disk.client.get_meta.side_effect = YaDiskConnectionError('timed out')
    with pytest.raises(YandexDiskConnectionError) as info:
        _download(work)
    assert info.value.operation == 'получение сведений о файле'


def test_remote_file_info(disk, remote_bytes):
    """yadisk_remote_file_info — сведения Диска (MD5 строчными)."""
    info = yadisk_remote_file_info('token', 'Папка/clinic.db')
    assert info == RemoteFileInfo('Папка/clinic.db', len(remote_bytes), _md5(remote_bytes), NOW)
    disk.client.close.assert_called_once()


def test_server_response_with_http_status():
    """Ответ сервера с HTTP-кодом."""
    exc = PathNotFoundError('DiskNotFoundError', 'Resource not found.', response=SimpleNamespace(status=404))
    assert yadisk_server_response(exc) == 'DiskNotFoundError; HTTP 404; Resource not found.'


# ---------------------------------------------------------------------------
# Исключения Яндекс.Диска (app.exceptions)
# ---------------------------------------------------------------------------

YANDEX_CLASSES = [
    YandexDiskError, YandexDiskTokenError, YandexDiskConnectionError, YandexDiskNotFoundError,
    YandexDiskNotAFileError, YandexDiskTransferError, YandexDiskBackupError,
]


def test_exceptions_exported_and_hierarchy():
    """Классы — в __all__ пакета, наследники SyncError; коды разные (5010–5017)."""
    classes = YANDEX_CLASSES + [YandexDiskVerifyError]
    for cls in classes:
        assert cls.__name__ in exceptions_package.__all__
        assert issubclass(cls, YandexDiskError) and issubclass(cls, SyncError)
    codes = [cls.default_code for cls in classes]
    assert sorted(codes) == list(range(5010, 5018))


@pytest.mark.parametrize('cls', YANDEX_CLASSES)
def test_exception_text_details_pickle(cls):
    """Текст пользователю, подробности, исходная ошибка, pickle — у каждого класса."""
    original = YaDiskConnectionError('reset')
    exc = cls(
        'причина',                                  # причина
        remote_path     =   '/clinic.db',           # файл на Диске
        local_path      =   'clinic.db.part',       # локальный
        server_response =   'HTTP 500',             # ответ сервера
        details         =   {'попытка': 2},         # прочее
        original        =   original,               # исходная ошибка
    )
    assert str(exc) == f"[{cls.default_code}] Яндекс.Диск, {cls.default_operation} «/clinic.db»: причина"
    assert exc.details == {
        'операция': cls.default_operation,
        'файл на Диске': '/clinic.db',
        'локальный файл': 'clinic.db.part',
        'ответ сервера': 'HTTP 500',
        'попытка': 2,
    }
    assert exc.original is original
    log = exc.log_text()
    assert 'Подробности: операция=' in log and 'Исходная ошибка: yadisk.exceptions.YaDiskConnectionError: reset' in log
    copied = pickle.loads(pickle.dumps(exc))
    assert type(copied) is cls
    assert str(copied) == str(exc)
    assert copied.remote_path == '/clinic.db' and copied.server_response == 'HTTP 500'
    assert copied.original_text == 'yadisk.exceptions.YaDiskConnectionError: reset'


def test_exception_minimal_and_text_details():
    """Без пути и ответа сервера; подробности строкой — ключ 'прочее'; свой код и операция."""
    exc = YandexDiskError('сбой', details='попытка 3', operation='загрузка', code=5099)
    assert str(exc) == '[5099] Яндекс.Диск, загрузка: сбой'
    assert exc.details == {'операция': 'загрузка', 'прочее': 'попытка 3'}
    assert exc.original is None


def test_verify_error_fields_and_pickle():
    """VerifyError: check / expected / actual — в атрибутах, подробностях и после pickle."""
    exc = YandexDiskVerifyError('md5', 'не совпал', expected='aa', actual='bb', details={'x': 1})
    assert exc.details == {
        'операция': 'проверка скачанного файла', 'проверка': 'md5',
        'ожидалось': 'aa', 'получено': 'bb', 'x': 1,
    }
    copied = pickle.loads(pickle.dumps(exc))
    assert (copied.check, copied.expected, copied.actual) == ('md5', 'aa', 'bb')


def test_import_star_does_not_shadow_builtins():
    """import * пакета исключений не перекрывает встроенный ConnectionError."""
    namespace: Dict[str, Any] = {}
    exec('from app.exceptions import *', namespace)
    assert 'ConnectionError' not in namespace
    assert 'YandexDiskConnectionError' in namespace


# ---------------------------------------------------------------------------
# Поток CheckedDownloadThread
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def qt_app():
    """QCoreApplication для настоящего запуска потока."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def _run_checked_thread(
    app    : QCoreApplication,        # приложение Qt
    thread : CheckedDownloadThread,   # поток
) -> Dict[str, list]:
    """Запускает поток, ждёт; возвращает все сигналы по именам."""
    got: Dict[str, list] = {'finished': [], 'error': [], 'downloaded': [], 'failed': [], 'order': []}
    thread.finished.connect(lambda code: (got['finished'].append(code), got['order'].append('finished')))
    thread.error.connect(lambda text: (got['error'].append(text), got['order'].append('error')))
    thread.downloaded.connect(lambda res: (got['downloaded'].append(res), got['order'].append('downloaded')))
    thread.failed.connect(lambda exc: (got['failed'].append(exc), got['order'].append('failed')))
    thread.start()
    thread.wait(5000)
    QTimer.singleShot(50, app.quit) # доставить сигналы из потока
    app.exec()
    return got


def test_thread_success(qt_app, disk, work, tmp_path):
    """Успех: downloaded(итог), затем finished(0); error нет."""
    thread = CheckedDownloadThread('t', 'Папка/clinic.db', str(work), backup_dir=str(tmp_path / 'b'))
    got = _run_checked_thread(qt_app, thread)
    assert got['order'] == ['downloaded', 'finished']
    assert got['finished'] == [0]
    result = got['downloaded'][0]
    assert isinstance(result, CheckedDownload)
    assert result is thread.result
    assert os.path.isfile(result.temp_path) and os.path.isfile(result.backup_path)
    result.discard()


def test_thread_failure(qt_app, disk, work):
    """Ошибка: failed(исключение), затем error(текст); finished нет, рабочая база цела."""
    disk.fail_after = 50
    thread = CheckedDownloadThread('t', 'Папка/clinic.db', str(work))
    got = _run_checked_thread(qt_app, thread)
    assert got['order'] == ['failed', 'error']
    assert isinstance(got['failed'][0], YandexDiskTransferError)
    assert got['error'][0] == str(got['failed'][0])
    assert thread.result is None
    assert _folder_files(work.parent) == ['clinic.db']


# ---------------------------------------------------------------------------
# Совместимость: прежний API не изменён
# ---------------------------------------------------------------------------

def test_old_api_signatures_unchanged():
    """Сигнатуры прежних функций и потоков — как до безопасного скачивания."""
    assert list(inspect.signature(ya_module.yadisk_download_file).parameters) == [
        'ya_token', 'ya_file_path', 'local_file_path', 'if_err', 'progress_callback',
    ]
    assert list(inspect.signature(ya_module.yadisk_upload_file).parameters) == [
        'ya_token', 'local_file_path', 'ya_file_path', 'if_err', 'progress_callback', 'overwrite',
    ]
    assert list(inspect.signature(DownloadThread.__init__).parameters) == [
        'self', 'token', 'remote_path', 'local_path', 'parent',
    ]
    assert list(inspect.signature(UploadThread.__init__).parameters) == [
        'self', 'token', 'local_path', 'remote_path', 'parent', 'overwrite',
    ]


def test_new_api_exported():
    """Новое API доступно из app.network."""
    for name in ('yadisk_download_db_checked', 'CheckedDownload', 'CheckedDownloadThread',
                 'DbFreshness', 'backup_local_db', 'compare_freshness'):
        assert name in network_package.__all__
        assert hasattr(network_package, name)


def test_doctests_db_download():
    """Примеры (>>>) в докстрингах модуля верны."""
    result = doctest.testmod(db_module, optionflags=doctest.ELLIPSIS)
    assert result.failed == 0
    assert result.attempted > 0
