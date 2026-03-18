
# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


import shutil
import uuid

from typing import Type, TypeVar, Generic, List, Optional, Dict, Any, Tuple, Union

import time as time_module
# from datetime import time
# import datetime

from contextlib import contextmanager

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
from app.utils.logger import AppLogger
# except ImportError as e:
#     # try:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name(file_module = __file__,levels_up = 2)
#     from ..utils.logger import AppLogger
#     # except ImportError as e:
#     #     pass #  raise # e # pass

# try:
from app.database.database import Database
# except ImportError as e:
#     # try:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name( file_module = __file__,levels_up = 2)
#     from ..backend.database import Database
#     # except ImportError as e:
#     #     AppLogger.get_instance(name='system').critical("Ошибка from database import")
#         # pass #  raise # e # pass

# try:
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name( file_module = __file__,levels_up = 2)
#         from ..backend.bd.clinic import Patient, Appointment, AppointmentNote, Photo
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from models import")
#         pass #  raise # e # pass

# try:
from app.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..backend.repositories.repositories_all import BaseRepository, PatientRepository, AppointmentRepository, PatientRepository, AppointmentNoteRepository, PhotoRepository
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from repositories_all import")
#         pass #  raise # e # pass

# try:
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from dto import")
#         pass #  raise # e # pass

# try:
from app.exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError, AppException
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..exceptions import PatientNotFoundError, PatientValidationError, AppointmentNotFoundError, AppointmentNoteNotFoundError, PhotoNotFoundError, PhotoFileError, AppException
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from exceptions import")
#         pass #  raise # e # pass

# try:
from app.utils.filtering.filtering import apply_filters, apply_post_filters
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..utils.filtering.filtering import apply_filters, apply_post_filtersception
#     except ImportError as e:
#         AppLogger.get_instance(name='system').critical("Ошибка from exceptions import")
#         pass #  raise # e # pass



