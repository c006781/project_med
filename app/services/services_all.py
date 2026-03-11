
# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


import shutil

from typing import Type, TypeVar, Generic, List

import time as time_module
# from datetime import time
# import datetime

# Импорты модулей
def _add_package_name(
    file_module: str = None,
    levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
) -> None:
    
    """
    Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

    :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
                       (подберите под структуру вашего проекта)
                       Примеры:
                         2 → до папки app
    """
    if file_module is None:
        file_module = __file__

    # Получаем директорию текущего файла
    current_dir = os.path.dirname(os.path.abspath(file_module))

    # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
    project_root = current_dir
    for _ in range(levels_up):
        project_root = os.path.dirname(project_root)

    # Добавляем корень проекта в начало sys.path (высокий приоритет)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Вычисляем правильное значение __package__
    # Пример: /project_med/app/models/bd → "app.models.bd"
    rel_path = os.path.relpath(current_dir, project_root)
    
    if rel_path == '.':
        package_name = ''
    else:
        package_name = rel_path.replace(os.sep, '.').strip('.')

    # Устанавливаем __package__
    global __package__
    if package_name:
        __package__ = package_name
    else:
        # Если мы в корне — можно оставить None или пустую строку
        __package__ = None



try:
    from ..backend.database import Database
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name( file_module = __file__,levels_up = 2)
        from ..backend.database import Database
    except ImportError:
        pass

try:
    from ..backend.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..backend.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
    except ImportError:
        pass

try:
    from ..dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
    except ImportError:
        pass

try:
    from ..exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError
    except ImportError:
        pass

# Сторонние библиотеки

from sqlalchemy.orm import Session




Model = TypeVar("Model")
DTO = TypeVar("DTO")
Repo = TypeVar("Repo", bound=BaseRepository)

class BaseService(Generic[Model, DTO, Repo]):
    """
    Базовый сервис, предоставляющий общие методы.
    
    Параметры:
        db (Database): экземпляр Database для получения сессий.
        repo_class (Type[Repo]): класс репозитория, с которым работает сервис.
    """
    def __init__(self, db: Database, repo_class: Type[Repo]):
        self._db = db
        self._repo_class = repo_class

    def _get_repo(self, session: Session) -> Repo:
        """Вспомогательный метод для создания репозитория с текущей сессией."""
        return self._repo_class(session)

    # Далее конкретные сервисы будут добавлять свои методы



class PatientService:
    """
    Сервис для управления пациентами.
    Все методы работают в собственной транзакции (сессии) и возвращают DTO.
    """
    def __init__(self, db: Database):
        """
        :param db: экземпляр Database, через который будем получать сессии.
        """
        self._db = db

    def get_all_patients(self) -> List[PatientDTO]:
        """
        Получить список всех пациентов.
        :return: список PatientDTO
        """
        with self._db.session_scope() as session:
            repo = PatientRepository(session)
            patients = repo.get_all()
            # Преобразуем каждую ORM-модель в DTO
            return [PatientDTO.from_orm(p) for p in patients]

    def get_patient_by_id(self, patient_id: int) -> PatientDTO:
        """
        Получить пациента по ID.
        :raises PatientNotFoundError: если пациент не найден
        """
        with self._db.session_scope() as session:
            repo = PatientRepository(session)
            patient = repo.get_by_id(patient_id)
            if patient is None:
                raise PatientNotFoundError(patient_id)
            return PatientDTO.from_orm(patient)

    def create_patient(self, patient_dto: PatientDTO) -> PatientDTO:
        """
        Создать нового пациента.
        :param patient_dto: DTO с данными нового пациента (id должен быть None)
        :return: DTO созданного пациента с присвоенным id
        :raises PatientValidationError: если данные невалидны
        """
        # Валидация (можно вынести в отдельный метод или использовать библиотеку)
        if not patient_dto.first_name or not patient_dto.last_name:
            raise PatientValidationError("first_name/last_name", "Имя и фамилия обязательны")

        with self._db.session_scope() as session:
            repo = PatientRepository(session)
            # Создаём ORM-объект из DTO (без id)
            from app.models.bd.models import Patient  # импорт внутри метода, чтобы избежать циклических зависимостей
            patient = Patient(
                first_name=patient_dto.first_name,
                last_name=patient_dto.last_name,
                birth_date=patient_dto.birth_date,
                phone=patient_dto.phone,
                email=patient_dto.email,
            )
            repo.add(patient)
            # После add объект получает id (при коммите или flush)
            session.flush() # чтобы получить id до коммита, но коммит сделает session_scope
            # Возвращаем DTO с id
            return PatientDTO.from_orm(patient)

    def update_patient(self, patient_dto: PatientDTO) -> PatientDTO:
        """
        Обновить данные существующего пациента.
        :param patient_dto: DTO с заполненными полями, включая id
        :return: обновлённый DTO
        :raises PatientNotFoundError: если пациента с таким id нет
        :raises PatientValidationError: при невалидных данных
        """
        if patient_dto.id is None:
            raise PatientValidationError("id", "ID пациента обязателен для обновления")

        with self._db.session_scope() as session:
            repo = PatientRepository(session)
            patient = repo.get_by_id(patient_dto.id)
            if patient is None:
                raise PatientNotFoundError(patient_dto.id)

            # Обновляем поля (можно использовать автоматическое обновление из DTO)
            patient.first_name = patient_dto.first_name
            patient.last_name = patient_dto.last_name
            patient.birth_date = patient_dto.birth_date
            patient.phone = patient_dto.phone
            patient.email = patient_dto.email

            # Репозиторий не нужен для update, так как объект уже в сессии и изменения отслеживаются
            # При выходе из session_scope будет коммит

            return PatientDTO.from_orm(patient)

    def delete_patient(self, patient_id: int) -> None:
        """
        Удалить пациента по ID.
        :raises PatientNotFoundError: если пациента нет
        """
        with self._db.session_scope() as session:
            repo = PatientRepository(session)
            patient = repo.get_by_id(patient_id)
            if patient is None:
                raise PatientNotFoundError(patient_id)
            repo.delete(patient)
            # commit произойдёт автоматически



