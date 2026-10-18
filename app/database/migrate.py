# app/database/migrate.py

"""
Миграции схемы БД (Alembic): довести базу до последней версии.

Вызывается при открытии базы (``Database.__init__``) вместо ``Base.metadata.create_all``:
create_all умеет только СОЗДАТЬ недостающие таблицы — новый столбец, индекс или изменение
типа в существующей базе он не применяет, и базы в клиниках расходились бы со схемой.

Три случая:
    * **новая (пустая) база** — применяются все миграции с первой;
    * **старая база без отметки версии** (создана create_all до 2026-10-16) — приводится
      к исходной миграции (``BASELINE``): НЕДОСТАЮЩЕЕ (таблицы, индексы, необязательные
      столбцы) дописывается — create_all в существующие таблицы ничего не добавлял, и базы
      разных лет отличаются; ЛИШНЕЕ (старые столбцы, посторонние таблицы) не трогается —
      данные не теряются, в лог предупреждение; НЕБЕЗОПАСНОЕ (нужен обязательный столбец
      без значения по умолчанию) — ``MigrationError``, база не меняется. Затем база
      помечается версией ``BASELINE`` и обновляется дальше;
    * **база с отметкой** — применяются недостающие миграции.

Перед применением миграций к существующей базе-файлу делается резервная копия
(``<файл>.bak-<ГГГГММДД_ЧЧММСС>-<версия>``): данные клиники дороже.

Пример:
    >>> from app.database.migrate import upgrade_database
    >>> upgrade_database(engine)          # при старте — Database делает это сам
    'a1b2c3d4'
"""

from __future__ import annotations

import functools
import os
# import shutil  # до M8 (2026-10-18): копия файла — теперь backup-API SQLite
import sqlite3
import time
from typing import List, Optional, Tuple

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import sqlalchemy as sa
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine

from app.utils.logger.logger import AppLogger

_log = AppLogger.get_instance('database.migrate', enable_file_logging='system')

# Папка миграций (рядом с этим модулем; в exe — внутри распакованного пакета app)
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')

# Исходная миграция: схема, которую строил create_all до введения миграций
BASELINE = '0001_baseline'


class MigrationError(RuntimeError):
    """
    База не может быть безопасно обновлена (например, старая база со схемой, отличной от
    исходной миграции). База при этом не изменяется.

    Пример:
        >>> raise MigrationError('схема не совпадает')
        Traceback (most recent call last):
        MigrationError: схема не совпадает
    """


def alembic_config(connection=None) -> Config:
    """
    Конфигурация Alembic из кода (без alembic.ini): папка миграций и, при передаче,
    соединение, в котором идут миграции.

    Args:
        connection: Соединение SQLAlchemy (``env.py`` возьмёт его из ``attributes``).

    Returns:
        ``alembic.config.Config``.

    Пример:
        >>> cfg = alembic_config()
        >>> cfg.get_main_option('script_location').endswith('migrations')
        True
    """
    cfg = Config()
    cfg.set_main_option('script_location', MIGRATIONS_DIR)
    if connection is not None:
        cfg.attributes['connection'] = connection
    return cfg


@functools.lru_cache(maxsize=1)
def head_revision() -> str:
    """
    Последняя версия схемы (голова цепочки миграций).

    Returns:
        Идентификатор ревизии.

    Результат запоминается (M4, 2026-10-16): миграции за время работы не меняются, а
    Database открывается многократно (тесты, пересоздание сервисов). Сбросить —
    ``head_revision.cache_clear()``.

    Raises:
        MigrationError: Цепочка разветвилась (несколько голов) — нужна миграция-слияние.

    Пример:
        >>> head_revision()
        '0001_baseline'
    """
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    if len(heads) != 1:
        raise MigrationError(f"у миграций {len(heads)} голов {heads} — нужна миграция-слияние")
    return heads[0]


