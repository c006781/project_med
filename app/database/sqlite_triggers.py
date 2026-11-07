# app/database/sqlite_triggers.py

"""
Встроенные триггеры SQLite: чтение из базы, сравнение с описанием, проверка, сохранение при
пересборке таблицы (Ф1.6.7д; решение владельца 2026-10-31).

Описание триггера — ``app/schema/define.py`` (``TableDef(triggers=(trigger(...),))``); модель
несёт его текст в ``Table.info[TRIGGERS_INFO]``. Схема, собранная миграциями в памяти, несёт
там же текст из базы (``attach_stored_triggers``), поэтому оба образца сравниваются с базой
одинаково.

Сам Alembic триггеров не видит. Модуль подключает к нему (при импорте, на весь процесс):
    * сравнение — отличия ``('add_trigger', таблица, имя, текст)``,
      ``('remove_trigger', таблица, имя, текст)``, ``('modify_trigger', таблица, имя, старый,
      новый)`` в ``compare_metadata``, а значит в ``schema_differences``,
      ``pending_model_changes``, автодостройке;
    * запись в файл миграции — ``TriggerChangeOp``.

Пересборка таблицы SQLite (``batch_alter_table``) удаляет её триггеры, а триггер другой
таблицы, упоминающий пересобираемую, роняет переименование: миграция оборачивает пересборку
в ``keep_triggers`` (устройство — ``IMPLEMENTATION.md`` §12).

Example:
    >>> from app.database.sqlite_triggers import read_triggers
    >>> read_triggers(connection)
    {}
"""

from __future__ import annotations

import contextlib
import itertools
import re
from typing import Any, Dict, Iterable, Iterator, List, NamedTuple, Optional, Tuple

from alembic import op
from alembic.autogenerate import comparators, renderers
from alembic.operations import ops
from alembic.util import DispatchPriority, PriorityDispatchResult
import sqlalchemy as sa

from app.schema.define import TRIGGERS_INFO

# Виды отличий триггеров. Все три данных не меняют и обратимы (в файле миграции есть оба текста).
ADD_TRIGGER    : str = 'add_trigger'      # в образце есть, в базе нет
REMOVE_TRIGGER : str = 'remove_trigger'   # в базе есть, в образце нет
MODIFY_TRIGGER : str = 'modify_trigger'   # текст различается
TRIGGER_KINDS  : Tuple[str, ...] = (ADD_TRIGGER, REMOVE_TRIGGER, MODIFY_TRIGGER)

# Строковые значения SQL не сжимаются: 'а  б' и 'а б' — разный текст правила
_SQL_LITERAL_RE = re.compile(r"""('(?:[^']|'')*'|"(?:[^"]|"")*")""")

# Операция в тексте CREATE TRIGGER (перед ней всегда момент; имя может быть словом update)
_TRIGGER_OPERATION_RE = re.compile(
    r'\b(?:BEFORE|AFTER|INSTEAD\s+OF)\s+(INSERT|UPDATE|DELETE)\b',   # BEFORE DELETE …
    flags   =   re.IGNORECASE,                                      # регистр как написан
)

# Номер проверочного запроса. Модуль sqlite3 кеширует запросы по тексту, а EXPLAIN не сверяет
# версию схемы: повтор того же текста после DDL показал бы план до изменения и ошибку бы не нашёл
_explain_counter = itertools.count(1)


class StoredTrigger(NamedTuple):
    """
    Триггер и его таблица.

    Attributes:
        table : (str) Имя таблицы.
        sql   : (str) Текст ``CREATE TRIGGER``.

    Example:
        >>> StoredTrigger(
        ...     'patients',                 # таблица
        ...     'CREATE TRIGGER "t" ...',   # текст
        ... ).table
        'patients'
    """

    table : str
    sql   : str


