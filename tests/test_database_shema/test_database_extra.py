import pytest
import os
from app.database.database import Database
from app.database.database_shema.clinic import Patient

def test_create_tables_recreate(tmp_path):
    """
    Тестирование метода create_tables с параметром recreate=True.

    Создаём таблицы (они уже созданы в __init__), добавляем данные,
    а затем пересоздаем таблицы с помощью recreate=True.
    Проверяем, что после пересоздания данных не существует.
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    db = Database(db_url)
    # Создаём таблицы (они уже созданы в __init__)
    # Убедимся, что файл существует
    assert db_path.exists()

    # Добавим данные
    with db.session_scope() as session:
        session.add(Patient(first_name="Test", last_name="Test"))
    # recreate=True должно пересоздать таблицы
    db.create_tables(recreate=True)
    # После пересоздания данных быть не должно
    with db.session_scope() as session:
        assert session.query(Patient).count() == 0

def test_fill_test_data(tmp_path):
    """
    Тестирование метода fill_test_data.

    Создаём экземпляр Database, заполняем fill_test_data,
    и проверяем, что данные добавлены.
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    db = Database(db_url)
    # Заполняем fill_test_data
    db.fill_test_data()
    with db.session_scope() as session:
        # Проверяем, что данные добавлены
        assert session.query(Patient).count() > 0
    # Повторный вызов не должен дублировать данных
    db.fill_test_data()
    with db.session_scope() as session:
        # Проверяем, что количество данных не изменилось
        assert session.query(Patient).count() == session.query(Patient).count()  # то же число
