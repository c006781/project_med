# app/services/sync_service.py
"""
Сервис синхронизации файла базы с Яндекс.Диском (``SyncService``).

Скачать / выгрузить сразу (``download_sync``, ``upload_sync`` — командная строка) или
подготовить поток Qt (``prepare_download``, ``prepare_upload``). Сеть — в
``app.network`` (``ya_dop``: функции Диска, ``thread_network``: потоки, ``db_download``:
безопасное скачивание); здесь — токен и пути из настроек, путь к файлу на Диске
(``remote_db_file_path``) и то, что общее у окна и командной строки при обмене файлом базы:

* :func:`backup_db_before_transfer` — резервная копия перед передачей, старые копии по
  ``BACKUP_COUNT`` (:func:`prune_db_backups`, :func:`parse_backup_count`);
* :func:`install_checked_download` — замена рабочей базы скачанной: подключения закрыть →
  заменить → убрать журналы прежней → открыть; не открылась — прежняя возвращается;
* :func:`remove_stale_downloads` — временные файлы, оставшиеся после аварийного выхода.

Общий объект приложения — ``app.dependencies.get_sync_service()`` (кэш, Ф1.6.10в):
настройки ему передаёт ``ConfigApplier.apply_sync``. ``DB_EXTENSIONS`` импортируется ради
прежнего адреса ``app.services.sync_service.DB_EXTENSIONS`` (реэкспорт; pyflakes видит его
неиспользуемым — намеренно).

Example:
    >>> from app.dependencies import get_sync_service
    >>> thread = get_sync_service().prepare_download()   # поток окна
    >>> thread.start()                                    # doctest: +SKIP — живой запрос
"""

# # Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


# import shutil

# from typing import Type, TypeVar, Generic, List

# from datetime import time

# Импорты модулей
# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None





import glob
import os
import re
import shutil
from typing import Any, Callable, List, Optional

from app.exceptions.exceptions_all import YandexDiskError, YandexDiskTransferError

from app.network.db_download import CheckedDownload, backup_local_db, yadisk_download_db_checked

from app.utils.logger.logger import AppLogger

# try:
from app.network.thread_network import DownloadThread, UploadThread
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..network.thread_network import DownloadThread, UploadThread
#     except ImportError as e:
#         pass #  raise # e # pass


# try:
from app.network.ya_dop import (
    DB_EXTENSIONS, # расширения файла БД (реэкспорт — прежний адрес app.services.sync_service)
    remote_db_file_path, # путь к файлу БД на Диске по настройкам
    # yadisk_download_file,
    # ↑ до 2026-11-07 (ТД-1): скачивание шло прямо в рабочий файл базы; теперь yadisk_download_db_checked
    yadisk_upload_file,
    YaDiskResult, # код результата
)
# from app.network.ya_dop import yadisk_download_file, yadisk_upload_file
# import os # remote_db_file_path: имя файла из локального пути
# ↑ до rework-yadisk, проход 1 (2026-10-21): remote_db_file_path перенесена в app.network (P1)
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..network.ya_dop import yadisk_download_file, yadisk_upload_file
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
    # from ..controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import AppConfigManager, get_config_env
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         # from ..controllers.conf.get_config import get_config_env
#         from ..controllers.config_manager.manager import get_config_env
#     except ImportError as e:
#         pass #  raise # e # pass







# # Расширения файла БД: путь на Диске без них считается папкой
# DB_EXTENSIONS = ('.db', '.sqlite', '.sqlite3')
#
#
# def remote_db_file_path(
#     remote_path: str, # путь на Диске из настроек: файл БД или папка
#     local_path: str, # локальный путь к БД — из него берётся имя файла
# ) -> str:
#     """
#     Путь к файлу БД на Яндекс.Диске.
#
#     Если в настройках указана папка (путь не кончается на .db/.sqlite/.sqlite3),
#     дописывается имя локального файла — как MainWindow._correct_remote_path у окна.
#
#     Args:
#         remote_path (str): Путь на Диске из настроек (None/'' — корень Диска).
#         local_path (str): Локальный путь к файлу БД.
#
#     Returns:
#         str: Путь к файлу БД на Диске.
#
#     Example:
#         >>> remote_db_file_path('Папка/база', './clinic.db')
#         'Папка/база/clinic.db'
#         >>> remote_db_file_path('/Папка/clinic.db', './other.db')
#         '/Папка/clinic.db'
#     """
#     remote_path = remote_path or ''
#     if remote_path.lower().endswith(DB_EXTENSIONS):
#         return remote_path
#     remote_dir = remote_path.rstrip('/\\')
#     return f"{remote_dir}/{os.path.basename(local_path)}"
# ↑ до rework-yadisk, проход 1 (2026-10-21): путь к файлу БД — основа сетевого модуля (P1),
#   перенесён в app.network.ya_dop.remote_db_file_path (там же '\\' → '/').


