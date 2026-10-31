# app/database/database.py
"""
Управление подключением к SQLite базе данных.

Модуль предоставляет класс :class:`Database`: движок SQLAlchemy, сессии потока
(``scoped_session``), контекстный менеджер ``session_scope`` (коммит / откат), отложенные
удаления файлов и действия после коммита / отката (обработчики событий сессии, ТД-9),
доведение базы до последней схемы миграциями при открытии (``app/database/migrate.py``).

Ошибки (2026-10-31, М8): отказ открыть базу — ``DatabaseConnectionError``, нарушение
целостности в ``session_scope`` — ``DbIntegrityError``; значения запросов (личные данные) в
ошибках скрыты, для отладки — ``Database(log_sql_params=True)`` (настройка
``LOG_SQL_PARAMS``). Подробно — ``app/database/IMPLEMENTATION.md`` §6, §9.

Example:
    >>> db = Database(
    ...     'sqlite:///clinic.db',   # файл базы
    ... )
    >>> with db.session_scope() as session:
    ...     patients = session.query(Patient).all()
    >>> db.close()
"""
# ↑ до 2026-10-31 (М8): описание без ошибок и отложенных действий, «Пример использования:».
# import os
# ↑ до 2026-10-31 (М8): не используется (pyflakes).

# Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

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


from app.utils.deferred_actions import ActionType, clear_actions_by_type, execute_actions, get_actions_by_type
from app.utils.logger.logger import AppLogger

from app.utils.file_deletions import (
    del_file_and_parent_dir, get_deletions_by_type,
    DeletionType, clear_deletions_by_type, ensure_deletions_dict
)
# try:
from app.database.database_shema.clinic import Base as Base
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..backend.bd.clinic import Base as Base
#     except ImportError as e:
#         pass #  raise # e # pass


# try:
from app.database.database_shema.temp_data_bd import populate_test_data
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..backend.bd.temp_data_bd import populate_test_data
#     except ImportError as e:
#         pass #  raise # e # pass

# Сторонние библиотеки

from sqlalchemy import create_engine, event
from sqlalchemy import exc as sa_exc   # ошибки драйвера — имена совпадают с исключениями приложения
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional, Tuple
import os     # резервная копия базы (backup_sqlite_database)
import re
import sqlite3
import time   # метка времени в имени резервной копии

from app.exceptions import AppException, DatabaseConnectionError, DbIntegrityError


# @AppLogger.get_instance(
#     name='api.Database',
#     enable_file_logging='system',
#     use_name_in_filename=False,  # 'system'
# ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
# ↑ до 2026-10-31 (М8): декоратор прежнего _make_deletion_handler остался здесь после ТД-9 —
#   через комментарии и пустые строки он оборачивал следующую функцию,
#   _discard_other_deletions; перенесён к _make_deletion_handler.
# def _make_deletion_handler(deletion_type: DeletionType):
#     """Создаёт обработчик для указанного типа отложенного удаления."""
#     logger = AppLogger.get_instance(
#         name='Database',
#         enable_file_logging='user',
#         use_name_in_filename=False,
#     )
#     @AppLogger.get_instance(
#         name='api.Database',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
#     def handler(session, *args):
#         items = get_deletions_by_type(session, deletion_type)
#         if not items:
#             return
#
#         failed_items = []
#         for item in items:
#             try:
#                 del_file_and_parent_dir(
#                     file_path=item['path'],
#                     remove_parent_if_empty=item.get('remove_parent_if_empty', False),
#                     force=item.get('force', False),
#                     logger=logger,
#                 )
#             except Exception as e:
#                 logger.warning(f"Ошибка удаления {item['path']}: {e}")
#                 failed_items.append(item)
#
#         clear_deletions_by_type(session, deletion_type)
#
#         if failed_items:
#             session._deletions[deletion_type].extend(failed_items)
#
#     return handler
# ↑ до 2026-10-30 (ТД-9): чистился только список своего события. Сессия — scoped_session
#   (одна на поток, close() её не заменяет), поэтому удаления «после коммита» из
#   откатившейся транзакции выполнял следующий чужой коммит, а «при откате» из
#   закоммиченной (новый файл фото) — следующий чужой откат: удалялся сохранённый файл.


