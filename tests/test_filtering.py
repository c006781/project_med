# tests/test_filtering.py
import pytest
from datetime import date
from app.utils.filtering.filtering import apply_filters, apply_post_filters, FilterOperator
from app.database.database_shema.clinic import Patient

def test_apply_filters_eq(db_session):
    """
    Тест на равенство фильтрации.
    Проверяем, что запрос с фильтром равенства строится.
    """
    query = db_session.query(Patient)
    filters = [
        {
            'column': 'first_name', 
            'operator': FilterOperator.EQ, 
            'value': 'Иван'
        }
    ]
    filtered_query , _= apply_filters(query, Patient, filters)
    # В тестовой БД пока нет данных, но проверим, что запрос строится
    assert filtered_query is not None

def test_apply_filters_like(db_session):
    """
    Тест на фильтрацию LIKE.
    Проверяем, что запрос с фильтром LIKE строится.
    """
    filters = [
        {
            'column': 'last_name', 
            'operator': FilterOperator.LIKE, 
            'value': 'Петр'
        }
    ]
    query = db_session.query(Patient)
    filtered , _= apply_filters(query, Patient, filters)
    sql = str(filtered)
    # assert "last_name LIKE ?" in sql
    # assert (" IN " in sql) or (" LIKE " in sql)   
    assert (" LIKE " in sql)   

def test_apply_filters_in(db_session):
    """
    Тест на фильтрацию IN.
    Проверяем, что запрос с фильтром IN строится.
    """
    filters = [{'column': 'id', 'operator': FilterOperator.IN, 'value': [1, 2, 3]}]
    query = db_session.query(Patient)
    filtered , _= apply_filters(query, Patient, filters)
    sql = str(filtered)
    # assert "id IN (1, 2, 3)" in sql
    assert (" IN " in sql) #or (" LIKE " in sql)   

def test_apply_filters_between(db_session):
    """
    Тест на фильтрацию BETWEEN.
    Проверяем, что запрос с фильтром BETWEEN строится.
    """
    filters = [{'column': 'birth_date', 'operator': FilterOperator.BETWEEN, 'value': ['1980-01-01', '1990-12-31']}]
    query = db_session.query(Patient)
    filtered , _= apply_filters(query, Patient, filters)
    sql = str(filtered)
    assert "birth_date BETWEEN" in sql

def test_apply_filters_is_null(db_session):
    """
    Тест на фильтрацию IS NULL.
    Проверяем, что запрос с фильтром IS NULL строится.
    """
    filters = [{'column': 'phone', 'operator': FilterOperator.IS_NULL}]
    query = db_session.query(Patient)
    filtered , _= apply_filters(query, Patient, filters)
    sql = str(filtered)
    assert "phone IS NULL" in sql

def test_apply_post_filters_fuzzy():
    """
    Тест на фильтрацию с нечетким поиском (fuzzy).
    Проверяем, что фильтр с нечетким поиском возвращает ожидаемый результат.
    """
    class Dummy:
        def __init__(self, name):
            self.name = name
    items = [        
        Dummy("Иван Петров"),   # должен пройти фильтр
        Dummy("Пётр Сидоров"),  # не должен пройти
        Dummy("Сергей"),        # не должен пройти
    ]

    post_filters = [('name', 'Ивн', 40)]
    filtered = apply_post_filters(items, post_filters, None)
    assert len(filtered) == 1
    assert filtered[0].name == "Иван Петров"

def test_apply_post_filters_fuzzy2():
    """
    Тест на фильтрацию с нечетким поиском (fuzzy) со множественным результатом.
    Проверяем, что фильтр с нечетким поиском возвращает ожидаемый результат.
    """
    class Dummy:
        def __init__(self, name):
            self.name = name
    items = [Dummy("Иван Петров"), Dummy("Пётр Иванов"), Dummy("Сергей")]

    post_filters = [('name', 'Иван', 50)]
    filtered = apply_post_filters(items, post_filters, None)
    assert len(filtered) == 2
    assert filtered[0].name in ["Иван Петров", "Пётр Иванов"] 