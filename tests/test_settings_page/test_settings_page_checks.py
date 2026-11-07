# tests/test_settings_page/test_settings_page_checks.py
"""
Потоки проверки токена и папки Яндекс.Диска: результат и ошибки доходят до сообщения.

Клиент ``yadisk.YaDisk`` подменён, сети нет; функции Диска настоящие.
"""
import pytest
from PySide6.QtCore import QEventLoop, QTimer

import yadisk

from app.network import ya_dop
from interfaces.gui.gui_window.pages import settings_page as sp


class FakeClient:
    """Подмена ``yadisk.YaDisk``: сценарий задаётся атрибутами класса."""

    token_ok = True                 # ответ check_token
    token_error = None              # исключение check_token
    existing = set()                # пути, которые есть на Диске
    exists_error = None             # исключение exists
    created = []                    # созданные папки
    init_error = None               # исключение при создании клиента

    def __init__(self, token=None):
        if FakeClient.init_error:
            raise FakeClient.init_error

    def check_token(self):
        if FakeClient.token_error:
            raise FakeClient.token_error
        return FakeClient.token_ok

    def exists(self, path):
        if FakeClient.exists_error:
            raise FakeClient.exists_error
        return path in FakeClient.existing

    def makedirs(self, path):
        FakeClient.created.append(path)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    """Подменяет клиент Диска и сбрасывает сценарий."""
    FakeClient.token_ok = True
    FakeClient.token_error = None
    FakeClient.existing = set()
    FakeClient.exists_error = None
    FakeClient.created = []
    FakeClient.init_error = None
    monkeypatch.setattr(
        ya_dop.yadisk,      # модуль в ya_dop
        'YaDisk',           # класс клиента
        FakeClient,         # подмена
    )
    return FakeClient


# настоящий запуск потока: ждём сигнал, он приходит в очередь событий страницы
def _run_thread(
    thread,   # запущенный поток страницы
) -> None:
    """Ждёт завершения потока, затем обрабатывает его сигнал в очереди событий."""
    assert thread.wait(5000)
    loop = QEventLoop()
    QTimer.singleShot(
        50,         # мс: сигнал уже в очереди
        loop.quit,  # выйти
    )
    loop.exec()


def test_token_valid_shows_information(page, messages):
    """Действительный токен: сообщение об успехе, кнопка снова работает."""
    page.token_edit.setText('  y0_токен ')
    page._check_token()
    assert not page.check_token_btn.isEnabled()
    assert page.check_token_btn.text() == "Проверка..."
    assert page.token_thread.token == 'y0_токен'
    _run_thread(page.token_thread)
    assert messages == [('information', "Результат", "Токен действителен")]
    assert page.check_token_btn.isEnabled()
    assert page.check_token_btn.text() == "Проверить"


def test_token_invalid_shows_warning(page, messages, fake_client):
    """Неверный токен: предупреждение."""
    fake_client.token_ok = False
    page.token_edit.setText('плохой')
    page._check_token()
    _run_thread(page.token_thread)
    assert messages == [('warning', "Результат", "Токен недействителен или нет соединения")]
    assert page.check_token_btn.isEnabled()


def test_token_connection_error_shows_warning(page, messages, fake_client):
    """Обрыв сети при проверке токена: функция Диска не бросает, сообщение есть."""
    fake_client.token_error = yadisk.exceptions.YaDiskConnectionError('нет сети')
    page.token_edit.setText('y0')
    page._check_token()
    _run_thread(page.token_thread)
    assert [kind for kind, _title, _text in messages] == ['warning']
    assert page.check_token_btn.isEnabled()


def test_token_unexpected_error_reaches_message(page, messages, fake_client):
    """Исключение вне функций Диска (клиент не создался) — сообщение, кнопка не залипает."""
    fake_client.init_error = RuntimeError('сломан клиент')
    page.token_edit.setText('y0')
    page._check_token()
    _run_thread(page.token_thread)
    assert len(messages) == 1
    kind, _title, text = messages[0]
    assert kind == 'warning'
    assert 'сломан клиент' in text
    assert page.check_token_btn.isEnabled()
    assert page.check_token_btn.text() == "Проверить"


def test_token_empty_no_thread(page, messages):
    """Пустой токен: предупреждение, поток не запускается."""
    page.token_edit.setText('   ')
    page._check_token()
    assert page.token_thread is None
    assert messages == [('warning', "Ошибка", "Токен не задан.")]
    assert page.check_token_btn.isEnabled()