def _discard_other_deletions(
    session  : Any,           # сессия со списками удалений
    finished : DeletionType,  # чем закончилась транзакция (COMMIT / ROLLBACK)
) -> None: # отбрасывает удаления противоположного события
    """
    Отбрасывает отложенные удаления противоположного события: транзакция закончилась
    ``finished``, и записи другого списка к ней больше не относятся.

    Записи с пометкой ``retry`` (удаление уже пытались выполнить своим событием, и оно не
    удалось — например, файл занят) остаются: их повторит следующее событие их вида.

    Args:
        session  : (Any) Сессия SQLAlchemy со словарём ``_deletions``.
        finished : (DeletionType) Событие, которым закончилась транзакция.

    Example:
        >>> _discard_other_deletions(
        ...     session,                 # закоммиченная сессия
        ...     DeletionType.COMMIT,     # закончилась коммитом
        ... )
        >>> get_deletions_by_type(session, DeletionType.ROLLBACK)
        []
    """
    other = DeletionType.ROLLBACK if finished is DeletionType.COMMIT else DeletionType.COMMIT
    items = get_deletions_by_type(session, other)
    items[:] = [item for item in items if item.get('retry')]


@AppLogger.get_instance(
    name                 = 'api.Database',  # журнал вызовов
    enable_file_logging  = 'system',        # системный файл
    use_name_in_filename = False,           # имя не в имени файла
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG'),
)
def _make_deletion_handler(
    deletion_type : DeletionType,  # событие обработчика (COMMIT — after_commit, ROLLBACK — after_rollback)
) -> Callable[..., None]: # обработчик события сессии
    """
    Создаёт обработчик события сессии для отложенных удалений вида ``deletion_type``.

    Обработчик: 1) отбрасывает удаления противоположного события (ТД-9, кроме повторов);
    2) удаляет файлы своего списка; 3) неудавшиеся оставляет в списке с пометкой ``retry`` —
    их повторит следующее событие того же вида, даже если между ними была транзакция
    другого вида.

    Args:
        deletion_type : (DeletionType) Какой список выполняет обработчик.

    Returns:
        (Callable[..., None]) Обработчик ``handler(session, *args)``.

    Example:
        >>> event.listen(
        ...     Session,                                    # фабрика сессий
        ...     'after_commit',                             # событие
        ...     _make_deletion_handler(DeletionType.COMMIT),
        ... )
    """
    logger = AppLogger.get_instance(
        name                 = 'Database', # журнал базы
        enable_file_logging  = 'user',     # файл пользователя
        use_name_in_filename = False,      # имя не в имени файла
    )

    @AppLogger.get_instance(
        name                 = 'api.Database', # журнал вызовов
        enable_file_logging  = 'system',       # системный файл
        use_name_in_filename = False,          # имя не в имени файла
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG'),
    )
    def handler(
        session : Any,  # сессия, транзакция которой закончилась
        *args   : Any,  # прочие аргументы события (не используются)
    ) -> None: # выполняет удаления своего события
        """
        Выполняет отложенные удаления своего события и отбрасывает удаления противоположного.

        Args:
            session : (Any) Сессия SQLAlchemy.
            *args   : (Any) Прочие аргументы события.

        Example:
            >>> handler(session)
        """
        # транзакция закончилась — записи противоположного события к ней больше не относятся
        _discard_other_deletions(
            session,
            deletion_type,
        )

        items = get_deletions_by_type(session, deletion_type)
        if not items:
            return

        failed_items = []
        for item in items:
            try:
                del_file_and_parent_dir(
                    file_path              = item['path'],
                    remove_parent_if_empty = item.get('remove_parent_if_empty', False),
                    force                  = item.get('force', False),
                    logger                 = logger,
                )
            except Exception as e:
                logger.warning(f"Ошибка удаления {item['path']}: {e}")
                item['retry'] = True  # повтор — следующим событием этого вида
                failed_items.append(item)

        clear_deletions_by_type(session, deletion_type)

        if failed_items:
            session._deletions[deletion_type].extend(failed_items)

    return handler


def _unicode_lower(
    value : Any,   # значение столбца
) -> Any: # строка в нижнем регистре или значение как есть
    """
    Возвращает ``lower()`` для SQLite, понимающий все буквы (встроенный — только латиницу).

    Args:
        value : (Any) Значение столбца (не строка — как есть, ``NULL`` — ``NULL``).

    Returns:
        (Any) Строка в нижнем регистре или исходное значение.

    Example:
        >>> _unicode_lower(
        ...     'ИВАНОВ',   # кириллица
        ... )
        'иванов'
    """
    return value.lower() if isinstance(value, str) else value


def _unicode_upper(
    value : Any,   # значение столбца
) -> Any: # строка в верхнем регистре или значение как есть
    """
    Возвращает ``upper()`` для SQLite, понимающий все буквы.

    Args:
        value : (Any) Значение столбца (не строка — как есть).

    Returns:
        (Any) Строка в верхнем регистре или исходное значение.

    Example:
        >>> _unicode_upper(
        ...     'иванов',   # кириллица
        ... )
        'ИВАНОВ'
    """
    return value.upper() if isinstance(value, str) else value


