# tests/test_database_shema/test_photo_files.py

"""
Файлы фото — отдельная таблица (Ф1.6.7б, решение владельца В-3; шаг 1): строка
``photo_files`` — файл в папке фото (ключ — путь от папки), ``photos.file_path`` — внешний
ключ на неё; на один файл — несколько фото; файл без ссылок убирает сборщик мусора.

Проверяется: описание (ключ-столбец, внешний ключ на столбец), миграция 0002 на старой базе
(заполнение, связь, индекс, откат без потерь), внешний ключ и сборщик на ``Database``.
"""

from datetime import date
from pathlib import Path
from typing import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

from app.database.database import Database
from app.database.database_shema.clinic import Appointment, Patient, Photo, PhotoFile
from app.database.migrate import BASELINE, current_revision, schema_at, upgrade_database
from app.exceptions import DbIntegrityError
from app.schema.clinic import PHOTO_FILES, PHOTOS
from app.schema.define import KEEP_USED, column


# ---------------------------------------------------------------------- описание

def test_photo_files_def_key_is_file_path():
    """Ключ таблицы файлов — путь файла (строка), «только используемые», без автоувеличения."""
    table = PhotoFile.__table__
    assert [c.name for c in table.primary_key.columns] == ['file_path']
    assert isinstance(table.c.file_path.type, sa.String)
    assert PHOTO_FILES.keep == KEEP_USED
    assert PhotoFile.__table_def__ is PHOTO_FILES


def test_photo_file_path_references_photo_files():
    """photos.file_path — внешний ключ на photo_files.file_path, индекс, связь file."""
    column_ = Photo.__table__.c.file_path
    assert [fk.target_fullname for fk in column_.foreign_keys] == ['photo_files.file_path']
    assert 'ix_photo_file_path' in {i.name for i in Photo.__table__.indexes}
    assert Photo.__mapper__.relationships['file'].mapper.class_ is PhotoFile
    assert PHOTOS.build_config()['file_path']['widget_type'] == 'image_thumbnail'   # окна — как было


def test_column_relation_needs_reference():
    """Связь без внешнего ключа — ошибка описания сразу, не при сборке модели."""
    with pytest.raises(ValueError, match='references'):
        column(
            'file_path',                    # имя
            sa.String(10),                  # тип
            'Файл',                         # подпись
            relation    =   'file',         # связь без внешнего ключа
        )


def test_primary_key_column_is_not_nullable():
    spec = column(
        'code',                             # имя
        sa.String(10),                      # тип
        'Код',                              # подпись
        primary_key =   True,               # ключ
    )
    assert spec.primary_key and not spec.nullable


# ---------------------------------------------------------------------- миграция 0002

def _legacy_with_photos(tmp_path: Path):
    """Старая база (схема 0001, без отметки версии) с фото: два фото на один путь."""
    path = tmp_path / 'legacy.db'
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    schema_at(BASELINE).create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))
        conn.execute(text("INSERT INTO appointments (id, patient_id, date) VALUES (1, 1, '2026-01-01')"))
        conn.execute(text("INSERT INTO appointments (id, patient_id, date) VALUES (2, 1, '2026-01-02')"))
        conn.execute(text(
            "INSERT INTO photos (id, appointment_id, file_path, uploaded_at) VALUES "
            "(1, 1, 'app_1\\a.jpg', '2026-01-01 10:00:00'), "      # путь Windows — как есть
            "(2, 2, 'app_1\\a.jpg', '2025-12-31 09:00:00'), "      # тот же файл, раньше
            "(3, 2, 'app_2/b.jpg', NULL)"
        ))
    return path, engine