# Что SQLite может оставить рядом с файлом базы: чужой журнал применился бы к новому файлу
_DB_SIDECAR_SUFFIXES = ('-journal', '-wal', '-shm')


# журнал этого модуля
def _sync_logger() -> Any:
    """
    Возвращает журнал функций обмена файлом базы.

    Returns:
        (AppLogger) Журнал пользователя.

    Example:
        >>> _sync_logger().info('Проверка')     # doctest: +SKIP
    """
    return AppLogger.get_instance(
        name                    =   'api.SyncService',  # тот же журнал, что у сервиса
        enable_file_logging     =   'user',             # файл журнала пользователя
        use_name_in_filename    =   False,              # без имени в файле
    )


# сколько копий базы хранить; None — значение негодное
def parse_backup_count(
    value : Any,    # значение настройки BACKUP_COUNT
) -> Optional[int]:
    """
    Переводит настройку ``BACKUP_COUNT`` в число; негодное значение не становится числом.

    Менеджер настроек оставляет непереводимую строку из файла как есть. Подставлять вместо неё
    умолчание здесь нельзя: вызывающий удалил бы копии по числу, которого пользователь не задавал.

    Args:
        value : (Any) Значение настройки.

    Returns:
        (int/None) Число не меньше 1; None — не целое число или меньше 1.

    Example:
        >>> parse_backup_count('7'), parse_backup_count('много'), parse_backup_count(0)
        (7, None, None)
    """
    if isinstance(value, bool):
        return None
    try:
        count = int(str(value).strip())
    except ValueError:
        return None
    return count if count >= 1 else None


# удаление старых копий базы сверх числа; только свои, по имени
def prune_db_backups(
    local_db_path : str,    # рабочая база: от неё имя копий
    backup_dir    : str,    # папка копий
    keep          : int,    # сколько новых копий оставить
) -> List[str]:
    """
    Удаляет старые резервные копии этой базы, оставляя ``keep`` самых новых.

    Копией считается только файл с именем ``<имя> - <ГГГГ-ММ-ДД_ЧЧ-ММ-СС>[ (N)]<расширение>``, как
    их называет ``backup_local_db``: чужие файлы и копии других баз в той же папке не трогаются.
    Порядок — по метке времени в имени, а не по дате файла (её меняет копирование папки).
    Ошибка удаления только пишется в журнал: уборка не должна мешать передаче.

    Args:
        local_db_path : (str) Рабочая база.
        backup_dir    : (str) Папка копий; нет — ничего не делается.
        keep          : (int) Сколько оставить; меньше 1 — ничего не удаляется.

    Returns:
        (List[str]) Удалённые файлы.

    Example:
        >>> prune_db_backups(
        ...     'clinic.db',    # рабочая база
        ...     'нет-папки',    # папки нет
        ...     5,              # оставить
        ... )
        []
    """
    if keep < 1:
        return []
    stem, suffix = os.path.splitext(os.path.basename(local_db_path))
    pattern = re.compile(
        rf"{re.escape(stem)} - (\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}})(?: \((\d+)\))?{re.escape(suffix)}",
    )
    copies = []
    try:
        with os.scandir(backup_dir) as entries:
            for entry in entries:
                match = pattern.fullmatch(entry.name)
                if match and entry.is_file(follow_symlinks=False):  # только своя копия
                    copies.append((match.group(1), int(match.group(2) or 1), entry.path))
    except OSError as exc:  # папки нет или она не читается
        _sync_logger().debug(f"Папка копий базы не прочитана: {backup_dir}: {exc}")
        return []
    copies.sort(reverse=True)
    removed : List[str] = []
    for _stamp, _number, path in copies[keep:]:
        try:
            os.remove(path)
            removed.append(path)
        except OSError as exc:
            _sync_logger().warning(f"Старая копия базы не удалена: {path}: {exc}")
    return removed