def _register_unicode_functions(
    dbapi_connection  : sqlite3.Connection,   # соединение sqlite3
    connection_record : Any,                  # запись пула (не используется)
) -> None: # подменяет lower / upper соединения на понимающие Юникод
    """
    Подменяет ``lower`` / ``upper`` соединения SQLite на понимающие Юникод (APP1).

    Args:
        dbapi_connection  : (sqlite3.Connection) Соединение.
        connection_record : (Any) Запись пула (не используется).

    Example:
        >>> event.listen(
        ...     engine,                        # движок
        ...     'connect',                     # новое соединение
        ...     _register_unicode_functions,   # обработчик
        ... )
    """
    dbapi_connection.create_function(
        'lower',               # имя функции SQL
        1,                     # число аргументов
        _unicode_lower,        # реализация
        deterministic = True,  # один результат на одно значение
    )
    dbapi_connection.create_function(
        'upper',               # имя функции SQL
        1,                     # число аргументов
        _unicode_upper,        # реализация
        deterministic = True,  # один результат на одно значение
    )


# Сообщения SQLite о нарушении целостности → текст пользователю (DbIntegrityError.detail)
_INTEGRITY_TEXTS : Tuple[Tuple[str, str], ...] = (
    ('UNIQUE constraint failed',      'повтор значения, которое должно быть уникальным'),
    ('NOT NULL constraint failed',    'не заполнено обязательное поле'),
    ('FOREIGN KEY constraint failed', 'нет связанной записи или на запись ссылаются другие'),
    ('CHECK constraint failed',       'значение не прошло проверку'),
)

# Операция и таблица запроса: INSERT [OR …] INTO t / UPDATE [OR …] t / DELETE FROM t
_STATEMENT_TARGET = re.compile(
    r'\s*(INSERT|UPDATE|DELETE)\b(?:\s+OR\s+\w+)?\s+(?:INTO\s+|FROM\s+)?"?(\w+)"?',
    re.IGNORECASE,
)


def _statement_target(
    statement : Optional[str],   # текст SQL (None — неизвестен)
) -> Tuple[Optional[str], Optional[str]]: # (операция, таблица) запроса изменения данных
    """
    Возвращает операцию (``INSERT`` / ``UPDATE`` / ``DELETE``) и таблицу из текста запроса
    изменения данных; другой запрос или нет текста — ``(None, None)``.

    Args:
        statement : (str/None) Текст SQL; None — неизвестен.

    Returns:
        (Tuple[Optional[str], Optional[str]]) Операция заглавными и имя таблицы.

    Example:
        >>> _statement_target(
        ...     'INSERT INTO patients (last_name) VALUES (?)',   # добавление
        ... )
        ('INSERT', 'patients')
        >>> _statement_target(
        ...     'SELECT 1',   # не изменение данных
        ... )
        (None, None)
    """
    match = _STATEMENT_TARGET.match(statement or '')
    if match is None:
        return None, None
    return match.group(1).upper(), match.group(2)


def _integrity_detail(
    message : str,   # сообщение SQLite (``UNIQUE constraint failed: patients.phone``)
) -> str: # что нарушено — понятным текстом
    """
    Возвращает понятный текст нарушения целостности по сообщению SQLite: вид нарушения и,
    если SQLite его назвал, поле (``таблица.поле``); незнакомое сообщение — как есть.

    Args:
        message : (str) Сообщение драйвера.

    Returns:
        (str) Текст для ``DbIntegrityError.detail`` (часть сообщения пользователю).

    Example:
        >>> _integrity_detail(
        ...     'UNIQUE constraint failed: patients.phone',   # повтор телефона
        ... )
        'повтор значения, которое должно быть уникальным (patients.phone)'
        >>> _integrity_detail(
        ...     'FOREIGN KEY constraint failed',   # без поля
        ... )
        'нет связанной записи или на запись ссылаются другие'
    """
    for prefix, text in _INTEGRITY_TEXTS:
        if message.startswith(prefix):
            target = message[len(prefix):].lstrip(':').strip()
            return f"{text} ({target})" if target else text
    return message


