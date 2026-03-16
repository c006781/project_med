# tests/test_temp_data_bd.py
import pytest
from app.database.database_shema.temp_data_bd import generate_test_data, populate_test_data
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo

def test_populate_test_data(db_session):
    # БД пустая
    populate_test_data(db_session)
    assert db_session.query(Patient).count() > 0
    assert db_session.query(Appointment).count() > 0
    assert db_session.query(AppointmentNote).count() > 0
    assert db_session.query(Photo).count() > 0

def test_populate_test_data_idempotent(db_session):
    # При повторном вызове не должно добавляться новых данных
    populate_test_data(db_session)
    count_patients = db_session.query(Patient).count()
    populate_test_data(db_session)
    assert db_session.query(Patient).count() == count_patients

def test_generate_test_data(tmp_path):
    db_path = tmp_path / "test.db"
    from app.database.database_shema.clinic import create_db
    create_db(str(db_path), recreate=True)  # создаём таблицы
    generate_test_data(str(db_path))
    from sqlalchemy import create_engine
    engine = create_engine(
        f"sqlite:///{db_path}",
        # connect_args={"check_same_thread": False},
    )
    from app.database.database_shema.clinic import Base
    Base.metadata.create_all(engine)  # таблицы уже должны быть созданы, но для проверки
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    assert session.query(Patient).count() > 0
    session.close()