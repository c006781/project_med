# app/database/migrations/versions/0002_photo_files.py

"""
Файлы фото — отдельная таблица, фото ссылаются на файл

Ревизия: 0002_photo_files
Предыдущая: 0001_baseline
Создана: 2026-11-01

Что меняет и почему: раньше путь файла был просто строкой фото — файл принадлежал одной
строке, удаление фото удаляло файл. Теперь файл — строка таблицы ``photo_files`` (ключ —
путь от папки фото), ``photos.file_path`` — внешний ключ на неё: на один файл могут
ссылаться несколько фото (приёмов), файл без ссылок убирает сборщик мусора приложения.

1. ``photo_files`` создаётся и заполняется всеми путями из ``photos`` (по одному на путь,
   время добавления — самое раннее у фото с этим путём). Файлы на диске не трогаются:
   перенос из папок приёмов в общую папку делает приложение (папку фото миграция не знает).
2. ``photos`` пересобирается (SQLite): внешний ключ ``fk_photos_file_path_photo_files`` и
   индекс ``ix_photo_file_path`` (поиск ссылок на файл). Внешние ключи на время миграции
   выключены, после — проверка новых висячих ссылок (MG10); их нет — каждый путь уже в
   ``photo_files``.

``downgrade`` — без потерь: пути остаются в ``photos``, ``photo_files`` удаляется.

Правила (app/database/IMPLEMENTATION.md §4): модели приложения НЕ импортировать (они
меняются, миграция — нет): для данных — op.execute / sa.table(); применённую миграцию
не менять и не удалять; downgrade — обратное действие или явный отказ (raise).
"""

from alembic import op
import sqlalchemy as sa

# правило имён ограничений моделей (A2) — постоянное, поэтому его брать можно
from app.database.database_shema.clinic import NAMING_CONVENTION


revision = '0002_photo_files'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Применение миграции: таблица файлов, её заполнение, ссылка фото на файл.

    Returns:
        None

    Example:
        >>> upgrade()     # вызывает Alembic
    """
    op.create_table(
        'photo_files',
        sa.Column('file_path', sa.String(length=500), nullable=False, comment='Путь к файлу от папки фото'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='Дата и время добавления файла'),
        sa.PrimaryKeyConstraint('file_path'),
        comment='Файлы фотографий (имя в папке фото)',
    )
    # каждый путь фото — строка файла (время — самое раннее у фото с этим путём)
    op.execute(
        "INSERT INTO photo_files (file_path, created_at) "
        "SELECT file_path, MIN(uploaded_at) FROM photos GROUP BY file_path"
    )
    with op.batch_alter_table(
        'photos',                                       # таблица
        naming_convention   =   NAMING_CONVENTION,      # имя новой связи по правилу
        recreate            =   'always',               # SQLite: связь — только пересборкой
    ) as batch_op:
        batch_op.create_foreign_key(
            'fk_photos_file_path_photo_files',          # имя по правилу
            'photo_files',                              # цель
            ['file_path'],                              # столбец фото
            ['file_path'],                              # ключ файла
        )
        batch_op.create_index('ix_photo_file_path', ['file_path'], unique=False)


def downgrade() -> None:
    """
    Откат миграции: ссылка и индекс убираются, таблица файлов удаляется (пути — в фото).

    Returns:
        None

    Example:
        >>> downgrade()   # вызывает Alembic
    """
    with op.batch_alter_table(
        'photos',                                       # таблица
        naming_convention   =   NAMING_CONVENTION,      # связь — по имени из правила
        recreate            =   'always',               # SQLite: пересборка
    ) as batch_op:
        batch_op.drop_index('ix_photo_file_path')
        batch_op.drop_constraint('fk_photos_file_path_photo_files', type_='foreignkey')
    op.drop_table('photo_files')