def current_revision(engine: Engine) -> Optional[str]:
    """
    Версия схемы базы (из таблицы ``alembic_version``).

    Args:
        engine: Движок базы.

    Returns:
        Ревизия или ``None`` (база без отметки — новая или созданная create_all).

    Пример:
        >>> current_revision(engine)
        '0001_baseline'
    """
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def schema_differences(engine: Engine, metadata=None) -> List:
    """
    Отличия схемы базы от моделей (``Base.metadata``) — как их видит autogenerate.

    Используется для старых баз (совпадает ли с исходной миграцией) и в тестах
    («модели = миграции»).

    Args:
        engine: Движок базы.
        metadata: Метаданные моделей; по умолчанию ``Base.metadata`` приложения.

    Returns:
        Список отличий (пусто — схемы совпадают).

    Пример:
        >>> schema_differences(engine)
        []
    """
    if metadata is None:
        from app.database.database_shema.clinic import Base
        metadata = Base.metadata
    if hasattr(engine, 'connect') and not hasattr(engine, 'in_transaction'):
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={'compare_type': True})
            diffs = compare_metadata(ctx, metadata)
    else:   # уже соединение (внутри транзакции миграции)
        ctx = MigrationContext.configure(engine, opts={'compare_type': True})
        diffs = compare_metadata(ctx, metadata)
    # таблица версий Alembic — служебная, не отличие
    return [d for d in diffs if not _is_alembic_table(d)]


def _is_alembic_table(diff) -> bool:
    """
    Отличие касается служебной таблицы ``alembic_version``.

    Args:
        diff: Элемент результата compare_metadata.

    Returns:
        ``True`` для служебной таблицы.

    Пример:
        >>> _is_alembic_table(('remove_table', table))
        True
    """
    item = diff[0] if isinstance(diff, list) else diff
    table = item[1] if len(item) > 1 else None
    return getattr(table, 'name', None) == 'alembic_version'


def _user_tables(engine: Engine) -> List[str]:
    """
    Таблицы базы, кроме служебных (``alembic_version``, ``sqlite_*``).

    Args:
        engine: Движок.

    Returns:
        Имена таблиц.

    Пример:
        >>> _user_tables(engine)
        ['appointments', 'appointments_notes', 'patients', 'photos']
    """
    return [t for t in inspect(engine).get_table_names()
            if t != 'alembic_version' and not t.startswith('sqlite_')]


def _backup(engine: Engine, revision: Optional[str]) -> Optional[str]:
    """
    Резервная копия файла базы перед миграцией (только SQLite-файл; память — нет).

    Копия — через backup-API SQLite (M8, 2026-10-18), а не копированием файла: в режиме
    WAL свежие изменения лежат в отдельном файле ``-wal`` и, пока базу держит открытой
    другая программа, в основной файл не сливаются — копия файла их теряла. Backup-API
    читает базу как обычный читатель (под нашей блокировкой записи это разрешено) и
    даёт согласованный снимок в любом режиме журнала.

    Args:
        engine: Движок.
        revision: Текущая ревизия (в имя копии).

    Returns:
        Путь к копии или ``None``.

    Пример:
        >>> _backup(engine, '0001_baseline')
        'clinic.db.bak-20261016_211500-0001_baseline'
    """
    path = engine.url.database
    if engine.url.get_backend_name() != 'sqlite' or not path or path == ':memory:' or not os.path.exists(path):
        return None
    backup = f"{path}.bak-{time.strftime('%Y%m%d_%H%M%S')}-{revision or 'none'}"
    n = 1
    while os.path.exists(backup):
        backup = f"{path}.bak-{time.strftime('%Y%m%d_%H%M%S')}-{revision or 'none'}-{n}"
        n += 1
    engine.dispose()            # закрыть соединения приложения
    # shutil.copy2(path, backup)
    # ↑ до M8 (2026-10-18): копия файла теряла изменения из -wal (режим WAL, база открыта другой программой)
    source = sqlite3.connect(path)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