def test_path_exists(page, messages, fake_client):
    """Папка есть: сообщение об успехе, ничего не создаётся."""
    fake_client.existing = {'Проекты/test/bd'}
    page.token_edit.setText('y0')
    page.remote_path_edit.setText('Проекты/test/bd/')
    page._check_remote_path()
    assert not page.check_path_btn.isEnabled()
    _run_thread(page.path_thread)
    assert messages == [('information', "Результат", "Путь существует")]
    assert fake_client.created == []
    assert page.check_path_btn.isEnabled()
    assert page.check_path_btn.text() == "Проверить наличие папки"


def test_path_missing_created(page, messages, fake_client):
    """Папки нет: создаётся, сообщение об этом."""
    page.token_edit.setText('y0')
    page.remote_path_edit.setText('Новая/папка')
    page._check_remote_path()
    _run_thread(page.path_thread)
    assert fake_client.created == ['Новая/папка']
    assert messages == [('information', "Результат", "Путь успешно создан: Новая/папка")]


def test_path_with_db_file_checks_its_folder(page, messages, fake_client):
    """В поле файл базы (так по умолчанию): создаётся его папка, а не папка с именем файла."""
    page.token_edit.setText('y0')
    page.remote_path_edit.setText('Проекты/test/bd/clinic.db')
    page._check_remote_path()
    _run_thread(page.path_thread)
    assert fake_client.created == ['Проекты/test/bd']


def test_path_bad_token_message(page, messages, fake_client):
    """Неверный токен при проверке папки: предупреждение, ничего не создаётся."""
    fake_client.token_ok = False
    page.token_edit.setText('плохой')
    page.remote_path_edit.setText('Папка')
    page._check_remote_path()
    _run_thread(page.path_thread)
    assert [kind for kind, _title, _text in messages] == ['warning']
    assert fake_client.created == []
    assert page.check_path_btn.isEnabled()


def test_path_disk_error_message(page, messages, fake_client):
    """Ошибка Диска при проверке папки: сообщение с текстом ошибки."""
    fake_client.exists_error = yadisk.exceptions.YaDiskConnectionError('обрыв')
    page.token_edit.setText('y0')
    page.remote_path_edit.setText('Папка')
    page._check_remote_path()
    _run_thread(page.path_thread)
    assert len(messages) == 1
    assert messages[0][0] == 'warning'
    assert 'обрыв' in messages[0][2]
    assert page.check_path_btn.isEnabled()


def test_path_unexpected_error_reaches_message(page, messages, fake_client):
    """Исключение вне функций Диска — сообщение, кнопка не залипает."""
    fake_client.init_error = RuntimeError('сломан клиент')
    page.token_edit.setText('y0')
    page.remote_path_edit.setText('Папка')
    page._check_remote_path()
    _run_thread(page.path_thread)
    assert len(messages) == 1
    assert 'сломан клиент' in messages[0][2]
    assert page.check_path_btn.isEnabled()


@pytest.mark.parametrize('token, path', [('', 'Папка'), ('y0', '')])
def test_path_requires_token_and_path(page, messages, token, path):
    """Нет токена или пути: предупреждение, поток не запускается."""
    page.token_edit.setText(token)
    page.remote_path_edit.setText(path)
    page._check_remote_path()
    assert page.path_thread is None
    assert [kind for kind, _title, _text in messages] == ['warning']


@pytest.mark.parametrize('remote, folder', [
    ('Проекты/test/bd/clinic.db', 'Проекты/test/bd'),
    ('Проекты\\test\\bd\\clinic.SQLITE', 'Проекты/test/bd'),
    ('Проекты/test/bd/', 'Проекты/test/bd'),
    ('/clinic.db', '/'),
    ('clinic.db', '/'),
    ('disk:/a/clinic.db', 'disk:/a'),
    ('/', '/'),
])
def test_remote_folder_of(remote, folder):
    """Папка для пути из настроек; правило «файл базы» — как у remote_db_file_path."""
    assert sp.remote_folder_of(remote) == folder


def test_wait_check_threads_without_threads(page):
    """Проверок не было — ожидание ничего не делает."""
    page.wait_check_threads(timeout_ms=1)


def test_wait_check_threads_waits_running(page, monkeypatch):
    """Идущая проверка: ждём её завершения."""
    import threading

    release = threading.Event()

    def slow_check(token):
        release.wait(5)
        return True

    monkeypatch.setattr(sp, 'check_token', slow_check)
    page.token_edit.setText('y0')
    page._check_token()
    assert page.token_thread.isRunning()
    release.set()
    page.wait_check_threads(timeout_ms=5000)
    assert page.token_thread.isFinished()
