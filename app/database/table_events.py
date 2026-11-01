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
  Живёт в ``session.info`` и очищается и при коммите, и при откате (сессия —
  ``scoped_session``, живёт дольше транзакции; как ТД-9).

Ошибки (Р-12): действие, отказывающее в операции, выбрасывает своё исключение приложения
(``AppException``) — оно проходит как есть, ``flush`` / коммит падает, ``session_scope``
откатывает всю транзакцию; другое исключение действия оборачивается в
``TableEventError`` (таблица, место, действие, id — в ``details``). После коммита / отката
откатывать уже нечего: ошибки действий там только пишутся в журнал (Р-5).

Ограничения SQLAlchemy: действия строк выполняются ВНУТРИ flush — менять сессию (``add``,
``delete``) в них нельзя, можно только читать через ``ctx.connection`` и запоминать;
изменения данных — в «перед коммитом». Изменения мимо ORM (``query().delete()``, сырой
SQL) событий не вызывают — в коде их нет (тест ``tests/test_database_shema/test_orm_only.py``, Р-1).

Example:
    >>> @register_action('log_removal')
    ... def log_removal(ctx: EventContext) -> None:
    ...     print(ctx.table, ctx.event)
    >>> # app/schema/clinic.py: TableDef(..., events=(on('after_delete', 'log_removal'),))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Mapper, object_session

from app.exceptions import AppException, TableEventError
from app.schema.define import ROW_EVENTS, TABLE_EVENTS, TRANSACTION_EVENTS
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


class _TransactionLog:
    """
    Журнал текущей транзакции сессии: изменённые строки таблиц с действиями транзакции и
    прежние значения, снятые в «перед изменением / удалением».

    Example:
        >>> log = _TransactionLog()
        >>> log.changes
        []
    """

    def __init__(self) -> None:
        """
        Создаёт пустой журнал.

        Example:
            >>> _TransactionLog().pending_old
            {}
        """
        self.changes     : List[Tuple[Any, RowChange]] = []          # (описание, строка)
        self.pending_old : Dict[Tuple[str, Any], Dict[str, Any]] = {}  # (таблица, ключ) → значения до

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
        _install_row_listeners()

    def listen(
        self,
        session_factory : Any,   # фабрика сессий (sessionmaker) с info={INFO_KEY: self}
    ) -> None: # вешает события сессии на фабрику (один раз)
        """
        Вешает обработчики ``before_commit``, ``after_commit``, ``after_rollback`` на фабрику
        сессий; повторный вызов для той же фабрики ничего не делает (Р-8).

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
        session_factory._table_events_listening = True

    # ------------------------------------------------------------------ журнал транзакции

    @staticmethod
    def _log(
        session : Any,   # сессия
    ) -> _TransactionLog: # журнал текущей транзакции (создаётся при первом обращении)
        """
        Возвращает журнал текущей транзакции сессии (создаёт при первом обращении).

        Args:
            session : (Session) Сессия.

        Returns:
            (_TransactionLog) Журнал.

        Example:
            >>> TableEvents._log(session).changes
            []
        """
        log = session.info.get(_TX_KEY)
        if log is None:
            log = session.info[_TX_KEY] = _TransactionLog()
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
        удалением»), выполняет действия места, записывает строку в журнал транзакции («после
        …», только таблицы с действиями транзакции).

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
        if table_def is None:
            return
        actions = table_def.actions_for(event_name)
        journal = _has_transaction_actions(table_def)
        if not actions and not journal:
            return

        log = self._log(session)
        operation = event_name.split('_', 1)[1]               # insert / update / delete
        row_key = (table_def.name, _primary_key(mapper, target))
        old : Dict[str, Any] = {}

        if event_name == 'before_update':
            old = _old_values(
                mapper,
                connection,
                target,
            )
            log.pending_old[row_key] = old
        elif event_name == 'before_delete' and journal: # строка до удаления — для «после коммита»
            log.pending_old[row_key] = _row_from_db(
                mapper,
                connection,
                target,
            )
        elif event_name == 'after_update':
            old = log.pending_old.get(row_key, {})

        if actions:
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

        if journal and event_name.startswith('after_'):
            before = log.pending_old.pop(row_key, {})
            values = before if operation == 'delete' else _loaded_values(mapper, target)
            log.changes.append((
                table_def,
                RowChange(
                    table     = table_def.name,                                 # таблица
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
        Перед коммитом: сбрасывает изменения в базу (журнал полон) и выполняет действия
        «перед коммитом» таблиц, у которых в транзакции есть изменённые строки. Действия
        могут менять данные — их сбросит коммит; отказ — исключение, коммит не состоится.

        Args:
            session : (Session) Сессия.

        Raises:
            AppException: Отказ действия; ``TableEventError`` — другая ошибка.

        Example:
            >>> events._before_commit(session)
        """
        session.flush()
        log = self._log(session)
        for table_def in log.tables():
            names = table_def.actions_for('before_commit')
            if names:
                self._run(
                    names,
                    self._transaction_context('before_commit', table_def, session, log),
                )

    def _after_commit(
        self,
        session : Any,   # закоммиченная сессия
    ) -> None: # действия «после коммита»
        """
        После коммита: выполняет действия «после коммита» таблиц с изменёнными строками;
        журнал транзакции забирается (следующая транзакция — с пустого). Ошибки — в журнал.

        Args:
            session : (Session) Сессия.

        Example:
            >>> events._after_commit(session)
        """
        log = self._take_log(session)
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

        Args:
            session : (Session) Сессия.

        Example:
            >>> events._after_rollback(session)
        """
        log = self._take_log(session)
        for table_def in log.tables():
            names = table_def.actions_for('after_rollback')
            if names:
                self._run_logged(
                    names,
                    self._transaction_context('after_rollback', table_def, session, log),
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
