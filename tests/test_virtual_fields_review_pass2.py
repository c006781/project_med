# tests/test_virtual_fields_review_pass2.py

"""
Тесты проверки модуля app.utils.virtual_fields, проход 2 (2026-10-25).

Ошибок не найдено (VF2 — описания и формат); тесты закрепляют поведение, записанное в
докстрингах: порядок поиска аргументов, цепочка вычислений, что пишется в DTO.
"""

from typing import Optional

from pydantic import BaseModel

from app.utils.virtual_fields import compute_virtual_fields, enrich_dto_with_computed_fields


def join(
    *parts : Optional[str],  # части строки (None пропускаются)
) -> str:
    """
    Склеивает непустые части через пробел (вычисление для тестов).

    Пример:
        >>> join('a', None, 'b')
        'a b'
    """
    return ' '.join(
        p for p in parts if p
    )


def test_vf2_chain_uses_earlier_computed_field() -> None:
    """Поле может опираться на вычисленное раньше (порядок конфигурации)."""
    configs = {
        'full': {'compute': {'func': join, 'args': ['last', 'first']}},
        'title': {'compute': {'func': join, 'args': ['full', 'role']}},
    }
    result = compute_virtual_fields(
        {'last': 'Иванов', 'first': 'Иван', 'role': 'врач'},  # данные
        configs,                                              # конфигурация
    )
    assert result['title'] == 'Иванов Иван врач'


def test_vf2_data_has_priority_over_extra_data() -> None:
    """Аргумент есть и в data, и в extra_data — берётся из data."""
    configs = {'out': {'compute': {'func': join, 'args': ['x']}}}
    result = compute_virtual_fields(
        {'x': 'из data'},             # данные
        configs,                      # конфигурация
        extra_data = {'x': 'из extra'},
    )
    assert result['out'] == 'из data'


def test_vf2_example_kwargs() -> None:
    """Пример из докстринга: именованные аргументы из конфигурации."""
    configs = {'age_text': {'compute': {
        'func'  : lambda age, unit: f'{age} {unit}',
        'args'  : ['age'],
        'kwargs': {'unit': 'лет'},
    }}}
    assert compute_virtual_fields({'age': 30}, configs) == {'age': 30, 'age_text': '30 лет'}


class Dto(BaseModel):
    """DTO для тестов обогащения."""
    name  : Optional[str] = None
    label : Optional[str] = None
    count : Optional[int] = None


def test_vf2_enrich_mutates_extra_data_and_skips_none() -> None:
    """enrich дополняет переданный extra_data связью; None в DTO не пишется."""

    class Obj:
        """ORM-объект-заглушка со связью."""
        rel = 'связь'

    configs = {
        'label': {'virtual': True, 'source_attr': 'rel',
                  'compute': {'func': lambda rel: None, 'args': ['rel']}},
    }
    extra = {}
    dto = enrich_dto_with_computed_fields(
        Dto(name='a', label='было'),  # DTO
        Obj(),                        # ORM-объект
        configs,                      # конфигурация
        extra,                        # дополняется на месте
    )
    assert extra == {'rel': 'связь'}
    assert dto.label == 'было'  # вычислено None — старое значение не затирается


def test_vf2_enrich_virtual_from_extra_data() -> None:
    """Виртуальное поле без compute берётся из extra_data (sql_compute)."""
    configs = {'count': {'virtual': True}}
    dto = enrich_dto_with_computed_fields(
        Dto(name='a'),                # DTO без count
        object(),                     # ORM-объект (связей нет)
        configs,                      # конфигурация
        {'count': 3},                 # значение подзапроса
    )
    assert dto.count == 3