# Сторонние библиотеки

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import selectinload



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

    def get_all(self, session: Optional[Session] = None) -> List[DTOType]:
        """
        Возвращает список всех записей в виде DTO.
        Логирует начало и конец операции.
        """
        self.logger.debug(f"Запрос всех записей {self._model_class.__name__}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            items = repo.get_all() # Предполагаем, что в репозитории есть метод get_all()
            # dtos = [self._dto_class.from_orm(item) for item in items]
            dtos = self.get_dtos(items)
            # self.logger.debug(f"Получено {len(dtos)} записей")
            return dtos

    def get_by_id(self, entity_id: int, session: Optional[Session] = None) -> DTOType:
        """
        Возвращает запись по ID.
        :raises: исключение, возвращаемое методом _not_found_exception(), если не найдено.
        """
        self.logger.debug(f"Запрос {self._model_class.__name__} с id={entity_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            item = repo.get_by_id(entity_id)
            if item is None:
                raise self._not_found_exception(entity_id)
            # dto = self._dto_class.from_orm(item)
            # dto = self._dto_class.model_validate(item)
            dto = self.get_dtos(item)
            # self.logger.debug(f"Найдена запись {dto}")
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

    def delete(self, entity_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет запись по ID.
        Логирует операцию.
        """
        self.logger.debug(f"Удаление {self._model_class.__name__} с id={entity_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
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
    
    def get_dtos(
            self, 
            item_s:Union[List, Any]  # список объектов или один объект
    )-> Union[List, Any] : 
        """
        Возвращает список DTO из списка объектов или один DTO из объекта.
        Если получен список объектов, то для каждого объекта пытается создать DTO.
        Если объект не может быть конвертирован в DTO, то выбрасывается исключение.
        """
        if isinstance(item_s, list):
            dtos = []  # список DTO
            for item in item_s:
                # try:
                dtos.append(self.get_dtos(item))  # рекурсивно добавляем DTO в список
                # except Exception as e:
                #     self.logger.error(f"Ошибка валидации для объекта: {item}")  # логгируем ошибку
                #     raise e  # выбрасываем исключение
            self.logger.debug(f"Получено {len(dtos)} записей")  # логгируем количество полученных DTO
            return dtos
        else:
            # данные из ТБ
            try:
                dto = self._dto_class.model_validate(item_s)  # создаем DTO из объекта
            except Exception as e:
                self.logger.error(f"Ошибка валидации для объекта: {item}")  # логгируем ошибку
                raise e  # выбрасываем исключение
            
            return dto
    
    def get_dto_out(
            self, 
            item,
    ): 
        return self.get_dtos(item)
 
        
    
    def get_filtered(
            self, 
            filters: List[Dict[str, Any]], 
            fuzzy_threshold: int = 60,
            session: Optional[Session] = None
        ) -> List[DTOType]:
        """
        Возвращает записи, отфильтрованные по заданным условиям.

        Параметры:
            filters: список словарей, каждый с ключами:
                - column (str): имя столбца модели.
                - operator (str): оператор из FilterOperator (например, 'eq', 'like', 'fuzzy').
                - value (any): значение для сравнения (зависит от оператора).
            fuzzy_threshold: порог схожести для нечёткого поиска (0-100). Используется только
                            для оператора 'fuzzy'.
            session: опциональная сессия SQLAlchemy для выполнения запроса.

        Возвращает:
            Список DTO, удовлетворяющих условиям фильтрации.

        Примечание:
            - Для SQL-операторов фильтрация происходит на уровне БД.
            - Для 'fuzzy' фильтрация выполняется в памяти после получения всех записей,
            поэтому может быть медленной на больших объёмах данных.
        """


        # """
        # Возвращает записи, отфильтрованные по заданным условиям.
        # filters: список словарей с ключами column, operator, value.
        # fuzzy_threshold: порог схожести для нечеткого поиска.
        # """
        self.logger.debug(f"Запрос отфильтрованных записей {self._model_class.__name__} с фильтрами {filters}")
        with self._session_scope(session) as sess:
            query = sess.query(self._model_class)
            # apply_filters теперь возвращает кортеж
            query, post_filters = apply_filters(query, self._model_class, filters, fuzzy_threshold)
            items = query.all()
            if post_filters:
                items = apply_post_filters(items, post_filters, self._model_class)
            # dtos = [self._dto_class.from_orm(item) for item in items]
            dtos = self.get_dtos(items)
            # self.logger.debug(f"Получено {len(dtos)} записей после фильтрации")
            return dtos


    @contextmanager
    def _session_scope(self, session: Optional[Session] = None):
        """
        Контекстный менеджер для работы с сессией.
        Если передана внешняя сессия, используем её (без commit/rollback).
        Иначе создаём новую через self._db.session_scope().
        """
        if session is not None:
            yield session
        else:
            with self._db.session_scope() as new_session:
                yield new_session


    def get_page(self, offset: int, limit: int,
                 filters: Optional[List[Dict[str, Any]]] = None,
                 order_by: Optional[List] = None,
                 session: Optional[Session] = None) -> Tuple[List[DTOType], int]:
        """
        Возвращает страницу DTO и общее количество записей.
        """
        self.logger.debug(f"Запрос страницы {self._model_class.__name__}: offset={offset}, limit={limit}, filters={filters}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            items = repo.get_page(offset, limit, filters=filters, order_by=order_by)
            total = repo.count(filters=filters)
            # dtos = [self._dto_class.from_orm(item) for item in items]
            dtos = self.get_dtos(items)
            return dtos, total



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
        
    def create_patient(self, patient_dto: PatientDTO, session: Optional[Session] = None) -> PatientDTO:
        """
        Создаёт нового пациента. Выполняет валидацию.
        """
        if not patient_dto.first_name or not patient_dto.last_name:
            self.logger.warning("Попытка создания пациента без имени/фамилии")
            raise PatientValidationError("first_name/last_name", "Имя и фамилия обязательны")

        self.logger.debug(f"Создание пациента: {patient_dto}")
        with self._session_scope(session) as sess:
            # Создаём ORM-объект
            patient = self._model_class(
                first_name=patient_dto.first_name,
                last_name=patient_dto.last_name,
                birth_date=patient_dto.birth_date,
                phone=patient_dto.phone,
                email=patient_dto.email,
            )
            repo = self._get_repo(sess)
            repo.add(patient)
            # Чтобы получить id, делаем flush (коммит будет в session_scope)
            sess.flush()
            # dto_out = self._dto_class.from_orm(patient)
            # dto_out = self._dto_class.model_validate(patient)
            dto_out = self.get_dto_out(patient)
            self.logger.info(f"Создан пациент с id={dto_out.id}")
            return dto_out
           
    def update_patient(self, patient_dto: PatientDTO, session: Optional[Session] = None) -> PatientDTO:
        """
        Обновляет существующего пациента.
        """
        if patient_dto.id is None:
            self.logger.warning("Попытка обновления пациента без id")
            raise PatientValidationError("id", "ID пациента обязателен для обновления")

        self.logger.debug(f"Обновление пациента id={patient_dto.id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            patient = repo.get_by_id(patient_dto.id)
            if patient is None:
                raise PatientNotFoundError(patient_dto.id)

            # Обновляем поля
            patient.first_name = patient_dto.first_name
            patient.last_name = patient_dto.last_name
            patient.birth_date = patient_dto.birth_date
            patient.phone = patient_dto.phone
            patient.email = patient_dto.email

            # commit произойдёт автоматически при выходе из session_scope
            # updated_dto = self._dto_class.from_orm(patient)
            # sess.commit()  # Явный коммит
            updated_dto = self.get_dto_out(patient)
            self.logger.info(f"Обновлён пациент id={updated_dto.id}")
            return updated_dto  
        
    # Переопределяем метод для генерации исключения "не найдено"
    def _not_found_exception(self, entity_id: int) -> Exception:
        self.logger.error(f"Пациент с идентификатором {entity_id} не найден.'")
        return PatientNotFoundError(entity_id) # Выбрасывается, когда пациент с указанным идентификатором не найден в базе данных.

    # Для совместимости с существующим кодом оставляем методы-обёртки,
    # которые вызывают методы базового класса
    def get_all_patients(self, session: Optional[Session] = None) -> List[PatientDTO]:
        self.logger.debug("Запрос всех пациентов")
        return self.get_all(session=session)

    def get_patient_by_id(self, patient_id: int, session: Optional[Session] = None) -> PatientDTO:
        self.logger.debug(f"Запрос пациента по id={patient_id}")
        return self.get_by_id(patient_id, session=session)

    def delete_patient(self, patient_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет пациента. Приёмы удаляются каскадно благодаря настройкам модели.
        После удаления проверяет, остались ли заметки, и удаляет неиспользуемые.
        """
        self.logger.debug(f"Удаление пациента id={patient_id}")
        with self._session_scope(session) as sess:
            # Получаем пациента со связанными приёмами (чтобы собрать ID заметок)
            # patient = session.get(Patient, patient_id)
            patient = sess.query(Patient).options(selectinload(Patient.appointments)).filter(Patient.id == patient_id).first()
            if patient is None:
                raise PatientNotFoundError(patient_id)

            # Собираем ID заметок, привязанных к приёмам этого пациента
            note_ids = [app.note_id for app in patient.appointments if app.note_id]

            # Удаляем пациента — каскадно удалятся все его приёмы и фото
            sess.delete(patient)
            sess.flush() # принудительно выполняем удаление, чтобы обновить состояние БД

            # Проверяем каждую заметку: остались ли ещё приёмы, ссылающиеся на неё           
            note_service = NoteService(self._db, logger_name=self.logger.name + ".NoteService")
            for note_id in note_ids:
                note_service.cleanup_unused_note(note_id, sess)

            self.logger.info(f"Удалён пациент id={patient_id}")
   
    def get_patients_filtered(self, filters: List[Dict[str, Any]], fuzzy_threshold: int = 60,
                              session: Optional[Session] = None) -> List[PatientDTO]:
        self.logger.debug(f"Запрос пациентов с фильтрацией: filters={filters}, fuzzy_threshold={fuzzy_threshold}")
        return self.get_filtered(filters, fuzzy_threshold, session=session)
   
class NoteService(BaseService[AppointmentNote, AppointmentNoteDTO, AppointmentNoteRepository]):
    """
    Сервис для работы с заметками приёмов.
    Все методы поддерживают опциональный параметр session для объединения в одну транзакцию.
    """

    def __init__(self, db: Database, logger_name: Optional[str] = None):
        if logger_name is None:
            logger_name = self.__class__.__name__
        super().__init__(
            db=db,
            repo_class=AppointmentNoteRepository,
            model_class=AppointmentNote,
            dto_class=AppointmentNoteDTO,
            logger_name=logger_name
        )

    def _not_found_exception(self, entity_id: int) -> Exception:
        return AppointmentNoteNotFoundError(entity_id)

    # ----------------------------------------------------------------------
    # Переопределённые методы базового класса (если нужно добавить логику)
    # ----------------------------------------------------------------------

    def get_all(self, session: Optional[Session] = None) -> List[AppointmentNoteDTO]:
        """
        Возвращает все заметки.
        """
        self.logger.debug("Запрос всех заметок")
        return super().get_all(session=session)

    def get_by_id(self, note_id: int, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Возвращает заметку по ID.
        """
        self.logger.debug(f"Запрос заметки id={note_id}")
        return super().get_by_id(note_id, session=session)

    def delete(self, note_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет заметку по ID.
        """
        self.logger.debug(f"Удаление заметки id={note_id}")
        super().delete(note_id, session=session)

    # ----------------------------------------------------------------------
    # Специфические методы сервиса
    # ----------------------------------------------------------------------
    def get_note(self, note_id: int, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Синоним для get_by_id.
        """
        return self.get_by_id(note_id, session=session)

    def create_note(self, text: str, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Создаёт новую заметку с указанным текстом.
        """
        self.logger.debug("Создание заметки")
        with self._session_scope(session) as sess:
            note = self._model_class(text=text)
            sess.add(note)
            sess.flush()
            # dto_out = self._dto_class.from_orm(note)
            dto_out = self.get_dto_out(note)
            self.logger.info(f"Создана заметка id={dto_out.id}")
            return dto_out

    def update_note(self, note_id: int, text: str, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Обновляет текст существующей заметки.
        """
        self.logger.debug(f"Обновление заметки id={note_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            note = repo.get_by_id(note_id)
            if note is None:
                raise AppointmentNoteNotFoundError(note_id)
            note.text = text
            # updated_dto = self._dto_class.from_orm(note)
            updated_dto = self.get_dto_out(note)
            self.logger.info(f"Обновлена заметка id={updated_dto.id}")
            return updated_dto

    def delete_note(self, note_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет заметку (синоним delete).
        """
        self.logger.debug(f"Удаляет запись по ID ({note_id})")
        self.delete(note_id, session=session)

    def get_or_create_note(self, text: str, session: Optional[Session] = None) -> Optional[AppointmentNoteDTO]:
        """
        Возвращает существующую заметку по точному совпадению текста,
        либо создаёт новую, если такой ещё нет.
        Если text пустой или None, возвращает None.
        """
        if not text:
            return None

        self.logger.debug(f"Поиск или создание заметки: {text[:50]}...")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            note = repo.get_by_text_exact(text)
            if note:
                self.logger.debug(f"Найдена существующая заметка id={note.id}")
                # return self._dto_class.from_orm(note)
                return self.get_dto_out(note)

            # Создаём новую заметку
            note = self._model_class(text=text)
            sess.add(note)
            sess.flush()
            self.logger.info(f"Создана новая заметка id={note.id}")
            # return self._dto_class.from_orm(note)
            return self.get_dto_out(note)

    def create_note_from_file(self, file_path: str, session: Optional[Session] = None) -> AppointmentNoteDTO:
        """
        Создаёт заметку, читая текст из файла.
        :raises FileNotFoundError, IOError
        """
        self.logger.debug(f"Создание заметки из файла: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            self.logger.exception(f"Ошибка чтения файла {file_path}")
            raise  # пробрасываем дальше
        return self.create_note(text, session=session)      
      
    def cleanup_unused_note(self, note_id: int, session: Session) -> None:
        """
        Удаляет заметку, если на неё больше не ссылаются никакие приёмы.
        Если заметка используется, ничего не делает.
        """
        if note_id is None:
            return
        # Проверяем, остались ли приёмы с этой заметкой
        remaining = session.query(Appointment).filter(Appointment.note_id == note_id).count()
        if remaining == 0:
            note_repo = AppointmentNoteRepository(session)
            note = note_repo.get_by_id(note_id)
            if note:
                note_repo.delete(note)
                self.logger.info(f"Заметка id={note_id} удалена как неиспользуемая")       

class AppointmentService(BaseService[Appointment, AppointmentDTO, AppointmentRepository]):
    """
    Сервис для работы с приёмами.
    Все методы, возвращающие DTO, стараются использовать подгрузку связей (patient, note)
    для предотвращения N+1 запросов.
    """

    def __init__(
        self,
        db: Database,
        note_service: Optional['NoteService'] = None,  
        photo_service: Optional['PhotoService'] = None,   
        logger_name: Optional[str] = None
    ):
        if logger_name is None:
            logger_name = self.__class__.__name__
          
        # Вызов конструктора базового класса с указанием классов модели, DTO и репозитория
  
        super().__init__(
            db=db,
            repo_class  = AppointmentRepository,
            model_class = Appointment,
            dto_class   = AppointmentDTO,
            logger_name = logger_name
        )

        self._note_service = note_service
        self._photo_service = photo_service

        # Если не передан, создадим по умолчанию (для совместимости)
        if self._note_service is None:
            self._note_service = NoteService(db, logger_name=logger_name + ".NoteService")

    def _not_found_exception(self, entity_id: int) -> Exception:
        """Возвращает исключение, если приём не найден."""
        self.logger.error(f"Приём с идентификатором {entity_id} не найден.")
        return AppointmentNotFoundError(entity_id)

    def get_dtos(
            self, 
            item_s:Union[List[AppointmentDTO], AppointmentDTO]  
    )-> Union[List[AppointmentDTO], AppointmentDTO] : 
        """
        Возвращает список DTO из списка объектов или один DTO из объекта.
        Если получен список объектов, то для каждого объекта пытается создать DTO.
        Если объект не может быть конвертирован в DTO, то выбрасывается исключение.
        """
        if isinstance(item_s, list):
            # Если получен список объектов
            dtos = []  # список DTO
            for item in item_s:
                # для каждого объекта пытаемся создать DTO
                dtos.append(self.get_dtos(item))  # рекурсивно добавляем DTO в список
            self.logger.debug(f"Получено {len(dtos)} записей")
            return dtos
        else:
            # данные из ТБ
            try:
                # создаем DTO из объекта
                dto = self._dto_class.model_validate(item_s)  
            except Exception as e:
                # если объект не может быть конвертирован в DTO, то выбрасываем исключение
                self.logger.error(f"Ошибка валидации для объекта: {item_s}")
                raise e
            
            # данные, которые подтягиваем отдельно
            try:
                # если объект имеет поле patient, то подгружаем его имя
                if item_s.patient:
                    dto.patient_name = f"{item_s.patient.last_name} {item_s.patient.first_name}"
            except Exception as e:
                # если нет поля patient, то выбрасываем исключение
                self.logger.error(f"Ошибка валидации для объекта (patient_name): {item_s}")
                raise e
            
            try:
                # если объект имеет поле note, то подгружаем текст заметки
                if item_s.note:
                    dto.note_text = item_s.note.text
            except Exception as e:
                # если нет поля note, то выбрасываем исключение
                self.logger.error(f"Ошибка валидации для объекта (note): {item_s}")
                raise e
            
            return dto

    # ----------------------------------------------------------------------
    # Переопределение методов получения данных с подгрузкой связей
    # ----------------------------------------------------------------------

    def get_all(self, session: Optional[Session] = None) -> List[AppointmentDTO]:
        """Возвращает все приёмы с подгруженными пациентом и заметкой."""
        self.logger.debug("get_all (with relations)")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            items = repo.get_all_with_relations()  # метод репозитория с подгрузкой
            # return [self._dto_class.from_orm(item) for item in items]
            # dtos = [self._dto_class.from_orm(item) for item in items]
            # dtos = [self._dto_class.model_validate(item) for item in items]
            dtos = self.get_dtos(items)
            # self.logger.debug(f"Получено {len(dtos)} записей")

            # dtos = []
            # for item in items:
            #     # dto = self.get_dtos(item)
            #     dto = self._dto_class.model_validate(item)
                
            #     # Заполняем виртуальные поля
            #     if item.patient:
            #         dto.patient_name = f"{item.patient.last_name} {item.patient.first_name}"
            #     if item.note:
            #         dto.note_text = item.note.text
            return dtos
        
    def get_appointments_by_patient(self, patient_id: int, session: Optional[Session] = None) -> List[AppointmentDTO]:
        """Возвращает приёмы пациента с подгруженными связями."""
        self.logger.debug(f"get_appointments_by_patient: patient_id={patient_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            items = repo.get_by_patient_with_relations(patient_id)
            # return [self._dto_class.from_orm(item) for item in items]
            # dtos = [self._dto_class.from_orm(item) for item in items]
            # dtos = [self._dto_class.model_validate(item) for item in items]
            dtos = self.get_dtos(items)
            # self.logger.debug(f"Получено {len(dtos)} записей для пациента {patient_id}")
            return dtos

    def get_appointment(self, appointment_id: int, session: Optional[Session] = None) -> AppointmentDTO:
        """Возвращает один приём по ID с подгруженными связями."""
        self.logger.debug(f"get_appointment: id={appointment_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            item = repo.get_by_id_with_relations(appointment_id)
            if item is None:
                raise AppointmentNotFoundError(appointment_id)
            # return self._dto_class.from_orm(item)
            return  self.get_dtos(item)

    def get_filtered(
            self, 
            filters: List[Dict[str, Any]], 
            fuzzy_threshold: int = 60,
            session: Optional[Session] = None,
        ) -> List[AppointmentDTO]:
        """Возвращает отфильтрованные приёмы с подгруженными связями."""
        # from ..utils.filtering import apply_filters, apply_post_filters

        self.logger.debug(f"get_filtered (with relations) filters={filters}")
        with self._session_scope(session) as sess:
            query = sess.query(self._model_class).options(
                joinedload(Appointment.patient),
                joinedload(Appointment.note)
            )
            query, post_filters = apply_filters(query, self._model_class, filters, fuzzy_threshold)
            items = query.all()
            if post_filters:
                items = apply_post_filters(items, post_filters, self._model_class)
            # return [self._dto_class.from_orm(item) for item in items]
            return self.get_dtos(items)

    # ----------------------------------------------------------------------
    # Методы создания, обновления и удаления (без изменений)
    # ----------------------------------------------------------------------

    def create_appointment(self, dto: AppointmentDTO, note_text: Optional[str] = None,
                           session: Optional[Session] = None) -> AppointmentDTO:
        """
        Создаёт новый приём.
        :param dto: DTO с данными (используются patient_id, date, time, note_id).
        :param note_text: текст заметки. Если передан, заметка будет найдена или создана,
                          и её ID автоматически подставлен (заменяет dto.note_id).
        :param session: опциональная сессия для работы в одной транзакции.
        :raises PatientNotFoundError: если пациент с указанным ID не найден.
        """
        self.logger.debug(f"Создание приёма: {dto}, note_text={note_text}")

        with self._session_scope(session) as sess:
            # Проверка существования пациента
            patient_repo = PatientRepository(sess)
            patient = patient_repo.get_by_id(dto.patient_id)
            if patient is None:
                raise PatientNotFoundError(dto.patient_id)

            # Обработка заметки
            note_id = dto.note_id
            if note_text:
                # note_service = NoteService( # создаём экземпляр (можно без логгера)
                #     self._db,
                #     logger_name=self.logger.name + ".NoteService" # (можно без логгера)
                #     )  
                note_dto = self._note_service.get_or_create_note(note_text, session=sess)
                note_id = note_dto.id if note_dto else None

            appointment = self._model_class(
                patient_id=dto.patient_id,
                date=dto.date,
                time=dto.time,
                note_id=note_id
            )
            sess.add(appointment)
            sess.flush()  # чтобы получить id
            # dto_out = self._dto_class.from_orm(appointment)
            dto_out = self.get_dto_out(appointment)
            self.logger.info(f"Создан приём id={dto_out.id}")
            return dto_out

    def update_appointment(self, dto: AppointmentDTO, note_text: Optional[str] = None,
                           session: Optional[Session] = None) -> AppointmentDTO:
        """
        Обновляет существующий приём.
        Если передан note_text, заметка будет найдена или создана, и ID старой заметки
        будет заменён на новую. Старая заметка будет удалена, если она больше не используется.
        """
        if dto.id is None:
            self.logger.warning("Попытка обновления приёма без id")
            raise ValueError("ID приёма не указан")

        self.logger.debug(f"Обновление приёма id={dto.id}")

        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            app = repo.get_by_id_with_relations(dto.id)  # используем метод с подгрузкой
            if app is None:
                raise AppointmentNotFoundError(dto.id)

            old_note_id = app.note_id

            # Обновляем основные поля
            app.date = dto.date
            app.time = dto.time

            # Обработка заметки
            if note_text is not None:
                # note_service = NoteService(self._db)
                note_dto = self._note_service.get_or_create_note(note_text, session=sess)
                app.note_id = note_dto.id if note_dto else None
            elif dto.note_id is not None:
                app.note_id = dto.note_id
            # иначе оставляем текущую заметку

            # Если заметка изменилась и была старая заметка
            if old_note_id is not None and old_note_id != app.note_id:
                # Проверяем, остались ли другие приёмы, ссылающиеся на старую заметку
                #  self._cleanup_unused_note(old_note_id, sess)
                 self._note_service.cleanup_unused_note(old_note_id, sess)

            # updated_dto = self._dto_class.from_orm(app)
            updated_dto = self.get_dto_out(app)
            self.logger.info(f"Обновлён приём id={updated_dto.id}")
            return updated_dto   

    def delete_appointment(
            self, 
            appointment_id: int, 
            session: Optional[Session] = None
        ) -> None:
        """
        Удаляет приём и, если заметка больше не используется, удаляет её.
        
        Шаги:
        1. Получаем приём из базы данных с подгруженными связями.
        2. Если приём не найден, выбрасываем исключение.
        3. Если приём имеет фото, удаляем их.
        4. Если приём имел заметку, и она больше не используется, удаляем ее.
        5. Удаляем сам приём.
        """
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            appointment = repo.get_by_id_with_relations(appointment_id)
            if appointment is None:
                raise AppointmentNotFoundError(appointment_id)

            # Удаляем фото, если есть сервис
            if self._photo_service is not None:
                for photo in appointment.photos:
                    self._photo_service.delete_photo(photo.id, session=sess)
            else:
                self.logger.warning("PhotoService not provided, photos will not be deleted from disk")      
            
            # Если приём имел заметку, и она больше не используется, удаляем ее
            note_id = appointment.note_id
            
            # Удаляем приём
            repo.delete(appointment)
            sess.flush()

            if note_id is not None:
                self._note_service.cleanup_unused_note(note_id, sess)


    def get_appointments_by_patient_page(
        self, 
        patient_id: int,  # ID пациента, для которого хотим получить страницу приёмов
        offset: int,  # смещение страницы
        limit: int,  # размер страницы
        filters: Optional[List[Dict[str, Any]]] = None,  # фильтры SQL
        order_by: Optional[List] = None,  # сортировка SQL
        session: Optional[Session] = None  # сессия для работы в одной транзакции
    ) -> Tuple[List[AppointmentDTO], int]:
        """
        Возвращает страницу приёмов пациента с подгруженными связями.
        """
        self.logger.debug(f"Запрос страницы приёмов пациента {patient_id}: offset={offset}, limit={limit}")
        with self._session_scope(session) as sess:
            # получаем репозиторий
            repo = self._get_repo(sess)
            items = repo.get_page_by_patient(patient_id, offset, limit, filters=filters, order_by=order_by)
            total = repo.count_by_patient(patient_id, filters=filters)
            # dtos = [self._dto_class.from_orm(item) for item in items]
            dtos = self.get_dtos(items)
            return dtos, total

class PhotoService(
    BaseService[Photo, PhotoDTO, PhotoRepository]
):
    """
    Сервис для работы с фотографиями приёмов.
    Все методы поддерживают опциональный параметр session для объединения в одну транзакцию.
    """

    def __init__(
        self, 
        db: Database, 
        photos_storage_path: str, 
        logger_name: 
        Optional[str] = None
    ):
        if logger_name is None:
            logger_name = self.__class__.__name__
        super().__init__(
            db=db,
            repo_class=PhotoRepository,
            model_class=Photo,
            dto_class=PhotoDTO,
            logger_name=logger_name
        )
        self._storage_path = photos_storage_path
        self._ensure_storage_exists()

    def _not_found_exception(self, entity_id: int) -> Exception:
        return PhotoNotFoundError(entity_id)

    # ----------------------------------------------------------------------
    # Специфические методы сервиса
    # ----------------------------------------------------------------------
 
    # def add_photo_to_appointment(self, appointment_id: int, source_file_path: str,
    #                               description: str = "", session: Optional[Session] = None) -> PhotoDTO:
    #     """
    #     Добавляет фото к приёму: копирует файл в хранилище и создаёт запись в БД.
    #     """
    #     self.logger.debug(f"Добавление фото к приёму id={appointment_id}, файл={source_file_path}, описание='{description}'")
    #     with self._session_scope(session) as sess:
    #         # Проверяем существование приёма
    #         app_repo = AppointmentRepository(sess)
    #         app = app_repo.get_by_id(appointment_id)
    #         if app is None:
    #             raise AppointmentNotFoundError(appointment_id)

    #         # Копируем файл (операция вне БД)
    #         rel_path = self._copy_file_to_storage(source_file_path, appointment_id)

    #         # Создаём запись в БД
    #         photo = self._model_class(
    #             appointment_id=appointment_id,
    #             file_path=rel_path,
    #             description=description
    #         )
    #         sess.add(photo)
    #         sess.flush()  # получаем id
    #         dto_out = self._dto_class.from_orm(photo)
    #         self.logger.info(f"Добавлено фото id={dto_out.id} к приёму {appointment_id}")
    #         return dto_out

    # ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}

    # def _is_allowed_file(filename: str) -> bool:
    #     ext = os.path.splitext(filename)[1].lower()
    #     return ext in ALLOWED_EXTENSIONS

    def add_photo_to_appointment(
            self, 
            appointment_id: int, 
            source_file_path: str,
            description: str = "", 
            session: Optional[Session] = None,
    )-> PhotoDTO:
        """
        Добавляет фотографию к указанному приёму.

        Процесс:
            1. Проверяет существование исходного файла.
            2. Создаёт запись в БД с временным путём 'pending' (чтобы получить ID фото).
            3. Копирует файл в хранилище, формируя имя на основе appointment_id и photo.id.
            4. Обновляет путь в записи на реальный относительный путь.
            5. Если на любом этапе (кроме проверки) возникает ошибка, транзакция откатывается,
            и запись не сохраняется.

        Параметры:
            appointment_id: ID приёма, к которому добавляется фото.
            source_file_path: путь к исходному файлу изображения на диске.
            description: описание фотографии (необязательно).
            session: опциональная сессия SQLAlchemy для работы в рамках внешней транзакции.

        Возвращает:
            PhotoDTO созданной фотографии.

        Исключения:
            AppointmentNotFoundError: если приём с указанным ID не существует.
            PhotoFileError: если исходный файл не найден, не удаётся его скопировать
                            или возникает другая ошибка ввода-вывода.
        """
        self.logger.debug(f"Добавление фото к приёму id={appointment_id}, файл={source_file_path}, описание='{description}'")
        
        # 1. Проверка существования и типа файла
        if not os.path.isfile(source_file_path):
            raise PhotoFileError(source_file_path, "проверка", "файл не существует")

        # if not self._is_allowed_file(source_file_path):
        #     raise PhotoFileError(source_file_path, "проверка", "неподдерживаемый формат файла")

        # # 2. Проверка свободного места и прав (опционально)
        # file_size = os.path.getsize(source_file_path)

        with self._session_scope(session) as sess:
            # Проверяем существование приёма
            app_repo = AppointmentRepository(sess)
            app = app_repo.get_by_id(appointment_id)
            if app is None:
                raise AppointmentNotFoundError(appointment_id)

            # 1. Создаём запись с временным путём (помечаем как ожидающую)
            photo = self._model_class(
                appointment_id=appointment_id,
                file_path='pending',  # временная метка
                description=description
            )
            sess.add(photo)
            sess.flush()  # получаем ID фото, нужен для имени файла

            # 2. Копируем файл в хранилище
            try:
                # Генерируем целевой путь на основе appointment_id и photo.id
                target_path = self._generate_target_path(source_file_path, appointment_id, photo.id)
                # Создаём папку назначения, если её нет
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copy2(source_file_path, target_path)
                self.logger.debug(f"Файл скопирован: {source_file_path} -> {target_path}")
            except Exception as e:
                # Если копирование не удалось — удаляем созданную запись
                # sess.delete(photo) # ненужен, так как дальше должен быть rollback
                # sess.commit()  # фиксируем удаление (чтобы не оставлять pending-запись)
                self.logger.exception(f"Ошибка копирования файла {source_file_path}")
                raise PhotoFileError(source_file_path, "копирование", str(e))

            # 3. Обновляем путь в записи на реальный относительный путь
            photo.file_path = os.path.relpath(target_path, self._storage_path)
            # при выходе из контекста произойдёт commit, сохраняющий изменения

            # dto_out = self._dto_class.from_orm(photo)
            dto_out = self.get_dto_out(photo)
            self.logger.info(f"Добавлено фото id={dto_out.id} к приёму {appointment_id}")
            return dto_out
    # def get_photos_for_appointment(self, appointment_id: int, session: Optional[Session] = None) -> List[PhotoDTO]:
    #     """
    #     Возвращает список фотографий для указанного приёма.
    #     """
    #     self.logger.debug(f"Запрос фото для приёма id={appointment_id}")
    #     with self._session_scope(session) as sess:
    #         repo = self._get_repo(sess)
    #         photos = repo.get_by_appointment(appointment_id)
    #         # return [self._dto_class.from_orm(p) for p in photos]
    #         dto_out = [self._dto_class.from_orm(p) for p in photos]
    #         self.logger.info(f"Запрос фото для приёма id={appointment_id}. Получено {len(dto_out)} записей")
    #         return dto_out

    def get_photos_for_appointment(
            self, 
            appointment_id: int, 
            session: Optional[Session] = None
        ) -> List[PhotoDTO]:
        """
        Возвращает список фотографий для указанного приёма.

        1. Создаём сессию SQLAlchemy (если не указана, то создаем новую).
        2. Получаем репозиторий фотографий.
        3. Получаем список фотографий для указанного приёма.
        4. Создаём список DTO для фотографий.
        5. Если файл фотографии не существует на диске или имеет статус 'pending', то выводим предупреждение.
        6. Возвращаем список DTO для фотографий.
        """
        self.logger.debug(f"Запрос фото для приёма id={appointment_id}")

        # 1. Создаём сессию SQLAlchemy (если не указана, то создаем новую)
        with self._session_scope(session) as sess:
            # 2. Получаем репозиторий фотографий
            repo = self._get_repo(sess)
            
            # 3. Получаем список фотографий для указанного приёма
            photos = repo.get_by_appointment(appointment_id)
            
            # 4. Создаём список DTO для фотографий
            dtos = []
            for p in photos:
                full_path = os.path.join(self._storage_path, p.file_path)

                # 5. Если файл фотографии не существует на диске или имеет статус 'pending', то выводим предупреждение
                if p.file_path == 'pending':
                    self.logger.warning(f"Фото id={p.id} имеет статус 'pending' (файл не загружен)")
                elif not os.path.exists(full_path):
                    self.logger.warning(f"Файл фото id={p.id} отсутствует на диске: {full_path}")
                    
                # 6. Создаём DTO для фотографии и добавляем в список
                # dtos.append(self._dto_class.from_orm(p))
                dtos.append(self.get_dto_out(p))
            
            # 7. Возвращаем список DTO для фотографий
            self.logger.info(f"Запрос фото для приёма id={appointment_id}. Получено {len(dtos)} записей")
            return dtos
    
    def delete_photo(self, photo_id: int, session: Optional[Session] = None) -> None:
        """
        Удаляет фото:
        1. Удаляет запись из БД.
        2. После успешного удаления записи пытается удалить файл.
        Если файл не удалился, только логирует ошибку (данные уже консистентны).
        """
        self.logger.debug(f"Удаление фото id={photo_id}")
        with self._session_scope(session) as sess:
            repo = self._get_repo(sess)
            photo = repo.get_by_id(photo_id)
            if photo is None:
                raise PhotoNotFoundError(photo_id)
            
            # Запоминаем путь к файлу до удаления записи
            file_path_to_delete = os.path.join(self._storage_path, photo.file_path)

            # Сначала пытаемся удалить файл
            try:
                if os.path.exists(file_path_to_delete):
                    os.remove(file_path_to_delete)
                    self.logger.debug(f"Удалён файл {file_path_to_delete}")
            except Exception as e:
                self.logger.exception(f"Не удалось удалить файл {file_path_to_delete}")
                raise PhotoFileError(file_path_to_delete, "удаление", str(e))

            # Если файл успешно удалён (или не существовал), удаляем запись
            repo.delete(photo) # Удаляем запись
            self.logger.info(f"Удалена запись фото id={photo_id}")

    # ----------------------------------------------------------------------
    # Вспомогательные методы (не требуют сессии)
    # ----------------------------------------------------------------------

    def _generate_target_path(self, source_path: str, appointment_id: int, photo_id: int) -> str:
        """
        Генерирует полный путь для сохранения файла на основе appointment_id и photo_id.

        Формат: <storage>/app_<appointment_id>/<photo_id>_<name(base_name)>_<unique_id>_<ext(base_name)>

        <storage> - путь к папке для хранения файлов
        app_<appointment_id> - папка для хранения файлов приёма с указанным ID
        <photo_id>_<name(base_name)>_<unique_id>_<ext(base_name)> - имя файла

        <name(base_name)> - имя файла без расширения (например, "image")
        <unique_id> - уникальный идентификатор (например, "12345678")
        <ext(base_name)> - расширение файла (например, ".jpg")
        """
        base_name = os.path.basename(source_path)
        name, ext = os.path.splitext(base_name)
        unique_id = uuid.uuid4().hex[:8]  # первые 8 символов UUID
        filename = f"{photo_id}_{name}_{unique_id}{ext}"
        app_folder = os.path.join(self._storage_path, f"app_{appointment_id}")
        return os.path.join(app_folder, filename)


    def _ensure_storage_exists(self):
        """Создаёт папку для фото, если её нет."""
        os.makedirs(self._storage_path, exist_ok=True)


            