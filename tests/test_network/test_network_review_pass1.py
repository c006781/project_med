# tests/test_network/test_network_review_pass1.py

"""
Тесты исправлений проверки модуля app.network, проход 1 (2026-10-21).

Номера (N1, N2 … T1, P1) — журнал проверок в ``app/network/IMPLEMENTATION.md``.
Сеть не нужна: клиент ``yadisk.YaDisk`` подменяется (фикстура ``disk``).
"""

import doctest
import sys
from typing import List, Tuple
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication, QTimer
from yadisk.exceptions import PathExistsError, YaDiskConnectionError

import app.network as network_package
import app.network.thread_network as thread_module
import app.network.ya_dop as ya_module
from app.network.thread_network import DownloadThread, UploadThread, YaDiskThread
from app.network.ya_dop import (
    DB_EXTENSIONS,
    YaDiskResult,
    check_and_create_path,
    check_remote_file_exists,
    check_token,
    normalize_remote_path,
    remote_db_file_path,
    remote_parent_dir,
    yadisk_download_file,
    yadisk_upload_file,
)


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def disk():
    """
    Подменённый клиент Яндекс.Диска: токен действителен, по пути лежит файл.

    Yields:
        MagicMock: Клиент; тест меняет ``check_token``/``is_file``/``exists`` и т. п.
    """
    client = MagicMock(name='YaDisk')
    client.check_token.return_value = True
    client.is_file.return_value = True
    client.exists.return_value = True
    with patch.object(ya_module.yadisk, 'YaDisk', return_value=client) as factory:
        client.factory = factory
        yield client


@pytest.fixture
def local_db(tmp_path):
    """Локальный файл БД для загрузки."""
    path = tmp_path / 'clinic.db'
    path.write_bytes(b'data')
    return path


@pytest.fixture(scope='module')
def qt_app():
    """QCoreApplication для тестов с настоящим запуском потока."""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    yield app


def _run_thread(
    app: QCoreApplication, # приложение Qt (цикл событий)
    thread: YaDiskThread, # поток для запуска
) -> Tuple[List[int], List[str]]:
    """Запускает поток по-настоящему (start), ждёт и возвращает (finished, error)."""
    finished: List[int] = []
    errors: List[str] = []
    thread.finished.connect(finished.append)
    thread.error.connect(errors.append)
    thread.start()
    thread.wait(5000)
    QTimer.singleShot(50, app.quit) # доставить сигналы из потока
    app.exec()
    return finished, errors


# ---------------------------------------------------------------------------
# N1 — нет сети: check_token бросал YaDiskConnectionError
# ---------------------------------------------------------------------------

def test_n1_download_no_network_returns_code(disk):
    """if_err=False при обрыве сети — код NO_CONNECTION, а не исключение."""
    disk.check_token.side_effect = YaDiskConnectionError('нет сети')
    assert yadisk_download_file('t', '/a.db', 'a.db', if_err=False) == YaDiskResult.NO_CONNECTION


def test_n1_download_no_network_raises_connection_error(disk):
    """if_err=True при обрыве сети — ConnectionError с русским текстом."""
    disk.check_token.side_effect = YaDiskConnectionError('нет сети')
    with pytest.raises(ConnectionError, match='Нет соединения с Яндекс.Диском'):
        yadisk_download_file('t', '/a.db', 'a.db', if_err=True)


def test_n1_upload_no_network_returns_code(disk, local_db):
    """Загрузка при обрыве сети — код NO_CONNECTION."""
    disk.check_token.side_effect = YaDiskConnectionError('нет сети')
    assert yadisk_upload_file('t', str(local_db), '/a.db', if_err=False) == YaDiskResult.NO_CONNECTION


def test_n1_check_token_no_network_false(disk):
    """check_token при обрыве сети — False (экран настроек не «зависает»)."""
    disk.check_token.side_effect = YaDiskConnectionError('нет сети')
    assert check_token('t') is False


