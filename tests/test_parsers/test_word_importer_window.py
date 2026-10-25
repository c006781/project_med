# tests/test_parsers/test_word_importer_window.py

"""
Импорт из Word в окне (offscreen Qt): предупреждения W2 видны пользователю.

Проход 1 ``parsers/word_importer.py`` (2026-10-25, ``parsers/IMPLEMENTATION.md`` W2):
статус файла в диалоге прогресса и итоговое окно показывают предупреждения
(нераспознанный телефон не записан). Остальное окно импорта — М18 (``_dev/ПЛАН.md`` Ф2.1.6).
Журналы и конфиг — временные (``tests/conftest.py``).
"""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QWidget  # noqa: E402

from interfaces.gui.gui_window import main_window  # noqa: E402


@pytest.fixture
def qapp():
    """Приложение Qt (одно на процесс)."""
    return QApplication.instance() or QApplication([])


def test_w2_dialog_shows_warning(qapp):
    """Успешный файл с предупреждением — «✅ Готово ⚠️ …», без предупреждения — «✅ Готово»."""
    dialog = main_window.ParsingProgressDialog()
    dialog.set_file_list(['а.docx', 'б.docx'])

    dialog.update_file_status('а.docx', 'success', 'Телефон не распознан: «12-34-56»')
    dialog.update_file_status('б.docx', 'success', '')

    assert dialog.list_widget.item(0).text().endswith('✅ Готово ⚠️ Телефон не распознан: «12-34-56»')
    assert dialog.list_widget.item(1).text().endswith('✅ Готово')
    dialog.deleteLater()


def test_w2_finished_message_has_warnings(qapp, monkeypatch):
    """Итоговое окно — текст format_results: ошибки и предупреждения по файлам."""
    shown = []
    monkeypatch.setattr(
        QMessageBox,
        'information',
        lambda parent, title, text: shown.append((title, text)),
    )
    window = main_window.MainWindow.__new__(main_window.MainWindow)     # без построения окна
    monkeypatch.setattr(
        main_window.MainWindow,
        '_refresh_after_parsing',
        lambda self: None,
    )

    window._on_parsing_finished(
        {
            'total'       : 1,
            'success'     : 1,
            'failed'      : 0,
            'error_files' : [],
            'warnings'    : [{'file_name': 'а.docx', 'warning': 'Телефон не распознан: «12-34-56»'}],
            'log_path'    : None,
        },
    )

    [(title, text)] = shown
    assert title == 'Парсинг завершён'
    assert 'Предупреждения:' in text
    assert 'а.docx: Телефон не распознан: «12-34-56»' in text


@pytest.mark.parametrize(
    'answer, checked, expected',
    [
        (QMessageBox.Ok, False, False),       # «Импорт», флажок снят — без поиска
        (QMessageBox.Ok, True, True),         # «Импорт», флажок — искать пациентов
        (QMessageBox.Cancel, True, None),     # «Отмена» — импорт не начинается
    ],
)
def test_td8_ask_find_existing(qapp, monkeypatch, answer, checked, expected):
    """ТД-8: перед импортом — вопрос с флажком «искать существующих пациентов» (снят по умолчанию)."""
    seen = {}

    def fake_exec(box):
        """Вместо показа: запоминает флажок по умолчанию, ставит ответ пользователя."""
        check = box.findChild(QCheckBox)
        seen['default'] = check.isChecked()
        check.setChecked(checked)
        return answer

    monkeypatch.setattr(QMessageBox, 'exec', fake_exec)
    parent = QWidget()          # методу нужен только родитель вопроса — окно не строим

    assert main_window.MainWindow._ask_find_existing(parent, 'C:/Документы') is expected
    assert seen['default'] is False
    parent.deleteLater()


def test_td8_thread_passes_flag(monkeypatch):
    """ТД-8: поток импорта передаёт выбор пользователя в batch_parse."""
    import parsers.word_importer as word_importer
    calls = []
    monkeypatch.setattr(
        word_importer,
        'batch_parse',
        lambda **kwargs: calls.append(kwargs) or ({'total': 0}, None),
    )

    main_window.ParsingThread('C:/Документы', find_existing=True).run()

    assert calls[0]['find_existing_patient'] is True
