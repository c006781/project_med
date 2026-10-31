# tests/test_utils/test_record_keys.py

"""Ключи сравнения записей (app/utils/record_keys.py, Ф1.6.10а; перенесены из parsers)."""

from datetime import date

from app.dto.dto_all import PatientDTO
from app.utils.record_keys import appointment_key, normalize_match, normalize_text, record_key

FIO_DATE = ('last_name', 'first_name', 'middle_name', 'birth_date')


def test_record_key_ignores_case_yo_spaces_and_empty_middle_name():
    a = PatientDTO(last_name='Ёлкина ', first_name='мария', middle_name=None, birth_date=date(1985, 6, 14))
    b = {'last_name': 'елкина', 'first_name': 'Мария', 'middle_name': '', 'birth_date': date(1985, 6, 14)}
    assert record_key(a, FIO_DATE) == record_key(b, FIO_DATE)


def test_record_key_compares_full_birth_date():
    # Решение владельца 2026-10-31: 01.01 (импорт, только год) и точная дата — разные пациенты
    a = {'last_name': 'Иванова', 'first_name': 'Мария', 'birth_date': date(1985, 1, 1)}
    b = dict(a, birth_date=date(1985, 6, 14))
    assert record_key(a, FIO_DATE) != record_key(b, FIO_DATE)


def test_appointment_key_normalizes_texts():
    assert appointment_key({'date': date(2026, 3, 14), 'reason_text': ' боль  '}) == \
        (date(2026, 3, 14), 'боль', None, None, None, None)


def test_parsers_use_same_functions():
    from parsers import word_importer
    assert word_importer.normalize_text is normalize_text
    assert word_importer.normalize_match is normalize_match
    assert word_importer.appointment_key is appointment_key
