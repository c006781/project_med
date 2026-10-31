# app/draft/integration.py

"""
Связка переносимого пакета черновиков (``app.utils.drafts``) с приложением.

Здесь — всё, что знает о приложении (пакет черновиков не знает):
    * ``build_app_schema()`` — дерево таблиц приложения (пациент → приём → фото) и общие
      данные (заметки) — из описаний таблиц ``app.tables``;
    * ``ServiceAdapter`` — сохранение через сервисы приложения в ОДНОЙ сессии SQLAlchemy
      (одна транзакция на все таблицы — D2, app/draft/IMPLEMENTATION.md);
    * ``make_parent_resolver()`` — определитель родителя записи без черновика через сервис;
    * ``save_with_confirmation()`` — сохранение с вопросами пользователю (новые родители,
      удаляемые ветки); живёт в ``app/utils/drafts/workflow.py``, здесь — для совместимости;
    * ``AppDrafts``, ``create_app_drafts()`` — черновики главного окна: одно хранилище на
      приложение, транзакция — из общей базы ``app.dependencies.get_db()`` (ТД-6).

Черновики данные БД сами не удаляют — только хранят правки до коммита (В-18, В-19).

Example:
    >>> drafts = create_app_drafts()
    >>> drafts.adapter.entities()
    ['patient', 'appointment', 'photo', 'note']
    >>> drafts.store.is_empty
    True
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING, Any, Callable, ContextManager, Dict, Hashable, Iterable, List, Mapping, Optional,
    Tuple, Type,
)

from app.exceptions import EntityNotFoundError
from app.utils.drafts import NodeKey, TreeSchema
# from app.utils.drafts import EntityType, NodeKey, TreeSchema
# ↑ до 2026-10-31 (М16, DB1): EntityType — только в закомментированном ручном дереве

if TYPE_CHECKING:
    from app.utils.drafts import DeletePolicy, DraftStore, SaveResult, SaveScope
    # from app.utils.drafts import (
    #     DeletePolicy, DraftStore, PersistenceAdapter, SavePlan, SaveResult, SaveScope,
    # )
    # ↑ до 2026-10-31 (М16, DB1): PersistenceAdapter, SavePlan не используются

_log = logging.getLogger(__name__)

# Тип записи -> (функция, возвращающая сервис; класс DTO)
ServiceSpec = Tuple[Callable[[], Any], Type[Any]]


def build_app_schema() -> TreeSchema: # дерево таблиц приложения для черновиков
    """
    Возвращает схему черновиков приложения — из описаний таблиц (``app.tables.CLINIC``).

    Дерево: пациент → приём → фото (родитель — из внешнего ключа модели). Заметки
    (``appointments_notes``) — не узел дерева, а корневой тип ``note`` общих данных реестра
    таблиц (2026-10-31, Ф1.3.4): цель ссылок ``*_id`` пациента и приёма, удалить
    используемую заметку нельзя (``restrict``). Сами тексты заметок по-прежнему сохраняют
    сервисы пациента и приёма вместе с записью (виртуальные поля ``is_note``).

    Note:
        ``app.tables`` импортируется внутри функции: он сам импортирует этот модуль.

    Returns:
        (TreeSchema) Схема: пациент → приём → фото и корневой ``note``.

    Example:
        >>> schema = build_app_schema()
        >>> schema.depth('photo')
        2
        >>> schema.parent_field('appointment')
        'patient_id'
    """
    # return TreeSchema([
    #     EntityType('patient', label='Пациент'),
    #     EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём'),
    #     EntityType('photo', parent='appointment', parent_field='appointment_id', label='Фото'),
    # ])
    # ↑ до 2026-10-18: дерево перечислялось вручную — новая таблица требовала правки здесь.
    #   Теперь — из описаний таблиц (app/tables, одно описание на таблицу; родитель — из
    #   внешнего ключа модели). Схема совпадает с прежней (тест).
    from app.tables import CLINIC         # здесь, а не наверху: app.tables импортирует этот модуль
    return CLINIC.drafts_schema()


class ServiceAdapter:
    """
    Запись черновиков через сервисы приложения (``PersistenceAdapter`` пакета черновиков).

    * ``transaction()`` — одна сессия SQLAlchemy на всё сохранение: из
      ``transaction_factory`` (приложение передаёт ``get_db().session_scope``), без неё —
      закрытый ``_session_scope`` первого сервиса (запасной путь, как до 2026-10-16).
      Коммит при выходе без ошибки, откат при исключении; ЭТА ЖЕ сессия передаётся всем
      сервисам.
    * ``create`` — DTO из данных черновика (без временного ``id``) → ``service.create``;
      id появляется сразу (сервис делает ``flush``) — дети ссылаются на него в той же
      транзакции.
    * ``update`` — текущий DTO из БД + изменения → ``service.update`` (сервисы
      принимают DTO целиком; виртуальные поля-заметки обрабатывает сервис).
    * ``delete`` — ``service.delete`` (потомков в БД удаляет сервис / каскад БД).
    * ``read``, ``referrers`` — чтение для ``find_conflicts`` и правила ``restrict``
      (кто ссылается на удаляемую запись) — внутри транзакции сохранения.

    Сервисы берутся функциями при КАЖДОЙ операции: после смены пути к БД
    (``reload_config``) адаптер работает с актуальными.

    Note:
        Набор типов приложения собирает ``app.tables.CLINIC.service_adapter()`` (дерево и
        общие данные — ``note``); имя, параметры и поведение класса читают тесты
        ``tests/test_dataset_app`` и главное окно — не менять без них.

    Example:
        >>> adapter = ServiceAdapter(
        ...     specs   =   {'patient': (get_patient_service, PatientDTO)},    # тип → (сервис, DTO)
        ... )
        >>> adapter.entities()
        ['patient']
    """

    def __init__(
        self,
        specs               : Mapping[str, ServiceSpec],                            # тип записи → (поставщик сервиса, класс DTO)
        transaction_factory : Optional[Callable[[], ContextManager[Any]]] = None,   # откуда брать транзакцию; None — сервис
    ) -> None: # набор сервисов и источник транзакции
        """
        Запоминает сервисы по типам записей и источник транзакции.

        Args:
            specs               : (Mapping[str, ServiceSpec]) Тип записи → (функция-поставщик
                сервиса, класс DTO).
            transaction_factory : (Callable/None) Откуда брать транзакцию (контекстный
                менеджер, отдающий сессию: коммит при выходе, откат при ошибке), например
                ``lambda: get_db().session_scope()``; None — ``_session_scope`` первого
                сервиса (так было до 2026-10-16; это закрытый метод сервисов, и адаптер был
                завязан на их внутреннее устройство).

        Raises:
            ValueError: Пустой набор — ``ServiceAdapter: не задано ни одного сервиса``.

        Example:
            >>> ServiceAdapter(
            ...     specs                 =   {'photo': (get_photo_service, PhotoDTO)},  # сервис фото
            ...     transaction_factory   =   lambda: get_db().session_scope(),          # общая база
            ... )
        """
        if not specs:
            raise ValueError("ServiceAdapter: не задано ни одного сервиса")
        self._specs: Dict[str, ServiceSpec] = dict(specs)
        self._transaction_factory = transaction_factory

    def entities(self) -> List[str]: # подключённые типы записей
        """
        Возвращает типы записей, которые умеет сохранять адаптер, — в порядке ``specs``.

        Returns:
            (List[str]) Имена типов.

        Example:
            >>> adapter.entities()
            ['patient', 'appointment', 'photo', 'note']
        """
        return list(self._specs)

    def service(
        self,
        entity : str,   # тип записи
    ) -> Any: # сервис типа записи (поставщик вызывается каждый раз)
        """
        Возвращает сервис типа записи — вызовом поставщика (актуальный после смены БД).

        Args:
            entity : (str) Тип записи.

        Returns:
            (Any) Сервис приложения.

        Raises:
            KeyError: Тип не подключён — ``ServiceAdapter: нет сервиса для '<тип>'``.

        Example:
            >>> adapter.service('photo')
            <app.services.services_all.PhotoService object at ...>
        """
        try:
            provider, _ = self._specs[entity]
        except KeyError:
            raise KeyError(f"ServiceAdapter: нет сервиса для '{entity}'") from None
        return provider()

    def dto_class(
        self,
        entity : str,   # тип записи
    ) -> Type[Any]: # класс DTO типа записи
        """
        Возвращает класс DTO типа записи.

        Args:
            entity : (str) Тип записи.

        Returns:
            (Type[Any]) Класс DTO.

        Raises:
            KeyError: Тип не подключён.

        Example:
            >>> adapter.dto_class('photo').__name__
            'PhotoDTO'
        """
        return self._specs[entity][1]

    def transaction(self) -> ContextManager[Any]: # одна сессия на всё сохранение
        """
        Открывает одну сессию SQLAlchemy на всё сохранение.

        Источник — ``transaction_factory``; без неё — ``_session_scope(None)`` первого
        сервиса (запасной путь).

        Returns:
            (ContextManager[Any]) Контекстный менеджер, отдающий сессию: коммит при выходе,
                откат при исключении.

        Example:
            >>> with adapter.transaction() as session:
            ...     adapter.delete('photo', 301, session)
        """
        if self._transaction_factory is not None:
            return self._transaction_factory()
        # Запасной путь (как до 2026-10-16): закрытый метод сервиса
        first = next(iter(self._specs))
        return self.service(first)._session_scope(None)

    def create(
        self,
        entity : str,               # тип записи
        data   : Mapping[str, Any], # поля из черновика (внешний ключ уже настоящий)
        tx     : Any,               # сессия транзакции
    ) -> Hashable: # создание записи через сервис
        """
        Создаёт запись через сервис: DTO из полей черновика без временного ``id``.

        Args:
            entity : (str) Тип записи.
            data   : (Mapping[str, Any]) Поля из черновика; внешний ключ уже настоящий
                (исполнитель заменил временный id родителя).
            tx     : (Any) Сессия транзакции.

        Returns:
            (Hashable) Id созданной записи.

        Example:
            >>> adapter.create(
            ...     'photo',                                                    # тип
            ...     {'appointment_id': 55, 'file_path': '/tmp/a.jpg'},          # поля
            ...     session,                                                    # транзакция
            ... )
            301
        """
        values = {k: v for k, v in data.items() if k != 'id'}
        dto = self.dto_class(entity)(**values)
        created = self.service(entity).create(dto, session=tx)
        return getattr(created, 'id', None)

    def update(
        self,
        entity    : str,                # тип записи
        entity_id : Hashable,           # id записи
        changes   : Mapping[str, Any],  # изменённые поля
        tx        : Any,                # сессия транзакции
    ) -> None: # изменение записи: текущий DTO + изменения
        """
        Изменяет запись: текущий DTO из БД + изменённые поля → ``service.update``.

        Args:
            entity    : (str) Тип записи.
            entity_id : (Hashable) Id записи.
            changes   : (Mapping[str, Any]) Изменённые поля (``id`` не меняется).
            tx        : (Any) Сессия транзакции.

        Raises:
            EntityNotFoundError: Записи нет (исключение сервиса, например
                ``AppointmentNotFoundError``).

        Example:
            >>> adapter.update(
            ...     'appointment',      # тип
            ...     12,                 # id
            ...     {'cost': 500},      # изменения
            ...     session,            # транзакция
            ... )
        """
        service = self.service(entity)
        current = service.get_by_id(entity_id, session=tx)
        dto = current.model_copy(update={k: v for k, v in changes.items() if k != 'id'})
        service.update(dto, session=tx)

    def read(
        self,
        entity    : str,        # тип записи
        entity_id : Hashable,   # id записи
        tx        : Any = None, # сессия транзакции; None — своя
    ) -> Optional[Dict[str, Any]]: # поля записи из БД или None
        """
        Читает текущую запись из БД (для ``find_conflicts``; для правил удаления ссылок —
        внутри транзакции сохранения: видны уже записанные правки).

        Args:
            entity    : (str) Тип записи.
            entity_id : (Hashable) Id записи.
            tx        : (Any/None) Сессия транзакции; None — своя сессия сервиса.

        Returns:
            (Dict[str, Any]/None) Поля записи; None — записи нет.

        Raises:
            Exception: Любая ошибка, кроме «не найдено» (``EntityNotFoundError`` и его
                наследников), — вызывающему; в том числе ``FileNotFoundError``.

        Example:
            >>> adapter.read('appointment', 12)['cost']
            400
        """
        try:
            # dto = self.service(entity).get_by_id(entity_id)
            # ↑ до 2026-10-18: только своей сессией; правила удаления ссылок читают внутри
            #   транзакции сохранения (видны уже записанные правки)
            dto = (self.service(entity).get_by_id(entity_id) if tx is None
                   else self.service(entity).get_by_id(entity_id, session=tx))
        # except Exception as e:
        #     if 'NotFound' in type(e).__name__:
        #         return None
        #     raise
        # ↑ до 2026-10-31 (М16, DB2): «не найдено» — по имени класса; под него попадал и
        #   FileNotFoundError (ошибка файла выдавалась за «записи нет»). Все «не найдено»
        #   сервисов — наследники EntityNotFoundError.
        except EntityNotFoundError:
            return None
        return None if dto is None else dto.model_dump()

    def referrers(
        self,
        entity : str,                   # тип ссылающихся записей
        field  : str,                   # поле ссылки
        ids    : Iterable[Hashable],    # id целей
        tx     : Any,                   # сессия транзакции
    ) -> List[Hashable]: # кто ссылается на цели
        """
        Возвращает id записей типа ``entity``, которые ссылаются полем ``field`` на записи
        ``ids`` (правило ``restrict`` черновиков; внутри транзакции сохранения).

        Пустой ``ids`` — пустой список без запроса к БД.

        Args:
            entity : (str) Тип ссылающихся записей.
            field  : (str) Поле ссылки.
            ids    : (Iterable[Hashable]) Id целей.
            tx     : (Any) Сессия транзакции.

        Returns:
            (List[Hashable]) Id ссылающихся записей.

        Example:
            >>> adapter.referrers(
            ...     'appointment',  # кто ссылается
            ...     'doctor_id',    # поле ссылки
            ...     [5],            # цели
            ...     session,        # транзакция
            ... )
            [12, 14]
        """
        wanted = list(ids)
        if not wanted:
            return []
        items, _ = self.service(entity).get_page_filtered(
            0,                                                          # с начала
            None,                                                       # без предела
            [{'column': field, 'operator': 'in', 'value': wanted}],     # фильтр по ссылке
            session   =   tx,                                           # транзакция сохранения
        )
        return [item.id for item in items]

    def delete(
        self,
        entity    : str,        # тип записи
        entity_id : Hashable,   # id записи
        tx        : Any,        # сессия транзакции
    ) -> None: # удаление записи через сервис
        """
        Удаляет запись через сервис (потомков в БД удаляет сервис / каскад БД).

        Args:
            entity    : (str) Тип записи.
            entity_id : (Hashable) Id записи.
            tx        : (Any) Сессия транзакции.

        Example:
            >>> adapter.delete('photo', 301, session)
        """
        self.service(entity).delete(entity_id, session=tx)


def make_parent_resolver(
    schema  : TreeSchema,       # схема дерева
    adapter : ServiceAdapter,   # адаптер с сервисами
) -> Callable[[str, Hashable], Optional[Hashable]]: # определитель родителя записи из БД
    """
    Возвращает определитель родителя записи без черновика: читает запись из БД и берёт
    поле внешнего ключа из схемы.

    Временные id новых записей (отрицательные) в БД не ищутся; корневой тип (нет поля
    родителя) — ``None`` без запроса. Ошибка чтения — ``None`` (хранилище в этом случае
    просто не поднимет значок выше): записи уже нет (``EntityNotFoundError`` — например,
    удалена другим окном) — строка журнала без трассировки; прочие ошибки — с трассировкой.

    Args:
        schema  : (TreeSchema) Схема дерева.
        adapter : (ServiceAdapter) Адаптер с сервисами.

    Returns:
        (Callable[[str, Hashable], Optional[Hashable]]) Функция ``(тип, id) -> id
            родителя | None``.

    Example:
        >>> resolve = make_parent_resolver(schema, adapter)
        >>> resolve('appointment', 12)
        1
    """

    def resolve(
        entity    : str,        # тип записи
        entity_id : Hashable,   # id записи
    ) -> Optional[Hashable]: # родитель записи из БД
        """
        Возвращает id родителя записи из БД.

        Args:
            entity    : (str) Тип записи.
            entity_id : (Hashable) Id записи.

        Returns:
            (Hashable/None) Id родителя; None — корневой тип, новая запись или ошибка чтения.

        Example:
            >>> resolve('photo', 301)
            55
        """
        field = schema.parent_field(entity)
        if field is None or (isinstance(entity_id, int) and entity_id < 0):
            return None
        try:
            dto = adapter.service(entity).get_by_id(entity_id)
        # ↓ до 2026-10-31 (М16, DB3): «записи нет» писалось трассировкой, как настоящая ошибка
        # except Exception:
        #     _log.exception("Не удалось определить родителя %s:%s", entity, entity_id)
        #     return None
        except EntityNotFoundError:
            _log.warning("Родитель %s:%s не определён: записи нет в БД", entity, entity_id)
            return None
        except Exception:
            _log.exception("Не удалось определить родителя %s:%s", entity, entity_id)
            return None
        return getattr(dto, field, None)

    return resolve


# ---------------------------------------------------------------------------
# Сохранение с вопросами пользователю
# ---------------------------------------------------------------------------
# До 2026-10-16 здесь была реализация save_with_confirmation (≈75 строк). В ней нет
# ничего от приложения — перенесена в переносимый пакет: app/utils/drafts/workflow.py.
# Имена Confirm и save_with_confirmation оставлены здесь (импорт) для совместимости.

from app.utils.drafts.workflow import Confirm, save_with_confirmation  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Сборка для приложения
# ---------------------------------------------------------------------------

@dataclass
class AppDrafts:
    """
    Черновики приложения: одно хранилище на главное окно (D1) + всё для сохранения.

    Attributes:
        schema  : (TreeSchema) Дерево таблиц.
        adapter : (ServiceAdapter) Сохранение через сервисы.
        store   : (DraftStore) Хранилище черновиков (общее для всех экранов).

    Example:
        >>> drafts = create_app_drafts()
        >>> drafts.save(
        ...     confirm_new_ancestors   =   ask,    # вопрос про новых родителей
        ...     confirm_deletes         =   ask,    # вопрос про удаляемые ветки
        ... )
    """

    schema: TreeSchema
    adapter: ServiceAdapter
    store: 'DraftStore'

    def save(
        self,
        targets               : Optional[Iterable[NodeKey]] = None,     # узлы цели; None — всё
        scope                 : Optional['SaveScope'] = None,           # направления; None — BRANCH
        confirm_new_ancestors : Optional[Confirm] = None,               # вопрос про новых родителей
        confirm_deletes       : Optional[Confirm] = None,               # вопрос про удаляемые ветки
        delete_policy         : Optional['DeletePolicy'] = None,        # политика удаления; None — по умолчанию
    ) -> Optional['SaveResult']: # сохранение с вопросами пользователю
        """
        Сохраняет черновики с вопросами пользователю — ``save_with_confirmation`` над
        своими хранилищем и адаптером.

        Args:
            targets               : (Iterable[NodeKey]/None) Узлы цели; None — всё.
            scope                 : (SaveScope/None) Направления; None — ``BRANCH``.
            confirm_new_ancestors : (Confirm/None) Вопрос про новых родителей.
            confirm_deletes       : (Confirm/None) Вопрос про удаляемые ветки.
            delete_policy         : (DeletePolicy/None) Политика удаления; None — по
                умолчанию пакета черновиков.

        Returns:
            (SaveResult/None) Итог; None — отказ пользователя.

        Example:
            >>> drafts.save(
            ...     [('appointment', 12)],  # цель
            ...     SaveScope.SELF,         # только сама запись
            ... )
        """
        return save_with_confirmation(
            self.store,             # хранилище
            self.adapter,           # запись через сервисы
            targets,                # цель
            scope,                  # направления
            confirm_new_ancestors,  # вопрос про новых родителей
            confirm_deletes,        # вопрос про удаляемые ветки
            delete_policy,          # политика удаления
        )


def create_app_drafts() -> AppDrafts: # черновики главного окна
    """
    Собирает черновики приложения: схема и адаптер — из описаний таблиц
    (``app.tables.CLINIC``), транзакция — общая база ``app.dependencies.get_db()``
    (одна на приложение, ТД-6; берётся при каждом сохранении — актуальная после смены БД),
    хранилище — с определителем родителя через БД.

    Note:
        Импорты внутри функции: ``app.tables`` и ``app.dependencies`` импортируют этот
        модуль (циклы импортов).

    Returns:
        (AppDrafts) Схема, адаптер, хранилище.

    Example:
        >>> drafts = create_app_drafts()
        >>> drafts.store.is_empty
        True
    """
    # from app.dependencies import (  # здесь, а не наверху: циклы импортов сервисов
    #     get_appointment_service, get_patient_service, get_photo_service,
    # )
    # from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
    # ↑ до 2026-10-18: нужны были для ручного перечня сервисов (ниже) — теперь описания таблиц
    from app.utils.drafts import DraftStore

    schema = build_app_schema()
    from app.dependencies import get_db
    # adapter = ServiceAdapter({
    #     'patient': (get_patient_service, PatientDTO),
    #     'appointment': (get_appointment_service, AppointmentDTO),
    #     'photo': (get_photo_service, PhotoDTO),
    # }, transaction_factory=lambda: get_db().session_scope())
    # ↑ до 2026-10-18: сервисы перечислялись вручную; теперь — из описаний таблиц
    from app.tables import CLINIC
    adapter = CLINIC.service_adapter(
        transaction_factory   =   lambda: get_db().session_scope(),   # общая база приложения
    )
    store = DraftStore(
        schema,                                                     # дерево таблиц
        parent_resolver   =   make_parent_resolver(schema, adapter),  # родитель из БД
    )
    return AppDrafts(
        schema    =   schema,     # дерево таблиц
        adapter   =   adapter,    # запись через сервисы
        store     =   store,      # общее хранилище
    )
