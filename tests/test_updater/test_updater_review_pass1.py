# tests/test_updater/test_updater_review_pass1.py

"""
Тесты исправлений проверки модуля app.updater, проход 1 (2026-10-21).

Номера (U1 …) — журнал проверок в ``app/UPDATER.md``. Сеть не нужна: ``urlopen`` и
``requests.get`` подменяются.
"""

import doctest
import io
import json
import urllib.error
from typing import List
from unittest.mock import MagicMock, patch

import pytest
import requests

import app.updater as updater
from app.updater import (
    ASSET_RULES,
    AUTO_UPDATE_SYSTEMS,
    AppUpdater,
    UpdateApplier,
    UpdateChecker,
    UpdateDownloader,
    auto_update_unavailable_reason,
    build_windows_update_script,
    github_headers,
    is_newer_version,
    mask_token,
    normalize_version,
    parse_version,
    select_release_asset,
    update_file_name,
)

SECRET = 'ghp_SECRETSECRETSECRET'


# ---------------------------------------------------------------------------
# U4 — сравнение версий
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'current, latest, expected',
    [
        ('2.0', '1.5', False),        # старая версия — не обновление (было True)
        ('1.2.0', '1.1.9', False),    # было True
        ('1.0', '1.0.0', False),      # одна версия (было True)
        ('1.0.0', '1.0', False),
        ('1.0', '1.0', False),
        ('1.0', '1.0.1', True),
        ('1.9', '1.10', True),        # по числам, не по строкам
        ('1.10', '1.9', False),
        ('1.0.0', 'v1.0.1', True),    # тег с 'v'
        ('1.0.0', 'V2', True),
        ('1.0', 'beta', False),       # непонятный номер — не обновление
        ('1.0', '1.1-beta', False),
        ('1.0', '', False),
        ('кривая', '2.0', False),
    ],
)
def test_u4_is_newer_version(current, latest, expected):
    """is_newer_version для разных пар."""
    assert is_newer_version(current, latest) is expected


def test_u4_old_name_delegates():
    """UpdateChecker._parse_version (прежнее имя) — та же логика."""
    assert UpdateChecker._parse_version('2.0', '1.5') is False
    assert UpdateChecker._parse_version('1.0', '1.1') is True


@pytest.mark.parametrize(
    'raw, expected',
    [('v1.2.3', '1.2.3'), ('V1', '1'), (' 1.0 ', '1.0'), ('', ''), (None, ''), ('1.0', '1.0')],
)
def test_u4_normalize_version(raw, expected):
    """normalize_version убирает 'v' и пробелы."""
    assert normalize_version(raw) == expected


@pytest.mark.parametrize(
    'raw, expected',
    [('1.2.0', (1, 2)), ('1.0.0', (1,)), ('0', (0,)), ('10.01', (10, 1)), ('1.', None), ('1..2', None), ('a', None)],
)
def test_u4_parse_version(raw, expected):
    """parse_version: числа, завершающие нули, ошибочные номера."""
    assert parse_version(raw) == expected


def test_u4_process_response_uses_tag(monkeypatch):
    """_process_response: версия из тега без 'v', сравнение по числам."""
    checker = UpdateChecker('2.0', 'o/r')
    has_update, version, url, data = checker._process_response({'tag_name': 'v1.5', 'html_url': 'h'})
    assert (has_update, version, url) == (False, '1.5', 'h')


# ---------------------------------------------------------------------------
# U7 — токен в журнале
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'token, expected',
    [('ghp_1234567890', 'ghp_…(14)'), ('', 'EMPTY'), (None, 'EMPTY'), ('  ', 'EMPTY'), ('ab', 'ab…(2)')],
)
def test_u7_mask_token(token, expected):
    """mask_token: начало и длина, без самого токена."""
    assert mask_token(token) == expected


def _logged_text(logger: MagicMock) -> str:
    """Все сообщения, переданные подменённому логгеру."""
    return ' '.join(str(arg) for call in logger.method_calls for arg in call.args)


def test_u7_checker_does_not_log_token():
    """UpdateChecker не пишет токен в журнал."""
    checker = UpdateChecker('1.0', 'o/r')
    checker.logger = MagicMock()
    request = checker._build_request(SECRET)
    assert request.get_header('Authorization') == f'token {SECRET}'
    assert SECRET not in _logged_text(checker.logger)


