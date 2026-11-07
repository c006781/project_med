# tests/test_utils/test_birth_precision.py

"""Дата рождения с точностью и сравнение пациентов (app/utils/record_keys.py, Ф1.6.10е)."""

from datetime import date

import pytest

from app.dto.dto_all import PatientDTO
from app.utils.record_keys import (
    BIRTH_PRECISION_DAY,
    BIRTH_PRECISION_MONTH,
    BIRTH_PRECISION_YEAR,
    MATCH_DIFFERENT,
    MATCH_FULL,
    MATCH_PARTIAL,
    birth_date_key,
    coarser_precision,
    effective_birth_precision,
    format_birth_date,
    match_patients,
    normalize_birth_date,
)


def _patient(
    middle=None,
    birth=None,
    precision=None,
    last='Иванова',
    first='Мария',
):
    return {
        'last_name': last,
        'first_name': first,
        'middle_name': middle,
        'birth_date': birth,
        'birth_date_precision': precision,
    }


# --- показ -----------------------------------------------------------------

@pytest.mark.parametrize(
    'value, precision, text',
    [
        (date(1999, 1, 1), BIRTH_PRECISION_YEAR, '1999'),
        (date(1999, 6, 1), BIRTH_PRECISION_MONTH, '06.1999'),
        (date(1999, 6, 14), BIRTH_PRECISION_DAY, '14.06.1999'),
        (date(1999, 6, 14), None, '14.06.1999'),         # без точности — полная
        (date(1999, 6, 14), 'нечто', '14.06.1999'),      # чтение не падает на странной строке
        (date(987, 6, 14), BIRTH_PRECISION_DAY, '14.06.0987'),  # strftime на Linux не дополняет нулями
    ],
)
def test_format_birth_date(value, precision, text):
    assert format_birth_date(value, precision) == text


def test_format_birth_date_empty():
    assert format_birth_date(None, BIRTH_PRECISION_YEAR) == ''
    assert format_birth_date(None, None, empty='—') == '—'


# --- запись ----------------------------------------------------------------

@pytest.mark.parametrize(
    'value, precision, expected',
    [
        (None, None, None),
        (None, BIRTH_PRECISION_YEAR, None),                  # даты нет — точности нет
        (date(1999, 6, 14), None, BIRTH_PRECISION_DAY),      # не задана — полная
        (date(1999, 1, 1), BIRTH_PRECISION_YEAR, BIRTH_PRECISION_YEAR),
        (date(1999, 6, 1), BIRTH_PRECISION_MONTH, BIRTH_PRECISION_MONTH),
        (date(1999, 6, 1), BIRTH_PRECISION_YEAR, BIRTH_PRECISION_DAY),     # месяц известен — не год
        (date(1999, 6, 14), BIRTH_PRECISION_YEAR, BIRTH_PRECISION_DAY),    # ввели точнее
        (date(1999, 6, 14), BIRTH_PRECISION_MONTH, BIRTH_PRECISION_DAY),   # ввели точнее
        (date(1999, 1, 1), BIRTH_PRECISION_DAY, BIRTH_PRECISION_DAY),      # настоящее 1 января
    ],
)
def test_normalize_birth_date(value, precision, expected):
    assert normalize_birth_date(value, precision) == (value, expected)


def test_normalize_birth_date_unknown_precision():
    with pytest.raises(ValueError, match='неизвестная точность'):
        normalize_birth_date(date(1999, 1, 1), 'decade')


def test_effective_precision():
    assert effective_birth_precision(None, BIRTH_PRECISION_YEAR) is None
    assert effective_birth_precision(date(1999, 1, 1), None) == BIRTH_PRECISION_DAY
    assert effective_birth_precision(date(1999, 1, 1), BIRTH_PRECISION_YEAR) == BIRTH_PRECISION_YEAR


def test_coarser_and_key():
    assert coarser_precision(BIRTH_PRECISION_DAY, BIRTH_PRECISION_YEAR) == BIRTH_PRECISION_YEAR
    assert coarser_precision(BIRTH_PRECISION_MONTH, BIRTH_PRECISION_DAY) == BIRTH_PRECISION_MONTH
    assert coarser_precision(BIRTH_PRECISION_MONTH, BIRTH_PRECISION_YEAR) == BIRTH_PRECISION_YEAR
    day = date(1999, 6, 14)
    assert birth_date_key(day, BIRTH_PRECISION_YEAR) == (1999,)
    assert birth_date_key(day, BIRTH_PRECISION_MONTH) == (1999, 6)
    assert birth_date_key(day, BIRTH_PRECISION_DAY) == (1999, 6, 14)


