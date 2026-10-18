# tests/test_dataset/test_core_basics.py

"""Ядро наборов данных: поля, запрос, источник в памяти, переносимость пакета."""

import ast
import datetime
import os
import sys

import pytest

from app.utils.dataset import (
    Condition, FieldDef, FieldKind, Fields, LookupDef, MemoryBackend, Op, Order, Query,
    apply_in_memory, sort_rows,
)

PACKAGE = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'utils', 'dataset')


# --------------------------------------------------------------------------- переносимость

def test_core_imports_only_stdlib_and_itself():
    """Ядро не тянет ни Qt, ни БД, ни черновики, ни код приложения — переносится как есть."""
    stdlib = set(sys.stdlib_module_names)
    for name in os.listdir(PACKAGE):
        if not name.endswith('.py'):
            continue
        tree = ast.parse(open(os.path.join(PACKAGE, name), encoding='utf-8').read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:              # относительный импорт — внутри пакета
                    continue
                modules = [node.module or '']
            else:
                continue
            for module in modules:
                assert module.split('.')[0] in stdlib, f"{name}: импорт {module}"


# --------------------------------------------------------------------------- поля

@pytest.mark.parametrize('kind, good, bad', [
    (FieldKind.STRING, 'a', 1),
    (FieldKind.INTEGER, 1, True),
    (FieldKind.FLOAT, 1, '1'),
    (FieldKind.BOOLEAN, False, 0),
    (FieldKind.DATE, datetime.date(2026, 1, 1), datetime.datetime(2026, 1, 1)),
    (FieldKind.DATETIME, datetime.datetime(2026, 1, 1), datetime.date(2026, 1, 1)),
    (FieldKind.BLOB, b'x', 'x'),
])
def test_field_kinds(kind, good, bad):
    assert kind.accepts(good) and kind.accepts(None)
    assert not kind.accepts(bad)


def test_field_validation_order_and_custom():
    f = FieldDef('age', 'Возраст', FieldKind.INTEGER, required=True,
                 validators=[lambda v, row: 'не меньше 0' if v < 0 else None])
    assert f.validate(None, {}) == ['поле «Возраст» обязательно']
    assert f.validate('5', {}) == ['поле «Возраст»: ожидается integer, получено str']
    assert f.validate(-1, {}) == ['поле «Возраст»: не меньше 0']
    assert f.validate(3, {}) == []
    assert FieldDef('s', required=True).validate('  ', {}) == ['поле «s» обязательно']


def test_field_flags():
    calc = FieldDef('full', calculated=lambda r: r['a'])
    assert not calc.stored and not calc.editable and calc.validate(None, {}) == []
    assert FieldDef('id', read_only=True).stored and not FieldDef('id', read_only=True).editable
    assert FieldDef('d', default=lambda: [1]).default_value() == [1]
    assert FieldDef('d').text(None) == '' and FieldDef('d').text(5) == '5'


def test_fields_collection():
    fields = Fields([FieldDef('id'), FieldDef('patient_id', references='patients'),
                     FieldDef('x', visible=False, calculated=len)])
    assert fields.names() == ['id', 'patient_id', 'x']
    assert [f.name for f in fields.visible()] == ['id', 'patient_id']
    assert [f.name for f in fields.stored()] == ['id', 'patient_id']
    assert fields.referencing('patients')[0].name == 'patient_id'
    with pytest.raises(KeyError, match='нет поля'):
        fields['nope']
    with pytest.raises(ValueError, match='дважды'):
        Fields([FieldDef('a'), FieldDef('a')])


# --------------------------------------------------------------------------- запрос

ROWS = [
    {'id': 1, 'name': 'Петров', 'age': 30},
    {'id': 2, 'name': 'иванов', 'age': None},
    {'id': 3, 'name': 'Иванова', 'age': 25},
]


@pytest.mark.parametrize('condition, ids', [
    (Condition('age', Op.EQ, 30), [1]),
    (Condition('age', Op.NE, 30), [2, 3]),
    (Condition('age', Op.GT, 20), [1, 3]),
    (Condition('age', Op.LT, 26), [3]),               # None не сравнивается — не подходит
    (Condition('age', Op.IS_NULL, True), [2]),
    (Condition('age', Op.IS_NULL, False), [1, 3]),
    (Condition('id', Op.IN, [1, 3]), [1, 3]),
    (Condition('name', Op.CONTAINS, 'ИВАН'), [2, 3]),  # без учёта регистра
    (Condition('name', Op.STARTSWITH, 'пет'), [1]),
    (Condition('name', Op.GT, 5), []),                 # несравнимые типы — не падает
])
def test_conditions(condition, ids):
    assert [r['id'] for r in apply_in_memory(ROWS, Query(conditions=(condition,)))] == ids


def test_sort_none_last_both_directions_and_case():
    asc = sort_rows(ROWS, [Order('age')])
    desc = sort_rows(ROWS, [Order('age', descending=True)])
    assert [r['id'] for r in asc] == [3, 1, 2]
    assert [r['id'] for r in desc] == [1, 3, 2]
    assert [r['id'] for r in sort_rows(ROWS, [Order.parse('name')])] == [2, 3, 1]


def test_sort_multiple_keys_and_mixed_types():
    rows = [{'a': 1, 'b': 2}, {'a': 1, 'b': 1}, {'a': 0, 'b': 9}]
    assert sort_rows(rows, [Order('a'), Order('b', True)]) == [
        {'a': 0, 'b': 9}, {'a': 1, 'b': 2}, {'a': 1, 'b': 1}]
    sort_rows([{'a': datetime.date(2026, 1, 1)}, {'a': 1}], [Order('a')])   # не падает


def test_query_window_and_where():
    q = Query(order=(Order('id', True),)).where(Condition('age', Op.IS_NULL, False)).window(1, 1)
    assert apply_in_memory(ROWS, q) == [ROWS[0]]


# --------------------------------------------------------------------------- источник в памяти

def test_memory_backend_copies_and_keys():
    source = [{'id': 1, 'tags': ['a']}]
    backend = MemoryBackend(source)
    source[0]['tags'].append('b')
    page = backend.fetch(Query())
    page.rows[0]['tags'].append('c')
    assert backend.get(1) == {'id': 1, 'tags': ['a']}          # снаружи не изменить
    assert backend.insert({'x': 1})['id'] == 2
    assert backend.insert({'id': 10})['id'] == 10
    with pytest.raises(ValueError, match='занят'):
        backend.insert({'id': 10})
    with pytest.raises(ValueError, match='смена ключа'):
        backend.update(1, {'id': 5})
    with pytest.raises(KeyError):
        backend.delete(99)
    with pytest.raises(ValueError, match='нет ключа'):
        MemoryBackend([{'x': 1}])


def test_memory_backend_window_total():
    backend = MemoryBackend([{'id': i} for i in range(1, 6)])
    page = backend.fetch(Query(offset=3, limit=10))
    assert [r['id'] for r in page.rows] == [4, 5] and page.total == 5


# --------------------------------------------------------------------------- подстановки

def test_lookup_backend_function_and_cache():
    backend = MemoryBackend([{'id': 1, 'last': 'Петров', 'first': 'Иван'}])
    calls = []

    def getter(key):
        calls.append(key)
        return backend.get(key)

    by_field = LookupDef('patient_id', backend, display='last')
    by_func = LookupDef('patient_id', getter, display=lambda r: f"{r['last']} {r['first'][0]}.")
    assert by_field.resolve(1) == 'Петров' and by_field.resolve(None) is None
    assert by_func.resolve(1) == 'Петров И.' and by_func.resolve(1) == 'Петров И.'
    assert calls == [1]                                           # второй раз — из кеша
    backend.update(1, {'last': 'Сидоров'})
    assert by_field.resolve(1) == 'Петров'
    by_field.invalidate(1)
    assert by_field.resolve(1) == 'Сидоров'
    assert by_field.resolve(404) is None