def test_u7_checker_get_token_not_logged():
    """_get_token не пишет токен в журнал."""
    checker = UpdateChecker('1.0', 'o/r')
    checker.logger = MagicMock()
    with patch('app.config.conf.getenv.get_getenv', return_value=SECRET):
        assert checker._get_token() == SECRET
    assert SECRET not in _logged_text(checker.logger)


def test_u7_downloader_does_not_log_token():
    """UpdateDownloader не пишет токен в журнал."""
    downloader = UpdateDownloader('u', '/tmp/x', SECRET)
    downloader.logger = MagicMock()
    headers = downloader._get_headers()
    assert headers['Authorization'] == f'token {SECRET}'
    assert headers['Accept'] == 'application/octet-stream'
    assert SECRET not in _logged_text(downloader.logger)


@pytest.mark.parametrize('token', [None, '', '   '])
def test_u7_github_headers_without_token(token):
    """Без токена — без Authorization."""
    headers = github_headers(token, 'application/json')
    assert 'Authorization' not in headers
    assert headers['Accept'] == 'application/json'
    assert headers['User-Agent']


def test_u7_github_headers_strips_token():
    """Пробелы вокруг токена убираются."""
    assert github_headers(' t ', 'a')['Authorization'] == 'token t'


# ---------------------------------------------------------------------------
# U2/U3 — выбор файла релиза и имя файла
# ---------------------------------------------------------------------------

ASSETS = [
    {'name': 'Source.zip', 'url': 'zip'},
    {'name': 'MedicalApp-Linux.tar.gz', 'url': 'linux'},
    {'name': 'MedicalApp.EXE', 'url': 'exe'},
]


@pytest.mark.parametrize(
    'system, expected',
    [('windows', 'exe'), ('linux', 'linux'), ('darwin', None), ('', None)],
)
def test_u3_select_release_asset(system, expected):
    """select_release_asset по ОС (регистр имени не важен)."""
    asset = select_release_asset(ASSETS, system)
    assert (asset['url'] if asset else None) == expected


def test_u3_select_release_asset_keyword_first():
    """Слово ОС в имени — подходящий файл (первый подходящий по порядку)."""
    assets = [{'name': 'app-windows.zip', 'url': 'kw'}, {'name': 'app.exe', 'url': 'exe'}]
    assert select_release_asset(assets, 'windows')['url'] == 'kw'


def test_u3_select_release_asset_no_name_and_empty():
    """Файл без имени и пустой список — без ошибок."""
    assert select_release_asset([{'url': 'x'}], 'windows') is None
    assert select_release_asset([], 'linux') is None


def test_u3_select_release_asset_accepts_generator():
    """Итератор (не список) тоже подходит — запасной проход не теряет элементы."""
    assets = iter([{'name': 'a.tar.gz', 'url': 'u'}])
    assert select_release_asset(assets, 'linux')['url'] == 'u'


@pytest.mark.parametrize(
    'system, expected',
    [('windows', 'MedicalApp_new_5.exe'), ('linux', 'MedicalApp_new_5.tar.gz'), ('darwin', 'MedicalApp_new_5')],
)
def test_u2_update_file_name(system, expected):
    """Расширение файла обновления — по ОС (на Linux было .exe)."""
    assert update_file_name(system, 5) == expected


def test_u2_rules_cover_extensions():
    """Для каждой ОС из правил выбора файла есть расширение."""
    assert set(ASSET_RULES) <= set(updater.UPDATE_FILE_EXTENSIONS)
    assert AUTO_UPDATE_SYSTEMS <= set(ASSET_RULES)


# ---------------------------------------------------------------------------
# U1/U5 — установка только где она возможна, проверка ДО скачивания
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'system, frozen, expect_none',
    [('windows', True, True), ('windows', False, False), ('linux', True, False), ('linux', False, False), ('', True, False)],
)
def test_u1_auto_update_unavailable_reason(system, frozen, expect_none):
    """Причина невозможности установки."""
    assert (auto_update_unavailable_reason(system, frozen) is None) is expect_none


def test_u1_reason_mentions_release_page_on_linux():
    """На Linux — понятный текст со ссылкой на страницу релиза."""
    assert 'страницы релиза' in auto_update_unavailable_reason('linux', True)


