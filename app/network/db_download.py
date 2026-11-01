# app/network/db_download.py
"""
Безопасное скачивание файла базы с Яндекс.Диска — сетевая часть (ТД-1, вариант А).

Прежнее :func:`app.network.ya_dop.yadisk_download_file` пишет прямо в указанный файл: обрыв
сети посередине оставляет рабочую базу испорченной. Здесь рабочий файл **не трогается**:

1. файл скачивается во **временный** рядом с рабочим (та же папка — тот же диск, поэтому
   замена потом — атомарный ``os.replace``);
2. временный **проверяется**: размер и MD5 — со сведениями Диска (И-2), открывается ли он как
   база SQLite (``PRAGMA quick_check``);
3. **какая база новее** (И-3): MD5 и дата изменения локальной базы против даты на Диске;
   локальная новее — предупреждение в результате (затирать или нет — решает вызывающий);
4. **резервная копия** локальной базы (И-4) — в папку из параметра (например, ``BACKUP_PATH``
   настроек; настройки здесь не читаются), через backup-API SQLite.

Любая ошибка — исключение ``YandexDisk*Error`` из ``app.exceptions`` (подробное: что делали,
файл, ответ сервера, исходная ошибка); временный файл при ошибке удаляется. Успех —
:class:`CheckedDownload`: путь проверенного временного файла и все сведения.

**Что делать вызывающему (окно, М18) с результатом:**

* ``result.freshness is DbFreshness.LOCAL_NEWER`` — спросить пользователя (текст —
  ``result.warnings``); отказ — ``result.discard()`` (временный файл удаляется, рабочая база
  как была);
* ``DbFreshness.SAME`` — замена не нужна: ``result.discard()``;
* иначе — закрыть подключения к базе (``app.dependencies.close_db()``), заменить
  ``os.replace(result.temp_path, result.local_path)``, убрать старые ``-journal`` / ``-wal`` /
  ``-shm`` рядом с рабочим файлом, если они есть, открыть заново (``reopen_db()``,
  ``reload_config()`` сервисов). Резервная копия уже сделана (``result.backup_path``), если
  передан ``backup_dir``; без него — :func:`backup_local_db` вызывающим после закрытия
  подключений.

Example:
    >>> result = yadisk_download_db_checked(      # doctest: +SKIP
    ...     ya_token        =   'y0_...',          # токен из настроек
    ...     ya_file_path    =   'Папка/clinic.db', # файл на Диске
    ...     local_db_path   =   './clinic.db',     # рабочая база (не меняется)
    ...     backup_dir      =   './backup',        # папка резервных копий
    ... )
    >>> result.freshness, result.backup_path      # doctest: +SKIP
    (<DbFreshness.REMOTE_NEWER: 'remote_newer'>, 'backup/clinic - 2026-11-01_12-00-00.db')
"""

# Стандартные библиотеки Python
import hashlib
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Tuple

# Сторонние библиотеки
from yadisk.exceptions import (
    NotFoundError,
    RequestError,
    UnauthorizedError,
    YaDiskError,
)

# Модули проекта
from app.exceptions import (
    YandexDiskBackupError,
    YandexDiskConnectionError,
    YandexDiskError,
    YandexDiskNotAFileError,
    YandexDiskNotFoundError,
    YandexDiskTokenError,
    YandexDiskTransferError,
    YandexDiskVerifyError,
)
from app.network.ya_dop import ProgressCallback, _open_client, normalize_remote_path

# Первые 16 байт любого файла базы SQLite 3
SQLITE_HEADER: bytes = b'SQLite format 3\x00'

# Размер блока при подсчёте MD5 (файл базы не читается в память целиком)
_MD5_CHUNK: int = 1024 * 1024

# Операции — в тексте и подробностях исключений
_OP_TOKEN = 'проверка токена'
_OP_META = 'получение сведений о файле'
_OP_DOWNLOAD = 'скачивание'


class DbFreshness(str, Enum):
    """
    Какая база новее — локальная или на Диске (И-3).

    Attributes:
        NO_LOCAL: Локальной базы нет — затирать нечего.
        SAME: Содержимое совпадает (MD5) — замена не нужна.
        REMOTE_NEWER: На Диске новее (или даты равны) — обычное скачивание.
        LOCAL_NEWER: Локальная изменена позже файла на Диске — скачивание затрёт эти правки.
        UNKNOWN: Дата на Диске неизвестна — сравнить нельзя.

    Example:
        >>> DbFreshness('local_newer') is DbFreshness.LOCAL_NEWER
        True
        >>> DbFreshness.LOCAL_NEWER == 'local_newer'
        True
    """

    NO_LOCAL = 'no_local'
    SAME = 'same'
    REMOTE_NEWER = 'remote_newer'
    LOCAL_NEWER = 'local_newer'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class RemoteFileInfo:
    """
    Сведения о файле на Яндекс.Диске (из ``get_meta``).

    Attributes:
        path     : (str) Путь на Диске (нормализованный).
        size     : (int/None) Размер в байтах; None — Диск не сообщил.
        md5      : (str/None) MD5 (строчные шестнадцатеричные); None — Диск не сообщил.
        modified : (datetime/None) Дата изменения (с часовым поясом); None — Диск не сообщил.

    Example:
        >>> RemoteFileInfo('/clinic.db', 4, 'abc', None).size
        4
    """

    path     : str                  # путь на Диске
    size     : Optional[int]        # размер, байт
    md5      : Optional[str]        # MD5
    modified : Optional[datetime]   # дата изменения


