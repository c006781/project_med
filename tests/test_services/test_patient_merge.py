# tests/test_services/test_patient_merge.py

"""
Объединение пациентов-дублей (app/services/patient_merge.py, Ф1.6.10а) — на НАСТОЯЩЕЙ
SQLite во временной папке (коммит, откат, резервная копия, файлы фото).
"""

import datetime
import os

import pytest

from app.database import Database
from app.database.database_shema.clinic import Photo
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.exceptions.exceptions_all import PatientNotFoundError, PatientValidationError
from app.services import AppointmentService, NoteService, PatientService, PhotoService
from app.services.patient_merge import (
    MergePlanChangedError,
    MergeRules,
    PatientMergeService,
    join_texts,
)

D85 = datetime.date(1985, 6, 14)


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
    merge = PatientMergeService(db, patient, appointment)
    yield {'db': db, 'patient': patient, 'appointment': appointment, 'merge': merge,
           'storage': storage, 'tmp': tmp_path}
    db.close()


def _patient(svc, last='Иванова', first='Мария', middle='Петровна', birth=D85, **fields):
    return svc['patient'].create(PatientDTO(last_name=last, first_name=first, middle_name=middle,
                                            birth_date=birth, **fields))


def _appointment(svc, patient_id, day=1, **fields):
    return svc['appointment'].create(AppointmentDTO(patient_id=patient_id,
                                                    date=datetime.date(2026, 3, day), **fields))


def _photo(svc, appointment_id, name):
    """Фото приёма: файл в хранилище и строка (как после добавления)."""
    path = svc['storage'] / name
    path.write_bytes(b'img-' + name.encode())
    with svc['db'].session_scope() as s:
        row = Photo(appointment_id=appointment_id, file_path=name)
        s.add(row)
        s.flush()
        return row.id


def _photos_of(svc, appointment_id):
    with svc['db'].session_scope() as s:
        return sorted(p.id for p in s.query(Photo).filter(Photo.appointment_id == appointment_id))


# --- поиск -----------------------------------------------------------------

def test_find_groups_by_fio_and_full_birth_date(svc):
    a = _patient(svc)
    b = _patient(svc, last='ИВАНОВА', middle='петровна ')               # регистр, пробел
    c = _patient(svc, last='Ёжикова', first='Анна', middle=None)
    d = _patient(svc, last='Ежикова', first='анна', middle='')          # «ё», пустое отчество
    _patient(svc, birth=datetime.date(1985, 1, 1))                      # тот же год — другой пациент
    groups = [[p.id for p in g] for g in svc['merge'].find_possible_duplicates()]
    assert groups == [[c.id, d.id], [a.id, b.id]]


# --- план ------------------------------------------------------------------

def test_plan_moves_appointments_and_skips_repeated(svc):
    main = _patient(svc)
    dup = _patient(svc)
    keep = _appointment(svc, main.id, day=1, reason_text='боль')
    repeat = _appointment(svc, dup.id, day=1, reason_text=' боль ')     # та же дата и тексты
    new = _appointment(svc, dup.id, day=2, reason_text='осмотр')
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert [m.appointment_id for m in plan.moved] == [new.id]
    assert [(s.appointment_id, s.twin_id) for s in plan.skipped] == [(repeat.id, keep.id)]
    assert any('не переносится' in w for w in plan.warnings)
    # план ничего не меняет
    assert len(svc['appointment'].get_appointments_by_patient(dup.id)) == 2


def test_plan_repeated_between_two_duplicates(svc):
    main = _patient(svc)
    d1, d2 = _patient(svc), _patient(svc)
    first = _appointment(svc, d1.id, day=5, procedure_text='чистка')
    second = _appointment(svc, d2.id, day=5, procedure_text='чистка')
    plan = svc['merge'].plan_merge(main.id, [d1.id, d2.id])
    assert [m.appointment_id for m in plan.moved] == [first.id]
    assert [(s.appointment_id, s.twin_id) for s in plan.skipped] == [(second.id, first.id)]


def test_plan_fills_empty_fields_and_warns_on_differences(svc):
    main = _patient(svc, middle=None, phone='+7 (999) 111-22-33')
    dup = _patient(svc, middle='Петровна', phone='+7 (999) 000-00-00')
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert [(c.field, c.value) for c in plan.changes] == [('middle_name', 'Петровна')]
    assert any(w.startswith('Телефон:') and 'остаётся значение главного' in w for w in plan.warnings)
    # отчество было пустым у главного — ключи разные, предупреждение
    assert any('не совпадают с главным' in w for w in plan.warnings)


def test_join_texts():
    assert join_texts(['аллергия', ' аллергия ', 'аллергия, астма', '', None, 'гипертония']) == \
        'аллергия, астма\nгипертония'
    assert join_texts([None, 'текст']) == 'текст'


# --- объединение -----------------------------------------------------------