def _migration_engine(engine: Engine) -> Engine:
    """
    Отдельный движок для миграций с НАСТОЯЩИМИ транзакциями (M1, 2026-10-16).

    Стандартный драйвер SQLite (pysqlite) сам фиксирует команды изменения схемы
    (CREATE/ALTER/DROP) мимо транзакции — сбой посреди миграции оставлял базу
    полуобновлённой. Рецепт SQLAlchemy: отключить автоуправление драйвера и начинать
    транзакцию явно (BEGIN). Только для движка миграций — поведение основного движка
    приложения не меняется. Не SQLite — тот же движок.

    Args:
        engine: Движок приложения.

    Returns:
        Движок для миграций (для SQLite — новый, его надо закрыть ``dispose()``).

    Пример:
        >>> m = _migration_engine(engine); ...; m.dispose()
    """
    if engine.url.get_backend_name() != 'sqlite' or engine.url.database in (None, '', ':memory:'):
        return engine
    migration = create_engine(engine.url)

    @event.listens_for(migration, 'connect')
    def _no_driver_transactions(dbapi_connection, connection_record):
        """
        Драйвер не начинает и не фиксирует транзакции сам.

        Внешние ключи — явно ВЫКЛ (M10, 2026-10-18): SQLite пересобирает таблицу при
        ALTER (создать новую → скопировать → удалить старую). С включёнными ключами
        удаление старой таблицы каскадом стёрло бы дочерние строки (или упало бы).
        Включать/выключать ключи можно только вне транзакции — поэтому здесь, при
        подключении. Целостность после миграции проверяет ``_check_foreign_keys``.
        """
        dbapi_connection.isolation_level = None
        dbapi_connection.execute('PRAGMA foreign_keys=OFF')

    @event.listens_for(migration, 'begin')
    def _explicit_begin(connection):
        """
        Транзакция начинается явно — DDL откатывается вместе с остальным.

        IMMEDIATE (M3, 2026-10-16): блокировка записи берётся СРАЗУ — вторая копия
        программы, открывающая ту же базу одновременно, ждёт, а не меняет её параллельно.
        """
        connection.exec_driver_sql('BEGIN IMMEDIATE')

    return migration


def upgrade_database(engine: Engine, backup: bool = True) -> str:
    """
    Доводит базу до последней версии схемы (см. описание модуля).

    Args:
        engine: Движок базы.
        backup: Делать резервную копию файла перед миграцией существующей базы.

    Returns:
        Ревизия базы после обновления (голова).

    Raises:
        MigrationError: Старая база без отметки не совпадает с исходной схемой, или
            цепочка миграций разветвилась. База не меняется.

    Пример:
        >>> upgrade_database(engine)
        '0001_baseline'
    """
    head = head_revision()
    if current_revision(engine) == head:
        return head                           # обычный случай — без блокировки и копий
    target = _migration_engine(engine)        # M1: транзакции, в которых откатывается и DDL
    try:
        return _upgrade(engine, target, head, backup)
    finally:
        if target is not engine:
            target.dispose()


def _upgrade(engine: Engine, target: Engine, head: str, backup: bool) -> str:
    """
    Тело ``upgrade_database``: изменения — через ``target`` (движок миграций).

    Всё — в ОДНОЙ транзакции движка миграций с блокировкой записи (M3): версия и таблицы
    базы читаются уже под блокировкой — если другая копия программы только что обновила
    базу, здесь это видно, и повторно ничего не делается.

    Args:
        engine: Движок приложения (резервная копия, закрытие соединений).
        target: Движок миграций.
        head: Последняя ревизия.
        backup: Делать резервную копию.

    Returns:
        Ревизия после обновления.

    Пример:
        >>> _upgrade(engine, target, '0001_baseline', True)
        '0001_baseline'
    """
    engine.dispose()                          # соединения приложения не держат базу
    with target.begin() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        tables = [n for n in inspect(conn).get_table_names()
                  if n != 'alembic_version' and not n.startswith('sqlite_')]
        if current == head:
            return head                       # обновила другая копия программы
        _ensure_known_revision(current)       # M9: база новее программы — отказ до любых изменений
        fk_before = _foreign_key_violations(conn)
        legacy_backup = None
        if current is None and tables:
            current, legacy_backup = _repair_legacy(engine, conn, backup)
            if current == head:
                return head
        # M6 (2026-10-17): копия старой базы уже сделана в этой же транзакции — до фиксации
        # файл тот же, вторая копия была бы дублем с неверной меткой версии.
        need_backup = backup and tables and legacy_backup is None
        backup_path = _backup(engine, current) if need_backup else None
        if backup_path:
            _log.info(f"Резервная копия базы перед миграцией: {backup_path}")
        command.upgrade(alembic_config(conn), 'head')
        _check_foreign_keys(conn, fk_before)  # M10: новые нарушения связей — откат всего
    _log.info(f"Схема базы обновлена: {current or 'пусто'} → {head}")
    return head