@dataclass(frozen=True)
class LocalFileInfo:
    """
    Сведения о локальном файле: размер, MD5, дата изменения.

    Attributes:
        path     : (str) Путь.
        size     : (int) Размер в байтах.
        md5      : (str) MD5 (строчные шестнадцатеричные).
        modified : (datetime) Дата изменения (UTC, с часовым поясом).

    Example:
        >>> from datetime import datetime, timezone
        >>> LocalFileInfo('clinic.db', 4, 'abc', datetime(2026, 1, 1, tzinfo=timezone.utc)).md5
        'abc'
    """

    path     : str        # путь
    size     : int        # размер, байт
    md5      : str        # MD5
    modified : datetime   # дата изменения (UTC)


@dataclass(frozen=True)
class CheckedDownload:
    """
    Итог безопасного скачивания: проверенный временный файл и сведения для решения.

    Рабочая база (``local_path``) не изменена. Что делать дальше — описание модуля.

    Attributes:
        temp_path   : (str) Скачанный и проверенный временный файл (рядом с рабочим).
        local_path  : (str) Рабочая база (не тронута).
        remote      : (RemoteFileInfo) Файл на Диске.
        downloaded  : (LocalFileInfo) Временный файл: размер, MD5 (совпали с Диском, если
            Диск их сообщил), дата скачивания.
        local       : (LocalFileInfo/None) Рабочая база до скачивания; None — её не было.
        freshness   : (DbFreshness) Какая база новее.
        backup_path : (str/None) Резервная копия рабочей базы; None — не делалась (нет
            ``backup_dir`` или нет рабочей базы).
        warnings    : (Tuple[str, ...]) Предупреждения для пользователя (локальная новее,
            Диск не сообщил MD5, рабочая база — не SQLite …).

    Example:
        >>> from datetime import datetime, timezone
        >>> when = datetime(2026, 1, 1, tzinfo=timezone.utc)
        >>> result = CheckedDownload(
        ...     temp_path   =   'clinic.db.download-1.part',                  # временный
        ...     local_path  =   'clinic.db',                                  # рабочая
        ...     remote      =   RemoteFileInfo('/clinic.db', 4, 'abc', when), # на Диске
        ...     downloaded  =   LocalFileInfo('t.part', 4, 'abc', when),      # скачанный
        ...     local       =   None,                                       # рабочей не было
        ...     freshness   =   DbFreshness.NO_LOCAL,                         # затирать нечего
        ...     backup_path =   None,                                         # копии нет
        ...     warnings    =   (),                                           # без предупреждений
        ... )
        >>> (result.local_newer, result.needs_replace)
        (False, True)
    """

    temp_path   : str                       # проверенный временный файл
    local_path  : str                       # рабочая база (не тронута)
    remote      : RemoteFileInfo            # файл на Диске
    downloaded  : LocalFileInfo             # временный файл
    local       : Optional[LocalFileInfo]   # рабочая база до скачивания
    freshness   : DbFreshness               # какая новее
    backup_path : Optional[str]             # резервная копия рабочей базы
    warnings    : Tuple[str, ...]           # предупреждения пользователю

    @property
    def local_newer(self) -> bool: # локальная база новее файла на Диске
        """
        Признак «локальная база новее» — скачивание затрёт её правки (И-3).

        Returns:
            (bool) True — ``freshness`` равно ``LOCAL_NEWER``.

        Example:
            >>> CheckedDownload('t', 'l', None, None, None, DbFreshness.LOCAL_NEWER, None, ()).local_newer
            True
        """
        return self.freshness is DbFreshness.LOCAL_NEWER

    @property
    def needs_replace(self) -> bool: # нужна ли замена рабочей базы
        """
        Нужна ли замена рабочей базы: нет, если содержимое совпадает (``SAME``).

        Решение при ``LOCAL_NEWER`` за вызывающим — здесь оно не учитывается.

        Returns:
            (bool) False — только при ``SAME``.

        Example:
            >>> CheckedDownload('t', 'l', None, None, None, DbFreshness.SAME, None, ()).needs_replace
            False
        """
        return self.freshness is not DbFreshness.SAME

    def discard(self) -> bool: # удаление временного файла (отказ от замены)
        """
        Удаляет временный файл — когда замену решили не делать (или она уже не нужна).

        Повторный вызов и вызов после ``os.replace`` безопасны (файла уже нет).

        Returns:
            (bool) True — файл удалён; False — его уже не было.

        Raises:
            OSError: Файл есть, но удалить его не удалось (занят другой программой).

        Example:
            >>> result.discard()   # doctest: +SKIP
            True
        """
        try:
            os.remove(self.temp_path)
        except FileNotFoundError:
            return False
        return True


# ----------------------------------------------------------------------------------------
# Локальные файлы: MD5, сведения, проверка SQLite, резервная копия
# ----------------------------------------------------------------------------------------

