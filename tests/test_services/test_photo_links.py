# tests/test_services/test_photo_links.py

"""
Фото на ссылках (Ф1.6.7б шаг 2, Ф1.6.10г, Ф1.6.10д, ОСТ п. 5.10; решение владельца В-3).

Настоящая SQLite во временной папке (коммит, откат, внешние ключи, сборщик мусора) и папка
фото во временной папке — рабочие настройки и папка фото из настроек не читаются.

Проверяется: новый файл — прямо в папке фото, имя по времени добавления (та же секунда —
``_2``); относительный путь — ссылка на имеющийся файл; файл удаляется только когда на него
больше никто не ссылается (сборщик мусора + действие ``remove_photo_file`` после коммита);
откат — файл на месте; файл не удалился — предупреждение, коммит проходит; ошибка ОС при
копировании — исключение фото; путь хранилища — у объекта; сценарий В-3 через черновики.
"""

import datetime
import errno
import os
import re
from unittest.mock import MagicMock

import pytest

from app.database.database import Database
from app.database.database_shema.clinic import PhotoFile
from app.database.file_actions import PHOTOS_ROOT, photo_file_path, remove_photo_file
from app.database.table_events import EventContext, RowChange
from app.draft.integration import ServiceAdapter, build_app_schema, make_parent_resolver
from app.dto.dto_all import AppointmentDTO, AppointmentNoteDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.exceptions import PhotoStorageNoSpaceError, PhotoValidationError
from app.services import services_all
from app.services.services_all import AppointmentService, NoteService, PatientService, PhotoService
from app.utils.drafts import DraftStore, SaveScope, save_with_confirmation


NAME_RE = re.compile(r'^\d{8}_\d{6}(_\d+)?\.[a-z0-9]+$')   # ГГГГММДД_ЧЧММСС[_N].расш


@pytest.fixture
def svc(tmp_path):
    """Сервисы на файле SQLite и временной папке фото — как в app/dependencies.py."""
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    yield {'db': db, 'storage': storage, 'photo': photo, 'appointment': appointment,
           'patient': patient, 'note': note}
    db.close()


@pytest.fixture
def src(tmp_path):
    """Исходный снимок вне папки фото (расширение заглавными)."""
    path = tmp_path / 'scan' / 'IMG_1.JPG'
    path.parent.mkdir()
    path.write_bytes(b'\xff\xd8fake')
    return str(path)


def _appointments(svc, n=2):
    patient = svc['patient'].create(PatientDTO(first_name='Иван', last_name='Петров',
                                               birth_date=datetime.date(1980, 5, 5)))
    return [svc['appointment'].create(AppointmentDTO(patient_id=patient.id,
                                                     date=datetime.date(2026, 10, i + 1)))
            for i in range(n)]


def _files(svc):
    return sorted(os.listdir(svc['storage']))


def _rows(svc):
    with svc['db'].session_scope() as session:
        return sorted(r.file_path for r in session.query(PhotoFile))


# ---------------------------------------------------------------- новый файл, имя, ссылка

def test_new_file_in_root_named_by_time(svc, src):
    """Новый файл — прямо в папке фото (без app_N), имя — время, расширение строчными."""
    a1, _ = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    assert NAME_RE.match(photo.file_path) and photo.file_path.endswith('.jpg')
    assert _files(svc) == [photo.file_path]
    assert _rows(svc) == [photo.file_path]
    assert os.path.isfile(src)                                     # исходник не тронут


def test_same_second_gets_number_and_foreign_file_kept(svc, src, monkeypatch):
    """Р-27: та же секунда — _2, _3; чужой файл с тем же именем не перезаписывается."""
    class _Fixed(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 1, 15, 30, 0)
    monkeypatch.setattr(services_all, '_dt', _Fixed)
    a1, _ = _appointments(svc)
    (svc['storage'] / '20261101_153000.jpg').write_bytes(b'foreign')
    names = [svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src)).file_path
             for _ in range(2)]
    assert names == ['20261101_153000_2.jpg', '20261101_153000_3.jpg']
    assert (svc['storage'] / '20261101_153000.jpg').read_bytes() == b'foreign'


