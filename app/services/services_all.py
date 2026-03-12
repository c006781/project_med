
# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


import shutil

from typing import Type, TypeVar, Generic, List, Optional, Dict, Any

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
    from ..utils.logger import AppLogger
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..utils.logger import AppLogger
    except ImportError:
        pass

try:
    from ..backend.database import Database
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name( file_module = __file__,levels_up = 2)
        from ..backend.database import Database
    except ImportError:
        AppLogger.get_instance(name='system').critical("Ошибка from database import")
        pass

try:
    from ..models.bd.models import Patient, Appointment, AppointmentNote, Photo
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name( file_module = __file__,levels_up = 2)
        from ..models.bd.models import Patient, Appointment, AppointmentNote, Photo
    except ImportError:
        AppLogger.get_instance(name='system').critical("Ошибка from models import")
        pass

try:
    from ..backend.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..backend.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
    except ImportError:
        AppLogger.get_instance(name='system').critical("Ошибка from repositories_all import")
        pass

try:
    from ..dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
    except ImportError:
        AppLogger.get_instance(name='system').critical("Ошибка from dto import")
        pass

try:
    from ..exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError, AppException
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError, AppException
    except ImportError:
        AppLogger.get_instance(name='system').critical("Ошибка from exceptions import")
        pass




# Сторонние библиотеки

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload



ModelType = TypeVar('ModelType')
DTOType = TypeVar('DTOType')
RepoType = TypeVar('RepoType', bound=BaseRepository)