def file_md5(
    path       : str,               # файл
    chunk_size : int = _MD5_CHUNK,  # размер блока чтения, байт
) -> str: # MD5 файла
    """
    Считает MD5 файла блоками (файл базы не читается в память целиком).

    Args:
        path       : (str) Файл.
        chunk_size : (int) Размер блока чтения, байт.

    Returns:
        (str) MD5 — строчные шестнадцатеричные, как ``md5`` у Яндекс.Диска.

    Raises:
        OSError: Файл не читается.

    Example:
        >>> import tempfile, os
        >>> with tempfile.NamedTemporaryFile(delete=False) as tmp:
        ...     _ = tmp.write(b'abc')
        >>> file_md5(tmp.name)
        '900150983cd24fb0d6963f7d28e17f72'
        >>> os.remove(tmp.name)
    """
    digest = hashlib.md5()
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(chunk_size), b''):
            digest.update(chunk)
    return digest.hexdigest()


def local_file_info(
    path : str,   # файл
) -> Optional[LocalFileInfo]: # размер, MD5 и дата изменения файла
    """
    Возвращает сведения о локальном файле или None, если файла нет.

    Дата изменения — из ``os.stat`` (``st_mtime``), в UTC с часовым поясом: так её можно
    сравнивать с датой Яндекс.Диска.

    Args:
        path : (str) Файл.

    Returns:
        (LocalFileInfo/None) Сведения; None — файла нет (или это папка).

    Raises:
        OSError: Файл есть, но не читается.

    Example:
        >>> local_file_info('нет-такого-файла.db') is None
        True
    """
    if not os.path.isfile(path):
        return None
    stat = os.stat(path)
    modified = datetime.fromtimestamp(
        stat.st_mtime,              # секунды от начала эпохи
        tz  =   timezone.utc,       # в UTC — сравнимо с датой Диска
    )
    return LocalFileInfo(
        path        =   path,               # путь
        size        =   stat.st_size,       # размер
        md5         =   file_md5(path),     # MD5
        modified    =   modified,           # дата изменения
    )


def has_sqlite_header(
    path : str,   # файл
) -> bool: # начинается ли файл с заголовка SQLite
    """
    Проверяет, что файл начинается с заголовка SQLite 3 (``SQLite format 3\\0``).

    Быстрая проверка без открытия базы; пустой и нечитаемый файл — ``False``.

    Args:
        path : (str) Файл.

    Returns:
        (bool) True — заголовок SQLite.

    Example:
        >>> has_sqlite_header('нет-такого-файла.db')
        False
    """
    try:
        with open(path, 'rb') as file:
            return file.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def sqlite_file_problem(
    path : str,   # проверяемый файл
) -> Optional[str]: # что не так с файлом базы (None — всё в порядке)
    """
    Проверяет, что файл — исправная база SQLite; возвращает текст проблемы или None.

    Порядок: заголовок (:func:`has_sqlite_header`) → открытие **только для чтения**
    (URI ``mode=ro`` — файл не меняется, журнал не создаётся) → ``PRAGMA quick_check``.
    Подключение закрывается сразу (на Windows открытый файл не заменить).

    Args:
        path : (str) Файл.

    Returns:
        (str/None) Текст проблемы на русском; None — база исправна.

    Example:
        >>> sqlite_file_problem('нет-такого-файла.db')
        'нет заголовка базы SQLite («SQLite format 3») — файл не база или повреждён'
    """
    if not has_sqlite_header(path):
        return 'нет заголовка базы SQLite («SQLite format 3») — файл не база или повреждён'
    uri = Path(path).resolve().as_uri() + '?mode=ro'
    try:
        with closing(
            sqlite3.connect(
                uri,                # файл только для чтения
                uri =   True,       # строка — URI
            ),
        ) as connection:
            rows = connection.execute('PRAGMA quick_check').fetchall()
    except sqlite3.Error as exc:
        return f'база SQLite не открывается: {exc}'
    if rows != [('ok',)]: # quick_check вернул список повреждений
        found = '; '.join(
            str(row[0]) for row in rows[:5]
        )
        return f'база SQLite повреждена: {found}'
    return None


def _unique_backup_path(
    local_db_path : str,   # рабочая база
    backup_dir    : str,   # папка копий
) -> str: # свободное имя копии с меткой времени
    """
    Возвращает свободное имя копии: ``<папка>/<имя> - <ГГГГ-ММ-ДД_ЧЧ-ММ-СС><расширение>``.

    Занято — к имени добавляется `` (2)``, `` (3)`` …: прежние копии не затираются.

    Args:
        local_db_path : (str) Рабочая база.
        backup_dir    : (str) Папка копий.

    Returns:
        (str) Путь копии (файла по нему ещё нет).

    Example:
        >>> _unique_backup_path('clinic.db', 'backup')   # doctest: +SKIP
        'backup\\\\clinic - 2026-11-01_12-00-00.db'
    """
    source = Path(local_db_path)
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    candidate = os.path.join(
        backup_dir,                                         # папка
        f"{source.stem} - {stamp}{source.suffix}",          # имя с меткой
    )
    number = 2
    while os.path.exists(candidate): # прежнюю копию не затирать
        candidate = os.path.join(
            backup_dir,                                             # папка
            f"{source.stem} - {stamp} ({number}){source.suffix}",   # имя с номером
        )
        number += 1
    return candidate