def normalize_sql(
    sql : str,   # текст CREATE TRIGGER
) -> str: # текст для сравнения: пробелы вне строк сжаты
    """
    Приводит текст триггера к виду для сравнения: подряд идущие пробелы и переводы строк вне
    строковых значений — один пробел, по краям и перед завершающей ``;`` — ничего.

    Регистр и кавычки не приводятся: другой текст считается отличием, а замена триггера
    данных не меняет.

    Args:
        sql : (str) Текст ``CREATE TRIGGER``.

    Returns:
        (str) Текст для сравнения.

    Example:
        >>> normalize_sql(
        ...     "CREATE TRIGGER t\\n  BEFORE DELETE ON a BEGIN SELECT 'x  y'; END;",   # текст
        ... )
        "CREATE TRIGGER t BEFORE DELETE ON a BEGIN SELECT 'x  y'; END"
    """
    parts = _SQL_LITERAL_RE.split(sql.strip().rstrip(';'))
    # нечётные части split с группой — сами строковые значения
    return ''.join(
        part if index % 2 else re.sub(r'\s+', ' ', part)
        for index, part in enumerate(parts)
    ).strip()


def read_triggers(
    connection : Any,   # соединение (можно внутри транзакции)
) -> Dict[str, StoredTrigger]: # триггеры базы по именам
    """
    Читает триггеры базы из ``sqlite_master``. Не SQLite — пусто.

    Args:
        connection : (Connection) Соединение SQLAlchemy.

    Returns:
        (Dict[str, StoredTrigger]) «имя → таблица и текст».

    Example:
        >>> read_triggers(connection)
        {'trg_a': StoredTrigger(table='patients', sql='CREATE TRIGGER "trg_a" ...')}
    """
    if connection.dialect.name != 'sqlite':
        return {}
    rows = connection.exec_driver_sql(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name",
    ).fetchall()
    return {
        name: StoredTrigger(
            table,   # таблица
            sql,     # текст
        )
        for name, table, sql in rows
    }


def described_triggers(
    tables : Iterable[sa.Table],   # таблицы образца (модели или схема из базы)
) -> Dict[str, StoredTrigger]: # триггеры образца по именам
    """
    Собирает триггеры таблиц образца из ``Table.info[TRIGGERS_INFO]``.

    Args:
        tables : (Iterable[Table]) Таблицы.

    Returns:
        (Dict[str, StoredTrigger]) «имя → таблица и текст». Имя на двух таблицах здесь не
        различить — такое описание отвергает ``definition_errors``.

    Example:
        >>> described_triggers(
        ...     Base.metadata.tables.values(),   # таблицы моделей
        ... )
        {}
    """
    result : Dict[str, StoredTrigger] = {}
    for table in tables:
        for name, sql in table.info.get(TRIGGERS_INFO, {}).items():
            result[name] = StoredTrigger(
                table.name,   # таблица
                sql,          # текст
            )
    return result


def attach_stored_triggers(
    connection : Any,          # соединение базы, из которой собрана схема
    metadata   : sa.MetaData,  # схема, собранная reflect
) -> None: # записывает в таблицы схемы триггеры базы
    """
    Записывает триггеры базы в ``Table.info`` схемы, собранной ``reflect`` (он их не читает):
    так схема последней миграции сравнивается с базой, как модели. Таблицы без триггеров
    ``info`` не получают.

    Args:
        connection : (Connection) Соединение базы.
        metadata   : (MetaData) Схема, меняется на месте.

    Example:
        >>> attach_stored_triggers(
        ...     connection,   # соединение
        ...     metadata,     # схема из этой базы
        ... )
    """
    for name, stored in read_triggers(connection).items():
        table = metadata.tables.get(stored.table)
        if table is not None: # служебную таблицу в схеме могли уже убрать
            table.info.setdefault(TRIGGERS_INFO, {})[name] = stored.sql


