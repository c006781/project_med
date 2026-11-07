# tests/test_database_shema/test_birth_precision_migration.py

"""Миграция 0003: точность даты рождения на старой базе, собранной по 0002 (Ф1.6.10е)."""

import datetime

import sqlalchemy as sa
from alembic import command

from app.database.migrate import alembic_config, current_revision, head_revision, upgrade_database

REVISION = '0003_birth_date_precision'
PREVIOUS = '0002_photo_files'


def _db_at_0002(tmp_path):
    """База файлом, доведённая Alembic до 0002, с данными во всех таблицах."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'clinic.db'}")
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), PREVIOUS)
        conn.execute(sa.text("INSERT INTO appointments_notes (id, text) VALUES (1, 'аллергия')"))
        conn.execute(sa.text(
            "INSERT INTO patients (id, first_name, last_name, birth_date, phone, description_id) VALUES "
            "(1, 'Иван', 'Петров', '1985-06-14', '+7', 1), "
            "(2, 'Анна', 'Смирнова', NULL, NULL, NULL), "
            "(3, 'Олег', 'Ким', '1999-01-01', NULL, NULL)"
        ))
        conn.execute(sa.text("INSERT INTO appointments (id, patient_id, date) VALUES (10, 1, '2026-01-02')"))
        conn.execute(sa.text("INSERT INTO photo_files (file_path) VALUES ('a.png')"))
        conn.execute(sa.text("INSERT INTO photos (id, appointment_id, file_path) VALUES (20, 10, 'a.png')"))
    return engine


def _rows(engine, table, columns):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa.text(f"SELECT {columns} FROM {table} ORDER BY 1"))]


def test_upgrade_old_db_keeps_data_and_sets_full_precision(tmp_path):
    engine = _db_at_0002(tmp_path)
    before = {
        'patients': _rows(engine, 'patients', 'id, first_name, last_name, birth_date, phone, description_id'),
        'appointments': _rows(engine, 'appointments', 'id, patient_id, date'),
        'photos': _rows(engine, 'photos', 'id, appointment_id, file_path'),
        'photo_files': _rows(engine, 'photo_files', 'file_path'),
        'appointments_notes': _rows(engine, 'appointments_notes', 'id, text'),
    }

    assert upgrade_database(engine) == head_revision()

    assert current_revision(engine) == head_revision()
    assert before['patients'] == _rows(engine, 'patients', 'id, first_name, last_name, birth_date, phone, description_id')
    assert before['appointments'] == _rows(engine, 'appointments', 'id, patient_id, date')
    assert before['photos'] == _rows(engine, 'photos', 'id, appointment_id, file_path')
    assert before['photo_files'] == _rows(engine, 'photo_files', 'file_path')
    assert before['appointments_notes'] == _rows(engine, 'appointments_notes', 'id, text')
    # у строк с датой — полная точность (в том числе 1 января: о ней ничего другого не известно)
    assert _rows(engine, 'patients', 'id, birth_date_precision') == [(1, 'day'), (2, None), (3, 'day')]
    # резервная копия перед миграцией
    assert list(tmp_path.glob('clinic.db.bak-*'))
    engine.dispose()


def test_upgraded_column_same_as_model(tmp_path):
    """Столбец базы совпадает с моделью (всю схему сравнивает test_models_match_migrations)."""
    from app.database.database_shema.clinic import Patient

    engine = _db_at_0002(tmp_path)
    upgrade_database(engine)
    [column] = [c for c in sa.inspect(engine).get_columns('patients') if c['name'] == 'birth_date_precision']
    model = Patient.__table__.c.birth_date_precision
    assert column['nullable'] is model.nullable
    assert str(column['type']) == str(model.type)
    engine.dispose()


def test_downgrade_keeps_dates(tmp_path):
    engine = _db_at_0002(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE patients SET birth_date_precision = 'year' WHERE id = 3"))
        command.downgrade(alembic_config(conn), PREVIOUS)
    inspector = sa.inspect(engine)
    assert 'birth_date_precision' not in [c['name'] for c in inspector.get_columns('patients')]
    assert _rows(engine, 'patients', 'id, birth_date') == [(1, '1985-06-14'), (2, None), (3, '1999-01-01')]
    assert _rows(engine, 'appointments', 'id, patient_id') == [(10, 1)]
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), REVISION)
    assert _rows(engine, 'patients', 'id, birth_date_precision') == [(1, 'day'), (2, None), (3, 'day')]
    engine.dispose()


def test_upgraded_db_is_readable_by_orm(tmp_path):
    from sqlalchemy.orm import Session

    from app.database.database_shema.clinic import Patient

    engine = _db_at_0002(tmp_path)
    upgrade_database(engine)
    with Session(engine) as session:
        patient = session.get(Patient, 1)
        assert patient.birth_date == datetime.date(1985, 6, 14)
        assert patient.birth_date_precision == 'day'
    engine.dispose()
