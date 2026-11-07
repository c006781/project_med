# tests/test_main_window/test_main_window_db_transfer.py
"""
Скачивание и выгрузка базы из окна: настоящие миксин, поток (``run`` без потока ОС) и файлы; клиент
Диска подменён, сеть не используется. Закрытие и открытие базы подменены: заменитель окна не
работает с общей базой (настоящая замена — ``test_main_window_startup.py``).
"""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

from app.config.config_manager.manager import AppConfigManager
from app.exceptions.exceptions_all import YandexDiskBackupError
from app.network.thread_network import CheckedDownloadThread
from app.services import sync_service as ss
from interfaces.gui.gui_window import main_window as mw
from tests.test_main_window.conftest import read_sqlite_value


@pytest.fixture
def window(host, work_db, tmp_path, monkeypatch):
    """Заменитель окна: настройки временные, поток скачивания выполняется сразу."""
    settings = {
        'YANDEX_TOKEN'         : 't',
        'database_remote_path' : 'Папка',
        'database_local_path'  : str(work_db),
        'BACKUP_PATH'          : str(tmp_path / 'копии'),
        'BACKUP_COUNT'         : 5,
    }
    monkeypatch.setattr(AppConfigManager, 'get_instance', classmethod(lambda cls, *a, **k: settings))
    monkeypatch.setattr(CheckedDownloadThread, 'start', lambda self: self.run())
    import app.dependencies as deps
    monkeypatch.setattr(deps, 'close_db', MagicMock())
    monkeypatch.setattr(ss, '_reopen_app_db', MagicMock())
    host.on_settings_changed = MagicMock()
    host.settings = settings
    return host


def _copies(tmp_path) -> list:
    """Файлы в папке копий."""
    folder = tmp_path / 'копии'
    return os.listdir(folder) if folder.exists() else []


def test_broken_download_leaves_db_and_backup(window, work_db, tmp_path, disk, messages):
    """Готово: обрыв скачивания не портит рабочую базу, старая — в резервной копии."""
    before = work_db.read_bytes()
    disk.fail_after = 100
    window._start_download()
    assert work_db.read_bytes() == before
    assert os.listdir(work_db.parent) == ['clinic.db']
    [copy] = _copies(tmp_path)
    assert read_sqlite_value(tmp_path / 'копии' / copy) == 'local'
    [(title, text)] = messages.texts('critical')
    assert title == 'База не скачана'
    assert 'Рабочая база не менялась' in text
    assert window._transfer_running is False
    assert window.stacked_widget.isEnabled() is True
    assert window.progress_bar.isVisibleTo(window) is False
    window.on_settings_changed.assert_not_called()


def test_failure_details_go_to_log(window, disk, messages):
    """Подробности сбоя — в журнал (log_text исключения)."""
    disk.fail_after = 100
    window._start_download()
    assert any('обрыв' in str(call) for call in window.logger.error.call_args_list)


def test_download_replaces_and_reloads(window, work_db, tmp_path, disk, messages):
    """Диск новее: база заменена без вопроса, экраны обновлены, копия названа в сообщении."""
    window._start_download()
    assert read_sqlite_value(work_db) == 'remote'
    window.on_settings_changed.assert_called_once_with(changed_blocks={'database'})
    [copy] = _copies(tmp_path)
    [(_title, text)] = messages.texts('information')
    assert copy in text
    assert messages.texts('question') == []


def test_backup_exists_before_transfer(window, tmp_path, disk, messages):
    """Копия — до начала скачивания; на время передачи экраны выключены."""
    seen = {}

    def on_download():
        seen['copies'] = len(_copies(tmp_path))
        seen['enabled'] = window.stacked_widget.isEnabled()
        seen['combo'] = window.action_combo.isEnabled()

    disk.on_download = on_download
    window._start_download()
    assert seen == {'copies': 1, 'enabled': False, 'combo': False}
    assert window.stacked_widget.isEnabled() is True


def _local_newer(work_db, disk) -> None:
    """Рабочая база изменена позже файла на Диске."""
    os.utime(work_db)
    disk.client.get_meta.return_value.modified = datetime.now(timezone.utc) - timedelta(days=1)