def test_relative_path_links_existing_file(svc, src):
    """Относительный путь в create — ссылка на имеющийся файл: копии нет, строка одна."""
    a1, a2 = _appointments(svc)
    first = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    second = svc['photo'].create(PhotoDTO(appointment_id=a2.id, file_path=first.file_path))
    assert second.file_path == first.file_path
    assert _files(svc) == [first.file_path] and _rows(svc) == [first.file_path]


def test_relative_path_without_file_row_rejected(svc):
    """Ссылка на файл, которого нет в таблице файлов, — ошибка проверки, фото не пишется."""
    a1, _ = _appointments(svc)
    with pytest.raises(PhotoValidationError):
        svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path='20990101_000000.jpg'))
    assert svc['photo'].get_all() == []


# ---------------------------------------------------------------- удаление по ссылкам

def test_shared_file_removed_only_with_last_link(svc, src):
    """В-3: файл общий — удаление одного фото файл не трогает, последнего — удаляет."""
    a1, a2 = _appointments(svc)
    first = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    second = svc['photo'].create(PhotoDTO(appointment_id=a2.id, file_path=first.file_path))
    svc['photo'].delete(first.id)
    assert _files(svc) == [first.file_path] and _rows(svc) == [first.file_path]
    svc['photo'].delete(second.id)
    assert _files(svc) == [] and _rows(svc) == []


def test_rollback_keeps_file(svc, src):
    """Откат транзакции удаления — фото, строка файла и файл на месте."""
    a1, _ = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    with pytest.raises(RuntimeError):
        with svc['db'].session_scope() as session:
            svc['photo'].delete(photo.id, session=session)
            raise RuntimeError('отмена')
    assert svc['photo'].get_by_id(photo.id).file_path == photo.file_path
    assert _files(svc) == [photo.file_path] and _rows(svc) == [photo.file_path]


def test_rollback_of_new_photo_removes_copy(svc, src):
    """Откат создания — копия удалена, строки нет."""
    a1, _ = _appointments(svc)
    with pytest.raises(RuntimeError):
        with svc['db'].session_scope() as session:
            svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src), session=session)
            raise RuntimeError('отмена')
    assert _files(svc) == [] and _rows(svc) == []


def test_delete_failure_warns_and_keeps_file(svc, src, monkeypatch):
    """FD10 / Р-5: файл не удалился — коммит прошёл, файл остаётся, предупреждение."""
    a1, _ = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    import app.database.file_actions as fa
    log = MagicMock()
    monkeypatch.setattr(fa, '_logger', lambda: log)
    monkeypatch.setattr(fa, 'delete_file_safely', lambda path, logger=None: (False, 'занят'))
    svc['photo'].delete(photo.id)
    assert svc['photo'].get_all() == [] and _rows(svc) == []
    assert _files(svc) == [photo.file_path]
    assert any('остаётся' in c.args[0] for c in log.warning.call_args_list)


def test_update_to_new_file_frees_old(svc, src, tmp_path):
    """Замена файла фото: прежний файл без ссылок удаляется после коммита."""
    a1, _ = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    other = tmp_path / 'scan' / 'b.png'
    other.write_bytes(b'png')
    changed = svc['photo'].update(photo.model_copy(update={'file_path': str(other)}))
    assert changed.file_path != photo.file_path and changed.file_path.endswith('.png')
    assert _files(svc) == [changed.file_path] and _rows(svc) == [changed.file_path]


def test_update_keeps_old_file_if_shared(svc, src, tmp_path):
    """Замена файла у одного из двух фото с общим файлом — общий файл остаётся."""
    a1, a2 = _appointments(svc)
    first = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    svc['photo'].create(PhotoDTO(appointment_id=a2.id, file_path=first.file_path))
    other = tmp_path / 'scan' / 'b.png'
    other.write_bytes(b'png')
    changed = svc['photo'].update(first.model_copy(update={'file_path': str(other)}))
    assert _files(svc) == sorted([first.file_path, changed.file_path])


