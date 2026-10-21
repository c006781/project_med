# tests/test_schema/test_schema_review_pass1.py

"""
Тесты исправлений проверки app/schema, проход 1 (2026-10-21).

SC1 — id заметок в DTO из описаний таблиц снова ``exclude=True`` (регрессия 2026-10-19,
DT6 в ``app/dto/IMPLEMENTATION.md``). Старый тест сравнения DTO (``dto_snapshot``) не
проверял ``exclude`` — поэтому регрессия не была замечена.
"""

import pytest

from app.dto import AppointmentDTO, PatientDTO, PhotoDTO
from app.schema.clinic import CLINIC_DEFS

DTO_BY_NAME = {dto.__name__: dto for dto in (PatientDTO, AppointmentDTO, PhotoDTO)}


def _note_specs(table):
    """Поля-заметки описания таблицы."""
    return [spec for spec in table.fields if spec.kind == 'note' and spec.dto]


@pytest.mark.parametrize('table', CLINIC_DEFS, ids=lambda t: t.name)
def test_sc1_note_ids_excluded(table):
    """У каждого поля-заметки: <x>_id — exclude=True, <x>_text — выгружается."""
    dto = DTO_BY_NAME[table.dto_name]
    for spec in _note_specs(table):
        assert dto.model_fields[spec.id_name].exclude is True, spec.id_name
        assert not dto.model_fields[spec.text_name].exclude, spec.text_name


def test_sc1_patient_dump_without_note_ids():
    """model_dump пациента — без id заметок, с текстами."""
    data = PatientDTO(first_name='И', last_name='П', description_id=3, description_text='т').model_dump()
    assert 'description_id' not in data and 'comment_id' not in data
    assert data['description_text'] == 'т'


def test_sc1_ids_still_readable():
    """id заметки доступен как атрибут (сервисы читают его напрямую)."""
    assert PatientDTO(first_name='И', last_name='П', description_id=3).description_id == 3


def test_sc1_appointment_dump_without_note_ids():
    """model_dump приёма — без id заметок; patient_id (не заметка) — выгружается."""
    data = AppointmentDTO(patient_id=1, date='2026-01-01', reason_id=5).model_dump()
    for name in ('reason_id', 'procedure_id', 'recommendations_id', 'note_id', 'cost_procedure_id'):
        assert name not in data
    assert data['patient_id'] == 1


def test_sc1_tables_have_note_fields():
    """Проверка не пустая: заметки есть у пациентов и приёмов."""
    assert sum(len(_note_specs(t)) for t in CLINIC_DEFS) >= 7
