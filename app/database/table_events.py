# app/database/table_events.py
"""
События таблиц в стиле RAD Studio (Ф1.6.7г): действия по имени, подключённые к местам
«перед / после добавления, изменения, удаления строки», «перед коммитом», «после коммита /
отката» в описании таблицы (``TableDef.events``, ``app/schema/define.py``).

Устройство:

* **Реестр действий** — ``register_action(имя)``: действие — функция ``action(ctx)``,
  ``ctx`` — :class:`EventContext`. Описание таблиц модули с действиями не импортирует (К6):
  связь — только по имени. Встроенные действия регистрирует слой базы, действия верхних
  слоёв — сборка приложения (``app.dependencies``) ДО открытия базы: имена из описаний
  сверяются с реестром при открытии (:func:`check_action_names`, Р-9).
* **События строк** — события ``Mapper`` SQLAlchemy (``before_insert`` … ``after_delete``)
  внутри сброса в базу (flush): срабатывают при любом источнике изменений через ORM
  (сервис, черновики, сборщик), в том числе при каскаде и удалении «сирот». Обработчики
  ставятся один раз на процесс (на класс ``Mapper``) и ищут диспетчер своей базы в
  ``session.info`` (:data:`INFO_KEY`); у сессии без диспетчера (не из ``Database``) ничего
  не делают.
* **Диспетчер** (:class:`TableEvents`) — свой у каждого ``Database``: передаётся через
  ``sessionmaker(info=...)``, события сессии (``before_commit``, ``after_commit``,
  ``after_rollback``) вешаются на эту же фабрику один раз. Переоткрытая база
  (``app.dependencies.reopen_db``) — новый ``Database``, новая фабрика и диспетчер: повторов
  нет (Р-8).
* **Журнал транзакции** — изменённые строки таблиц, у которых есть действия транзакции
  (:class:`RowChange`): их получают действия «перед коммитом», «после коммита / отката».
  Живёт в ``session.info``, привязан к корневой транзакции (слабой ссылкой) и забирается при
  коммите, при откате и при конце транзакции без них (``close()`` — как откат, Р-16): сессия —
  ``scoped_session``, живёт дольше транзакции (как ТД-9). Точки сохранения (``begin_nested``)
  событиями транзакции не считаются (Р-18).

* **Сборщик мусора** — для таблиц ``keep='used'`` («только используемые»): кандидаты —
  строки, на которые в транзакции убрали ссылку (снимаются при сбросе); перед коммитом,
  ПОСЛЕ действий «перед коммитом» (они — один раз), круги «сброс → проверка одним запросом
  на таблицу → удаление через ORM» до неподвижной точки. Предел рабочих кругов — глубина
  цепочки таблиц по схеме + 1 (:class:`_CollectorPlan`, при открытии базы), при превышении —
  ``TableEventError`` и откат (решение владельца 2026-11-01). Полная проверка для кнопки —
  :meth:`TableEvents.find_unused` / :meth:`TableEvents.delete_unused`.

Ошибки (Р-12): действие, отказывающее в операции, выбрасывает своё исключение приложения
(``AppException``) — оно проходит как есть, ``flush`` / коммит падает, ``session_scope``
откатывает всю транзакцию; другое исключение действия оборачивается в
``TableEventError`` (таблица, место, действие, id — в ``details``). После коммита / отката
откатывать уже нечего: ошибки действий там только пишутся в журнал (Р-5).

Ограничения SQLAlchemy: действия строк выполняются ВНУТРИ flush — менять сессию (``add``,
``delete``) в них нельзя, можно только читать через ``ctx.connection`` и запоминать;
изменения данных — в «перед коммитом». Добавление / удаление строк сессии действием строки —
``TableEventError`` (Р-21: SQLAlchemy такие правки молча теряет или вставляет после уборки). Изменения мимо ORM (``query().delete()``, сырой
SQL) событий не вызывают — в коде их нет (тест ``tests/test_database_shema/test_orm_only.py``, Р-1).

Example:
    >>> @register_action('log_removal')
    ... def log_removal(ctx: EventContext) -> None:
    ...     print(ctx.table, ctx.event)
    >>> # app/schema/clinic.py: TableDef(..., events=(on('after_delete', 'log_removal'),))
"""

from __future__ import annotations

import weakref   # журнал транзакции — слабая ссылка на транзакцию (Р-16)
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import event, exists, inspect, select
from sqlalchemy.orm import ONETOMANY, Mapper, object_session

from app.exceptions import AppException, TableEventError
from app.schema.define import KEEP_USED, ROW_EVENTS, TABLE_EVENTS, TRANSACTION_EVENTS
from app.utils.logger import AppLogger


INFO_KEY : str = 'table_events'      # session.info: диспетчер базы
_TX_KEY  : str = 'table_events_tx'   # session.info: журнал текущей транзакции

# Реестр действий: имя → функция action(ctx)
_ACTIONS : Dict[str, Callable[['EventContext'], None]] = {}


@dataclass
class RowChange:
    """
    Изменённая в транзакции строка (журнал для действий транзакции).

    Attributes:
        table     : (str) Имя таблицы.
        operation : (str) ``insert`` / ``update`` / ``delete``.
        key       : (Any) Первичный ключ (одно значение или кортеж).
        values    : (Dict[str, Any]) Значения столбцов: после добавления / изменения —
            загруженные в объекте; удаления — строка до удаления.
        old       : (Dict[str, Any]) Изменения: прежние значения изменённых столбцов.

    Example:
        >>> RowChange('photos', 'delete', 7, {'file_path': 'a.png'}).operation
        'delete'
    """

    table     : str
    operation : str
    key       : Any
    values    : Dict[str, Any] = field(default_factory=dict)
    old       : Dict[str, Any] = field(default_factory=dict)


@dataclass
class EventContext:
    """
    Что получает действие события таблицы.

    Attributes:
        event      : (str) Место события (``after_delete``, ``after_commit`` …).
        table      : (str) Имя таблицы.
        table_def  : (Any) Описание таблицы (``TableDef``).
        session    : (Any) Сессия SQLAlchemy.
        target     : (Any) События строк: объект строки; транзакции — None.
        connection : (Any) События строк: соединение flush (только чтение); иначе None.
        old        : (Dict[str, Any]) ``before_update`` / ``after_update``: прежние значения
            изменённых столбцов; иначе пусто.
        changes    : (Tuple[RowChange, ...]) События транзакции: строки этой таблицы,
            изменённые в транзакции (по порядку); строк — пусто.

    Example:
        >>> def forbid(ctx: EventContext) -> None:
        ...     if ctx.target.paid:
        ...         raise AppointmentValidationError('paid', 'оплаченный приём не удаляется')
    """

    event      : str
    table      : str
    table_def  : Any
    session    : Any
    target     : Any = None
    connection : Any = None
    old        : Dict[str, Any] = field(default_factory=dict)
    changes    : Tuple[RowChange, ...] = ()


