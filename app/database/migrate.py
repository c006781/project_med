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
(``<файл>.bak-<ГГГГММДД_ЧЧММСС>-<версия>``, backup-API SQLite — MG8): данные клиники дороже.

Защиты (подробно — ``IMPLEMENTATION.md`` рядом):
    * всё — одна транзакция, откатывается и изменение схемы (MG1);
    * блокировка записи сразу и решение под ней — две копии программы не мешают (MG3);
    * база новее программы — отказ до любых изменений (MG9);
    * внешние ключи на время миграции выключены, после — проверка новых «висячих»
      ссылок (MG10);
    * понятный текст ошибки для окна запуска — ``startup_error_text`` (MG7);
    * встроенные триггеры SQLite (Ф1.6.7д, ``sqlite_triggers``): Alembic их не видит — сравнение
      добавлено к его отличиям; недостающий или изменённый дописывается автодостройкой, после
      миграции проверяется, что триггеры компилируются (MG14).

Автоматизация (2026-10-18, «автомиграции»):
    * **автодостройка** при каждом запуске: база сравнивается со схемой ПОСЛЕДНЕЙ миграции;
      недостающее безопасное (таблица, индекс, необязательный столбец) дописывается само,
      лишнее не трогается, обязательный столбец без значения — отказ. Тот же механизм,
      что для старых баз (там сравнение с исходной схемой);
    * **генерация миграции** по изменившимся моделям — только безопасные добавления
      (``generate_migration``); при запуске из исходников включается точкой входа
      (``configure(autogenerate=True)``), в exe — нет (файлы миграций там не пишутся);
    * **проверка для сборки** — ``python -m app.database.migrate check [--generate]``:
      модели = миграции, одна «голова»; иначе код выхода 1 (сборка останавливается).
    Переименования, смена типов, перенос данных — только вручную: автоматика видит
    переименование как «удалить + добавить» и потеряла бы данные.

Пример:
    >>> from app.database.migrate import upgrade_database
    >>> upgrade_database(engine)          # при старте — Database делает это сам
    '0001_baseline'
"""

from __future__ import annotations

import dataclasses
import datetime
import functools
import os
# import shutil  # до MG8 (2026-10-18): копия файла — теперь backup-API SQLite
import sqlite3
import sys
# import time
# ↑ до 2026-11-01 (итоговая перепроверка Ф1.6.7г): нужен был только прежнему _backup
#   (закомментирован при выносе копии в database.backup_sqlite_database, Ф1.6.10а); pyflakes.
from typing import List, Optional, Sequence, Tuple, Union

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext   # alembic.migration — лишь совместимый псевдоним
from alembic.script import ScriptDirectory
import sqlalchemy as sa
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine

from app.database import sqlite_triggers   # заодно подключает сравнение триггеров к Alembic
from app.utils.logger.logger import AppLogger

_log = AppLogger.get_instance('database.migrate', enable_file_logging='system')

# Папка миграций (рядом с этим модулем; в exe — внутри распакованного пакета app)
MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')

# Исходная миграция: схема, которую строил create_all до введения миграций
BASELINE = '0001_baseline'


@dataclasses.dataclass
class MigrationSettings:
    """
    Что делает ``upgrade_database`` сверх применения миграций (2026-10-18).

    Attributes:
        repair_drift: Автодостройка — дописывать в базу недостающее безопасное по схеме
            последней миграции (по умолчанию да: база, у которой вручную удалили индекс
            или таблицу, чинится сама).
        autogenerate: Перед обновлением создавать миграцию по изменившимся моделям
            (только безопасные добавления). По умолчанию НЕТ: включает точка входа при
            запуске из исходников. В тестах и в exe — выключено (тесты регистрируют свои
            модели на общей ``Base``; в exe файлы миграций — во временной папке).

    Пример:
        >>> MigrationSettings()
        MigrationSettings(repair_drift=True, autogenerate=False)
    """

    repair_drift: bool = True
    autogenerate: bool = False


_settings = MigrationSettings()


def configure(
    **changes : bool,   # поля MigrationSettings
) -> MigrationSettings: # настройки до изменения
    """
    Меняет настройки автоматики миграций (для всего процесса).

    Args:
        **changes : (bool) Поля ``MigrationSettings`` (``repair_drift``, ``autogenerate``).

    Returns:
        (MigrationSettings) Настройки ДО изменения (копия) — чтобы вернуть:
            ``configure(**dataclasses.asdict(old))``.

    Raises:
        TypeError: Неизвестная настройка.

    Example:
        >>> old = configure(
        ...     autogenerate    =   True,   # точка входа при запуске из исходников
        ... )
        >>> old.autogenerate
        False
    """
    unknown = set(changes) - {f.name for f in dataclasses.fields(MigrationSettings)}
    if unknown:
        raise TypeError(f"неизвестные настройки миграций: {sorted(unknown)}")
    previous = dataclasses.replace(_settings)
    for name, value in changes.items():
        setattr(_settings, name, bool(value))
    return previous


class MigrationError(RuntimeError):
    """
    База не может быть безопасно обновлена (например, старая база со схемой, отличной от
    исходной миграции). База при этом не изменяется.

    Пример:
        >>> raise MigrationError('схема не совпадает')
        Traceback (most recent call last):
        MigrationError: схема не совпадает
    """


def alembic_config(
    connection : Optional[sa.engine.Connection] = None,   # соединение миграций
    metadata   : Optional[sa.MetaData] = None,            # модели для генерации миграции
) -> Config: # конфигурация Alembic из кода
    """
    Конфигурация Alembic из кода (без alembic.ini): папка миграций и, при передаче,
    соединение, в котором идут миграции.

    Args:
        connection : (Connection/None) Соединение SQLAlchemy (``env.py`` возьмёт его из
            ``attributes``); None — без соединения.
        metadata   : (MetaData/None) Модели для сравнения при генерации миграции; None — в
            ``env.py`` ``Base.metadata`` приложения.

    Returns:
        (Config) ``alembic.config.Config``.

    Example:
        >>> cfg = alembic_config()
        >>> cfg.get_main_option('script_location').endswith('migrations')
        True
    """
    cfg = Config()
    cfg.set_main_option('script_location', MIGRATIONS_DIR)
    if connection is not None:
        cfg.attributes['connection'] = connection
    if metadata is not None:
        cfg.attributes['target_metadata'] = metadata
    return cfg


@functools.lru_cache(maxsize=1)
def head_revision() -> str:
    """
    Последняя версия схемы (голова цепочки миграций).

    Returns:
        Идентификатор ревизии.

    Результат запоминается (MG4, 2026-10-16): миграции за время работы не меняются, а
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


