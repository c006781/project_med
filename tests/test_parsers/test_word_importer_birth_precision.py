# tests/test_parsers/test_word_importer_birth_precision.py

"""Импорт и точность даты (Ф1.6.10е): год хранится как «только год», поиск — как прежний ``patient_key``."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.dto.dto_all import PatientDTO
from parsers import word_importer
from parsers.word_importer import PatientInfoExtractor, batch_parse, find_patients_by_key, patient_key

from tests.test_parsers.test_word_importer_docx import ROWS, make_docx

HEADER = 'Иванов Иван Иванович 1990 89991234567 тётя Анна'


def _stored(**fields):
    defaults = {
        'id': 1,
        'last_name': 'Иванов',
        'first_name': 'Иван',
        'middle_name': 'Иванович',
        'birth_date': date(1990, 5, 12),
        'birth_date_precision': 'day',
    }
    return PatientDTO(**{**defaults, **fields})


def _found(monkeypatch, document, *stored):
    repository = MagicMock()
    repository.return_value.get_all.return_value = list(stored)
    monkeypatch.setattr(word_importer, 'PatientRepository', repository)
    return find_patients_by_key(MagicMock(), document)


def _document(**fields):
    defaults = {
        'last_name': 'Иванов',
        'first_name': 'Иван',
        'middle_name': 'Иванович',
        'birth_date': date(1990, 1, 1),
        'birth_date_precision': 'year',
    }
    return PatientDTO(**{**defaults, **fields})


def test_header_year_gets_year_precision():
    dto = PatientInfoExtractor.extract('Иванов Иван Иванович 1990г 89991234567')
    assert (dto.birth_date, dto.birth_date_precision) == (date(1990, 1, 1), 'year')


def test_header_without_year_has_no_precision():
    dto = PatientInfoExtractor.extract('Иванов Иван Иванович')
    assert dto.birth_date is None and dto.birth_date_precision is None


def test_year_in_document_does_not_find_exact_date_of_same_year(monkeypatch):
    """Совпадение по году сразу добавило бы приёмы без одобрения: до формы — только равная дата."""
    assert _found(monkeypatch, _document(), _stored()) == []


def test_year_in_document_finds_equal_date(monkeypatch):
    stored = _stored(birth_date=date(1990, 1, 1))
    assert _found(monkeypatch, _document(), stored) == [stored]


def test_year_in_document_does_not_find_other_year(monkeypatch):
    assert _found(monkeypatch, _document(birth_date=date(1991, 1, 1)), _stored()) == []


def test_one_sided_empty_is_not_found(monkeypatch):
    """Неполное совпадение импорт сам не совмещает: приёмы добавились бы без одобрения."""
    assert _found(monkeypatch, _document(middle_name=None), _stored()) == []
    assert _found(monkeypatch, _document(birth_date=None, birth_date_precision=None), _stored()) == []


def test_both_empty_middle_name_found_as_before(monkeypatch):
    stored = _stored(middle_name=None, birth_date=date(1990, 1, 1))
    assert _found(monkeypatch, _document(middle_name=None), stored) == [stored]


@pytest.mark.parametrize(
    'stored_date, precision, found',
    [
        (date(1990, 1, 1), 'day', True),     # та же дата: точность не учитывается
        (date(1990, 1, 1), 'year', True),
        (date(1990, 6, 1), 'month', False),  # тот же год, другая дата
        (date(1990, 5, 12), 'day', False),
    ],
)
def test_found_only_by_equal_date_at_any_precision(monkeypatch, stored_date, precision, found):
    stored = _stored(birth_date=stored_date, birth_date_precision=precision)
    assert _found(monkeypatch, _document(), stored) == ([stored] if found else [])


# (фамилия, имя, отчество, дата, точность) документа и базы: отбор равен прежнему patient_key
BASE = ('Ёлкин', 'Иван', 'Петрович', date(1990, 1, 1), 'year')


@pytest.mark.parametrize(
    'document, stored',
    [
        (BASE, BASE),
        (BASE, ('ЕЛКИН ', 'иван', ' петрович', date(1990, 1, 1), 'day')),   # регистр, «ё», пробелы
        (BASE, ('Елкин.', 'Иван', 'Петрович', date(1990, 1, 1), None)),     # пунктуация
        (BASE, ('Елкин', 'Иван', 'Петрович', date(1990, 6, 14), 'day')),    # тот же год
        (BASE, ('Елкин', 'Иван', 'Петрович', date(1990, 6, 1), 'month')),   # тот же год
        (BASE, ('Елкин', 'Иван', 'Петрович', date(1991, 1, 1), 'year')),    # другой год
        (BASE, ('Елкин', 'Иван', 'Петрович', None, None)),                  # даты нет в базе
        (('Елкин', 'Иван', 'Петрович', None, None), BASE),                  # даты нет в документе
        (('Елкин', 'Иван', 'Петрович', None, None), ('елкин', 'иван', 'петрович', None, None)),
        (BASE, ('Елкин', 'Иван', None, date(1990, 1, 1), 'year')),          # отчества нет в базе
        (('Елкин', 'Иван', None, date(1990, 1, 1), 'year'), BASE),          # отчества нет в документе
        (('Елкин', 'Иван', None, date(1990, 1, 1), 'year'), ('Елкин', 'Иван', '', date(1990, 1, 1), 'day')),
        (BASE, ('Елкин', 'Иван', 'Иванович', date(1990, 1, 1), 'year')),    # другое отчество
        (BASE, ('Петров', 'Иван', 'Петрович', date(1990, 1, 1), 'year')),   # другая фамилия
        (BASE, ('Елкин', 'Пётр', 'Петрович', date(1990, 1, 1), 'year')),    # другое имя
    ],
)
def test_same_result_as_patient_key(monkeypatch, document, stored):
    names = ('last_name', 'first_name', 'middle_name', 'birth_date', 'birth_date_precision')
    document_dto = PatientDTO(**dict(zip(names, document)))
    stored_dto = PatientDTO(id=1, **dict(zip(names, stored)))
    expected = patient_key(*document[:4]) == patient_key(*stored[:4])
    assert _found(monkeypatch, document_dto, stored_dto) == ([stored_dto] if expected else [])


# --- импорт целиком ---------------------------------------------------------

def _import(folder, services, name, find_existing):
    results, _ = batch_parse(
        folder,
        specific_files        = [name],
        find_existing_patient = find_existing,
        **services,
    )
    assert results['success'] == 1, results['error_files']


def test_import_new_patient_stored_with_year_precision(tmp_path, services):
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    _import(str(tmp_path), services, 'а.docx', False)
    [patient] = services['patient_service'].get_all()
    assert patient.birth_date == date(1990, 1, 1) and patient.birth_date_precision == 'year'


def test_import_year_does_not_join_exact_date(tmp_path, services):
    """Документ с годом не добавляет приёмы пациенту с точной датой: новый пациент, дубль найдёт поиск."""
    stored = services['patient_service'].create(_stored(id=None))
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    _import(str(tmp_path), services, 'а.docx', True)
    patients = {p.id: p for p in services['patient_service'].get_all()}
    assert len(patients) == 2
    assert (patients[stored.id].birth_date, patients[stored.id].birth_date_precision) == (date(1990, 5, 12), 'day')
    assert services['appointment_service'].get_appointments_by_patient(stored.id) == []
    [new_id] = set(patients) - {stored.id}
    assert patients[new_id].birth_date_precision == 'year'


def test_import_year_joins_equal_date(tmp_path, services):
    stored = services['patient_service'].create(_stored(id=None, birth_date=date(1990, 1, 1)))
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    _import(str(tmp_path), services, 'а.docx', True)
    [patient] = services['patient_service'].get_all()
    assert patient.id == stored.id
    assert len(services['appointment_service'].get_appointments_by_patient(stored.id)) == 1


def test_import_without_search_never_matches(tmp_path, services):
    services['patient_service'].create(_stored(id=None))
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    _import(str(tmp_path), services, 'а.docx', False)
    assert len(services['patient_service'].get_all()) == 2
