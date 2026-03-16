# tests/test_database.py
import pytest
from app.database.database import Database
from app.database.database_shema.clinic import Base

from sqlalchemy import text

def test_database_initialization(tmp_path):
    """Проверка создания экземпляра Database и подключения."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    db = Database(db_url)
    assert db.engine is not None
    assert db.Session is not None
    # Проверяем, что таблицы созданы
    with db.session_scope() as session:
        # Должна быть возможность выполнить запрос
        session.execute(text("SELECT 1"))
    db.close()

def test_session_scope_commit(tmp_path):
    """Проверка, что session_scope коммитит изменения."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    db = Database(db_url)
    from app.database.database_shema.clinic import Patient
    with db.session_scope() as session:
        patient = Patient(first_name="Иван", last_name="Петров")
        session.add(patient)
    # После выхода из контекста данные должны быть в БД
    with db.session_scope() as session:
        assert session.query(Patient).count() == 1
    db.close()

def test_session_scope_rollback_on_error(tmp_path):
    """Проверка отката транзакции при ошибке."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    db = Database(db_url)
    from app.database.database_shema.clinic import Patient
    try:
        with db.session_scope() as session:
            patient = Patient(first_name="Иван", last_name="Петров")
            session.add(patient)
            raise ValueError("Тестовая ошибка")
    except ValueError:
        pass
    # Данные не должны быть сохранены
    with db.session_scope() as session:
        assert session.query(Patient).count() == 0
    db.close()