def test_n1_check_and_create_path_no_network(disk):
    """check_and_create_path при обрыве сети — (False, текст)."""
    disk.check_token.side_effect = YaDiskConnectionError('нет сети')
    ok, message = check_and_create_path('t', 'Папка')
    assert ok is False
    assert 'Нет соединения' in message


def test_n1_check_remote_file_exists_no_network(disk):
    """check_remote_file_exists при обрыве сети — (False, текст)."""
    disk.check_token.side_effect = YaDiskConnectionError('нет сети')
    ok, message = check_remote_file_exists('t', '/a.db')
    assert ok is False
    assert 'Нет соединения' in message


def test_n1_bad_token_message(disk):
    """Недействительный токен — свой текст (не «нет соединения»)."""
    disk.check_token.return_value = False
    with pytest.raises(ConnectionError, match='Токен Яндекс.Диска недействителен'):
        yadisk_download_file('t', '/a.db', 'a.db', if_err=True)


def test_n1_network_error_during_exists_returns_failed(disk):
    """Сеть оборвалась после проверки токена (на exists) — FAILED, не исключение."""
    disk.is_file.side_effect = YaDiskConnectionError('обрыв')
    assert yadisk_download_file('t', '/a.db', 'a.db', if_err=False) == YaDiskResult.FAILED


def test_n1_network_error_during_exists_raises_when_if_err(disk):
    """То же при if_err=True — исходное исключение библиотеки."""
    disk.is_file.side_effect = YaDiskConnectionError('обрыв')
    with pytest.raises(YaDiskConnectionError):
        yadisk_download_file('t', '/a.db', 'a.db', if_err=True)


# ---------------------------------------------------------------------------
# N2 — клиент закрывается после каждой операции
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'call',
    [
        lambda: yadisk_download_file('t', '/a.db', 'a.db'),
        lambda: check_token('t'),
        lambda: check_and_create_path('t', 'Папка'),
        lambda: check_remote_file_exists('t', '/a.db'),
    ],
    ids=['download', 'check_token', 'check_and_create_path', 'check_remote_file_exists'],
)
def test_n2_client_closed(disk, tmp_path, monkeypatch, call):
    """Каждая операция закрывает клиент (HTTP-сессию)."""
    monkeypatch.chdir(tmp_path)
    call()
    disk.close.assert_called_once()


def test_n2_client_closed_upload(disk, local_db):
    """Загрузка закрывает клиент."""
    yadisk_upload_file('t', str(local_db), '/a.db')
    disk.close.assert_called_once()


def test_n2_client_closed_on_exception(disk):
    """Клиент закрывается и при исключении (if_err=True)."""
    disk.is_file.return_value = False
    disk.exists.return_value = False
    with pytest.raises(FileNotFoundError):
        yadisk_download_file('t', '/a.db', 'a.db', if_err=True)
    disk.close.assert_called_once()


def test_n2_client_created_with_token(disk):
    """Клиент создаётся с переданным токеном."""
    check_token('мой-токен')
    disk.factory.assert_called_once_with(token='мой-токен')


# ---------------------------------------------------------------------------
# N3 — пути на Диске
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'raw, expected',
    [
        ('Папка\\база\\', 'Папка/база'),  # путь из Windows
        ('/a//b/', '/a/b'),               # повторные и завершающий '/'
        ('a/b', 'a/b'),                   # без начального '/' — как есть
        ('disk:/a/', 'disk:/a'),          # схема сохраняется
        ('disk:', 'disk:/'),              # корень со схемой
        ('/', '/'),                       # корень
        ('', ''),                         # пусто
        (None, ''),                       # не задано
    ],
)
def test_n3_normalize_remote_path(raw, expected):
    """normalize_remote_path для разных написаний."""
    assert normalize_remote_path(raw) == expected


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('/Папка/база/clinic.db', '/Папка/база'),
        ('Папка\\clinic.db', 'Папка'),
        ('Папка/clinic.db', 'Папка'),
        ('/clinic.db', None),
        ('clinic.db', None),
        ('disk:/clinic.db', None),
        ('disk:/a/clinic.db', 'disk:/a'),
    ],
)
def test_n3_remote_parent_dir(raw, expected):
    """remote_parent_dir: папка файла; None — файл в корне."""
    assert remote_parent_dir(raw) == expected


