# app/database/migrations/env.py

"""
Окружение Alembic для миграций БД приложения.

Запускается Alembic'ом (не импортируется приложением напрямую). Соединение берётся:
    * из ``config.attributes['connection']`` — так вызывает ``app.database.migrate``
      (приложение, тесты): миграции идут в том же соединении;
    * иначе из ``sqlalchemy.url`` конфигурации — запуск из консоли
      (``alembic -c app/database/migrations/alembic.ini upgrade head``).

``render_as_batch=True``: SQLite почти не умеет ALTER TABLE — Alembic пересобирает таблицу
(создать новую → скопировать → заменить). ``compare_type=True``: изменение типа столбца
тоже считается отличием модели от миграций.

Пример:
    >>> from app.database.migrate import upgrade_database
    >>> upgrade_database(engine)        # Alembic выполнит этот файл
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database.database_shema.clinic import Base

config = context.config
# target_metadata = Base.metadata
# ↑ до 2026-10-18: всегда модели приложения. Теперь их можно передать (generate_migration,
#   тесты) через config.attributes['target_metadata']; по умолчанию — как раньше.
target_metadata = config.attributes.get('target_metadata', Base.metadata)


def _configure(connection) -> None:
    """
    Настраивает контекст миграций на соединение.

    Args:
        connection: Соединение SQLAlchemy.

    Returns:
        None

    Пример:
        >>> _configure(connection)
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    """
    Режим «без БД» (генерация SQL-скрипта): ``alembic upgrade head --sql``.

    Returns:
        None

    Пример:
        >>> run_migrations_offline()
    """
    context.configure(
        url=config.get_main_option('sqlalchemy.url'),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Обычный режим: миграции в соединении приложения (или по ``sqlalchemy.url``).

    Returns:
        None

    Пример:
        >>> run_migrations_online()
    """
    connection = config.attributes.get('connection')
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = engine_from_config(config.get_section(config.config_ini_section, {}),
                                prefix='sqlalchemy.', poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
