# tests/test_settings_page/test_settings_page_cleanup.py
"""
Кнопки уборки на экране настроек: сначала список, потом подтверждение, потом удаление.

База и папка фото — временные, сервисы настоящие; главного окна нет. Подмена — только у
функций ``get_db`` / ``get_photo_service``, которые в программе отдают общие объекты.
"""
import datetime
import os
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit

from app.database.database import Database
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.services.services_all import AppointmentService, NoteService, PatientService, PhotoService
from interfaces.gui.gui_window.pages import settings_page as sp


@pytest.fixture
def world(tmp_path, page, monkeypatch):
    """Временная база с пациентом, приёмом и одним фото; страница смотрит на них."""
    db_path = tmp_path / 'clinic.db'
    storage = tmp_path / 'photos'
    db = Database(f'sqlite:///{db_path}')
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo, field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    person = patient.create(
        PatientDTO(
            first_name  =   'Иван',
            last_name   =   'Петров',
            birth_date  =   datetime.date(1980, 1, 1),
        ),
    )
    visit = appointment.create(
        AppointmentDTO(
            patient_id  =   person.id,
            date        =   datetime.date(2026, 10, 1),
        ),
    )
    source = tmp_path / 'scan.jpg'
    source.write_bytes(b'img')
    linked = photo.create(
        PhotoDTO(
            appointment_id  =   visit.id,
            file_path       =   str(source),
        ),
    ).file_path
    monkeypatch.setattr(sp, 'get_photo_service', lambda: photo)
    monkeypatch.setattr(sp, 'get_db', lambda: db)
    page.config_manager['database_local_path'] = str(db_path)
    page.config_manager['PHOTOS_STORAGE_PATH'] = str(storage)
    page._load_settings()
    yield SimpleNamespace(db=db, photo=photo, storage=storage, linked=linked, note=note, visit=visit)
    db.close()


# файл в папке фото старше порога свежести
def _orphan(
    storage,        # папка фото
    name : str,     # имя файла
):
    """Создаёт в папке фото старый файл, на который никто не ссылается."""
    path = storage / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x')
    past = datetime.datetime.now().timestamp() - 3600
    os.utime(path, (past, past))
    return path


@pytest.fixture
def dialogs(monkeypatch):
    """Подменяет окно подтверждения: запоминает показанное, отвечает значением ``answer``."""
    shown = SimpleNamespace(calls=[], answer=True)

    def confirm(parent, title, intro, lines):
        shown.calls.append((title, intro, list(lines)))
        return shown.answer

    monkeypatch.setattr(sp, 'confirm_cleanup', confirm)
    return shown


def test_clean_photos_lists_then_deletes(world, page, dialogs, messages):
    """Файл без ссылок: сначала список с базой и папкой, после подтверждения удалён; файл с ссылкой цел."""
    orphan = _orphan(world.storage, '20250101_000000.jpg')
    page._on_clean_photos_clicked()
    assert len(dialogs.calls) == 1
    title, intro, lines = dialogs.calls[0]
    assert lines == ['20250101_000000.jpg']
    assert 'файлов без ссылок: 1' in intro
    assert str(world.storage) in intro
    assert not orphan.exists()
    assert (world.storage / world.linked).exists()
    assert messages == [('information', "Очистка фото", "Удалено: 1.")]


def test_clean_photos_cancel_deletes_nothing(world, page, dialogs, messages):
    """Отказ в подтверждении: ничего не удалено, сообщений нет."""
    orphan = _orphan(world.storage, '20250101_000000.jpg')
    dialogs.answer = False
    page._on_clean_photos_clicked()
    assert orphan.exists()
    assert messages == []


def test_clean_photos_nothing_to_delete(world, page, dialogs, messages):
    """Нечего удалять: окна подтверждения нет, только сообщение."""
    page._on_clean_photos_clicked()
    assert dialogs.calls == []
    assert messages == [('information', "Очистка фото", "Файлов без ссылок нет.")]


def test_clean_photos_notes_fresh_and_missing(world, page, dialogs, messages):
    """Свежий файл не предлагается; фото без файла — пояснение; удалять нечего."""
    (world.storage / '20260101_000000.jpg').write_bytes(b'x')
    os.remove(world.storage / world.linked)
    page._on_clean_photos_clicked()
    assert dialogs.calls == []
    text = messages[0][2]
    assert 'моложе 10 минут: 1' in text
    assert 'без файла на диске: 1' in text
    assert (world.storage / '20260101_000000.jpg').exists()


