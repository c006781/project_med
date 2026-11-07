# tests/test_main_window/test_main_window_word_import.py
"""
Импорт из Word в окне: итоги в окне прогресса, закрытие обновляет страницы, папка из настроек.

Окно не строится: методы вызываются на виджете-заменителе; файлы и база не используются.
"""
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QFileDialog, QWidget

from app.config.config_manager.manager import AppConfigManager, WORD_DOCUMENTS_PATH_KEY
from interfaces.gui.gui_window import main_window as mw

RESULTS = {
    'total'       : 2,
    'success'     : 1,
    'failed'      : 1,
    'error_files' : [{'file_name': 'б.docx', 'error': 'не читается'}],
    'warnings'    : [{'file_name': 'а.docx', 'warning': 'Телефон не распознан'}],
    'log_path'    : '/журнал/parser.log',
}


class ImportHost(QWidget):
    """Заменитель окна с настоящими методами импорта и записью обновления страниц."""

    _on_parsing_finished = mw.MainWindow._on_parsing_finished
    _on_parsing_error = mw.MainWindow._on_parsing_error
    _on_parsing_dialog_closed = mw.MainWindow._on_parsing_dialog_closed
    _start_parsing = mw.MainWindow._start_parsing
    _running_task = mw.SyncMixin._running_task

    def __init__(self) -> None:
        super().__init__()
        self.logger = MagicMock()
        self.refreshed = 0
        self.progress_dialog = None

    def _refresh_after_parsing(self) -> None:
        self.refreshed += 1


@pytest.fixture
def import_host(qapp):
    """Заменитель с открытым окном прогресса."""
    host = ImportHost()
    host.progress_dialog = mw.ParsingProgressDialog(host)
    host.progress_dialog.show()
    return host


def test_results_stay_in_open_dialog(import_host, messages):
    """Окно открыто: итоги в нём, окна сообщения нет, страницы обновятся при закрытии."""
    dialog = import_host.progress_dialog
    import_host._on_parsing_finished(RESULTS)
    assert dialog.isVisible() is True
    text = dialog.summary_text.toPlainText()
    assert 'Обработано файлов: 2' in text
    assert 'б.docx: не читается' in text
    assert 'а.docx: Телефон не распознан' in text
    assert messages == []
    assert import_host.refreshed == 0


def test_close_button_refreshes_pages(import_host, messages):
    """«Закрыть» закрывает окно и обновляет страницы один раз."""
    dialog = import_host.progress_dialog
    import_host._on_parsing_finished(RESULTS)
    assert dialog.close_btn.text() == 'Закрыть'
    dialog.close_btn.click()
    assert dialog.isVisible() is False
    assert import_host.refreshed == 1
    assert import_host.progress_dialog is None


def test_esc_after_finish_also_refreshes(import_host, messages):
    """Esc после итогов тоже обновляет страницы."""
    dialog = import_host.progress_dialog
    import_host._on_parsing_finished(RESULTS)
    dialog.reject()
    assert dialog.isVisible() is False
    assert import_host.refreshed == 1


def test_hidden_dialog_falls_back_to_message(import_host, messages):
    """Окно скрыто пользователем: итоги сообщением, страницы сразу."""
    import_host.progress_dialog.close_btn.click()
    assert import_host.progress_dialog.isVisible() is False
    import_host._on_parsing_finished(RESULTS)
    [(title, text)] = messages.texts('information')
    assert title == 'Парсинг завершён'
    assert 'б.docx: не читается' in text
    assert import_host.refreshed == 1


def test_error_close_button_really_closes(import_host, messages):
    """Сбой импорта: кнопка «Закрыть» закрывает модальное окно, страницы обновляются."""
    dialog = import_host.progress_dialog
    import_host._on_parsing_error('нет доступа к папке')
    assert 'нет доступа к папке' in dialog.summary_text.toPlainText()
    dialog.close_btn.click()
    assert dialog.isVisible() is False
    assert import_host.refreshed == 1


def test_error_without_dialog_is_a_message(qapp, messages):
    """Окно уже скрыто: сбой сообщением."""
    host = ImportHost()
    host._on_parsing_error('сбой')
    [(_title, text)] = messages.texts('critical')
    assert 'сбой' in text
    assert host.refreshed == 1


def test_status_does_not_pile_up(qapp):
    """Статус заменяет прежний, имя файла остаётся."""
    dialog = mw.ParsingProgressDialog()
    dialog.set_file_list(['а.docx'])
    dialog.update_file_status('а.docx', 'processing')
    dialog.update_file_status('а.docx', 'success', 'Телефон не распознан')
    text = dialog.list_widget.item(0).text()
    assert text.startswith('а.docx')
    assert 'Ожидание' not in text
    assert 'Обработка' not in text
    assert 'Телефон не распознан' in text


def test_button_does_not_promise_cancel(qapp):
    """Отменить импорт нельзя, кнопка этого не обещает."""
    assert mw.ParsingProgressDialog().close_btn.text() == 'Скрыть'


def test_folder_dialog_opens_in_setting(qapp, monkeypatch):
    """Выбор папки открывается в папке документов из настроек; отмена импорт не начинает."""
    seen = {}

    def choose(parent, title, start, options):
        seen['start'] = start
        return ''

    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', staticmethod(choose))
    monkeypatch.setattr(
        AppConfigManager,
        'get_instance',
        classmethod(lambda cls, *a, **k: {WORD_DOCUMENTS_PATH_KEY: '/документы/word'}),
    )
    ImportHost()._start_parsing()
    assert seen['start'] == '/документы/word'


def test_second_import_is_refused_while_running(qapp, messages, monkeypatch):
    """Импорт уже идёт: второй поток не запускается, поток не уничтожается на ходу."""
    host = ImportHost()
    host.parsing_thread = MagicMock()
    host.parsing_thread.isRunning.return_value = True
    choose = MagicMock()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', staticmethod(choose))
    host._start_parsing()
    choose.assert_not_called()
    [(_title, text)] = messages.texts('warning')
    assert 'импорт из Word' in text