def _integrity_error(
    exc            : sa_exc.IntegrityError,   # ошибка драйвера
    log_sql_params : bool,                    # значения запроса — в подробности
) -> DbIntegrityError: # исключение приложения для ошибки целостности
    """
    Строит ``DbIntegrityError`` по ``sqlalchemy.exc.IntegrityError``: текст пользователю —
    что нарушено (``_integrity_detail``); ``details`` — таблица, операция, текст SQL и,
    только при ``log_sql_params``, значения запроса (личные данные — по умолчанию не
    пишутся); исходная ошибка — ``original`` явно (``exc.orig``, ``sqlite3.IntegrityError``):
    ``session_scope`` пишет журнал до ``raise … from exc``, когда цепочки ещё нет.

    Args:
        exc            : (sqlalchemy.exc.IntegrityError) Ошибка драйвера.
        log_sql_params : (bool) Добавить значения запроса в ``details``.

    Returns:
        (DbIntegrityError) Исключение для ``raise … from exc``.

    Example:
        >>> error = _integrity_error(
        ...     exc,            # повтор телефона
        ...     False,          # значения не писать
        ... )
        >>> str(error)
        '[6001] Нарушение целостности данных: повтор значения, которое должно быть уникальным (patients.phone)'
        >>> error.details['таблица']
        'patients'
    """
    operation, table = _statement_target(
        exc.statement,   # текст SQL
    )
    details : Dict[str, Any] = {
        'таблица'  : table,           # куда писали
        'операция' : operation,       # INSERT / UPDATE / DELETE
        'SQL'      : exc.statement,   # текст запроса без значений
    }
    if log_sql_params: # отладка: значения запроса (личные данные)
        details['параметры'] = exc.params
    driver_error = exc.orig if exc.orig is not None else exc
    return DbIntegrityError(
        _integrity_detail(
            str(driver_error),   # сообщение драйвера
        ),
        details  = {key: value for key, value in details.items() if value is not None},
        original = driver_error,   # явно: журнал пишется до raise … from (цепочки ещё нет)
    )


def backup_sqlite_database(
    engine : Any,   # движок SQLAlchemy базы (Engine)
    label  : str,   # метка в имени копии (ревизия миграции, 'merge' …)
) -> Optional[str]: # резервная копия файла SQLite рядом с базой
    """
    Делает резервную копию файла базы SQLite рядом с ним: ``<файл>.bak-<ГГГГММДД_ЧЧММСС>-<метка>``.

    Копия — через backup-API SQLite (M8, 2026-10-18), а не копированием файла: в режиме
    WAL свежие изменения лежат в отдельном файле ``-wal`` и, пока базу держит открытой
    другая программа, в основной файл не сливаются — копия файла их теряла. Backup-API
    даёт согласованный снимок в любом режиме журнала. Существующая копия с тем же именем
    не перезаписывается (к имени добавляется ``-N``). Перед копией закрываются свободные
    соединения движка (``dispose``).

    Вынесено 2026-10-31 из ``migrate._backup`` (тот теперь вызывает эту функцию): копия
    нужна и перед объединением пациентов (Ф1.6.10а).

    Args:
        engine : (Engine) Движок базы.
        label  : (str) Метка в имени копии.

    Returns:
        (str/None) Путь к копии; None — не SQLite-файл, база в памяти или файла нет.

    Example:
        >>> backup_sqlite_database(
        ...     db.engine,   # движок базы
        ...     'merge',     # метка
        ... )
        'clinic.db.bak-20261031_211500-merge'
    """
    path = engine.url.database
    if engine.url.get_backend_name() != 'sqlite' or not path or path == ':memory:' or not os.path.exists(path):
        return None
    stamp = time.strftime('%Y%m%d_%H%M%S')
    backup = f"{path}.bak-{stamp}-{label}"
    n = 1
    while os.path.exists(backup): # копию с тем же именем не затирать
        backup = f"{path}.bak-{stamp}-{label}-{n}"
        n += 1
    engine.dispose()            # закрыть свободные соединения приложения
    source = sqlite3.connect(path)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