def test_clean_photos_empty_legacy_folder_listed(world, page, dialogs, messages):
    """Пустая папка старого хранения — в списке с пометкой."""
    (world.storage / 'app_3').mkdir()
    page._on_clean_photos_clicked()
    assert dialogs.calls[0][2] == ['app_3 (пустая папка)']
    assert not (world.storage / 'app_3').exists()


def test_clean_photos_file_linked_while_list_shown_is_kept(world, page, dialogs, messages, monkeypatch):
    """Файл привязали, пока показывали список: не удаляется, итог — предупреждение."""
    orphan = _orphan(world.storage, '20250101_000000.jpg')
    real_check = world.photo.check_storage
    calls = []

    def check(min_age=None):
        calls.append(min_age)
        report = real_check(min_age)
        if len(calls) > 1:      # повторная проверка в clean_storage
            report['extra'] = []
        return report

    monkeypatch.setattr(world.photo, 'check_storage', check)
    page._on_clean_photos_clicked()
    assert orphan.exists()
    kind, _title, text = messages[0]
    assert kind == 'warning'
    assert 'Удалено: 0.' in text
    assert '20250101_000000.jpg' in text


@pytest.mark.parametrize('method, title', [
    ('check_storage', "Не удалось проверить папку фото"),
    ('clean_storage', "Не удалось очистить папку фото"),
])
def test_clean_photos_error_reaches_message(world, page, dialogs, messages, monkeypatch, method, title):
    """Ошибка сервиса: сообщение пользователю, исключение не уходит в цикл событий Qt."""
    _orphan(world.storage, '20250101_000000.jpg')

    def fail(*args, **kwargs):
        raise OSError('диск недоступен')

    monkeypatch.setattr(world.photo, method, fail)
    page._on_clean_photos_clicked()
    assert messages[0][0] == 'critical'
    assert title in messages[0][2]
    assert 'диск недоступен' in messages[0][2]


# --- когда уборка запрещена ---------------------------------------------------------------

def test_cleanup_blocked_without_database_file(world, page, dialogs, messages, monkeypatch):
    """Нет файла базы: сервисы не вызываются (открылась бы пустая база, и все фото стали бы «без ссылок»)."""
    called = []
    monkeypatch.setattr(sp, 'get_photo_service', lambda: called.append(1))
    page.db_path_edit.setText(str(world.storage / 'нет.db'))
    for handler in (page._on_clean_photos_clicked, page._on_clean_rows_clicked):
        handler()
    assert called == []
    assert dialogs.calls == []
    assert [kind for kind, _title, _text in messages] == ['warning', 'warning']


@pytest.mark.parametrize('field', ['photos_path_edit', 'db_path_edit'])
def test_cleanup_blocked_with_unsaved_paths(world, page, dialogs, messages, tmp_path, field):
    """Путь в форме не сохранён: сверка шла бы по другому пути, чем видит пользователь."""
    other = tmp_path / 'другая.db'
    other.write_bytes(b'')
    getattr(page, field).setText(str(other))
    page._on_clean_photos_clicked()
    assert dialogs.calls == []
    assert 'сначала сохраните' in messages[0][2]


def test_cleanup_blocked_with_drafts(world, page, dialogs, messages):
    """Есть несохранённые черновики: уборка не запускается."""
    page.main_window = SimpleNamespace(drafts=SimpleNamespace(store=SimpleNamespace(is_empty=False)))
    page._on_clean_rows_clicked()
    assert dialogs.calls == []
    assert 'черновики' in messages[0][2]


def test_cleanup_allowed_with_empty_drafts(world, page):
    """Черновики пусты и пути сохранены: можно."""
    page.main_window = SimpleNamespace(drafts=SimpleNamespace(store=SimpleNamespace(is_empty=True)))
    assert page._cleanup_blocked_reason() is None


# --- записи без ссылок --------------------------------------------------------------------

# заметка, на которую никто не ссылается
def _unused_note(
    world,  # база теста
) -> int:
    """Добавляет заметку без ссылок и возвращает её id."""
    from app.database.database_shema.clinic import AppointmentNote

    with world.db.session_scope() as session:
        row = AppointmentNote(text='ничья')
        session.add(row)
        session.flush()
        return row.id


