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

Репозиторий только строит запросы в переданной сессии: не открывает и не фиксирует
транзакций (``add`` / ``delete`` без ``flush`` и ``commit``) — это делает вызывающий
(``Database.session_scope``, сервисы). Ошибки базы проходят как есть; нарушение
целостности при фиксации ``session_scope`` превращает в ``DbIntegrityError``.
Устройство и решения — ``app/repositories/IMPLEMENTATION.md``.

Example:
    >>> from app.database import Database
    >>> db = Database("sqlite:///clinic.db")
    >>> with db.session_scope() as session:
    ...     repo = PatientRepository(session)
    ...     patient = repo.get_by_id(1)
    ...     print(patient.first_name)
    Иван
"""

# Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from typing import (
    List, Optional, Any,
    Dict, TypeVar, Generic, Union,
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
from sqlalchemy.orm import Query
from sqlalchemy.orm import joinedload
from sqlalchemy import select

ModelType = TypeVar('ModelType')

class BaseRepository(Generic[ModelType], ABC):
    """
    Базовый репозиторий: общие запросы к одной таблице (модели ``model_class``).

    Наследник задаёт только ``model_class`` (атрибутом класса) и свои особые запросы.
    Методы работают в сессии, переданной в конструктор, и не фиксируют транзакцию.

    Note:
        Страницы приложения собирает ``BaseService.get_page`` (заметки, fuzzy, sql_compute);
        :meth:`get_page` / :meth:`count` здесь — простой путь для тестов и скриптов.

    Example:
        >>> class PatientRepository(BaseRepository):
        ...     model_class = Patient
        >>> PatientRepository(session).count()
        3
    """

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def __init__(
        self,
        session : Session,  # сессия SQLAlchemy, в которой работает репозиторий
    ) -> None: # запоминает сессию, заводит журнал по имени класса
        """
        Создаёт репозиторий поверх сессии и журнал с именем класса (файл ``user``).

        Args:
            session : (Session) Открытая сессия; транзакцией управляет вызывающий.

        Example:
            >>> with db.session_scope() as session:
            ...     repo = PatientRepository(session)
            >>> repo.logger.name
            'PatientRepository'
        """
        self._session = session

        self.logger = AppLogger.get_instance(
            name                    =   self.__class__.__name__,    # журнал по имени класса
            # share_file_with = 'user',
            enable_file_logging     =   'user',                     # файл user
            use_name_in_filename    =   False,                      # 'user',
        )

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_all_with_relations(
        self,
        relations : Optional[List[Any]] = None, # опции загрузки (joinedload / selectinload); None — без них
    ) -> List[ModelType]: # все записи таблицы со связями
        """
        Возвращает все записи таблицы с подгруженными связями (eager loading).

        Порядок строк не задан (без ``ORDER BY``).

        Args:
            relations : (List[Any]/None) Готовые опции загрузки, например
                ``[selectinload(Appointment.photos)]``; None или пусто — без подгрузки.

        Returns:
            (List[ModelType]) Все записи; пустой список — таблица пуста.

        Example:
            >>> repo.get_all_with_relations(
            ...     relations   =   [selectinload(Appointment.photos)],  # фото приёмов
            ... )
            [<Appointment(id=1, patient_id=1, date=2026-01-01)>, <Appointment(id=2, patient_id=1, date=2026-01-02)>]
        """
        query = self._session.query(self.model_class)

        if relations:
            query = query.options(*relations)

        return query.all() 
    
    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_by_id_with_relations(
        self,
        entity_id : int,                        # id записи
        options   : Optional[List[Any]] = None, # опции загрузки; None — без них
    ) -> Optional[ModelType]: # запись по id с готовыми опциями загрузки
        """
        Возвращает запись по ID с подгруженными связями (eager loading).

        Принимает готовые опции загрузки; по именам связей — :meth:`get_with_relations`.

        Args:
            entity_id : (int) ID записи.
            options   : (List[Any]/None) Опции, например
                ``[joinedload(Patient.description_note)]``; None или пусто — без подгрузки.

        Returns:
            (ModelType/None) Запись; None — записи с таким ID нет.

        Example:
            >>> repo.get_by_id_with_relations(
            ...     entity_id   =   1,                                          # id пациента
            ...     options     =   [joinedload(Patient.description_note)],     # заметка
            ... )
            <Patient(id=1, name=Петров Иван)>
        """
        query = self._session.query(self.model_class)

        if options:
            query = query.options(*options)

        rezult = query.filter(self.model_class.id == entity_id).first()

        return rezult
    
    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_with_relations(
        self,
        entity_id : int,                        # id записи
        relations : Optional[List[str]] = None, # имена связей модели; None — без подгрузки
    ) -> Optional[ModelType]: # запись по id со связями, подгруженными по именам
        """
        Возвращает запись по ID, подгружая связи по их именам (``joinedload``).

        В отличие от :meth:`get_by_id_with_relations` принимает имена связей (строки), а не
        готовые опции загрузки. Неизвестное имя (опечатка в ``source_attr`` описания поля)
        не роняет запрос: пропускается с предупреждением в журнал.

        Args:
            entity_id : (int) ID записи.
            relations : (List[str]/None) Имена связей модели, например ``['appointments']``;
                None или пустой список — запись без подгрузки связей.

        Returns:
            (ModelType/None) Запись со связями; None — записи с таким ID нет.

        Example:
            >>> repo = PatientRepository(session)
            >>> patient = repo.get_with_relations(
            ...     entity_id   =   1,                  # id пациента
            ...     relations   =   ['appointments'],   # подгрузить приёмы
            ... )
            >>> len(patient.appointments)
            2
        """
        query = self._session.query(self.model_class)

        # for rel in relations:
        #     self.logger.debug(
        #         f"get_with_relations: "
        #         f"self.model_class {self.model_class}"
        #         f"self.model_class.id {self.model_class.id} "
        #         f"rel {rel} "
        #         f"entity_id {entity_id}"
        #         f"query {query} "
        #     )
        # ↑ до 2026-10-31 (R4): relations=None давал TypeError; строка журнала склеивала
        #   части без пробелов и на каждую связь собирала текст SQL (str(query)).
        self.logger.debug(
            f"get_with_relations: {self.model_class.__name__} id={entity_id}, связи={relations}"
        )
        for rel in relations or []:
            if hasattr(self.model_class, rel):
                query = query.options(
                    joinedload(
                        getattr(self.model_class, rel)
                    )
                )
            else:
                # REPO2 (2026-10-16): раньше неизвестная связь (опечатка в source_attr)
                # молча пропускалась — данные просто не загружались
                self.logger.warning(
                    f"get_with_relations: у {self.model_class.__name__} нет связи '{rel}' — пропущена"
                )
                        
        return query.filter(self.model_class.id == entity_id).first()

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_by_id(
        self,
        entity_id : int,    # id записи
    ) -> Optional[ModelType]: # запись по первичному ключу
        """
        Возвращает запись по ID (``Session.get``: сначала из сессии, иначе запросом).

        Args:
            entity_id : (int) ID записи.

        Returns:
            (ModelType/None) Запись; None — записи с таким ID нет.

        Example:
            >>> PatientRepository(session).get_by_id(1)
            <Patient(id=1, name=Петров Иван)>
        """
        self.logger.debug(f"get_by_id: {entity_id}")
        
        return self._session.get(self.model_class, entity_id)
    
    # def get_all(self) -> List[ModelType]:
    #     self.logger.debug(f"get_all")
    #     return self._session.get(self.model_class).all()
    
    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_all(self) -> List[ModelType]: # все записи таблицы
        """
        Возвращает все записи таблицы ``model_class`` (порядок не задан, связи — лениво).

        Returns:
            (List[ModelType]) Все записи; пустой список — таблица пуста.

        Example:
            >>> PatientRepository(session).get_all()
            [<Patient(id=1, name=Петров Иван)>]
        """
        self.logger.debug("get_all")
        return self._session.query(self.model_class).all()

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def add(
        self,
        entity : ModelType, # новая запись
    ) -> ModelType: # запись, добавленная в сессию
        """
        Добавляет запись в сессию (``Session.add``) и возвращает её же.

        В базу запись попадёт при ``flush`` / ``commit`` вызывающего: до этого ``entity.id``
        ещё ``None``.

        Args:
            entity : (ModelType) Новая запись модели ``model_class``.

        Returns:
            (ModelType) Тот же объект.

        Example:
            >>> patient = repo.add(
            ...     Patient(first_name='Иван', last_name='Петров'),    # новый пациент
            ... )
            >>> session.commit(); patient.id
            1
        """
        # self.logger.debug(f"add: {entity}")
        # ↑ до 2026-10-31 (R6): строка модели (ФИО пациента) попадала в журнал
        self.logger.debug(f"add: {self._log_ref(entity)}")
        self._session.add(entity)
        return entity

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def delete(
        self,
        entity : ModelType, # запись из этой сессии
    ) -> None: # помечает запись на удаление
        """
        Помечает запись на удаление (``Session.delete``); удаляется при ``commit`` вызывающего.

        Связанные записи (заметки, фото, файлы) не трогает: каскады — по модели, файлы —
        сервисы (``file_deletions``).

        Args:
            entity : (ModelType) Запись, загруженная в этой сессии.

        Raises:
            sqlalchemy.orm.exc.UnmappedInstanceError: ``entity`` — не объект модели (например, None).

        Example:
            >>> repo.delete(
            ...     repo.get_by_id(1),  # удаляемый пациент
            ... )
            >>> session.commit(); repo.get_by_id(1) is None
            True
        """
        
        # self.logger.debug(f"delete: {entity}")
        # ↑ до 2026-10-31 (R6): строка модели (ФИО пациента) попадала в журнал
        self.logger.debug(f"delete: {self._log_ref(entity)}")
        self._session.delete(entity)

    @staticmethod
    def _log_ref(
        entity : Any,   # запись модели
    ) -> str: # «Класс id=N» для журнала — без значений полей
        """
        Возвращает ссылку на запись для журнала: имя класса и ``id``, без значений полей.

        Строка модели (``__repr__``) содержит ФИО и тексты — личные данные, в журнал их не
        пишем (как значения запросов в ошибках базы, ``LOG_SQL_PARAMS``).

        Args:
            entity : (Any) Запись модели; ``id`` до ``flush`` — None.

        Returns:
            (str) Например ``'Patient id=1'``.

        Example:
            >>> BaseRepository._log_ref(
            ...     Patient(first_name='Иван'), # новая запись
            ... )
            'Patient id=None'
        """
        return f"{type(entity).__name__} id={getattr(entity, 'id', None)}"

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
    def model_class(self) -> Any: # класс модели таблицы
        """
        Возвращает класс модели SQLAlchemy, с которой работает репозиторий.

        Наследник задаёт его атрибутом класса (``model_class = Patient``) — абстрактное
        свойство не даёт создать репозиторий без модели.

        Returns:
            (Any) Класс модели.

        Raises:
            NotImplementedError: Наследник не задал ``model_class``.

        Example:
            >>> PatientRepository(session).model_class
            <class 'app.database.database_shema.clinic.Patient'>
        """
        raise NotImplementedError("Подклассы должны определить model_class")
    
    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_unique_values(
        self,
        column_name : str,  # имя столбца модели
    ) -> List[Any]: # различные значения столбца по возрастанию
        """
        Возвращает различные значения столбца (``SELECT DISTINCT … ORDER BY``) по возрастанию.

        ``None`` (пустые ячейки) входит в список — в SQLite первым. Неизвестный столбец —
        предупреждение в журнал и пустой список (не ошибка).

        Args:
            column_name : (str) Имя столбца модели, например ``'last_name'``.

        Returns:
            (List[Any]) Значения; пустой список — нет такого столбца или записей.

        Raises:
            NotImplementedError: У репозитория ``model_class = None``.

        Example:
            >>> repo.get_unique_values(
            ...     'last_name',    # столбец
            ... )
            ['Иванов', 'Петров']
        """
        
        self.logger.debug(f"get_unique_values: column_name = {column_name}")
        if self.model_class is None:
            err_ = NotImplementedError("model_class не определён в репозитории")
            # self.logger.exception(err_.message)
            # ↑ до REPO1 (2026-10-16): у NotImplementedError нет .message — вместо понятной
            #   ошибки вылетал AttributeError
            self.logger.error(str(err_))
            raise err_
        try:
            column = getattr(self.model_class, column_name, None)
            if column is None:
                self.logger.warning(f"Столбец '{column_name}' не найден в модели {self.model_class.__name__}")
                return []
            # stmt = select(column).distinct()
            # ↑ до 2026-10-31 (R5): порядок значений не задан — список подсказок мог идти вразнобой
            stmt = select(column).distinct().order_by(column)
            return self._session.execute(stmt).scalars().all()
        except Exception as e:
            self.logger.exception(f"Ошибка в get_unique_values (столбец '{column_name}'): {e}")
            raise  # пробрасываем исключение, чтобы не скрывать проблемы 

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_page(
        self,
        offset    : int,                                                # сколько записей пропустить
        limit     : int,                                                # сколько записей взять
        filters   : Optional[Union[List[Any], Dict[str, Any]]] = None,  # фильтры (список или дерево); None — все
        order_by  : Optional[List[Any]] = None,                         # 'поле' / '-поле' / выражения
        relations : Optional[List[Any]] = None,                         # опции загрузки связей
    ) -> List[ModelType]: # страница записей с SQL-фильтрами и устойчивым порядком
        # ВНИМАНИЕ (REPO3, 2026-10-16): приложение этот метод НЕ использует — страницы
        # собирает BaseService.get_page (фильтры по заметкам, fuzzy, sql_compute,
        # сортировка по заметкам). Здесь — простой путь для тестов и скриптов.
        """
        Возвращает страницу записей: SQL-фильтры, сортировка, ``offset`` / ``limit``.

        Порядок:
            1. фильтры — :meth:`_apply_sql_filters` (список или дерево; ``'fuzzy'``
               пропускается с предупреждением);
            2. сортировка — :meth:`_order_clauses`, последним ключом всегда ``id``
               (:meth:`_id_tiebreaker`) — страницы не повторяют и не теряют записи;
            3. ``OFFSET`` / ``LIMIT``.
        Не проверяет ``offset`` / ``limit``: в SQLite отрицательный ``offset`` — как 0,
        отрицательный ``limit`` — без ограничения.

        Args:
            offset    : (int) Смещение (с 0).
            limit     : (int) Размер страницы; 0 — пустой список.
            filters   : (list/dict/None) Фильтры ``apply_filters``; None или пусто — без отбора.
            order_by  : (List[Any]/None) ``'date'`` — по возрастанию, ``'-date'`` — по убыванию,
                готовые выражения SQLAlchemy — как есть; неизвестное поле — пропуск с
                предупреждением. None — только по ``id``.
            relations : (List[Any]/None) Опции загрузки (``selectinload(...)``); None — без них.

        Returns:
            (List[ModelType]) Записи страницы; пустой список — за пределами данных.

        Raises:
            ValueError: Неизвестный столбец или оператор фильтра (из ``apply_filters``).

        Example:
            >>> repo.get_page(
            ...     offset      =   0,                                                          # первая страница
            ...     limit       =   20,                                                         # 20 записей
            ...     filters     =   [{'column': 'patient_id', 'operator': 'eq', 'value': 1}],   # приёмы пациента
            ...     order_by    =   ['-date'],                                                  # новые сверху
            ... )
            [<Appointment(id=2, patient_id=1, date=2026-01-02)>, <Appointment(id=1, patient_id=1, date=2026-01-01)>]
        """
        
        query = self._session.query(self.model_class)
        if relations:
            query = query.options(*relations)

        # if filters:
        #     # Отфильтровываем fuzzy-операторы, они не поддерживаются на уровне SQL
        #     sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
        #     if sql_filters:
        #         query, _ = apply_filters(query, self.model_class, sql_filters)
        # ↑ до 2026-10-31 (R1, R2): дерево фильтров ({'and'/'or': …}) роняло запрос
        #   (AttributeError), а отброшенный 'fuzzy' молча расширял страницу.
        query = self._apply_sql_filters(
            query,          # запрос модели
            filters,        # фильтры (список или дерево)
            'get_page',     # кто вызвал — для журнала
        )
        # if order_by:
        #     # query = query.order_by(*order_by)
        #     # ↑ до REPO3 (2026-10-16): строки передавались как есть — '-date' (по убыванию,
        #     #   как в BaseService) давал ошибку SQL. Теперь — как в BaseService.
        #     query = query.order_by(*self._order_clauses(order_by))
        # ↑ до 2026-10-31 (R3): без order_by порядок строк не задан, при равных ключах —
        #   тоже: соседние страницы могли повторять и терять записи. Теперь id — последний ключ.
        query = query.order_by(
            *self._order_clauses(order_by or []),
            *self._id_tiebreaker(),
        )
        return query.offset(offset).limit(limit).all()

    def _apply_sql_filters(
        self,
        query   : Query,                                        # запрос модели
        filters : Optional[Union[List[Any], Dict[str, Any]]],   # список или дерево фильтров
        caller  : str,                                          # имя метода — для журнала
    ) -> Query: # запрос с SQL-частью фильтров
        """
        Применяет SQL-часть фильтров; нечёткий отбор (``'fuzzy'``) пропускает с предупреждением.

        Фильтры — в любом формате ``apply_filters``: плоский список листьев
        ``{'column', 'operator', 'value'}`` (через «И») или дерево узлов ``{'and': […]}`` /
        ``{'or': […]}``. Узлы ``'fuzzy'`` в SQL дают «истину», а сам нечёткий отбор
        (``apply_post_filters`` по готовому списку) здесь НЕ делается: он сломал бы
        ``offset`` / ``limit`` и ``count``. Нужен нечёткий поиск — ``BaseService.get_page``.

        Args:
            query   : (Query) Запрос по ``model_class``.
            filters : (list/dict/None) Фильтры; None или пусто — запрос без изменений.
            caller  : (str) Имя вызывающего метода — в текст предупреждения.

        Returns:
            (Query) Запрос с условиями SQL.

        Raises:
            ValueError: Неизвестный столбец или оператор, ``'fuzzy'`` внутри ``'or'``
                (из ``apply_filters``).

        Example:
            >>> query = repo._apply_sql_filters(
            ...     session.query(Patient),                                         # запрос
            ...     {'or': [{'column': 'last_name', 'operator': 'eq', 'value': 'А'},
            ...             {'column': 'last_name', 'operator': 'eq', 'value': 'Б'}]}, # дерево
            ...     'count',                                                        # для журнала
            ... )
            >>> query.count()
            2
        """
        if not filters:
            return query
        query, post_filters = apply_filters(
            query,              # запрос
            self.model_class,   # модель
            filters,            # фильтры как есть
        )
        if post_filters: # 'fuzzy' в репозитории не применяется
            self.logger.warning(
                f"{caller}: нечёткий отбор (fuzzy) в репозитории не выполняется — пропущен: "
                f"{[column for column, _value, _threshold in post_filters]}"
            )
        return query

    def _id_tiebreaker(self) -> List[Any]: # последний ключ сортировки страниц
        """
        Возвращает ``[model_class.id.asc()]`` — последний ключ сортировки страниц.

        Без него порядок строк в SQL не задан (нет ``order_by`` или ключи равны), и соседние
        страницы ``offset`` / ``limit`` могут повторять одни записи и терять другие. У модели
        без столбца ``id`` — пустой список (сортировка как задана).

        Returns:
            (List[Any]) Выражения для ``order_by``: одно или ни одного.

        Example:
            >>> [str(c) for c in PatientRepository(session)._id_tiebreaker()]
            ['patients.id ASC']
        """
        column = getattr(self.model_class, 'id', None)
        return [column.asc()] if column is not None else []

    def _order_clauses(
        self,
        order_by : List[Any],   # 'поле' / '-поле' / готовые выражения
    ) -> List[Any]: # выражения SQLAlchemy для order_by
        """
        Переводит сортировку в выражения: ``'поле'`` / ``'-поле'`` → ``asc()`` / ``desc()``.

        Готовые выражения SQLAlchemy — как есть; неизвестное поле — предупреждение в журнал
        и пропуск (REPO3, 2026-10-16). Сортирует только по столбцам модели (заметки,
        ``sql_compute`` — ``BaseService``).

        Args:
            order_by : (List[Any]) Поля или выражения; пустой список — пустой результат.

        Returns:
            (List[Any]) Выражения для ``Query.order_by``.

        Example:
            >>> [str(c) for c in repo._order_clauses(
            ...     ['-date', 'id'],    # дата по убыванию, затем id
            ... )]
            ['appointments.date DESC', 'appointments.id ASC']
        """
        clauses = []
        for spec in order_by:
            if not isinstance(spec, str):
                clauses.append(spec)
                continue
            name = spec[1:] if spec.startswith('-') else spec
            column = getattr(self.model_class, name, None)
            if column is None:
                self.logger.warning(f"Сортировка: у {self.model_class.__name__} нет поля '{name}' — пропущено")
                continue
            clauses.append(column.desc() if spec.startswith('-') else column.asc())
        return clauses

    @AppLogger.get_instance(
        name                    =   'BaseRepository',           # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def count(
        self,
        filters : Optional[Union[List[Any], Dict[str, Any]]] = None,   # фильтры (список или дерево); None — все
    ) -> int: # число записей с SQL-фильтрами
        """
        Возвращает число записей с учётом SQL-фильтров (как у :meth:`get_page`).

        ``'fuzzy'`` не применяется — пропуск с предупреждением (:meth:`_apply_sql_filters`).

        Args:
            filters : (list/dict/None) Фильтры ``apply_filters``; None или пусто — все записи.

        Returns:
            (int) Число записей.

        Raises:
            ValueError: Неизвестный столбец или оператор фильтра (из ``apply_filters``).

        Example:
            >>> repo.count(
            ...     filters =   {'or': [{'column': 'last_name', 'operator': 'eq', 'value': 'Петров'},
            ...                         {'column': 'last_name', 'operator': 'eq', 'value': 'Иванов'}]},  # дерево
            ... )
            2
        """
        query = self._session.query(self.model_class)
        # if filters:
        #     sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
        #     if sql_filters:
        #         query, _ = apply_filters(query, self.model_class, sql_filters)
        # ↑ до 2026-10-31 (R1, R2): как в get_page — дерево фильтров роняло запрос,
        #   'fuzzy' молча пропускался.
        query = self._apply_sql_filters(
            query,      # запрос модели
            filters,    # фильтры (список или дерево)
            'count',    # кто вызвал — для журнала
        )
        return query.count()



class AppointmentNoteRepository(BaseRepository):
    """
    Репозиторий заметок (``AppointmentNote``): общие запросы и поиск по точному тексту.

    Example:
        >>> AppointmentNoteRepository(session).get_by_text_exact('Первичный осмотр')
        <Note(id=1, text_preview=Первичный осмотр)>
    """

    model_class =  AppointmentNote
    
    @AppLogger.get_instance(
        name                    =   'AppointmentNoteRepository',# журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_by_text_exact(
        self,
        text : str, # искомый текст заметки
    ) -> Optional[AppointmentNote]: # заметка с точно таким текстом
        """
        Возвращает первую заметку с точно таким текстом (с учётом регистра и пробелов).

        Сервисы так переиспользуют одинаковые заметки вместо создания копий. Текст в журнал
        не пишется (личные данные) — только его длина.

        Args:
            text : (str) Текст заметки целиком.

        Returns:
            (AppointmentNote/None) Заметка; None — такой нет.

        Example:
            >>> AppointmentNoteRepository(session).get_by_text_exact(
            ...     'Тестовая заметка', # текст
            ... )
            <Note(id=1, text_preview=Тестовая заметка)>
        """

        # self.logger.debug(f"get_by_text_exact: text = {text}")
        # ↑ до 2026-10-31 (R6): текст заметки (личные данные) попадал в журнал
        self.logger.debug(
            f"get_by_text_exact: текст из {len(text) if text is not None else 0} символов"
        )
        return self._session.query(AppointmentNote).filter(AppointmentNote.text == text).first()

class AppointmentRepository(BaseRepository):
    """
    Репозиторий приёмов (``Appointment``): общие запросы и выборки по пациенту.

    Example:
        >>> AppointmentRepository(session).count_by_patient(1)
        2
    """

    model_class =  Appointment

    # @AppLogger.get_instance(
    #     name = 'AppointmentRepository',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def get_all_with_note(self):
    #     """
    #     Возвращает все приёмы с подгруженной заметкой.

    #     :return: список приёмов
    #     :rtype: List[Appointment]
    #     """
    #     self.logger.debug(f"get_all_with_note")
    #     return self._session.query(Appointment).options(joinedload(Appointment.note)).all()

    # @AppLogger.get_instance(
    #     name = 'AppointmentRepository',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _get_joinedload_Appointment(self):
    #     return [
    #         joinedload(Appointment.patient),
    #         joinedload(Appointment.reason_note),
    #         joinedload(Appointment.procedure_note),
    #         joinedload(Appointment.recommendations_note),
    #         joinedload(Appointment.note),
    #         joinedload(Appointment.cost_procedure_note),
    #         # joinedload(Appointment.photos)   # если нужно, можно оставить
    #     ]

    # @AppLogger.get_instance(
    #     name = 'AppointmentRepository',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # # def get_all_with_relations(self) -> List[Appointment]:
    # #     """
    # #     Возвращает все приёмы с подгруженными пациентом и заметкой.

    # #     :return: список приёмов
    # #     :rtype: List[Appointment]
    # #     """
    #     # self.logger.debug("get_all_with_relations")

    #     # return self._session.query(Appointment).options(
    #     #     # joinedload(Appointment.patient),
    #     #     # joinedload(Appointment.note)
    #     #     *self._get_joinedload_Appointment()
    #     # ).all()
    # def get_all_with_relations(self, relations: Optional[List] = None):
    #     query = self._session.query(Appointment)
    #     if relations:
    #         query = query.options(*relations)
            
    #     return query.all()
    
    @AppLogger.get_instance(
        name                    =   'AppointmentRepository',    # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_by_patient_with_relations(
        self,
        patient_id : int,                        # id пациента
        relations  : Optional[List[Any]] = None, # опции загрузки связей; None — без них
    ) -> List[Appointment]: # все приёмы пациента
        """
        Возвращает все приёмы пациента; связи — по переданным опциям загрузки.

        Порядок не задан (без ``ORDER BY``); страницами — :meth:`get_page_by_patient`.

        Args:
            patient_id : (int) ID пациента.
            relations  : (List[Any]/None) Опции загрузки, например
                ``[selectinload(Appointment.photos)]``; None или пусто — без подгрузки.

        Returns:
            (List[Appointment]) Приёмы; пустой список — приёмов нет (или нет пациента).

        Example:
            >>> AppointmentRepository(session).get_by_patient_with_relations(
            ...     patient_id  =   1,                                  # пациент
            ...     relations   =   [selectinload(Appointment.photos)], # с фото
            ... )
            [<Appointment(id=1, patient_id=1, date=2026-01-01)>]
        """
        self.logger.debug(
            f"get_by_patient_with_relations: "
            f"patient_id={patient_id}"
        )
        query = self._session.query(Appointment).filter_by(
            patient_id  =   patient_id,     # приёмы пациента
        )
        if relations:
            query = query.options(
                # joinedload(Appointment.patient),
                # joinedload(Appointment.note),
                # # joinedload(Appointment.photos),
                *relations
            )
        
        return query.all()

    # @AppLogger.get_instance(
    #     name = 'AppointmentRepository',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def get_by_id_with_relations(self, appointment_id: int, relations: Optional[List] = None):
    #     query = self._session.query(Appointment)

    #     if relations:
    #         query = query.options(*relations)

    #     return query.filter(Appointment.id == appointment_id).first()
    
    # def get_by_id_with_relations(self, appointment_id: int) -> Optional[Appointment]:
    #     """
    #     Возвращает приём по ID с подгруженными связями (пациентом и заметкой).

    #     :param appointment_id: ID приёма
    #     :type appointment_id: int
    #     :return: приём или None, если не найдено
    #     :rtype: Optional[Appointment]
    #     """
    #     # Получаем приём с подгруженными связями (пациентом и заметкой)
    #     # с помощью метода joinedload, который подгруживает связанные таблицы
    #     # для получения полного объекта приёма с подгруженными связями
    #     # мы используем метод options с параметром joinedload
    #     #
    #     # В методе joinedload мы указываем связанные таблицы, которые
    #     # необходимо подгружить для получения полного объекта приёма
    #     # с подгруженными связями
    #     # в этом случае, мы подгруживаем таблицы patients и notes
    #     #
    #     # Затем мы используем метод filter для фильтрации результатов
    #     # по ID приёма
    #     #
    #     # В конце мы используем метод first, чтобы получить первый
    #     # результат фильтрации (иначе None, если не найдено)
        
    #     self.logger.debug(f"get_by_id_with_relations: appointment_id={appointment_id}")
        
    #     # Получаем приём с подгруженными связями
    #     return self._session.query(Appointment).options(# Получаем приём с подгруженными связями
    #         *self._get_joinedload_Appointment(),

    #         joinedload(Appointment.photos) 
    #     ).filter( # Фильтруем результаты по ID приёма
    #         Appointment.id == appointment_id
    #     ).first()   # Возвращаем первый результат фильтрации (иначе None)

    @AppLogger.get_instance(
        name                    =   'AppointmentRepository',    # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_page(
        self,
        offset    : int,                                                # сколько записей пропустить
        limit     : int,                                                # сколько записей взять
        filters   : Optional[Union[List[Any], Dict[str, Any]]] = None,  # фильтры (список или дерево); None — все
        order_by  : Optional[List[Any]] = None,                         # 'поле' / '-поле' / выражения
        relations : Optional[List[Any]] = None,                         # опции загрузки связей
    ) -> List[Appointment]: # страница приёмов (как BaseRepository.get_page)
        """
        Возвращает страницу приёмов — то же, что :meth:`BaseRepository.get_page`.

        Связи подгружаются только переданные в ``relations`` (сам метод ничего не добавляет).

        Args:
            offset    : (int) Смещение (с 0).
            limit     : (int) Размер страницы.
            filters   : (list/dict/None) Фильтры ``apply_filters``; None или пусто — без отбора.
            order_by  : (List[Any]/None) ``'date'`` / ``'-date'`` / выражения; последним ключом — ``id``.
            relations : (List[Any]/None) Опции загрузки; None — без них.

        Returns:
            (List[Appointment]) Приёмы страницы.

        Raises:
            ValueError: Неизвестный столбец или оператор фильтра (из ``apply_filters``).

        Example:
            >>> AppointmentRepository(session).get_page(
            ...     offset      =   0,          # первая страница
            ...     limit       =   10,         # 10 приёмов
            ...     order_by    =   ['-date'],  # новые сверху
            ... )
            [<Appointment(id=2, patient_id=1, date=2026-01-02)>, <Appointment(id=1, patient_id=1, date=2026-01-01)>]
        """
        # query = self._session.query(Appointment).options(
        #     # joinedload(Appointment.patient),
        #     # joinedload(Appointment.note)
        #     *self._get_joinedload_Appointment()
        # )
        # query = self._session.query(Appointment)
        #
        # if relations:
        #     query = query.options(*relations)
        #
        # if filters:
        #     sql_filters = [f for f in filters if f.get('operator') != 'fuzzy']
        #     if sql_filters:
        #         query, _ = apply_filters(query, Appointment, sql_filters)
        #
        # if order_by:
        #     query = query.order_by(*order_by)
        #
        # return query.offset(offset).limit(limit).all()
        # ↑ до REPO3 (2026-10-16): точная копия BaseRepository.get_page (с Appointment вместо
        #   model_class). Теперь — базовый метод.
        return super().get_page(
            offset,                     # смещение
            limit,                      # размер страницы
            filters     =   filters,    # фильтры
            order_by    =   order_by,   # сортировка
            relations   =   relations,  # опции загрузки
        )

    @AppLogger.get_instance(
        name                    =   'AppointmentRepository',    # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_page_by_patient(
        self,
        patient_id : int,                                                # id пациента
        offset     : int,                                                # сколько записей пропустить
        limit      : int,                                                # сколько записей взять
        filters    : Optional[Union[List[Any], Dict[str, Any]]] = None,  # доп. фильтры (список или дерево)
        order_by   : Optional[List[Any]] = None,                         # 'поле' / '-поле' / выражения
        relations  : Optional[List[Any]] = None,                         # опции загрузки связей
    ) -> List[Appointment]: # страница приёмов одного пациента
        """
        Возвращает страницу приёмов пациента: условие ``patient_id`` «И» фильтры вызывающего.

        Условие по пациенту добавляет :meth:`_with_patient_filter`; дальше — :meth:`get_page`.

        Args:
            patient_id : (int) ID пациента.
            offset     : (int) Смещение (с 0).
            limit      : (int) Размер страницы.
            filters    : (list/dict/None) Дополнительные фильтры; None — только пациент.
            order_by   : (List[Any]/None) Сортировка; последним ключом — ``id``.
            relations  : (List[Any]/None) Опции загрузки; None — без них.

        Returns:
            (List[Appointment]) Приёмы пациента на странице.

        Raises:
            ValueError: Неизвестный столбец или оператор фильтра (из ``apply_filters``).

        Example:
            >>> AppointmentRepository(session).get_page_by_patient(
            ...     patient_id  =   1,          # пациент
            ...     offset      =   0,          # первая страница
            ...     limit       =   2,          # 2 приёма
            ...     order_by    =   ['date'],   # старые сверху
            ... )
            [<Appointment(id=1, patient_id=1, date=2026-01-01)>, <Appointment(id=2, patient_id=1, date=2026-01-02)>]
        """
        # base_filters = [
        #     {
        #         'column': 'patient_id',
        #         'operator': 'eq',
        #         'value': patient_id
        #     }
        # ]
        #
        # if filters:
        #     all_filters = base_filters + filters
        # else:
        #     all_filters = base_filters
        # ↑ до 2026-10-31 (R1): дерево фильтров ({'and'/'or': …}) давало TypeError (list + dict)
        all_filters = self._with_patient_filter(
            patient_id,     # пациент
            filters,        # фильтры вызывающего
        )

        return self.get_page(
            offset,                         # смещение
            limit,                          # размер страницы
            filters     =   all_filters,    # пациент + фильтры вызывающего
            order_by    =   order_by,       # сортировка
            relations   =   relations,      # опции загрузки
        )
    
    @AppLogger.get_instance(
        name                    =   'AppointmentRepository',    # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def count_by_patient(
        self,
        patient_id : int,                                                # id пациента
        filters    : Optional[Union[List[Any], Dict[str, Any]]] = None,  # доп. фильтры (список или дерево)
    ) -> int: # число приёмов пациента с фильтрами
        """
        Возвращает число приёмов пациента с учётом дополнительных фильтров.

        Пара к :meth:`get_page_by_patient` (те же фильтры — тот же отбор); связи не грузит.

        Args:
            patient_id : (int) ID пациента.
            filters    : (list/dict/None) Дополнительные фильтры; None — все приёмы пациента.

        Returns:
            (int) Число приёмов.

        Raises:
            ValueError: Неизвестный столбец или оператор фильтра (из ``apply_filters``).

        Example:
            >>> AppointmentRepository(session).count_by_patient(
            ...     patient_id  =   1,                                                                  # пациент
            ...     filters     =   [{'column': 'date', 'operator': 'ge', 'value': date(2026, 1, 2)}], # с 2 января
            ... )
            1
        """
        # base_filters = [
        #     {
        #         'column': 'patient_id',
        #         'operator': 'eq',
        #         'value': patient_id
        #     }
        # ]
        #
        # if filters:
        #     all_filters = base_filters + filters
        # else:
        #     all_filters = base_filters
        # ↑ до 2026-10-31 (R1): дерево фильтров ({'and'/'or': …}) давало TypeError (list + dict)
        all_filters = self._with_patient_filter(
            patient_id,     # пациент
            filters,        # фильтры вызывающего
        )

        return self.count(
            filters =   all_filters,    # пациент + фильтры вызывающего
        )

    @staticmethod
    def _with_patient_filter(
        patient_id : int,                                           # id пациента
        filters    : Optional[Union[List[Any], Dict[str, Any]]],    # фильтры вызывающего
    ) -> List[Any]: # фильтры «приёмы пациента» + фильтры вызывающего (через «И»)
        """
        Добавляет к фильтрам условие ``patient_id == patient_id`` (через «И»).

        Плоский список дополняется листом; дерево (``{'and'/'or': …}``) становится одним
        узлом списка — ``apply_filters`` объединит его с условием по пациенту через «И».

        Args:
            patient_id : (int) ID пациента.
            filters    : (list/dict/None) Фильтры вызывающего; None или пусто — только пациент.

        Returns:
            (List[Any]) Фильтры для ``get_page`` / ``count``.

        Example:
            >>> AppointmentRepository._with_patient_filter(
            ...     7,                                          # пациент
            ...     {'or': [{'column': 'date', 'operator': 'is_null'}]},  # дерево
            ... )
            [{'column': 'patient_id', 'operator': 'eq', 'value': 7}, {'or': [{'column': 'date', 'operator': 'is_null'}]}]
        """
        base_filters = [
            {
                'column'    : 'patient_id',  # столбец
                'operator'  : 'eq',          # равно
                'value'     : patient_id,    # пациент
            }
        ]
        if not filters:
            return base_filters
        if isinstance(filters, dict): # дерево — одним узлом
            return base_filters + [filters]
        return base_filters + list(filters)

