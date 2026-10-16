# pip install pytest pytest-cov pytest-mock

# tests/conftest.py

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

# import tempfile
from datetime import date, time 
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
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.database import Database
#     except ImportError as e:
#         pass


# try:
#     from ..app.models.bd.models import Base
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.models.bd.models import Base
#     except ImportError as e:
#         pass


# try:
#     from ..app.controllers.conf.get_config import get_config_env
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.controllers.conf.get_config import get_config_env
#     except ImportError as e:
#         pass


# try:
#     from ..app.services import PatientService, AppointmentService, NoteService, PhotoService
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.services import PatientService, AppointmentService, NoteService, PhotoService
#     except ImportError as e:
#         pass


# try:
#     from ..app.backend.repositories import PatientRepository, AppointmentRepository
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.repositories import PatientRepository, AppointmentRepository
#     except ImportError as e:
#         pass

# try:
#     from ..app.backend.repositories import PatientRepository, AppointmentRepository
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.repositories import PatientRepository, AppointmentRepository
#     except ImportError as e:
#         pass

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импорт app.* создаёт логгеры, а они читают конфиг через get_getenv(),
# который перезаписывает .env, если ключ пустой (GITHUB_TOKEN='' в .env).
# load_dotenv не переопределяет уже заданные переменные, поэтому .env не трогается.
os.environ.setdefault('GITHUB_TOKEN', 'test-placeholder')

# E3 (2026-10-15): .env ищется в папке ЗАПУЩЕННОГО файла, а под pytest это сам pytest
# (site-packages). Направляем .env всего набора во временную папку — тесты не создают
# файлов в venv и не читают/не пишут боевой .env проекта (раньше find_dotenv находил его).
import tempfile as _tempfile
os.environ.setdefault('PROJECT_MED_ENV_DIR', _tempfile.mkdtemp(prefix='project_med_env_'))

# T2 (2026-10-16): тесты, идущие через app.dependencies (CLI и т. п.), открывали НАСТОЯЩИЕ
# config.msgpack и clinic.db проекта (путь к конфигу из .env — 'config.msgpack' от текущей
# папки = корня проекта). create_all дописал в боевую базу таблицу тестовой модели.
# Теперь весь набор работает с временным конфигом: временные база, фото и логи.
_TEST_DATA_DIR = _tempfile.mkdtemp(prefix='project_med_data_')
_TEST_CONFIG = os.path.join(_TEST_DATA_DIR, 'config.msgpack')
os.environ.setdefault('APP_CONFIG_PATH', _TEST_CONFIG)
if os.environ['APP_CONFIG_PATH'] == _TEST_CONFIG:
    import msgpack as _msgpack
    with open(_TEST_CONFIG, 'wb') as _f:
        _msgpack.pack({
            'database_local_path': os.path.join(_TEST_DATA_DIR, 'clinic.db'),
            'PHOTOS_STORAGE_PATH': os.path.join(_TEST_DATA_DIR, 'photos'),
            'LOG_DIR': os.path.join(_TEST_DATA_DIR, 'logs'),
            'BACKUP_PATH': os.path.join(_TEST_DATA_DIR, 'backup'),
        }, _f)

# T2: страховка — открыть боевую базу проекта из теста нельзя (тест сразу падает)
_REAL_DB = os.path.normcase(os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'clinic.db')))


def _guard_real_db(create_engine_func):
    """Обёртка create_engine: запрет на боевую clinic.db проекта (T2)."""
    def guarded(url, *args, **kwargs):
        text = str(url)
        if text.startswith('sqlite:///'):
            path = os.path.normcase(os.path.abspath(text[len('sqlite:///'):]))
            if path == _REAL_DB:
                raise RuntimeError(
                    f"Тест пытается открыть БОЕВУЮ базу проекта {path}. Тесты должны работать "
                    "с временной базой (tests/conftest.py, T2)."
                )
        return create_engine_func(url, *args, **kwargs)
    return guarded