class AppointmentService:
    def __init__(self, db: Database):
        self._db = db

    def get_appointments_by_patient(self, patient_id: int) -> List[AppointmentDTO]:
        """Все приёмы пациента."""
        with self._db.session_scope() as session:
            repo = AppointmentRepository(session)
            appointments = repo.get_by_patient(patient_id)
            return [AppointmentDTO.from_orm(a) for a in appointments]

    def get_appointment(self, appointment_id: int) -> AppointmentDTO:
        with self._db.session_scope() as session:
            repo = AppointmentRepository(session)
            app = repo.get_by_id(appointment_id)
            if app is None:
                raise AppointmentNotFoundError(appointment_id)
            return AppointmentDTO.from_orm(app)

    def create_appointment(self, dto: AppointmentDTO) -> AppointmentDTO:
        """Создание нового приёма. dto.patient_id должен быть указан."""
        with self._db.session_scope() as session:
            # Проверим, что пациент существует
            patient_repo = PatientRepository(session)
            patient = patient_repo.get_by_id(dto.patient_id)
            if patient is None:
                raise PatientNotFoundError(dto.patient_id)

            # Создаём ORM-объект
            from app.models.bd.models import Appointment
            appointment = Appointment(
                patient_id=dto.patient_id,
                date=dto.date,
                time=dto.time,
                note_id=dto.note_id,  # может быть None
            )
            session.add(appointment)
            # Чтобы получить id, можно сделать flush
            session.flush()
            return AppointmentDTO.from_orm(appointment)

    def update_appointment(self, dto: AppointmentDTO) -> AppointmentDTO:
        if dto.id is None:
            raise ValueError("ID приёма не указан")
        with self._db.session_scope() as session:
            repo = AppointmentRepository(session)
            app = repo.get_by_id(dto.id)
            if app is None:
                raise AppointmentNotFoundError(dto.id)

            app.date = dto.date
            app.time = dto.time
            app.note_id = dto.note_id
            # При необходимости можно менять пациента, но осторожно с внешними ключами
            # app.patient_id = dto.patient_id

            return AppointmentDTO.from_orm(app)

    def delete_appointment(self, appointment_id: int) -> None:
        with self._db.session_scope() as session:
            repo = AppointmentRepository(session)
            app = repo.get_by_id(appointment_id)
            if app is None:
                raise AppointmentNotFoundError(appointment_id)
            repo.delete(app)