# резервная копия перед передачей; старые копии — по настройке
def backup_db_before_transfer(
    local_db_path : str,            # рабочая база
    config        : Any = None,     # настройки (метод get); None — менеджер настроек
) -> Optional[str]:
    """
    Делает резервную копию рабочей базы перед обменом с Диском и удаляет старые копии.

    Копия — в папку ``BACKUP_PATH``, до начала скачивания и до выгрузки (решение владельца,
    В-20). Старые копии — по ``BACKUP_COUNT``; значение негодное — ничего не удаляется, в журнал
    предупреждение. Если папка не задана, берётся умолчание программы.

    Args:
        local_db_path : (str) Рабочая база.
        config        : (Any) Настройки; None — ``AppConfigManager.get_instance()``.

    Returns:
        (str/None) Путь копии; None — рабочей базы нет.

    Raises:
        YandexDiskBackupError: Копию сделать не удалось: передачу начинать нельзя.

    Example:
        >>> backup_db_before_transfer(
        ...     'нет-такого-файла.db',                                  # базы нет
        ...     {'BACKUP_PATH': 'backup', 'BACKUP_COUNT': 5},           # настройки
        ... ) is None
        True
    """
    config = AppConfigManager.get_instance() if config is None else config
    backup_dir = config.get('BACKUP_PATH') or AppConfigManager.default_of('BACKUP_PATH')
    backup_path = backup_local_db(
        local_db_path,  # рабочая база
        backup_dir,     # папка копий
    )
    raw_count = config.get('BACKUP_COUNT')
    keep = parse_backup_count(raw_count)
    if keep is None:  # негодное значение: лишнего не удалять
        _sync_logger().warning(f"BACKUP_COUNT не число от 1: {raw_count!r}; старые копии базы не удаляются")
    elif backup_path is not None:  # копия появилась — уборка по числу
        prune_db_backups(
            local_db_path,  # рабочая база
            backup_dir,     # папка копий
            keep,           # сколько оставить
        )
    return backup_path


# удаление недокачанных временных файлов базы
def remove_stale_downloads(
    local_db_path : str,    # рабочая база
) -> List[str]:
    """
    Удаляет временные файлы скачивания базы, оставшиеся после аварийного выхода.

    Вызывается при запуске программы: своё скачивание в этот момент не идёт. Удаляются только
    файлы ``<база>.download-*.part`` рядом с базой. Ошибка удаления только пишется в журнал.

    Args:
        local_db_path : (str) Рабочая база.

    Returns:
        (List[str]) Удалённые файлы.

    Example:
        >>> remove_stale_downloads('нет-папки/clinic.db')
        []
    """
    pattern = glob.escape(os.path.abspath(local_db_path)) + '.download-*.part'
    removed : List[str] = []
    for path in glob.glob(pattern):
        if not os.path.isfile(path):
            continue
        try:
            os.remove(path)
            removed.append(path)
        except OSError as exc:
            _sync_logger().warning(f"Временный файл базы не удалён: {path}: {exc}")
    return removed


# журналы SQLite прежней базы рядом с файлом
def _remove_db_sidecars(
    local_db_path : str,    # файл базы
) -> None:
    """
    Удаляет журналы SQLite рядом с файлом базы: чужой журнал применился бы к новому файлу.

    Args:
        local_db_path : (str) Файл базы.

    Raises:
        OSError: Журнал есть, но удалить его нельзя (занят).

    Example:
        >>> _remove_db_sidecars('нет-такого-файла.db')
    """
    for suffix in _DB_SIDECAR_SUFFIXES:
        try:
            os.remove(local_db_path + suffix)
        except FileNotFoundError:
            pass