import app.database.database as _database_module  # noqa: E402
_database_module.create_engine = _guard_real_db(_database_module.create_engine)

from app.repositories import (
    PatientRepository, AppointmentRepository,
    AppointmentNoteRepository, PhotoRepository
)
from app.services import (
    PatientService, AppointmentService,
    NoteService, PhotoService, SyncService
)
from app.database.database_shema.clinic import (
    Base, Patient, Appointment, AppointmentNote, Photo
)
# from app.database.database_shema import Database
from app.database import Database

# from app.controllers.conf.get_config import get_config_env
# from app.config.config_manager.manager import get_config_env
# from app.config.conf.getenv import get_dotenv_path, save_env_file


# Сторонние библиотеки
# pip install pytest pytest-cov pytest-mock
import pytest # pip install pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import (
    # sessionmaker, 
    Session
)



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
    engine = create_engine(
        db_url, 
        echo=False,
        # connect_args={"check_same_thread": False},
    )
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
def patient_service(database, appointment_service):
    # (до 2026-10-16 — без appointment_service: каскадное удаление пациента падало
    #  RuntimeError «AppointmentService не передан»)
    """
    Фикстура сервиса пациентов.

    Возвращает экземпляр PatientService, инициализированный с помощью Database.
    """
    # return PatientService(database)
    # ↑ до 2026-10-16: без field_configs сервис не знает полей — пациент записывался с
    #   пустыми полями (NOT NULL first_name). Собираем как app/dependencies.py.
    from app.dto.field_configs import PATIENT_CONFIG
    return PatientService(database, field_configs=PATIENT_CONFIG,
                          appointment_service=appointment_service)

# @pytest.fixture
# def appointment_service(database, note_service):
#     """
#     Фикстура сервиса приёмов.
#
#     Возвращает экземпляр AppointmentService, инициализированный с помощью Database и NoteService.
#     """
#     return AppointmentService(database, note_service=note_service)
#
# @pytest.fixture
# def note_service(database):
#     """
#     Фикстура сервиса заметок.
#
#     Возвращает экземпляр NoteService, инициализированный с помощью Database.
#     """
#     return NoteService(database)
# ↑ до 2026-10-16: обе перекрывались одноимёнными фикстурами ниже (pytest берёт последнюю).

@pytest.fixture
def photo_service(database, tmp_path):
    """
    Фикстура PhotoService с временной папкой для хранения фото.

    tmp_path — встроенная фикстура pytest, создаёт временную директорию.

    Возвращает экземпляр PhotoService, инициализированный с помощью Database и временной папки для фото.
    """
    storage = tmp_path / "photos"
    storage.mkdir(parents=True, exist_ok=True)
    # return PhotoService(database, str(storage))
    # ↑ до 2026-10-16: без field_configs (см. patient_service)
    from app.dto.field_configs import PHOTO_CONFIG
    return PhotoService(database, str(storage), field_configs=PHOTO_CONFIG)


@pytest.fixture
def sample_patient(db_session):
    """
    Создаёт тестового пациента в БД и возвращает его ORM-объект.

    Patient(first_name="Иван", last_name="Петров", birth_date=None, phone="+71234567890", email="ivan@test.ru")
    """
    from app.database.database_shema.clinic import Patient
    patient = Patient(
        first_name="Иван",  # имя
        last_name="Петров",  # фамилия
        birth_date=None,  # дата рождения
        phone="+71234567890",  # телефон
        # email="ivan@test.ru"  # электронная почта
        # ↑ до 2026-10-16: поля email в схеме Patient нет — TypeError в каждой зависящей
        #   фикстуре (43 ошибки подготовки тестов)
    )
    db_session.add(patient)
    db_session.commit()  # коммитим, чтобы получить id
    return patient