def test_appointment_delete_removes_unshared_file(svc, src):
    """Удаление приёма (каскад к фото) — файл без ссылок удаляется."""
    a1, _ = _appointments(svc)
    svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    svc['appointment'].delete(a1.id)
    assert _files(svc) == [] and _rows(svc) == []


def test_move_photo_keeps_file(svc, src):
    """Перенос фото в другой приём — меняется только ссылка, файл на месте."""
    a1, a2 = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    svc['photo'].update(photo.model_copy(update={'appointment_id': a2.id}))
    assert svc['photo'].get_by_id(photo.id).appointment_id == a2.id
    assert _files(svc) == [photo.file_path]


# ---------------------------------------------------------------- Ф1.6.10д, ОСТ 5.10

def test_copy_os_error_is_photo_error(svc, src, monkeypatch):
    """Ф1.6.10д: нет места при копировании — PhotoStorageNoSpaceError, копии и строки нет."""
    a1, _ = _appointments(svc)

    def no_space(fsrc, fdst, *args):
        fdst.write(b'part')
        raise OSError(errno.ENOSPC, 'No space left on device')
    monkeypatch.setattr(services_all.shutil, 'copyfileobj', no_space)
    with pytest.raises(PhotoStorageNoSpaceError) as info:
        svc['photo'].add_photo_to_appointment(a1.id, src)
    assert isinstance(info.value.original, OSError)
    assert _files(svc) == [] and _rows(svc) == []


def test_storage_path_per_object(svc, tmp_path):
    """ОСТ п. 5.10: папка — у объекта; второй сервис не меняет первую."""
    other = PhotoService(svc['db'], str(tmp_path / 'other'), field_configs=PHOTO_CONFIG)
    assert svc['photo']._storage_path == str(svc['storage'])
    assert other._storage_path == str(tmp_path / 'other')


def test_storage_path_published_to_database(svc, tmp_path):
    """Папка фото — ресурс базы для действия после коммита; смена папки — тоже."""
    events = svc['db'].table_events
    assert events.resources[PHOTOS_ROOT] == os.path.abspath(svc['storage'])
    svc['photo']._storage_path = str(tmp_path / 'new')
    assert events.resources[PHOTOS_ROOT] == os.path.abspath(tmp_path / 'new')


# ---------------------------------------------------------------- действие remove_photo_file

def _ctx(changes, root):
    return EventContext(event='after_commit', table='photo_files', table_def=None,
                        session=None, changes=tuple(changes),
                        resources={PHOTOS_ROOT: root} if root else {})


def test_action_deletes_only_finally_deleted(tmp_path):
    """Удалили и добавили снова — файл нужен; добавили и удалили — нет."""
    for name in ('a.jpg', 'b.jpg'):
        (tmp_path / name).write_bytes(b'x')
    remove_photo_file(_ctx([
        RowChange('photo_files', 'delete', 'a.jpg'), RowChange('photo_files', 'insert', 'a.jpg'),
        RowChange('photo_files', 'insert', 'b.jpg'), RowChange('photo_files', 'delete', 'b.jpg'),
    ], str(tmp_path)))
    assert sorted(os.listdir(tmp_path)) == ['a.jpg']


def test_action_removes_empty_legacy_folder(tmp_path):
    """Старый путь Windows (app_1\\x.jpg, Р-29): файл и опустевшая папка app_1 удаляются."""
    (tmp_path / 'app_1').mkdir()
    (tmp_path / 'app_1' / 'x.jpg').write_bytes(b'x')
    remove_photo_file(_ctx([RowChange('photo_files', 'delete', 'app_1\\x.jpg')], str(tmp_path)))
    assert os.listdir(tmp_path) == []


def test_action_without_root_keeps_files(tmp_path, monkeypatch):
    """Папки фото нет в ресурсах — ничего не удаляется, предупреждение."""
    import app.database.file_actions as fa
    log = MagicMock()
    monkeypatch.setattr(fa, '_logger', lambda: log)
    (tmp_path / 'a.jpg').write_bytes(b'x')
    remove_photo_file(_ctx([RowChange('photo_files', 'delete', 'a.jpg')], None))
    assert os.listdir(tmp_path) == ['a.jpg']
    assert 'Папка фото не задана' in log.warning.call_args.args[0]


