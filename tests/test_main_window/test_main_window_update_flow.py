# tests/test_main_window/test_main_window_update_flow.py
"""
Обновление глазами окна: сигналы модуля обновлений, откат Linux, несохранённое перед установкой.

Модуль обновлений настоящий или подменён, сеть не используется.
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

import app.updater
from interfaces.gui.gui_window import main_window as mw


@pytest.fixture
def connected(host):
    """Заменитель окна с настоящим AppUpdater и подключёнными сигналами."""
    host._init_updater()
    return host


def test_warning_signal_is_connected(connected, messages):
    """Предупреждение установки (нет хеша) доходит до пользователя."""
    connected.updater.download_warning.emit('нет контрольной суммы')
    assert messages.texts('warning') == [('Предупреждение об обновлении', 'нет контрольной суммы')]


def test_update_error_goes_to_update_handler(connected, messages):
    """Ошибка обновления — обработчиком обновлений, хотя SyncMixin раньше в наследовании."""
    connected.updater.download_error.emit('нет прав на запись')
    assert messages.texts('warning') == [('Обновление не установлено', 'нет прав на запись')]
    assert messages.texts('critical') == []


def test_update_error_title_does_not_claim_download(connected, messages):
    """Отказ до скачивания: заголовок не говорит о скачивании."""
    connected.updater.download_error.emit('Обновление работает только в установленной программе')
    [(title, _text)] = messages.texts('warning')
    assert 'скачать' not in title.lower()
    assert 'загруз' not in title.lower()


def test_update_error_hides_progress(connected, messages):
    """После ошибки полоса скрыта, окно ожидания закрыто."""
    connected.progress_bar.setVisible(True)
    connected.update_progress_dialog = mw.UpdateProgressDialog(connected)
    connected.updater.download_error.emit('сбой')
    assert connected.progress_bar.isVisibleTo(connected) is False
    assert connected.update_progress_dialog is None


def test_progress_updates_bar_and_dialog(connected):
    """Прогресс виден и в окне ожидания; размер неизвестен — бегущая полоса."""
    connected.update_progress_dialog = mw.UpdateProgressDialog(connected)
    connected.updater.download_progress.emit(30, 100)
    assert connected.progress_bar.value() == 30
    assert connected.update_progress_dialog.maximum() == 100
    assert connected.update_progress_dialog.value() == 30
    connected.updater.download_progress.emit(30, 0)
    assert connected.progress_bar.maximum() == 0
    assert connected.update_progress_dialog.maximum() == 0


# ---- причина отката Linux ----

def _use_system(monkeypatch, system: str) -> None:
    """Подменяет определение ОС у окна."""
    monkeypatch.setattr(mw, 'current_system', lambda: system)


def test_linux_failure_shown_once_with_db_hint(host, messages, monkeypatch, tmp_path):
    """Настоящий файл причины: показан один раз и удалён, подсказка о копии базы добавлена."""
    _use_system(monkeypatch, 'linux')
    monkeypatch.setattr(app.updater, 'get_install_root', lambda: str(tmp_path))
    (tmp_path / app.updater.LINUX_FAILURE_FILE).write_text('не установлен файл app/x.py', encoding='utf-8')
    host._show_linux_update_failure()
    [(title, text)] = messages.texts('warning')
    assert title == 'Обновление не установлено'
    assert 'не установлен файл app/x.py' in text
    assert '.bak-' in text
    assert 'не возвращается' in text
    assert not (tmp_path / app.updater.LINUX_FAILURE_FILE).exists()
    host._show_linux_update_failure()
    assert len(messages.texts('warning')) == 1


def test_linux_failure_hint_is_not_repeated(host, messages, monkeypatch):
    """Причина уже называет копию базы: подсказка не дублируется."""
    _use_system(monkeypatch, 'linux')
    reason = 'новая версия не запустилась: копия базы рядом (*.bak-*)'
    monkeypatch.setattr(mw, 'pop_linux_update_failure', lambda: reason)
    host._show_linux_update_failure()
    assert messages.texts('warning') == [('Обновление не установлено', reason)]


def test_linux_failure_no_file_no_message(host, messages, monkeypatch):
    """Сбоя не было: окна нет."""
    _use_system(monkeypatch, 'linux')
    monkeypatch.setattr(mw, 'pop_linux_update_failure', lambda: None)
    host._show_linux_update_failure()
    assert messages == []


def test_linux_failure_only_on_linux(host, messages, monkeypatch):
    """На другой ОС файл не читается."""
    _use_system(monkeypatch, 'windows')
    pop = MagicMock(return_value='текст')
    monkeypatch.setattr(mw, 'pop_linux_update_failure', pop)
    host._show_linux_update_failure()
    pop.assert_not_called()
    assert messages == []


# ---- несохранённое перед установкой ----

def _with_drafts(host, monkeypatch, choice: str, saved: bool = True) -> MagicMock:
    """Даёт окну непустые черновики и ответ на вопрос при выходе."""
    import interfaces.gui.gui_window.drafts_qt as dq
    host.drafts = SimpleNamespace(store=SimpleNamespace(is_empty=False))
    monkeypatch.setattr(dq, 'ask_on_close', lambda parent: choice)
    host.save_drafts = MagicMock(return_value=saved)
    return host.save_drafts


@pytest.fixture
def updater_mock(host):
    """Подменённый модуль обновлений: установка записывается, программа не завершается."""
    host.updater = MagicMock()
    return host.updater


def test_install_without_changes_starts_at_once(host, updater_mock, messages):
    """Изменений нет: без вопросов, сразу установка и модальное окно ожидания."""
    host._install_update({'tag_name': 'v2'})
    updater_mock.apply_update_from_release.assert_called_once_with({'tag_name': 'v2'})
    assert messages == []
    assert host.update_progress_dialog.isModal() is True


def test_install_cancelled_on_unsaved(host, updater_mock, monkeypatch):
    """Ответ «отмена»: установка не начинается."""
    _with_drafts(host, monkeypatch, 'cancel')
    host._install_update({'tag_name': 'v2'})
    updater_mock.apply_update_from_release.assert_not_called()
    assert host.update_progress_dialog is None


def test_install_saves_before_exit(host, updater_mock, monkeypatch):
    """Ответ «сохранить»: сначала сохранение, потом установка."""
    save = _with_drafts(host, monkeypatch, 'save')
    host._install_update({'tag_name': 'v2'})
    save.assert_called_once_with()
    updater_mock.apply_update_from_release.assert_called_once()


def test_install_stops_when_save_failed(host, updater_mock, monkeypatch):
    """Сохранение не удалось: установка не начинается, изменения остаются."""
    _with_drafts(host, monkeypatch, 'save', saved=False)
    host._install_update({'tag_name': 'v2'})
    updater_mock.apply_update_from_release.assert_not_called()


def test_discard_keeps_drafts_until_exit(host, updater_mock, monkeypatch):
    """«Не сохранять»: установка идёт, черновики на месте, на случай её неудачи."""
    save = _with_drafts(host, monkeypatch, 'discard')
    host._install_update({'tag_name': 'v2'})
    save.assert_not_called()
    updater_mock.apply_update_from_release.assert_called_once()
    assert host.drafts.store.is_empty is False


def test_pending_pilot_edit_is_finished_first(host, updater_mock, messages):
    """Незавершённая правка, которая не прошла проверку: установка не начинается."""
    host.dataset_pilot_page = SimpleNamespace(finish_pending_edits=lambda: 'пустое поле')
    host._install_update({'tag_name': 'v2'})
    updater_mock.apply_update_from_release.assert_not_called()
    [(title, text)] = messages.texts('warning')
    assert title == 'Незавершённая правка'
    assert 'пустое поле' in text


def _with_old_page(host, changed) -> None:
    """Даёт окну один старый экран со своими правками."""
    def check():
        if isinstance(changed, Exception):
            raise changed
        return changed
    host.page_manager = SimpleNamespace(
        _pages          =   {'note_list': SimpleNamespace(_has_unsaved_changes=check)},
        _get_page_title =   lambda page_id: 'Заметки',
    )


@pytest.mark.parametrize('answer, started', [
    (QMessageBox.StandardButton.No, False),
    (QMessageBox.StandardButton.Yes, True),
])
def test_old_page_changes_are_asked(host, updater_mock, messages, answer, started):
    """Правки старого экрана не теряются молча: вопрос с названием экрана."""
    _with_old_page(host, True)
    messages.answer = answer
    host._install_update({'tag_name': 'v2'})
    assert updater_mock.apply_update_from_release.called is started
    [(_title, text)] = messages.texts('question')
    assert 'Заметки' in text


def test_old_page_check_failure_means_ask(host, updater_mock, messages):
    """Сбой проверки экрана — вопрос, а не молчаливая потеря."""
    _with_old_page(host, RuntimeError('сломан'))
    messages.answer = QMessageBox.StandardButton.No
    host._install_update({'tag_name': 'v2'})
    updater_mock.apply_update_from_release.assert_not_called()


def test_old_page_no_changes_no_question(host, updater_mock, messages):
    """Правок на старом экране нет: вопроса нет."""
    _with_old_page(host, False)
    host._install_update({'tag_name': 'v2'})
    assert messages == []
    updater_mock.apply_update_from_release.assert_called_once()


# ---- окно ожидания ----

def test_progress_dialog_cannot_be_closed_by_user(qapp):
    """Esc и закрытие окна не срабатывают: правка после вопроса о несохранённом невозможна."""
    dialog = mw.UpdateProgressDialog()
    dialog.show()
    dialog.reject()
    assert dialog.isVisible() is True
    assert dialog.close() is False
    assert dialog.isVisible() is True
    dialog.finish()
    assert dialog.isVisible() is False


# ---- кнопка «Скачать и установить» ----

def _click(monkeypatch, text: str) -> None:
    """Подменяет показ вопроса: выбрана кнопка с этим текстом."""
    monkeypatch.setattr(QMessageBox, 'exec', lambda self: 0)
    monkeypatch.setattr(
        QMessageBox,
        'clickedButton',
        lambda self: next(b for b in self.buttons() if b.text() == text),
    )


def test_download_button_uses_public_property(host, messages, monkeypatch):
    """Данные релиза — из свойства модуля, закрытый атрибут не читается."""
    _click(monkeypatch, 'Скачать и установить')
    host.updater = SimpleNamespace(
        pending_release_data        =   {'tag_name': 'v2'},
        apply_update_from_release   =   MagicMock(),
    )
    host._on_update_available('v2', 'https://x/r')
    host.updater.apply_update_from_release.assert_called_once_with({'tag_name': 'v2'})


def test_download_button_without_release_data(host, messages, monkeypatch):
    """Данных релиза нет: сообщение, установка не начинается."""
    _click(monkeypatch, 'Скачать и установить')
    host.updater = SimpleNamespace(
        pending_release_data        =   None,
        apply_update_from_release   =   MagicMock(),
    )
    host._on_update_available('v2', 'https://x/r')
    host.updater.apply_update_from_release.assert_not_called()
    assert messages.texts('warning') == [('Ошибка', 'Не удалось получить данные релиза')]


# ---- замена файла окном ----

def test_apply_update_file_has_no_linux_script(host, messages, monkeypatch, tmp_path):
    """На Linux окно не заменяет файл и не запускает скрипт: это делает UpdateApplier."""
    new_file = tmp_path / 'new'
    current = tmp_path / 'current'
    new_file.write_text('1')
    current.write_text('2')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(current))
    monkeypatch.setattr(mw.platform, 'system', lambda: 'Linux')
    popen = MagicMock()
    monkeypatch.setattr(mw.subprocess, 'Popen', popen)
    host._apply_update_file(str(new_file))
    popen.assert_not_called()
    [(title, _text)] = messages.texts('warning')
    assert title == 'ОС не поддерживается'


def test_file_replacement_asks_about_unsaved(host, messages, monkeypatch):
    """Замена скачанным файлом тоже не теряет несохранённое."""
    _with_drafts(host, monkeypatch, 'cancel')
    host._apply_update_file = MagicMock()
    host._on_update_download_finished('/tmp/update')
    host._apply_update_file.assert_not_called()