def test_n3_download_normalizes_backslashes(disk, tmp_path):
    """Скачивание передаёт в библиотеку путь с '/'."""
    local = tmp_path / 'a.db'
    yadisk_download_file('t', 'Папка\\a.db', str(local))
    assert disk.download.call_args.args[0] == 'Папка/a.db'


def test_n3_upload_normalizes_and_creates_parent(disk, local_db):
    """Загрузка: путь с '/' и папка-родитель с '/'."""
    disk.exists.return_value = False
    yadisk_upload_file('t', str(local_db), 'Папка\\база\\a.db')
    disk.makedirs.assert_called_once_with('Папка/база')
    assert disk.upload.call_args.args[1] == 'Папка/база/a.db'


def test_n3_upload_to_root_no_makedirs(disk, local_db):
    """Файл в корне Диска — папки не создаются."""
    disk.exists.return_value = False
    yadisk_upload_file('t', str(local_db), '/a.db')
    disk.makedirs.assert_not_called()


def test_n3_check_and_create_path_normalizes(disk):
    """check_and_create_path: путь с '/'."""
    disk.exists.return_value = False
    check_and_create_path('t', 'Папка\\база')
    disk.makedirs.assert_called_once_with('Папка/база')


# ---------------------------------------------------------------------------
# P1 — путь к файлу БД (перенесён из SyncService)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'remote, local, expected',
    [
        ('Папка/база', './clinic.db', 'Папка/база/clinic.db'),
        ('Папка/база/', './clinic.db', 'Папка/база/clinic.db'),
        ('Папка\\база\\', 'C:\\data\\clinic.db', 'Папка/база/clinic.db'),  # Windows
        ('/Папка/main.sqlite', './clinic.db', '/Папка/main.sqlite'),
        ('/Папка/main.SQLITE3', './clinic.db', '/Папка/main.SQLITE3'),
        ('/Папка/main.DB', './clinic.db', '/Папка/main.DB'),
        ('', './clinic.db', '/clinic.db'),
        (None, './clinic.db', '/clinic.db'),
        ('/', './clinic.db', '/clinic.db'),
        ('disk:/', './clinic.db', 'disk:/clinic.db'),
        ('Папка', 'clinic.db', 'Папка/clinic.db'),
    ],
)
def test_p1_remote_db_file_path(remote, local, expected):
    """remote_db_file_path для разных настроек."""
    assert remote_db_file_path(remote, local) == expected


def test_p1_db_extensions():
    """Расширения файла БД."""
    assert DB_EXTENSIONS == ('.db', '.sqlite', '.sqlite3')


def test_p1_sync_service_uses_network_helper():
    """SyncService берёт функцию из app.network (одна реализация на всё приложение)."""
    import app.services.sync_service as sync_module
    assert sync_module.remote_db_file_path is remote_db_file_path
    assert sync_module.DB_EXTENSIONS is DB_EXTENSIONS


# ---------------------------------------------------------------------------
# N4 — коды результата и тексты
# ---------------------------------------------------------------------------

def test_n4_codes_compatible_with_old_numbers():
    """Прежние числа не изменились."""
    assert (YaDiskResult.OK, YaDiskResult.NO_CONNECTION, YaDiskResult.NOT_FOUND, YaDiskResult.FAILED) == (0, -1, -2, -3)


def test_n4_every_code_has_message():
    """У каждого кода есть русский текст."""
    for code in YaDiskResult:
        assert code.message
        assert code.message != code.name


