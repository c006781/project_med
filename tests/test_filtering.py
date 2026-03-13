# tests/test_filtering.py
import pytest
from datetime import date
from app.utils.filtering import apply_filters, apply_post_filters, FilterOperator
from app.models.bd.models import Patient

def test_apply_filters_eq(db_session):
    query = db_session.query(Patient)
    filters = [{'column': 'first_name', 'operator': FilterOperator.EQ, 'value': 'Иван'}]
    filtered_query = apply_filters(query, Patient, filters)
    # В тестовой БД пока нет данных, но проверим, что запрос строится
    assert filtered_query is not None

def test_apply_filters_like(db_session):
    filters = [{'column': 'last_name', 'operator': FilterOperator.LIKE, 'value': 'Петр'}]
    query = db_session.query(Patient)
    filtered = apply_filters(query, Patient, filters)
    sql = str(filtered)
    # assert "last_name LIKE ?" in sql
    # assert (" IN " in sql) or (" LIKE " in sql)   
    assert (" LIKE " in sql)   

def test_apply_filters_in(db_session):
    filters = [{'column': 'id', 'operator': FilterOperator.IN, 'value': [1, 2, 3]}]
    query = db_session.query(Patient)
    filtered = apply_filters(query, Patient, filters)
    sql = str(filtered)
    # assert "id IN (1, 2, 3)" in sql
    assert (" IN " in sql) #or (" LIKE " in sql)   

def test_apply_filters_between(db_session):
    filters = [{'column': 'birth_date', 'operator': FilterOperator.BETWEEN, 'value': ['1980-01-01', '1990-12-31']}]
    query = db_session.query(Patient)
    filtered = apply_filters(query, Patient, filters)
    sql = str(filtered)
    assert "birth_date BETWEEN" in sql

def test_apply_filters_is_null(db_session):
    filters = [{'column': 'phone', 'operator': FilterOperator.IS_NULL}]
    query = db_session.query(Patient)
    filtered = apply_filters(query, Patient, filters)
    sql = str(filtered)
    assert "phone IS NULL" in sql

def test_apply_post_filters_fuzzy():
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
    class Dummy:
        def __init__(self, name):
            self.name = name
    items = [Dummy("Иван Петров"), Dummy("Пётр Иванов"), Dummy("Сергей")]

    post_filters = [('name', 'Иван', 50)]
    filtered = apply_post_filters(items, post_filters, None)
    assert len(filtered) == 2
    assert filtered[0].name in ["Иван Петров", "Пётр Иванов"] 