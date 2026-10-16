# tests/test_services/test_data_layer_review.py

"""
Проверка слоя данных (DTO, field_configs, репозитории, BaseService) на НАСТОЯЩЕЙ SQLite
во временной папке (с настоящими commit/rollback и удалением файлов после коммита).

Ошибки, найденные при проверке, — номера DATA*/DB* из app/services/IMPLEMENTATION.md.
"""

import datetime
import os

import pytest

from app.database import Database
from app.database.database_shema.clinic import Appointment, AppointmentNote, Patient
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.exceptions.exceptions_all import AppointmentNoteNotFoundError
from app.services import AppointmentService, NoteService, PatientService, PhotoService


@pytest.fixture
def svc(tmp_path):
    """Сервисы как в app/dependencies.py, на файле SQLite."""
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    storage.mkdir()
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    yield {'db': db, 'note': note, 'photo': photo, 'appointment': appointment,
           'patient': patient, 'storage': storage, 'tmp': tmp_path}
    db.close()


def _patient(svc, last='Петров'):
    return svc['patient'].create(PatientDTO(first_name='Иван', last_name=last,
                                            birth_date=datetime.date(1980, 5, 5)))


def _appointment(svc, patient_id, **fields):
    return svc['appointment'].create(AppointmentDTO(patient_id=patient_id,
                                                    date=datetime.date(2026, 10, 16), **fields))


# ---------------------------------------------------------------------------
# DB1: repr заметки
# ---------------------------------------------------------------------------

def test_db1_note_repr():
    assert repr(AppointmentNote(id=3, text='Длинный текст заметки')) == \
        "<Note(id=3, text_preview=Длинный текст заметки)>"
    assert repr(AppointmentNote(text=None)) == "<Note(id=None, text_preview=)>"


# ---------------------------------------------------------------------------
# DATA1: правка текста общей заметки не должна менять её у других записей
# ---------------------------------------------------------------------------

def test_data1_shared_note_edit_does_not_affect_others(svc):
    p = _patient(svc)
    a1 = _appointment(svc, p.id, procedure_text='Чистка')
    a2 = _appointment(svc, p.id, procedure_id=a1.procedure_id)          # та же заметка
    assert a2.procedure_text == 'Чистка'

    dto = svc['appointment'].get_by_id(a1.id).model_copy(update={'procedure_text': 'Пломба'})
    svc['appointment'].update(dto)

    assert svc['appointment'].get_by_id(a1.id).procedure_text == 'Пломба'
    assert svc['appointment'].get_by_id(a2.id).procedure_text == 'Чистка'


def test_data1_unused_old_note_removed(svc):
    p = _patient(svc)
    a = _appointment(svc, p.id, procedure_text='Чистка')
    old_id = a.procedure_id
    dto = svc['appointment'].get_by_id(a.id).model_copy(update={'procedure_text': 'Пломба'})
    updated = svc['appointment'].update(dto)
    assert updated.procedure_id != old_id
    with pytest.raises(AppointmentNoteNotFoundError):
        svc['note'].get_note(old_id)


def test_data1_same_text_reuses_existing_note(svc):
    p = _patient(svc)
    a1 = _appointment(svc, p.id, procedure_text='Чистка')
    a2 = _appointment(svc, p.id, procedure_text='Пломба')
    dto = svc['appointment'].get_by_id(a2.id).model_copy(update={'procedure_text': 'Чистка'})
    assert svc['appointment'].update(dto).procedure_id == a1.procedure_id


# ---------------------------------------------------------------------------
# DATA2: «текст не передан» ≠ «текст очищен»
# ---------------------------------------------------------------------------

def test_data2_create_with_existing_note_id(svc):
    p = _patient(svc)
    note = svc['note'].create_note('Общая заметка')
    a = _appointment(svc, p.id, note_id=note.id)
    assert a.note_id == note.id and a.note_text == 'Общая заметка'


def test_data2_update_without_note_texts_keeps_notes(svc):
    """DTO без текстов заметок (поля не переданы) — заметки не стираются."""
    p = _patient(svc)
    a = _appointment(svc, p.id, procedure_text='Чистка')
    bare = AppointmentDTO(id=a.id, patient_id=p.id, date=datetime.date(2026, 1, 1),
                          procedure_id=a.procedure_id)
    svc['appointment'].update(bare)
    assert svc['appointment'].get_by_id(a.id).procedure_text == 'Чистка'