@pytest.mark.parametrize('code', [0, -1, -2, -3, -4, -5])
def test_n4_describe_known(code):
    """describe для известных кодов — текст message."""
    assert YaDiskResult.describe(code) == YaDiskResult(code).message


def test_n4_describe_unknown():
    """describe для неизвестного кода — без исключения."""
    assert YaDiskResult.describe(7) == 'Неизвестный код 7'


def test_n4_functions_return_enum(disk, tmp_path):
    """Функции возвращают YaDiskResult (int)."""
    result = yadisk_download_file('t', '/a.db', str(tmp_path / 'a.db'))
    assert isinstance(result, YaDiskResult)
    assert isinstance(result, int)


def test_n4_messages_russian_download_missing(disk):
    """Нет файла на Диске — русский текст исключения."""
    disk.is_file.return_value = False
    disk.exists.return_value = False
    with pytest.raises(FileNotFoundError, match='не найден на Яндекс.Диске'):
        yadisk_download_file('t', '/a.db', 'a.db', if_err=True)


def test_n4_messages_russian_upload_local_missing(tmp_path):
    """Нет локального файла — русский текст исключения (клиент не создаётся)."""
    with patch.object(ya_module.yadisk, 'YaDisk') as factory:
        with pytest.raises(FileNotFoundError, match='Локальный файл'):
            yadisk_upload_file('t', str(tmp_path / 'нет.db'), '/a.db', if_err=True)
        factory.assert_not_called()


# ---------------------------------------------------------------------------
# N5 — скачивание папки
# ---------------------------------------------------------------------------

def test_n5_download_dir_returns_not_a_file(disk, tmp_path):
    """Путь на Диске — папка: NOT_A_FILE, скачивания нет."""
    disk.is_file.return_value = False
    disk.exists.return_value = True
    assert yadisk_download_file('t', '/Папка', str(tmp_path / 'a.db')) == YaDiskResult.NOT_A_FILE
    disk.download.assert_not_called()


def test_n5_download_dir_raises_is_a_directory(disk):
    """То же при if_err=True — IsADirectoryError."""
    disk.is_file.return_value = False
    disk.exists.return_value = True
    with pytest.raises(IsADirectoryError, match='к папке'):
        yadisk_download_file('t', '/Папка', 'a.db', if_err=True)


def test_n5_check_remote_file_exists_dir(disk):
    """check_remote_file_exists: папка — (False, текст про папку)."""
    disk.is_file.return_value = False
    disk.exists.return_value = True
    assert check_remote_file_exists('t', '/Папка') == (False, YaDiskResult.NOT_A_FILE.message)


def test_n5_check_remote_file_exists_file(disk):
    """check_remote_file_exists: файл — (True, ...)."""
    assert check_remote_file_exists('t', '/a.db') == (True, 'Файл существует')


def test_n5_check_remote_file_exists_missing(disk):
    """check_remote_file_exists: ничего нет — (False, текст с путём)."""
    disk.is_file.return_value = False
    disk.exists.return_value = False
    ok, message = check_remote_file_exists('t', '/a.db')
    assert ok is False
    assert '/a.db' in message


def test_n5_check_remote_file_exists_request_error(disk):
    """check_remote_file_exists: сбой запроса — (False, текст), без исключения."""
    disk.is_file.side_effect = RuntimeError('сбой')
    ok, message = check_remote_file_exists('t', '/a.db')
    assert ok is False
    assert 'сбой' in message


def test_n5_local_fs_error_returns_failed(disk, tmp_path):
    """
    Ошибка локальной ФС при if_err=False (в т. ч. FileNotFoundError от download) — FAILED,
    а не исключение (не путается с «нет файла на Диске»).
    """
    disk.download.side_effect = FileNotFoundError('локально')
    assert yadisk_download_file('t', '/a.db', str(tmp_path / 'a.db')) == YaDiskResult.FAILED


