# tests/test_main_window/conftest.py
"""
Общее для тестов главного окна: заменитель окна из настоящих миксинов, окна сообщений подменены.

Настоящее окно здесь не строится (оно пишет журналы, открывает базу, ставит таймеры): запуск
настоящего окна — только в подпроцессе, ``test_main_window_startup.py``. Сеть не используется.
"""
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QProgressBar, QWidget

import app.network.ya_dop as ya_module
from interfaces.gui.gui_window import main_window as mw


class WindowHost(QWidget, mw.SyncMixin, mw.UpdateMixin):
    """
    Заменитель окна: настоящий виджет и настоящие миксины Диска и обновлений.

    Порядок базовых классов тот же, что у ``MainWindow``. Методы окна, нужные миксинам, взяты у
    самого ``MainWindow``; черновиков и страниц нет, пока тест их не задаст.

    Attributes:
        logger       : (MagicMock) Журнал.
        progress_bar : (QProgressBar) Полоса прогресса.
    """

    _resolve_unsaved_before_exit = mw.MainWindow._resolve_unsaved_before_exit
    _old_pages_with_changes = mw.MainWindow._old_pages_with_changes
    _confirm_old_pages_loss = mw.MainWindow._confirm_old_pages_loss

    def __init__(self) -> None:
        super().__init__()
        self.logger = MagicMock()
        self.progress_bar = QProgressBar()
        self.stacked_widget = QWidget()
        self.action_combo = QComboBox()
        self.update_progress_dialog = None
        self._transfer_running = False


class Messages(list):
    """Записи окон сообщений: (вид, заголовок, текст); ``answer`` — ответ на вопрос."""

    answer = QMessageBox.StandardButton.Yes

    def texts(self, kind: str) -> List[Tuple[str, str]]:
        """Заголовки и тексты окон этого вида."""
        return [(title, text) for shown, title, text in self if shown == kind]


@pytest.fixture
def qapp() -> QApplication:
    """Приложение Qt на платформе offscreen."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def messages(monkeypatch) -> Messages:
    """Подменяет окна сообщений: они записываются, а не показываются."""
    log = Messages()

    def record(kind: str) -> Any:
        def show(parent, title, text, *args, **kwargs):
            log.append((kind, title, text))
            return log.answer if kind == 'question' else QMessageBox.StandardButton.Ok
        return staticmethod(show)

    for kind in ('question', 'warning', 'information', 'critical'):
        monkeypatch.setattr(QMessageBox, kind, record(kind))
    return log


@pytest.fixture
def host(qapp) -> WindowHost:
    """Заменитель окна; окно ожидания установки закрывается после теста."""
    window = WindowHost()
    yield window
    window._close_update_progress()


class FakeDisk:
    """
    Подменённый клиент Яндекс.Диска с одной базой; сеть не используется.

    Attributes:
        content    : (bytes) Файл на Диске.
        fail_after : (int/None) Записать столько байт и оборвать соединение.
        client     : (MagicMock) Клиент, который получает код.
        on_download: (callable/None) Вызывается в начале скачивания (проверка порядка).
    """

    def __init__(self, content: bytes, modified: datetime) -> None:
        self.content = content
        self.fail_after = None
        self.on_download = None
        self.client = MagicMock(name='YaDisk')
        self.client.check_token.return_value = True
        self.client.get_meta.return_value = SimpleNamespace(
            type        =   'file',                             # файл
            size        =   len(content),                       # размер
            md5         =   hashlib.md5(content).hexdigest(),   # контрольная сумма
            modified    =   modified,                           # дата на Диске
        )
        self.client.download.side_effect = self._download

    def _download(self, src_path, dst_path, progress_callback=None) -> None:
        """Пишет файл или его часть с обрывом."""
        if self.on_download:
            self.on_download()
        with open(dst_path, 'wb') as file:
            if self.fail_after is not None:
                file.write(self.content[:self.fail_after])
                raise ConnectionError('обрыв соединения')
            file.write(self.content)


def make_sqlite_bytes(folder: Any, value: str) -> bytes:
    """Создаёт в папке базу SQLite с одной строкой и возвращает её байты."""
    path = os.path.join(str(folder), f'source-{value}.db')
    connection = sqlite3.connect(path)
    with connection:
        connection.execute('CREATE TABLE t (v TEXT)')
        connection.execute('INSERT INTO t VALUES (?)', (value,))
    connection.close()
    with open(path, 'rb') as file:
        data = file.read()
    os.remove(path)
    return data


def read_sqlite_value(path: Any) -> str:
    """Читает строку из базы, созданной ``make_sqlite_bytes``."""
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute('SELECT v FROM t').fetchone()[0]
    finally:
        connection.close()


@pytest.fixture
def work_db(tmp_path) -> Any:
    """Рабочая база ``clinic.db`` со значением 'local', изменена час назад."""
    folder = tmp_path / 'work'
    folder.mkdir()
    local = folder / 'clinic.db'
    local.write_bytes(make_sqlite_bytes(folder, 'local'))
    stamp = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
    os.utime(local, (stamp, stamp))
    return local


@pytest.fixture
def disk(tmp_path) -> FakeDisk:
    """Диск с базой 'remote', файл на Диске новее рабочей базы."""
    fake = FakeDisk(
        make_sqlite_bytes(tmp_path, 'remote'),  # файл на Диске
        datetime.now(timezone.utc),             # дата на Диске
    )
    with patch.object(ya_module.yadisk, 'YaDisk', return_value=fake.client):
        yield fake