def _ensure_known_revision(current: Optional[str]) -> None:
    """
    Версия базы известна этой программе (M9, 2026-10-18).

    Сценарий: новая версия программы обновила базу (например, до 0003), затем запустили
    старую (знает до 0002). Раньше Alembic падал невнятным «Can't locate revision», а
    перед этим успевала сделаться резервная копия. Теперь — понятный отказ, база не
    трогается.

    Args:
        current: Версия базы (``None`` — без отметки, это не ошибка).

    Raises:
        MigrationError: Версия базы неизвестна программе.

    Пример:
        >>> _ensure_known_revision('0001_baseline')      # известна — ничего
        >>> _ensure_known_revision('0099_future')
        Traceback (most recent call last):
        MigrationError: версия базы 0099_future новее этой программы ...
    """
    if current is None:
        return
    try:
        known = ScriptDirectory.from_config(alembic_config()).get_revision(current) is not None
    except Exception:          # ResolutionError/CommandError — версии нет в миграциях программы
        known = False
    if not known:
        raise MigrationError(f"версия базы {current} новее этой программы (знает до {head_revision()}) — "
                             "запустите более новую версию программы")


def _foreign_key_violations(connection) -> set:
    """
    Нарушения внешних ключей в базе SQLite (``PRAGMA foreign_key_check``).

    Args:
        connection: Соединение (может быть в транзакции).

    Returns:
        Множество ``(таблица, rowid, родительская таблица, № ключа)``; не SQLite — пусто.

    Пример:
        >>> _foreign_key_violations(conn)
        set()
    """
    if connection.dialect.name != 'sqlite':
        return set()
    return {tuple(row) for row in connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()}


def _check_foreign_keys(connection, before: set) -> None:
    """
    После миграции не появилось НОВЫХ нарушений связей (M10, 2026-10-18).

    На время миграции ключи выключены (пересборка таблиц SQLite); ошибочная миграция
    могла оставить «висячие» ссылки. Сравнение — с нарушениями ДО миграции: в старых
    базах ключи никогда не проверялись, и их собственные нарушения не должны мешать
    обновлению (их не создавали миграции).

    Args:
        connection: Соединение миграции (в транзакции).
        before: Результат ``_foreign_key_violations`` до миграции.

    Raises:
        MigrationError: Есть новые нарушения — транзакция откатится.

    Пример:
        >>> _check_foreign_keys(conn, set())
    """
    new = _foreign_key_violations(connection) - before
    if new:
        sample = ', '.join(f"{t}#{rowid}→{parent}" for t, rowid, parent, _ in sorted(new, key=str)[:5])
        raise MigrationError(f"после миграции нарушены связи ({len(new)}): {sample} — изменения отменены")


