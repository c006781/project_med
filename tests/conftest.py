# pip install pytest pytest-cov pytest-mock

# tests/conftest.py

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

import tempfile

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

# try:
#     from ..app.backend.database import Database
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.database import Database
#     except ImportError:
#         pass


# try:
#     from ..app.models.bd.models import Base
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.models.bd.models import Base
#     except ImportError:
#         pass


# try:
#     from ..app.controllers.conf.get_config import get_config_env
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.controllers.conf.get_config import get_config_env
#     except ImportError:
#         pass


# try:
#     from ..app.services import PatientService, AppointmentService, NoteService, PhotoService
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.services import PatientService, AppointmentService, NoteService, PhotoService
#     except ImportError:
#         pass


# try:
#     from ..app.backend.repositories import PatientRepository, AppointmentRepository
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.repositories import PatientRepository, AppointmentRepository
#     except ImportError:
#         pass

# try:
#     from ..app.backend.repositories import PatientRepository, AppointmentRepository
# except ImportError:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.repositories import PatientRepository, AppointmentRepository
#     except ImportError:
#         pass

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backend.repositories import PatientRepository, AppointmentRepository
from app.services import PatientService, AppointmentService, NoteService, PhotoService
from app.controllers.conf.get_config import get_config_env
from app.models.bd.models import Base
from app.backend.database import Database

# Сторонние библиотеки
# pip install pytest pytest-cov pytest-mock
import pytest # pip install pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

@pytest.fixture(scope="session")
def engine():
    """
    Создаёт движок SQLAlchemy для временной БД.
    Используем SQLite in-memory для изоляции тестов.
    При необходимости можно заменить на другую БД (например, PostgreSQL).
    """
    # Используем in-memory SQLite — быстро и изолированно.
    # Для будущего переезда на серверную БД можно параметризовать через переменные окружения.
    db_url = "sqlite:///:memory:"
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)  # создаём таблицы
    return engine

@pytest.fixture
def db_session(engine):
    """
    Фикстура сессии для каждого теста.
    После теста откатываем транзакцию, чтобы не влиять на другие тесты.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    # Можно также использовать sessionmaker, но здесь просто пример

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def database(db_session):
    """
    Фикстура, имитирующая класс Database, но с уже созданной сессией.
    Для тестов сервисов, которым нужен Database с session_scope.
    """
    class TestDatabase:
        def session_scope(self):
            """Контекстный менеджер, возвращающий ту же сессию (без commit/rollback)."""
            class Context:
                def __enter__(self_):
                    return db_session
                def __exit__(self_, *args):
                    pass
            return Context()
        def close(self):
            pass

    return TestDatabase()

@pytest.fixture
def patient_service(database):
    """Фикстура сервиса пациентов."""
    return PatientService(database)

@pytest.fixture
def appointment_service(database):
    return AppointmentService(database)

@pytest.fixture
def note_service(database):
    return NoteService(database)

@pytest.fixture
def photo_service(database, tmp_path):
    """
    Фикстура PhotoService с временной папкой для хранения фото.
    tmp_path — встроенная фикстура pytest, создаёт временную директорию.
    """
    storage = tmp_path / "photos"
    storage.mkdir()
    return PhotoService(database, str(storage))

@pytest.fixture
def sample_patient(db_session):
    """Создаёт тестового пациента в БД и возвращает его ORM-объект."""
    from app.models.bd.models import Patient
    patient = Patient(
        first_name="Иван",
        last_name="Петров",
        birth_date=None,
        phone="+71234567890",
        email="ivan@test.ru"
    )
    db_session.add(patient)
    db_session.commit()  # коммитим, чтобы получить id
    return patient