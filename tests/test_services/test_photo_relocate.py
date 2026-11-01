# tests/test_services/test_photo_relocate.py

"""
Перенос старых фото ``app_<N>/…`` прямо в папку фото (Ф1.6.7б шаг 3; решение владельца
2026-11-01: автоматически при запуске, перед началом — копия базы, полной копии папки нет).

Настоящая SQLite и папка фото во временной папке; старые строки и файлы создаются тестом.
"""

import datetime
import os

import pytest

from app.database.database import Database
from app.database.database_shema.clinic import Photo, PhotoFile
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.services.services_all import AppointmentService, NoteService, PatientService, PhotoService


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
    a1, a2 = (appointment.create(AppointmentDTO(patient_id=p.id, date=datetime.date(2026, 10, d)))
              for d in (1, 2))
    yield {'db': db, 'storage': storage, 'photo': photo, 'a1': a1.id, 'a2': a2.id,
           'dir': tmp_path}
    db.close()


def _legacy(svc, name, appointments, created=None, content=b'old'):
    """Старая строка файла, фото на неё и (если content) сам файл в app_<N>/."""
    if content is not None:
        path = svc['storage'] / name.replace('\\', '/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with svc['db'].session_scope() as session:
        session.add(PhotoFile(file_path=name, created_at=created))
        session.flush()
        for appointment_id in appointments:
            session.add(Photo(appointment_id=appointment_id, file_path=name))


def _photos(svc):
    with svc['db'].session_scope() as session:
        return sorted(p.file_path for p in session.query(Photo))


def _rows(svc):
    with svc['db'].session_scope() as session:
        return sorted(r.file_path for r in session.query(PhotoFile))


def _backups(svc):
    return [n for n in os.listdir(svc['dir']) if n.startswith('clinic.db.bak-') and n.endswith('-photos')]


def test_nothing_to_relocate_no_backup(svc):
    """Старых фото нет — ничего, даже копии базы."""
    assert svc['photo'].relocate_legacy_files() == {'moved': 0, 'missing': 0, 'unused': 0, 'failed': 0}
    assert _backups(svc) == []


def test_relocate_moves_file_links_and_cleans_old(svc):
    """Файл — в корень папки с именем по времени строки; обе ссылки переведены; старый файл,
    строка и опустевшая папка app_1 убраны; перед переносом — копия базы."""
    _legacy(svc, 'app_1\\a.JPG', [svc['a1'], svc['a2']], created=datetime.datetime(2025, 12, 31, 9, 0, 0))
    report = svc['photo'].relocate_legacy_files()
    assert report == {'moved': 1, 'missing': 0, 'unused': 0, 'failed': 0}
    assert _photos(svc) == ['20251231_090000.jpg', '20251231_090000.jpg']
    assert _rows(svc) == ['20251231_090000.jpg']
    assert sorted(os.listdir(svc['storage'])) == ['20251231_090000.jpg']
    assert (svc['storage'] / '20251231_090000.jpg').read_bytes() == b'old'
    assert len(_backups(svc)) == 1


def test_missing_old_file_left_as_is_without_backup(svc):
    """Старого файла нет на диске — строка и фото как есть, копии базы нет."""
    _legacy(svc, 'app_2/b.jpg', [svc['a1']], content=None)
    assert svc['photo'].relocate_legacy_files() == {'moved': 0, 'missing': 1, 'unused': 0, 'failed': 0}
    assert _photos(svc) == ['app_2/b.jpg'] and _backups(svc) == []


def test_unused_legacy_row_not_copied_every_start(svc):
    """Старая строка без ссылок не переносится (иначе копия плодилась бы при каждом запуске):
    файл и строка на месте до полной проверки по кнопке, копии базы нет."""
    _legacy(svc, 'app_5/u.jpg', [])
    for _ in range(2):
        assert svc['photo'].relocate_legacy_files() == {'moved': 0, 'missing': 0, 'unused': 1, 'failed': 0}
    assert sorted(os.listdir(svc['storage'])) == ['app_5'] and _rows(svc) == ['app_5/u.jpg']
    assert _backups(svc) == []


def test_relocate_in_batches(svc):
    """Пачками: все файлы перенесены, имена той же секунды — с номером."""
    stamp = datetime.datetime(2025, 1, 2, 3, 4, 5)
    for i in range(5):
        _legacy(svc, f'app_1/{i}.jpg', [svc['a1']], created=stamp)
    report = svc['photo'].relocate_legacy_files(batch=2)
    assert report == {'moved': 5, 'missing': 0, 'unused': 0, 'failed': 0}
    assert _rows(svc) == ['20250102_030405.jpg'] + [f'20250102_030405_{n}.jpg' for n in range(2, 6)]
    assert sorted(os.listdir(svc['storage'])) == _rows(svc)


def test_failed_batch_rolled_back_and_stops(svc, monkeypatch):
    """Ошибка во второй пачке — она откачена (новых копий нет, ссылки старые), первая
    сохранена, исключение наружу не выходит."""
    for i in range(4):
        _legacy(svc, f'app_1/{i}.jpg', [svc['a1']], created=datetime.datetime(2025, 1, 1, 0, 0, i))
    real = svc['photo']._store_new_file
    calls = []

    def flaky(source, session, added_at=None):
        calls.append(source)
        if len(calls) == 3:
            raise OSError('диск')
        return real(source, session, added_at=added_at)
    monkeypatch.setattr(svc['photo'], '_store_new_file', flaky)
    report = svc['photo'].relocate_legacy_files(batch=2)
    assert report == {'moved': 2, 'missing': 0, 'unused': 0, 'failed': 2}
    assert _photos(svc) == ['20250101_000000.jpg', '20250101_000001.jpg', 'app_1/2.jpg', 'app_1/3.jpg']
    assert sorted(os.listdir(svc['storage'])) == ['20250101_000000.jpg', '20250101_000001.jpg', 'app_1']
    assert sorted(os.listdir(svc['storage'] / 'app_1')) == ['2.jpg', '3.jpg']


def test_relocate_called_by_get_photo_service(monkeypatch):
    """При запуске: get_photo_service, собрав сервис, вызывает перенос (одна строка)."""
    import app.dependencies as deps
    calls = []
    monkeypatch.setattr(deps.PhotoService, 'relocate_legacy_files', lambda self: calls.append(self))
    deps.get_photo_service.cache_clear()
    try:
        service = deps.get_photo_service()
        assert calls == [service]
    finally:
        deps.get_photo_service.cache_clear()