def _explain_statement(
    connection : Any,   # соединение
    table      : str,   # таблица
    operation  : str,   # INSERT / UPDATE / DELETE
) -> str: # запрос, компиляция которого проверяет триггеры таблицы
    """
    Строит запрос ``EXPLAIN``: SQLite компилирует вместе с ним триггеры операции, и опечатка в
    таблице или столбце видна без выполнения; строки не меняются. Для изменения названы все
    столбцы — чтобы попали и триггеры ``UPDATE OF``. В конце — уникальный комментарий
    (см. ``_explain_counter``).

    Args:
        connection : (Connection) Соединение.
        table      : (str) Таблица.
        operation  : (str) ``INSERT``, ``UPDATE`` или ``DELETE``.

    Returns:
        (str) Запрос.

    Example:
        >>> _explain_statement(
        ...     connection,   # соединение
        ...     'patients',   # таблица
        ...     'DELETE',     # операция
        ... )
        'EXPLAIN DELETE FROM "patients" /* 1 */'
    """
    quoted = _quote(table)
    mark   = f'/* {next(_explain_counter)} */'
    if operation == 'INSERT':
        return f'EXPLAIN INSERT INTO {quoted} DEFAULT VALUES {mark}'
    if operation == 'DELETE':
        return f'EXPLAIN DELETE FROM {quoted} {mark}'
    rows = connection.exec_driver_sql(f'PRAGMA table_info({quoted}) {mark}').fetchall()
    columns = ', '.join(f'{_quote(row[1])} = {_quote(row[1])}' for row in rows)
    return f'EXPLAIN UPDATE {quoted} SET {columns} {mark}'


def _quote(
    name : str,   # имя таблицы, столбца, триггера
) -> str: # имя в двойных кавычках
    """
    Заключает имя SQL в двойные кавычки.

    Args:
        name : (str) Имя.

    Returns:
        (str) Имя в кавычках.

    Example:
        >>> _quote(
        ...     'patients',   # имя
        ... )
        '"patients"'
    """
    doubled = name.replace('"', '""')
    return f'"{doubled}"'


def _trigger_operations(
    sql : str,   # текст CREATE TRIGGER
) -> List[str]: # операции, при которых срабатывает триггер
    """
    Определяет операцию триггера по тексту: слово после ``BEFORE`` / ``AFTER`` / ``INSTEAD OF``
    (имя триггера само может быть словом ``update``). Сторонний триггер без этих слов — все три
    операции: лишняя проверка ничего не портит.

    Args:
        sql : (str) Текст ``CREATE TRIGGER``.

    Returns:
        (List[str]) Операции.

    Example:
        >>> _trigger_operations(
        ...     'CREATE TRIGGER "update" BEFORE DELETE ON "a" BEGIN SELECT 1; END',   # текст
        ... )
        ['DELETE']
    """
    match = _TRIGGER_OPERATION_RE.search(sql)
    return [match.group(1).upper()] if match else ['INSERT', 'UPDATE', 'DELETE']


def trigger_errors(
    connection : Any,   # соединение (можно внутри транзакции)
) -> List[str]: # ошибки компиляции триггеров базы
    """
    Компилирует (без выполнения) триггеры базы и возвращает ошибки: SQLite принимает
    ``CREATE TRIGGER`` с несуществующей таблицей или столбцом и падает только при срабатывании.
    Заодно видно, что миграция удалила столбец или таблицу, которые нужны триггеру.

    Args:
        connection : (Connection) Соединение.

    Returns:
        (List[str]) Строки «таблица, операция: ошибка SQLite» (пусто — всё компилируется).

    Example:
        >>> trigger_errors(connection)
        []
    """
    errors : List[str] = []
    checks = {
        (stored.table, operation)
        for stored in read_triggers(connection).values()
        for operation in _trigger_operations(stored.sql)
    }
    for table, operation in sorted(checks):
        statement = _explain_statement(
            connection,   # соединение
            table,        # таблица
            operation,    # операция
        )
        try:
            connection.exec_driver_sql(statement).fetchall()
        except sa.exc.DBAPIError as exc:
            errors.append(f"{table}, {operation}: {exc.orig}")
    return errors