def _applier(release=None):
    """UpdateApplier с собранными ошибками."""
    applier = UpdateApplier(release or {'assets': ASSETS})
    errors: List[str] = []
    applier.error.connect(errors.append)
    return applier, errors


def test_u5_not_frozen_error_before_download():
    """Из исходников — ошибка сразу, скачивание не начинается (раньше — после скачивания)."""
    applier, errors = _applier()
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater.sys, 'frozen', False, create=True):
        applier.start()
    downloader_cls.assert_not_called()
    assert errors == ['Автообновление работает только в собранном приложении']


def test_u1_linux_error_before_download():
    """Собранная программа на Linux — ошибка до скачивания (раньше — AttributeError после)."""
    applier, errors = _applier()
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='linux'):
        applier.start()
    downloader_cls.assert_not_called()
    assert len(errors) == 1 and 'только для Windows' in errors[0]


def test_u1_windows_no_asset_error():
    """Windows, в релизе нет exe — ошибка, без скачивания."""
    applier, errors = _applier({'assets': [{'name': 'a.tar.gz', 'url': 'u'}]})
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='windows'), \
         patch('app.config.conf.getenv.get_getenv', return_value=''):
        applier.start()
    downloader_cls.assert_not_called()
    assert errors == ['Не найден подходящий файл обновления для вашей ОС']


def test_u1_windows_starts_download(tmp_path):
    """Windows, exe собран — скачивание файла .exe рядом с программой."""
    applier, errors = _applier()
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='windows'), \
         patch.object(updater, 'get_app_dir', return_value=str(tmp_path)), \
         patch('app.config.conf.getenv.get_getenv', return_value=SECRET):
        applier.start()
    assert errors == []
    url, path, token = downloader_cls.call_args.args
    assert url == 'exe'
    assert path.startswith(str(tmp_path)) and path.endswith('.exe')
    assert token == SECRET
    downloader_cls.return_value.start.assert_called_once()


def test_u1_apply_update_on_linux_no_attribute_error(tmp_path):
    """_apply_update не на Windows — сообщение, а не AttributeError (STARTUPINFO)."""
    applier, errors = _applier()
    applier._downloaded_file = str(tmp_path / 'new.exe')
    with patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='linux'):
        applier._apply_update()
    assert len(errors) == 1


def test_u1_apply_update_missing_file():
    """Скачанного файла нет — 'Новый файл не найден'."""
    applier, errors = _applier()
    applier._downloaded_file = '/нет/такого.exe'
    with patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='windows'):
        applier._apply_update()
    assert errors == ['Новый файл не найден']


def test_u1_is_running():
    """is_running: нет потока — False; поток работает — True."""
    applier, _ = _applier()
    assert applier.is_running() is False
    applier._downloader = MagicMock()
    applier._downloader.isRunning.return_value = True
    assert applier.is_running() is True


# ---------------------------------------------------------------------------
# U6 — скачивание: неполный файл, временный файл, закрытие ответа
# ---------------------------------------------------------------------------

def _response(data: bytes, length=None, status_error=None):
    """Подменённый ответ requests с потоком data."""
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.headers = {'content-length': str(len(data) if length is None else length)}
    response.raw = io.BytesIO(data)
    if status_error:
        response.raise_for_status.side_effect = status_error
    return response


def _run_downloader(tmp_path, response, token=None, side_effect=None):
    """Запуск UpdateDownloader.run с подменённым requests.get."""
    target = tmp_path / 'sub' / 'MedicalApp_new_1.exe'
    downloader = UpdateDownloader('https://x/asset', str(target), token)
    downloader.logger = MagicMock()
    finished: List[str] = []
    errors: List[str] = []
    progress: List[tuple] = []
    downloader.finished.connect(finished.append)
    downloader.error.connect(errors.append)
    downloader.progress.connect(lambda c, t: progress.append((c, t)))
    with patch.object(updater.requests, 'get', return_value=response, side_effect=side_effect) as get:
        downloader.run()
    return target, finished, errors, progress, get


def test_u6_download_success(tmp_path):
    """Успех: файл записан, .part нет, finished(путь), прогресс до конца."""
    data = b'x' * 1000
    target, finished, errors, progress, _ = _run_downloader(tmp_path, _response(data))
    assert errors == []
    assert finished == [str(target)]
    assert target.read_bytes() == data
    assert not (tmp_path / 'sub' / 'MedicalApp_new_1.exe.part').exists()
    assert progress[-1] == (1000, 1000)


