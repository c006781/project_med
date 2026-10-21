# tests/test_virtual_fields_review_pass1.py

"""
Тесты проверки модуля app.utils.virtual_fields, проход 1 (2026-10-21).

VF1 — compute_virtual_fields без extra_data (по умолчанию None) падал TypeError.
"""

from typing import Optional

import pytest
from pydantic import BaseModel

from app.utils.virtual_fields import compute_virtual_fields, enrich_dto_with_computed_fields


def upper(value):
    """Вычисление для тестов."""
    return None if value is None else str(value).upper()


CONFIG = {
    'name': {},
    'name_upper': {'virtual': True, 'compute': {'func': upper, 'args': ['name']}},
}


def test_vf1_without_extra_data():
    """extra_data не передан — вычисление работает (раньше TypeError)."""
    assert compute_virtual_fields({'name': 'ab'}, CONFIG)['name_upper'] == 'AB'


def test_arg_from_extra_data():
    """Аргумента нет в данных — берётся из extra_data."""
    config = {'x': {'compute': {'func': upper, 'args': ['rel']}}}
    assert compute_virtual_fields({}, config, {'rel': 'q'})['x'] == 'Q'


def test_missing_arg_is_none():
    """Аргумента нет нигде — None."""
    config = {'x': {'compute': {'func': lambda v: v is None, 'args': ['нет']}}}
    assert compute_virtual_fields({}, config)['x'] is True


def test_kwargs_passed():
    """kwargs вычисления передаются."""
    config = {'x': {'compute': {'func': lambda *, k: k * 2, 'kwargs': {'k': 3}}}}
    assert compute_virtual_fields({}, config)['x'] == 6


def test_error_gives_none_others_computed():
    """Ошибка вычисления — None, остальные поля считаются."""
    config = {'bad': {'compute': {'func': lambda: 1 / 0}}, **CONFIG}
    result = compute_virtual_fields({'name': 'a'}, config)
    assert result['bad'] is None and result['name_upper'] == 'A'


def test_not_callable_skipped():
    """func не функция — поле не трогается."""
    assert compute_virtual_fields({'x': 1}, {'x': {'compute': {'func': 'нет'}}}) == {'x': 1}


def test_source_data_not_mutated():
    """Исходный словарь не меняется."""
    data = {'name': 'a'}
    compute_virtual_fields(data, CONFIG)
    assert data == {'name': 'a'}


class Dto(BaseModel):
    """DTO для теста обогащения."""
    name: Optional[str] = None
    name_upper: Optional[str] = None
    rel_text: Optional[str] = None


def test_enrich_dto_from_source_attr():
    """enrich: аргумент из связанного объекта (source_attr) ORM-объекта."""
    class Obj:
        rel = 'связь'
    config = {**CONFIG, 'rel_text': {'virtual': True, 'source_attr': 'rel', 'compute': {'func': upper, 'args': ['rel']}}}
    dto = enrich_dto_with_computed_fields(Dto(name='ab'), Obj(), config)
    assert (dto.name_upper, dto.rel_text) == ('AB', 'СВЯЗЬ')