def _remove_quietly(
    path : Optional[str],   # файл (None — нечего удалять)
) -> None:
    """
    Удаляет файл, если он есть; ошибки удаления не бросает (уборка после сбоя).

    Args:
        path : (str/None) Файл; None — ничего не делать.

    Example:
        >>> _remove_quietly('нет-такого-файла.part')
    """
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def backup_local_db(
    local_db_path : str,   # рабочая база
    backup_dir    : str,   # папка резервных копий (создаётся при необходимости)
) -> Optional[str]: # резервная копия рабочей базы (И-4)
    """
    Делает резервную копию рабочей базы в ``backup_dir``; прежние копии не затираются.

    Имя — ``<имя> - <ГГГГ-ММ-ДД_ЧЧ-ММ-СС><расширение>`` (занято — с `` (N)``). Копия базы
    SQLite — через backup-API (согласованный снимок, даже если база открыта программой, в том
    числе в режиме WAL — как ``app.database.database.backup_sqlite_database``). Файл без
    заголовка SQLite или база, которую SQLite не читает (повреждена), — копируется побайтно:
    сохраняется как есть. Не удалось — недописанная копия удаляется.

    Не делает: не удаляет старые копии (число копий из настроек — забота вызывающего), не
    читает настройки (папка — параметром, например ``BACKUP_PATH``).

    Args:
        local_db_path : (str) Рабочая база.
        backup_dir    : (str) Папка копий; нет — создаётся.

    Returns:
        (str/None) Путь копии; None — рабочей базы нет (копировать нечего).

    Raises:
        YandexDiskBackupError: Папку не создать, нет прав, нет места и т. п. (``original`` —
            ошибка ОС или SQLite).

    Example:
        >>> backup_local_db(
        ...     'нет-такого-файла.db',    # рабочей базы нет
        ...     'backup',                 # папка копий
        ... ) is None
        True
    """
    if not os.path.isfile(local_db_path):
        return None
    target: Optional[str] = None
    try:
        os.makedirs(backup_dir, exist_ok=True)
        target = _unique_backup_path(local_db_path, backup_dir)
        if has_sqlite_header(local_db_path): # база — согласованный снимок через SQLite
            try:
                with closing(sqlite3.connect(local_db_path)) as source, \
                        closing(sqlite3.connect(target)) as copy:
                    source.backup(copy)
            except sqlite3.DatabaseError: # база повреждена — копия как есть
                _remove_quietly(target)
                shutil.copy2(local_db_path, target)
        else: # не база SQLite — копия как есть
            shutil.copy2(local_db_path, target)
    except (OSError, sqlite3.Error) as exc:
        _remove_quietly(target)
        raise YandexDiskBackupError(
            str(exc) or type(exc).__name__,                         # причина
            local_path  =   local_db_path,                          # рабочая база
            details     =   {
                'папка копий' : backup_dir,     # куда копировали
                'копия'       : target,         # имя копии
            },                                                      # подробности
        ) from exc
    return target


# ----------------------------------------------------------------------------------------
# Какая база новее (И-3)
# ----------------------------------------------------------------------------------------