def test_u6_download_incomplete_is_error(tmp_path):
    """Сервер прислал меньше Content-Length — ошибка, файла нет (недокачанный exe не запустится)."""
    target, finished, errors, _, _ = _run_downloader(tmp_path, _response(b'x' * 10, length=100))
    assert finished == []
    assert len(errors) == 1 and 'не полностью' in errors[0]
    assert not target.exists()
    assert not (tmp_path / 'sub' / 'MedicalApp_new_1.exe.part').exists()


def test_u6_download_unknown_size_ok(tmp_path):
    """Размер неизвестен (Content-Length 0) — скачанное принимается."""
    response = _response(b'abc')
    response.headers = {}
    target, finished, errors, _, _ = _run_downloader(tmp_path, response)
    assert finished == [str(target)] and target.read_bytes() == b'abc'


def test_u6_download_http_error(tmp_path):
    """HTTP-ошибка — error, файла нет."""
    response = _response(b'', status_error=requests.HTTPError('404 Not Found'))
    target, finished, errors, _, _ = _run_downloader(tmp_path, response)
    assert finished == [] and errors == ['404 Not Found']
    assert not target.exists()


def test_u6_download_connection_error_text(tmp_path):
    """Нет соединения — понятный текст."""
    _, finished, errors, _, _ = _run_downloader(
        tmp_path, None, side_effect=requests.exceptions.ConnectionError('нет сети'))
    assert finished == []
    assert errors and errors[0].startswith('Нет соединения с сервером обновлений')


def test_u6_download_keeps_existing_target_on_error(tmp_path):
    """Ошибка скачивания не портит уже лежащий файл с тем же именем."""
    target = tmp_path / 'sub' / 'MedicalApp_new_1.exe'
    target.parent.mkdir()
    target.write_bytes(b'old')
    _run_downloader(tmp_path, _response(b'x', length=5))
    assert target.read_bytes() == b'old'


def test_u6_download_response_closed(tmp_path):
    """Ответ закрывается (контекстный менеджер)."""
    response = _response(b'abc')
    _run_downloader(tmp_path, response)
    response.__exit__.assert_called_once()


@pytest.mark.parametrize('token, verify_is_false', [(None, False), ('', False), (SECRET, True)])
def test_u6_verify_param(tmp_path, token, verify_is_false):
    """Публичный — проверка сертификата certifi; приватный — без проверки (ТД-4, как было)."""
    _, _, _, _, get = _run_downloader(tmp_path, _response(b'a'), token=token)
    verify = get.call_args.kwargs['verify']
    assert (verify is False) is verify_is_false
    if not verify_is_false:
        assert verify == updater.certifi.where()


def test_u6_downloader_signals_stream_and_timeout(tmp_path):
    """Запрос — потоком, с таймаутами."""
    _, _, _, _, get = _run_downloader(tmp_path, _response(b'a'))
    assert get.call_args.kwargs['stream'] is True
    assert get.call_args.kwargs['timeout'] == (5, 120)


# ---------------------------------------------------------------------------
# U8 — AppUpdater
# ---------------------------------------------------------------------------

def test_u8_check_finished_sets_pending_and_emits():
    """Есть обновление — pending_release_data и update_available(tag, url)."""
    app_updater = AppUpdater()
    got = []
    app_updater.update_available.connect(lambda tag, url: got.append((tag, url)))
    release = {'tag_name': 'v2.0', 'html_url': 'h'}
    app_updater._on_check_finished(True, release)
    assert got == [('v2.0', 'h')]
    assert app_updater.pending_release_data is release


def test_u8_check_finished_missing_keys_no_keyerror():
    """В ответе нет tag_name/html_url — без KeyError."""
    app_updater = AppUpdater()
    got = []
    app_updater.update_available.connect(lambda tag, url: got.append((tag, url)))
    app_updater._on_check_finished(True, {})
    assert got == [('', '')]


def test_u8_no_update_clears_pending():
    """Обновления нет — pending сбрасывается, no_update."""
    app_updater = AppUpdater()
    app_updater._pending_release_data = {'x': 1}
    calls = []
    app_updater.no_update.connect(lambda: calls.append(1))
    app_updater._on_check_finished(False, {})
    assert calls == [1]
    assert app_updater.pending_release_data is None


