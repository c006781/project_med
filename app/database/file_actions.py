# app/database/file_actions.py
"""
Встроенные действия событий таблиц для файлов (Ф1.6.7б, решение владельца 2026-10-26, В-3).

* ``remove_photo_file`` — место ``after_commit`` таблицы файлов фото (``PHOTO_FILES``,
  ``app/schema/clinic.py``): строку файла, на которую больше никто не ссылается, удалил
  сборщик мусора (Р-25: только он, отдельным кругом после удаления фото) — после коммита
  удаляется и сам файл в папке фото.

Папка фото — ресурс базы ``TableEvents.resources['photos_root']`` (:data:`PHOTOS_ROOT`):
её кладёт сервис фото (он знает настройку ``PHOTOS_STORAGE_PATH``); слой базы настроек не
читает. После коммита база не трогается: что удалено, видно по журналу транзакции
(``ctx.changes``) — последнее действие со строкой. Файл не удалился (занят, нет прав) —
предупреждение в журнал, файл остаётся (FD10, Р-5): его найдёт сверка «файлы ↔ ссылки»
(Ф1.6.10г).

Действия регистрирует :func:`register_file_actions` — ``Database.__init__`` до сверки имён
(``check_action_names``, Р-9).

Example:
    >>> register_file_actions()
    >>> 'remove_photo_file' in registered_actions()
    True
"""

from __future__ import annotations

import ntpath
import os
import re
from typing import Any, Dict, List, Optional

from app.database.table_events import EventContext, register_action
from app.utils.file_deletions import delete_empty_directory, delete_file_safely
from app.utils.logger import AppLogger


PHOTOS_ROOT        : str = 'photos_root'         # ресурс базы: папка фото (абсолютный путь)
REMOVE_PHOTO_FILE  : str = 'remove_photo_file'   # имя действия в описании PHOTO_FILES

# Имя файла фото нашего вида (Ф1.6.7б): время добавления ГГГГММДД_ЧЧММСС, номер в той же
# секунде, расширение строчными. Старые пути (app_<N>/<uuid>.jpg) — не этого вида: их переносит
# PhotoService.relocate_legacy_files; сверка трогает только имена этого вида и папки app_*.
PHOTO_NAME_RE      : 're.Pattern[str]' = re.compile(r'^\d{8}_\d{6}(_\d+)?(\.[a-z0-9]+)?$')


def _logger() -> AppLogger: # журнал действий с файлами
    """
    Возвращает журнал действий с файлами (``api.FileActions``, файл пользователя).

    Returns:
        (AppLogger) Журнал.

    Example:
        >>> _logger().info('сообщение')
    """
    return AppLogger.get_instance(
        name                 = 'api.FileActions',   # журнал действий с файлами
        enable_file_logging  = 'user',              # файл пользователя
        use_name_in_filename = False,               # имя не в имени файла
    )


def photo_file_path(
    root : str,   # папка фото
    name : str,   # путь файла от папки фото (как в БД)
) -> Optional[str]: # полный путь файла внутри папки фото или None
    """
    Возвращает полный путь файла фото по имени из БД — только внутри папки фото.

    Старые пути Windows (``app_1\\a.jpg``, Р-29) понимаются на любой системе. Абсолютное
    имя (в том числе с буквой диска ``C:/x.jpg``, ``C:x.jpg`` — на любой системе, база
    ходит между Windows и Linux), выход из папки (``..``) или сама папка — None: такое имя
    не трогается.

    Args:
        root : (str) Папка фото.
        name : (str) Путь файла от папки фото.

    Returns:
        (str/None) Полный путь; None — имя ведёт вне папки фото.

    Example:
        >>> photo_file_path('C:/photos', '20261101_120000.jpg')
        'C:\\\\photos\\\\20261101_120000.jpg'
        >>> photo_file_path('C:/photos', '../clinic.db') is None
        True
        >>> photo_file_path('/photos', 'C:/x.jpg') is None
        True
    """
    if not root or not name:
        return None
    relative = name.replace('\\', '/')                # старые пути Windows (Р-29)
    # ↑ до 2026-11-05 (M13): было `if os.path.isabs(relative) or relative.startswith('/')` —
    #   на Linux имя с буквой диска (`C:/x.jpg`, `C:x.jpg`) считалось относительным, а на Windows
    #   `C:x.jpg` ломало `commonpath`
    if os.path.isabs(relative) or relative.startswith('/') or ntpath.splitdrive(relative)[0]:
        return None
    base = os.path.normpath(os.path.abspath(root))
    path = os.path.normpath(
        os.path.join(
            base,       # папка фото
            relative,   # имя от неё
        ),
    )
    if path == base or os.path.commonpath([base, path]) != base: # вне папки фото
        return None
    return path