class BaseService(Generic[ModelType, DTOType, RepoType]):
    """
    Абстрактный базовый сервис, предоставляющий стандартные методы работы с сущностями.

    Параметры:
        db (Database): экземпляр Database для получения сессий.
        repo_class (Type[RepoType]): класс репозитория, с которым работает сервис.
        model_class (Type[ModelType]): класс ORM-модели (нужен для создания экземпляров).
        dto_class (Type[DTOType]): класс DTO (нужен для преобразования).
        logger_name (str, optional): имя логгера. По умолчанию будет использовано имя класса сервиса.

    Атрибуты:
        logger (AppLogger): логгер для записи событий.
    """

    def __init__(
        self,
        db: Database,
        repo_class: Type[RepoType],
        model_class: Type[ModelType],
        dto_class: Type[DTOType],
        logger_name: Optional[str] = None
    ):
        self._db            = db
        self._repo_class    = repo_class
        self._model_class   = model_class
        self._dto_class     = dto_class

        # Настройка логгера: если имя не передано, используем имя класса сервиса
        if logger_name is None:
            logger_name = self.__class__.__name__
        self.logger = AppLogger.get_instance(logger_name)

    def _get_repo(self, session) -> RepoType:
        """Создаёт репозиторий с переданной сессией."""
        return self._repo_class(session)

    def get_all(self) -> List[DTOType]:
        """
        Возвращает список всех записей в виде DTO.
        Логирует начало и конец операции.
        """
        self.logger.debug(f"Запрос всех записей {self._model_class.__name__}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            # Предполагаем, что в репозитории есть метод get_all()
            items = repo.get_all()  # type: List[ModelType]
            dtos = [self._dto_class.from_orm(item) for item in items]
            self.logger.debug(f"Получено {len(dtos)} записей")
            return dtos

    def get_by_id(self, entity_id: int) -> DTOType:
        """
        Возвращает запись по ID.
        :raises: исключение, возвращаемое методом _not_found_exception(), если не найдено.
        """
        self.logger.debug(f"Запрос {self._model_class.__name__} с id={entity_id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            item = repo.get_by_id(entity_id)
            if item is None:
                raise self._not_found_exception(entity_id)
            dto = self._dto_class.from_orm(item)
            self.logger.debug(f"Найдена запись {dto}")
            return dto

    def create(self, dto: DTOType) -> DTOType:
        """
        Создаёт новую запись из DTO.
        Должен быть переопределён в наследнике, так как логика создания специфична.
        """
        raise NotImplementedError("Метод create должен быть переопределён в наследнике")

    def update(self, dto: DTOType) -> DTOType:
        """
        Обновляет существующую запись.
        Должен быть переопределён в наследнике, так как обновление специфично.
        """
        raise NotImplementedError("Метод update должен быть переопределён в наследнике")

    def delete(self, entity_id: int) -> None:
        """
        Удаляет запись по ID.
        Логирует операцию.
        """
        self.logger.debug(f"Удаление {self._model_class.__name__} с id={entity_id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            item = repo.get_by_id(entity_id)
            if item is None:
                raise self._not_found_exception(entity_id)
            repo.delete(item)
            self.logger.info(f"Удалена запись {self._model_class.__name__} с id={entity_id}")

    def _not_found_exception(self, entity_id: int) -> Exception:
        """
        Возвращает исключение, которое будет выброшено при отсутствии записи.
        Должно быть переопределено в наследнике.
        """
        raise NotImplementedError(
            f"Метод _not_found_exception не реализован для {self.__class__.__name__}"
        )
    
    def get_filtered(self, filters: List[Dict[str, Any]], fuzzy_threshold: int = 60) -> List[DTOType]:
        """
        Возвращает записи, отфильтрованные по заданным условиям.
        filters: список словарей с ключами column, operator, value.
        fuzzy_threshold: порог схожести для нечеткого поиска.
        """
        from ..utils.filtering import apply_filters, apply_post_filters

        self.logger.debug(f"Запрос отфильтрованных записей {self._model_class.__name__} с фильтрами {filters}")
        with self._db.session_scope() as session:
            query = session.query(self._model_class)
            query = apply_filters(query, self._model_class, filters, fuzzy_threshold=fuzzy_threshold)
            post_filters = getattr(query, '_post_filters', [])
            items = query.all()
            if post_filters:
                items = apply_post_filters(items, post_filters, self._model_class)
            dtos = [self._dto_class.from_orm(item) for item in items]
            self.logger.debug(f"Получено {len(dtos)} записей после фильтрации")
            return dtos



class PatientService(BaseService[Patient, PatientDTO, PatientRepository]):
    """
    Сервис для управления пациентами.
    """
    def __init__(
            self, 
            db: Database, 
            logger_name: Optional[str] = None, 
        ):
        if logger_name is None:
            logger_name = self.__class__.__name__

        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
        super().__init__(
            db          = db,
            repo_class  = PatientRepository,
            model_class = Patient,
            dto_class   = PatientDTO,
            logger_name = logger_name,
        )

    # Переопределяем create, так как логика создания специфична
    def create_patient(self, patient_dto: PatientDTO) -> PatientDTO:
        """
        Создаёт нового пациента. Выполняет валидацию.
        """
        # Валидация (можно вынести в отдельный метод)
        if not patient_dto.first_name or not patient_dto.last_name:
            self.logger.warning("Попытка создания пациента без имени/фамилии")
            raise PatientValidationError("first_name/last_name", "Имя и фамилия обязательны")

        self.logger.debug(f"Создание пациента: {patient_dto}")
        with self._db.session_scope() as session:
            # Создаём ORM-объект
            patient = self._model_class(
                first_name  = patient_dto.first_name,
                last_name   = patient_dto.last_name,
                birth_date  = patient_dto.birth_date,
                phone       = patient_dto.phone,
                email       = patient_dto.email,
            )
            repo = self._get_repo(session)
            repo.add(patient)
            # Чтобы получить id, делаем flush (коммит будет в session_scope)
            session.flush()
            dto_out = self._dto_class.from_orm(patient)
            self.logger.info(f"Создан пациент с id={dto_out.id}")
            return dto_out

    # Переопределяем update
    def update_patient(self, patient_dto: PatientDTO) -> PatientDTO:
        """
        Обновляет существующего пациента.
        """
        if patient_dto.id is None:
            self.logger.warning("Попытка обновления пациента без id")
            raise PatientValidationError("id", "ID пациента обязателен для обновления")

        self.logger.debug(f"Обновление пациента id={patient_dto.id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            patient = repo.get_by_id(patient_dto.id)
            if patient is None:
                raise PatientNotFoundError(patient_dto.id)

            # Обновляем поля
            patient.first_name  = patient_dto.first_name
            patient.last_name   = patient_dto.last_name
            patient.birth_date  = patient_dto.birth_date
            patient.phone       = patient_dto.phone
            patient.email       = patient_dto.email

            # commit произойдёт автоматически при выходе из session_scope
            updated_dto = self._dto_class.from_orm(patient)
            self.logger.info(f"Обновлён пациент id={updated_dto.id}")
            return updated_dto

    # Переопределяем метод для генерации исключения "не найдено"
    def _not_found_exception(self, entity_id: int) -> Exception:
        self.logger.error(f"Пациент с идентификатором {entity_id} не найден.'")
        return PatientNotFoundError(entity_id) # Выбрасывается, когда пациент с указанным идентификатором не найден в базе данных.

    # Для совместимости с существующим кодом оставляем методы-обёртки,
    # которые вызывают методы базового класса
    def get_all_patients(self) -> List[PatientDTO]:
        self.logger.debug(f"Возвращает список всех записей в виде DTO")
        return self.get_all()

    def get_patient_by_id(self, patient_id: int) -> PatientDTO:
        self.logger.debug(f"Возвращает запись по ID ({patient_id})")
        return self.get_by_id(patient_id)

    def delete_patient(self, patient_id: int) -> None:
        self.logger.debug(f"Удаляет запись по ID ({patient_id})")
        self.delete(patient_id)

    def get_patients_filtered(self, filters: List[Dict[str, Any]], fuzzy_threshold: int = 60) -> List[PatientDTO]:
        self.logger.debug(f"Возвращает записи, отфильтрованные по заданным условиям")
        return self.get_filtered(filters, fuzzy_threshold)    

class AppointmentService(BaseService[Appointment, AppointmentDTO, AppointmentRepository]):
    def __init__(
            self, 
            db: Database, 
            logger_name: Optional[str] = None, 
        ):
        if logger_name is None:
            logger_name = self.__class__.__name__

        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
        super().__init__(
            db          = db,
            repo_class  = AppointmentRepository,
            model_class = Appointment,
            dto_class   = AppointmentDTO,
            logger_name = logger_name
        )

    def _not_found_exception(self, entity_id: int) -> Exception:
        self.logger.error(f"Приём с идентификатором {entity_id} не найден.")
        return AppointmentNotFoundError(entity_id)

    # Специфический метод
    def get_appointments_by_patient(self, patient_id: int) -> List[AppointmentDTO]:
        """
        Все приёмы пациента.
        """
        self.logger.debug(f"Запрос приёмов пациента id={patient_id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            # Предполагаем, что у AppointmentRepository есть метод get_by_patient
            apps = repo.get_by_patient(patient_id)
            return [self._dto_class.from_orm(a) for a in apps]

    def get_appointment(self, appointment_id: int) -> AppointmentDTO:
        self.logger.debug(f"Возвращает запись по ID ({appointment_id})")
        return self.get_by_id(appointment_id)

    def delete_appointment(self, appointment_id: int) -> None:
        self.logger.debug(f"Удаляет запись по ID ({appointment_id})")
        self.delete(appointment_id)

    def get_appointments_filtered(self, filters: List[Dict[str, Any]], fuzzy_threshold: int = 60) -> List[AppointmentDTO]:
        return self.get_filtered(filters, fuzzy_threshold)

    # def create_appointment(self, dto: AppointmentDTO, note_text: Optional[str] = None) -> AppointmentDTO:
    #     """
    #     Создаёт новый приём.
    #     :param dto: DTO с данными (поля patient_id, date, time, note_id могут быть None)
    #     :param note_text: если передан, создаётся новая заметка с этим текстом и привязывается к приёму.
    #     """
    #     self.logger.debug(f"Создание приёма: {dto}, note_text={note_text}")
    #     with self._db.session_scope() as session:
    #         # Проверка существования пациента
    #         patient_repo = PatientRepository(session)
    #         patient = patient_repo.get_by_id(dto.patient_id)
    #         if patient is None:
    #             raise PatientNotFoundError(dto.patient_id)

    #         # Обработка заметки
    #         note_id = dto.note_id
    #         if note_text is not None:
    #             from app.models.bd.models import AppointmentNote
    #             note = AppointmentNote(text=note_text)
    #             session.add(note)
    #             session.flush()
    #             note_id = note.id

    #         appointment = self._model_class(
    #             patient_id=dto.patient_id,
    #             date=dto.date,
    #             time=dto.time,
    #             note_id=note_id
    #         )            

    #         session.add(appointment)
            
    #         session.flush() # Чтобы получить id, можно сделать flush

    #         dto_out = self._dto_class.from_orm(appointment)
    #         self.logger.info(f"Создан приём id={dto_out.id}")
    #         return dto_out
    
    def create_appointment(self, dto: AppointmentDTO, note_text: Optional[str] = None) -> AppointmentDTO:
        """
        Создаёт новый приём.
        :param dto: DTO с данными (используются patient_id, date, time).
        :param note_text: текст заметки. Если передан, заметка будет найдена или создана,
                        и её ID автоматически подставлен.
        """
        self.logger.debug(f"Создание приёма: {dto}, note_text={note_text}")

        with self._db.session_scope() as session:
            # Проверка существования пациента
            patient_repo = PatientRepository(session)
            patient = patient_repo.get_by_id(dto.patient_id)
            if patient is None:
                raise PatientNotFoundError(dto.patient_id)

            # Обработка заметки
            note_id = None
            if note_text:
                # Создаём экземпляр NoteService с тем же подключением к БД
                note_service = NoteService(self._db, logger_name=self.logger.name + ".NoteService")
                note_dto = note_service.get_or_create_note(note_text)
                if note_dto:
                    note_id = note_dto.id

            appointment = self._model_class(
                patient_id=dto.patient_id,
                date=dto.date,
                time=dto.time,
                note_id=note_id
            )
            session.add(appointment)
            session.flush()  # чтобы получить id
            dto_out = self._dto_class.from_orm(appointment)
            self.logger.info(f"Создан приём id={dto_out.id}")
            return dto_out


    def update_appointment(self, dto: AppointmentDTO, note_text: Optional[str] = None) -> AppointmentDTO:
        """
        Обновляет приём.
        Если передан note_text, то создаётся новая заметка, и ID старой заменяется новой.
        Если note_text не передан, но dto.note_id указан, то привязывается существующая заметка.
        """
        if dto.id is None:
            self.logger.warning("Попытка обновления приёма без id")
            raise ValueError("ID приёма не указан")
        self.logger.debug(f"Обновление приёма id={dto.id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            app = repo.get_by_id(dto.id)
            if app is None:
                raise AppointmentNotFoundError(dto.id)

            app.date = dto.date
            app.time = dto.time

            if note_text is not None:
                from app.models.bd.models import AppointmentNote
                note = AppointmentNote(text=note_text)
                session.add(note)
                session.flush()
                app.note_id = note.id
            elif dto.note_id is not None:
                app.note_id = dto.note_id
            # иначе оставляем без изменений

            # Если нужно менять пациента, то тоже можно, но осторожно
            # app.patient_id = dto.patient_id

            updated_dto = self._dto_class.from_orm(app)
            self.logger.info(f"Обновлён приём id={updated_dto.id}")
            return updated_dto



class NoteService(BaseService[AppointmentNote, AppointmentNoteDTO, AppointmentNoteRepository]):
    def __init__(
            self, 
            db: Database, 
            logger_name: Optional[str] = None, 
        ):
        if logger_name is None:
            logger_name = self.__class__.__name__
            
        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
        super().__init__(
            db          =db,
            repo_class  = AppointmentNoteRepository,
            model_class = AppointmentNote,
            dto_class   = AppointmentNoteDTO,
            logger_name = logger_name
        )

    def _not_found_exception(self, entity_id: int) -> Exception:
        return AppointmentNoteNotFoundError(entity_id)

    def get_note(self, note_id: int) -> AppointmentNoteDTO:
        self.logger.debug(f"Возвращает запись по ID ({note_id})")
        return self.get_by_id(note_id)

    def create_note(self, text: str) -> AppointmentNoteDTO:
        self.logger.debug("Создание заметки")
        with self._db.session_scope() as session:
            note = self._model_class(text=text)
            session.add(note)
            session.flush()
            dto_out = self._dto_class.from_orm(note)
            self.logger.info(f"Создана заметка id={dto_out.id}")
            return dto_out

    def update_note(self, note_id: int, text: str) -> AppointmentNoteDTO:
        self.logger.debug(f"Обновление заметки id={note_id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            note = repo.get_by_id(note_id)
            if note is None:
                raise AppointmentNoteNotFoundError(note_id)
            note.text = text
            updated_dto = self._dto_class.from_orm(note)
            self.logger.info(f"Обновлена заметка id={updated_dto.id}")
            return updated_dto

    def delete_note(self, note_id: int) -> None:
        self.logger.debug(f"Удаляет запись по ID ({note_id})")
        self.delete(note_id)

    def get_or_create_note(self, text: str) -> Optional[AppointmentNoteDTO]:
        """
        Возвращает существующую заметку по точному совпадению текста,
        либо создаёт новую, если такой ещё нет.
        Если text пустой или None, возвращает None.
        """
        if not text:  # пустой текст не обрабатываем
            return None

        self.logger.debug(f"Поиск или создание заметки: {text[:50]}...")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            note = repo.get_by_text_exact(text)
            if note:
                self.logger.debug(f"Найдена существующая заметка id={note.id}")
                return self._dto_class.from_orm(note)

            # Создаём новую заметку
            note = self._model_class(text=text)
            session.add(note)
            session.flush()  # чтобы получить id
            self.logger.info(f"Создана новая заметка id={note.id}")
            return self._dto_class.from_orm(note)




class PhotoService(BaseService[Photo, PhotoDTO, PhotoRepository]):
    def __init__(
            self, 
            db: 
            Database, 
            photos_storage_path: str, 
            logger_name: Optional[str] = None, 
        ):
        if logger_name is None:
            logger_name = self.__class__.__name__
            
        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
        super().__init__(
            db          = db,
            repo_class  = PhotoRepository,
            model_class = Photo,
            dto_class   = PhotoDTO,
            logger_name = logger_name
        )
        self._storage_path = photos_storage_path

    def _not_found_exception(self, entity_id: int) -> Exception:
        return PhotoNotFoundError(entity_id)

    # Метод для добавления фото (со своим логгированием)
    def add_photo_to_appointment(self, appointment_id: int, source_file_path: str, description: str = "") -> PhotoDTO:
        """
        Добавляет фото к приёму: копирует файл в хранилище и создаёт запись в БД.
        """
        self.logger.debug(f"Добавление фото к приёму id={appointment_id}, файл={source_file_path}")
        with self._db.session_scope() as session:
            # Проверим, что приём существует
            app_repo = AppointmentRepository(session)
            app = app_repo.get_by_id(appointment_id)
            if app is None:
                raise AppointmentNotFoundError(appointment_id)

            # Копируем файл (метод из исходного кода)
            rel_path = self._copy_file_to_storage(source_file_path, appointment_id)

            # Создаём запись фото
            from app.models.bd.models import Photo  # можно импортировать вверху, но оставим как есть
            photo = Photo(
                appointment_id=appointment_id,
                file_path=rel_path,
                description=description
            )
            session.add(photo)
            session.flush()
            dto_out = self._dto_class.from_orm(photo)
            self.logger.info(f"Добавлено фото id={dto_out.id} к приёму {appointment_id}")
            return dto_out

    def _copy_file_to_storage(self, source_path: str, appointment_id: int) -> str:
        """
        Копирует файл в хранилище и возвращает относительный путь.
        (Код скопирован из исходного PhotoService без изменений, но с добавлением логирования.)
        """
        import os, shutil, time
        self._ensure_storage_exists()
        app_folder = os.path.join(self._storage_path, f"app_{appointment_id}")
        os.makedirs(app_folder, exist_ok=True)

        base_name = os.path.basename(source_path)
        name, ext = os.path.splitext(base_name)
        dest_name = f"{name}_{int(time.time())}{ext}"
        dest_path = os.path.join(app_folder, dest_name)

        try:
            shutil.copy2(source_path, dest_path)
            self.logger.debug(f"Файл скопирован: {source_path} -> {dest_path}")
        except Exception as e:
            self.logger.exception(f"Ошибка копирования файла {source_path}")
            raise PhotoFileError(source_path, "копирование", str(e))

        return os.path.relpath(dest_path, self._storage_path)

    def _ensure_storage_exists(self):
        """Создаёт папку для фото, если её нет."""
        os.makedirs(self._storage_path, exist_ok=True)

    def get_photos_for_appointment(self, appointment_id: int) -> List[PhotoDTO]:
        self.logger.debug(f"Запрос фото для приёма id={appointment_id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            photos = repo.get_by_appointment(appointment_id)
            return [self._dto_class.from_orm(p) for p in photos]

    def delete_photo(self, photo_id: int) -> None:
        """
        Удаляет запись фото из БД и сам файл из хранилища.
        """
        self.logger.debug(f"Удаление фото id={photo_id}")
        with self._db.session_scope() as session:
            repo = self._get_repo(session)
            photo = repo.get_by_id(photo_id)
            if photo is None:
                raise PhotoNotFoundError(photo_id)
            
            # Получаем полный путь к файлу
            full_path = os.path.join(self._storage_path, photo.file_path)
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    self.logger.debug(f"Удалён файл {full_path}")
            except Exception as e:
                self.logger.exception(f"Ошибка удаления файла {full_path}")
                raise PhotoFileError(full_path, "удаление", str(e))

            repo.delete(photo)
            self.logger.info(f"Удалена запись фото id={photo_id}")




            