def test_data2_empty_text_clears_note(svc):
    p = _patient(svc)
    a = _appointment(svc, p.id, procedure_text='Чистка')
    dto = svc['appointment'].get_by_id(a.id).model_copy(update={'procedure_text': ''})
    updated = svc['appointment'].update(dto)
    assert updated.procedure_id is None and not updated.procedure_text


def test_data2_shared_note_kept_until_last_user_deleted(svc):
    p = _patient(svc)
    note = svc['note'].create_note('Общая заметка')
    a1 = _appointment(svc, p.id, note_id=note.id)
    a2 = _appointment(svc, p.id, note_id=note.id)
    svc['appointment'].delete(a1.id)
    assert svc['note'].get_note(note.id).text == 'Общая заметка'
    svc['appointment'].delete(a2.id)
    with pytest.raises(AppointmentNoteNotFoundError):
        svc['note'].get_note(note.id)


# ---------------------------------------------------------------------------
# DATA3: страница приёмов пациента
# ---------------------------------------------------------------------------

def test_data3_appointments_by_patient_page(svc):
    p, other = _patient(svc), _patient(svc, 'Сидоров')
    for _ in range(5):
        _appointment(svc, p.id)
    _appointment(svc, other.id)
    items, total = svc['appointment'].get_appointments_by_patient_page(p.id, 0, 2)
    assert total == 5 and len(items) == 2 and all(i.patient_id == p.id for i in items)


# ---------------------------------------------------------------------------
# DATA4: нечёткий поиск
# ---------------------------------------------------------------------------

def test_data4_fuzzy_filter(svc):
    for last in ('Иванов', 'Иванофф', 'Петров'):
        _patient(svc, last)
    found = svc['patient'].get_patients_filtered(
        [{'column': 'last_name', 'operator': 'fuzzy', 'value': 'Иванов'}], fuzzy_threshold=70)
    assert sorted(p.last_name for p in found) == ['Иванов', 'Иванофф']


def test_data4_fuzzy_combined_with_sql_filter(svc):
    for last in ('Иванов', 'Иванофф', 'Петров'):
        _patient(svc, last)
    found = svc['patient'].get_patients_filtered([
        {'column': 'last_name', 'operator': 'fuzzy', 'value': 'Иванов'},
        {'column': 'last_name', 'operator': 'ne', 'value': 'Иванофф'},
    ], fuzzy_threshold=70)
    assert [p.last_name for p in found] == ['Иванов']


# ---------------------------------------------------------------------------
# Файлы фото удаляются после коммита (на настоящей БД)
# ---------------------------------------------------------------------------

def test_photo_file_removed_after_delete(svc):
    p = _patient(svc)
    a = _appointment(svc, p.id)
    src = svc['tmp'] / 'src.jpg'
    src.write_bytes(b'\xff\xd8fake')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(src)))
    stored = svc['storage'] / photo.file_path
    assert stored.exists()
    svc['photo'].delete(photo.id)
    assert not stored.exists()


def test_data8_replaced_photo_file_removed(svc):
    """DATA8: при замене файла фото старый файл удаляется с диска (после коммита)."""
    p = _patient(svc)
    a = _appointment(svc, p.id)
    first, second = svc['tmp'] / 'a.jpg', svc['tmp'] / 'b.jpg'
    first.write_bytes(b'a')
    second.write_bytes(b'b')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(first)))
    old_file = svc['storage'] / photo.file_path
    updated = svc['photo'].update(photo.model_copy(update={'file_path': str(second)}))
    assert not old_file.exists()
    assert (svc['storage'] / updated.file_path).read_bytes() == b'b'


# ---------------------------------------------------------------------------
# DATA7: постраничная выдача с нечётким поиском
# ---------------------------------------------------------------------------

def test_data7_fuzzy_paging_counts_after_filter(svc):
    for last in ('Иванов', 'Петров', 'Иванофф', 'Сидоров', 'Иванова'):
        _patient(svc, last)
    fuzzy = [{'column': 'last_name', 'operator': 'fuzzy', 'value': 'Иванов'}]
    page1, total = svc['patient'].get_page_filtered(0, 2, filters=fuzzy, fuzzy_threshold=70)
    page2, _ = svc['patient'].get_page_filtered(2, 2, filters=fuzzy, fuzzy_threshold=70)
    assert total == 3
    assert len(page1) == 2 and len(page2) == 1
    assert {p.last_name for p in page1 + page2} == {'Иванов', 'Иванофф', 'Иванова'}