def test_n5_local_fs_error_raises_when_if_err(disk, tmp_path):
    """То же при if_err=True — исходное исключение."""
    disk.download.side_effect = PermissionError('занято')
    with pytest.raises(PermissionError):
        yadisk_download_file('t', '/a.db', str(tmp_path / 'a.db'), if_err=True)


def test_n5_download_creates_local_dir(disk, tmp_path):
    """Скачивание создаёт локальную папку."""
    target = tmp_path / 'новая' / 'вложенная' / 'a.db'
    assert yadisk_download_file('t', '/a.db', str(target)) == YaDiskResult.OK
    assert target.parent.is_dir()


def test_n5_download_passes_progress(disk, tmp_path):
    """Колбэк прогресса передаётся в библиотеку."""
    callback = MagicMock()
    yadisk_download_file('t', '/a.db', str(tmp_path / 'a.db'), progress_callback=callback)
    assert disk.download.call_args.kwargs['progress_callback'] is callback


# ---------------------------------------------------------------------------
# N6 — файл на Диске уже есть
# ---------------------------------------------------------------------------

def test_n6_upload_exists_returns_code(disk, local_db):
    """overwrite=False, файл есть — ALREADY_EXISTS."""
    disk.upload.side_effect = PathExistsError()
    assert yadisk_upload_file('t', str(local_db), '/a.db') == YaDiskResult.ALREADY_EXISTS


def test_n6_upload_exists_raises_file_exists(disk, local_db):
    """То же при if_err=True — FileExistsError с текстом."""
    disk.upload.side_effect = PathExistsError()
    with pytest.raises(FileExistsError, match='уже есть'):
        yadisk_upload_file('t', str(local_db), '/a.db', if_err=True)


def test_n6_upload_overwrite_passed(disk, local_db):
    """overwrite передаётся в библиотеку."""
    yadisk_upload_file('t', str(local_db), '/a.db', overwrite=True)
    assert disk.upload.call_args.kwargs['overwrite'] is True


def test_n6_upload_other_error_failed(disk, local_db):
    """Прочая ошибка загрузки — FAILED."""
    disk.upload.side_effect = RuntimeError('нет места')
    assert yadisk_upload_file('t', str(local_db), '/a.db') == YaDiskResult.FAILED


def test_n6_upload_other_error_raises(disk, local_db):
    """Прочая ошибка при if_err=True — исходное исключение."""
    disk.upload.side_effect = RuntimeError('нет места')
    with pytest.raises(RuntimeError, match='нет места'):
        yadisk_upload_file('t', str(local_db), '/a.db', if_err=True)


def test_check_and_create_path_exists(disk):
    """Папка есть — (True, 'Путь существует'), ничего не создаётся."""
    assert check_and_create_path('t', 'Папка') == (True, 'Путь существует')
    disk.makedirs.assert_not_called()


def test_check_and_create_path_error(disk):
    """Ошибка создания — (False, текст)."""
    disk.exists.return_value = False
    disk.makedirs.side_effect = RuntimeError('запрещено')
    ok, message = check_and_create_path('t', 'Папка')
    assert ok is False
    assert 'запрещено' in message


def test_check_token_valid(disk):
    """Токен действителен — True."""
    assert check_token('t') is True


# ---------------------------------------------------------------------------
# T1 — потоки
# ---------------------------------------------------------------------------

def test_t1_threads_share_base():
    """Оба потока — наследники YaDiskThread."""
    assert issubclass(DownloadThread, YaDiskThread)
    assert issubclass(UploadThread, YaDiskThread)


def test_t1_base_operation_not_implemented():
    """Базовый поток без _operation — ошибка в сигнал error, не падение."""
    thread = YaDiskThread('t')
    errors: List[str] = []
    thread.error.connect(errors.append)
    thread.run()
    assert errors and 'не реализован' in errors[0]