@pytest.fixture
def patient_repo(db_session):
    """
    Возвращает репозиторий для работы с пациентами (PatientRepository).

    db_session — сессия БД, которая будет использоваться для работы с репозиторием.
    """
    return PatientRepository(db_session)

@pytest.fixture
def appointment_repo(db_session):
    """
    Возвращает репозиторий для работы с приёмами (AppointmentRepository).
    """
    return AppointmentRepository(db_session)

@pytest.fixture
def note_repo(db_session):
    """
    Возвращает репозиторий для работы с заметками приёмов (AppointmentNoteRepository).
    """
    return AppointmentNoteRepository(db_session)

@pytest.fixture
def photo_repo(db_session):
    """
    Возвращает репозиторий для работы с фотографиями приёмов (PhotoRepository).
    """
    return PhotoRepository(db_session)

@pytest.fixture
def appointment_service(database, note_service, photo_service):
    """
    Фикстура сервиса приёмов.
    Возвращает AppointmentService с уже созданным Database и сервисами NoteService и PhotoService.
    """
    # return AppointmentService(database, note_service=note_service, photo_service=photo_service)
    # ↑ до 2026-10-16: без field_configs (см. patient_service)
    from app.dto.field_configs import APPOINTMENT_CONFIG
    return AppointmentService(database, note_service=note_service, photo_service=photo_service,
                              field_configs=APPOINTMENT_CONFIG)

@pytest.fixture
def note_service(database):
    """
    Фикстура сервиса заметок приёмов.

    Возвращает экземпляр NoteService, инициализированный с помощью Database.
    """
    # return NoteService(database)
    # ↑ до 2026-10-16: без field_configs (см. patient_service)
    from app.dto.field_configs import NOTE_CONFIG
    return NoteService(database, field_configs=NOTE_CONFIG)

@pytest.fixture
def sync_service():
    """
    Возвращает экземпляр SyncService, инициализированный для синхронизации с Яндекс.Диском.
    """
    return SyncService()

@pytest.fixture
def sample_appointment(db_session, sample_patient, sample_note):
    """
    Фикстура примера приёма.

    Создаёт приём с данными: пациент - sample_patient, заметка - sample_note,
    дата и время - сегодня и 10:00 соответственно.

    db_session — сессия БД, которая будет использоваться для работы с репозиторием.

    Returns:
        Appointment: созданный приём.
    """
    
    from app.database.database_shema.clinic import Appointment
    app = Appointment(
        patient_id=sample_patient.id,
        date=date.today(),
        # time=time(10, 0),
        # ↑ до 2026-10-16: поля time в схеме Appointment нет
        note_id=sample_note.id
    )
    db_session.add(app)
    db_session.commit()
    return app

@pytest.fixture
def sample_note(db_session):
    """
    Фикстура примера заметки.

    Создаёт заметку с текстом "Тестовая заметка" и добавляет ее в БД.

    db_session — сессия БД, которая будет использоваться для работы с репозиторием.

    Returns:
        AppointmentNote: созданная заметка.
    """
    note = AppointmentNote(text="Тестовая заметка")
    db_session.add(note)
    db_session.commit()
    return note

@pytest.fixture
def sample_photo(db_session, sample_appointment, tmp_path):
    """
    Фикстура примера фото.

    Создаёт фото с данными: приём - sample_appointment, путь к файлу - app1/test.jpg,
    описание - "Тестовое фото". Создаёт временный файл с данным именем test.jpg,
    и добавляет фото в БД.

    db_session — сессия БД, которая будет использоваться для работы с репозиторием.
    tmp_path — временная папка, созданная pytest.

    Returns:
        Photo: созданное фото.
    """
    storage = tmp_path / "photos"
    storage.mkdir(exist_ok=True)
    rel_path = "app1/test.jpg"
    full_path = storage / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"dummy")
    photo = Photo(
        appointment_id=sample_appointment.id,
        file_path=rel_path,
        description="Тестовое фото"
    )
    db_session.add(photo)
    db_session.commit()
    return photo