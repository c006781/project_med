# tests/test_services/test_photo_storage_check.py

"""
Сверка папки фото со строками файлов (Ф1.6.7б шаг 4, Ф1.6.10г; кнопка — М19, Ф2.2.6).

Трогаются только имена нашего вида и папки ``app_*`` (Р-28); свежие файлы (моложе порога)
не трогаются; сначала список (``check_storage``), потом удаление подтверждённого
(``clean_storage``), с повторной проверкой. Папка фото и база — во временной папке.
"""

import datetime
import os
import time

import pytest

from app.database.database import Database
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.services.services_all import AppointmentService, NoteService, PatientService, PhotoService


OLD = time.time() - 3600   # «старый» файл — час назад


@pytest.fixture
def svc(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    p = patient.create(PatientDTO(first_name='Иван', last_name='Петров',
                                  birth_date=datetime.date(1980, 5, 5)))
    a = appointment.create(AppointmentDTO(patient_id=p.id, date=datetime.date(2026, 10, 1)))
    src = tmp_path / 'scan.jpg'
    src.write_bytes(b'img')
    linked = photo.create(PhotoDTO(appointment_id=a.id, file_path=str(src))).file_path
    os.utime(storage / linked, (OLD, OLD))
    yield {'db': db, 'storage': storage, 'photo': photo, 'linked': linked}
    db.close()


def _put(storage, name, old=True):
    path = storage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x')
    if old:
        os.utime(path, (OLD, OLD))
    return path


def test_check_lists_only_ours_and_legacy(svc):
    """Наш вид без строки и файлы в app_* — к удалению; чужие файлы и папки не смотрятся;
    привязанный файл — нет."""
    s = svc['storage']
    _put(s, '20250101_000000.jpg')
    _put(s, 'app_3/old.jpg')
    _put(s, 'readme.txt')
    _put(s, 'other/20250101_000001.jpg')
    (s / 'app_4').mkdir()
    report = svc['photo'].check_storage()
    assert report == {'extra': ['20250101_000000.jpg', 'app_3/old.jpg'], 'fresh': [],
                      'empty_dirs': ['app_4'], 'missing': []}


def test_fresh_files_not_offered(svc):
    """Р-28: файл моложе 10 минут — в fresh, не к удалению; clean его не трогает."""
    path = _put(svc['storage'], '20250101_000000.jpg', old=False)
    report = svc['photo'].check_storage()
    assert report['extra'] == [] and report['fresh'] == ['20250101_000000.jpg']
    result = svc['photo'].clean_storage({'extra': ['20250101_000000.jpg']})
    assert result == {'deleted': [], 'kept': ['20250101_000000.jpg']} and path.exists()


def test_missing_file_reported(svc):
    """Строка файла без файла на диске — в missing (удалять нечего)."""
    os.remove(svc['storage'] / svc['linked'])
    assert svc['photo'].check_storage()['missing'] == [svc['linked']]


def test_clean_deletes_confirmed_and_empty_legacy_dirs(svc):
    """Удаляется подтверждённое; опустевшая после этого app_* — тоже; привязанный файл и
    чужие — на месте."""
    s = svc['storage']
    _put(s, '20250101_000000.jpg')
    _put(s, 'app_3/old.jpg')
    _put(s, 'readme.txt')
    result = svc['photo'].clean_storage(svc['photo'].check_storage())
    assert sorted(result['deleted']) == ['20250101_000000.jpg', 'app_3', 'app_3/old.jpg']
    assert result['kept'] == []
    assert sorted(os.listdir(s)) == sorted([svc['linked'], 'readme.txt'])


def test_clean_rechecks_linked_since_listing(svc):
    """Файл привязали за время показа списка — не удаляется."""
    report = {'extra': [svc['linked']], 'empty_dirs': []}
    assert svc['photo'].clean_storage(report) == {'deleted': [], 'kept': [svc['linked']]}
    assert (svc['storage'] / svc['linked']).exists()


def test_clean_ignores_names_outside_scope(svc):
    """Имя не из сверки (чужой файл, выход из папки) — не удаляется."""
    _put(svc['storage'], 'readme.txt')
    result = svc['photo'].clean_storage({'extra': ['readme.txt', '../clinic.db'],
                                         'empty_dirs': ['other']})
    assert result['deleted'] == [] and (svc['storage'] / 'readme.txt').exists()
