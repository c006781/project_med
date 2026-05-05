# app/repositories/repositories_all.py
"""
Слой доступа к данным (репозитории).

Каждый репозиторий инкапсулирует запросы к конкретной таблице БД.
Базовый класс :class:`BaseRepository` предоставляет общие методы:
- get_by_id, get_all, add, delete
- get_page (пагинация с фильтрацией)
- get_unique_values (уникальные значения столбца)

Конкретные репозитории:
- :class:`PatientRepository`
- :class:`AppointmentRepository`
- :class:`AppointmentNoteRepository`
- :class:`PhotoRepository`

Пример использования:
    >>> from app.database import Database
    >>> db = Database("sqlite:///clinic.db")
    >>> with db.session_scope() as session:
    ...     repo = PatientRepository(session)
    ...     patient = repo.get_by_id(1)
    ...     print(patient.first_name)
"""

# Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from typing import (
    List, Optional, Any, 
    Dict, TypeVar, Generic
)

from abc import ABC, abstractmethod

from app.utils.logger.logger import AppLogger

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
from app.database.database_shema.clinic import AppointmentNote, Appointment, Patient, Photo
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...backend.bd.clinic import AppointmentNote, Appointment, Patient, Photo
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
# from app.utils.logger.logger import AppLogger
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...utils.logger.logger import AppLogger
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
from app.utils.filtering.filtering import apply_filters
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...utils.filtering.filtering import apply_filters
#     except ImportError as e:
#         pass #  raise # e # pass

# Сторонние библиотеки

from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import select

ModelType = TypeVar('ModelType')

