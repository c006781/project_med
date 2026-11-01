# app/network/__init__.py

"""
Пакет app.network — обмен с Яндекс.Диском (синхронизация файла БД).

Содержит:

- ``ya_dop.py`` — функции без Qt: скачивание/загрузка, проверки токена и путей, коды
  результата :class:`YaDiskResult`, пути (:func:`remote_db_file_path` и др.);
- ``thread_network.py`` — потоки Qt :class:`YaDiskThread` (база), :class:`DownloadThread`,
  :class:`UploadThread`, :class:`CheckedDownloadThread`;
- ``db_download.py`` — безопасное скачивание базы (ТД-1): во временный файл → проверка
  (размер, MD5, SQLite) → какая база новее → резервная копия; рабочую базу не меняет
  (:func:`yadisk_download_db_checked`, итог — :class:`CheckedDownload`).

Подробности — ``app/network/IMPLEMENTATION.md``.

Example:
    >>> from app.network import YaDiskResult, remote_db_file_path
    >>> remote_db_file_path('Папка', './clinic.db')
    'Папка/clinic.db'
    >>> YaDiskResult.describe(-1)
    'Токен Яндекс.Диска недействителен или нет соединения'
"""
# - dop_yadisk/: функции для прямого вызова Яндекс.Диска (yadisk_download_file, yadisk_upload_file).
# ↑ до rework-yadisk, проход 1 (2026-10-21): подпакета dop_yadisk нет — функции в ya_dop.py

# Импортируем классы потоков из thread_network
from app.network.thread_network import (
    DownloadThread, 
    UploadThread,
    YaDiskThread,
)

# Поток безопасного скачивания базы
from app.network.thread_network import CheckedDownloadThread

# Безопасное скачивание базы (ТД-1): временный файл, проверка, сравнение, резервная копия
from app.network.db_download import (
    CheckedDownload,
    DbFreshness,
    LocalFileInfo,
    RemoteFileInfo,
    backup_local_db,
    compare_freshness,
    file_md5,
    has_sqlite_header,
    local_file_info,
    sqlite_file_problem,
    yadisk_download_db_checked,
    yadisk_remote_file_info,
    yadisk_server_response,
)

# Функции и типы работы с Яндекс.Диском
from app.network.ya_dop import (
    DB_EXTENSIONS,
    YaDiskResult,
    check_and_create_path,
    check_remote_file_exists,
    check_token,
    normalize_remote_path,
    remote_db_file_path,
    remote_parent_dir,
    yadisk_download_file, 
    yadisk_upload_file,
)

# Экспортируем публичный API пакета
__all__ = [
    'DB_EXTENSIONS',
    'DownloadThread',
    'UploadThread',
    'YaDiskResult',
    'YaDiskThread',
    'check_and_create_path',
    'check_remote_file_exists',
    'check_token',
    'normalize_remote_path',
    'remote_db_file_path',
    'remote_parent_dir',
    'yadisk_download_file',
    'yadisk_upload_file',
    # Безопасное скачивание базы (с 2026-11-01)
    'CheckedDownload',
    'CheckedDownloadThread',
    'DbFreshness',
    'LocalFileInfo',
    'RemoteFileInfo',
    'backup_local_db',
    'compare_freshness',
    'file_md5',
    'has_sqlite_header',
    'local_file_info',
    'sqlite_file_problem',
    'yadisk_download_db_checked',
    'yadisk_remote_file_info',
    'yadisk_server_response',
]