def _repair_legacy(engine: Engine, conn, backup: bool) -> Tuple[str, Optional[str]]:
    """
    Старая база без отметки: приведение к исходной схеме и отметка ``BASELINE``
    (внутри транзакции с блокировкой).

    Args:
        engine: Движок приложения (для резервной копии).
        conn: Соединение движка миграций (в транзакции).
        backup: Делать резервную копию.

    Returns:
        ``(BASELINE, путь копии или None)`` — путь нужен ``_upgrade``, чтобы не делать
        вторую копию того же файла (M6).

    Raises:
        MigrationError: Небезопасное отличие (см. ``_plan_legacy_repair``).

    Пример:
        >>> _repair_legacy(engine, conn, True)
        ('0001_baseline', '/data/clinic.db.bak-20261017_101500-legacy')
    """
    added, ignored = _plan_legacy_repair(conn)
    legacy_backup = _backup(engine, 'legacy') if (backup and added) else None
    if legacy_backup:
        _log.info(f"Резервная копия старой базы перед приведением к схеме: {legacy_backup}")
    _apply_legacy_repair(conn, added)
    command.stamp(alembic_config(conn), BASELINE)
    for line in ignored:
        _log.warning(f"Старая база: {line} — оставлено как есть (данные не трогаем)")
    _log.info(f"Старая база приведена к исходной схеме ({len(added)} дописано, "
              f"{len(ignored)} оставлено) и отмечена {BASELINE}")
    return BASELINE, legacy_backup


def _baseline_metadata():
    """
    Схема, которую строит исходная миграция (``BASELINE``), — собранная во временной
    базе в памяти (а не текущие модели: модели со временем меняются).

    Returns:
        ``MetaData`` исходной схемы (без служебной ``alembic_version``).

    Пример:
        >>> sorted(_baseline_metadata().tables)
        ['appointments', 'appointments_notes', 'patients', 'photos']
    """
    from sqlalchemy import MetaData, create_engine
    reference = create_engine('sqlite://')
    try:
        with reference.begin() as conn:
            command.upgrade(alembic_config(conn), BASELINE)
        meta = MetaData()
        meta.reflect(reference)
        meta.remove(meta.tables['alembic_version'])
        return meta
    finally:
        reference.dispose()


# Отличия старой базы, которые можно ДОПИСАТЬ (недостающее)
_ADDABLE = ('add_table', 'add_index', 'add_column')


def _plan_legacy_repair(engine: Engine):
    """
    Что дописать в старую базу до исходной схемы и что оставить как есть.

    Args:
        engine: Движок старой базы.

    Returns:
        ``(добавить, оставить)``: элементы autogenerate для дописывания и строки-описания
        оставленных отличий (лишние таблицы/столбцы/индексы, иные типы).

    Raises:
        MigrationError: Нужен обязательный столбец без значения по умолчанию — его нельзя
            добавить в таблицу с данными.

    Пример:
        >>> added, ignored = _plan_legacy_repair(engine)
        >>> [a[0] for a in added]
        ['add_index']
    """
    added, ignored = [], []
    for diff in schema_differences(engine, _baseline_metadata()):   # engine — движок или соединение
        items = diff if isinstance(diff, list) else [diff]
        for item in items:
            kind = item[0]
            if kind not in _ADDABLE:
                ignored.append(describe_differences([item])[0])
                continue
            if kind == 'add_column':
                column = item[3]
                if not column.nullable and column.server_default is None:
                    raise MigrationError(
                        f"Старой базе не хватает обязательного столбца {item[2]}.{column.name} без "
                        "значения по умолчанию — автоматически добавить нельзя, база не изменена"
                    )
            added.append(item)
    return added, ignored


def _apply_legacy_repair(connection, added) -> None:
    """
    Дописывает в старую базу недостающие таблицы, индексы, необязательные столбцы.

    Args:
        connection: Соединение (внутри транзакции).
        added: Элементы из ``_plan_legacy_repair``.

    Returns:
        None

    Пример:
        >>> _apply_legacy_repair(conn, [('add_index', index)])
    """
    from alembic.operations import Operations
    ops = Operations(MigrationContext.configure(connection))
    for item in sorted(added, key=lambda i: _ADDABLE.index(i[0])):   # таблицы → индексы → столбцы
        kind = item[0]
        if kind == 'add_table':
            item[1].create(bind=connection)
        elif kind == 'add_index':
            item[1].create(bind=connection)
        elif kind == 'add_column':
            column = item[3]
            fresh = sa.Column(column.name, column.type, nullable=column.nullable,
                              server_default=column.server_default)
            ops.add_column(item[2], fresh)
        _log.info(f"Старая база: дописано {describe_differences([item])[0]}")