def schema_differences(
    engine   : Union[Engine, sa.engine.Connection],   # движок или соединение (внутри транзакции)
    metadata : Optional[sa.MetaData] = None,          # образец; None — модели приложения
) -> List: # отличия схемы базы от образца
    """
    Возвращает отличия схемы базы от моделей (``Base.metadata``) — как их видит autogenerate
    (и триггеры: Alembic их сам не видит, сравнение добавляет ``sqlite_triggers``).

    Используется для старых баз (совпадает ли с исходной миграцией) и в тестах
    («модели = миграции»).

    Args:
        engine   : (Engine/Connection) Движок базы или соединение внутри транзакции.
        metadata : (MetaData/None) Метаданные образца; None — ``Base.metadata`` приложения.

    Returns:
        (List) Отличия; пусто — схемы совпадают.

    Example:
        >>> schema_differences(
        ...     engine,   # база
        ... )
        []
    """
    if metadata is None:
        metadata = _default_metadata()
    if hasattr(engine, 'connect') and not hasattr(engine, 'in_transaction'):
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={'compare_type': True})
            diffs = compare_metadata(ctx, metadata)
    else:   # уже соединение (внутри транзакции миграции)
        ctx = MigrationContext.configure(engine, opts={'compare_type': True})
        diffs = compare_metadata(ctx, metadata)
    # таблица версий Alembic — служебная, не отличие
    return [d for d in diffs if not _is_alembic_table(d)]


def _default_metadata() -> sa.MetaData: # модели приложения по умолчанию
    """
    Возвращает модели по умолчанию — ``Base.metadata`` приложения (одно место: тесты
    подменяют его, чтобы модели других тестов на общей ``Base`` не попадали в сравнение).

    Returns:
        (MetaData) Модели приложения.

    Example:
        >>> 'patients' in _default_metadata().tables
        True
    """
    from app.database.database_shema.clinic import Base
    return Base.metadata


def _is_alembic_table(
    diff : Union[tuple, list],   # элемент результата compare_metadata
) -> bool: # отличие касается служебной таблицы
    """
    Возвращает ``True``, если отличие касается служебной таблицы ``alembic_version``.

    Args:
        diff : (tuple/list) Элемент результата compare_metadata.

    Returns:
        (bool) ``True`` для служебной таблицы.

    Example:
        >>> _is_alembic_table(
        ...     ('remove_table', table),   # отличие
        ... )
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

    Копия — через backup-API SQLite (MG8, 2026-10-18), а не копированием файла: в режиме
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
    # Код копии вынесен 2026-10-31 в app.database.database.backup_sqlite_database (нужна и
    # перед объединением пациентов, Ф1.6.10а); импорт внутри — migrate грузит Database лениво.
    from app.database.database import backup_sqlite_database
    return backup_sqlite_database(
        engine,                  # движок базы
        revision or 'none',      # метка — текущая ревизия
    )
    # path = engine.url.database
    # if engine.url.get_backend_name() != 'sqlite' or not path or path == ':memory:' or not os.path.exists(path):
    #     return None
    # backup = f"{path}.bak-{time.strftime('%Y%m%d_%H%M%S')}-{revision or 'none'}"
    # n = 1
    # while os.path.exists(backup):
    #     backup = f"{path}.bak-{time.strftime('%Y%m%d_%H%M%S')}-{revision or 'none'}-{n}"
    #     n += 1
    # engine.dispose()            # закрыть соединения приложения
    # # shutil.copy2(path, backup)
    # # ↑ до MG8 (2026-10-18): копия файла теряла изменения из -wal (режим WAL, база открыта другой программой)
    # source = sqlite3.connect(path)
    # target = sqlite3.connect(backup)
    # try:
    #     source.backup(target)
    # finally:
    #     target.close()
    #     source.close()
    # return backup
    # ↑ до 2026-10-31 (Ф1.6.10а): копия делалась здесь; теперь — общая функция.


def _migration_engine(engine: Engine) -> Engine:
    """
    Отдельный движок для миграций с НАСТОЯЩИМИ транзакциями (MG1, 2026-10-16).

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
    def _no_driver_transactions(
        dbapi_connection  : sqlite3.Connection,   # новое соединение
        connection_record : object,               # запись пула (не используется)
    ) -> None: # драйвер не управляет транзакциями; внешние ключи выключены
        """
        Отключает у драйвера собственное управление транзакциями: он не начинает и не
        фиксирует их сам.

        Внешние ключи — явно ВЫКЛ (MG10, 2026-10-18): SQLite пересобирает таблицу при
        ALTER (создать новую → скопировать → удалить старую). С включёнными ключами
        удаление старой таблицы каскадом стёрло бы дочерние строки (или упало бы).
        Включать/выключать ключи можно только вне транзакции — поэтому здесь, при
        подключении. Целостность после миграции проверяет ``_check_foreign_keys``.

        Args:
            dbapi_connection  : (sqlite3.Connection) Соединение.
            connection_record : (object) Запись пула.

        Example:
            >>> _no_driver_transactions(
            ...     sqlite3.connect(':memory:'),   # соединение
            ...     None,                          # запись пула
            ... )
        """
        dbapi_connection.isolation_level = None
        dbapi_connection.execute('PRAGMA foreign_keys=OFF')

    @event.listens_for(migration, 'begin')
    def _explicit_begin(
        connection : sa.engine.Connection,   # соединение, начинающее транзакцию
    ) -> None: # начинает транзакцию явно (BEGIN IMMEDIATE)
        """
        Начинает транзакцию явно — DDL откатывается вместе с остальным.

        IMMEDIATE (MG3, 2026-10-16): блокировка записи берётся СРАЗУ — вторая копия
        программы, открывающая ту же базу одновременно, ждёт, а не меняет её параллельно.

        Args:
            connection : (Connection) Соединение SQLAlchemy.

        Example:
            >>> with migration.begin() as conn:   # вызывается событием begin
            ...     pass
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

    Кроме миграций — автодостройка по последней схеме (``MigrationSettings.repair_drift``)
    и, если включено, генерация миграции по моделям (``MigrationSettings.autogenerate``).

    Raises:
        MigrationError: Старая база без отметки не совпадает с исходной схемой, или
            цепочка миграций разветвилась, или базе не хватает обязательного столбца,
            или модели изменены небезопасно (при ``autogenerate``). База не меняется.

    Пример:
        >>> upgrade_database(engine)
        '0001_baseline'
    """
    if _settings.autogenerate:
        generate_migration()                  # из исходников: модели изменились — миграция
    head = head_revision()
    if current_revision(engine) == head and not _drift_plan(engine, head)[0]:
        return head                           # обычный случай — без блокировки и копий
    target = _migration_engine(engine)        # MG1: транзакции, в которых откатывается и DDL
    try:
        return _upgrade(engine, target, head, backup)
    finally:
        if target is not engine:
            target.dispose()