class PhotoRepository(BaseRepository):
    """
    Репозиторий фото приёмов (``Photo``): общие запросы и фото одного приёма.

    Example:
        >>> PhotoRepository(session).get_by_appointment(1)
        [<Photo(id=1, appointment_id=1, file=app1/test.jpg)>]
    """
    model_class =  Photo

    @AppLogger.get_instance(
        name                    =   'PhotoRepository',          # журнал замеров времени
        # share_file_with = 'system',
        enable_file_logging     =   'system',                   # файл system
        use_name_in_filename    =   False,                      # 'system',
    ).log_execution_time(
        level   =   AppLogger._parse_log_level(
            'DEBUG',    # уровень замера
        ),
    )
    def get_by_appointment(
        self,
        appointment_id : int,   # id приёма
    ) -> List[Photo]: # все фото приёма
        """
        Возвращает все фото приёма (порядок не задан); ошибка запроса — в журнал и дальше.

        Args:
            appointment_id : (int) ID приёма.

        Returns:
            (List[Photo]) Фото; пустой список — у приёма фото нет.

        Raises:
            Exception: Ошибка запроса (``sqlalchemy.exc``) — после записи в журнал.

        Example:
            >>> PhotoRepository(session).get_by_appointment(
            ...     1,  # id приёма
            ... )
            [<Photo(id=1, appointment_id=1, file=app1/test.jpg)>, <Photo(id=2, appointment_id=1, file=another.jpg)>]
        """
        self.logger.debug(f"get_by_appointment: appointment_id = {appointment_id}")
        try:
            return self._session.query(Photo).filter_by(
                appointment_id  =   appointment_id,     # фото приёма
            ).all()
        except Exception as e:
            self.logger.exception(f"Ошибка в get_by_appointment: {e}")
            raise   


class PatientRepository(BaseRepository):
    """
    Репозиторий пациентов (``Patient``): только общие запросы :class:`BaseRepository`.

    Example:
        >>> PatientRepository(session).get_with_relations(1, ['appointments'])
        <Patient(id=1, name=Петров Иван)>
    """
    model_class =  Patient

    # @AppLogger.get_instance(
    #     name = 'PatientRepository',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def get_all_with_relations(self, relations: Optional[List] = None):
    #     query = self._session.query(Patient)
    #     if relations:
    #         query = query.options(*relations)
    #     return query.all()
    
        
# 0==0