def test_merge_moves_photos_keeps_files_and_deletes_duplicate(svc):
    main = _patient(svc, description_text='аллергия')
    dup = _patient(svc, description_text='астма', comment_text='звонить вечером')
    keep = _appointment(svc, main.id, day=1, reason_text='боль')
    repeat = _appointment(svc, dup.id, day=1, reason_text='боль')
    new = _appointment(svc, dup.id, day=2, reason_text='осмотр')
    p_repeat = _photo(svc, repeat.id, 'r.jpg')
    p_new = _photo(svc, new.id, 'n.jpg')

    result = svc['merge'].merge_patients(main.id, [dup.id])

    assert result.backup_path and os.path.exists(result.backup_path)
    assert {a.id for a in svc['appointment'].get_appointments_by_patient(main.id)} == {keep.id, new.id}
    assert _photos_of(svc, keep.id) == [p_repeat]                       # фото повторного — к двойнику
    assert _photos_of(svc, new.id) == [p_new]
    assert (svc['storage'] / 'r.jpg').exists() and (svc['storage'] / 'n.jpg').exists()
    with pytest.raises(PatientNotFoundError):
        svc['patient'].get_by_id(dup.id)
    stored = svc['patient'].get_by_id(main.id)
    assert stored.description_text == 'аллергия\nастма'
    assert stored.comment_text == 'звонить вечером'


def test_merge_rolls_back_on_error(svc, monkeypatch):
    main = _patient(svc)
    dup = _patient(svc)
    new = _appointment(svc, dup.id, day=2)
    merge = svc['merge']

    def _fail(*args, **kwargs):
        raise RuntimeError('сбой посреди объединения')

    monkeypatch.setattr(svc['patient'], 'delete_patient', _fail)
    with pytest.raises(RuntimeError):
        merge.merge_patients(main.id, [dup.id], backup=False)
    assert [a.id for a in svc['appointment'].get_appointments_by_patient(dup.id)] == [new.id]
    assert svc['patient'].get_by_id(dup.id).id == dup.id


def test_merge_refuses_changed_plan(svc):
    main = _patient(svc)
    dup = _patient(svc)
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    _appointment(svc, dup.id, day=3)                                   # данные изменились
    with pytest.raises(MergePlanChangedError):
        svc['merge'].merge_patients(main.id, [dup.id], expected=plan, backup=False)
    assert svc['patient'].get_by_id(dup.id).id == dup.id


def test_merge_with_confirmed_plan(svc):
    main = _patient(svc)
    dup = _patient(svc)
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert svc['merge'].merge_patients(main.id, [dup.id], expected=plan, backup=False).plan == plan


@pytest.mark.parametrize('dups', [[], [1], [2, 2]])
def test_merge_rejects_bad_ids(svc, dups):
    with pytest.raises(PatientValidationError):
        svc['merge'].plan_merge(1, dups)


def test_rules_can_disable_photo_move(svc):
    main = _patient(svc)
    dup = _patient(svc)
    _appointment(svc, main.id, day=1)
    repeat = _appointment(svc, dup.id, day=1)
    _photo(svc, repeat.id, 'r.jpg')
    merge = PatientMergeService(svc['db'], svc['patient'], svc['appointment'],
                                rules=MergeRules(move_photos_of_repeated=False))
    plan = merge.plan_merge(main.id, [dup.id])
    assert plan.skipped[0].photo_ids == () and any('удаляются' in w for w in plan.warnings)


def test_log_has_no_personal_data(svc):
    from tests.test_services.test_services_check import _log_lines
    main = _patient(svc, last='Секретова')
    dup = _patient(svc, last='Секретова')
    lines = []
    lines += _log_lines(
        svc['patient'],
        lambda: lines.extend(_log_lines(
            svc['merge'],
            lambda: svc['merge'].merge_patients(main.id, [dup.id], backup=False),
        )),
    )
    text = '\n'.join(lines)
    assert 'Объединены пациенты' in text and 'Секретова' not in text


def test_dependencies_provider_builds_service(monkeypatch):
    """get_patient_merge_service собирается из текущих сервисов и не входит в реестр перезагрузки."""
    import app.dependencies as deps
    sentinel = {'db': object(), 'patient': object(), 'appointment': object()}
    monkeypatch.setattr(deps, 'get_db', lambda: sentinel['db'])
    monkeypatch.setattr(deps, 'get_patient_service', lambda: sentinel['patient'])
    monkeypatch.setattr(deps, 'get_appointment_service', lambda: sentinel['appointment'])
    service = deps.get_patient_merge_service()
    assert (service._db, service._patients, service._appointments) == \
        (sentinel['db'], sentinel['patient'], sentinel['appointment'])
    assert deps.get_patient_merge_service not in deps._SERVICE_PROVIDERS


def test_merge_without_birth_date(svc):
    """ТД-14: дата рождения необязательна — пациенты без неё ищутся как дубли и объединяются."""
    main = _patient(svc, birth=None, middle=None)
    dup = _patient(svc, birth=None, middle=None, phone='+7 (999) 111-22-33')
    groups = [[p.id for p in g] for g in svc['merge'].find_possible_duplicates()]
    assert groups == [[main.id, dup.id]]
    svc['merge'].merge_patients(main.id, [dup.id], backup=False)
    assert svc['patient'].get_by_id(main.id).phone == '+7 (999) 111-22-33'
