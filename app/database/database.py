# app/database/database.py
"""
Управление подключением к SQLite базе данных.

Модуль предоставляет класс :class:`Database`, который инкапсулирует создание движка SQLAlchemy,
управление сессиями и контекстный менеджер для автоматической фиксации/отката изменений.

Пример использования:
    >>> db = Database("sqlite:///clinic.db")
    >>> with db.session_scope() as session:
    ...     patients = session.query(Patient).all()
    >>> db.close()
"""
import os

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
import re
import sqlite3

from app.exceptions import AppException, DatabaseConnectionError, DbIntegrityError


@AppLogger.get_instance(
    name='api.Database',
    enable_file_logging='system',
    use_name_in_filename=False,  # 'system'
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
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


def _unicode_lower(value):
    """
    ``lower()`` для SQLite, понимающий все буквы (встроенный — только латиницу).

    Args:
        value: Значение столбца (не строка — как есть, ``NULL`` — ``NULL``).

    Returns:
        Строка в нижнем регистре или исходное значение.

    Пример:
        >>> _unicode_lower('ИВАНОВ')
        'иванов'
    """
    return value.lower() if isinstance(value, str) else value


def _unicode_upper(value):
    """
    ``upper()`` для SQLite, понимающий все буквы.

    Args:
        value: Значение столбца.

    Returns:
        Строка в верхнем регистре или исходное значение.

    Пример:
        >>> _unicode_upper('иванов')
        'ИВАНОВ'
    """
    return value.upper() if isinstance(value, str) else value


def _register_unicode_functions(dbapi_connection, connection_record) -> None:
    """
    Подменяет ``lower``/``upper`` соединения SQLite на понимающие Юникод (APP1).

    Args:
        dbapi_connection: Соединение sqlite3.
        connection_record: Запись пула (не используется).

    Returns:
        None

    Пример:
        >>> event.listen(engine, 'connect', _register_unicode_functions)
    """
    dbapi_connection.create_function('lower', 1, _unicode_lower, deterministic=True)
    dbapi_connection.create_function('upper', 1, _unicode_upper, deterministic=True)


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


class Database:
    """
    Центральный класс для управления подключением к SQLite базе данных.

    Создаёт движок SQLAlchemy, фабрику сессий и предоставляет контекстный менеджер
    для безопасной работы с сессиями. При инициализации автоматически создаёт все
    таблицы, определённые в `Base.metadata`.

    Атрибуты:
        engine (sqlalchemy.engine.Engine): Движок SQLAlchemy для выполнения SQL-запросов.
        Session (scoped_session): Фабрика сессий, привязанная к текущему потоку.
        logger (AppLogger): Логгер для записи событий БД.

    **Примечание о регистрации обработчиков `after_commit` и `after_rollback`:**
        Для поддержки отложенного удаления файлов при инициализации класса сессии
        регистрируются два обработчика: один для `after_commit` (удаляет файлы из
        `session._deletions[COMMIT]`), другой для `after_rollback` (удаляет файлы из
        `session._deletions[ROLLBACK]`). Регистрация происходит один раз на класс сессии.

    Example:
        >>> db = Database("sqlite:///clinic.db")
        >>> with db.session_scope() as session:
        ...     patients = session.query(Patient).all()
        >>> db.close()

    **Примечание о регистрации обработчика `after_commit`**:
        Обработчик `delete_pending_files` регистрируется при инициализации класса
        сессии (создаваемого через `sessionmaker`) и автоматически вызывается после
        каждого успешного коммита. Для предотвращения повторной регистрации
        используется флаг `Session._after_commit_registered`.

        При откате транзакции (rollback) список отложенных удалений
        (`session._pending_deletions`) очищается, файлы не удаляются.

        Обработчик использует захваченный в замыкании логгер (`self.logger`), что
        безопасно, поскольку время жизни экземпляра `Database` совпадает с жизнью
        класса сессии.
    """


    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='api.Database',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
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
            bind=self.engine,
            future=True
        )

        # Регистрация обработчиков
        if not hasattr(Session, '_deletion_handlers_registered'):  # Флаг для однократной регистрации
            event.listen(Session, "after_commit", _make_deletion_handler(DeletionType.COMMIT))
            event.listen(Session, "after_rollback", _make_deletion_handler(DeletionType.ROLLBACK))
            Session._deletion_handlers_registered = True

        # Регистрация обработчиков для отложенных действий (обновлений UI)
        if not hasattr(Session, '_deferred_actions_registered'):
            # from app.utils.deferred_actions import (
            #     get_actions_by_type, clear_actions_by_type, execute_actions,
            #     ActionType
            # )

            logger=AppLogger.get_instance(
                name = 'api.Database',
                # share_file_with = 'system',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system',
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
            Session
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
    def get_session(self):
        """
        Возвращает новую сессию, привязанную к текущему потоку.

        Возвращает:
            Session: Объект сессии SQLAlchemy.

        Примечание:
            Рекомендуется использовать `session_scope()` вместо прямого вызова
            `get_session()`, так как контекстный менеджер автоматически управляет
            коммитом/откатом и закрытием.
        """

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
    def close(self):
        """
        Закрывает все активные сессии и освобождает ресурсы движка (удаляет привязку к потокам).

        Вызывается при завершении работы приложения или при перезагрузке конфигурации.
        После вызова `close()` объект Database больше не должен использоваться.
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
    def create_tables(self, recreate: bool = False):
        """
        Создаёт таблицы в БД.
        
        Если параметр recreate=True, то сначала удаляет все существующие таблицы в БД,
        а затем создает новые.
        Если параметр recreate=False, то просто создает новые таблицы,
        если они не существуют.

        Параметры:
            recreate (bool): Если True, все существующие таблицы удаляются перед созданием.
                             По умолчанию False.

        Предупреждение:
            Использование `recreate=True` приведёт к полной потере данных!
        """
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
        upgrade_database(self.engine, backup=not recreate)

    @AppLogger.get_instance(
        name = 'Database',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def fill_test_data(self):
        """
        Заполняет БД тестовыми данными.

        Используется для отладки и демонстрации. Вызывает `populate_test_data(session)`
        внутри собственной транзакции.

        Примечание:
            Если в таблицах уже есть данные, новые не добавляются (проверка
            `session.query(Patient).count() > 0`).
        """

        with self.session_scope() as session:
            # Заполняем тестовыми данными
            populate_test_data(session)
# 0==0