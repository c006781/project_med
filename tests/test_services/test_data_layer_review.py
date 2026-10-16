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


# ↓ до решения владельца 2026-10-16 («перенос разрешён»): тест фиксировал, что перенос фото
#   не сохраняется, но об этом пишется предупреждение.
# def test_data11_ignored_non_updatable_change_reported(svc):
#     p = _patient(svc)
#     a1, a2 = _appointment(svc, p.id), _appointment(svc, p.id)
#     src = svc['tmp'] / 's.jpg'
#     src.write_bytes(b'x')
#     photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=str(src)))
#     got = []
#     handler = svc['photo'].logger.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
#     try:
#         svc['photo'].update(photo.model_copy(update={'appointment_id': a2.id, 'description': 'd'}))
#     finally:
#         svc['photo'].logger.remove_output(handler)
#     assert svc['photo'].get_by_id(photo.id).appointment_id == a1.id     # как раньше — не переносится
#     assert any(line.startswith('WARNING|') and 'appointment_id' in line for line in got)


# ---------------------------------------------------------------------------
# Перенос к другому родителю (решение владельца 2026-10-16: разрешён)
# ---------------------------------------------------------------------------

def test_move_photo_to_other_appointment(svc):
    p = _patient(svc)
    a1, a2 = _appointment(svc, p.id), _appointment(svc, p.id)
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=str(src)))
    moved = svc['photo'].update(photo.model_copy(update={'appointment_id': a2.id}))
    assert moved.appointment_id == a2.id
    assert (svc['storage'] / moved.file_path).exists()            # файл на месте
    counts = {a.id: a.has_photos for a in svc['appointment'].get_page(0, 10)[0]}
    assert counts[a2.id] != counts[a1.id]


def test_move_appointment_to_other_patient(svc):
    p1, p2 = _patient(svc), _patient(svc, 'Сидоров')
    a = _appointment(svc, p1.id, procedure_text='Чистка')
    moved = svc['appointment'].update(svc['appointment'].get_by_id(a.id).model_copy(
        update={'patient_id': p2.id}))
    assert moved.patient_id == p2.id and moved.procedure_text == 'Чистка'
    assert svc['appointment'].get_appointments_by_patient_page(p1.id, 0, 10)[1] == 0


def test_move_to_missing_parent_rejected(svc):
    from app.exceptions.exceptions_all import AppointmentNotFoundError, PatientNotFoundError
    p = _patient(svc)
    a = _appointment(svc, p.id)
    with pytest.raises(PatientNotFoundError):
        svc['appointment'].update(svc['appointment'].get_by_id(a.id).model_copy(update={'patient_id': 999}))
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    photo = svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(src)))
    with pytest.raises(AppointmentNotFoundError):
        svc['photo'].update(photo.model_copy(update={'appointment_id': 999}))
    with pytest.raises(AppointmentNotFoundError):
        svc['photo'].create(PhotoDTO(appointment_id=999, file_path=str(src)))
    assert svc['photo'].get_by_id(photo.id).appointment_id == a.id


def test_data11_no_false_warning_on_note_text_change(svc):
    """Ссылки на заметки меняет механизм заметок — предупреждения «не изменяется» нет."""
    p = _patient(svc)
    a = _appointment(svc, p.id, procedure_text='Чистка')
    got = []
    handler = svc['appointment'].logger.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    try:
        svc['appointment'].update(svc['appointment'].get_by_id(a.id).model_copy(
            update={'procedure_text': 'Пломба'}))
    finally:
        svc['appointment'].logger.remove_output(handler)
    assert not [line for line in got if 'updatable=False' in line]


# ---------------------------------------------------------------------------
# Проход по замыслу «всё из описания полей» (DYN*)
# ---------------------------------------------------------------------------

def test_dyn1_add_photo_uses_generic_create_and_cleans_on_rollback(svc):
    """DYN1: старый путь добавления фото — через общий create: при откате файл удаляется."""
    from app.exceptions.exceptions_all import AppointmentNotFoundError, PhotoFileError
    p = _patient(svc)
    a = _appointment(svc, p.id)
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    dto = svc['photo'].add_photo_to_appointment(a.id, str(src), 'описание')
    assert (svc['storage'] / dto.file_path).exists() and dto.description == 'описание'
    with pytest.raises(PhotoFileError):
        svc['photo'].add_photo_to_appointment(a.id, str(svc['tmp'] / 'нет.jpg'))
    with pytest.raises(AppointmentNotFoundError):
        svc['photo'].add_photo_to_appointment(999, str(src))
    before = set(svc['storage'].rglob('*.jpg'))
    with pytest.raises(RuntimeError):
        with svc['db'].session_scope() as sess:
            svc['photo'].add_photo_to_appointment(a.id, str(src), session=sess)
            raise RuntimeError('сбой после копирования')
    assert set(svc['storage'].rglob('*.jpg')) == before           # копия убрана при откате