@pytest.mark.parametrize('name', ['../clinic.db', '/etc/passwd', 'C:/x.jpg', '', '.'])
def test_photo_file_path_stays_inside_root(tmp_path, name):
    """Имя, ведущее вне папки фото (или сама папка), не трогается."""
    assert photo_file_path(str(tmp_path), name) is None


# ---------------------------------------------------------------- через черновики (В-3)

@pytest.fixture
def drafts(svc):
    adapter = ServiceAdapter({
        'patient': (lambda: svc['patient'], PatientDTO),
        'appointment': (lambda: svc['appointment'], AppointmentDTO),
        'photo': (lambda: svc['photo'], PhotoDTO),
        'note': (lambda: svc['note'], AppointmentNoteDTO),
    })
    schema = build_app_schema()
    store = DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter))

    def save(targets=None, scope=None):
        return save_with_confirmation(store, adapter, targets, scope,
                                      lambda plan: True, lambda plan: True)
    return store, save


def test_drafts_new_photo_saved_into_root(svc, drafts, src):
    """Новое фото из черновика — файл по времени в папке фото."""
    store, save = drafts
    a1, _ = _appointments(svc)
    store.create('photo', {'file_path': src}, parent_id=a1.id)
    save()
    [photo] = svc['photo'].get_all()
    assert NAME_RE.match(photo.file_path) and _files(svc) == [photo.file_path]


def test_drafts_moved_to_deleted_new_appointment_keeps_file(svc, drafts, src):
    """В-3: фото перенесли из приёма 1 в новый приём 2, приём 2 удалили и сохранили только
    его — фото у приёма 1 (черновики поглощают перенос, ОСТ п. 5.6), файл на месте."""
    store, save = drafts
    a1, _ = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    a2 = store.create('appointment', {'date': datetime.date(2026, 10, 9)}, parent_id=a1.patient_id)
    store.modify('photo', photo.id, {'appointment_id': a2},
                 original={'appointment_id': a1.id}, parent_id=a1.id)
    store.delete('appointment', a2)
    save([('appointment', a2)], SaveScope.SELF)
    assert svc['photo'].get_by_id(photo.id).appointment_id == a1.id
    assert _files(svc) == [photo.file_path]


def test_drafts_delete_one_of_shared_then_other(svc, drafts, src):
    """Через черновики: удалили одно из двух фото с общим файлом — файл остаётся;
    удалили второе (отдельное сохранение) — файл удалён."""
    store, save = drafts
    a1, a2 = _appointments(svc)
    first = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    second = svc['photo'].create(PhotoDTO(appointment_id=a2.id, file_path=first.file_path))
    store.delete('photo', first.id, parent_id=a1.id)
    store.delete('photo', second.id, parent_id=a2.id)
    save([('appointment', a1.id)], SaveScope.BRANCH)
    assert [p.id for p in svc['photo'].get_all()] == [second.id]
    assert _files(svc) == [first.file_path]
    save([('appointment', a2.id)], SaveScope.BRANCH)
    assert svc['photo'].get_all() == [] and _files(svc) == []


def test_drafts_failed_save_keeps_everything(svc, drafts, src, monkeypatch):
    """Сбой сохранения черновиков — откат: фото и файл на месте, новая копия убрана."""
    store, save = drafts
    a1, _ = _appointments(svc)
    photo = svc['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=src))
    store.delete('photo', photo.id, parent_id=a1.id)
    store.create('photo', {'file_path': src}, parent_id=a1.id)
    real_create = svc['photo'].create

    def boom(dto, session=None):
        real_create(dto, session=session)
        raise RuntimeError('сбой')
    monkeypatch.setattr(svc['photo'], 'create', boom)
    with pytest.raises(RuntimeError):
        save()
    assert [p.id for p in svc['photo'].get_all()] == [photo.id]
    assert _files(svc) == [photo.file_path] and _rows(svc) == [photo.file_path]
