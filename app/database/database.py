# app/database/database.py

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


from app.utils.logger.logger import AppLogger

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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager


class Database:
    """
    Центральный класс для работы с БД.
    Создаёт движок, фабрику сессий и предоставляет контекстный менеджер для сессий.
    """

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
        Инициализирует объект Database.

        :param db_url: URL для подключения к БД (например, 'sqlite:///database.db')
        """
        self.engine = create_engine(
            db_url, 
            echo=False, 
            future=True,
            connect_args={"check_same_thread": False},
        )

        self.logger = AppLogger.get_instance(
            name = 'backend.Database',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        self.Session = scoped_session( 
            sessionmaker(
                bind=self.engine, 
                future=True
            )
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
        """Возвращает сессию, привязанную к текущему потоку."""
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
        Контекстный менеджер для безопасной работы с сессией.
        
        Он работает следующим образом:
        1. Создаёт сессию.
        2. Возвращает сессию в контексте with.
        3. Если в контексте не было ошибок, коммитит сессию.
        4. Если была ошибка, откатывает сессию.
        5. Закрывает сессию и удаляет привязку к потоку.
        
        Это помогает безопасно работать с сессиями, не забывая коммитить или откатывать.
        """
        session = self.get_session()
        try:
            # Возвращает сессию в контексте with
            yield session
            # Если в контексте не было ошибок, коммитит сессию
            session.commit()
        except Exception as e:
            self.logger.exception(f"Ошибка: {e}")
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
        """Закрывает все сессии и удаляет привязку к потокам."""
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
        а затем создает новые. Если параметр recreate=False, то просто создает новые таблицы,
        если они не существуют.
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
        
        Создаёт сессию, вызывает populate_test_data и коммитит сессию.
        """
        with self.session_scope() as session:
            # Заполняем тестовыми данными
            populate_test_data(session)
# 0==0