# tests/test_main_window/test_pilot_moved_record.py
"""
Экран наборов данных и перенесённая запись: правка считается пользовательской, сохранение без
обработчика окна задаёт вопросы. База не используется: хранилище подменено.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QWidget

from app.dataset_app.drafts_writer import DraftsWriter
from interfaces.gui.gui_window.pages.dataset_pilot_page import DataSetPilotPage


def test_writer_marks_user_edit():
    """Правка с экрана передаётся хранилищу как правка пользователя."""
    store = MagicMock()
    store.get.return_value = None
    writer = DraftsWriter.__new__(DraftsWriter)
    writer.store = store
    writer.entity = 'photo'
    writer._own = 0
    writer._parent = lambda row: 5
    writer.update(None, 7, {'appointment_id': -1}, {'appointment_id': -1}, {'appointment_id': 12})
    assert store.modify.call_args.kwargs['by_user'] is True
    assert store.modify.call_args.kwargs['original'] == {'appointment_id': 12}


class PageStub(QWidget):
    """Заменитель экрана с настоящими методами сохранения."""

    save = DataSetPilotPage.save
    _save_targets = DataSetPilotPage._save_targets
    _save_with_questions = DataSetPilotPage._save_with_questions

    def __init__(self, drafts) -> None:
        super().__init__()
        self.drafts = drafts
        self._save_handler = None
        self.clinic = SimpleNamespace(drafts=drafts, post_all=lambda: None, patients=SimpleNamespace(current_key=3))
        self.status = []

    def show_status(self, text: str) -> None:
        self.status.append(text)

    def show_error(self, text: str) -> None:
        self.status.append(text)


def test_save_all_passes_questions(qapp):
    """«Сохранить всё» без обработчика окна: вопросы переданы."""
    drafts = MagicMock()
    page = PageStub(drafts)
    assert page.save() is True
    kwargs = drafts.save.call_args.kwargs
    assert callable(kwargs['confirm_new_ancestors'])
    assert callable(kwargs['confirm_deletes'])


def test_save_targets_passes_questions(qapp):
    """Сохранение отмеченных без обработчика окна: вопросы переданы."""
    drafts = MagicMock()
    page = PageStub(drafts)
    assert page._save_targets([('patient', 3)]) is True
    assert drafts.save.call_args.args[0] == [('patient', 3)]
    assert callable(drafts.save.call_args.kwargs['confirm_deletes'])


def test_refused_question_reports_cancel(qapp):
    """Отказ в вопросе: статус говорит об отмене."""
    drafts = MagicMock()
    drafts.save.return_value = None
    page = PageStub(drafts)
    assert page.save() is False
    assert page.status == ['Сохранение отменено']


def test_window_handler_still_used(qapp):
    """Обработчик окна главнее: прямого сохранения нет."""
    drafts = MagicMock()
    page = PageStub(drafts)
    page._save_handler = MagicMock(return_value=True)
    assert page.save() is True
    drafts.save.assert_not_called()
