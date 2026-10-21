# tests/test_filtering_review_pass2.py

"""
Тесты исправлений проверки модуля app.utils.filtering, проход 2 (2026-10-21).

FL6 — поле-заметка поддерживает все операторы диалога фильтра и набора данных
(раньше — только ilike/like/eq, остальные — ValueError).
"""

import warnings

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, declarative_base

from app.utils.filtering.filtering import apply_filters, column_condition

Base = declarative_base()


class Note(Base):
    """Заметки (общая таблица текстов)."""
    __tablename__ = 'notes'
    id = sa.Column(sa.Integer, primary_key=True)
    text = sa.Column(sa.String)


class Rec(Base):
    """Запись со ссылкой на заметку."""
    __tablename__ = 'recs'
    id = sa.Column(sa.Integer, primary_key=True)
    note_id = sa.Column(sa.Integer, sa.ForeignKey('notes.id'))


NOTES = {'note_text': {'foreign_key': 'note_id', 'note_model': Note, 'text_column': 'text'}}


@pytest.fixture
def session():
    """Записи: 1 → 'альфа', 2 → 'бета', 3 → без заметки, 4 → заметка с пустым текстом, 5 → 'альфа'."""
    engine = sa.create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add_all([Note(id=10, text='альфа'), Note(id=20, text='бета'), Note(id=40, text='')])
        sess.add_all([Rec(id=1, note_id=10), Rec(id=2, note_id=20), Rec(id=3, note_id=None),
                      Rec(id=4, note_id=40), Rec(id=5, note_id=10)])
        sess.commit()
        yield sess


def ids(session, node):
    """id записей, прошедших фильтр по полю-заметке (предупреждения — ошибка)."""
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        query, _ = apply_filters(session.query(Rec), Rec, node, note_mappings=NOTES)
        return sorted(rec.id for rec in query.all())


def leaf(op, value=None, **extra):
    """Лист фильтра по полю-заметке."""
    return [{'column': 'note_text', 'operator': op, 'value': value, **extra}]


@pytest.mark.parametrize(
    'op, value, extra, expected',
    [
        ('eq', 'альфа', {}, [1, 5]),
        ('ilike', 'льф', {}, [1, 5]),
        ('like', 'ет', {}, [2]),
        ('ne', 'альфа', {}, [2, 4]),                   # как у обычного столбца: без заметки — не входит
        ('in', ['бета', 'альфа'], {}, [1, 2, 5]),
        ('not_in', ['альфа'], {}, [2, 4]),
        ('between', ['а', 'в'], {}, [1, 2, 5]),
        ('between', 'б', {'value2': 'в'}, [2]),
        ('gt', 'альфа', {}, [2]),
        ('ge', 'альфа', {}, [1, 2, 5]),
        ('lt', 'бета', {}, [1, 4, 5]),
        ('le', 'бета', {}, [1, 2, 4, 5]),
        ('is_null', None, {}, [3, 4]),                 # нет заметки или пустой текст
        ('is_not_null', None, {}, [1, 2, 5]),
    ],
)
def test_fl6_note_operators(session, op, value, extra, expected):
    """Все операторы на поле-заметке (раньше кроме eq/like/ilike — ValueError)."""
    assert ids(session, leaf(op, value, **extra)) == expected


def test_fl6_note_in_or_group(session):
    """Поле-заметка внутри 'or'."""
    node = {'or': [leaf('is_null')[0], leaf('eq', 'бета')[0]]}
    assert ids(session, node) == [2, 3, 4]


def test_fl6_note_unknown_operator(session):
    """Неизвестный оператор на поле-заметке — ValueError."""
    with pytest.raises(ValueError, match='Неизвестный оператор'):
        ids(session, leaf('xx', 'a'))


def test_fl6_note_like_none(session):
    """ilike с None на поле-заметке — все с заметкой (раньше AttributeError)."""
    assert ids(session, leaf('ilike', None)) == [1, 2, 4, 5]


def test_fl6_column_condition_public():
    """column_condition доступна для повторного использования."""
    assert str(column_condition(Rec.id, 'eq', '5')) == 'recs.id = :id_1'