def definition_errors(
    metadata : sa.MetaData,   # модели
) -> List[str]: # ошибки описания триггеров
    """
    Проверяет описание триггеров во временной базе в памяти: повтор имени на разных таблицах
    (имена триггеров едины на базу), синтаксис, существование таблиц и столбцов. Нет ни одного
    триггера — база не создаётся и моделей не касается.

    Args:
        metadata : (MetaData) Модели.

    Returns:
        (List[str]) Строки «таблица.триггер: ошибка» (пусто — описание верно).

    Example:
        >>> definition_errors(Base.metadata)
        []
    """
    owners : Dict[str, List[str]] = {}
    for table in metadata.tables.values():
        for name in table.info.get(TRIGGERS_INFO, {}):
            owners.setdefault(name, []).append(table.name)
    if not owners:
        return []
    errors = [
        f"{', '.join(tables)}: имя триггера {name} повторяется (имена едины на всю базу)"
        for name, tables in owners.items()
        if len(tables) > 1
    ]
    reference = sa.create_engine('sqlite://')
    try:
        with reference.begin() as connection:
            metadata.create_all(connection)
            for name, stored in described_triggers(metadata.tables.values()).items():
                # по одному: ошибка компиляции SQLite триггер не называет
                problem = _single_trigger_error(
                    connection,   # база в памяти
                    name,         # имя
                    stored,       # таблица и текст
                )
                if problem:
                    errors.append(f"{stored.table}.{name}: {problem}")
    finally:
        reference.dispose()
    return errors


def _single_trigger_error(
    connection : Any,             # соединение базы в памяти
    name       : str,             # имя триггера
    stored     : StoredTrigger,   # таблица и текст
) -> Optional[str]: # текст ошибки SQLite или None
    """
    Создаёт один триггер, компилирует его операцию и удаляет.

    Args:
        connection : (Connection) Соединение базы в памяти.
        name       : (str) Имя триггера.
        stored     : (StoredTrigger) Таблица и текст.

    Returns:
        (str/None) Ошибка SQLite; None — триггер верен.

    Example:
        >>> _single_trigger_error(
        ...     connection,                                   # база в памяти
        ...     't',                                          # имя
        ...     StoredTrigger('a', 'CREATE TRIGGER "t" ...'),  # таблица и текст
        ... ) is None
        True
    """
    try:
        connection.exec_driver_sql(stored.sql)
    except sa.exc.DBAPIError as exc:
        return str(exc.orig)
    try:
        for operation in _trigger_operations(stored.sql):
            statement = _explain_statement(
                connection,     # соединение
                stored.table,   # таблица
                operation,      # операция
            )
            connection.exec_driver_sql(statement).fetchall()
    except sa.exc.DBAPIError as exc:
        return str(exc.orig)
    finally:
        connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS {_quote(name)}')
    return None


def drop_trigger_sql(
    name : str,   # имя триггера
) -> str: # текст DROP TRIGGER IF EXISTS
    """
    Возвращает команду удаления триггера (``IF EXISTS``: на базе его могло не быть).

    Args:
        name : (str) Имя.

    Returns:
        (str) Команда SQL.

    Example:
        >>> drop_trigger_sql(
        ...     'trg_a',   # имя
        ... )
        'DROP TRIGGER IF EXISTS "trg_a"'
    """
    return f'DROP TRIGGER IF EXISTS {_quote(name)}'


