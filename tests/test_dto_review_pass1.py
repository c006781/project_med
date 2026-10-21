# tests/test_dto_review_pass1.py

"""
Тесты исправлений проверки модуля app.dto, проход 1 (2026-10-21).

Номера (DT1 …) — журнал проверок в ``app/dto/IMPLEMENTATION.md``.
"""

import doctest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.dto as dto_package
import app.dto.compute_fields as compute_module
import app.dto.dto_all as dto_module
import app.dto.field_configs as configs_module
from app.dto import AppointmentNoteDTO
from app.dto.compute_fields import (
    PATIENT_LOAD_ERROR_TEXT,
    PATIENT_NOT_FOUND_TEXT,
    get_patient_full_name,
    join_name_parts,
)
from app.dto.field_configs import get_note_fields
from app.exceptions import PatientNotFoundError


def _service_returning(patient=None, error=None):
    """Подменённый сервис пациентов."""
    service = MagicMock()
    if error is not None:
        service.get_patient_by_id.side_effect = error
    else:
        service.get_patient_by_id.return_value = patient
    return service


def _full_name(patient=None, error=None, patient_id=1):
    """get_patient_full_name с подменённым сервисом."""
    with patch.object(compute_module, 'get_patient_service', return_value=_service_returning(patient, error)):
        return get_patient_full_name(patient_id)


# ---------------------------------------------------------------------------
# DT1 — отчества нет
# ---------------------------------------------------------------------------

def test_dt1_without_middle_name():
    """Без отчества — «Фамилия Имя» (раньше «Ошибка загрузки»)."""
    patient = SimpleNamespace(last_name='Петров', first_name='Иван', middle_name=None)
    assert _full_name(patient) == 'Петров Иван'


def test_dt1_with_middle_name():
    """С отчеством — «Фамилия Имя Отчество»."""
    patient = SimpleNamespace(last_name='Петров', first_name='Иван', middle_name='Сергеевич')
    assert _full_name(patient) == 'Петров Иван Сергеевич'


def test_dt1_model_without_middle_name_attribute():
    """У объекта нет атрибута middle_name — без ошибки."""
    patient = SimpleNamespace(last_name='Петров', first_name='Иван')
    assert _full_name(patient) == 'Петров Иван'


@pytest.mark.parametrize(
    'parts, expected',
    [
        (['Петров', 'Иван', None], 'Петров Иван'),
        ([' Петров ', '', 'Иванович'], 'Петров Иванович'),
        ([None, None, None], ''),
        ([], ''),
        (['  ', 'Иван'], 'Иван'),
        ([1, 'a'], '1 a'),
    ],
)
def test_dt1_join_name_parts(parts, expected):
    """join_name_parts пропускает пустые части."""
    assert join_name_parts(parts) == expected


# ---------------------------------------------------------------------------
# DT2 — пациент не найден / сбой
# ---------------------------------------------------------------------------

def test_dt2_not_found_exception():
    """PatientNotFoundError — «Пациент не найден» (раньше «Ошибка загрузки»)."""
    assert _full_name(error=PatientNotFoundError(5)) == PATIENT_NOT_FOUND_TEXT


def test_dt2_service_returns_none():
    """Сервис вернул None — «Пациент не найден»."""
    assert _full_name(patient=None) == PATIENT_NOT_FOUND_TEXT


def test_dt2_other_error():
    """Прочий сбой — «Ошибка загрузки»."""
    assert _full_name(error=RuntimeError('база занята')) == PATIENT_LOAD_ERROR_TEXT


def test_dt2_none_id():
    """ID не задан — пустая строка, сервис не вызывается."""
    with patch.object(compute_module, 'get_patient_service') as factory:
        assert get_patient_full_name(None) == ''
    factory.assert_not_called()


def test_dt2_texts():
    """Тексты прежние."""
    assert (PATIENT_NOT_FOUND_TEXT, PATIENT_LOAD_ERROR_TEXT) == ('Пациент не найден', 'Ошибка загрузки')


# ---------------------------------------------------------------------------
# DT3 — get_note_fields
# ---------------------------------------------------------------------------

def test_dt3_get_note_fields_returns_id_fields():
    """Возвращаются имена полей с id заметок."""
    configs = {
        'description_text': {'is_note': 'description_id'},
        'comment_text': {'is_note': 'comment_id'},
        'phone': {},
        'x': {'is_note': ''},
    }
    assert get_note_fields(configs) == ['description_id', 'comment_id']


def test_dt3_get_note_fields_patient_config():
    """У пациента — поля заметок описания и комментария."""
    assert set(get_note_fields(configs_module.PATIENT_CONFIG)) == {'description_id', 'comment_id'}


def test_dt3_get_note_fields_empty():
    """Пустая конфигурация — пустой список."""
    assert get_note_fields({}) == []


# ---------------------------------------------------------------------------
# DT4 — примеры в докстрингах; DTO
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('module', [dto_module, configs_module, compute_module])
def test_dt4_doctests(module):
    """Примеры (>>>) верны (раньше 2 примера в dto_all падали)."""
    result = doctest.testmod(module)
    assert result.failed == 0
    assert result.attempted > 0


def test_dt4_note_dto_requires_text():
    """Текст заметки обязателен."""
    with pytest.raises(Exception):
        AppointmentNoteDTO()


def test_dt4_package_exports():
    """Пакет экспортирует все DTO."""
    for name in dto_package.__all__:
        assert hasattr(dto_package, name)