class Database:
    """
    Подключение к базе SQLite: движок, сессии потока и ``session_scope``.

    При создании доводит базу до последней версии схемы миграциями (``upgrade_database``;
    до 2026-10-16 — ``Base.metadata.create_all``). На фабрику сессий (свою у каждого
    объекта — ``sessionmaker``) один раз регистрируются обработчики ``after_commit`` /
    ``after_rollback``: отложенные удаления файлов (``session._deletions``) и действия
    (``session._actions``) своего события выполняются, противоположного — отбрасываются
    (ТД-9; неудавшееся удаление повторяется следующим событием своего вида).

    Attributes:
        engine         : (sqlalchemy.engine.Engine) Движок.
        Session        : (scoped_session) Фабрика сессий, одна сессия на поток.
        log_sql_params : (bool) Значения запросов видны в ошибках и журнале.
        logger         : (AppLogger) Журнал базы (создаётся при первом обращении).

    Example:
        >>> db = Database(
        ...     'sqlite:///clinic.db',   # файл базы
        ... )
        >>> with db.session_scope() as session:
        ...     patients = session.query(Patient).all()
        >>> db.close()
    """
    # ↑ до 2026-10-31 (М8): описание называло create_all, прежние _pending_deletions,
    #   delete_pending_files, _after_commit_registered (их нет с 31.05 / 16.10).


    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger: # журнал базы (создаётся при первом обращении)
        """
        Возвращает журнал базы; создаётся при первом обращении (``api.Database``, файл
        пользователя) — так он есть и у объекта, созданного без ``__init__``.

        Returns:
            (AppLogger) Журнал.

        Example:
            >>> db.logger.debug('сообщение')
        """
        try:
            return self._logger
        except AttributeError:
            self._logger = AppLogger.get_instance(
                name                 = 'api.Database',   # журнал базы
                enable_file_logging  = 'user',           # файл пользователя
                use_name_in_filename = False,            # имя не в имени файла
            )

        return self._logger

    @logger.setter
    def logger(
        self,
        value : AppLogger,   # свой журнал (например, заглушка в тестах)
    ) -> None: # подменяет журнал базы
        """
        Подменяет журнал базы.

        Args:
            value : (AppLogger) Журнал.

        Example:
            >>> db.logger = AppLogger.get_instance('test')
        """
        self._logger = value

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # def __init__(self, db_url: str):
    # ↑ до 2026-10-31 (М8): без флага значений запросов; описание называло create_all.
    def __init__(
        self,
        db_url         : str,            # URL базы ('sqlite:///clinic.db')
        *,
        log_sql_params : bool = False,   # значения запросов — в журнал (отладка)
    ) -> None:
        """
        Открывает базу: движок, фабрика сессий, обработчики отложенных удалений и действий;
        доводит базу до последней версии схемы (``upgrade_database``: новая — создаётся,
        старая — приводится и обновляется, перед изменением — резервная копия).

        Значения запросов (ФИО, телефоны, тексты — личные данные) в ошибках SQLAlchemy по
        умолчанию скрыты (``hide_parameters``): их пишут в журнал трассировки и
        ``DbIntegrityError``. ``log_sql_params=True`` (настройка ``LOG_SQL_PARAMS``) — для
        отладки: значения видны, при открытии — предупреждение в журнал.

        Для SQLite — ``check_same_thread=False`` (сессии из разных потоков) и свои
        ``lower`` / ``upper`` для всех букв (APP1).

        Args:
            db_url         : (str) URL подключения (``sqlite:///database.db``).
            log_sql_params : (bool) Писать значения запросов в журнал.

        Raises:
            DatabaseConnectionError: Ошибка драйвера при открытии или обновлении базы
                (занята, нет доступа, файл не открывается); исходная — в цепочке
                (``original``), текст — ``migrate.database_error_text``.
            MigrationError: Базу нельзя безопасно обновить (как раньше).

        Example:
            >>> db = Database(
            ...     'sqlite:///clinic.db',   # файл базы
            ... )
            >>> db.log_sql_params
            False
        """
        self.log_sql_params = log_sql_params

        # self.engine = create_engine(
        #     db_url,
        #     echo=False,
        #     future=True,
        #     connect_args={"check_same_thread": False},
        # )
        # ↑ до 2026-10-31 (М8): значения запросов всегда попадали в текст ошибок SQLAlchemy
        #   (и в журнал — трассировкой).
        self.engine = create_engine(
            db_url,
            echo            = False,                            # без журнала SQL
            future          = True,                             # стиль SQLAlchemy 2.0
            hide_parameters = not log_sql_params,               # значения запросов в ошибках
            connect_args    = {"check_same_thread": False},     # сессии из разных потоков
        )
        if log_sql_params: # отладка — личные данные в журнале
            self.logger.warning(
                "В журнал пишутся значения запросов к базе (личные данные) — "
                "настройка LOG_SQL_PARAMS"
            )
        # APP1 (2026-10-18): поиск «без учёта регистра» (ilike → lower(...) LIKE lower(...))
        # по кириллице на деле УЧИТЫВАЛ регистр: встроенный lower() SQLite понимает только
        # латиницу («иван» не находил «Иванов»). Свой lower — для всех букв (Юникод).
        if self.engine.url.get_backend_name() == 'sqlite':
            event.listen(self.engine, 'connect', _register_unicode_functions)

        Session = sessionmaker(
            bind   = self.engine,   # движок
            future = True,          # стиль SQLAlchemy 2.0
        )

        # Регистрация обработчиков
        if not hasattr(Session, '_deletion_handlers_registered'):  # Флаг для однократной регистрации
            event.listen(
                Session,                                        # фабрика сессий
                "after_commit",                                 # после коммита
                _make_deletion_handler(DeletionType.COMMIT),    # удаления «после коммита»
            )
            event.listen(
                Session,                                        # фабрика сессий
                "after_rollback",                               # после отката
                _make_deletion_handler(DeletionType.ROLLBACK),  # удаления «при откате»
            )
            Session._deletion_handlers_registered = True

        # Регистрация обработчиков для отложенных действий (обновлений UI)
        if not hasattr(Session, '_deferred_actions_registered'):
            # from app.utils.deferred_actions import (
            #     get_actions_by_type, clear_actions_by_type, execute_actions,
            #     ActionType
            # )

            logger = AppLogger.get_instance(
                name                 = 'api.Database',   # журнал базы
                # share_file_with = 'system',
                enable_file_logging  = 'user',           # файл пользователя
                use_name_in_filename = False,            # 'system',
            )

            # @event.listens_for(Session, "after_commit")
            # def execute_commit_actions(session, *args):
            #     actions = get_actions_by_type(session, ActionType.COMMIT)
            #     if actions:
            #         execute_actions(actions, logger=logger)
            #         clear_actions_by_type(session, ActionType.COMMIT)
            #
            # @event.listens_for(Session, "after_rollback")
            # def execute_rollback_actions(session, *args):
            #     actions = get_actions_by_type(session, ActionType.ROLLBACK)
            #     if actions:
            #         execute_actions(actions, logger=logger)
            #         clear_actions_by_type(session, ActionType.ROLLBACK)
            # ↑ до 2026-10-30 (ТД-9): список противоположного события не чистился — действие
            #   «после коммита» из откатившейся транзакции выполнял следующий чужой коммит
            #   той же сессии (scoped_session), «при откате» из закоммиченной — чужой откат.

            @event.listens_for(Session, "after_commit")
            def execute_commit_actions(
                session : Any,  # закоммиченная сессия
                *args   : Any,  # прочие аргументы события (не используются)
            ) -> None: # выполняет действия «после коммита», отбрасывает «при откате»
                """
                Выполняет отложенные действия «после коммита» и отбрасывает действия «при
                откате» (транзакция закоммичена — они к ней больше не относятся, ТД-9).

                Args:
                    session : (Any) Сессия SQLAlchemy.
                    *args   : (Any) Прочие аргументы события.

                Example:
                    >>> execute_commit_actions(session)
                """
                clear_actions_by_type(session, ActionType.ROLLBACK)
                actions = get_actions_by_type(session, ActionType.COMMIT)
                if actions:
                    execute_actions(
                        actions,
                        logger = logger,
                    )
                    clear_actions_by_type(session, ActionType.COMMIT)

            @event.listens_for(Session, "after_rollback")
            def execute_rollback_actions(
                session : Any,  # откатившаяся сессия
                *args   : Any,  # прочие аргументы события (не используются)
            ) -> None: # выполняет действия «при откате», отбрасывает «после коммита»
                """
                Выполняет отложенные действия «при откате» и отбрасывает действия «после
                коммита» (транзакция откатилась — они к ней больше не относятся, ТД-9).

                Args:
                    session : (Any) Сессия SQLAlchemy.
                    *args   : (Any) Прочие аргументы события.

                Example:
                    >>> execute_rollback_actions(session)
                """
                clear_actions_by_type(session, ActionType.COMMIT)
                actions = get_actions_by_type(session, ActionType.ROLLBACK)
                if actions:
                    execute_actions(
                        actions,
                        logger = logger,
                    )
                    clear_actions_by_type(session, ActionType.ROLLBACK)

            Session._deferred_actions_registered = True

        # # Регистрируем обработчик только один раз для данного класса сессии
        # if not hasattr(Session, '_after_commit_registered'):
        #
        #     logger = self.logger
        #
        #     # Регистрируем обработчик отложенного удаления файлов (один раз для всех сессий)
        #     # @event.listens_for(self.Session, "after_commit")
        #
        #     # Регистрация обработчика отложенного удаления файлов.
        #     # Каждый экземпляр Database создаёт свой класс сессии через sessionmaker,
        #     # поэтому регистрация для этого конкретного класса сессии выполняется
        #     # ровно один раз. Если в будущем будет создан новый экземпляр Database
        #     # (например, при перезагрузке конфигурации), он создаст новый класс
        #     # сессии и новый обработчик – это корректно, так как старый экземпляр
        #     # Database будет закрыт и больше не используется.
        #     @event.listens_for(Session, "after_commit")
        #     def delete_pending_files(session, *args):
        #         if not hasattr(session, '_pending_deletions'):
        #             logger.warning("session._pending_deletions не определён")
        #             return
        #
        #         items_error = []
        #
        #         items = session._pending_deletions.copy()
        #         session._pending_deletions.clear()
        #
        #         for item in items:
        #             try:
        #                 # Поддержка старого формата (строка) и нового (словарь)
        #                 if isinstance(item, str):
        #                     path = item  # указатель на файл
        #                     remove_parent_if_empty = False # нужно ли удалять род папку
        #                     force = False # нужно ли удалять род папку если она не пустая
        #
        #                 elif isinstance(item, dict):
        #                     path = item.get('path')
        #                     remove_parent_if_empty = item.get('remove_parent_if_empty', False)
        #                     force = item.get('force', False)
        #
        #                 else:
        #                     err_text = f"Unexpected item type: {type(item)}"
        #                     logger.error(err_text)
        #                     raise ValueError(err_text)
        #
        #                 if not path:
        #                     logger.warning("Попытка запланировать удаление пустого пути, игнорируем")
        #                     continue
        #
        #                 del_file_and_parent_dir( # физическое удаление
        #                     file_path = path,
        #                     remove_parent_if_empty = remove_parent_if_empty,
        #                     force = force,
        #                     logger = logger
        #                 )
        #
        #             except Exception as e:
        #                 logger.warning(f"Ошибка при удалении {item}: {e}")
        #
        #                 # при ошибке переходим к следующему элементу
        #                 items_error.append(item)
        #
        #         # после цикла список должен быть пуст, но на всякий случай:
        #         session._pending_deletions = items_error + session._pending_deletions
        #
        #     Session._after_commit_registered = True

        self.Session = scoped_session(
            Session,   # одна сессия на поток
        )

        # # Автоматическое создание таблиц (если их нет)
        # Base.metadata.create_all(self.engine)
        # ↑ до 2026-10-16 (миграции): create_all только СОЗДАЁТ недостающие таблицы — новые
        #   столбцы и индексы в существующую базу не добавлял (у настоящей базы проекта не
        #   было индекса ix_appointment_note_text). Теперь база доводится до последней
        #   версии схемы миграциями Alembic (app/database/migrate.py): новая — создаётся,
        #   старая без отметки — приводится к исходной схеме, остальные — обновляются;
        #   перед изменением существующей базы — резервная копия файла.
        from app.database.migrate import database_error_text, upgrade_database
        # upgrade_database(self.engine)
        # ↑ до 2026-10-31 (М8, Ф1.6.7в): ошибка драйвера уходила наружу как есть — текст
        #   пользователю строил только startup_error_text окна запуска.
        try:
            upgrade_database(self.engine)
        except (sa_exc.DatabaseError, sqlite3.Error) as exc: # драйвер: занята, нет доступа
            self.engine.dispose()  # соединения пула не держат файл
            raise DatabaseConnectionError(
                database_error_text(
                    exc,   # ошибка драйвера
                ),
                details = {
                    'база'     : self.engine.url.database,                # файл
                    'операция' : 'открытие базы и обновление схемы',      # что делали
                },
            ) from exc

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_session(self) -> Any: # сессия текущего потока
        """
        Возвращает сессию текущего потока (``scoped_session``: в одном потоке — та же
        сессия, не новая).

        Note:
            Лучше ``session_scope()``: он сам коммитит / откатывает и закрывает сессию, а
            откат блока без запросов проводит через обработчики (ТД-9) — сессия,
            откаченная вручную без транзакции, этой защиты не получает.

        Returns:
            (Session) Сессия SQLAlchemy.

        Example:
            >>> session = db.get_session()
        """
        # ↑ до 2026-10-31 (М8): описание — «новую сессию» (у scoped_session — та же на поток).

        return self.Session()

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @contextmanager
    # def session_scope(self):
    # ↑ до 2026-10-31 (М8): без аннотации возврата.
    def session_scope(self) -> Iterator[Any]: # сессия на блок with: коммит или откат
        """
        Даёт сессию на блок ``with``: без ошибки — коммит, с ошибкой — откат и повторный
        выброс исключения; в конце сессия закрывается.

        Ошибки (2026-10-31, М8, Ф1.6.7в): ``sqlalchemy.exc.IntegrityError`` (повтор
        уникального, пустое обязательное поле, внешний ключ — в блоке или при коммите)
        выбрасывается как ``DbIntegrityError`` (``raise … from exc``: текст пользователю —
        что нарушено, ``details`` — таблица, операция, SQL, значения — только при
        ``log_sql_params``; исходная ``sqlite3.IntegrityError`` — ``original``); остальные —
        как есть. Журнал пишет этот метод — ``log_text()`` исключения приложения (иначе
        ``Ошибка: <текст>``) с трассировкой; кто ловит выше, второй раз не пишет.

        Порядок: 1) сессия потока (``scoped_session`` — одна на поток, ``close()`` её не
        заменяет); 2) словарь отложенных удалений ``session._deletions`` (COMMIT / ROLLBACK);
        3) блок; 4) коммит — обработчики ``after_commit`` выполняют удаления и действия
        «после коммита» и отбрасывают «при откате»; при ошибке — откат: обработчики
        ``after_rollback`` наоборот. Если в блоке не было запросов (транзакция не
        начиналась), перед откатом начинается пустая транзакция — иначе SQLAlchemy не
        вызывает ``after_rollback``, и списки блока достались бы следующей транзакции (ТД-9).
        ``session.remove()`` не вызывается — привязка к потоку остаётся.

        Returns:
            (Iterator[Any]) Сессия SQLAlchemy на время блока.

        Raises:
            DbIntegrityError: Нарушение целостности — после отката.
            Exception: Любое другое исключение блока или коммита — после отката, как есть.

        Example:
            >>> with db.session_scope() as session:
            ...     patients = session.query(Patient).all()
        """
        # ↑ до 2026-10-30 (ТД-9): описание называло прежний список _pending_deletions и
        #   обещало «удаление привязки к потоку» (remove закомментирован).
        session = self.get_session()

        # # Создаём список для отложенных удалений, привязанный к сессии
        # if not hasattr(session, '_pending_deletions'):
        #     session._pending_deletions = []
        ensure_deletions_dict(session)  # гарантируем наличие _deletions
        try:
            # Возвращает сессию в контексте with
            yield session

            # Если в контексте не было ошибок, коммитит сессию
            session.commit()

            self.logger.debug(f"Коммит сессии: {session}")

        except Exception as e:
            # self.logger.exception(f"Ошибка: {e}")
            # ↑ до 2026-10-31 (М8, Ф1.6.7в): ошибка драйвера — в журнал и наружу как есть
            #   (вместе со значениями запроса); у исключений приложения — без подробностей.
            error : Optional[AppException] = None
            if isinstance(e, sa_exc.IntegrityError): # нарушение целостности — исключение приложения
                error = _integrity_error(
                    e,                     # ошибка драйвера
                    self.log_sql_params,   # значения запроса — по настройке
                )
            elif isinstance(e, AppException):
                error = e
            self.logger.exception(
                error.log_text() if error is not None else f"Ошибка: {e}",
            )

            # При откате просто очищаем список, файлы не удаляем
            # if hasattr(session, '_pending_deletions'):
            #     session._pending_deletions.clear()

            # Транзакция не начиналась (в блоке не было запросов к БД): rollback() тогда ничего
            # не делает и after_rollback не вызывается — отложенные удаления и действия этого
            # блока достались бы следующей транзакции потока (ТД-9). Пустая транзакция
            # соединения не открывает, её откат проходит через обработчики.
            if not session.in_transaction():
                session.begin()

            # Если была ошибка, откатывает сессию
            session.rollback()

            if error is not None and error is not e:
                raise error from e
            raise
        finally:
            # Закрывает сессию и удаляет привязку к потоку
            session.close()
            # session.remove()

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def close(self) -> None: # закрывает сессии потоков и освобождает движок
        """
        Закрывает сессии потоков (``Session.remove()`` — привязка к потокам снимается) и
        освобождает соединения движка (``engine.dispose()``).

        Вызывается при завершении работы приложения или при перезагрузке конфигурации.
        После ``close()`` объект больше не используется.

        Example:
            >>> db.close()
        """

        self.Session.remove()
        self.engine.dispose()

        self.logger.debug("Database engine disposed")

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def create_tables(
        self,
        recreate : bool = False,   # удалить все таблицы и создать заново (данные пропадут)
    ) -> None: # доводит базу до последней схемы (или пересоздаёт)
        """
        Доводит базу до последней версии схемы миграциями (``upgrade_database``; до
        2026-10-16 — ``create_all``).

        ``recreate=True`` — сначала удаляет все таблицы моделей и отметку версии
        (``alembic_version``: иначе миграции сочли бы пустую базу свежей), затем создаёт
        всё с первой миграции, без резервной копии. ``recreate=False`` — недостающие
        миграции, перед изменением — копия файла.

        Note:
            ``recreate=True`` удаляет все данные.

        Args:
            recreate : (bool) Пересоздать базу.

        Example:
            >>> db.create_tables(
            ...     recreate   =   True,   # тестовая база с нуля
            ... )
        """
        # ↑ до 2026-10-31 (М8): описание — «создаёт таблицы» (с 16.10 — миграции).
        if recreate:
            # Удаляет все существующие таблицы в БД
            Base.metadata.drop_all(self.engine)
            # pass
            # (2026-10-16, миграции) и отметку версии — иначе миграции сочтут пустую базу
            # свежей и таблицы не создадут
            with self.engine.begin() as conn:
                conn.exec_driver_sql('DROP TABLE IF EXISTS alembic_version')
        # # Создает новые таблицы в БД, если они не существуют
        # Base.metadata.create_all(self.engine)
        # ↑ до 2026-10-16: см. __init__ — теперь миграции
        from app.database.migrate import upgrade_database
        upgrade_database(
            self.engine,
            backup   =   not recreate,   # пересоздаваемую не копировать
        )

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def fill_test_data(self) -> None: # заполняет пустую базу тестовыми данными
        """
        Заполняет базу тестовыми данными (``populate_test_data``) в своей транзакции —
        для отладки и демонстрации.

        Note:
            Есть хотя бы один пациент — ничего не добавляется
            (``session.query(Patient).count() > 0``).

        Example:
            >>> db.fill_test_data()
        """

        with self.session_scope() as session:
            # Заполняем тестовыми данными
            populate_test_data(session)
# 0==0