def test_migration_fills_photo_files_from_photos(tmp_path):
    path, engine = _legacy_with_photos(tmp_path)
    upgrade_database(engine)
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT file_path, created_at FROM photo_files ORDER BY file_path')).all()
        photos = conn.execute(text('SELECT id, file_path FROM photos ORDER BY id')).all()
    assert rows == [('app_1\\a.jpg', '2025-12-31 09:00:00'), ('app_2/b.jpg', None)]   # по строке на путь
    assert photos == [(1, 'app_1\\a.jpg'), (2, 'app_1\\a.jpg'), (3, 'app_2/b.jpg')]  # фото не тронуты
    fks = inspect(engine).get_foreign_keys('photos')
    assert {fk['name']: fk['referred_table'] for fk in fks}['fk_photos_file_path_photo_files'] == 'photo_files'
    assert 'ix_photo_file_path' in {i['name'] for i in inspect(engine).get_indexes('photos')}
    with engine.connect() as conn:
        assert conn.execute(text('PRAGMA foreign_key_check')).all() == []


def test_migration_downgrade_keeps_photos(tmp_path):
    from alembic import command
    from app.database.migrate import alembic_config
    path, engine = _legacy_with_photos(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), BASELINE)
    assert current_revision(engine) == BASELINE
    assert 'photo_files' not in inspect(engine).get_table_names()
    assert inspect(engine).get_foreign_keys('photos')[0]['referred_table'] == 'appointments'
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM photos')).scalar() == 3


# ---------------------------------------------------------------------- база приложения

@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite:///{(tmp_path / 'photos.db').as_posix()}")
    yield database
    database.close()


def _appointments(db: Database) -> tuple:
    with db.session_scope() as s:
        patient = Patient(last_name='Петров', first_name='Иван')
        s.add(patient)
        s.flush()
        first = Appointment(patient_id=patient.id, date=date(2026, 11, 1))
        second = Appointment(patient_id=patient.id, date=date(2026, 11, 2))
        s.add_all([first, second])
        s.flush()
        return first.id, second.id


def _file_rows(db: Database) -> list:
    with db.session_scope() as s:
        return sorted(s.scalars(sa.select(PhotoFile.file_path)))


def test_photo_without_file_row_rejected(db):
    first, _ = _appointments(db)
    with pytest.raises(DbIntegrityError):
        with db.session_scope() as s:
            s.add(Photo(appointment_id=first, file_path='нет_такого.jpg'))


def test_file_row_written_before_photo_by_relation(db):
    """Фото и строка файла в одной транзакции, фото добавлено первым — порядок по связи."""
    first, _ = _appointments(db)
    with db.session_scope() as s:
        s.add(Photo(appointment_id=first, file_path='a.jpg'))
        s.add(PhotoFile(file_path='a.jpg'))
    assert _file_rows(db) == ['a.jpg']


def test_shared_file_kept_until_last_link_removed(db):
    """Два фото (приёма) на один файл: удалили одно — файл в базе; удалили второе — убран."""
    first, second = _appointments(db)
    with db.session_scope() as s:
        shared = PhotoFile(file_path='общий.jpg')
        s.add_all([
            Photo(appointment_id=first, file=shared),
            Photo(appointment_id=second, file=shared),
        ])
    with db.session_scope() as s:
        s.delete(s.scalars(sa.select(Photo).where(Photo.appointment_id == first)).one())
    assert _file_rows(db) == ['общий.jpg']
    with db.session_scope() as s:
        s.delete(s.scalars(sa.select(Photo)).one())
    assert _file_rows(db) == []


def test_move_photo_keeps_file(db):
    """Перенос фото в другой приём — меняется только связь, строка файла на месте."""
    first, second = _appointments(db)
    with db.session_scope() as s:
        s.add(Photo(appointment_id=first, file=PhotoFile(file_path='x.jpg')))
    with db.session_scope() as s:
        s.scalars(sa.select(Photo)).one().appointment_id = second
    assert _file_rows(db) == ['x.jpg']


def test_rolled_back_delete_keeps_file_row(db):
    first, _ = _appointments(db)
    with db.session_scope() as s:
        s.add(Photo(appointment_id=first, file=PhotoFile(file_path='y.jpg')))
    with pytest.raises(RuntimeError):
        with db.session_scope() as s:
            s.delete(s.scalars(sa.select(Photo)).one())
            raise RuntimeError('отмена')
    assert _file_rows(db) == ['y.jpg']
