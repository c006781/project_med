# tests/test_database_shema/test_foreign_keys.py

"""
Р-2 (Ф1.6.7г, шаг 5): основной движок ``Database`` проверяет внешние ключи SQLite
(``PRAGMA foreign_keys=ON``) — висячая ссылка не проходит молча, в том числе при ошибке
сборщика мусора; ``Database(foreign_keys=False)`` — как раньше.
"""

from datetime import date
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import text

import app.database.table_events as te
from app.database.database import Database
from app.database.database_shema.clinic import Appointment, AppointmentNote, Patient
from app.exceptions import DbIntegrityError


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(f"sqlite:///{(tmp_path / 'fk.db').as_posix()}")
    yield database
    database.close()


def _patient_with_note(db: Database) -> None:
    with db.session_scope() as s:
        note = AppointmentNote(text='общая')
        patient = Patient(last_name='Петров', first_name='Иван')
        s.add_all([note, patient])
        s.flush()
        s.add(Appointment(patient_id=patient.id, date=date(2026, 11, 1), reason_id=note.id))


def test_pragma_is_on(db):
    with db.session_scope() as s:
        assert s.execute(text('PRAGMA foreign_keys')).scalar() == 1


def test_dangling_reference_rejected(db):
    with pytest.raises(DbIntegrityError, match='нет связанной записи'):
        with db.session_scope() as s:
            s.add(Appointment(patient_id=999, date=date(2026, 11, 1)))


def test_delete_of_referenced_note_rejected(db):
    _patient_with_note(db)
    with pytest.raises(DbIntegrityError):
        with db.session_scope() as s:
            s.execute(text('DELETE FROM appointments_notes'))   # мимо ORM — только проверка базы
    with db.session_scope() as s:
        assert s.query(AppointmentNote).count() == 1


def test_flag_off_keeps_old_behaviour(tmp_path):
    database = Database(
        f"sqlite:///{(tmp_path / 'off.db').as_posix()}",
        foreign_keys    =   False,      # как до 2026-11-01
    )
    try:
        with database.session_scope() as s:
            assert s.execute(text('PRAGMA foreign_keys')).scalar() == 0
            s.add(Appointment(patient_id=999, date=date(2026, 11, 1)))
    finally:
        database.close()


def test_collector_error_caught_by_database(db, monkeypatch):
    """Сборщик ошибочно счёл используемую заметку ненужной — база не даст её удалить."""
    _patient_with_note(db)
    other = None
    with db.session_scope() as s:
        other = AppointmentNote(text='вторая')
        s.add(other)
        s.flush()
        other = other.id
        s.add(Patient(last_name='Сидоров', first_name='Пётр', comment_id=other))
    monkeypatch.setattr(
        te.TableEvents,
        '_unused',
        lambda self, session, table, ids, existing: [1],        # «ошибка»: заметка 1 занята
    )
    with pytest.raises(DbIntegrityError):
        with db.session_scope() as s:
            s.get(Patient, 2).comment_id = None                 # кандидат — заметка 2
    with db.session_scope() as s:
        assert s.query(AppointmentNote).count() == 2            # откат, ничего не удалено