# --- сравнение -------------------------------------------------------------

def test_full_match_ignores_case_yo_spaces():
    match = match_patients(
        _patient('Петровна', date(1985, 6, 14)),
        _patient(' петровна ', date(1985, 6, 14), last='ИВАНОВА', first='мария'),
    )
    assert match.same and match.label == MATCH_FULL
    assert match.empty_fields == () and match.date_precision == BIRTH_PRECISION_DAY
    assert match.describe() == 'полное'


def test_owner_example_incomplete_match():
    """Пример владельца: «Иванова Мария Петровна, без даты» + «Иванова Мария, 14.06.1985»."""
    match = match_patients(
        _patient('Петровна'),
        _patient(None, date(1985, 6, 14)),
    )
    assert match.same and match.label == MATCH_PARTIAL
    assert match.empty_fields == ('middle_name', 'birth_date')
    assert match.one_sided_fields == ('middle_name', 'birth_date')
    assert match.describe() == 'неполное: пусто отчество, дата рождения'


def test_filled_and_different_are_different_patients():
    by_middle = match_patients(_patient('Петровна'), _patient('Ивановна'))
    assert not by_middle.same and by_middle.differing_fields == ('middle_name',)
    assert by_middle.label == MATCH_DIFFERENT
    by_date = match_patients(_patient(None, date(1985, 6, 14)), _patient(None, date(1985, 6, 15)))
    assert not by_date.same and by_date.differing_fields == ('birth_date',)
    assert by_date.describe() == 'разные: различаются дата рождения'


@pytest.mark.parametrize('name', [{'last': 'Петрова'}, {'first': 'Анна'}])
def test_last_and_first_name_must_match(name):
    assert not match_patients(_patient(), _patient(**name)).same


def test_empty_name_does_not_match_anything():
    """«Пустое не противоречит» — не к фамилии и имени: они совпадают всегда."""
    assert not match_patients(_patient(), _patient(first='')).same


def test_both_empty_is_unknown_but_not_one_sided():
    match = match_patients(_patient(), _patient(middle=''))
    assert match.same and match.label == MATCH_PARTIAL
    assert match.empty_fields == ('middle_name', 'birth_date')
    assert match.one_sided_fields == ()


@pytest.mark.parametrize(
    'left, left_precision, right, right_precision, same, used',
    [
        (date(1999, 1, 1), 'year', date(1999, 6, 14), 'day', True, 'year'),
        (date(1999, 6, 14), 'day', date(1999, 1, 1), 'year', True, 'year'),
        (date(1999, 1, 1), 'year', date(2000, 1, 1), 'year', False, 'year'),
        (date(1999, 1, 1), 'year', date(2000, 6, 14), 'day', False, 'year'),
        (date(1999, 6, 1), 'month', date(1999, 6, 14), 'day', True, 'month'),
        (date(1999, 6, 1), 'month', date(1999, 7, 14), 'day', False, 'month'),
        (date(1999, 6, 1), 'month', date(1999, 1, 1), 'year', True, 'year'),
        (date(1999, 1, 1), 'day', date(1999, 6, 14), 'day', False, 'day'),   # 1 января — настоящая дата
        (date(1999, 1, 1), None, date(1999, 6, 14), 'day', False, 'day'),    # без точности — полная
    ],
)
def test_date_compared_by_least_precise(left, left_precision, right, right_precision, same, used):
    match = match_patients(
        _patient(None, left, left_precision),
        _patient(None, right, right_precision),
    )
    assert match.same is same
    assert match.date_precision == used


def test_comparison_is_not_transitive():
    """Год совпадает с обеими точными датами, а они друг с другом — нет: поэтому попарно."""
    year = _patient('Петровна', date(1999, 1, 1), 'year')
    first = _patient('Петровна', date(1999, 6, 14), 'day')
    second = _patient('Петровна', date(1999, 6, 15), 'day')
    assert match_patients(year, first).same and match_patients(year, second).same
    assert not match_patients(first, second).same


def test_match_works_with_dto_and_dict():
    dto = PatientDTO(last_name='Иванова', first_name='Мария', birth_date=date(1985, 6, 14))
    assert match_patients(dto, _patient(None, date(1985, 1, 1), 'year')).same


def test_custom_fields():
    match = match_patients(
        _patient('Петровна', date(1985, 6, 14)),
        _patient('Ивановна', date(1990, 6, 14)),
        fields = ('last_name', 'first_name'),
    )
    assert match.label == MATCH_FULL and match.date_precision is None
