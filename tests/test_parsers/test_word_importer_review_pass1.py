# tests/test_parsers/test_word_importer_review_pass1.py

"""
Тесты исправлений проверки ``parsers/word_importer.py``, проход 1 (2026-10-25).

Номера W1–W9 — ``parsers/IMPLEMENTATION.md`` §4. На старом коде эти тесты падают.
Без сети и БД.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from app.dto.dto_all import PatientDTO
from parsers.word_importer import (
    PatientInfoExtractor,
    WordFileParser,
    normalize_patient_dto,
    normalize_phone,
    normalize_text,
)


# ----------------------------------------------------------------------
# W1 — normalize_text убирает лишние пробелы
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('  Иван  ', 'Иван'),                                  # пробелы по краям
        ('Тест  1 1', 'Тест 1 1'),                             # повторные внутри
        ('Тест 1 1\n причина обращения', 'Тест 1 1\nпричина обращения'),  # у каждой строки
        ('a\r\nb', 'a\nb'),                                    # \r\n — один перенос
        ('a\xa0\xa0b', 'a b'),                                 # неразрывные пробелы
        ('строка 1\n   \nстрока 3', 'строка 1\n\nстрока 3'),   # строка из пробелов — пустая
    ],
)
def test_w1_normalize_text_strips_spaces(raw, expected):
    """W1: пробелы по краям строк и повторные убираются, переносы — остаются."""
    assert normalize_text(raw) == expected


# ----------------------------------------------------------------------
# W3 — код города из 4–5 цифр
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('8 (3842) 12-34-56', '+7 (3842) 12-34-56'),     # код в скобках
        ('+7 (38451) 2-34-56', '+7 (38451) 2-34-56'),    # пятизначный код
        ('8 3842 123456', '+7 (3842) 12-34-56'),         # код отдельной группой
        ('3842 12 34 56', '+7 (3842) 12-34-56'),         # без 8
        ('8 (495) 123-45-67', '+7 (495) 123-45-67'),     # трёхзначный код — обычный вид
        ('83842123456', '+7 (384) 212-34-56'),           # слитно — группировки нет, обычный вид
    ],
)
def test_w3_area_code_by_grouping(raw, expected):
    """W3: вид номера — по исходной группировке (скобки или первая группа цифр)."""
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('4951234567', '+7 (495) 123-45-67'),            # 10 цифр, код города с 4
        ('3842123456', '+7 (384) 212-34-56'),            # 10 цифр, код города с 3
    ],
)
def test_w3_ten_digits_landline(raw, expected):
    """W3: 10 цифр с кодом города РФ (3…, 4…) — распознаются (раньше — только 8…, 9…)."""
    assert normalize_phone(raw) == expected


def test_w3_ten_digits_not_russian():
    """10 цифр, не начинающиеся с 3, 4, 8, 9, — не номер РФ."""
    assert normalize_phone('1234567890') is None


# ----------------------------------------------------------------------
# W2 — нераспознанный телефон: сообщение, телефон не записывается
# ----------------------------------------------------------------------

def test_w2_unrecognized_phone_reported():
    """W2: телефон не распознан — поле пустое, предупреждение с исходным текстом и пациентом."""
    dto = PatientDTO(
        last_name   = 'Иванов',
        first_name  = 'Иван',
        middle_name = 'Иванович',
        phone       = '12-34-56',
    )
    warnings = []

    result = normalize_patient_dto(
        dto,
        warnings = warnings,
    )

    assert result.phone is None
    assert len(warnings) == 1
    assert '12-34-56' in warnings[0]
    assert 'Иванов Иван Иванович' in warnings[0]


def test_w2_recognized_phone_no_warning():
    """Распознанный телефон — без предупреждения."""
    dto = PatientDTO(
        last_name  = 'Иванов',
        first_name = 'Иван',
        phone      = '8 999 123 45 67',
    )
    warnings = []

    normalize_patient_dto(
        dto,
        warnings = warnings,
    )

    assert dto.phone == '+7 (999) 123-45-67'
    assert warnings == []


def test_w2_names_cleaned():
    """ФИО чистятся normalize_text (W1)."""
    dto = PatientDTO(
        last_name  = ' Иванов ',
        first_name = 'Иван  ',
    )

    normalize_patient_dto(dto)

    assert (dto.last_name, dto.first_name) == ('Иванов', 'Иван')


# ----------------------------------------------------------------------
# W5 — телефон в шапке с +, скобками, дефисами; группировка сохраняется
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'line, phone, description',
    [
        ('Иванов Иван Иванович 1990 +7 999 123-45-67', '+7 999 123-45-67', None),
        ('Иванов Иван Иванович 1990 8-999-123-45-67 Анна', '8-999-123-45-67', 'Анна'),
        ('Иванов Иван Иванович 1990 8 (3842) 12-34-56 тётя', '8 (3842) 12-34-56', 'тётя'),
        ('Иванов Иван Иванович 1990 951 164 9014 Анна тётя', '951 164 9014', 'Анна тётя'),
    ],
)
def test_w5_extract_phone_forms(line, phone, description):
    """W5: телефон в шапке — как в тексте (с группировкой), описание — после него."""
    dto = PatientInfoExtractor.extract(line)

    assert dto.phone == phone
    assert dto.description_text == description


# ----------------------------------------------------------------------
# W6 — год не склеивается с телефоном и не становится отчеством
# ----------------------------------------------------------------------

def test_w6_phone_without_year():
    """W6: без года 11 цифр телефона не дают год 8999."""
    dto = PatientInfoExtractor.extract('Иванов Иван Иванович 89991234567')

    assert dto.middle_name == 'Иванович'
    assert dto.birth_date is None
    assert dto.phone == '89991234567'


def test_w6_no_middle_name():
    """W6: без отчества год — год, а не отчество."""
    dto = PatientInfoExtractor.extract('Иванов Иван 1990 89991234567')

    assert dto.middle_name is None
    assert dto.birth_date == date(1990, 1, 1)
    assert dto.phone == '89991234567'


def test_w6_two_words():
    """Только фамилия и имя — распознаётся (раньше — None)."""
    dto = PatientInfoExtractor.extract('Иванов Иван')

    assert (dto.last_name, dto.first_name, dto.middle_name) == ('Иванов', 'Иван', None)


@pytest.mark.parametrize(
    'line, description',
    [
        ('Иванов Иван Иванович 2012 г. Анна', 'Анна'),        # «г.» через пробел
        ('Иванов Иван Иванович 2012г Анна', 'Анна'),          # «г» слитно
        ('Иванов Иван Иванович 2012 галина', 'галина'),       # слово на «г» — не «год»
    ],
)
def test_w6_year_suffix(line, description):
    """Пометка года «г» / «г.» не попадает в описание; слово на «г» — не пометка."""
    dto = PatientInfoExtractor.extract(line)

    assert dto.birth_date == date(2012, 1, 1)
    assert dto.description_text == description


# ----------------------------------------------------------------------
# W9 — заголовки столбцов сравниваются после нормализации
# ----------------------------------------------------------------------

def _header_row(titles):
    """Строка заголовков таблицы-подделки (у ячеек есть только ``text``)."""
    return SimpleNamespace(
        cells = [SimpleNamespace(text=title) for title in titles],
    )


def test_w9_header_normalized():
    """
    W9: заголовок сравнивается после normalize_match — повторный пробел, ё, пунктуация
    не мешают. Причина обращения — поле без запасного поиска по синонимам (он есть только
    у даты и фото), поэтому раньше столбец терялся.
    """
    parser = WordFileParser.__new__(WordFileParser)     # без чтения файла
    parser.mapping = {
        'дата приема'       : 'date',
        'причина обращения' : 'reason_text',
        'фото'              : 'photos',
    }

    mapping = parser._map_columns(
        _header_row(['Дата приёма.', 'Причина  обращения:', 'Фото']),
    )

    assert mapping == {'date': 0, 'reason_text': 1, 'photos': 2}