def _as_utc(
    moment : datetime,   # дата (с часовым поясом или без)
) -> datetime: # дата в UTC с часовым поясом
    """
    Приводит дату к UTC с часовым поясом; дата без пояса считается UTC.

    Args:
        moment : (datetime) Дата.

    Returns:
        (datetime) Дата в UTC.

    Example:
        >>> _as_utc(datetime(2026, 1, 1)).tzinfo
        datetime.timezone.utc
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def compare_freshness(
    local  : Optional[LocalFileInfo],   # рабочая база (None — её нет)
    remote : RemoteFileInfo,            # файл на Диске
) -> DbFreshness: # какая база новее
    """
    Определяет, какая база новее: локальная или на Диске (И-3).

    Порядок: нет локальной — ``NO_LOCAL``; MD5 совпал — ``SAME``; нет даты на Диске —
    ``UNKNOWN``; локальная изменена позже — ``LOCAL_NEWER``, иначе ``REMOTE_NEWER``.

    Сначала MD5, потом даты — потому что после прошлого скачивания дата локального файла —
    время скачивания, то есть всегда позже даты на Диске: без сравнения содержимого
    нетронутая база считалась бы «новее». Ограничение: правки на обоих компьютерах сразу
    (оба файла изменены после последней синхронизации) так не распознать — для этого нужна
    запись о последней синхронизации.

    Args:
        local  : (LocalFileInfo/None) Рабочая база; None — её нет.
        remote : (RemoteFileInfo) Файл на Диске.

    Returns:
        (DbFreshness) Итог сравнения.

    Example:
        >>> from datetime import datetime, timezone
        >>> early = datetime(2026, 1, 1, tzinfo=timezone.utc)
        >>> late = datetime(2026, 1, 2, tzinfo=timezone.utc)
        >>> compare_freshness(
        ...     LocalFileInfo('clinic.db', 4, 'aaa', late),   # правлена позже
        ...     RemoteFileInfo('/clinic.db', 4, 'bbb', early),  # на Диске
        ... )
        <DbFreshness.LOCAL_NEWER: 'local_newer'>
        >>> compare_freshness(
        ...     LocalFileInfo('clinic.db', 4, 'aaa', late),   # скачана раньше
        ...     RemoteFileInfo('/clinic.db', 4, 'AAA', early),  # то же содержимое
        ... )
        <DbFreshness.SAME: 'same'>
    """
    if local is None:
        return DbFreshness.NO_LOCAL
    if remote.md5 and local.md5.lower() == remote.md5.lower():
        return DbFreshness.SAME
    if remote.modified is None:
        return DbFreshness.UNKNOWN
    if _as_utc(local.modified) > _as_utc(remote.modified):
        return DbFreshness.LOCAL_NEWER
    return DbFreshness.REMOTE_NEWER


def _freshness_warning(
    freshness : DbFreshness,              # итог сравнения
    local     : Optional[LocalFileInfo],  # рабочая база
    remote    : RemoteFileInfo,           # файл на Диске
) -> Optional[str]: # предупреждение пользователю о сравнении баз
    """
    Текст предупреждения по итогу сравнения баз; None — предупреждать не о чем.

    Args:
        freshness : (DbFreshness) Итог сравнения.
        local     : (LocalFileInfo/None) Рабочая база.
        remote    : (RemoteFileInfo) Файл на Диске.

    Returns:
        (str/None) Текст; None — ``NO_LOCAL``, ``SAME``, ``REMOTE_NEWER``.

    Example:
        >>> _freshness_warning(DbFreshness.SAME, None, RemoteFileInfo('/a.db', 1, 'x', None)) is None
        True
    """
    if freshness is DbFreshness.LOCAL_NEWER and local is not None and remote.modified:
        local_time = local.modified.astimezone().strftime('%d.%m.%Y %H:%M:%S')
        remote_time = remote.modified.astimezone().strftime('%d.%m.%Y %H:%M:%S')
        return (
            f"Локальная база изменена позже ({local_time}), чем файл на Яндекс.Диске "
            f"({remote_time}): замена затрёт локальные изменения"
        )
    if freshness is DbFreshness.UNKNOWN:
        return 'Яндекс.Диск не сообщил дату файла — какая база новее, проверить нельзя'
    return None


# ----------------------------------------------------------------------------------------
# Яндекс.Диск
# ----------------------------------------------------------------------------------------

def yadisk_server_response(
    exc : BaseException,   # ошибка библиотеки yadisk (или любая)
) -> Optional[str]: # ответ сервера Диска одной строкой
    """
    Возвращает ответ сервера Диска из ошибки ``yadisk``: тип ошибки API, HTTP-код, текст.

    Args:
        exc : (BaseException) Ошибка.

    Returns:
        (str/None) ``'<тип API>; HTTP <код>; <текст>'`` (пустые части пропускаются);
            None — ошибка не от ``yadisk``.

    Example:
        >>> from yadisk.exceptions import PathNotFoundError
        >>> yadisk_server_response(PathNotFoundError('DiskNotFoundError', 'Resource not found.'))
        'DiskNotFoundError; Resource not found.'
        >>> yadisk_server_response(OSError('диск')) is None
        True
    """
    if not isinstance(exc, YaDiskError):
        return None
    parts = []
    if exc.error_type:
        parts.append(exc.error_type)
    status = getattr(exc.response, 'status', None)
    if isinstance(status, int): # HTTP-код ответа
        parts.append(f"HTTP {status}")
    text = str(exc)
    if text:
        parts.append(text)
    return '; '.join(parts) or type(exc).__name__


def _disk_error(
    exc         : BaseException,   # исходная ошибка
    operation   : str,             # что делали
    remote_path : str,             # файл на Диске
    local_path  : Optional[str],   # локальный файл
) -> YandexDiskError: # исключение Яндекс.Диска по исходной ошибке
    """
    Переводит ошибку запроса к Диску (или локальной ФС при скачивании) в ``YandexDisk*Error``.

    Выбор класса: токен не принят (``UnauthorizedError``) — ``YandexDiskTokenError``; нет
    файла (``NotFoundError``) — ``YandexDiskNotFoundError``; при скачивании любая другая
    ошибка — ``YandexDiskTransferError`` (обрыв, сбой сервера, ошибка записи на диск);
    вне скачивания: нет связи (``RequestError``) — ``YandexDiskConnectionError``, прочее —
    ``YandexDiskError``. Возвращает, а не бросает: вызывающий пишет ``raise … from exc``.

    Args:
        exc         : (BaseException) Исходная ошибка.
        operation   : (str) Что делали.
        remote_path : (str) Файл на Диске.
        local_path  : (str/None) Локальный файл; None — не задан.

    Returns:
        (YandexDiskError) Исключение (или наследник) для ``raise``.

    Example:
        >>> from yadisk.exceptions import YaDiskConnectionError
        >>> err = _disk_error(YaDiskConnectionError('timed out'), 'скачивание', '/a.db', 'a.part')
        >>> (type(err).__name__, err.reason)
        ('YandexDiskTransferError', 'связь прервалась во время скачивания: timed out')
    """
    server = yadisk_server_response(exc)
    text = str(exc) or type(exc).__name__
    error_class: Any
    if isinstance(exc, UnauthorizedError):
        error_class, reason = YandexDiskTokenError, f"токен не принят сервером: {text}"
    elif isinstance(exc, NotFoundError):
        error_class, reason = YandexDiskNotFoundError, 'файл не найден на Яндекс.Диске'
    elif operation == _OP_DOWNLOAD:
        error_class = YandexDiskTransferError
        if isinstance(exc, RequestError):
            reason = f"связь прервалась во время скачивания: {text}"
        elif isinstance(exc, OSError):
            reason = f"ошибка записи скачиваемого файла: {text}"
        else:
            reason = f"скачивание не удалось: {text}"
    elif isinstance(exc, RequestError):
        error_class, reason = YandexDiskConnectionError, f"нет связи с Яндекс.Диском: {text}"
    else:
        error_class, reason = YandexDiskError, text
    return error_class(
        reason,                                 # причина
        operation       =   operation,          # что делали
        remote_path     =   remote_path,        # файл на Диске
        local_path      =   local_path,         # локальный файл
        server_response =   server,             # ответ сервера
        original        =   exc,                # исходная ошибка
    )


def _check_token(
    client      : Any,   # открытый клиент yadisk.YaDisk
    remote_path : str,   # файл на Диске (для текста ошибки)
) -> None:
    """
    Проверяет токен; недействителен или нет связи — исключение Яндекс.Диска.

    Args:
        client      : (yadisk.YaDisk) Клиент.
        remote_path : (str) Файл на Диске.

    Raises:
        YandexDiskConnectionError: Нет связи (``check_token`` бросил ошибку ``yadisk``).
        YandexDiskTokenError: Сервер ответил, что токен недействителен.

    Example:
        >>> _check_token(client, '/clinic.db')   # doctest: +SKIP
    """
    try:
        valid = client.check_token()
    except YaDiskError as exc: # нет сети, таймаут, сбой сервера
        raise YandexDiskConnectionError(
            f"нет связи с Яндекс.Диском: {exc or type(exc).__name__}",     # причина
            operation       =   _OP_TOKEN,                                  # что делали
            remote_path     =   remote_path,                                # файл на Диске
            server_response =   yadisk_server_response(exc),                # ответ сервера
            original        =   exc,                                        # исходная ошибка
        ) from exc
    if not valid:
        raise YandexDiskTokenError(
            'токен Яндекс.Диска недействителен',    # причина
            remote_path     =   remote_path,        # файл на Диске
        )


def _remote_file_info(
    client      : Any,   # открытый клиент yadisk.YaDisk
    remote_path : str,   # нормализованный путь на Диске
) -> RemoteFileInfo: # сведения о файле на Диске
    """
    Читает сведения о файле на Диске одним запросом ``get_meta``.

    Args:
        client      : (yadisk.YaDisk) Клиент.
        remote_path : (str) Путь на Диске.

    Returns:
        (RemoteFileInfo) Сведения.

    Raises:
        YandexDiskNotFoundError: Файла нет.
        YandexDiskNotAFileError: По пути — папка.
        YandexDiskTokenError, YandexDiskConnectionError, YandexDiskError: Сбой запроса.

    Example:
        >>> _remote_file_info(client, '/clinic.db')   # doctest: +SKIP
        RemoteFileInfo(path='/clinic.db', size=40960, md5='…', modified=datetime…)
    """
    try:
        meta = client.get_meta(remote_path)
    except YaDiskError as exc:
        raise _disk_error(exc, _OP_META, remote_path, None) from exc
    kind = getattr(meta, 'type', None)
    if kind != 'file': # папка (или неизвестный тип ресурса)
        raise YandexDiskNotAFileError(
            'путь ведёт к папке, а не к файлу',             # причина
            operation   =   _OP_META,                       # что делали
            remote_path =   remote_path,                    # путь на Диске
            details     =   {'тип ресурса': kind},          # что ответил Диск
        )
    size = getattr(meta, 'size', None)
    md5 = getattr(meta, 'md5', None)
    modified = getattr(meta, 'modified', None)
    return RemoteFileInfo(
        path        =   remote_path,                                            # путь
        size        =   size if isinstance(size, int) else None,                # размер
        md5         =   md5.lower() if isinstance(md5, str) and md5 else None,  # MD5
        modified    =   modified if isinstance(modified, datetime) else None,   # дата
    )


def yadisk_remote_file_info(
    ya_token     : str,   # OAuth-токен
    ya_file_path : str,   # путь к файлу на Диске
) -> RemoteFileInfo: # сведения о файле на Диске (размер, MD5, дата)
    """
    Возвращает сведения о файле на Яндекс.Диске: размер, MD5, дату изменения.

    Нужна, например, чтобы до скачивания показать пользователю дату файла на Диске.

    Args:
        ya_token     : (str) OAuth-токен.
        ya_file_path : (str) Путь к файлу на Диске (проходит ``normalize_remote_path``).

    Returns:
        (RemoteFileInfo) Сведения.

    Raises:
        YandexDiskTokenError: Токен недействителен.
        YandexDiskConnectionError: Нет связи.
        YandexDiskNotFoundError: Файла нет.
        YandexDiskNotAFileError: По пути — папка.
        YandexDiskError: Прочий сбой запроса.

    Example:
        >>> yadisk_remote_file_info('y0_...', 'Папка/clinic.db')   # doctest: +SKIP
        RemoteFileInfo(path='Папка/clinic.db', size=40960, md5='…', modified=datetime…)
    """
    remote_path = normalize_remote_path(ya_file_path)
    with _open_client(ya_token) as client:
        _check_token(client, remote_path)
        return _remote_file_info(client, remote_path)


def _verify_download(
    temp_path : str,              # скачанный временный файл
    remote    : RemoteFileInfo,   # сведения Диска
) -> Tuple[LocalFileInfo, Tuple[str, ...]]: # сведения о скачанном файле и предупреждения
    """
    Проверяет скачанный файл: размер и MD5 — с Диском (И-2), затем — база ли это SQLite.

    Диск не сообщил размер или MD5 — эта проверка пропускается, с предупреждением.

    Args:
        temp_path : (str) Скачанный файл.
        remote    : (RemoteFileInfo) Сведения Диска.

    Returns:
        (Tuple[LocalFileInfo, Tuple[str, ...]]) Сведения о файле и предупреждения.

    Raises:
        YandexDiskVerifyError: Размер / MD5 не совпали или файл не исправная база SQLite.
        OSError: Файл не читается.

    Example:
        >>> _verify_download('clinic.db.download-1.part', remote)   # doctest: +SKIP
        (LocalFileInfo(...), ())
    """
    info = local_file_info(temp_path)
    if info is None: # библиотека не создала файл — считаем пустым
        raise YandexDiskVerifyError(
            'size',                                         # что проверялось
            'скачанный файл не появился',                   # причина
            expected    =   remote.size,                    # с Диска
            remote_path =   remote.path,                    # файл на Диске
            local_path  =   temp_path,                      # временный файл
        )
    warnings = []
    if remote.size is None:
        warnings.append('Яндекс.Диск не сообщил размер файла — размер не сверялся')
    elif info.size != remote.size:
        raise YandexDiskVerifyError(
            'size',                                                         # что проверялось
            f"размер {info.size} байт не совпал с размером на Диске "
            f"({remote.size} байт) — файл скачан не полностью",            # причина
            expected    =   remote.size,                                    # с Диска
            actual      =   info.size,                                      # скачано
            remote_path =   remote.path,                                    # файл на Диске
            local_path  =   temp_path,                                      # временный файл
        )
    if remote.md5 is None:
        warnings.append('Яндекс.Диск не сообщил MD5 файла — содержимое не сверялось')
    elif info.md5 != remote.md5:
        raise YandexDiskVerifyError(
            'md5',                                                  # что проверялось
            'MD5 скачанного файла не совпал с MD5 на Диске — файл повреждён при передаче',
            expected    =   remote.md5,                             # с Диска
            actual      =   info.md5,                               # скачано
            remote_path =   remote.path,                            # файл на Диске
            local_path  =   temp_path,                              # временный файл
        )
    problem = sqlite_file_problem(temp_path)
    if problem is not None:
        raise YandexDiskVerifyError(
            'sqlite',                                       # что проверялось
            f"скачанный файл — не исправная база: {problem}",  # причина
            actual      =   problem,                        # что не так
            remote_path =   remote.path,                    # файл на Диске
            local_path  =   temp_path,                      # временный файл
        )
    return info, tuple(warnings)


def _temp_download_path(
    local_db_path : str,   # рабочая база
) -> str: # новый пустой временный файл рядом с рабочей базой
    """
    Создаёт пустой временный файл рядом с рабочей базой: ``<имя>.download-<случайное>.part``.

    Рядом — значит на том же диске: последующий ``os.replace`` атомарен. Имя уникальное
    (``tempfile.mkstemp``) — два скачивания не мешают друг другу. Папка создаётся.

    Args:
        local_db_path : (str) Рабочая база.

    Returns:
        (str) Путь временного файла.

    Raises:
        OSError: Папку или файл не создать.

    Example:
        >>> _temp_download_path('./clinic.db')   # doctest: +SKIP
        '.\\\\clinic.db.download-k2j3h4.part'
    """
    folder = os.path.dirname(os.path.abspath(local_db_path))
    os.makedirs(folder, exist_ok=True)
    handle, path = tempfile.mkstemp(
        prefix  =   os.path.basename(local_db_path) + '.download-',   # имя рабочей базы
        suffix  =   '.part',                                           # недокачанный
        dir     =   folder,                                            # рядом с рабочей
    )
    os.close(handle) # файл откроет yadisk.download
    return path


def yadisk_download_db_checked(
    ya_token          : str,                                # OAuth-токен
    ya_file_path      : str,                                # путь к базе на Диске
    local_db_path     : str,                                # рабочая база (не меняется)
    *,
    backup_dir        : Optional[str] = None,               # папка резервной копии; None — без копии
    progress_callback : Optional[ProgressCallback] = None,  # прогресс (передано, всего)
) -> CheckedDownload: # проверенный временный файл и сведения для замены
    """
    Скачивает базу с Диска во временный файл, проверяет её, сравнивает с рабочей и делает
    резервную копию рабочей. Рабочую базу не меняет.

    Порядок:
        1. токен (``check_token``) и сведения о файле на Диске (``get_meta``: тип, размер,
           MD5, дата);
        2. скачивание во временный файл рядом с рабочей базой (:func:`_temp_download_path`);
        3. проверка: размер и MD5 — с Диском, база SQLite открывается и исправна;
        4. сравнение с рабочей базой (:func:`compare_freshness`): локальная новее —
           предупреждение в ``warnings``, решение — за вызывающим;
        5. если задан ``backup_dir`` и рабочая база есть — резервная копия
           (:func:`backup_local_db`).
    Ошибка на любом шаге — исключение, временный файл удаляется, рабочая база не тронута
    (обрыв сети посередине скачивания её не портит).

    Не делает (это окно, М18): не закрывает подключения к базе, не заменяет файл, не
    открывает базу заново, не спрашивает пользователя — см. описание модуля.

    Note:
        Колбэк прогресса вызывается из потока скачивания. Исключение в колбэке прерывает
        скачивание — так можно сделать отмену (И-1): ``YandexDiskTransferError`` с этой
        ошибкой в ``original``.

    Args:
        ya_token          : (str) OAuth-токен.
        ya_file_path      : (str) Путь к базе на Диске (проходит ``normalize_remote_path``).
        local_db_path     : (str) Рабочая база; её папка — место временного файла.
        backup_dir        : (str/None) Папка резервной копии рабочей базы (например,
            ``BACKUP_PATH``); None — копия не делается (её сделает вызывающий).
        progress_callback : (ProgressCallback/None) Колбэк прогресса; None — без него.

    Returns:
        (CheckedDownload) Проверенный временный файл и сведения.

    Raises:
        YandexDiskTokenError: Токен недействителен.
        YandexDiskConnectionError: Нет связи до начала скачивания.
        YandexDiskNotFoundError: Файла на Диске нет.
        YandexDiskNotAFileError: По пути на Диске — папка.
        YandexDiskTransferError: Скачивание прервано или не удалось (сеть, сервер, запись
            временного файла).
        YandexDiskVerifyError: Скачанный файл не прошёл проверку (размер, MD5, SQLite).
        YandexDiskBackupError: Резервная копия рабочей базы не удалась.
        YandexDiskError: Прочий сбой запроса к Диску.

    Example:
        >>> result = yadisk_download_db_checked(          # doctest: +SKIP
        ...     ya_token          =   'y0_...',            # токен
        ...     ya_file_path      =   'Папка/clinic.db',   # на Диске
        ...     local_db_path     =   './clinic.db',       # рабочая база
        ...     backup_dir        =   './backup',          # копия рабочей
        ... )
        >>> result.local_newer, result.needs_replace      # doctest: +SKIP
        (False, True)
    """
    remote_path = normalize_remote_path(ya_file_path)
    temp_path: Optional[str] = None
    try:
        with _open_client(ya_token) as client:
            _check_token(client, remote_path)
            remote = _remote_file_info(client, remote_path)
            try:
                temp_path = _temp_download_path(local_db_path)
                client.download(
                    remote_path,                                # откуда
                    temp_path,                                  # куда — временный файл
                    progress_callback   =   progress_callback,  # прогресс
                )
            except Exception as exc: # обрыв, сбой сервера, запись на диск, отмена
                raise _disk_error(exc, _OP_DOWNLOAD, remote_path, temp_path) from exc
        try:
            downloaded, warnings = _verify_download(temp_path, remote)
            local = local_file_info(local_db_path)
        except OSError as exc: # временный или рабочий файл не читается
            raise YandexDiskVerifyError(
                'read',                                         # что проверялось
                f"файл не читается: {exc}",                     # причина
                remote_path =   remote_path,                    # файл на Диске
                local_path  =   temp_path,                      # временный файл
            ) from exc
        freshness = compare_freshness(local, remote)
        notes = list(warnings)
        freshness_note = _freshness_warning(freshness, local, remote)
        if freshness_note:
            notes.insert(0, freshness_note) # главное предупреждение — первым
        if local is not None and not has_sqlite_header(local_db_path):
            notes.append('Рабочая база — не файл SQLite (повреждена?); её копия — побайтно')
        backup_path = None
        if backup_dir:
            backup_path = backup_local_db(local_db_path, backup_dir)
    except BaseException:
        _remove_quietly(temp_path) # рабочая база не тронута, временный — убрать
        raise
    return CheckedDownload(
        temp_path   =   temp_path,          # проверенный временный
        local_path  =   local_db_path,      # рабочая (не тронута)
        remote      =   remote,             # на Диске
        downloaded  =   downloaded,         # скачанный
        local       =   local,              # рабочая до скачивания
        freshness   =   freshness,          # какая новее
        backup_path =   backup_path,        # резервная копия
        warnings    =   tuple(notes),       # предупреждения
    )
