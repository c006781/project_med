# tests/test_parsers/test_word_importer.py

"""
Тесты текущего поведения чистых функций импорта из Word (``parsers/word_importer.py``).

Задача плана Ф1.1.1 (2026-10-25): зафиксировать то, что уже работает правильно, до
исправлений W1–W9 (тесты исправлений — ``test_word_importer_review_pass1.py``).
Без сети и БД; файлы — только во временной папке ``tmp_path``.
"""

from datetime import date

import pytest

from parsers.word_importer import (
    PatientInfoExtractor,
    WordFileParser,
    filter_unprocessed_files,
    get_all_docx_files,
    get_successful_files_from_log,
    normalize_match,
    normalize_phone,
    normalize_text,
)


# ----------------------------------------------------------------------
# normalize_text
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('', ''),                                    # пустая строка
        (None, ''),                                  # None — как пустая
        ('Иван', 'Иван'),                            # чистый текст не меняется
        ('a\rb', 'a\nb'),                            # \r → перенос строки
        ('a\tb', 'a b'),                             # табуляция → пробел
        ('\n\nтекст\n\n', 'текст'),                  # пустые строки по краям убираются
        ('строка 1\n\nстрока 3', 'строка 1\n\nстрока 3'),  # внутренние пустые — остаются
    ],
)
def test_normalize_text_keeps_line_breaks(raw, expected):
    """Переносы строк сохраняются, пустые строки по краям убираются."""
    assert normalize_text(raw) == expected


# ----------------------------------------------------------------------
# normalize_phone
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('951 164 9014', '+7 (951) 164-90-14'),      # 10 цифр с пробелами
        ('8-999-123-45-67', '+7 (999) 123-45-67'),   # 8 и дефисы
        ('+79991234567', '+7 (999) 123-45-67'),      # +7 слитно
        ('9991234567', '+7 (999) 123-45-67'),        # 10 цифр
        ('89991234567', '+7 (999) 123-45-67'),       # 11 цифр с 8
        ('79991234567', '+7 (999) 123-45-67'),       # 11 цифр с 7
    ],
)
def test_normalize_phone_russian_formats(raw, expected):
    """Мобильные номера РФ в разных записях → +7 (XXX) XXX-XX-XX."""
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize('raw', ['', None, 'нет', '12-34-56', '+375 29 123 45 67'])
def test_normalize_phone_unrecognized_is_none(raw):
    """Пусто, без цифр, городской без кода, чужая страна — None."""
    assert normalize_phone(raw) is None


# ----------------------------------------------------------------------
# normalize_match
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('', ''),
        ('Дата  Приёма', 'дата приема'),                          # регистр, ё, пробелы
        ('Рекомендации и дата сл. приёма', 'рекомендации и дата сл приема'),  # пунктуация
        ('  Фото ', 'фото'),                                      # пробелы по краям
    ],
)
def test_normalize_match(raw, expected):
    """Заголовки приводятся к виду для сравнения."""
    assert normalize_match(raw) == expected


# ----------------------------------------------------------------------
# WordFileParser.parse_date
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('14.03.26', date(2026, 3, 14)),       # ДД.ММ.ГГ
        ('1.2.26', date(2026, 2, 1)),          # без ведущих нулей
        ('14.04.2026', date(2026, 4, 14)),     # ДД.ММ.ГГГГ
        ('2026-03-14', date(2026, 3, 14)),     # ISO
        (' 14.03.26 ', date(2026, 3, 14)),     # пробелы по краям
    ],
)
def test_parse_date_formats(raw, expected):
    """Поддерживаемые форматы даты."""
    assert WordFileParser.parse_date(raw) == expected


@pytest.mark.parametrize('raw', ['abc', '14/03/2026', '32.01.2026'])
def test_parse_date_invalid_raises(raw):
    """Нераспознанная или несуществующая дата — ValueError."""
    with pytest.raises(ValueError):
        WordFileParser.parse_date(raw)


# ----------------------------------------------------------------------
# PatientInfoExtractor.extract
# ----------------------------------------------------------------------

def test_extract_full_line():
    """ФИО, год, телефон, описание — из строки как в образцах ``doc/``."""
    dto = PatientInfoExtractor.extract('Фамилия1 Имя1 отчество1 2012 89999999999 тест тест тест')

    assert dto.last_name == 'Фамилия1'
    assert dto.first_name == 'Имя1'
    assert dto.middle_name == 'отчество1'
    assert dto.birth_date == date(2012, 1, 1)
    assert dto.description_text == 'тест тест тест'


def test_extract_docstring_example():
    """Пример из описания класса: год с «г», телефон группами, контакт."""
    dto = PatientInfoExtractor.extract('Постольник Анастасия Александровна 2012г 951 164 9014 Анна тётя')

    assert (dto.last_name, dto.first_name, dto.middle_name) == ('Постольник', 'Анастасия', 'Александровна')
    assert dto.birth_date == date(2012, 1, 1)
    assert dto.description_text == 'Анна тётя'


def test_extract_uses_first_line_only():
    """Берётся только первая строка текста до таблицы."""
    dto = PatientInfoExtractor.extract('Иванов Иван Иванович 1990\nвторая строка')

    assert dto.last_name == 'Иванов'
    assert dto.birth_date == date(1990, 1, 1)
    assert dto.description_text is None


@pytest.mark.parametrize('raw', ['', 'Иванов'])
def test_extract_unrecognized_is_none(raw):
    """Пусто или одно слово — шапка не распознана."""
    assert PatientInfoExtractor.extract(raw) is None


# ----------------------------------------------------------------------
# Журнал обработанных файлов
# ----------------------------------------------------------------------

def _write_log(path, lines):
    """Пишет журнал парсера (строки как есть)."""
    path.write_text(
        '\n'.join(lines) + '\n',
        encoding = 'utf-8',
    )


def test_successful_files_from_log(tmp_path):
    """Из журнала берутся только файлы со статусом success; прочие строки — пропуск."""
    log = tmp_path / 'parser.log'
    _write_log(
        log,
        [
            '!!>>\t2026-05-15 00:39:05\t2026-05-15 00:39:06\tа.docx\tsuccess\t',
            '!!>>\t2026-05-15 00:39:05\t2026-05-15 00:39:07\tб.docx\tfailed\tошибка',
            'продолжение многострочного сообщения об ошибке',
            '!!>>\tкороткая',
        ],
    )

    assert get_successful_files_from_log(str(log)) == {'а.docx'}


def test_successful_files_no_log(tmp_path):
    """Журнала нет — пустое множество."""
    assert get_successful_files_from_log(str(tmp_path / 'нет.log')) == set()


def test_filter_unprocessed_files(tmp_path):
    """Успешно обработанные убираются, порядок остальных сохраняется."""
    log = tmp_path / 'parser.log'
    _write_log(
        log,
        ['!!>>\tt\tt\tб.docx\tsuccess\t'],
    )

    assert filter_unprocessed_files(['а.docx', 'б.docx', 'в.docx'], str(log)) == ['а.docx', 'в.docx']


def test_get_all_docx_files_skips_temp(tmp_path):
    """Временные файлы Word (``~$…``) и не-.docx — пропускаются; регистр расширения не важен."""
    for name in ('а.docx', 'Б.DOCX', '~$а.docx', 'в.doc', 'г.txt'):
        (tmp_path / name).write_bytes(b'')

    assert set(get_all_docx_files(str(tmp_path))) == {'а.docx', 'Б.DOCX'}