# отказ от скачанного файла без падения
def discard_download(
    result : CheckedDownload,   # итог безопасного скачивания
) -> None:
    """
    Удаляет временный файл отказанного скачивания; занятый файл остаётся до следующего запуска.

    Args:
        result : (CheckedDownload) Итог скачивания.

    Example:
        >>> discard_download(result)    # doctest: +SKIP
    """
    try:
        result.discard()
    except OSError as exc:
        _sync_logger().warning(f"Временный файл базы не удалён: {result.temp_path}: {exc}")


# открыть общую базу заново и перезагрузить сервисы
def _reopen_app_db() -> None:
    """
    Открывает общую базу заново и перезагружает сервисы: те же объекты, что у страниц окна.

    Импорт внутри функции: ``app.dependencies`` импортирует этот модуль.

    Raises:
        DatabaseConnectionError: Базу не удалось открыть.
        MigrationError: Базу нельзя безопасно обновить.
        RuntimeError: Часть сервисов не перезагружена.

    Example:
        >>> _reopen_app_db()    # doctest: +SKIP
    """
    from app.dependencies import create_config_applier
    create_config_applier().apply_database(AppConfigManager.get_instance().get_all())


# замена рабочей базы проверенной скачанной
def install_checked_download(
    result : CheckedDownload,   # итог безопасного скачивания
) -> None:
    """
    Заменяет рабочую базу скачанной и открывает её; при сбое рабочая база остаётся прежней.

    Порядок:
        1. закрыть подключения (``close_db``): на Windows открытый файл не заменить;
        2. запомнить прежний файл рядом (``<база>.download-previous.part``);
        3. ``os.replace`` временного файла на место рабочего (атомарно, тот же диск);
        4. убрать журналы SQLite прежней базы (``-journal``, ``-wal``, ``-shm``);
        5. открыть базу и перезагрузить сервисы;
        6. убрать запомненный файл.
    Сбой шагов 2–4: прежний файл на месте, база открывается снова. Сбой шага 5 (скачанная база
    новее программы, миграция не прошла): прежний файл возвращается и открывается. После сбоя
    временный файл удаляется.

    Note:
        ``close_db`` закрывает сессию вызывающего потока и пул; другие потоки в этот момент с
        базой работать не должны: окно на время передачи выключает экраны и не даёт начать импорт.

    Не делает: не спрашивает пользователя и не решает, нужна ли замена (``result.needs_replace``,
    ``result.local_newer``), не делает резервную копию (:func:`backup_db_before_transfer`).

    Args:
        result : (CheckedDownload) Итог ``yadisk_download_db_checked``.

    Raises:
        YandexDiskTransferError: Замена не удалась, рабочая база прежняя (``original`` — причина).
        Exception: Скачанная база не открылась и прежнюю вернуть не удалось; файл остаётся на месте,
            резервная копия — в папке копий.

    Example:
        >>> install_checked_download(result)    # doctest: +SKIP
    """
    from app.dependencies import close_db
    local_path = result.local_path
    previous = f"{local_path}.download-previous.part"
    had_local = os.path.isfile(local_path)
    replaced = False
    close_db()
    try:
        if had_local:
            shutil.copy2(
                local_path, # рабочая база
                previous,   # прежняя версия на время замены
            )
        os.replace(
            result.temp_path,   # скачанный и проверенный файл
            local_path,         # рабочая база
        )
        replaced = True
        _remove_db_sidecars(local_path)
    except OSError as exc:  # файл занят, нет места: рабочая база прежняя
        discard_download(result)
        if replaced:  # журнал не убрался: вернуть прежний файл
            _restore_previous_db(local_path, previous, had_local)
        else:  # рабочий файл не менялся, запомненная копия могла остаться неполной
            _remove_stale_previous(previous)
        _reopen_app_db()
        raise YandexDiskTransferError(
            f"рабочая база не заменена: {exc}",     # причина
            operation   =   'замена базы',          # что делали
            local_path  =   local_path,             # рабочая база
        ) from exc
    try:
        _reopen_app_db()
    except Exception as exc:  # скачанная база не открывается этой версией программы
        _sync_logger().exception(f"Скачанная база не открылась: {exc}")
        close_db()
        _restore_previous_db(local_path, previous, had_local)
        _reopen_app_db()
        raise YandexDiskTransferError(
            f"скачанная база не открылась, рабочая база возвращена: {exc}",     # причина
            operation   =   'замена базы',                                      # что делали
            local_path  =   local_path,                                         # рабочая база
        ) from exc
    _remove_stale_previous(previous)


