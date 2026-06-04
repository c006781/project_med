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
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager


@AppLogger.get_instance(
    name='api.Database',
    enable_file_logging='system',
    use_name_in_filename=False,  # 'system'
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def _make_deletion_handler(deletion_type: DeletionType):
    """Создаёт обработчик для указанного типа отложенного удаления."""
    logger = AppLogger.get_instance(
        name='Database',
        enable_file_logging='user',
        use_name_in_filename=False,
    )
    @AppLogger.get_instance(
        name='api.Database',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def handler(session, *args):
        items = get_deletions_by_type(session, deletion_type)
        if not items:
            return

        failed_items = []
        for item in items:
            try:
                del_file_and_parent_dir(
                    file_path=item['path'],
                    remove_parent_if_empty=item.get('remove_parent_if_empty', False),
                    force=item.get('force', False),
                    logger=logger,
                )
            except Exception as e:
                logger.warning(f"Ошибка удаления {item['path']}: {e}")
                failed_items.append(item)

        clear_deletions_by_type(session, deletion_type)

        if failed_items:
            session._deletions[deletion_type].extend(failed_items)

    return handler


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
    def __init__(self, db_url: str):
        """
        Инициализирует подключение к БД и создаёт таблицы (если их нет).

        Параметры:
            db_url (str): URL подключения к БД (например, 'sqlite:///database.db').

        Особенности:
            - Для SQLite автоматически устанавливается `check_same_thread=False`,
              чтобы разрешить использование сессий из разных потоков.
            - Таблицы создаются вызовом `Base.metadata.create_all(self.engine)`.
        """

        self.engine = create_engine(
            db_url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False},
        )

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

            @event.listens_for(Session, "after_commit")
            def execute_commit_actions(session, *args):
                actions = get_actions_by_type(session, ActionType.COMMIT)
                if actions:
                    execute_actions(actions, logger=logger)
                    clear_actions_by_type(session, ActionType.COMMIT)

            @event.listens_for(Session, "after_rollback")
            def execute_rollback_actions(session, *args):
                actions = get_actions_by_type(session, ActionType.ROLLBACK)
                if actions:
                    execute_actions(actions, logger=logger)
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

        # Автоматическое создание таблиц (если их нет)
        Base.metadata.create_all(self.engine)

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
    def session_scope(self):
        """
        Контекстный менеджер для автоматической фиксации/отката изменений.

        Обеспечивает:
            - Автоматический коммит при успешном завершении блока.
            - Откат (rollback) при возникновении исключения.
            - Закрытие сессии и удаление привязки к потоку в блоке `finally`.
            - Инициализацию атрибута `session._pending_deletions` (список путей для
              отложенного удаления файлов после коммита).

        Алгоритм:
            1. Создаёт сессию.
            2. Гарантирует наличие атрибута `_pending_deletions` (пустой список).
            3. Возвращает сессию в контексте `with`.
            4. Если в контексте не было ошибок, коммитит сессию. После коммита
               обработчик `after_commit` удаляет файлы из `_pending_deletions`.
            5. Если была ошибка, откатывает сессию и очищает `_pending_deletions`
               (файлы не удаляются).
            6. Закрывает сессию и удаляет привязку к потоку.

        Исключения:
            Любое исключение, возникшее внутри блока, пробрасывается после отката.
        """
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
            self.logger.exception(f"Ошибка: {e}")

            # При откате просто очищаем список, файлы не удаляем
            # if hasattr(session, '_pending_deletions'):
            #     session._pending_deletions.clear()

            # Если была ошибка, откатывает сессию
            session.rollback()

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
        # Создает новые таблицы в БД, если они не существуют
        Base.metadata.create_all(self.engine)

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