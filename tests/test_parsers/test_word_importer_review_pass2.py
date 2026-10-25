# tests/test_parsers/test_word_importer_review_pass2.py

"""
Тесты исправлений проверки ``parsers/word_importer.py``, проход 2 — итоговая
перепроверка модуля (2026-10-25).

Номера W11–W13 — ``parsers/IMPLEMENTATION.md`` §4. На старом коде эти тесты падают.
Документы — синтетические (``test_word_importer_docx.make_docx``), БД — в памяти.
"""

import pytest

from parsers.word_importer import batch_parse
from tests.test_parsers.test_word_importer_docx import (  # noqa: F401 (services — фикстура)
    ROWS,
    make_docx,
    services,
)


def test_w11_invalid_date_message(tmp_path, services):
    """W11: неверная дата — в сообщении поле и само значение, а не «отсутствует»."""
    make_docx(
        str(tmp_path / 'а.docx'),
        'Иванов Иван Иванович 1990',
        [['32.13.26', 'причина', '', '', '', '']],
    )

    results, _ = batch_parse(
        str(tmp_path),
        **services,
    )

    [error] = results['error_files']
    text = str(error['error'])
    assert 'Отсутствуют' not in text
    assert 'Дата приёма' in text
    assert '32.13.26' in text


def test_w12_text_in_photo_cell(tmp_path, services):
    """W12: текст в ячейке «Фото» без рисунка — не путь к файлу; файл импортируется без фото."""
    make_docx(
        str(tmp_path / 'а.docx'),
        'Иванов Иван Иванович 1990',
        [['14.03.26', 'причина', '', '', '', '', 'нет фото']],
    )

    results, _ = batch_parse(
        str(tmp_path),
        **services,
    )

    assert results['success'] == 1, results['error_files']
    [patient] = services['patient_service'].get_all()
    [appointment] = services['appointment_service'].get_appointments_by_patient(patient.id)
    assert services['photo_service'].get_photos_for_appointment(appointment.id) == []


def test_w13_specific_files_extension_case(tmp_path, services):
    """W13: файл «.DOCX» из списка (--files) обрабатывается, как и при отборе всей папки."""
    make_docx(
        str(tmp_path / 'Б.DOCX'),
        'Иванов Иван Иванович 1990',
        ROWS,
    )

    results, _ = batch_parse(
        str(tmp_path),
        specific_files = ['Б.DOCX'],
        **services,
    )

    assert (results['total'], results['success']) == (1, 1)


@pytest.mark.xfail(
    strict = True,     # исправят ТД-8 — тест начнёт проходить, пометку снять
    reason = 'ТД-8: find_matching_patient читает Patient.description_text — у ORM его нет',
)
def test_td8_update_existing_patient_with_description(tmp_path, services):
    """ТД-8: повторный импорт с обновлением пациента и описанием в шапке — без падения и дублей."""
    make_docx(
        str(tmp_path / 'а.docx'),
        'Иванов Иван Иванович 1990 89991234567 тётя Анна',
        ROWS,
    )
    batch_parse(
        str(tmp_path),
        specific_files = ['а.docx'],
        **services,
    )

    results, _ = batch_parse(
        str(tmp_path),
        specific_files          = ['а.docx'],
        update_existing_patient = True,
        **services,
    )

    assert results['success'] == 1, results['error_files']
    assert len(services['patient_service'].get_all()) == 1