# строки таблицы заметок
def _note_ids(
    world,  # база теста
) -> list:
    """Возвращает id всех заметок."""
    from app.database.database_shema.clinic import AppointmentNote

    with world.db.session_scope() as session:
        return [row.id for row in session.query(AppointmentNote).all()]


def test_clean_rows_lists_then_deletes(world, page, dialogs, messages):
    """Заметка без ссылок: в списке — заголовок таблицы и id, после подтверждения удалена."""
    note_id = _unused_note(world)
    page._on_clean_rows_clicked()
    _title, intro, lines = dialogs.calls[0]
    assert 'записей без ссылок: 1' in intro
    assert lines == [f"Заметки: {note_id}"]
    assert note_id not in _note_ids(world)
    assert messages == [('information', "Очистка записей", "Удалено: 1.")]


def test_clean_rows_cancel_deletes_nothing(world, page, dialogs, messages):
    """Отказ: запись на месте."""
    note_id = _unused_note(world)
    dialogs.answer = False
    page._on_clean_rows_clicked()
    assert note_id in _note_ids(world)
    assert messages == []


def test_clean_rows_nothing_to_delete(world, page, dialogs, messages):
    """Нечего удалять: только сообщение."""
    page._on_clean_rows_clicked()
    assert dialogs.calls == []
    assert messages == [('information', "Очистка записей", "Записей без ссылок нет.")]


def test_clean_rows_photo_file_row_removes_file(world, page, dialogs, messages):
    """Строка файла без ссылок удаляется вместе с файлом (после коммита)."""
    from app.database.database_shema.clinic import PhotoFile

    orphan = _orphan(world.storage, '20250101_000000.jpg')
    with world.db.session_scope() as session:
        session.add(PhotoFile(file_path='20250101_000000.jpg'))
    page._on_clean_rows_clicked()
    assert any('20250101_000000.jpg' in line for line in dialogs.calls[0][2])
    assert not orphan.exists()


def test_clean_rows_error_reaches_message(world, page, dialogs, messages, monkeypatch):
    """Ошибка базы: сообщение пользователю."""
    def fail():
        raise RuntimeError('база недоступна')

    monkeypatch.setattr(sp, 'get_db', fail)
    page._on_clean_rows_clicked()
    assert messages[0][0] == 'critical'
    assert 'база недоступна' in messages[0][2]


def test_kept_list_is_limited(page, messages):
    """Длинный список неудалённого в сообщении сокращается."""
    page._show_cleanup_result(
        "Очистка",                              # заголовок
        0,                                      # удалено
        [f'f{i}' for i in range(25)],           # не удалено
    )
    text = messages[0][2]
    assert 'f19' in text
    assert 'f20' not in text
    assert 'и ещё 5' in text


# --- окно подтверждения -------------------------------------------------------------------

@pytest.mark.parametrize('code, expected', [
    (QDialog.DialogCode.Accepted, True),
    (QDialog.DialogCode.Rejected, False),
])
def test_confirm_dialog_shows_full_list(qapp, monkeypatch, code, expected):
    """Окно показывает весь список и пояснение; ответ — по кнопке; по умолчанию выбрана отмена."""
    seen = {}

    def run(dialog):
        seen['list'] = dialog.findChild(QPlainTextEdit).toPlainText()
        seen['intro'] = dialog.findChild(QLabel).text()
        buttons = dialog.findChild(QDialogButtonBox)
        seen['default'] = [b.isDefault() for b in buttons.buttons()]
        seen['roles'] = [buttons.buttonRole(b) for b in buttons.buttons()]
        return code

    monkeypatch.setattr(sp.QDialog, 'exec', run)
    lines = [f'файл{i}.jpg' for i in range(500)]
    assert sp.confirm_cleanup(None, "Заголовок", "Будет удалено", lines) is expected
    assert seen['list'].splitlines() == lines
    assert seen['intro'] == "Будет удалено"
    # кнопка по умолчанию — отмена: Enter ничего не удалит
    index = seen['default'].index(True)
    assert seen['roles'][index] == QDialogButtonBox.ButtonRole.RejectRole


def test_storage_report_notes_empty():
    """Пояснять нечего — пусто."""
    assert sp.storage_report_notes({'extra': ['a'], 'fresh': [], 'empty_dirs': [], 'missing': []}) == []