def describe_differences(diffs: List) -> List[str]:
    """
    Отличия схем — короткими строками (для сообщений, журнала и тестов).

    Формы записей autogenerate: ``('add_table', Table)``, ``('add_index', Index)``,
    ``('add_column', схема, таблица, Column)``, ``('modify_type', схема, таблица, столбец,
    …)`` и т. п. (M2, 2026-10-16: раньше имя столбца терялось).

    Args:
        diffs: Результат ``schema_differences`` (элементы или списки элементов).

    Returns:
        Строки вида ``'remove_column patients.email'``.

    Пример:
        >>> describe_differences(schema_differences(engine))
        ['add_index appointments_notes.ix_appointment_note_text']
    """
    result: List[str] = []
    for diff in diffs:
        for item in (diff if isinstance(diff, list) else [diff]):
            kind = item[0]
            if kind.endswith('_column'):
                column = item[3]
                result.append(f"{kind} {item[2]}.{getattr(column, 'name', column)}")
            elif kind.startswith('modify_'):
                result.append(f"{kind} {item[2]}.{item[3]}")
            elif kind.endswith('_index') or kind.endswith('_constraint') or kind.endswith('_fk'):
                obj = item[1]
                table = getattr(getattr(obj, 'table', None), 'name', '')
                result.append(f"{kind} {table}.{getattr(obj, 'name', obj)}")
            else:
                result.append(f"{kind} {getattr(item[1], 'name', item[1])}")
    return result


def startup_error_text(exc: BaseException) -> Optional[str]:
    """
    Понятный пользователю текст ошибки открытия базы при запуске (проход 3, M7, 2026-10-18).

    Раньше отказ миграции или заблокированная база вылетали из ``Database.__init__``
    необработанным исключением: в exe без консоли программа молча закрывалась. Функция
    без Qt — её зовёт окно запуска (``interfaces/gui/gui_window/main.py``), её же
    проверяют тесты.

    Args:
        exc: Исключение, поднятое при открытии базы (в т. ч. обёрнутое — смотрится
            цепочка ``__cause__``/``__context__``).

    Returns:
        Текст для сообщения или ``None`` — ошибка не про базу (пусть идёт дальше как есть).

    Пример:
        >>> startup_error_text(MigrationError('нет обязательного столбца'))
        'Базу данных нельзя безопасно обновить: нет обязательного столбца. ...'
        >>> startup_error_text(ValueError('x')) is None
        True
    """
    from sqlalchemy.exc import DatabaseError

    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:      # обход цепочки причин
        seen.add(id(current))
        if isinstance(current, MigrationError):
            return (f"Базу данных нельзя безопасно обновить: {current}. "
                    "База не изменена. Обратитесь к разработчику.")
        if isinstance(current, DatabaseError):
            detail = str(getattr(current, 'orig', None) or current).lower()
            if 'locked' in detail or 'busy' in detail:
                return ("База данных занята другой копией программы (идёт обновление или запись). "
                        "Закройте другие копии и запустите программу снова.")
            if 'readonly' in detail or 'read-only' in detail or 'unable to open' in detail:
                return ("Нет доступа на запись к файлу базы данных или его папке. "
                        "Проверьте права и путь к базе в настройках.")
            return (f"Ошибка базы данных при запуске: {getattr(current, 'orig', None) or current}. "
                    "Если база обновлялась — рядом с файлом есть резервная копия (.bak-…).")
        current = current.__cause__ or current.__context__
    return None