class BaseRepository(Generic[ModelType], ABC):
    """Все репозитории должны наследовать этот класс."""

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, session: Session):
        """
        Инициализирует репозиторий.

        :param session: сессия для работы с БД
        :type session: Session
        """
        self._session = session

        self.logger = AppLogger.get_instance(
            name = self.__class__.__name__,
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_with_relations(
        self,
        entity_id: int, 
        relations: List[str]
    ):
        """
        Возвращает объект по ID с подгруженными связями.

        :param entity_id: ID объекта
        :type entity_id: int
        :param relations: список связей, которые нужно подгрузить
        :type relations: List[str]
        :return: объект с подгруженными связями
        :rtype: self.model_class
        """
        query = self._session.query(self.model_class)

        self.logger.debug(
            f"get_with_relations: "
            f"entity_id {entity_id} "
            f"query {query} "
            f"self.model_class {self.model_class}"
        )

        for rel in relations:
            self.logger.debug(f"get_with_relations: rel {rel}")

            if hasattr(self.model_class, rel):
                query = query.options(
                    joinedload(
                        getattr(self.model_class, rel)
                    )
                )   
                
                self.logger.debug(
                    f"get_with_relations: "
                    f"rel {rel} "
                    f"query {query}"
                )
        
        self.logger.debug(
            f"self.model_class.id {self.model_class.id} "
            f"entity_id {entity_id}"
        )

        return query.filter(self.model_class.id == entity_id).first()

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(        
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_by_id(self, entity_id: int) -> Optional[ModelType]:
        """
        Возвращает запись по ID.

        :param entity_id: ID записи
        :type entity_id: int
        :return: запись, если найдена, иначе None
        :rtype: Optional[ModelType]
        """
        self.logger.debug(f"get_by_id: {entity_id}")
        
        return self._session.get(self.model_class, entity_id)
    
    # def get_all(self) -> List[ModelType]:
    #     self.logger.debug(f"get_all")
    #     return self._session.get(self.model_class).all()
    
    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_all(self) -> List[ModelType]:
        """
        Возвращает список всех записей в БД.
        :return: список записей в виде объектов ModelType
        """
        self.logger.debug(f"get_all")
        return self._session.query(self.model_class).all()

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add(self, entity: ModelType) -> ModelType:
        """
        Добавляет запись в БД.

        :param entity: запись для добавления
        :type entity: ModelType
        :return: добавленная запись
        :rtype: ModelType
        """
        self.logger.debug(f"add: {entity}")
        self._session.add(entity)
        return entity

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def delete(self, entity: ModelType) -> None:
        """
        Удаляет запись из БД.

        :param entity: запись для удаления
        :type entity: ModelType
        :return: None
        """
        
        self.logger.debug(f"delete: {entity}")
        self._session.delete(entity)

    # # Метод update – если мы хотим его оставить
    # def update(self, entity: ModelType) -> ModelType:
    #     # Предполагаем, что объект уже прикреплён к сессии (получен через get_by_id)
    #     # Если же объект может быть detached, используем merge:
    #     # return self._session.merge(entity)
    #     # Но тогда он должен возвращать обновлённый объект.
    #     # Для простоты можно оставить без тела, просто зафиксировать, что изменения отслеживаются.
    #     self.logger.debug(f"update: {entity} (изменения отслеживаются автоматически)")
    #     return self._session.merge(entity)  

    @property
    @abstractmethod
    def model_class(self):
        """Должен быть переопределён в наследниках."""
        raise NotImplementedError("Подклассы должны определить model_class")
    
    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_unique_values(self, column_name: str) -> List[Any]:
        """
        Возвращает список уникальных значений столбца.

        :param column_name: имя столбца
        :type column_name: str
        :return: список уникальных значений
        :rtype: List[Any]
        """
        
        self.logger.debug(f"get_unique_values: column_name = {column_name}")
        if self.model_class is None:
            err_ = NotImplementedError("model_class не определён в репозитории")
            self.logger.exception(err_.message)
            raise err_
        try:
            column = getattr(self.model_class, column_name, None)
            if column is None:
                self.logger.warning(f"Столбец '{column_name}' не найден в модели {self.model_class.__name__}")
                return []
            stmt = select(column).distinct()
            return self._session.execute(stmt).scalars().all()
        except Exception as e:
            self.logger.exception(f"Ошибка в get_unique_values (столбец '{column_name}'): {e}")
            raise  # пробрасываем исключение, чтобы не скрывать проблемы 

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_page(
        self, 
        offset: int, 
        limit: int,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[List] = None
    ) -> List[ModelType]:
        """
        Возвращает страницу записей с учётом SQL-фильтров.

        :param offset: смещение страницы (начиная с 0)
        :type offset: int
        :param limit: количество записей на странице
        :type limit: int
        :param filters: список словарей с фильтрами для записей
        :type filters: Optional[List[Dict[str, Any]]]
        :param order_by: список полей для сортировки записей
        :type order_by: Optional[List]
        :return: список записей на странице
        :rtype: List[ModelType]
        """
        
        query = self._session.query(self.model_class)
        if filters:
            # Отфильтровываем fuzzy-операторы, они не поддерживаются на уровне SQL
            sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
            if sql_filters:
                query, _ = apply_filters(query, self.model_class, sql_filters)
        if order_by:
            query = query.order_by(*order_by)
        return query.offset(offset).limit(limit).all()

    @AppLogger.get_instance(
        name = 'BaseRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def count(self, filters: Optional[List[Dict[str, Any]]] = None) -> int:
        """
        Возвращает количество записей в базе данных с учётом фильтров.
        
        :param filters: список словарей с фильтрами для записей
        :type filters: Optional[List[Dict[str, Any]]]
        :return: количество записей
        :rtype: int
        """
        query = self._session.query(self.model_class)
        if filters:
            sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
            if sql_filters:
                query, _ = apply_filters(query, self.model_class, sql_filters)
        return query.count()



class AppointmentNoteRepository(BaseRepository):

    model_class =  AppointmentNote
    
    @AppLogger.get_instance(
        name = 'AppointmentNoteRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_by_text_exact(self, text: str):
        """
        Возвращает запись с точным текстом или None, если не найдено.  (чувствительно к регистру)

        :param text: текст для поиска
        :type text: str
        :return: запись или None
        :rtype: Optional[AppointmentNote]
        """
    
        self.logger.debug(f"get_by_text_exact: text = {text}")
        return self._session.query(AppointmentNote).filter(AppointmentNote.text == text).first()

class AppointmentRepository(BaseRepository):

    model_class =  Appointment

    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_all_with_note(self):
        """
        Возвращает все приёмы с подгруженной заметкой.

        :return: список приёмов
        :rtype: List[Appointment]
        """
        self.logger.debug(f"get_all_with_note")
        return self._session.query(Appointment).options(joinedload(Appointment.note)).all()

    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_joinedload_Appointment(self):
        return [
            joinedload(Appointment.patient),
            joinedload(Appointment.reason_note),
            joinedload(Appointment.procedure_note),
            joinedload(Appointment.recommendations_note),
            joinedload(Appointment.note),
            joinedload(Appointment.cost_procedure_note),
            # joinedload(Appointment.photos)   # если нужно, можно оставить
        ]

    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_all_with_relations(self) -> List[Appointment]:
        """
        Возвращает все приёмы с подгруженными пациентом и заметкой.

        :return: список приёмов
        :rtype: List[Appointment]
        """
        self.logger.debug("get_all_with_relations")

        return self._session.query(Appointment).options(
            # joinedload(Appointment.patient),
            # joinedload(Appointment.note)
            *self._get_joinedload_Appointment()
        ).all()
    
    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_by_patient_with_relations(self, patient_id: int) -> List[Appointment]:
        """
        Возвращает приёмы пациента с подгруженными пациентом и заметкой.

        :param patient_id: ID пациента
        :type patient_id: int
        :return: список приёмов
        :rtype: List[Appointment]
        """
        self.logger.debug(
            f"get_by_patient_with_relations: "
            f"patient_id={patient_id}"
        )

        return self._session.query(Appointment).filter_by(patient_id=patient_id).options(
            # joinedload(Appointment.patient),
            # joinedload(Appointment.note),
            # # joinedload(Appointment.photos),
            *self._get_joinedload_Appointment()
        ).all()

    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_by_id_with_relations(self, appointment_id: int) -> Optional[Appointment]:
        """
        Возвращает приём по ID с подгруженными связями (пациентом и заметкой).

        :param appointment_id: ID приёма
        :type appointment_id: int
        :return: приём или None, если не найдено
        :rtype: Optional[Appointment]
        """
        # Получаем приём с подгруженными связями (пациентом и заметкой)
        # с помощью метода joinedload, который подгруживает связанные таблицы
        # для получения полного объекта приёма с подгруженными связями
        # мы используем метод options с параметром joinedload
        #
        # В методе joinedload мы указываем связанные таблицы, которые
        # необходимо подгружить для получения полного объекта приёма
        # с подгруженными связями
        # в этом случае, мы подгруживаем таблицы patients и notes
        #
        # Затем мы используем метод filter для фильтрации результатов
        # по ID приёма
        #
        # В конце мы используем метод first, чтобы получить первый
        # результат фильтрации (иначе None, если не найдено)
        
        self.logger.debug(f"get_by_id_with_relations: appointment_id={appointment_id}")
        
        # Получаем приём с подгруженными связями
        return self._session.query(Appointment).options(# Получаем приём с подгруженными связями
            *self._get_joinedload_Appointment(),

            joinedload(Appointment.photos) 
        ).filter( # Фильтруем результаты по ID приёма
            Appointment.id == appointment_id
        ).first()   # Возвращаем первый результат фильтрации (иначе None)

    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_page(
        self, 
        offset: int, 
        limit: int, 
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[List] = None
    ) -> List[Appointment]:
        """
        Возвращает страницу приёмов с подгруженными связями. (пациентом и заметкой)

        :param offset: смещение страницы (начиная с 0)
        :type offset: int
        :param limit: количество записей на странице
        :type limit: int
        :param filters: список словарей с фильтрами для записей
        :type filters: Optional[List[dict[str, Any]]]
        :param order_by: список полей для сортировки записей
        :type order_by: Optional[List]
        :return: список записей на странице
        :rtype: List[Appointment]
        """
        query = self._session.query(Appointment).options(
            # joinedload(Appointment.patient),
            # joinedload(Appointment.note)
            *self._get_joinedload_Appointment()
        )
        if filters:
            sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
            if sql_filters:
                query, _ = apply_filters(query, Appointment, sql_filters)

        if order_by:
            query = query.order_by(*order_by)
            
        return query.offset(offset).limit(limit).all()

    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_page_by_patient(
        self, 
        patient_id: int, 
        offset: int, 
        limit: int,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[List] = None
    ) -> List[Appointment]:
        """
        Возвращает страницу приёмов для указанного пациента с подгруженными связями.
        
        :param patient_id: ID пациента, для которого хотим получить страницу приёмов
        :type patient_id: int
        :param offset: смещение страницы (начиная с 0)
        :type offset: int
        :param limit: количество записей на странице
        :type limit: int
        :param filters: список словарей с фильтрами для записей
        :type filters: Optional[List[dict[str, Any]]]
        :param order_by: список полей для сортировки записей
        :type order_by: Optional[List]
        :return: список записей на странице
        :rtype: List[Appointment]
        """
        base_filters = [{'column': 'patient_id', 'operator': 'eq', 'value': patient_id}]
        if filters:
            all_filters = base_filters + filters
        else:
            all_filters = base_filters
        return self.get_page(offset, limit, filters=all_filters, order_by=order_by)
    
    @AppLogger.get_instance(
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def count_by_patient(
        self, 
        patient_id: int, 
        filters: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        Возвращает количество приёмов конкретного пациента с подгрузкой связей.
        
        :param patient_id: ID пациента
        :type patient_id: int
        :param filters: список словарей с фильтрами для приёмов
        :type filters: Optional[List[Dict[str, Any]]]
        :return: количество приёмов
        :rtype: int
        """
        base_filters = [
            {
                'column': 'patient_id', 
                'operator': 'eq', 
                'value': patient_id
            }
        ]

        if filters:
            all_filters = base_filters + filters
        else:
            all_filters = base_filters

        return self.count(filters=all_filters)

class PhotoRepository(BaseRepository):
    model_class =  Photo

    @AppLogger.get_instance(
        name = 'PhotoRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_by_appointment(self, appointment_id: int) -> List[Photo]:
        
        """
        Возвращает список фотографий приёма с указанным ID.

        :param appointment_id: ID приёма
        :type appointment_id: int
        :return: список фотографий приёма(может быть пустым)
        :rtype: List[Photo]
        """
        self.logger.debug(f"get_by_appointment: appointment_id = {appointment_id}")
        try:
            return self._session.query(Photo).filter_by(appointment_id=appointment_id).all()
        except Exception as e:
            self.logger.exception(f"Ошибка в get_by_appointment: {e}")
            raise   


class PatientRepository(BaseRepository):
    model_class =  Patient
    
        
# 0==0