@contextlib.contextmanager
def keep_triggers(
    connection : Any = None,   # соединение; None — соединение текущей миграции
) -> Iterator[None]: # контекст пересборки таблиц в миграции
    """
    Сохраняет триггеры базы на время пересборки таблиц в миграции.

    Пересборка SQLite (``batch_alter_table``: новая таблица → перенос → удаление старой →
    переименование) теряет триггеры таблицы молча; а триггер ДРУГОЙ таблицы, упоминающий
    пересобираемую, роняет переименование («error in trigger …: no such table»). Поэтому на
    входе все триггеры базы снимаются, на выходе создаются заново с прежним текстом — кроме
    триггеров таблиц, удалённых в блоке, и созданных в блоке заново под тем же именем.

    Текст берётся из самой базы: миграция не зависит от текущего описания. Убрать или
    изменить триггер — командой после блока. Внутри блока триггеры не работают (перенос
    данных их не вызывает). Нужный триггеру столбец удалён в блоке — ``_upgrade`` увидит это
    проверкой ``trigger_errors`` и откатит миграцию. При ошибке в блоке триггеры не
    возвращаются — откатывается вся транзакция миграции.

    Args:
        connection : (Connection/None) Соединение; None — ``op.get_bind()`` текущей миграции.

    Example:
        >>> with keep_triggers():
        ...     with op.batch_alter_table(
        ...         'photos',                # таблица
        ...         recreate    =   'always',  # пересборка
        ...     ) as batch:
        ...         batch.drop_column('description')
    """
    bind  = connection if connection is not None else op.get_bind()
    saved = read_triggers(bind)
    for name in saved:
        bind.exec_driver_sql(drop_trigger_sql(name))
    yield
    tables = {
        row[0]
        for row in bind.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    current = read_triggers(bind)
    for name, stored in saved.items():
        if stored.table in tables and name not in current:
            bind.exec_driver_sql(stored.sql)


def apply_trigger_diff(
    connection : Any,     # соединение (в транзакции)
    item       : tuple,   # отличие ADD_TRIGGER / MODIFY_TRIGGER
) -> None: # приводит триггер базы к тексту образца
    """
    Приводит триггер базы к тексту образца: снимает прежний, если есть, и создаёт.

    Args:
        connection : (Connection) Соединение.
        item       : (tuple) Отличие: новый текст — последний элемент.

    Example:
        >>> apply_trigger_diff(
        ...     connection,                                                  # соединение
        ...     ('add_trigger', 'patients', 'trg_a', 'CREATE TRIGGER ...'),  # отличие
        ... )
    """
    connection.exec_driver_sql(drop_trigger_sql(item[2]))
    connection.exec_driver_sql(item[-1])


class TriggerChangeOp(ops.MigrateOperation):
    """
    Изменение триггера в автоматической миграции: ``old`` → ``new``, None — триггера нет.

    Args:
        table : (str) Таблица.
        name  : (str) Имя триггера.
        old   : (str/None) Текст до изменения.
        new   : (str/None) Текст после изменения.

    Example:
        >>> TriggerChangeOp(
        ...     'patients',                 # таблица
        ...     'trg_a',                    # имя
        ...     None,                       # не было
        ...     'CREATE TRIGGER "trg_a"',   # стало
        ... ).to_diff_tuple()[0]
        'add_trigger'
    """

    def __init__(
        self,
        table : str,             # таблица
        name  : str,             # имя триггера
        old   : Optional[str],   # текст до; None — не было
        new   : Optional[str],   # текст после; None — не будет
    ) -> None: # запоминает изменение
        self.table = table
        self.name  = name
        self.old   = old
        self.new   = new

    def reverse(self) -> 'TriggerChangeOp': # обратное изменение (для downgrade)
        """
        Возвращает обратное изменение — для ``downgrade``.

        Returns:
            (TriggerChangeOp) Изменение ``new`` → ``old``.

        Example:
            >>> TriggerChangeOp('t', 'a', None, 'x').reverse().to_diff_tuple()
            ('remove_trigger', 't', 'a', 'x')
        """
        return TriggerChangeOp(
            self.table,   # таблица
            self.name,    # имя
            self.new,     # было
            self.old,     # стало
        )

    def to_diff_tuple(self) -> tuple: # отличие в виде записи compare_metadata
        """
        Возвращает отличие в виде записи ``compare_metadata``.

        Returns:
            (tuple) ``('add_trigger', таблица, имя, текст)``,
            ``('remove_trigger', таблица, имя, текст)`` или
            ``('modify_trigger', таблица, имя, старый, новый)``.

        Example:
            >>> TriggerChangeOp('t', 'a', 'x', 'y').to_diff_tuple()
            ('modify_trigger', 't', 'a', 'x', 'y')
        """
        if self.old is None:
            return (ADD_TRIGGER, self.table, self.name, self.new)
        if self.new is None:
            return (REMOVE_TRIGGER, self.table, self.name, self.old)
        return (MODIFY_TRIGGER, self.table, self.name, self.old, self.new)


@comparators.dispatch_for(
    'schema',                           # уровень схемы
    priority    =   DispatchPriority.LAST,   # после таблиц: триггер новой таблицы — после неё
)
def _compare_triggers(
    autogen_context : Any,   # контекст autogenerate
    upgrade_ops     : Any,   # куда добавить изменения
    schemas         : Any,   # схемы (в SQLite одна)
) -> PriorityDispatchResult: # результат для диспетчера Alembic
    """
    Сравнивает триггеры образца с базой и добавляет изменения в ``upgrade_ops``.

    Таблица вне образца (посторонняя или удаляемая) не рассматривается: её триггеры уйдут вместе
    с ней или не наши. Триггер таблицы образца, которого в образце нет, — ``remove_trigger``:
    генератор удалит его файлом миграции, автодостройка оставит как есть.

    Args:
        autogen_context : (AutogenContext) Контекст autogenerate.
        upgrade_ops     : (UpgradeOps) Куда добавить изменения.
        schemas         : (set) Схемы (не используются).

    Returns:
        (PriorityDispatchResult) ``CONTINUE`` — сравнение идёт дальше.

    Example:
        >>> compare_metadata(context, metadata)   # вызывает Alembic
        [('add_trigger', 'patients', 'trg_a', 'CREATE TRIGGER ...')]
    """
    connection = autogen_context.connection
    if connection is None or connection.dialect.name != 'sqlite':
        return PriorityDispatchResult.CONTINUE
    tables    = autogen_context.table_key_to_table
    stored    = read_triggers(connection)
    described = described_triggers(tables.values())
    for name, trigger in described.items():
        current = stored.get(name)
        if current is None:
            upgrade_ops.ops.append(
                TriggerChangeOp(
                    trigger.table,   # таблица
                    name,            # имя
                    None,            # не было
                    trigger.sql,     # стало
                ),
            )
        elif normalize_sql(current.sql) != normalize_sql(trigger.sql):
            upgrade_ops.ops.append(
                TriggerChangeOp(
                    trigger.table,   # таблица
                    name,            # имя
                    current.sql,     # было
                    trigger.sql,     # стало
                ),
            )
    for name, current in stored.items():
        if name not in described and current.table in tables:
            upgrade_ops.ops.append(
                TriggerChangeOp(
                    current.table,   # таблица
                    name,            # имя
                    current.sql,     # было
                    None,            # не будет
                ),
            )
    return PriorityDispatchResult.CONTINUE


@renderers.dispatch_for(TriggerChangeOp)
def _render_trigger_change(
    autogen_context : Any,               # контекст autogenerate
    operation       : TriggerChangeOp,   # изменение
) -> List[str]: # строки файла миграции
    """
    Записывает изменение в файл миграции: снять прежний, создать новый. Через
    ``exec_driver_sql``: ``op.execute`` прочёл бы двоеточие в тексте как параметр запроса.

    Args:
        autogen_context : (AutogenContext) Контекст autogenerate (не используется).
        operation       : (TriggerChangeOp) Изменение.

    Returns:
        (List[str]) Строки кода.

    Example:
        >>> _render_trigger_change(
        ...     None,                                     # контекст
        ...     TriggerChangeOp('t', 'a', 'x', None),     # удаление
        ... )
        ['op.get_bind().exec_driver_sql(\\'DROP TRIGGER IF EXISTS "a"\\')']
    """
    lines = [f"op.get_bind().exec_driver_sql({drop_trigger_sql(operation.name)!r})"]
    if operation.new is not None:
        lines.append(f"op.get_bind().exec_driver_sql({operation.new!r})")
    return lines