def register_action(
    name    : str,                                           # имя действия (как в описании)
    func    : Optional[Callable[[EventContext], None]] = None,  # действие; None — декоратор
    *,
    replace : bool = False,                                  # заменить уже зарегистрированное
) -> Callable[..., Any]: # регистрирует действие (или возвращает декоратор)
    """
    Регистрирует действие события таблицы под именем ``name``.

    Без ``func`` — декоратор. Имя уже занято другим действием — ошибка (две разные функции
    под одним именем — молчаливая подмена); та же функция повторно — без ошибки.

    Args:
        name    : (str) Имя действия — так его называют в ``on(...)`` описания.
        func    : (Callable/None) Действие ``action(ctx)``; None — вернуть декоратор.
        replace : (bool) Заменить другое действие с тем же именем (тесты, перезагрузка).

    Returns:
        (Callable) Зарегистрированная функция или декоратор.

    Raises:
        ValueError: Пустое имя; имя занято другим действием (без ``replace``).

    Example:
        >>> @register_action('log_removal')
        ... def log_removal(ctx: EventContext) -> None:
        ...     pass
        >>> 'log_removal' in registered_actions()
        True
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"имя действия должно быть непустой строкой, а не {name!r}")

    def decorator(
        f : Callable[[EventContext], None],   # действие
    ) -> Callable[[EventContext], None]: # регистрирует и возвращает действие
        """Регистрирует действие под именем ``name`` и возвращает его без изменений."""
        current = _ACTIONS.get(name)
        if current is not None and current is not f and not replace:
            raise ValueError(f"действие {name!r} уже зарегистрировано: {current!r}")
        _ACTIONS[name] = f
        return f

    if func is None:
        return decorator
    return decorator(func)


def unregister_action(
    name : str,   # имя действия
) -> None: # убирает действие из реестра
    """
    Убирает действие из реестра (нет такого — ничего не делает). Для тестов.

    Args:
        name : (str) Имя действия.

    Example:
        >>> unregister_action('log_removal')
    """
    _ACTIONS.pop(name, None)


def registered_actions() -> Tuple[str, ...]: # имена зарегистрированных действий
    """
    Возвращает имена зарегистрированных действий по алфавиту.

    Returns:
        (Tuple[str, ...]) Имена.

    Example:
        >>> registered_actions()
        ()
    """
    return tuple(sorted(_ACTIONS))


def table_def_of(
    mapper_or_class : Any,   # Mapper или класс модели
) -> Any: # описание таблицы (TableDef) или None
    """
    Возвращает описание таблицы модели (``__table_def__``, ставит ``TableDef.build_model``);
    модель без описания (написанная вручную, тестовая) — None.

    Args:
        mapper_or_class : (Any) ``Mapper`` или класс модели.

    Returns:
        (TableDef/None) Описание.

    Example:
        >>> table_def_of(Patient) is PATIENTS
        True
    """
    cls = getattr(mapper_or_class, 'class_', mapper_or_class)
    return getattr(cls, '__table_def__', None)


def _mapped_defs(
    base : Any,   # декларативная база (Base приложения)
) -> List[Any]: # описания таблиц моделей базы
    """
    Возвращает описания таблиц всех моделей базы ``base`` (у которых оно есть).

    Args:
        base : (Any) Декларативная база.

    Returns:
        (List[TableDef]) Описания (без повторов).

    Example:
        >>> [d.name for d in _mapped_defs(Base)][:1]
        ['patients']
    """
    result : List[Any] = []
    for mapper in base.registry.mappers:
        table_def = table_def_of(mapper)
        if table_def is not None and table_def not in result:
            result.append(table_def)
    return result


def check_action_names(
    base : Any,   # декларативная база (Base приложения)
) -> None: # сверяет имена действий описаний с реестром
    """
    Сверяет имена действий во всех описаниях таблиц моделей ``base`` с реестром (Р-9):
    опечатка обнаруживается при открытии базы, а не при первом событии.

    Args:
        base : (Any) Декларативная база.

    Raises:
        TableEventError: Есть неизвестные имена — все перечислены (таблица, место, имя).

    Example:
        >>> check_action_names(Base)   # всё зарегистрировано — без ошибки
    """
    unknown : List[str] = []
    for table_def in _mapped_defs(base):
        for event_name in TABLE_EVENTS:
            for name in table_def.actions_for(event_name):
                if name not in _ACTIONS:
                    unknown.append(f"{table_def.name}.{event_name}: {name}")
    if unknown:
        raise TableEventError(
            f"в описании таблиц названы неизвестные действия: {'; '.join(unknown)}",
            details = {
                'зарегистрированы' : ', '.join(registered_actions()) or '—',   # что есть
            },
        )


def _has_transaction_actions(
    table_def : Any,   # описание таблицы
) -> bool: # нужен ли таблице журнал транзакции
    """
    Возвращает ``True``, если у таблицы есть действия «перед коммитом», «после коммита /
    отката» — им нужен журнал изменённых строк.

    Args:
        table_def : (TableDef) Описание.

    Returns:
        (bool) Нужен журнал.

    Example:
        >>> _has_transaction_actions(PATIENTS)
        False
    """
    return any(table_def.actions_for(name) for name in TRANSACTION_EVENTS)


def _primary_key(
    mapper : Any,   # Mapper модели
    target : Any,   # объект строки
) -> Any: # первичный ключ строки
    """
    Возвращает первичный ключ строки: одно значение или кортеж (составной).

    Args:
        mapper : (Mapper) Модель.
        target : (Any) Объект.

    Returns:
        (Any) Ключ.

    Example:
        >>> _primary_key(inspect(Patient), patient)
        1
    """
    values = mapper.primary_key_from_instance(target)
    return values[0] if len(values) == 1 else tuple(values)


def _loaded_values(
    mapper : Any,   # Mapper модели
    target : Any,   # объект строки
) -> Dict[str, Any]: # загруженные значения столбцов
    """
    Возвращает значения столбцов, загруженные в объекте (не загруженные — не попадают;
    запросов нет).

    Args:
        mapper : (Mapper) Модель.
        target : (Any) Объект.

    Returns:
        (Dict[str, Any]) Атрибут → значение.

    Example:
        >>> _loaded_values(inspect(Photo), photo)['file_path']
        'app_1/a.png'
    """
    state_dict = inspect(target).dict
    return {
        prop.key: state_dict[prop.key]
        for prop in mapper.column_attrs
        if prop.key in state_dict
    }


def _row_from_db(
    mapper     : Any,   # Mapper модели
    connection : Any,   # соединение flush
    target     : Any,   # объект строки
) -> Dict[str, Any]: # строка в базе до изменения
    """
    Читает строку из базы по первичному ключу через соединение flush (в ``before_update`` /
    ``before_delete`` — значения ДО изменения, даже если в объекте они не загружены или
    уже изменены).

    Args:
        mapper     : (Mapper) Модель.
        connection : (Connection) Соединение flush.
        target     : (Any) Объект.

    Returns:
        (Dict[str, Any]) Атрибут → значение; строки нет — пусто.

    Example:
        >>> _row_from_db(inspect(Photo), connection, photo)['file_path']
        'app_1/a.png'
    """
    props = list(mapper.column_attrs)
    keys = mapper.primary_key_from_instance(target)
    query = select(
        *[prop.columns[0] for prop in props],
    ).where(
        *[column == value for column, value in zip(mapper.primary_key, keys)],
    )
    row = connection.execute(query).first()
    if row is None:
        return {}
    return {prop.key: value for prop, value in zip(props, row)}


def _old_values(
    mapper     : Any,   # Mapper модели
    connection : Any,   # соединение flush
    target     : Any,   # изменяемый объект
) -> Dict[str, Any]: # прежние значения изменённых столбцов
    """
    Возвращает прежние значения изменённых столбцов (``before_update``): из истории
    атрибута, а если её нет (атрибут меняли, не загрузив) — из строки в базе.

    Args:
        mapper     : (Mapper) Модель.
        connection : (Connection) Соединение flush.
        target     : (Any) Объект.

    Returns:
        (Dict[str, Any]) Атрибут → прежнее значение.

    Example:
        >>> _old_values(inspect(Appointment), connection, appointment)
        {'reason_id': 5}
    """
    state = inspect(target)
    old : Dict[str, Any] = {}
    unknown : List[str] = []
    for prop in mapper.column_attrs:
        history = state.attrs[prop.key].history
        if not history.has_changes():
            continue
        if history.deleted:
            old[prop.key] = history.deleted[0]
        else: # меняли, не загрузив, — прежнее значение только в базе
            unknown.append(prop.key)
    if unknown:
        row = _row_from_db(
            mapper,
            connection,
            target,
        )
        for key in unknown:
            old[key] = row.get(key)
    return old


_IN_CHUNK : int = 500   # id в одном IN (предел переменных SQLite — 999 в старых версиях)


def _chunks(
    values : List[Any],   # значения
) -> Iterable[List[Any]]: # порции по _IN_CHUNK
    """
    Делит список на порции для ``IN (...)`` (предел числа переменных запроса SQLite).

    Args:
        values : (List[Any]) Значения.

    Returns:
        (Iterable[List[Any]]) Порции по порядку.

    Example:
        >>> [len(c) for c in _chunks(list(range(1200)))]
        [500, 500, 200]
    """
    for start in range(0, len(values), _IN_CHUNK):
        yield values[start:start + _IN_CHUNK]


def _cascade_closure(
    mapper : Any,   # Mapper модели
) -> List[Tuple[Any, frozenset]]: # модели, удаляемые ORM вместе со строкой, и их ключи связи
    """
    Возвращает модель и все модели, строки которых ORM удаляет вместе с её строкой
    (связи «один ко многим» с каскадом ``delete`` / ``delete-orphan``, рекурсивно), — у
    каждой столбцы связи с родителем (они указывают на удаляемого родителя, ссылкой на
    другую таблицу не считаются).

    Args:
        mapper : (Mapper) Модель.

    Returns:
        (List[Tuple[Mapper, frozenset]]) Пары «модель — столбцы связи с родителем».

    Example:
        >>> [m.class_.__name__ for m, _ in _cascade_closure(inspect(Patient))]
        ['Patient', 'Appointment', 'Photo']
    """
    result : List[Tuple[Any, frozenset]] = [(mapper, frozenset())]
    seen = {mapper}
    index = 0
    while index < len(result):
        current, _ = result[index]
        index += 1
        for rel in current.relationships:
            if rel.direction is not ONETOMANY:
                continue
            if not (rel.cascade.delete or rel.cascade.delete_orphan):
                continue
            if rel.mapper in seen:
                continue
            seen.add(rel.mapper)
            result.append((rel.mapper, frozenset(rel.remote_side)))
    return result


class _CollectorPlan:
    """
    План сборщика мусора, вычисленный по схеме при открытии базы: таблицы «только
    используемые», глубина цепочки удалений и предел кругов (решение владельца 2026-11-01:
    глубина по схеме + 1; при превышении — откат).

    Глубина: граф на таблицах «только используемые», ребро U → V — если строка U (или
    строка, которую ORM удаляет вместе с ней каскадом) ссылается на V; глубина — число
    таблиц на самом длинном пути. Удаление строки U освобождает строки V — следующий круг.
    Круг в графе (самоссылка, A ↔ B) — ошибка: подсчёт ссылок такие строки не собирает, а
    число кругов зависело бы от данных (Р-20).

    Attributes:
        used  : (Dict[Table, Mapper]) Таблицы «только используемые» и их модели.
        order : (List[Table]) Они же в порядке зависимостей метаданных.
        depth : (int) Глубина цепочки (у заметок — 1; нет таблиц — 0).
        limit : (int) Предел рабочих кругов: ``depth + 1``.

    Example:
        >>> plan = _CollectorPlan.build(Base)
        >>> (plan.depth, plan.limit)
        (1, 2)
    """

    def __init__(
        self,
        used  : Dict[Any, Any],   # таблица → модель (только используемые)
        order : List[Any],        # таблицы в порядке зависимостей
        depth : int,              # глубина цепочки удалений
    ) -> None:
        """
        Создаёт план (обычно — :meth:`build`).

        Args:
            used  : (Dict[Table, Mapper]) Таблицы «только используемые».
            order : (List[Table]) Порядок обхода.
            depth : (int) Глубина.

        Example:
            >>> _CollectorPlan({}, [], 0).limit
            1
        """
        self.used  = used
        self.order = order
        self.depth = depth
        self.limit = depth + 1
        self._watched : Dict[Any, Tuple[Tuple[str, str], ...]] = {}

    @classmethod
    def build(
        cls,
        base : Any,   # декларативная база
    ) -> '_CollectorPlan': # план по схеме моделей базы
        """
        Строит план по моделям базы ``base``.

        Args:
            base : (Any) Декларативная база.

        Returns:
            (_CollectorPlan) План.

        Raises:
            TableEventError: Таблицы «только используемые» ссылаются по кругу; у такой
                таблицы составной первичный ключ.

        Example:
            >>> _CollectorPlan.build(Base).limit
            2
        """
        used : Dict[Any, Any] = {}
        for mapper in base.registry.mappers:
            table_def = table_def_of(mapper)
            if table_def is not None and table_def.keep == KEEP_USED:
                if len(mapper.primary_key) != 1:
                    raise TableEventError(
                        f"таблица «только используемые» {mapper.local_table.name}: составной "
                        f"первичный ключ сборщик не поддерживает",
                    )
                used[mapper.local_table] = mapper
        edges : Dict[Any, set] = {table: set() for table in used}
        for table, mapper in used.items():
            for member, link in _cascade_closure(mapper):
                for fk in member.local_table.foreign_keys:
                    if fk.column.table in used and fk.parent not in link:
                        edges[table].add(fk.column.table)
        depth = _longest_path(edges)       # круг — ошибка (до сортировки: она бы предупреждала)
        order = [table for table in base.metadata.sorted_tables if table in used]
        return cls(
            used,                           # таблицы
            order,                          # порядок
            depth,                          # глубина
        )

    def is_used(
        self,
        mapper : Any,   # Mapper модели
    ) -> bool: # таблица «только используемые»
        """
        Возвращает ``True``, если таблица модели — «только используемые».

        Args:
            mapper : (Mapper) Модель.

        Returns:
            (bool) Да / нет.

        Example:
            >>> plan.is_used(inspect(AppointmentNote))
            True
        """
        return mapper.local_table in self.used

    def watched(
        self,
        mapper : Any,   # Mapper модели
    ) -> Tuple[Tuple[str, str], ...]: # (атрибут, таблица цели) ссылок на «только используемые»
        """
        Возвращает ссылки модели на таблицы «только используемые»: пары «атрибут столбца —
        имя таблицы цели» (запоминается на модель; работает и для моделей без описания).

        Args:
            mapper : (Mapper) Модель.

        Returns:
            (Tuple[Tuple[str, str], ...]) Пары; пусто — модель ни на что такое не ссылается.

        Example:
            >>> plan.watched(inspect(Patient))
            (('description_id', 'appointments_notes'), ('comment_id', 'appointments_notes'))
        """
        cached = self._watched.get(mapper)
        if cached is None:
            pairs = []
            if self.used:
                for prop in mapper.column_attrs:
                    for column in prop.columns:
                        for fk in getattr(column, 'foreign_keys', ()):
                            if fk.column.table in self.used:
                                pairs.append((prop.key, fk.column.table.name))
            cached = self._watched[mapper] = tuple(pairs)
        return cached

    def refs(
        self,
        table    : Any,        # таблица «только используемые»
        existing : set,        # имена таблиц, существующих в базе
    ) -> List[Any]: # столбцы, ссылающиеся на таблицу
        """
        Возвращает все столбцы схемы, ссылающиеся на таблицу (внешние ключи из метаданных),
        — только таблиц, существующих в базе (модель могли добавить, а миграцию не
        применить). Метаданные читаются каждый раз: модели могут добавиться после открытия.

        Args:
            table    : (Table) Таблица.
            existing : (set) Имена таблиц в базе.

        Returns:
            (List[Column]) Столбцы.

        Example:
            >>> [c.name for c in plan.refs(notes_table, existing)][:2]
            ['description_id', 'comment_id']
        """
        return [
            fk.parent
            for other in table.metadata.sorted_tables
            if other.name in existing
            for fk in other.foreign_keys
            if fk.column.table is table
        ]


def _longest_path(
    edges : Dict[Any, set],   # граф: таблица → таблицы, которые она освобождает
) -> int: # число вершин на самом длинном пути
    """
    Возвращает число вершин на самом длинном пути графа освобождения; круг — ошибка.

    Args:
        edges : (Dict[Table, set]) Граф.

    Returns:
        (int) Глубина; пустой граф — 0.

    Raises:
        TableEventError: В графе круг (самоссылка, A ↔ B …) — с путём круга.

    Example:
        >>> _longest_path({'a': {'b'}, 'b': set()})
        2
    """
    depth : Dict[Any, int] = {}
    visiting : List[Any] = []

    def visit(
        node : Any,   # вершина
    ) -> int: # глубина от вершины
        """Возвращает глубину пути от вершины; круг — TableEventError."""
        if node in depth:
            return depth[node]
        if node in visiting:
            cycle = visiting[visiting.index(node):] + [node]
            raise TableEventError(
                "таблицы «только используемые» ссылаются по кругу ("
                + ' → '.join(getattr(t, 'name', str(t)) for t in cycle)
                + ") — сборщик мусора такие строки не соберёт",
            )
        visiting.append(node)
        result = 1 + max((visit(nxt) for nxt in edges[node]), default=0)
        visiting.pop()
        depth[node] = result
        return result

    return max((visit(node) for node in edges), default=0)


class _TransactionLog:
    """
    Журнал текущей транзакции сессии: изменённые строки таблиц с действиями транзакции,
    прежние значения, снятые в «перед изменением / удалением», и состояние сборщика мусора
    (кандидаты, удалённое, круги).

    Example:
        >>> log = _TransactionLog()
        >>> log.changes
        []
    """

    def __init__(
        self,
        transaction : Any = None,   # корневая транзакция сессии (None — пустой журнал)
    ) -> None:
        """
        Создаёт пустой журнал корневой транзакции ``transaction`` (слабая ссылка: журнал
        другой транзакции не подхватывается — Р-16).

        Args:
            transaction : (SessionTransaction/None) Корневая транзакция; None — журнал ни к
                чему не привязан (пустой, для закончившейся транзакции без журнала).

        Example:
            >>> _TransactionLog().pending_old
            {}
        """
        self.transaction = weakref.ref(transaction) if transaction is not None else None
        self.changes     : List[Tuple[Any, RowChange]] = []          # (описание, строка)
        self.pending_old : Dict[Tuple[str, Any], Dict[str, Any]] = {}  # (таблица, ключ) → значения до
        # сборщик мусора
        self.candidates  : Dict[str, Dict[Any, Any]] = {}   # таблица → {id: источник (почему)}
        self.gone        : set = set()                      # (таблица, id) удалённые в транзакции
        self.phase       : str = 'collect'                  # collect → loop → sealed | failed
        self.collected   : List[Tuple[str, Any, int, Any]] = []   # (таблица, id, круг, источник)
        self.rounds      : List[Dict[str, Any]] = []        # круги: кандидаты, удалено
        self.late        : List[Tuple[str, Any, Any]] = []  # кандидаты после уборки (Р-15)

    def belongs_to(
        self,
        transaction : Any,   # корневая транзакция сессии
    ) -> bool: # журнал этой транзакции
        """
        Возвращает ``True``, если журнал ведётся для транзакции ``transaction``.

        Args:
            transaction : (SessionTransaction) Корневая транзакция.

        Returns:
            (bool) Журнал этой транзакции.

        Example:
            >>> _TransactionLog(tx).belongs_to(tx)
            True
        """
        return self.transaction is not None and self.transaction() is transaction

    def nominate(
        self,
        table  : str,   # таблица «только используемые»
        row_id : Any,   # id строки, на которую убрали ссылку
        source : Any,   # почему: (таблица, атрибут, id, операция)
    ) -> None: # добавляет кандидата сборщика
        """
        Добавляет кандидата сборщика: на строку ``table`` / ``row_id`` в транзакции убрали
        ссылку. Уже удалённая в транзакции — пропускается; после уборки (журнал закрыт) —
        запоминается как поздний (Р-15: проверен не будет, предупреждение после коммита).

        Args:
            table  : (str) Таблица.
            row_id : (Any) Id строки.
            source : (Any) Источник — для журнала (Р-11).

        Example:
            >>> log.nominate('appointments_notes', 5, ('appointments', 'reason_id', 88, 'update'))
        """
        if row_id is None or (table, row_id) in self.gone:
            return
        if self.phase == 'sealed':
            self.late.append((table, row_id, source))
            return
        self.candidates.setdefault(table, {}).setdefault(row_id, source)

    def for_table(
        self,
        table_def : Any,   # описание таблицы
    ) -> Tuple[RowChange, ...]: # строки таблицы в журнале
        """
        Возвращает изменённые строки таблицы по порядку изменений.

        Args:
            table_def : (TableDef) Описание.

        Returns:
            (Tuple[RowChange, ...]) Строки.

        Example:
            >>> log.for_table(PHOTOS)
            ()
        """
        return tuple(change for owner, change in self.changes if owner is table_def)

    def tables(self) -> List[Any]: # описания таблиц с изменениями, по порядку первого изменения
        """
        Возвращает описания таблиц, у которых есть изменённые строки, — по порядку первого
        изменения.

        Returns:
            (List[TableDef]) Описания.

        Example:
            >>> log.tables()
            []
        """
        result : List[Any] = []
        for owner, _ in self.changes:
            if owner not in result:
                result.append(owner)
        return result


class TableEvents:
    """
    Диспетчер событий таблиц одной базы: исполняет действия описаний таблиц и ведёт журнал
    транзакции.

    Один на ``Database``: ``Database`` создаёт фабрику сессий с ``info={INFO_KEY:
    диспетчер}`` и вызывает :meth:`listen` — события сессии вешаются на эту фабрику один
    раз. Обработчики событий строк общие для процесса (:func:`_install_row_listeners`).

    Attributes:
        logger : (AppLogger) Журнал.

    Example:
        >>> events = TableEvents()
        >>> Session = sessionmaker(bind=engine, info={INFO_KEY: events})
        >>> events.listen(Session)
    """

    def __init__(
        self,
        logger : Optional[AppLogger] = None,   # журнал (None — api.TableEvents)
    ) -> None:
        """
        Создаёт диспетчер и (один раз на процесс) ставит обработчики событий строк.

        Args:
            logger : (AppLogger/None) Журнал; None — ``api.TableEvents``, файл пользователя.

        Example:
            >>> TableEvents().logger is not None
            True
        """
        self.logger = logger or AppLogger.get_instance(
            name                 = 'api.TableEvents',   # журнал событий таблиц
            enable_file_logging  = 'user',              # файл пользователя
            use_name_in_filename = False,               # имя не в имени файла
        )
        self.plan = _CollectorPlan({}, [], 0)           # без таблиц «только используемые»
        self._commits = 0                               # номер коммита для журнала (Р-11)
        _install_row_listeners()

    def configure(
        self,
        base : Any,   # декларативная база (Base приложения)
    ) -> None: # вычисляет план сборщика по схеме
        """
        Вычисляет план сборщика мусора по моделям ``base`` (при открытии базы): таблицы
        «только используемые», глубину цепочки удалений и предел кругов (глубина + 1).

        Args:
            base : (Any) Декларативная база.

        Raises:
            TableEventError: Таблицы «только используемые» ссылаются по кругу.

        Example:
            >>> events.configure(Base)
            >>> events.plan.limit
            2
        """
        self.plan = _CollectorPlan.build(base)
        if self.plan.used:
            self.logger.debug(
                f"сборщик мусора: {', '.join(t.name for t in self.plan.order)}; "
                f"глубина {self.plan.depth}; предел кругов {self.plan.limit}"
            )

    def listen(
        self,
        session_factory : Any,   # фабрика сессий (sessionmaker) с info={INFO_KEY: self}
    ) -> None: # вешает события сессии на фабрику (один раз)
        """
        Вешает обработчики ``before_commit``, ``after_commit``, ``after_rollback``,
        ``after_transaction_end`` на фабрику сессий; повторный вызов для той же фабрики
        ничего не делает (Р-8).

        Args:
            session_factory : (sessionmaker) Фабрика.

        Example:
            >>> events.listen(Session)
            >>> events.listen(Session)   # повтор — без второй регистрации
        """
        if getattr(session_factory, '_table_events_listening', False):
            return
        event.listen(session_factory, 'before_commit', self._before_commit)
        event.listen(session_factory, 'after_commit', self._after_commit)
        event.listen(session_factory, 'after_rollback', self._after_rollback)
        event.listen(session_factory, 'after_transaction_end', self._after_transaction_end)
        session_factory._table_events_listening = True

    # ------------------------------------------------------------------ журнал транзакции

    def _log(
        self,
        session : Any,   # сессия
    ) -> _TransactionLog: # журнал текущей транзакции (создаётся при первом обращении)
        """
        Возвращает журнал текущей корневой транзакции сессии (создаёт при первом обращении).

        Журнал в ``session.info`` от другой транзакции (её закрыли так, что ни одно событие
        журнал не забрало) — отбрасывается с предупреждением: его строки к этой транзакции
        не относятся (Р-16).

        Args:
            session : (Session) Сессия.

        Returns:
            (_TransactionLog) Журнал.

        Example:
            >>> events._log(session).changes
            []
        """
        transaction = session.get_transaction()
        log = session.info.get(_TX_KEY)
        if log is not None and not log.belongs_to(transaction):
            self.logger.warning(
                f"журнал событий таблиц закончившейся транзакции отброшен "
                f"({len(log.changes)} строк)"
            )
            log = None
        if log is None:
            log = session.info[_TX_KEY] = _TransactionLog(transaction)
        return log

    @staticmethod
    def _take_log(
        session : Any,   # сессия
    ) -> _TransactionLog: # журнал закончившейся транзакции (в сессии больше нет)
        """
        Забирает журнал закончившейся транзакции из сессии: следующая транзакция начинает с
        пустого (сессия живёт дольше транзакции, ТД-9).

        Args:
            session : (Session) Сессия.

        Returns:
            (_TransactionLog) Журнал (пустой, если его не было).

        Example:
            >>> TableEvents._take_log(session).changes
            []
        """
        return session.info.pop(_TX_KEY, None) or _TransactionLog()

    # ------------------------------------------------------------------ исполнение действий

    def _run(
        self,
        names : Iterable[str],   # имена действий по порядку
        ctx   : EventContext,    # что получает действие
    ) -> None: # выполняет действия; ошибку — исключением приложения
        """
        Выполняет действия по порядку. Исключение приложения из действия проходит как есть
        (намеренный отказ, Р-12); другое — ``TableEventError`` с подробностями (``raise …
        from``). Транзакцию откатывает тот, кто коммитит (``session_scope``).

        Args:
            names : (Iterable[str]) Имена действий.
            ctx   : (EventContext) Контекст.

        Raises:
            AppException: Отказ действия — как есть.
            TableEventError: Другая ошибка действия или действия нет в реестре.

        Example:
            >>> events._run(('log_removal',), ctx)
        """
        for name in names:
            action = _ACTIONS.get(name)
            details = {
                'таблица'  : ctx.table,                                         # где
                'место'    : ctx.event,                                         # когда
                'действие' : name,                                              # что
                'id'       : _primary_key(inspect(ctx.target).mapper, ctx.target)
                             if ctx.target is not None else None,               # строка
            }
            if action is None: # реестр сверяется при открытии; сюда — только если сняли после
                raise TableEventError(
                    f"действие {name!r} не зарегистрировано",
                    details = details,
                )
            try:
                action(ctx)
            except AppException:
                raise
            except Exception as exc:
                raise TableEventError(
                    f"действие {name!r} ({ctx.table}, {ctx.event}) завершилось ошибкой: {exc}",
                    details = details,
                ) from exc

    def _run_logged(
        self,
        names : Iterable[str],   # имена действий по порядку
        ctx   : EventContext,    # что получает действие
    ) -> None: # выполняет действия; ошибки — только в журнал
        """
        Выполняет действия после коммита / отката: откатывать уже нечего (Р-5), поэтому
        ошибка действия пишется в журнал, остальные действия выполняются.

        Args:
            names : (Iterable[str]) Имена действий.
            ctx   : (EventContext) Контекст.

        Example:
            >>> events._run_logged(('delete_photo_file',), ctx)
        """
        for name in names:
            try:
                self._run(
                    (name,),
                    ctx,
                )
            except AppException as exc:
                self.logger.exception(exc.log_text())

    # ------------------------------------------------------------------ события строк

    def on_row(
        self,
        event_name : str,   # место (ROW_EVENTS)
        mapper     : Any,   # Mapper модели
        connection : Any,   # соединение flush
        target     : Any,   # объект строки
        session    : Any,   # сессия объекта
    ) -> None: # исполняет действия строки и ведёт журнал
        """
        Обрабатывает событие строки: снимает прежние значения («перед изменением /
        удалением»), выполняет действия места, затем отмечает кандидатов сборщика мусора
        (прежние ссылки на таблицы «только используемые» — при сбросе, пока история есть,
        Р-3; после действий — их правки своей строки учтены), записывает строку в журнал
        транзакции («после …», только таблицы с действиями транзакции). Ссылки смотрятся и у
        моделей без описания.

        Args:
            event_name : (str) Место события строки.
            mapper     : (Mapper) Модель.
            connection : (Connection) Соединение flush.
            target     : (Any) Объект.
            session    : (Session) Сессия.

        Raises:
            AppException: Отказ действия; ``TableEventError`` — другая ошибка.

        Example:
            >>> events.on_row('after_delete', inspect(Photo), connection, photo, session)
        """
        table_def = table_def_of(mapper)
        actions = table_def.actions_for(event_name) if table_def is not None else ()
        journal = table_def is not None and _has_transaction_actions(table_def)
        watched = self.plan.watched(mapper) if event_name in ('before_update', 'before_delete') else ()
        used = self.plan.is_used(mapper)
        if not (actions or journal or watched or used):
            return

        log = self._log(session)
        operation = event_name.split('_', 1)[1]               # insert / update / delete
        table_name = mapper.local_table.name
        row_key = (table_name, _primary_key(mapper, target))
        old : Dict[str, Any] = {}
        row : Dict[str, Any] = {}

        if event_name == 'before_update':
            old = _old_values(
                mapper,
                connection,
                target,
            )
            log.pending_old[row_key] = old
        elif event_name == 'before_delete' and (journal or watched): # строка до удаления
            row = _row_from_db(
                mapper,
                connection,
                target,
            )
            if journal: # для «после коммита / отката»
                log.pending_old[row_key] = row
        elif event_name == 'after_update':
            old = log.pending_old.get(row_key, {})

        if actions:
            # внутри flush сессию менять нельзя: SQLAlchemy молча теряет правки чужих объектов,
            # а новые вставляет уже после уборки (Р-21) — нарушение видно по числу new / deleted
            before_change = (len(session.new), len(session.deleted))
            self._run(
                actions,
                EventContext(
                    event      = event_name,           # место
                    table      = table_def.name,       # таблица
                    table_def  = table_def,            # описание
                    session    = session,              # сессия
                    target     = target,               # строка
                    connection = connection,           # чтение внутри flush
                    old        = old,                  # прежние значения (изменение)
                ),
            )
            if (len(session.new), len(session.deleted)) != before_change:
                raise TableEventError(
                    f"действие события {event_name} таблицы {table_def.name} добавило или "
                    f"удалило строки сессии внутри сброса в базу — так нельзя (изменения — в "
                    f"«перед коммитом»)",
                    details = {
                        'таблица'  : table_name,                  # где
                        'место'    : event_name,                  # когда
                        'действия' : ', '.join(actions),          # кто
                        'id'       : row_key[1],                  # строка
                    },
                )

        # сборщик мусора: прежние ссылки на «только используемые» — кандидаты (после действий)
        if watched:
            state_dict = inspect(target).dict
            for key, target_table in watched:
                if event_name == 'before_update':
                    if key not in old or old[key] == state_dict.get(key, old[key]):
                        continue
                    released = old[key]
                else: # удаление — все ссылки строки
                    released = row.get(key)
                log.nominate(
                    target_table,                                       # таблица цели
                    released,                                           # id строки цели
                    (table_name, key, row_key[1], operation),           # почему (Р-11)
                )
        if used and event_name == 'after_delete':
            log.gone.add(row_key)
        elif used and event_name == 'after_insert': # id мог быть выдан повторно (Р-19)
            log.gone.discard(row_key)

        if journal and event_name.startswith('after_'):
            before = log.pending_old.pop(row_key, {})
            values = before if operation == 'delete' else _loaded_values(mapper, target)
            log.changes.append((
                table_def,
                RowChange(
                    table     = table_name,                                     # таблица
                    operation = operation,                                      # что сделано
                    key       = row_key[1],                                     # ключ
                    values    = values,                                         # значения
                    old       = before if operation == 'update' else {},        # прежние
                ),
            ))

    # ------------------------------------------------------------------ события транзакции

    def _transaction_context(
        self,
        event_name : str,                  # место (TRANSACTION_EVENTS)
        table_def  : Any,                  # описание таблицы
        session    : Any,                  # сессия
        log        : _TransactionLog,      # журнал транзакции
    ) -> EventContext: # контекст действия транзакции
        """
        Строит контекст действия транзакции: строки таблицы из журнала.

        Args:
            event_name : (str) Место.
            table_def  : (TableDef) Описание.
            session    : (Session) Сессия.
            log        : (_TransactionLog) Журнал.

        Returns:
            (EventContext) Контекст.

        Example:
            >>> events._transaction_context('after_commit', PHOTOS, session, log).changes
            ()
        """
        return EventContext(
            event     = event_name,                 # место
            table     = table_def.name,             # таблица
            table_def = table_def,                  # описание
            session   = session,                    # сессия
            changes   = log.for_table(table_def),   # строки транзакции
        )

    def _before_commit(
        self,
        session : Any,   # коммитящаяся сессия
    ) -> None: # действия «перед коммитом»
        """
        Перед коммитом, по порядку (решение владельца 2026-11-01, разбор предела цикла):
        1) сброс в базу (журнал полон); 2) действия «перед коммитом» таблиц с изменёнными
        строками — **один раз** (в общем цикле со сборщиком пара действий может зацикливаться
        без конца); 3) сборщик мусора — последним (:meth:`_collect`); 4) журнал закрыт:
        кандидаты после уборки не проверяются — предупреждение после коммита (Р-15).
        Отказ или ошибка — исключение, коммит не состоится; повторный коммит той же
        транзакции без отката — снова ошибка.

        Точка сохранения (``begin_nested``) — не коммит транзакции: пропускается (Р-18).

        Args:
            session : (Session) Сессия.

        Raises:
            AppException: Отказ действия; ``TableEventError`` — другая ошибка, предел кругов
                сборщика, повторный коммит после ошибки.

        Example:
            >>> events._before_commit(session)
        """
        if session.in_nested_transaction(): # выпуск точки сохранения — транзакция идёт дальше
            return
        log = self._log(session)
        if log.phase == 'failed': # после ошибки уборки транзакцию нужно откатить
            raise TableEventError(
                "после ошибки обработки изменений транзакцию нужно откатить, а не коммитить снова",
            )
        try:
            session.flush()
            for table_def in log.tables():
                names = table_def.actions_for('before_commit')
                if names:
                    self._run(
                        names,
                        self._transaction_context('before_commit', table_def, session, log),
                    )
            log.phase = 'loop'
            self._collect(
                session,
                log,
            )
            log.phase = 'sealed'
        except BaseException:
            log.phase = 'failed'
            raise

    # ------------------------------------------------------------------ сборщик мусора

    def _collect(
        self,
        session : Any,               # коммитящаяся сессия
        log     : _TransactionLog,   # журнал транзакции
    ) -> None: # убирает неиспользуемые строки до неподвижной точки
        """
        Сборщик мусора: круг — сброс (удаления прошлого круга и их каскады дают новых
        кандидатов) → кандидаты, ещё не удалённые → проверка одним запросом на таблицу
        (строка есть и ссылок нет) → удаление через ORM (события срабатывают и у удаляемых).
        Кандидатов нет — неподвижная точка.

        Предел (решение владельца 2026-11-01): рабочих кругов не больше ``plan.limit``
        (глубина цепочки по схеме + 1); круг сверх глубины — предупреждение (схема учтена не
        полностью), сверх предела — ``TableEventError``, транзакция откатывается целиком
        (превысить точную границу можно только ошибкой в действиях — коммит сохранил бы её
        результат). Время, число удалений, повтор кандидатов не ограничиваются — законно
        растут; идут в подробности ошибки.

        Args:
            session : (Session) Сессия.
            log     : (_TransactionLog) Журнал.

        Raises:
            TableEventError: Предел кругов превышен (подробности — круги, кандидаты).

        Example:
            >>> events._collect(session, log)
        """
        plan = self.plan
        round_no = 0
        existing : Optional[set] = None
        while True:
            session.flush()
            batch = {
                table: {i: s for i, s in ids.items() if (table, i) not in log.gone}
                for table, ids in log.candidates.items()
            }
            batch = {table: ids for table, ids in batch.items() if ids}
            log.candidates = {}
            # рабочий круг — есть кандидаты или сессия снова изменена после сброса (чужое
            # изменение во время уборки: обработчики after_flush* и т. п.)
            dirty = bool(session.new or session.dirty or session.deleted)
            if not batch and not dirty:
                return
            round_no += 1
            if round_no > plan.limit:
                raise TableEventError(
                    "уборка ненужных записей не закончилась — сработала защита от "
                    "зацикливания; изменения не сохранены",
                    details = {
                        'место'                 : 'перед коммитом, сборщик мусора',
                        'предел кругов'         : plan.limit,
                        'глубина по схеме'      : plan.depth,
                        'круги'                 : log.rounds,
                        'кандидаты последнего'  : {t: sorted(ids)[:20] for t, ids in batch.items()},
                    },
                )
            if round_no > plan.depth:
                self.logger.warning(
                    f"сборщик мусора: круг {round_no} сверх глубины схемы {plan.depth} "
                    f"(кандидаты: { {t: sorted(ids)[:20] for t, ids in batch.items()} })"
                )
            if existing is None: # один раз за уборку: модель могли добавить без миграции
                existing = set(inspect(session.connection()).get_table_names())
            removed = 0
            for table in plan.order:
                ids = batch.get(table.name)
                if not ids:
                    continue
                doomed = self._unused(
                    session,
                    table,
                    list(ids),
                    existing,
                )
                removed += self._delete_rows(
                    session,
                    log,
                    table,
                    doomed,
                    {i: (round_no, ids[i]) for i in doomed},
                )
            log.rounds.append({
                'круг'      : round_no,                                         # номер
                'кандидаты' : {t: len(ids) for t, ids in batch.items()},       # сколько проверено
                'удалено'   : removed,                                          # сколько удалено
            })

    def _unused(
        self,
        session  : Any,          # сессия
        table    : Any,          # таблица «только используемые»
        ids      : List[Any],    # кандидаты
        existing : set,          # таблицы, существующие в базе
    ) -> List[Any]: # кандидаты, которые есть в базе и на которые никто не ссылается
        """
        Возвращает id кандидатов, которые есть в базе и на которые не ссылается ни один
        столбец схемы (``NOT EXISTS`` по всем внешним ключам на таблицу), — один запрос на
        порцию. Строку, уже удалённую другим путём (старая уборка, Р-7), запрос не вернёт.

        Args:
            session  : (Session) Сессия.
            table    : (Table) Таблица.
            ids      : (List[Any]) Кандидаты.
            existing : (set) Имена таблиц в базе.

        Returns:
            (List[Any]) Неиспользуемые id по возрастанию.

        Example:
            >>> events._unused(session, notes_table, [5, 7], existing)
            [7]
        """
        pk = list(table.primary_key.columns)[0]
        conditions = [~exists().where(column == pk) for column in self.plan.refs(table, existing)]
        result : List[Any] = []
        for part in _chunks(sorted(ids)):
            result.extend(
                session.scalars(
                    select(pk).where(pk.in_(part), *conditions),
                ),
            )
        return sorted(result)

    def _delete_rows(
        self,
        session : Any,               # сессия
        log     : _TransactionLog,   # журнал транзакции
        table   : Any,               # таблица «только используемые»
        ids     : List[Any],         # что удалить
        why     : Dict[Any, Any],    # id → (круг, источник) — для журнала
    ) -> int: # сколько удалено
        """
        Удаляет строки через ORM (события таблицы срабатывают). Перед удалением —
        ``expire`` обратных коллекций «один ко многим» (у заметки — приёмы): иначе
        устаревшая загруженная коллекция при удалении обнулила бы ссылку строки, уже
        переведённой на другую цель (Р-17). Удаление — в ``no_autoflush``; сбросит его
        следующий круг. Каждая строка — в журнал уборки (пишется после коммита, Р-11).

        Args:
            session : (Session) Сессия.
            log     : (_TransactionLog) Журнал.
            table   : (Table) Таблица.
            ids     : (List[Any]) Id.
            why     : (Dict[Any, Any]) Круг и источник по id.

        Returns:
            (int) Число удалённых строк.

        Example:
            >>> events._delete_rows(session, log, notes_table, [7], {7: (1, None)})
            1
        """
        if not ids:
            return 0
        mapper = self.plan.used[table]
        pk = mapper.primary_key[0]
        reverse = [rel.key for rel in mapper.relationships if rel.direction is ONETOMANY]
        count = 0
        with session.no_autoflush:
            for part in _chunks(ids):
                for obj in session.scalars(select(mapper.class_).where(pk.in_(part))):
                    if reverse:
                        session.expire(
                            obj,
                            reverse,   # обратные коллекции — перечитать (Р-17)
                        )
                    session.delete(obj)
                    row_id = _primary_key(mapper, obj)
                    round_no, source = why.get(row_id, (0, None))
                    log.collected.append((table.name, row_id, round_no, source))
                    count += 1
        return count

    def find_unused(
        self,
        session : Any,   # сессия (чтение)
    ) -> Dict[str, List[Any]]: # таблица → неиспользуемые id (полная проверка)
        """
        Полная проверка (для кнопки, М19): все строки таблиц «только используемые», на
        которые никто не ссылается, — в том числе ставшие такими давно или созданные и не
        привязанные (Р-13). Только чтение: показать пользователю список «будет удалено»
        (Р-11), удалить — :meth:`delete_unused` после подтверждения.

        Args:
            session : (Session) Сессия.

        Returns:
            (Dict[str, List[Any]]) Таблица → id по возрастанию (только непустые).

        Example:
            >>> db.table_events.find_unused(session)
            {'appointments_notes': [3, 17]}
        """
        existing = set(inspect(session.connection()).get_table_names())
        result : Dict[str, List[Any]] = {}
        for table in self.plan.order:
            if table.name not in existing:
                continue
            pk = list(table.primary_key.columns)[0]
            conditions = [~exists().where(column == pk) for column in self.plan.refs(table, existing)]
            ids = sorted(session.scalars(select(pk).where(*conditions)))
            if ids:
                result[table.name] = ids
        return result

    def delete_unused(
        self,
        session  : Any,                    # сессия транзакции удаления
        expected : Dict[str, List[Any]],   # подтверждённый список (find_unused)
    ) -> Dict[str, List[Any]]: # что удалено
        """
        Удаляет подтверждённые пользователем неиспользуемые строки (результат
        :meth:`find_unused`): только те, что и сейчас без ссылок (за время показа списка их
        могли привязать). Через ORM — события таблиц срабатывают; освобождённые этим
        удалением строки соберёт обычная уборка при коммите. Каждая строка — в журнал после
        коммита (Р-11). Коммит — у вызывающего (``session_scope``).

        Args:
            session  : (Session) Сессия.
            expected : (Dict[str, List[Any]]) Таблица → id.

        Returns:
            (Dict[str, List[Any]]) Таблица → удалённые id (только непустые).

        Raises:
            ValueError: Таблица — не «только используемые».

        Example:
            >>> with db.session_scope() as session:
            ...     db.table_events.delete_unused(session, {'appointments_notes': [3, 17]})
            {'appointments_notes': [3, 17]}
        """
        by_name = {table.name: table for table in self.plan.order}
        unknown = [name for name in expected if name not in by_name]
        if unknown:
            raise ValueError(f"не таблицы «только используемые»: {', '.join(unknown)}")
        log = self._log(session)
        existing = set(inspect(session.connection()).get_table_names())
        result : Dict[str, List[Any]] = {}
        for name, ids in expected.items():
            table = by_name[name]
            doomed = self._unused(
                session,
                table,
                list(ids),
                existing,
            )
            self._delete_rows(
                session,
                log,
                table,
                doomed,
                {i: (0, 'полная проверка') for i in doomed},
            )
            if doomed:
                result[name] = doomed
        return result

    def _log_collected(
        self,
        log : _TransactionLog,   # журнал закоммиченной транзакции
    ) -> None: # строки уборки — в журнал (Р-11)
        """
        Пишет в журнал каждую убранную строку закоммиченной транзакции (Р-11): что удалено и
        почему — какое изменение убрало последнюю ссылку, круг; без текстов строк (личные
        данные). Поздние кандидаты (после уборки, Р-15) — предупреждение.

        Args:
            log : (_TransactionLog) Журнал.

        Example:
            >>> events._log_collected(log)
        """
        if not log.collected and not log.late:
            return
        self._commits += 1
        for table, row_id, round_no, source in log.collected:
            if isinstance(source, tuple):
                src_table, key, src_id, operation = source
                reason = (
                    f"последнюю ссылку убрало {'удаление' if operation == 'delete' else 'изменение'} "
                    f"{src_table} id={src_id} ({key}), круг {round_no}"
                )
            elif source:
                reason = str(source)
            else:
                reason = 'нет ссылок'
            self.logger.info(
                f"Сборщик мусора (коммит №{self._commits}): удалена неиспользуемая строка "
                f"{table} id={row_id} — {reason}"
            )
        for table, row_id, source in log.late:
            self.logger.warning(
                f"Сборщик мусора (коммит №{self._commits}): ссылку на {table} id={row_id} убрали "
                f"после уборки ({source}) — строка не проверена, её найдёт полная проверка"
            )

    def _after_commit(
        self,
        session : Any,   # закоммиченная сессия
    ) -> None: # действия «после коммита»
        """
        После коммита: выполняет действия «после коммита» таблиц с изменёнными строками;
        журнал транзакции забирается (следующая транзакция — с пустого). Ошибки — в журнал.
        Выпуск точки сохранения пропускается (Р-18): данные ещё не закоммичены.

        Args:
            session : (Session) Сессия.

        Example:
            >>> events._after_commit(session)
        """
        if session.in_nested_transaction():
            return
        log = self._take_log(session)
        self._log_collected(
            log,   # строки уборки — в журнал (Р-11)
        )
        for table_def in log.tables():
            names = table_def.actions_for('after_commit')
            if names:
                self._run_logged(
                    names,
                    self._transaction_context('after_commit', table_def, session, log),
                )

    def _after_rollback(
        self,
        session : Any,   # откатившаяся сессия
    ) -> None: # действия «после отката»
        """
        После отката: выполняет действия «после отката» таблиц с изменёнными (и теперь
        отменёнными) строками; журнал забирается. Ошибки — в журнал.

        Откат точки сохранения пропускается (Р-18): транзакция идёт дальше. Её строки
        остаются в журнале — точек сохранения ORM в программе нет, учёт по ним не ведётся.

        Args:
            session : (Session) Сессия.

        Example:
            >>> events._after_rollback(session)
        """
        if session.in_nested_transaction():
            return
        self._run_rollback_actions(
            session,
            self._take_log(session),
        )

    def _run_rollback_actions(
        self,
        session : Any,               # сессия
        log     : _TransactionLog,   # журнал отменённой транзакции
    ) -> None: # действия «после отката» по журналу
        """
        Выполняет действия «после отката» таблиц, строки которых есть в журнале отменённой
        транзакции. Ошибки — в журнал.

        Args:
            session : (Session) Сессия.
            log     : (_TransactionLog) Журнал.

        Example:
            >>> events._run_rollback_actions(session, log)
        """
        for table_def in log.tables():
            names = table_def.actions_for('after_rollback')
            if names:
                self._run_logged(
                    names,
                    self._transaction_context('after_rollback', table_def, session, log),
                )

    def _after_transaction_end(
        self,
        session     : Any,   # сессия
        transaction : Any,   # закончившаяся транзакция
    ) -> None: # закрывает журнал транзакции, брошенной без коммита и отката
        """
        Конец корневой транзакции: журнал, который не забрали ни коммит, ни откат, —
        транзакцию закрыли без них (``close()``, ``Session.remove()``), изменения отброшены.
        Журнал забирается и обрабатывается как откат: иначе его строки достались бы
        следующей транзакции сессии (Р-16; ``close()`` вызывает только это событие).

        Внутренние транзакции (сброс, точки сохранения) пропускаются.

        Args:
            session     : (Session) Сессия.
            transaction : (SessionTransaction) Закончившаяся транзакция.

        Example:
            >>> events._after_transaction_end(session, session.get_transaction())
        """
        if transaction.parent is not None or transaction.nested:
            return
        log = session.info.get(_TX_KEY)
        if log is None or not log.belongs_to(transaction):
            return
        session.info.pop(_TX_KEY, None)
        if log.changes:
            self.logger.warning(
                f"транзакция закрыта без коммита и отката — изменения ({len(log.changes)} строк) "
                f"отброшены, выполняются действия «после отката»"
            )
        self._run_rollback_actions(
            session,
            log,
        )


_ROW_LISTENERS_INSTALLED : bool = False   # обработчики событий строк стоят (один раз на процесс)


def _row_listener(
    event_name : str,   # место (ROW_EVENTS)
) -> Callable[[Any, Any, Any], None]: # обработчик события Mapper
    """
    Создаёт обработчик события строки ``Mapper``: находит диспетчер базы в ``session.info``
    и передаёт ему событие; сессии без диспетчера — ничего.

    Args:
        event_name : (str) Место.

    Returns:
        (Callable) Обработчик ``handler(mapper, connection, target)``.

    Example:
        >>> event.listen(
        ...     Mapper,                          # все модели
        ...     'after_delete',                  # событие
        ...     _row_listener('after_delete'),   # обработчик
        ... )
    """
    def handler(
        mapper     : Any,   # Mapper модели
        connection : Any,   # соединение flush
        target     : Any,   # объект строки
    ) -> None: # передаёт событие диспетчеру базы
        """Передаёт событие строки диспетчеру базы объекта (если он есть)."""
        session = object_session(target)
        dispatcher = session.info.get(INFO_KEY) if session is not None else None
        if dispatcher is not None:
            dispatcher.on_row(
                event_name,
                mapper,
                connection,
                target,
                session,
            )

    return handler


def _install_row_listeners() -> None: # ставит обработчики событий строк (один раз на процесс)
    """
    Ставит обработчики событий строк на класс ``Mapper`` (все модели процесса) — один раз
    на процесс: базы и диспетчеры разные, обработчики общие (диспетчер — из
    ``session.info``).

    Example:
        >>> _install_row_listeners()
    """
    global _ROW_LISTENERS_INSTALLED
    if _ROW_LISTENERS_INSTALLED:
        return
    for event_name in ROW_EVENTS:
        event.listen(
            Mapper,                          # все модели
            event_name,                      # событие строки
            _row_listener(event_name),       # обработчик
        )
    _ROW_LISTENERS_INSTALLED = True


__all__ = [
    'INFO_KEY', 'EventContext', 'RowChange', 'TableEvents',
    'register_action', 'unregister_action', 'registered_actions',
    'table_def_of', 'check_action_names',
]