def _upgrade(
    engine : Engine,   # движок приложения
    target : Engine,   # движок миграций
    head   : str,      # последняя ревизия
    backup : bool,     # делать резервную копию
) -> str: # ревизия после обновления
    """
    Выполняет тело ``upgrade_database``: изменения — через ``target`` (движок миграций).

    Всё — в ОДНОЙ транзакции движка миграций с блокировкой записи (MG3): версия и таблицы
    базы читаются уже под блокировкой — если другая копия программы только что обновила
    базу, здесь это видно, и повторно ничего не делается. После миграций и автодостройки —
    проверки связей (MG10) и триггеров (MG14): новые ошибки откатывают всё.

    Args:
        engine : (Engine) Движок приложения (резервная копия, закрытие соединений).
        target : (Engine) Движок миграций.
        head   : (str) Последняя ревизия.
        backup : (bool) Делать резервную копию.

    Returns:
        (str) Ревизия после обновления.

    Raises:
        MigrationError: Отказ приведения, новые нарушения связей, сломанные триггеры.

    Example:
        >>> _upgrade(
        ...     engine,            # движок приложения
        ...     target,            # движок миграций
        ...     '0001_baseline',   # последняя ревизия
        ...     True,              # с копией
        ... )
        '0001_baseline'
    """
    engine.dispose()                          # соединения приложения не держат базу
    with target.begin() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        tables = [n for n in inspect(conn).get_table_names()
                  if n != 'alembic_version' and not n.startswith('sqlite_')]
        _ensure_known_revision(current)       # MG9: база новее программы — отказ до любых изменений
        if current == head and not _drift_plan(conn, head)[0]:
            return head                       # обновила другая копия программы
        start = current
        fk_before = _foreign_key_violations(conn)
        triggers_before = set(sqlite_triggers.trigger_errors(conn))
        backup_path = None
        if current is None and tables:
            current, backup_path = _repair_legacy(engine, conn, backup)
        if current != head:
            # MG6 (2026-10-17): копия старой базы уже сделана в этой же транзакции — до фиксации
            # файл тот же, вторая копия была бы дублем с неверной меткой версии.
            if backup and tables and backup_path is None:
                backup_path = _backup(engine, current)
                if backup_path:
                    _log.info(f"Резервная копия базы перед миграцией: {backup_path}")
            command.upgrade(alembic_config(conn), 'head')
        # автодостройка: копия — только если в этой транзакции ещё ничего не меняли
        # (иначе копия уже есть, а сделать её после записи — читать заблокированный файл)
        _repair_drift(engine, conn, head, may_backup=backup and bool(tables) and backup_path is None
                      and current == start)
        _check_foreign_keys(conn, fk_before)  # MG10: новые нарушения связей — откат всего
        _check_triggers(
            conn,               # соединение миграции
            triggers_before,    # ошибки триггеров до миграции
        )
    if start != head:
        _log.info(f"Схема базы обновлена: {start or 'пусто'} → {head}")
    return head