def _gone_keys(
    ctx : EventContext,   # контекст действия транзакции
) -> List[Any]: # ключи строк, удалённых транзакцией окончательно
    """
    Возвращает ключи строк, последнее действие с которыми в транзакции — удаление.

    Удалили и добавили снова (то же имя) — строка есть, файл нужен; добавили и удалили в
    одной транзакции — файла не нужно.

    Args:
        ctx : (EventContext) Контекст (``changes`` — журнал таблицы по порядку).

    Returns:
        (List[Any]) Ключи по порядку первого изменения.

    Example:
        >>> _gone_keys(ctx)
        ['20261101_120000.jpg']
    """
    last : Dict[Any, str] = {}
    for change in ctx.changes:
        last[change.key] = change.operation
    return [key for key, operation in last.items() if operation == 'delete']


@register_action(REMOVE_PHOTO_FILE)
def remove_photo_file(
    ctx : EventContext,   # after_commit таблицы файлов фото
) -> None: # удаляет файлы фото, строки которых удалены транзакцией
    """
    Удаляет с диска файлы фото, строки которых закоммиченная транзакция удалила.

    Строку файла удаляет только сборщик мусора — когда на файл больше не ссылается ни одно
    фото (Р-25). Здесь — физический файл: ``<папка фото>/<имя>``; папка старого вида
    (``app_<N>``), ставшая пустой, — тоже (не сама папка фото). База не трогается.
    Ошибки удаления — предупреждение в журнал, файл остаётся (FD10, Р-5). Папки фото нет
    в ресурсах базы (сервис фото не создан) — предупреждение, файлы остаются.

    Args:
        ctx : (EventContext) Контекст ``after_commit`` (``changes``, ``resources``).

    Example:
        >>> # app/schema/clinic.py: PHOTO_FILES … events=(on('after_commit', 'remove_photo_file'),)
        >>> remove_photo_file(ctx)
    """
    gone = _gone_keys(ctx)
    if not gone:
        return
    logger = _logger()
    root = ctx.resources.get(PHOTOS_ROOT)
    if not root:
        logger.warning(
            f"Папка фото не задана (нет сервиса фото) — файлы удалённых строк остаются: "
            f"{', '.join(map(str, gone))}; их найдёт сверка файлов"
        )
        return
    base = os.path.normpath(os.path.abspath(root))
    for name in gone:
        path = photo_file_path(
            base,         # папка фото
            str(name),    # имя из БД
        )
        if path is None:
            logger.warning(f"Файл фото {name!r} — вне папки фото {base}, не удаляется")
            continue
        if not os.path.isfile(path): # удалять нечего
            logger.info(f"Файла фото уже нет на диске: {path}")
            continue
        deleted, error = delete_file_safely(
            path,
            logger = logger,
        )
        if not deleted: # занят, нет прав — остаётся (FD10)
            logger.warning(
                f"Файл фото не удалён, остаётся (найдёт сверка файлов): {path}; {error}"
            )
            continue
        logger.info(f"Удалён файл фото {name} — на него больше не ссылается ни одно фото")
        parent = os.path.dirname(path)
        if parent != base and os.path.basename(parent).startswith('app_'): # папка старого вида
            delete_empty_directory(
                parent,
                logger = logger,
            )


def register_file_actions() -> None: # регистрирует действия с файлами (повтор — без ошибки)
    """
    Регистрирует встроенные действия с файлами в реестре событий таблиц. Повторный вызов
    ничего не меняет (та же функция под тем же именем).

    Example:
        >>> register_file_actions()
    """
    register_action(
        REMOVE_PHOTO_FILE,   # имя
        remove_photo_file,   # действие
    )


__all__ = [
    'PHOTOS_ROOT', 'REMOVE_PHOTO_FILE', 'PHOTO_NAME_RE', 'photo_file_path', 'remove_photo_file',
    'register_file_actions',
]