def test_dyn2_note_references_from_schema(svc):
    names = sorted(c.name for _, c in svc['note']._note_references())
    assert names == sorted(['comment_id', 'description_id', 'reason_id', 'procedure_id',
                            'recommendations_id', 'note_id', 'cost_procedure_id'])


def test_dyn2_note_referenced_by_unconfigured_model_kept(svc, monkeypatch):
    """Заметка защищена ссылкой из схемы, даже если конфиг про неё «не знает»."""
    import app.dependencies as deps
    monkeypatch.setattr(deps, '_NOTE_USAGE_MODELS', [], raising=False)   # реестр пуст
    p = _patient(svc)
    a = _appointment(svc, p.id, procedure_text='Чистка')
    svc['note'].cleanup_unused_note(a.procedure_id)
    assert svc['note'].get_note(a.procedure_id).text == 'Чистка'


def test_dyn3_generic_parent_check(svc):
    """Пациент со ссылкой на несуществующую заметку — ошибка (раньше проверки не было)."""
    from app.exceptions.exceptions_all import PatientValidationError
    with pytest.raises(PatientValidationError, match='appointments_notes'):
        svc['patient'].create(PatientDTO(first_name='И', last_name='П', comment_id=999,
                                         birth_date=datetime.date(1990, 1, 1)))


def test_dyn3_update_without_fk_change_skips_parent_queries(svc):
    p = _patient(svc)
    a = _appointment(svc, p.id)
    dto = svc['appointment'].get_by_id(a.id).model_copy(update={'date': datetime.date(2026, 2, 2)})
    calls = []
    real = svc['appointment']._validate_parents
    svc['appointment']._validate_parents = lambda d, s: calls.append(1) or real(d, s)
    svc['appointment'].update(dto)
    assert calls == []


def test_dyn4_counts_mechanism_works(svc):
    """DYN4: старый механизм 'counts' (дублирует sql_compute) работает — характеризующий тест."""
    p = _patient(svc)
    a = _appointment(svc, p.id)
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    svc['photo'].create(PhotoDTO(appointment_id=a.id, file_path=str(src)))
    svc['appointment']._field_configs = dict(svc['appointment']._field_configs,
                                             photo_count={'virtual': True, 'counts': 'photos'})
    items, _ = svc['appointment'].get_page(0, 10)
    with svc['db'].session_scope() as sess:
        obj = sess.get(Appointment, a.id)
        svc['appointment']._add_counts_to_items([obj], svc['appointment']._get_count_mappings(), sess)
        assert obj._count_photos == 1


def test_dyn5_order_by_note_text_and_sql_compute(svc):
    p = _patient(svc)
    a1 = _appointment(svc, p.id, procedure_text='Бэ')
    a2 = _appointment(svc, p.id, procedure_text='Аа')
    a3 = _appointment(svc, p.id, procedure_text='Вв')
    src = svc['tmp'] / 's.jpg'
    src.write_bytes(b'x')
    for _ in range(2):
        svc['photo'].create(PhotoDTO(appointment_id=a3.id, file_path=str(src)))
    by_note, _ = svc['appointment'].get_page(0, 10, order_by=['procedure_text'])
    assert [a.id for a in by_note] == [a2.id, a1.id, a3.id]
    by_photos, _ = svc['appointment'].get_page(0, 10, order_by=['-has_photos'])
    assert by_photos[0].id == a3.id


def test_dyn5_unknown_order_field_warns(svc):
    got = []
    handler = svc['patient'].logger.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    try:
        svc['patient'].get_page(0, 10, order_by=['фамилия_с_опечаткой'])
    finally:
        svc['patient'].logger.remove_output(handler)
    assert any(line.startswith('WARNING|') and 'фамилия_с_опечаткой' in line for line in got)


def test_dyn6_note_filter_escapes_wildcards(svc):
    p = _patient(svc)
    _appointment(svc, p.id, procedure_text='скидка 50%')
    _appointment(svc, p.id, procedure_text='скидка 500')
    found, total = svc['appointment'].get_page(
        0, 10, filters=[{'column': 'procedure_text', 'operator': 'ilike', 'value': '50%'}])
    assert total == 1 and found[0].procedure_text == 'скидка 50%'
