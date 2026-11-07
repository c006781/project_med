# tests/test_parsers/test_word_importer_birth_precision.py

"""Поиск пациента при импорте: дата по наименее точной из двух (Ф1.6.10е)."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.dto.dto_all import PatientDTO
from parsers import word_importer
from parsers.word_importer import PatientInfoExtractor, batch_parse, find_patients_by_key

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


def test_year_in_document_finds_exact_date_of_same_year(monkeypatch):
    stored = _stored()
    assert _found(monkeypatch, _document(), stored) == [stored]


def test_year_in_document_does_not_find_other_year(monkeypatch):
    assert _found(monkeypatch, _document(birth_date=date(1991, 1, 1)), _stored()) == []


def test_one_sided_empty_is_not_found(monkeypatch):
    """Неполное совпадение импорт сам не совмещает: приёмы добавились бы без одобрения."""
    assert _found(monkeypatch, _document(middle_name=None), _stored()) == []
    assert _found(monkeypatch, _document(birth_date=None, birth_date_precision=None), _stored()) == []


def test_both_empty_middle_name_found_as_before(monkeypatch):
    stored = _stored(middle_name=None)
    assert _found(monkeypatch, _document(middle_name=None), stored) == [stored]


@pytest.mark.parametrize('stored_date, precision', [(date(1990, 1, 1), 'day'), (date(1990, 6, 1), 'month')])
def test_stored_any_precision_same_year_found(monkeypatch, stored_date, precision):
    stored = _stored(birth_date=stored_date, birth_date_precision=precision)
    assert _found(monkeypatch, _document(), stored) == [stored]


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


def test_import_finds_exact_date_and_does_not_change_it(tmp_path, services):
    """Документ с годом находит пациента с точной датой того же года; его дата не меняется."""
    stored = services['patient_service'].create(_stored(id=None))
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    _import(str(tmp_path), services, 'а.docx', True)
    [patient] = services['patient_service'].get_all()
    assert patient.id == stored.id
    assert (patient.birth_date, patient.birth_date_precision) == (date(1990, 5, 12), 'day')
    assert len(services['appointment_service'].get_appointments_by_patient(stored.id)) == 1


def test_import_without_search_never_matches(tmp_path, services):
    services['patient_service'].create(_stored(id=None))
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    _import(str(tmp_path), services, 'а.docx', False)
    assert len(services['patient_service'].get_all()) == 2