class NoteService:
    def __init__(self, db: Database):
        self._db = db

    def get_note(self, note_id: int) -> AppointmentNoteDTO:
        with self._db.session_scope() as session:
            repo = AppointmentNoteRepository(session)
            note = repo.get_by_id(note_id)
            if note is None:
                raise AppointmentNoteNotFoundError(note_id)
            return AppointmentNoteDTO.from_orm(note)

    def create_note(self, text: str) -> AppointmentNoteDTO:
        with self._db.session_scope() as session:
            from app.models.bd.models import AppointmentNote
            note = AppointmentNote(text=text)
            session.add(note)
            session.flush()
            return AppointmentNoteDTO.from_orm(note)

    def update_note(self, note_id: int, text: str) -> AppointmentNoteDTO:
        with self._db.session_scope() as session:
            repo = AppointmentNoteRepository(session)
            note = repo.get_by_id(note_id)
            if note is None:
                raise AppointmentNoteNotFoundError(note_id)
            note.text = text
            return AppointmentNoteDTO.from_orm(note)

    def delete_note(self, note_id: int) -> None:
        with self._db.session_scope() as session:
            repo = AppointmentNoteRepository(session)
            note = repo.get_by_id(note_id)
            if note is None:
                raise AppointmentNoteNotFoundError(note_id)
            repo.delete(note)





class PhotoService:
    def __init__(self, db: Database, photos_storage_path: str):
        """
        :param db: Database instance
        :param photos_storage_path: абсолютный путь к папке, где хранятся фото (берётся из настроек)
        """
        self._db = db
        self._storage_path = photos_storage_path

    def _ensure_storage_exists(self):
        """Создаёт папку для фото, если её нет."""
        os.makedirs(self._storage_path, exist_ok=True)

    def _copy_file_to_storage(self, source_path: str, appointment_id: int) -> str:
        """
        Копирует файл в хранилище и возвращает относительный путь (для хранения в БД).
        Формат: appointments/{appointment_id}/photo_{timestamp}.ext
        """
        self._ensure_storage_exists()
        # Создаём подпапку для приёма
        app_folder = os.path.join(self._storage_path, f"app_{appointment_id}")
        os.makedirs(app_folder, exist_ok=True)

        # Генерируем имя файла (можно добавить timestamp)
        base_name = os.path.basename(source_path)
        name, ext = os.path.splitext(base_name)

        # dest_name = f"{name}_{int(datetime.now().time())}{ext}"
        # dest_name = f"{name}_{int(datetime.now().time())}{ext}"
        # dest_name = f"{name}_{int(time.time())}{ext}"
        dest_name = f"{name}_{int(time_module.time())}{ext}"

        dest_path = os.path.join(app_folder, dest_name)

        try:
            shutil.copy2(source_path, dest_path)
        except Exception as e:
            raise PhotoFileError(source_path, "копирование", str(e))

        # Возвращаем относительный путь для хранения в БД
        return os.path.relpath(dest_path, self._storage_path)

    def add_photo_to_appointment(self, appointment_id: int, source_file_path: str, description: str = "") -> PhotoDTO:
        """
        Добавляет фото к приёму: копирует файл в хранилище и создаёт запись в БД.
        """
        with self._db.session_scope() as session:
            # Проверим, что приём существует
            app_repo = AppointmentRepository(session)
            app = app_repo.get_by_id(appointment_id)
            if app is None:
                raise AppointmentNotFoundError(appointment_id)

            # Копируем файл
            rel_path = self._copy_file_to_storage(source_file_path, appointment_id)

            # Создаём запись фото
            from app.models.bd.models import Photo
            photo = Photo(
                appointment_id=appointment_id,
                file_path=rel_path,
                description=description
            )
            session.add(photo)
            session.flush()
            return PhotoDTO.from_orm(photo)

    def get_photos_for_appointment(self, appointment_id: int) -> List[PhotoDTO]:
        with self._db.session_scope() as session:
            repo = PhotoRepository(session)
            photos = repo.get_by_appointment(appointment_id)
            return [PhotoDTO.from_orm(p) for p in photos]

    def delete_photo(self, photo_id: int) -> None:
        """
        Удаляет запись фото из БД и сам файл из хранилища.
        """
        with self._db.session_scope() as session:
            repo = PhotoRepository(session)
            photo = repo.get_by_id(photo_id)
            if photo is None:
                raise PhotoNotFoundError(photo_id)

            # Получаем полный путь к файлу
            full_path = os.path.join(self._storage_path, photo.file_path)
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                # Логируем, но не прерываем удаление записи? Можно пробросить исключение
                raise PhotoFileError(full_path, "удаление", str(e))

            repo.delete(photo)




            