# tests/test_temp_data_bd.py
import pytest
from app.database.database_shema.temp_data_bd import generate_test_data, populate_test_data
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo

def test_populate_test_data(db_session):
    """
    Тест на заполнение БД тестовыми данными.

    БД пустая, заполняем тестовыми данными и проверяем, что в БД есть данные.
    """
    # БД пустая
    populate_test_data(db_session)
    # Проверяем, что в БД есть данные
    assert db_session.query(Patient).count() > 0
    assert db_session.query(Appointment).count() > 0
    assert db_session.query(AppointmentNote).count() > 0
    assert db_session.query(Photo).count() > 0

def test_populate_test_data_idempotent(db_session):
    """
    Тест на то, что при повторном вызове populate_test_data не добавляется новых данных.

    Populate_test_data вызывается два раза, и после каждого вызова проверяем,
    что количество пациентов не изменилось.
    """
    # При повторном вызове не должно добавляться новых данных
    populate_test_data(db_session)
    # Проверяем, что количество пациентов не изменилось
    count_patients = db_session.query(Patient).count()
    populate_test_data(db_session)
    assert db_session.query(Patient).count() == count_patients

def test_generate_test_data(tmp_path):
    """
    Тест на функцию generate_test_data.

    Создаём файл БД, создаём таблицы, заполняем тестовыми данными и
    проверяем, что в БД есть данные.
    """
    db_path = tmp_path / "test.db"
    from app.database.database_shema.clinic import create_db
    # Создаём файл БД
    create_db(str(db_path), recreate=True)
    # Заполняем тестовыми данными
    generate_test_data(str(db_path))
    # Подключаемся к БД
    from sqlalchemy import create_engine
    engine = create_engine(
        f"sqlite:///{db_path}",
        # connect_args={"check_same_thread": False},
    )
    # Создаём сессию
    from app.database.database_shema.clinic import Base
    Base.metadata.create_all(engine)  # таблицы уже должны быть созданы, но для проверки
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    # Проверяем, что в БД есть данные
    assert session.query(Patient).count() > 0
    # Закрываем сессию
    session.close()
