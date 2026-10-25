# tests/test_parsers/test_word_importer_find_existing.py

"""
Поиск существующего пациента при импорте из Word — ТД-8 (``_dev/ТЕХДОЛГ.md``).

Решение владельца 2026-10-25 («совмещённый вариант»): по умолчанию импорт не совмещает
(каждый документ — новый пациент); пользователь может включить поиск по ФИО + году
рождения (окно — флажок перед импортом, ``pars_start.py --find_existing_patient``):
один найденный — приёмы к нему, повторные (та же дата и тексты) пропускаются; несколько —
новый пациент и предупреждение «возможный дубль». Дубли объединяются в программе
(``_dev/ПЛАН.md`` Ф1.6.10а). Документы — синтетические, БД — в памяти.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from parsers.word_importer import (
    appointment_key,
    batch_parse,
    patient_key,
)
from tests.test_parsers.test_word_importer_docx import (
    ROWS,
    make_docx,
)


HEADER = 'Иванов Иван Иванович 1990 89991234567 тётя Анна'


def _import(
    folder        : str,           # папка документов
    services      : dict,          # сервисы и БД
    file_name     : str,           # какой файл импортировать
    find_existing : bool = False,  # искать существующего пациента
):
    """Импорт одного файла папки; возвращает результаты batch_parse."""
    results, _ = batch_parse(
        folder,
        specific_files        = [file_name],
        find_existing_patient = find_existing,
        **services,
    )
    return results


# ----------------------------------------------------------------------
# Ключи
# ----------------------------------------------------------------------

def test_patient_key_normalized():
    """Ключ пациента: регистр, «ё», пробелы не важны; от даты рождения — только год."""
    assert patient_key('Ёлкин ', 'иван', None, date(1990, 5, 12)) == patient_key('ЕЛКИН', 'Иван', '', date(1990, 1, 1))
    assert patient_key('Ёлкин', 'Иван', None, date(1990, 1, 1)) != patient_key('Ёлкин', 'Иван', None, date(1991, 1, 1))


def test_appointment_key_from_row_and_dto():
    """Ключ приёма одинаков у строки документа и у DTO из базы (тексты нормализуются)."""
    row = {'date': date(2026, 3, 14), 'reason_text': 'боль  в зубе', 'note_text': None}
    stored = SimpleNamespace(            # приём из базы — объект с атрибутами, как DTO
        date                 = date(2026, 3, 14),
        reason_text          = 'боль в зубе',
        procedure_text       = None,
        recommendations_text = None,
        cost_procedure_text  = None,
        note_text            = None,
    )

    assert appointment_key(row) == appointment_key(stored)


# ----------------------------------------------------------------------
# Поиск выключен (по умолчанию)
# ----------------------------------------------------------------------

def test_default_no_matching(tmp_path, services):
    """По умолчанию каждый документ — новый пациент, даже при тех же ФИО и годе."""
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS)
    make_docx(str(tmp_path / 'б.docx'), HEADER, ROWS)

    _import(str(tmp_path), services, 'а.docx')
    _import(str(tmp_path), services, 'б.docx')

    assert len(services['patient_service'].get_all()) == 2


# ----------------------------------------------------------------------
# Поиск включён
# ----------------------------------------------------------------------

def test_found_one_adds_appointments_skips_repeats(tmp_path, services):
    """Один найденный: новые приёмы — к нему, повторный пропущен с предупреждением, без падения на описании."""
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    make_docx(
        str(tmp_path / 'б.docx'),
        'ИВАНОВ иван Иванович 1990 89991234567 тётя Анна',     # регистр другой
        ROWS,                                                   # первый приём — повтор
    )
    _import(str(tmp_path), services, 'а.docx')

    results = _import(str(tmp_path), services, 'б.docx', find_existing=True)

    assert results['success'] == 1, results['error_files']
    [patient] = services['patient_service'].get_all()
    appointments = services['appointment_service'].get_appointments_by_patient(patient.id)
    assert sorted(a.date for a in appointments) == [date(2026, 3, 14), date(2026, 4, 14)]
    [warning] = [w['warning'] for w in results['warnings']]
    assert 'уже есть' in warning and '14.03.2026' in warning


def test_found_one_reports_differences(tmp_path, services):
    """Один найденный с другим телефоном: данные пациента не меняются, предупреждение."""
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS[:1])
    make_docx(str(tmp_path / 'б.docx'), 'Иванов Иван Иванович 1990 89990000000', ROWS[1:])
    _import(str(tmp_path), services, 'а.docx')

    results = _import(str(tmp_path), services, 'б.docx', find_existing=True)

    [patient] = services['patient_service'].get_all()
    assert patient.phone == '+7 (999) 123-45-67'      # из первого документа, не изменён
    warnings = ' '.join(w['warning'] for w in results['warnings'])
    assert '+7 (999) 000-00-00' in warnings
    assert 'не изменён' in warnings


def test_found_several_creates_new_with_warning(tmp_path, services):
    """Несколько найденных (дубли уже есть): новый пациент, предупреждение «возможный дубль»."""
    make_docx(str(tmp_path / 'а.docx'), HEADER, ROWS)
    make_docx(str(tmp_path / 'б.docx'), HEADER, ROWS)
    make_docx(str(tmp_path / 'в.docx'), HEADER, ROWS)
    _import(str(tmp_path), services, 'а.docx')
    _import(str(tmp_path), services, 'б.docx')

    results = _import(str(tmp_path), services, 'в.docx', find_existing=True)

    assert results['success'] == 1
    assert len(services['patient_service'].get_all()) == 3
    [warning] = [w['warning'] for w in results['warnings']]
    assert 'дубль' in warning


@pytest.mark.parametrize('flag', ['--find_existing_patient', '--update_existing_patient'])
def test_pars_start_args_find_flag(tmp_path, flag, monkeypatch):
    """Флаг поиска в командной строке; старое имя --update_existing_patient — то же самое."""
    import parsers.word_importer as word_importer
    calls = []
    monkeypatch.setattr(word_importer, 'pars_start', lambda **kwargs: calls.append(kwargs) or {})

    word_importer.pars_start_args(argv=['--folder', str(tmp_path), flag])

    assert calls[0]['find_existing_patient'] is True