def test_local_newer_refused_keeps_db(window, work_db, disk, messages):
    """Локальная новее, отказ (по умолчанию): база прежняя, временного файла нет."""
    _local_newer(work_db, disk)
    messages.answer = QMessageBox.StandardButton.No
    window._start_download()
    [(title, text)] = messages.texts('question')
    assert title == 'Локальная база новее'
    assert 'затрёт локальные изменения' in text
    assert read_sqlite_value(work_db) == 'local'
    assert os.listdir(work_db.parent) == ['clinic.db']


def test_local_newer_accepted_replaces(window, work_db, disk, messages):
    """Локальная новее, согласие: база заменена."""
    _local_newer(work_db, disk)
    window._start_download()
    assert read_sqlite_value(work_db) == 'remote'


def test_same_content_no_replace(window, work_db, disk, messages):
    """Содержимое совпало: без замены, временного файла нет, сообщение."""
    import hashlib
    disk.content = work_db.read_bytes()
    disk.client.get_meta.return_value.size = len(disk.content)
    disk.client.get_meta.return_value.md5 = hashlib.md5(disk.content).hexdigest()
    window._start_download()
    assert os.listdir(work_db.parent) == ['clinic.db']
    [(_title, text)] = messages.texts('information')
    assert 'совпадает' in text
    window.on_settings_changed.assert_not_called()


def test_warning_is_shown(window, work_db, disk, messages):
    """Предупреждение проверки (Диск не сообщил MD5) показано вместе с итогом."""
    disk.client.get_meta.return_value.md5 = None
    window._start_download()
    [(_title, text)] = messages.texts('information')
    assert 'MD5' in text or 'контрольн' in text.lower()


# ---- несохранённое ----

@pytest.fixture
def drafts(window):
    """Непустые черновики окна."""
    window.drafts = SimpleNamespace(store=MagicMock(is_empty=False))
    return window.drafts


def test_drafts_refused_keeps_everything(window, work_db, disk, messages, drafts):
    """Несохранённые черновики, отказ: база и черновики на месте, временного файла нет."""
    messages.answer = QMessageBox.StandardButton.No
    window._start_download()
    assert read_sqlite_value(work_db) == 'local'
    drafts.store.clear.assert_not_called()
    assert os.listdir(work_db.parent) == ['clinic.db']


def test_drafts_accepted_are_cleared(window, work_db, disk, messages, drafts):
    """Несохранённые черновики, согласие: база заменена, черновики прежней базы убраны."""
    window._start_download()
    assert read_sqlite_value(work_db) == 'remote'
    drafts.store.clear.assert_called_once_with()
    drafts.store.clear_history.assert_called_once_with()


def test_failed_replace_keeps_drafts(window, work_db, disk, messages, drafts, monkeypatch):
    """Замена не удалась: база прежняя, значит и черновики нужны."""
    def replace(src, dst):
        raise PermissionError('файл занят')
    monkeypatch.setattr(ss.os, 'replace', replace)
    window._start_download()
    assert read_sqlite_value(work_db) == 'local'
    drafts.store.clear.assert_not_called()


def test_pilot_invalid_edit_cancels(window, work_db, disk, messages):
    """Незавершённая правка с ошибкой: замены нет, причина названа."""
    window.dataset_pilot_page = SimpleNamespace(finish_pending_edits=lambda: 'неверная дата')
    window._start_download()
    assert read_sqlite_value(work_db) == 'local'
    [(_title, text)] = messages.texts('warning')
    assert 'неверная дата' in text


def test_old_page_changes_refused(window, work_db, disk, messages):
    """Правки старого экрана, отказ: замены нет."""
    window.page_manager = SimpleNamespace(
        _pages          =   {'note_list': SimpleNamespace(_has_unsaved_changes=lambda: True)},
        _get_page_title =   lambda page_id: 'Заметки',
    )
    messages.answer = QMessageBox.StandardButton.No
    window._start_download()
    assert read_sqlite_value(work_db) == 'local'


# ---- сбои замены и копии ----