def test_t1_custom_thread_extension():
    """Новая операция — один метод _operation."""
    class EchoThread(YaDiskThread):
        def _operation(self) -> int:
            return YaDiskResult.NOT_A_FILE

    thread = EchoThread('t')
    finished: List[int] = []
    thread.finished.connect(finished.append)
    thread.run()
    assert finished == [-4]


def test_t1_download_no_extra_requests(disk, tmp_path):
    """Скачивание через поток: токен проверяется один раз (раньше — дважды)."""
    thread = DownloadThread('t', '/a.db', str(tmp_path / 'a.db'))
    finished: List[int] = []
    thread.finished.connect(finished.append)
    thread.run()
    assert finished == [0] # скачивание дошло до конца (не отказ на проверке)
    disk.download.assert_called_once()
    assert disk.check_token.call_count == 1
    assert disk.factory.call_count == 1


def test_t1_download_thread_finished_code(disk, tmp_path):
    """Успех — finished(0)."""
    thread = DownloadThread('t', '/a.db', str(tmp_path / 'a.db'))
    finished: List[int] = []
    thread.finished.connect(finished.append)
    thread.run()
    assert finished == [0]


def test_t1_download_thread_dir_error_text(disk, tmp_path):
    """Папка вместо файла — error с понятным текстом."""
    disk.is_file.return_value = False
    thread = DownloadThread('t', '/Папка', str(tmp_path / 'a.db'))
    errors: List[str] = []
    thread.error.connect(errors.append)
    thread.run()
    assert errors and 'к папке' in errors[0]


def test_t1_upload_thread_passes_overwrite(disk, local_db):
    """UploadThread передаёт overwrite."""
    UploadThread('t', str(local_db), '/a.db', overwrite=True).run()
    assert disk.upload.call_args.kwargs['overwrite'] is True


def test_t1_upload_thread_default_overwrite_false():
    """UploadThread по умолчанию не перезаписывает."""
    assert UploadThread('t', 'a', 'b').overwrite is False


def test_t1_empty_exception_text_replaced():
    """Исключение без текста — в error имя типа (не пустая строка)."""
    with patch.object(thread_module, 'yadisk_download_file', side_effect=ConnectionError()):
        thread = DownloadThread('t', '/a.db', 'a.db')
        errors: List[str] = []
        thread.error.connect(errors.append)
        thread.run()
    assert errors == ['ConnectionError']


def test_t1_progress_signal(disk, tmp_path):
    """Колбэк прогресса потока → сигнал progress."""
    thread = DownloadThread('t', '/a.db', str(tmp_path / 'a.db'))
    progress: List[Tuple[int, int]] = []
    thread.progress.connect(lambda current, total: progress.append((current, total)))
    thread._progress_callback(5, 10)
    assert progress == [(5, 10)]


def test_finished_signal_emitted_once_with_code(qt_app, disk, tmp_path):
    """
    Настоящий запуск потока: подключённый к finished обработчик вызывается ровно один раз
    и с кодом — встроенный QThread.finished() без аргументов в него не попадает.
    """
    thread = DownloadThread('t', '/a.db', str(tmp_path / 'a.db'))
    finished, errors = _run_thread(qt_app, thread)
    assert finished == [0]
    assert errors == []


def test_error_signal_real_thread(qt_app, disk, tmp_path):
    """Настоящий запуск потока с ошибкой — один error, без finished."""
    disk.check_token.return_value = False
    thread = DownloadThread('t', '/a.db', str(tmp_path / 'a.db'))
    finished, errors = _run_thread(qt_app, thread)
    assert finished == []
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# Документация — примеры в докстрингах исполняются
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('module', [ya_module, thread_module, network_package])
def test_doctests(module):
    """Примеры (>>>) в докстрингах модуля верны."""
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.failed == 0


def test_public_api_exported():
    """Публичный API пакета доступен из app.network."""
    for name in network_package.__all__:
        assert hasattr(network_package, name), name
