# tests/test_filtering_review_pass1.py

"""
Тесты исправлений проверки модуля app.utils.filtering, проход 1 (2026-10-21).

Номера (FL1 …) — журнал проверок в ``app/utils/filtering/IMPLEMENTATION.md``.
Запросы выполняются на настоящей SQLite в памяти.
"""

import datetime
import doctest
import warnings

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, declarative_base

import app.utils.filtering.filtering as filtering
from app.utils.filtering.filtering import _convert_value, apply_filters, escape_like, like_condition

Base = declarative_base()


class Item(Base):
    """Таблица для проверки фильтров."""
    __tablename__ = 'items'
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String)
    day = sa.Column(sa.Date)
    at = sa.Column(sa.Time)
    price = sa.Column(sa.Float)


@pytest.fixture
def session():
    """SQLite в памяти с тремя записями."""
    engine = sa.create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add_all([
            Item(id=1, name='a_b', day=datetime.date(2026, 1, 1), at=datetime.time(9, 30), price=1.5),
            Item(id=12, name='Иван', day=datetime.date(2026, 5, 1), at=datetime.time(14, 0, 15), price=10.0),
            Item(id=3, name=None, day=None, at=None, price=None),
        ])
        sess.commit()
        yield sess


def ids(session, filters):
    """id записей, прошедших фильтр (без предупреждений SQLAlchemy)."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        query, _ = apply_filters(session.query(Item), Item, filters)
        return sorted(item.id for item in query.all())


# FL1 — «содержит» по нестроковому столбцу

def test_fl1_ilike_on_integer(session):
    """Поиск «1» по id — по тексту (раньше AttributeError)."""
    assert ids(session, [{'column': 'id', 'operator': 'ilike', 'value': '1'}]) == [1, 12]


def test_fl1_like_on_integer_value_int(session):
    """Число в значении — тоже по тексту."""
    assert ids(session, [{'column': 'id', 'operator': 'like', 'value': 2}]) == [12]


def test_fl1_ilike_on_date(session):
    """«Содержит» по дате — по тексту ISO."""
    assert ids(session, [{'column': 'day', 'operator': 'ilike', 'value': '2026-05'}]) == [12]


def test_fl1_ilike_on_float(session):
    """«Содержит» по дробному числу."""
    assert ids(session, [{'column': 'price', 'operator': 'ilike', 'value': '.5'}]) == [1]


def test_fl1_string_column_not_cast():
    """Строковый столбец — без CAST."""
    assert 'CAST' not in str(like_condition(Item.name, 'x'))
    assert 'CAST' in str(like_condition(Item.id, 'x'))


# FL2 — None и экранирование

def test_fl2_ilike_none(session):
    """None — как пустая строка: все непустые (раньше AttributeError)."""
    assert ids(session, [{'column': 'name', 'operator': 'ilike', 'value': None}]) == [1, 12]


@pytest.mark.parametrize('value, expected', [(None, ''), (5, '5'), ('a%b_c', 'a\\%b\\_c'), ('\\', '\\\\')])
def test_fl2_escape_like(value, expected):
    """escape_like: None, число, спецсимволы."""
    assert escape_like(value) == expected


def test_fl2_underscore_literal(session):
    """'_' ищется как символ, а не «любой символ»."""
    assert ids(session, [{'column': 'name', 'operator': 'ilike', 'value': '_'}]) == [1]


def test_fl2_case_insensitive_cyrillic_ascii(session):
    """ilike без учёта регистра (латиница — SQLite)."""
    assert ids(session, [{'column': 'name', 'operator': 'ilike', 'value': 'A_B'}]) == [1]


# FL3 — пустые and/or

@pytest.mark.parametrize('node', [{'and': []}, {'or': []}, {'and': [{'or': []}]}])
def test_fl3_empty_groups_no_warning_all_rows(session, node):
    """Пустые группы — все записи, без устаревшего вызова (warning → ошибка в ids)."""
    assert ids(session, node) == [1, 3, 12]


def test_fl3_or_still_works(session):
    """Непустое 'or' — как раньше."""
    node = {'or': [{'column': 'id', 'operator': 'eq', 'value': 1}, {'column': 'id', 'operator': 'eq', 'value': 3}]}
    assert ids(session, node) == [1, 3]


# FL4 — время

@pytest.mark.parametrize(
    'value, expected',
    [('9:30', datetime.time(9, 30)), ('09:30', datetime.time(9, 30)),
     ('14:00:15', datetime.time(14, 0, 15)), (' 9:30 ', datetime.time(9, 30))],
)
def test_fl4_convert_time(value, expected):
    """Время «Ч:ММ», «Ч:ММ:СС» (раньше '9:30' — ValueError)."""
    assert _convert_value(Item.at, value) == expected


def test_fl4_bad_time():
    """Неверное время — понятный ValueError."""
    with pytest.raises(ValueError):
        _convert_value(Item.at, 'полдень')


def test_fl4_filter_by_time(session):
    """Фильтр по времени «9:30»."""
    assert ids(session, [{'column': 'at', 'operator': 'eq', 'value': '9:30'}]) == [1]


# FL5 — between с value2

def test_fl5_between_value2(session):
    """between: value + value2 (раньше ошибка «должно быть списком»)."""
    node = [{'column': 'day', 'operator': 'between', 'value': '2026-01-01', 'value2': '2026-02-01'}]
    assert ids(session, node) == [1]


def test_fl5_between_list_still_works(session):
    """between списком — как раньше."""
    assert ids(session, [{'column': 'day', 'operator': 'between', 'value': ['2026-04-01', '2026-06-01']}]) == [12]


def test_fl5_between_bad():
    """between без второй границы — ValueError."""
    with pytest.raises(ValueError):
        apply_filters(None, Item, [{'column': 'day', 'operator': 'between', 'value': '2026-01-01'}])


# Прочее поведение (не менялось)

@pytest.mark.parametrize(
    'node, expected',
    [
        ([{'column': 'id', 'operator': 'gt', 'value': '2'}], [3, 12]),
        ([{'column': 'name', 'operator': 'is_null'}], [3]),
        ([{'column': 'name', 'operator': 'is_not_null'}], [1, 12]),
        ([{'column': 'id', 'operator': 'in', 'value': ['1', '3']}], [1, 3]),
        ([{'column': 'id', 'operator': 'not_in', 'value': [1]}], [3, 12]),
        ([{'column': 'id', 'operator': 'ne', 'value': 1}], [3, 12]),
    ],
)
def test_other_operators(session, node, expected):
    """Остальные операторы."""
    assert ids(session, node) == expected


def test_unknown_operator():
    """Неизвестный оператор — ValueError."""
    with pytest.raises(ValueError, match='Неизвестный оператор'):
        apply_filters(None, Item, [{'column': 'id', 'operator': 'xx', 'value': 1}])


def test_doctests():
    """Примеры (>>>) в докстрингах верны."""
    result = doctest.testmod(filtering)
    assert result.failed == 0
