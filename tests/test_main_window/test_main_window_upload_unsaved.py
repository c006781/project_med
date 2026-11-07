# tests/test_main_window/test_main_window_upload_unsaved.py
"""
Выгрузка базы на Диск при несохранённых изменениях: вопрос до копии и передачи (В-39).

Окно — лёгкая заглушка с настоящим методом, сеть и файлы не участвуют.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox

from interfaces.gui.gui_window import main_window as mw


# заглушка окна с настоящими проверками выгрузки
def _host(
    drafts_empty : bool = True,     # черновиков нет
    pending      : str = None,      # незавершённая правка экрана наборов данных
    running      : str = None,      # идущая работа
) -> SimpleNamespace:
    """Собирает заглушку: `_prepare_transfer` возвращает None, чтобы передача не началась."""
    host = SimpleNamespace(
        drafts              =   SimpleNamespace(store=SimpleNamespace(is_empty=drafts_empty)),
        dataset_pilot_page  =   SimpleNamespace(finish_pending_edits=lambda: pending),
        _running_task       =   lambda: running,
        _prepare_transfer   =   MagicMock(return_value=None),
    )
    host._confirm_upload_unsaved = lambda: mw.SyncMixin._confirm_upload_unsaved(host)
    return host


@pytest.fixture
def question(monkeypatch):
    """Подменяет вопрос: запоминает вызовы, по умолчанию отвечает «Нет»."""
    ask = MagicMock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(mw.QMessageBox, 'question', ask)
    return ask


def test_no_changes_no_question(question):
    """Изменений нет: вопроса нет, передача идёт дальше."""
    host = _host()
    mw.SyncMixin._start_upload(host)
    question.assert_not_called()
    host._prepare_transfer.assert_called_once()


@pytest.mark.parametrize('kwargs', [{'drafts_empty': False}, {'pending': 'Пациенты: дата неверна'}])
def test_refused_stops_before_backup(question, kwargs):
    """Черновики или незавершённая правка, отказ: ни копии, ни передачи."""
    host = _host(**kwargs)
    mw.SyncMixin._start_upload(host)
    question.assert_called_once()
    host._prepare_transfer.assert_not_called()


def test_accepted_goes_on(question):
    """Пользователь согласился: передача идёт дальше."""
    question.return_value = QMessageBox.StandardButton.Yes
    host = _host(drafts_empty=False)
    mw.SyncMixin._start_upload(host)
    host._prepare_transfer.assert_called_once()


def test_default_answer_is_no(question):
    """По умолчанию в вопросе выбран отказ."""
    host = _host(drafts_empty=False)
    mw.SyncMixin._start_upload(host)
    assert question.call_args.args[-1] == QMessageBox.StandardButton.No


def test_running_task_no_question(question):
    """Идёт другая работа: не спрашивать, откажет проверка в `_prepare_transfer`."""
    host = _host(drafts_empty=False, running='скачивание')
    mw.SyncMixin._start_upload(host)
    question.assert_not_called()
    host._prepare_transfer.assert_called_once()
