# tests/test_services/test_services_errors_review_pass1.py

"""
Тесты проверки app/services (ошибки проверки полей), проход 1 (2026-10-21).

SE1 — таблица без своего класса исключения: ошибка проверки — EntityValidationError
(поле, причина, таблица), а не голый ValueError. Таблица «Назначение» — из
tests/test_services/test_new_table_by_config.py (подключена только описанием).
"""

import pytest

from app.exceptions import EntityValidationError
from tests.test_services.test_new_table_by_config import PrescriptionDTO, env  # noqa: F401  (фикстура)


def test_se1_required_field_entity_validation_error(env):
    """Пустое обязательное поле — EntityValidationError с полем и таблицей."""
    with pytest.raises(EntityValidationError) as info:
        env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage=''))
    assert info.value.entity == 'Prescription'
    assert info.value.field
    assert 'обязатель' in info.value.reason


def test_se1_missing_parent_entity_validation_error(env):
    """Нет родительской записи — EntityValidationError, причина с таблицей родителя."""
    with pytest.raises(EntityValidationError, match='appointments') as info:
        env['rx'].create(PrescriptionDTO(appointment_id=999, dosage='1'))
    assert 'appointments' in info.value.reason


def test_se1_still_value_error(env):
    """Интерфейс, ловящий ValueError, по-прежнему ловит."""
    with pytest.raises(ValueError):
        env['rx'].create(PrescriptionDTO(appointment_id=env['a1'].id, dosage=''))