def _ensure_known_revision(current: Optional[str]) -> None:
    """
    Версия базы известна этой программе (MG9, 2026-10-18).

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


def _foreign_key_violations(
    connection : sa.engine.Connection,   # соединение (может быть в транзакции)
) -> set: # нарушения внешних ключей
    """
    Возвращает нарушения внешних ключей в базе SQLite (``PRAGMA foreign_key_check``).

    Args:
        connection : (Connection) Соединение.

    Returns:
        (set) ``(таблица, rowid, родительская таблица, № ключа)``; не SQLite — пусто.

    Example:
        >>> _foreign_key_violations(
        ...     conn,   # соединение
        ... )
        set()
    """
    if connection.dialect.name != 'sqlite':
        return set()
    return {tuple(row) for row in connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()}


def _check_foreign_keys(
    connection : sa.engine.Connection,   # соединение миграции (в транзакции)
    before     : set,                    # нарушения до миграции
) -> None: # после миграции не появилось новых нарушений связей
    """
    Проверяет, что после миграции не появилось НОВЫХ нарушений связей (MG10, 2026-10-18).

    На время миграции ключи выключены (пересборка таблиц SQLite); ошибочная миграция
    могла оставить «висячие» ссылки. Сравнение — с нарушениями ДО миграции: в старых
    базах ключи никогда не проверялись, и их собственные нарушения не должны мешать
    обновлению (их не создавали миграции).

    Args:
        connection : (Connection) Соединение миграции.
        before     : (set) Результат ``_foreign_key_violations`` до миграции.

    Raises:
        MigrationError: Есть новые нарушения — транзакция откатится.

    Example:
        >>> _check_foreign_keys(
        ...     conn,    # соединение
        ...     set(),   # нарушений не было
        ... )
    """
    new = _foreign_key_violations(connection) - before
    if new:
        sample = ', '.join(f"{t}#{rowid}→{parent}" for t, rowid, parent, _ in sorted(new, key=str)[:5])
        raise MigrationError(f"после миграции нарушены связи ({len(new)}): {sample} — изменения отменены")


def _check_triggers(
    connection : sa.engine.Connection,   # соединение миграции (в транзакции)
    before     : set,                    # ошибки компиляции триггеров до миграции
) -> None: # после миграции не появилось сломанных триггеров
    """
    Проверяет, что после миграции не появилось НОВЫХ ошибок компиляции триггеров (MG14,
    2026-11-07): миграция могла удалить столбец или таблицу, нужные триггеру, а SQLite узнал бы
    об этом только при срабатывании — запись в таблицу падала бы уже у пользователя. Старые
    ошибки (триггер сторонней программы) обновлению не мешают — как и в ``_check_foreign_keys``.

    Args:
        connection : (Connection) Соединение миграции.
        before     : (set) Результат ``trigger_errors`` до миграции.

    Raises:
        MigrationError: Есть новые ошибки — транзакция откатится.

    Example:
        >>> _check_triggers(
        ...     conn,    # соединение
        ...     set(),   # ошибок не было
        ... )
    """
    new = set(sqlite_triggers.trigger_errors(connection)) - before
    if new:
        raise MigrationError(
            f"после миграции сломаны триггеры: {'; '.join(sorted(new))} — изменения отменены"
        )


def check_trigger_definitions(
    metadata : Optional[sa.MetaData] = None,   # модели; None — модели приложения
) -> None: # описание триггеров верно
    """
    Проверяет описание триггеров до открытия базы (MG14, 2026-11-07; по образцу Р-9): SQLite
    принимает ``CREATE TRIGGER`` с опечаткой в таблице или столбце и падает только при
    срабатывании, а имена триггеров едины на базу. Настоящая база не нужна и не трогается;
    таблица без триггеров ни на что не влияет.

    Args:
        metadata : (MetaData/None) Модели; None — ``Base.metadata`` приложения.

    Raises:
        MigrationError: Описание неверно — перечислены все ошибки (таблица, триггер, текст).

    Example:
        >>> check_trigger_definitions()   # триггеры верны — без ошибки
    """
    if metadata is None:
        metadata = _default_metadata()
    errors = sqlite_triggers.definition_errors(metadata)
    if errors:
        raise MigrationError(f"в описании таблиц неверные триггеры: {'; '.join(errors)}")


def _repair_legacy(
    engine : Engine,                 # движок приложения (резервная копия)
    conn   : sa.engine.Connection,   # соединение движка миграций (в транзакции)
    backup : bool,                   # делать резервную копию
) -> Tuple[str, Optional[str]]: # версия базы и путь копии
    """
    Приводит старую базу без отметки к исходной схеме и ставит отметку ``BASELINE`` (внутри
    транзакции с блокировкой).

    Args:
        engine : (Engine) Движок приложения (для резервной копии).
        conn   : (Connection) Соединение движка миграций.
        backup : (bool) Делать резервную копию.

    Returns:
        (Tuple[str, Optional[str]]) ``(BASELINE, путь копии или None)`` — путь нужен
            ``_upgrade``, чтобы не делать вторую копию того же файла (MG6).

    Raises:
        MigrationError: Небезопасное отличие (см. ``_plan_legacy_repair``).

    Example:
        >>> _repair_legacy(
        ...     engine,   # движок приложения
        ...     conn,     # соединение миграции
        ...     True,     # с копией
        ... )
        ('0001_baseline', '/data/clinic.db.bak-20261017_101500-legacy')
    """
    added, ignored = _plan_legacy_repair(conn)
    legacy_backup = _backup(engine, 'legacy') if (backup and added) else None
    if legacy_backup:
        _log.info(f"Резервная копия старой базы перед приведением к схеме: {legacy_backup}")
    _apply_legacy_repair(conn, added, where='Старая база')
    command.stamp(alembic_config(conn), BASELINE)
    for line in ignored:
        _log.warning(f"Старая база: {line} — оставлено как есть (данные не трогаем)")
    _log.info(f"Старая база приведена к исходной схеме ({len(added)} дописано, "
              f"{len(ignored)} оставлено) и отмечена {BASELINE}")
    return BASELINE, legacy_backup


def _baseline_metadata() -> sa.MetaData: # схема исходной миграции
    """
    Возвращает схему, которую строит исходная миграция (``BASELINE``).

    Returns:
        (MetaData) Исходная схема (без служебной ``alembic_version``).

    Example:
        >>> sorted(_baseline_metadata().tables)
        ['appointments', 'appointments_notes', 'patients', 'photos']
    """
    return schema_at(BASELINE)


def schema_at(
    revision : str,   # ревизия (BASELINE, head_revision() …)
) -> sa.MetaData: # схема, которую строят миграции до ревизии
    """
    Возвращает схему, которую строят миграции до ``revision``, — собранную во временной
    базе в памяти (а не текущие модели: модели меняются, миграции — нет).

    Запоминается (по ревизии и папке миграций): строится один раз за процесс.
    Возвращаемый ``MetaData`` — общий, менять его нельзя.

    Args:
        revision : (str) Ревизия (``BASELINE``, ``head_revision()`` …).

    Returns:
        (MetaData) Схема (без служебной ``alembic_version``).

    Example:
        >>> 'patients' in schema_at(
        ...     head_revision(),   # последняя ревизия
        ... ).tables
        True
    """
    return _schema_at(revision, MIGRATIONS_DIR)


@functools.lru_cache(maxsize=8)
def _schema_at(
    revision       : str,   # ревизия
    migrations_dir : str,   # папка миграций (только для ключа кеша)
) -> sa.MetaData: # схема ревизии (тело schema_at)
    """
    Возвращает схему ревизии — тело ``schema_at`` (ключ кеша включает папку миграций —
    тесты подменяют её).

    Args:
        revision       : (str) Ревизия.
        migrations_dir : (str) Папка миграций (только для ключа кеша).

    Returns:
        (MetaData) Схема.

    Example:
        >>> _schema_at(
        ...     '0001_baseline',   # исходная
        ...     MIGRATIONS_DIR,    # папка миграций
        ... )
        MetaData()
    """
    from sqlalchemy import MetaData
    reference = create_engine('sqlite://')
    try:
        with reference.begin() as conn:
            command.upgrade(alembic_config(conn), revision)
        meta = MetaData()
        meta.reflect(reference)
        meta.remove(meta.tables['alembic_version'])
        with reference.connect() as conn: # reflect триггеры не читает (Ф1.6.7д)
            sqlite_triggers.attach_stored_triggers(
                conn,   # база, из которой собрана схема
                meta,   # схема
            )
        return meta
    finally:
        reference.dispose()


# Отличия, которые можно ДОПИСАТЬ (недостающее), — в порядке применения:
# таблицы → столбцы → индексы (MG12, 2026-10-18: раньше индексы шли до столбцов — индекс
# на недостающем столбце создавался раньше самого столбца, и приведение падало)
# _ADDABLE = ('add_table', 'add_index', 'add_column')
# _ADDABLE = ('add_table', 'add_column', 'add_index')
# ↑ до 2026-11-07 (MG14): без триггеров. Они — последними: триггеру нужны таблица и столбцы.
#   Лишний триггер (remove_trigger) не трогается, как и всё лишнее; изменённый заменяется
#   текстом последней миграции: данные при этом не меняются, а правило программы — на месте.
_ADDABLE = ('add_table', 'add_column', 'add_index', sqlite_triggers.ADD_TRIGGER, sqlite_triggers.MODIFY_TRIGGER)


def _plan_legacy_repair(
    engine : Union[Engine, sa.engine.Connection],   # движок старой базы или соединение
) -> Tuple[list, List[str]]: # что дописать и что оставить
    """
    Определяет, что дописать в старую базу до исходной схемы и что оставить как есть.

    Args:
        engine : (Engine/Connection) Соединение движка миграций (внутри транзакции с
            блокировкой) или движок старой базы — ``schema_differences`` принимает оба.

    Returns:
        (Tuple[list, List[str]]) ``(добавить, оставить)`` — см. ``_plan_repair``.

    Raises:
        MigrationError: Нужен обязательный столбец без значения по умолчанию.

    Example:
        >>> added, ignored = _plan_legacy_repair(
        ...     engine,   # старая база
        ... )
        >>> [a[0] for a in added]
        ['add_index']
    """
    return _plan_repair(engine, _baseline_metadata(), where='Старой базе')


def _plan_repair(
    engine    : Union[Engine, sa.engine.Connection],   # база
    reference : sa.MetaData,                           # целевая схема (schema_at)
    where     : str = 'Базе',                          # начало сообщения об отказе
) -> Tuple[list, List[str]]: # что дописать и что оставить
    """
    Определяет, что дописать в базу до схемы ``reference`` и что оставить как есть.

    Общая часть приведения старых баз (к исходной схеме) и автодостройки (к последней).

    Args:
        engine    : (Engine/Connection) Соединение или движок базы.
        reference : (MetaData) Целевая схема (``schema_at(...)``).
        where     : (str) Начало сообщения об отказе («Старой базе», «Базе»).

    Returns:
        (Tuple[list, List[str]]) ``(добавить, оставить)``: элементы autogenerate для
            дописывания (и триггеры: недостающий и с другим текстом) и строки-описания
            оставленных отличий (лишние таблицы/столбцы/индексы/триггеры, иные типы).

    Raises:
        MigrationError: Нужен обязательный столбец без значения по умолчанию — его нельзя
            добавить в таблицу с данными.

    Example:
        >>> added, ignored = _plan_repair(
        ...     conn,                           # соединение
        ...     schema_at(head_revision()),     # схема последней миграции
        ... )
        >>> added
        []
    """
    added, ignored = [], []
    for diff in schema_differences(engine, reference):   # engine — движок или соединение
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
                        f"{where} не хватает обязательного столбца {item[2]}.{column.name} без "
                        "значения по умолчанию — автоматически добавить нельзя, база не изменена"
                    )
            added.append(item)
    return added, ignored


def _drift_plan(
    engine : Union[Engine, sa.engine.Connection],   # база (уже на head)
    head   : str,                                   # последняя ревизия
) -> Tuple[list, List[str]]: # что дописать и что оставить
    """
    Строит план автодостройки: чего не хватает базе до схемы последней миграции.

    Args:
        engine : (Engine/Connection) Соединение или движок базы.
        head   : (str) Последняя ревизия.

    Returns:
        (Tuple[list, List[str]]) ``(добавить, оставить)``; автодостройка выключена —
            ``([], [])``.

    Raises:
        MigrationError: Не хватает обязательного столбца (см. ``_plan_repair``).

    Example:
        >>> _drift_plan(
        ...     engine,            # база
        ...     head_revision(),   # последняя ревизия
        ... )
        ([], [])
    """
    if not _settings.repair_drift:
        return [], []
    return _plan_repair(engine, schema_at(head))


def _repair_drift(
    engine     : Engine,                 # движок приложения (резервная копия)
    conn       : sa.engine.Connection,   # соединение движка миграций (в транзакции)
    head       : str,                    # последняя ревизия (база уже на ней)
    may_backup : bool,                   # сделать копию, если будет что дописать
) -> List[str]: # описания дописанного
    """
    Дописывает в базу недостающее безопасное по схеме последней миграции (автодостройка).

    Зачем: базу могли поправить вручную (удалить индекс, таблицу) или её когда-то
    создали иначе. Миграции этого не заметят (версия базы — последняя), а программа
    упадёт на первом обращении. Лишнее не трогается (данные не теряются), в журнал —
    отладочная запись (иначе предупреждение повторялось бы при каждом запуске).

    Триггер без пересборки не теряется, но его могли удалить или поменять сторонней
    программой: недостающий дописывается, с другим текстом — заменяется текстом последней
    миграции (предупреждение в журнал), лишний остаётся (MG14).

    Args:
        engine     : (Engine) Движок приложения.
        conn       : (Connection) Соединение движка миграций (в транзакции с блокировкой).
        head       : (str) Последняя ревизия.
        may_backup : (bool) Сделать копию; ``False`` — копия уже есть или в транзакции уже
            писали.

    Returns:
        (List[str]) Описания дописанного.

    Raises:
        MigrationError: Не хватает обязательного столбца.

    Example:
        >>> _repair_drift(
        ...     engine,                 # движок приложения
        ...     conn,                   # соединение миграции
        ...     head_revision(),        # последняя ревизия
        ...     may_backup  =   True,   # копия перед дозаписью
        ... )
        ['add_index appointments_notes.ix_appointment_note_text']
    """
    added, ignored = _drift_plan(conn, head)
    for line in ignored:
        _log.debug(f"База: {line} — отличие от схемы оставлено как есть")
    if not added:
        return []
    if may_backup:
        path = _backup(engine, f"{head}-repair")
        if path:
            _log.info(f"Резервная копия базы перед автодостройкой: {path}")
    done = []
    for item in sorted(added, key=lambda i: _ADDABLE.index(i[0])):
        # A5 (2026-10-18): каждый пункт — в своей точке отката. Пункт, который нельзя
        # дописать (уникальный индекс при повторах в данных…), пропускается с
        # предупреждением — иначе программа не запускалась бы НИ РАЗУ на этой базе.
        savepoint = conn.begin_nested()
        try:
            _apply_legacy_repair(conn, [item], where='Автодостройка')
            savepoint.commit()
            done.append(item)
        except Exception as exc:
            savepoint.rollback()
            _log.warning(f"Автодостройка: не удалось дописать {describe_differences([item])[0]} — "
                         f"пропущено ({exc}); база работает без этого")
    return describe_differences(done)


def _apply_legacy_repair(
    connection : sa.engine.Connection,   # соединение (внутри транзакции)
    added      : list,                   # элементы из _plan_repair
    where      : str = 'Старая база',    # начало записи в журнал
) -> None: # дописывает недостающее в базу
    """
    Дописывает в базу недостающие таблицы, столбцы (необязательные), индексы, триггеры
    (изменённый триггер заменяется текстом образца).

    Args:
        connection : (Connection) Соединение.
        added      : (list) Элементы из ``_plan_repair``.
        where      : (str) Начало записи в журнал («Старая база», «Автодостройка»).

    Example:
        >>> _apply_legacy_repair(
        ...     conn,                    # соединение
        ...     [('add_index', index)],  # что дописать
        ... )
    """
    from alembic.operations import Operations
    ops = Operations(MigrationContext.configure(connection))
    for item in sorted(added, key=lambda i: _ADDABLE.index(i[0])):   # таблицы → столбцы → индексы (MG12)
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
        elif kind in sqlite_triggers.TRIGGER_KINDS: # снять прежний текст, если есть, и создать
            sqlite_triggers.apply_trigger_diff(
                connection,   # соединение
                item,         # отличие
            )
        if kind == sqlite_triggers.MODIFY_TRIGGER: # правило меняли мимо программы — заметить
            _log.warning(f"{where}: текст триггера заменён: {describe_differences([item])[0]}")
        else:
            _log.info(f"{where}: дописано {describe_differences([item])[0]}")


def describe_differences(
    diffs : List,   # результат schema_differences
) -> List[str]: # отличия короткими строками
    """
    Описывает отличия схем короткими строками (для сообщений, журнала и тестов).

    Формы записей autogenerate: ``('add_table', Table)``, ``('add_index', Index)``,
    ``('add_column', схема, таблица, Column)``, ``('modify_type', схема, таблица, столбец,
    …)`` и т. п. (MG2, 2026-10-16: раньше имя столбца терялось); триггеры —
    ``('add_trigger', таблица, имя, текст)`` и т. п. (``sqlite_triggers``).

    Args:
        diffs : (List) Результат ``schema_differences`` (элементы или списки элементов).

    Returns:
        (List[str]) Строки вида ``'remove_column patients.email'``.

    Example:
        >>> describe_differences(
        ...     schema_differences(
        ...         engine,   # база
        ...     ),
        ... )
        ['add_index appointments_notes.ix_appointment_note_text']
    """
    result: List[str] = []
    for diff in diffs:
        for item in (diff if isinstance(diff, list) else [diff]):
            kind = item[0]
            if kind in sqlite_triggers.TRIGGER_KINDS:
                result.append(f"{kind} {item[1]}.{item[2]}")
            elif kind.endswith('_column'):
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


def database_error_text(
    exc : BaseException,   # ошибка драйвера (sqlalchemy.exc.DatabaseError, sqlite3.Error)
) -> str: # понятный пользователю текст ошибки открытия базы
    """
    Возвращает понятный пользователю текст ошибки базы при её открытии: «занята другой
    копией», «нет доступа на запись» или общий текст с исходным сообщением драйвера.

    Один источник текста для ``Database.__init__`` (``DatabaseConnectionError``) и
    ``startup_error_text`` (2026-10-31, М8; до этого разбор жил только в
    ``startup_error_text``). Сообщение драйвера — из ``orig`` (SQLAlchemy) или самой ошибки
    (``sqlite3`` — резервная копия через backup-API идёт мимо SQLAlchemy).

    Args:
        exc : (BaseException) Ошибка драйвера.

    Returns:
        (str) Текст для сообщения пользователю.

    Example:
        >>> import sqlite3
        >>> database_error_text(
        ...     sqlite3.OperationalError('database is locked'),   # другая копия пишет
        ... )
        'База данных занята другой копией программы (идёт обновление или запись). ...'
    """
    source = getattr(exc, 'orig', None) or exc
    detail = str(source).lower()
    if 'locked' in detail or 'busy' in detail:
        return ("База данных занята другой копией программы (идёт обновление или запись). "
                "Закройте другие копии и запустите программу снова.")
    if 'readonly' in detail or 'read-only' in detail or 'unable to open' in detail:
        return ("Нет доступа на запись к файлу базы данных или его папке. "
                "Проверьте права и путь к базе в настройках.")
    return (f"Ошибка базы данных при запуске: {source}. "
            "Если база обновлялась — рядом с файлом есть резервная копия (.bak-…).")


# def startup_error_text(exc: BaseException) -> Optional[str]:
# ↑ до 2026-10-31 (М8): сигнатура без комментария (формат skill п. 7).
def startup_error_text(
    exc : BaseException,   # ошибка, поднятая при открытии базы
) -> Optional[str]: # понятный пользователю текст или None — ошибка не про базу
    """
    Возвращает понятный пользователю текст ошибки открытия базы при запуске (проход 3, MG7,
    2026-10-18).

    Раньше отказ миграции или заблокированная база вылетали из ``Database.__init__``
    необработанным исключением: в exe без консоли программа молча закрывалась. Функция
    без Qt — её зовёт окно запуска (``interfaces/gui/gui_window/main.py``), её же
    проверяют тесты.

    Обход цепочки ``__cause__`` / ``__context__``: ``DatabaseConnectionError`` (так
    ``Database.__init__`` оборачивает ошибку драйвера с 2026-10-31) — её текст без кода;
    ``MigrationError`` — «нельзя безопасно обновить»; ошибка драйвера SQLAlchemy —
    ``database_error_text``.

    Args:
        exc : (BaseException) Исключение (в том числе обёрнутое).

    Returns:
        (str/None) Текст для сообщения; None — ошибка не про базу (пусть идёт дальше как
        есть).

    Example:
        >>> startup_error_text(
        ...     MigrationError('нет обязательного столбца'),   # отказ миграции
        ... )
        'Базу данных нельзя безопасно обновить: нет обязательного столбца. ...'
        >>> startup_error_text(
        ...     ValueError('x'),   # не про базу
        ... ) is None
        True
    """
    from sqlalchemy.exc import DatabaseError
    from app.exceptions import DatabaseConnectionError

    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:      # обход цепочки причин
        seen.add(id(current))
        if isinstance(current, DatabaseConnectionError): # текст уже собран — без кода [6002]
            return current.detail
        if isinstance(current, MigrationError):
            return (f"Базу данных нельзя безопасно обновить: {current}. "
                    "База не изменена. Обратитесь к разработчику.")
        if isinstance(current, DatabaseError):
            # detail = str(getattr(current, 'orig', None) or current).lower()
            # if 'locked' in detail or 'busy' in detail:
            #     return ("База данных занята другой копией программы (идёт обновление или запись). "
            #             "Закройте другие копии и запустите программу снова.")
            # if 'readonly' in detail or 'read-only' in detail or 'unable to open' in detail:
            #     return ("Нет доступа на запись к файлу базы данных или его папке. "
            #             "Проверьте права и путь к базе в настройках.")
            # return (f"Ошибка базы данных при запуске: {getattr(current, 'orig', None) or current}. "
            #         "Если база обновлялась — рядом с файлом есть резервная копия (.bak-…).")
            # ↑ до 2026-10-31 (М8): разбор — здесь; теперь общий с Database.__init__.
            return database_error_text(
                current,   # ошибка драйвера
            )
        current = current.__cause__ or current.__context__
    return None


def _flat(diffs: Sequence) -> list:
    """
    Отличия autogenerate — плоским списком (изменения столбца приходят списком).

    Args:
        diffs: Результат ``schema_differences``.

    Returns:
        Список элементов.

    Пример:
        >>> _flat([('add_table', t), [('modify_nullable', ...)]])
        [('add_table', t), ('modify_nullable', ...)]
    """
    return [item for diff in diffs for item in (diff if isinstance(diff, list) else [diff])]


def is_safe_addition(
    item : tuple,   # элемент отличий autogenerate
) -> bool: # отличие можно применить автоматически
    """
    Проверяет, можно ли применить отличие автоматически без риска для данных.

    Безопасно: новая таблица, новый индекс, новый столбец — необязательный или со
    значением по умолчанию. Всё остальное (удаление, смена типа или обязательности,
    связи в существующей таблице) — только вручную: например, переименование
    автоматика видит как «удалить + добавить» и потеряла бы данные.

    Триггер (появление, изменение, удаление) безопасен: данные не меняются, в файле миграции
    есть оба текста; что миграция не потеряла триггеры при пересборке, проверяет
    ``generate_migration``.

    Args:
        item : (tuple) Элемент отличий autogenerate.

    Returns:
        (bool) ``True`` — можно автоматически.

    Example:
        >>> is_safe_addition(
        ...     ('add_table', table),   # новая таблица
        ... )
        True
        >>> is_safe_addition(
        ...     ('remove_column', None, 'patients', column),   # удаление столбца
        ... )
        False
    """
    kind = item[0]
    if kind in ('add_table', 'add_index') or kind in sqlite_triggers.TRIGGER_KINDS:
        return True
    if kind == 'add_column':
        column = item[3]
        return bool(column.nullable) or column.server_default is not None
    return False


def unsafe_changes(changes: Sequence) -> list:
    """
    Какие изменения из списка нельзя применить автоматически.

    Уникальный индекс на существующей таблице — небезопасен (A4): повторы в данных.
    Кроме ``is_safe_addition``: новая СВЯЗЬ (внешний ключ) в существующей таблице безопасна,
    если все её столбцы добавляются этими же изменениями (A2, 2026-10-18) — в новых
    столбцах ещё нет данных, нарушить связь нечему. Типичный случай — новый
    необязательный ``doctor_id`` со ссылкой на врачей. SQLite пересоберёт таблицу
    (``render_as_batch``), данные сохранятся.

    Args:
        changes: Плоский список отличий autogenerate.

    Returns:
        Небезопасные элементы (пусто — всё можно автоматически).

    Пример:
        >>> unsafe_changes([('add_column', None, 'appointments', doctor_id), ('add_fk', fk)])
        []
    """
    added_columns = {(item[2], item[3].name) for item in changes
                     if item[0] == 'add_column' and is_safe_addition(item)}
    added_tables = {item[1].name for item in changes if item[0] == 'add_table'}
    result = []
    for item in changes:
        if item[0] == 'add_index' and item[1].unique and item[1].table.name not in added_tables:
            # A4: уникальный индекс на СУЩЕСТВУЮЩЕЙ таблице — при повторах в данных клиники
            # миграция упадёт, и программа перестанет запускаться на этой базе. Что делать
            # с повторами, решает человек (миграция вручную).
            result.append(item)
            continue
        if is_safe_addition(item):
            continue
        if item[0] == 'add_fk':
            constraint = item[1]
            table = constraint.table.name
            if all((table, column.name) in added_columns for column in constraint.columns):
                continue
        result.append(item)
    return result


def pending_model_changes(
    metadata : Optional[sa.MetaData] = None,   # модели; None — модели приложения
) -> list: # отличия моделей от схемы последней миграции
    """
    Возвращает, чем модели отличаются от схемы последней миграции (то, что попало бы в новую
    миграцию), — в том числе появление, изменение и удаление триггера.

    Сравнение — во временной базе в памяти (настоящая база не нужна и не трогается).

    Args:
        metadata : (MetaData/None) Модели; None — ``Base.metadata`` приложения.

    Returns:
        (list) Плоский список отличий autogenerate (пусто — модели = миграции).

    Raises:
        MigrationError: У миграций несколько «голов» (A1).

    Example:
        >>> pending_model_changes()
        []
    """
    head_revision()                 # A1: две «головы» — MigrationError, а не ошибка Alembic
    reference = create_engine('sqlite://')
    try:
        with reference.begin() as conn:
            command.upgrade(alembic_config(conn), 'head')
            return _flat(schema_differences(conn, metadata))
    finally:
        reference.dispose()


def _next_revision_id() -> str:
    """
    Номер новой автомиграции: ``<NNNN>_auto_<ГГГГММДД_ЧЧММСС>`` (латиница — §4 заметок).

    Время в номере — чтобы две ветки разработки не создали одинаковый номер.

    Returns:
        Идентификатор ревизии.

    Пример:
        >>> _next_revision_id()
        '0002_auto_20261018_181500'
    """
    script = ScriptDirectory.from_config(alembic_config())
    n = len(list(script.walk_revisions())) + 1
    return f"{n:04d}_auto_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"


def generate_migration(
    metadata : Optional[sa.MetaData] = None,   # модели; None — модели приложения
    message  : Optional[str] = None,           # заголовок файла
) -> Optional[str]: # путь созданного файла миграции
    """
    Создаёт файл миграции по изменившимся моделям — только если все изменения безопасны.

    Args:
        metadata : (MetaData/None) Модели; None — ``Base.metadata`` приложения.
        message  : (str/None) Заголовок файла (имя файла — номер ревизии); None —
            «Автомиграция: <что меняет>».

    Returns:
        (str/None) Путь созданного файла; None — модели = миграции, создавать нечего.

    Raises:
        MigrationError: Есть небезопасные изменения (переименование, смена типа, удаление…) —
            файл не создаётся, миграцию нужно написать вручную (§4 заметок); описание триггеров
            неверно; созданная миграция теряет триггеры при пересборке таблицы (MG14) — файл
            удаляется.

    Example:
        >>> generate_migration()        # добавили модель — появится versions/0002_auto_….py
        '.../migrations/versions/0002_auto_20261018_181500.py'
    """
    if metadata is None:
        metadata = _default_metadata()
    check_trigger_definitions(
        metadata,   # опечатка в триггере не должна попасть в файл миграции
    )
    changes = pending_model_changes(metadata)
    if not changes:
        return None
    unsafe = unsafe_changes(changes)
    if unsafe:
        raise MigrationError(
            "модели изменены так, что автоматическую миграцию делать нельзя: "
            f"{', '.join(describe_differences(unsafe))} — напишите миграцию вручную "
            "(app/database/IMPLEMENTATION.md §4)"
        )
    rev_id = _next_revision_id()
    if message is None:
        summary = ', '.join(describe_differences(changes))
        message = 'Автомиграция: ' + (summary if len(summary) <= 120 else summary[:117] + '...')
    reference = create_engine('sqlite://')
    try:
        with reference.begin() as conn:
            command.upgrade(alembic_config(conn), 'head')
            cfg = alembic_config(conn, metadata)
            cfg.set_main_option('file_template', '%%(rev)s')
            script = command.revision(cfg, message=message, autogenerate=True, rev_id=rev_id)
    finally:
        reference.dispose()
    path = script.path
    lines = '\n'.join(f"    * {line}" for line in describe_differences(changes))
    with open(path, encoding='utf-8') as f:
        text = f.read()
    text = text.replace('Что меняет и почему: (заполнить)',
                        'Что меняет и почему: создана автоматически (generate_migration, '
                        f'{datetime.date.today().isoformat()}) — только безопасные добавления:\n{lines}', 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    head_revision.cache_clear()
    _refuse_lost_triggers(
        path,       # созданный файл
        metadata,   # модели
    )
    _log.warning(f"Создана автомиграция {rev_id}: {', '.join(describe_differences(changes))} — "
                 f"проверьте и добавьте в git: {path}")
    return path


def _refuse_lost_triggers(
    path     : str,           # созданный файл миграции
    metadata : sa.MetaData,   # модели
) -> None: # созданная автомиграция сохраняет триггеры
    """
    Проверяет применением в памяти, что автомиграция не потеряла триггеры (MG14, 2026-11-07).

    Автомиграция может пересобрать таблицу (новая связь — ``batch_alter_table``): её триггеры
    пропадут молча, а триггер другой таблицы, упоминающий её, уронит переименование. Такой файл
    удаляется — нужна миграция вручную с ``keep_triggers``. В описании нет триггеров — терять
    нечего, проверка не выполняется.

    Args:
        path     : (str) Созданный файл миграции.
        metadata : (MetaData) Модели.

    Raises:
        MigrationError: Триггеры потеряны или миграция на них падает; файл удалён.

    Example:
        >>> _refuse_lost_triggers(
        ...     'versions/0003_auto.py',   # файл
        ...     Base.metadata,             # модели
        ... )
    """
    if not sqlite_triggers.described_triggers(metadata.tables.values()):
        return
    try:
        lost = [
            item
            for item in pending_model_changes(metadata)
            if item[0] in sqlite_triggers.TRIGGER_KINDS
        ]
        reason = ', '.join(describe_differences(lost))
    except sa.exc.DBAPIError as exc:
        reason = str(exc.orig)
    if reason:
        os.remove(path)
        head_revision.cache_clear()
        raise MigrationError(
            f"автоматическая миграция теряет триггеры при пересборке таблицы ({reason}) — "
            "напишите миграцию вручную с keep_triggers (app/database/IMPLEMENTATION.md §12)"
        )


def main(
    argv : Optional[Sequence[str]] = None,   # аргументы; None — sys.argv[1:]
) -> int: # код выхода
    """
    Проверка для сборки: ``python -m app.database.migrate check [--generate]``.

    * ``check`` — у миграций одна «голова» и модели = миграции. Нет — код 1 и список.
    * ``check --generate`` — то же, но безопасные изменения сразу оформляются файлом
      миграции (код всё равно 1: файл нужно просмотреть и добавить в git, затем собрать
      заново). Небезопасные — код 1 и подсказка написать вручную.

    Настоящая база не открывается: сравнение — во временной базе в памяти.

    Args:
        argv : (Sequence[str]/None) Аргументы; None — ``sys.argv[1:]``.

    Returns:
        (int) Код выхода: 0 — всё совпадает, 1 — нет, 2 — неверные аргументы.

    Example:
        >>> main(
        ...     ['check'],   # аргументы
        ... )
        0
    """
    import argparse
    parser = argparse.ArgumentParser(prog='python -m app.database.migrate',
                                     description='Проверка миграций БД для сборки')
    parser.add_argument('command', choices=['check'])
    parser.add_argument('--generate', action='store_true',
                        help='безопасные изменения моделей сразу оформить файлом миграции')
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:   # A3: вывод в файл/канал с однобайтовой кодировкой — не падать на кириллице
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    try:
        head = head_revision()
        check_trigger_definitions()
        changes = pending_model_changes()
    except MigrationError as exc:
        print(f"ОШИБКА миграций: {exc}")
        return 1
    if not changes:
        print(f"Миграции в порядке: модели = миграции, последняя версия {head}")
        return 0
    print("Модели отличаются от миграций:")
    for line in describe_differences(changes):
        print(f"  {line}")
    if args.generate:
        try:
            path = generate_migration()
        except MigrationError as exc:
            print(f"ОШИБКА: {exc}")
            return 1
        print(f"Создана миграция: {path}\nПросмотрите её, добавьте в git и запустите сборку снова.")
    else:
        print("Создайте миграцию (app/database/IMPLEMENTATION.md §4) или запустите с --generate.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