def test_data4b_fuzzy_inside_or_rejected(svc):
    _patient(svc)
    tree = {'or': [{'column': 'last_name', 'operator': 'fuzzy', 'value': 'Иванов'},
                   {'column': 'last_name', 'operator': 'eq', 'value': 'Петров'}]}
    with pytest.raises(ValueError, match="внутри 'or'"):
        svc['patient'].get_page_filtered(0, 10, filters=tree)


# ---------------------------------------------------------------------------
# DATA12 (N+1) и B5 (вложенные DTO)
# ---------------------------------------------------------------------------

def _count_queries(db, action):
    from sqlalchemy import event
    count = {'n': 0}

    def on_execute(*args, **kwargs):
        count['n'] += 1

    event.listen(db.engine, 'before_cursor_execute', on_execute)
    try:
        result = action()
    finally:
        event.remove(db.engine, 'before_cursor_execute', on_execute)
    return result, count['n']


def test_data12_page_queries_do_not_grow_with_rows(svc):
    p = _patient(svc)
    for i in range(3):
        _appointment(svc, p.id, procedure_text=f'proc {i}')
    (_, small), n_small = _count_queries(svc['db'], lambda: svc['appointment'].get_page(0, 50))
    for i in range(30):
        _appointment(svc, p.id, procedure_text=f'proc {i % 3}')
    (items, total), n_big = _count_queries(svc['db'], lambda: svc['appointment'].get_page(0, 50))
    assert total == 33 and n_big == n_small                  # не «строк + 2»
    assert items[0].procedure_text and items[0].has_photos is not None


def test_b5_nested_photos_are_dtos_without_warnings(svc):
    import warnings
    p = _patient(svc)
    a = _appointment(svc, p.id)
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(src)))
    detail = svc['appointment'].get_by_id(a.id)
    assert detail.photos and all(isinstance(ph, PhotoDTO) for ph in detail.photos)
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        detail.model_dump()


def test_data14_cascade_delete_without_double_delete(svc):
    """DATA14: удаление пациента → приёмы → фото и файлы, без повторного DELETE (SAWarning)."""
    import warnings
    from sqlalchemy.exc import SAWarning
    p = _patient(svc)
    a = _appointment(svc, p.id, procedure_text='Чистка')
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(src)))
    stored = svc['storage'] / photo.file_path
    with warnings.catch_warnings():
        warnings.simplefilter('error', SAWarning)
        svc['patient'].delete_patient(p.id)
    assert svc['appointment'].get_all() == [] and svc['photo'].get_all() == []
    assert not stored.exists()
    with pytest.raises(AppointmentNoteNotFoundError):
        svc['note'].get_note(a.procedure_id)


def test_data10_photo_update_uses_service_storage_not_global_config(svc, monkeypatch):
    """DATA10: замена файла фото не обращается к глобальному конфигу и не удаляет дважды."""
    import app.services.services_all as sa
    p = _patient(svc)
    a = _appointment(svc, p.id)
    first, second = svc['tmp'] / 'a.jpg', svc['tmp'] / 'b.jpg'
    first.write_bytes(b'a')
    second.write_bytes(b'b')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(first)))

    def no_global_config(*args, **kwargs):
        raise AssertionError('сервис полез в глобальный конфиг приложения')

    monkeypatch.setattr(sa.AppConfigManager, 'get_instance', no_global_config)
    updated = svc['photo'].update(photo.model_copy(update={'file_path': str(second)}))
    assert (svc['storage'] / updated.file_path).exists()


def test_data11_ignored_non_updatable_change_reported(svc):
    p = _patient(svc)
    a1, a2 = _appointment(svc, p.id), _appointment(svc, p.id)
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=str(src)))
    got = []
    handler = svc['photo'].logger.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    try:
        svc['photo'].update(photo.model_copy(update={'appointment_id': a2.id, 'description': 'd'}))
    finally:
        svc['photo'].logger.remove_output(handler)
    assert svc['photo'].get_by_id(photo.id).appointment_id == a1.id     # как раньше — не переносится
    assert any(line.startswith('WARNING|') and 'appointment_id' in line for line in got)
