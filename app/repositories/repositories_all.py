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
        name='BaseRepository',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_all_with_relations(
        self, 
        relations: Optional[List] = None
    ) -> List[ModelType]:
        """Возвращает все записи с подгруженными связями (eager loading)."""
        query = self._session.query(self.model_class)

        if relations:
            query = query.options(*relations)

        return query.all() 
    
    @AppLogger.get_instance(
        name='BaseRepository',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_by_id_with_relations(
        self, 
        entity_id: int, 
        options: Optional[List] = None
    ) -> Optional[ModelType]:
        """
        Возвращает запись по ID с подгруженными связями (eager loading).

        :param entity_id: ID записи.
        :param options: Список опций joinedload (например, [joinedload(Patient.description_note)]).
        :return: Объект модели или None.
        """
        query = self._session.query(self.model_class)

        if options:
            query = query.options(*options)

        rezult = query.filter(self.model_class.id == entity_id).first()

        return rezult
    
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
        order_by: Optional[List] = None,
        relations: Optional[List] = None,
    ) -> List[ModelType]:
        # ВНИМАНИЕ (REPO3, 2026-10-16): приложение этот метод НЕ использует — страницы
        # собирает BaseService.get_page (фильтры по заметкам, fuzzy, sql_compute,
        # сортировка по заметкам). Здесь — простой путь для тестов и скриптов.
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
        query   : Query,                                    # запрос модели
        filters : Optional[Union[List[Any], Dict[str, Any]]],  # список или дерево фильтров
        caller  : str,                                      # имя метода — для журнала
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
            >>> PatientRepository(session)._id_tiebreaker()
            [<sqlalchemy.sql.elements.UnaryExpression object at 0x...>]
        """
        column = getattr(self.model_class, 'id', None)
        return [column.asc()] if column is not None else []

    def _order_clauses(self, order_by: List[Any]) -> List[Any]:
        """
        Сортировка: строки 'поле' / '-поле' → выражения SQLAlchemy; готовые выражения —
        как есть; неизвестное поле — предупреждение и пропуск (REPO3, 2026-10-16).

        Args:
            order_by: Поля или выражения.

        Returns:
            Выражения для ``order_by``.

        Пример:
            >>> repo._order_clauses(['-date', 'id'])
            [<desc date>, <asc id>]
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
        name = 'AppointmentRepository',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_by_patient_with_relations(self, patient_id: int, relations=None) -> List[Appointment]:
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
        query = self._session.query(Appointment).filter_by(patient_id=patient_id)
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
        order_by: Optional[List] = None,
        relations: Optional[List] = None,
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
        return super().get_page(offset, limit, filters=filters, order_by=order_by, relations=relations)

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
        order_by: Optional[List] = None,
        relations: Optional[List] = None,
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
            offset, 
            limit, 
            filters=all_filters, 
            order_by=order_by, 
            relations=relations, 
        )
    
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

        return self.count(filters=all_filters)

    @staticmethod
    def _with_patient_filter(
        patient_id : int,                                       # id пациента
        filters    : Optional[Union[List[Any], Dict[str, Any]]],   # фильтры вызывающего
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