def test_u8_pending_none_initially():
    """До проверки — None (раньше атрибута не было — окно проверяло hasattr)."""
    assert AppUpdater().pending_release_data is None


def test_u9_download_update_passes_file_path(tmp_path):
    """download_update: путём файла — файл в папке обновлений (раньше — сама папка)."""
    app_updater = AppUpdater()
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater, 'get_app_dir', return_value=str(tmp_path)), \
         patch.object(updater, 'current_system', return_value='windows'):
        app_updater.download_update('https://x/a')
    url, path = downloader_cls.call_args.args
    assert path.startswith(str(tmp_path / 'MedicalAppUpdates'))
    assert path.endswith('.exe')


def test_u8_apply_from_release_no_double_start():
    """Повторный запуск во время скачивания — второго UpdateApplier нет."""
    app_updater = AppUpdater()
    with patch.object(updater, 'UpdateApplier') as applier_cls:
        applier_cls.return_value.is_running.return_value = True
        app_updater.apply_update_from_release({})
        app_updater.apply_update_from_release({})
    assert applier_cls.call_count == 1


def test_u8_apply_from_release_connects_signals():
    """Прогресс и ошибки applier → сигналы AppUpdater."""
    app_updater = AppUpdater()
    errors = []
    app_updater.download_error.connect(errors.append)
    with patch.object(updater, 'current_system', return_value='windows'), \
         patch.object(updater.sys, 'frozen', False, create=True):
        app_updater.apply_update_from_release({'assets': ASSETS})
    assert errors == ['Автообновление работает только в собранном приложении']


# ---------------------------------------------------------------------------
# UpdateChecker.run
# ---------------------------------------------------------------------------

def _run_checker(current, payload=None, side_effect=None):
    """UpdateChecker.run с подменённым urlopen."""
    checker = UpdateChecker(current, 'o/r')
    checker.logger = MagicMock()
    finished, errors = [], []
    checker.finished.connect(lambda has, data: finished.append((has, data)))
    checker.error.connect(errors.append)
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(payload).encode('utf-8')
    with patch.object(updater.urllib.request, 'urlopen', return_value=response, side_effect=side_effect), \
         patch('app.config.conf.getenv.get_getenv', return_value=''):
        checker.run()
    return finished, errors


def test_checker_run_update_found():
    """Новее — finished(True, релиз)."""
    finished, errors = _run_checker('1.0', {'tag_name': 'v1.1', 'html_url': 'h'})
    assert errors == [] and finished[0][0] is True


def test_checker_run_older_release_no_update():
    """Релиз старее текущей — finished(False, …) (раньше True)."""
    finished, errors = _run_checker('2.0', {'tag_name': 'v1.5'})
    assert finished[0][0] is False


def test_checker_run_http_error():
    """HTTP-ошибка — error с кодом."""
    error = urllib.error.HTTPError('u', 404, 'Not Found', {}, None)
    finished, errors = _run_checker('1.0', side_effect=error)
    assert finished == [] and '404' in errors[0]


def test_checker_run_not_dict():
    """Ответ не объект (список) — error, а не AttributeError в потоке."""
    finished, errors = _run_checker('1.0', ['a'])
    assert finished == [] and 'неожиданный' in errors[0]


def test_checker_run_network_error_text():
    """Сбой без текста — в error имя типа."""
    finished, errors = _run_checker('1.0', side_effect=TimeoutError())
    assert finished == [] and errors == ['TimeoutError']


# ---------------------------------------------------------------------------
# Скрипт замены (Windows) и документация
# ---------------------------------------------------------------------------

def test_windows_script_contains_names():
    """Скрипт: имена файлов, переименование, самоудаление."""
    script = build_windows_update_script('Old.exe', 'New.exe', 'u.log')
    assert '$old = "Old.exe"' in script
    assert '$new = "New.exe"' in script
    assert '$log = "u.log"' in script
    assert '--rename-to `"$old`"' in script
    assert 'Remove-Item -Path $MyInvocation.MyCommand.Path -Force' in script


def test_doctests():
    """Примеры (>>>) в докстрингах модуля верны."""
    result = doctest.testmod(updater, optionflags=doctest.ELLIPSIS)
    assert result.failed == 0
    assert result.attempted > 0