def test_replace_failure_message(window, work_db, disk, messages, monkeypatch):
    """Замена не удалась: сообщение с копией, база прежняя, экраны обновлены."""
    def replace(src, dst):
        raise PermissionError('файл занят')
    monkeypatch.setattr(ss.os, 'replace', replace)
    window._start_download()
    assert read_sqlite_value(work_db) == 'local'
    [(title, text)] = messages.texts('critical')
    assert title == 'База не заменена'
    assert 'файл занят' in text
    assert 'Резервная копия' in text
    window.on_settings_changed.assert_called_once()


def test_reload_failure_is_not_fatal(window, disk, messages):
    """Сбой обновления экрана не мешает сообщить итог."""
    window.on_settings_changed.side_effect = RuntimeError('экран сломан')
    window._start_download()
    assert len(messages.texts('information')) == 1


def test_backup_failure_stops_download(window, work_db, disk, messages, monkeypatch):
    """Копия не удалась: скачивание не начато, сообщение, база прежняя."""
    def fail(*args):
        raise YandexDiskBackupError('нет места', local_path='clinic.db')
    monkeypatch.setattr(ss, 'backup_local_db', fail)
    window._start_download()
    disk.client.download.assert_not_called()
    [(title, text)] = messages.texts('critical')
    assert title == 'Резервная копия не сделана'
    assert 'Загрузка с Диска не начата' in text
    assert window._transfer_running is False


def test_no_token_stops_before_backup(window, tmp_path, disk, messages):
    """Нет токена: ни копии, ни скачивания."""
    window.settings['YANDEX_TOKEN'] = ''
    window._start_download()
    assert _copies(tmp_path) == []
    disk.client.download.assert_not_called()


def test_second_transfer_refused(window, tmp_path, disk, messages):
    """Передача уже идёт: новая не начинается, копия не делается."""
    window._transfer_running = True
    window._start_upload()
    assert _copies(tmp_path) == []
    [(_title, text)] = messages.texts('warning')
    assert 'обмен базой' in text


# ---- выгрузка ----

def test_upload_backup_then_thread(window, tmp_path, messages, monkeypatch):
    """Выгрузка: копия до запуска потока, передача выключает экраны, итог включает."""
    thread = MagicMock()
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        seen['copies'] = len(_copies(tmp_path))
        return thread

    monkeypatch.setattr(mw, 'UploadThread', create)
    window._start_upload()
    assert seen['copies'] == 1
    assert seen['remote_path'] == 'Папка/clinic.db'
    assert seen['overwrite'] is True
    thread.start.assert_called_once_with()
    assert window.stacked_widget.isEnabled() is False
    window._on_upload_finished(0)
    assert window.stacked_widget.isEnabled() is True
    assert window._transfer_running is False


def test_upload_error_unlocks(window, messages):
    """Ошибка выгрузки возвращает окно в работу."""
    window._set_transfer_running(True)
    window._on_upload_error('нет места на Диске')
    assert window.stacked_widget.isEnabled() is True
    assert messages.texts('critical') == [('Ошибка', 'нет места на Диске')]


# ---- выход и установка во время передачи ----

def test_exit_refused_during_transfer(window, messages):
    """Идёт передача: выход отменён, сообщение (поток нельзя уничтожить на ходу)."""
    window._transfer_running = True
    assert window._resolve_unsaved_before_exit() is False
    [(title, _text)] = messages.texts('warning')
    assert title == 'Идёт работа'


def test_update_refused_during_transfer(window, messages):
    """Идёт передача: установка обновления не начинается."""
    window._transfer_running = True
    window.updater = MagicMock()
    window._install_update({'tag_name': 'v2'})
    window.updater.apply_update_from_release.assert_not_called()


def test_back_does_nothing_during_transfer(window):
    """«Назад» во время передачи: вопрос о сохранении записал бы в передаваемый файл."""
    window._transfer_running = True
    window.page_manager = MagicMock()
    mw.NavigationMixin._on_back_clicked(window)
    window.page_manager.go_back.assert_not_called()


def test_stale_downloads_removed_at_start(window, work_db):
    """Старт: недокачанные файлы этой базы убраны."""
    stale = work_db.parent / 'clinic.db.download-old.part'
    stale.write_bytes(b'x')
    window._remove_stale_db_downloads()
    assert not stale.exists()
    assert work_db.exists()
