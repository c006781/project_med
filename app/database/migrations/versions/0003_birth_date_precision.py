# app/database/migrations/versions/0003_birth_date_precision.py

"""
Точность даты рождения пациента

Ревизия: 0003_birth_date_precision
Предыдущая: 0002_photo_files
Создана: 2026-11-07

Что меняет и почему: дата рождения бывает известна не полностью («1999»), а хранилась только
полной датой — 01.01.1999 нельзя было отличить от настоящего первого января, и пациента с годом
нельзя было сравнить с пациентом с точной датой. Рядом с ``birth_date`` появляется
необязательный столбец ``birth_date_precision`` (``day`` / ``month`` / ``year``).

1. Столбец добавляется без пересборки таблицы (``ADD COLUMN``): данные и триггеры не затрагиваются.
2. У строк с датой — полная точность (``day``): это единственное, что о них известно; у строк
   без даты точность остаётся пустой.

``downgrade`` убирает столбец: сами даты на месте, «только год» снова выглядит как 01.01 этого
года — как было до этой миграции.

Правила (app/database/IMPLEMENTATION.md §4): модели приложения НЕ импортировать (они
меняются, миграция — нет): для данных — op.execute / sa.table(); применённую миграцию
не менять и не удалять; downgrade — обратное действие или явный отказ (raise);
пересборка таблицы (batch_alter_table) удаляет её триггеры — оборачивать в
sqlite_triggers.keep_triggers() (§12).
"""

from alembic import op
import sqlalchemy as sa

from app.database import sqlite_triggers
# правило имён ограничений моделей (A2) — постоянное, поэтому его брать можно
from app.database.database_shema.clinic import NAMING_CONVENTION


revision = '0003_birth_date_precision'
down_revision = '0002_photo_files'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Применение миграции: столбец точности, у строк с датой — полная точность.

    Returns:
        None

    Example:
        >>> upgrade()     # вызывает Alembic
    """
    op.add_column(
        'patients',                     # таблица
        sa.Column(
            'birth_date_precision',     # столбец
            sa.String(length=10),       # 'day' / 'month' / 'year'
            nullable    =   True,       # без даты точности нет
            comment     =   'Точность даты рождения: day, month, year',  # как в описании таблицы
        ),
    )
    patients = sa.table(
        'patients',                             # таблица (не модель: модели меняются)
        sa.column('birth_date'),                # дата
        sa.column('birth_date_precision'),      # точность
    )
    op.execute(
        patients.update().where(
            patients.c.birth_date.is_not(None),     # только строки с датой
        ).values(
            birth_date_precision = 'day',           # полная точность
        ),
    )


def downgrade() -> None:
    """
    Откат миграции: столбец точности убирается, даты остаются.

    Returns:
        None

    Example:
        >>> downgrade()   # вызывает Alembic
    """
    with sqlite_triggers.keep_triggers():
        with op.batch_alter_table(
            'patients',                                     # таблица
            naming_convention   =   NAMING_CONVENTION,      # связи — по имени из правила
            recreate            =   'always',               # SQLite 3.34: нет DROP COLUMN
        ) as batch_op:
            batch_op.drop_column('birth_date_precision')