# вернуть прежний файл базы на место
def _restore_previous_db(
    local_path : str,   # рабочая база
    previous   : str,   # запомненная прежняя версия
    had_local  : bool,  # был ли рабочий файл до замены
) -> None:
    """
    Возвращает прежний файл базы; не было прежнего и файл заменён — убирает скачанный.

    Args:
        local_path : (str) Рабочая база.
        previous   : (str) Запомненная прежняя версия.
        had_local  : (bool) Был ли рабочий файл до замены.

    Raises:
        OSError: Вернуть не удалось.

    Example:
        >>> _restore_previous_db('нет.db', 'нет.part', False)
    """
    if os.path.isfile(previous):
        os.replace(
            previous,   # прежняя версия
            local_path, # рабочая база
        )
    elif not had_local and os.path.isfile(local_path):
        os.remove(local_path)
    _remove_db_sidecars(local_path)


# запомненный файл больше не нужен
def _remove_stale_previous(
    previous : str,     # запомненная прежняя версия
) -> None:
    """
    Удаляет запомненную прежнюю версию; не удалилась — останется до следующего запуска.

    Args:
        previous : (str) Файл.

    Example:
        >>> _remove_stale_previous('нет-такого-файла.part')
    """
    try:
        os.remove(previous)
    except FileNotFoundError:
        pass
    except OSError as exc:
        _sync_logger().warning(f"Прежняя версия базы не удалена: {previous}: {exc}")


class SyncService:
    """
    Синхронизация файла базы с Яндекс.Диском: скачать / выгрузить сразу или потоком.

    Токен и пути — атрибуты ``token``, ``remote_path`` (файл или папка на Диске),
    ``local_path`` (файл базы); их меняет ``ConfigApplier.apply_sync`` (общий объект —
    ``app.dependencies.get_sync_service``, кэш) или :meth:`reload_config`. Путь на Диске —
    ``remote_db_file_path``: папка из настроек дополняется именем локального файла.

    Attributes:
        token       : (str/None) OAuth-токен Яндекс.Диска (``YANDEX_TOKEN``).
        remote_path : (str/None) Путь на Диске из настроек (``database_remote_path``).
        local_path  : (str/None) Локальный файл базы (``database_local_path``).

    Example:
        >>> service = get_sync_service()
        >>> service.download_sync()     # doctest: +SKIP — живой запрос
        <YaDiskResult.OK: 0>
    """

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self) -> None:
        """
        Создаёт сервис: токен и пути читает из ``.env`` (``get_config_env``) один раз.

        Дальше значения обновляют ``ConfigApplier.apply_sync`` или :meth:`reload_config`.

        Raises:
            KeyError: В настройках нет ``YANDEX_TOKEN``, ``database_remote_path`` или
                ``database_local_path``.

        Example:
            >>> SyncService().local_path
            'clinic.db'
        """

        config = get_config_env()

        # получение токена Яндекс.Диска из .env
        self.token = config['YANDEX_TOKEN']

        # получение пути к файлу на Яндекс.Диске
        self.remote_path = config['database_remote_path']

        # получение пути к локальному файлу
        self.local_path = config['database_local_path']

        self.logger = AppLogger.get_instance(
            name='api.SyncService',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        # Подписываемся на изменения конфига
        # AppConfigManager.add_change_listener(self.reload_config)
        # ↑ до 2026-10-14 (CM4): применение настроек — только ConfigApplier.apply_sync().

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def download_sync(
        self,
        progress_callback : Optional[Callable[[int, int], Any]] = None, # прогресс: (передано, всего)
        overwrite_newer   : bool = False,                               # заменять локальную базу, которая новее
    ) -> int: # YaDiskResult.OK — рабочая база совпадает с файлом на Диске
        """
        Скачивает файл базы с Яндекс.Диска и заменяет рабочую (в этом потоке, с ожиданием).

        Порядок: резервная копия → скачивание во временный файл и проверка → замена → открытие
        (:func:`backup_db_before_transfer`, ``yadisk_download_db_checked``,
        :func:`install_checked_download`). Обрыв сети рабочую базу не портит. Содержимое
        совпало — замены нет. Спросить некого, поэтому базу, изменённую позже файла на Диске,
        без ``overwrite_newer`` не заменяет: сообщает об этом исключением. Предупреждения — в журнал.

        Ошибки — исключениями: код результата при успехе всегда ``OK``.
        Путь на Диске — ``remote_db_file_path(remote_path, local_path)``.

        Args:
            progress_callback : (callable/None) Вызывается с ``(передано, всего)`` байт;
                None — без прогресса.
            overwrite_newer   : (bool) Заменять локальную базу, изменённую позже файла на Диске.

        Returns:
            (int) ``YaDiskResult.OK`` (0).

        Raises:
            YandexDiskBackupError: Резервная копия не удалась, скачивание не начато.
            YandexDiskTokenError: Токен недействителен.
            YandexDiskConnectionError: Нет связи.
            YandexDiskNotFoundError: Файла на Диске нет.
            YandexDiskNotAFileError: Путь на Диске ведёт к папке.
            YandexDiskTransferError: Скачивание прервано или замена не удалась; база прежняя.
            YandexDiskVerifyError: Скачанный файл не прошёл проверку; база прежняя.
            YandexDiskError: Локальная база новее и ``overwrite_newer`` выключен; база прежняя.

        Example:
            >>> get_sync_service().download_sync()   # doctest: +SKIP — живой запрос
            <YaDiskResult.OK: 0>
        """
        # вызов функции yadisk_download_file с параметрами, сохраненными в __init__
        # return yadisk_download_file(
        #     ya_token=self.token,
        #     ya_file_path=self.remote_path,
        #     local_file_path=self.local_path,
        #     if_err=True,
        #     progress_callback=progress_callback
        # )

        # yadisk_download_file вызывает функцию yadisk_download_file с параметрами,
        # сохраненными в __init__, и передает прогресс загрузки
        # в колбэк _progress_callback.
        # Если возникнет какая-либо ошибка, то сообщение об ошибке
        # передается в колбэк error.
        # return yadisk_download_file(
        #     ya_token=self.token,
        #     ya_file_path=remote_db_file_path(self.remote_path, self.local_path),
        #     # ya_file_path=self.remote_path,
        #     # ↑ до rework-sync-service (2026-10-21): папка из настроек шла как путь к файлу
        #     local_file_path=self.local_path,
        #     if_err=True,
        #     progress_callback=progress_callback
        # )
        # ↑ до 2026-11-07 (ТД-1): скачивание шло поверх открытой рабочей базы, обрыв её портил
        backup_db_before_transfer(self.local_path)
        result = yadisk_download_db_checked(
            ya_token            =   self.token,                                                 # токен
            ya_file_path        =   remote_db_file_path(self.remote_path, self.local_path),     # откуда
            local_db_path       =   self.local_path,                                            # рабочая база
            progress_callback   =   progress_callback,                                          # прогресс
        )
        for warning in result.warnings:
            self.logger.warning(warning)
        if not result.needs_replace:  # содержимое совпало
            discard_download(result)
            return YaDiskResult.OK
        if result.local_newer and not overwrite_newer:  # спросить некого: локальные правки не затирать
            discard_download(result)
            raise YandexDiskError(
                f"{result.warnings[0]}; база не заменена",  # причина
                operation   =   'скачивание',               # что делали
                remote_path =   result.remote.path,         # файл на Диске
                local_path  =   result.local_path,          # рабочая база
            )
        install_checked_download(result)
        return YaDiskResult.OK

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def upload_sync(
        self,
        progress_callback : Optional[Callable[[int, int], Any]] = None, # прогресс: (передано, всего)
    ) -> int: # YaDiskResult.OK — файл базы выгружен
        """
        Выгружает ``local_path`` на Яндекс.Диск, заменяя файл там (в этом потоке, с ожиданием).

        Перед выгрузкой — резервная копия рабочей базы (:func:`backup_db_before_transfer`).
        Ошибки — исключениями (``if_err=True``): код результата при успехе всегда ``OK``.
        Файл на Диске перезаписывается (``overwrite=True``, как у окна).

        Args:
            progress_callback : (callable/None) Вызывается с ``(передано, всего)`` байт;
                None — без прогресса.

        Returns:
            (int) ``YaDiskResult.OK`` (0).

        Raises:
            YandexDiskBackupError: Резервная копия не удалась, выгрузка не начата.
            ConnectionError: Токен недействителен или нет связи.
            FileNotFoundError: Локального файла базы нет.
            Exception: Прочая ошибка выгрузки.

        Example:
            >>> get_sync_service().upload_sync()     # doctest: +SKIP — живой запрос
            <YaDiskResult.OK: 0>
        """
        # вызов функции yadisk_upload_file с параметрами, сохраненными в __init__
        # return yadisk_upload_file(
        #     ya_token=self.token,
        #     local_file_path=self.local_path,
        #     ya_file_path=self.remote_path,
        #     if_err=True,
        #     progress_callback=progress_callback
        # )

        # yadisk_upload_file вызывает функцию yadisk_upload_file с параметрами,
        # сохраненными в __init__, и передает прогресс загрузки
        # в колбэк _progress_callback.
        # Если возникнет какая-либо ошибка, то сообщение об ошибке
        # передается в колбэк error.
        backup_db_before_transfer(self.local_path)
        return yadisk_upload_file(
            ya_token=self.token,
            local_file_path=self.local_path,
            ya_file_path=remote_db_file_path(self.remote_path, self.local_path),
            # ya_file_path=self.remote_path,
            # ↑ до rework-sync-service (2026-10-21): папка из настроек шла как путь к файлу
            if_err=True,
            progress_callback=progress_callback,
            # Файл БД на Диске заменяется (как у окна); без этого повторная выгрузка
            # падала — файл уже есть
            overwrite=True,
        )
    
    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def prepare_download(self) -> DownloadThread:
        """
        Возвращает настроенный, но ещё не запущенный поток для скачивания.
        
        Это метод возвращает настроенный, но не запущенный поток DownloadThread.
        Поток будет скачивать файл с Яндекс.Диска в локальную файловую систему.
        Он будет вызывать функцию _progress_callback для обновления прогресса.

        Example:
            >>> sync_service.prepare_download().start()   # поток запускает вызывающий
        """
        # Создаем настроенный, но не запущенный поток DownloadThread
        thread = DownloadThread(
            token=self.token, 
            remote_path=remote_db_file_path(self.remote_path, self.local_path),
            # remote_path=self.remote_path,
            # ↑ до rework-sync-service (2026-10-21): папка из настроек шла как путь к файлу
            local_path=self.local_path
        )

        # Можно добавить общие обработчики, но лучше оставить GUI подключаться
        # к сигналам и слотам потока
        
        return thread

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def prepare_upload(self) -> UploadThread:
        """
        Возвращает настроенный, но ещё не запущенный поток для загрузки.

        Это метод возвращает настроенный, но не запущенный поток UploadThread.
        Поток будет загружать файл из локальной файловой системы на Яндекс.Диск.
        Он будет вызывать функцию _progress_callback для обновления прогресса.

        Example:
            >>> sync_service.prepare_upload().start()   # поток запускает вызывающий
        """
        thread = UploadThread(
            token=self.token, 
            local_path=self.local_path, 
            remote_path=remote_db_file_path(self.remote_path, self.local_path),
            # remote_path=self.remote_path
            # ↑ до rework-sync-service (2026-10-21): папка из настроек шла как путь к файлу
            # Файл БД на Диске заменяется (как у окна)
            overwrite=True,
        )

        return thread
    
    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def reload_config(self) -> None:
        """Перезагружает токен и пути из текущей конфигурации.

        Example:
            >>> sync_service.reload_config()
        """
        # from app.config.config_manager.manager import AppConfigManager
        
        config = AppConfigManager.get_instance()

        self.token = config.get('YANDEX_TOKEN')
        self.remote_path = config.get('database_remote_path')
        self.local_path = config.get('database_local_path')

        self.logger.info("Конфигурация SyncService обновлена")
