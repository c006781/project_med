# tests/test_updater/test_updater_review_pass4.py

"""
Тесты прохода 4 модуля app.updater (2026-10-31): проверка файла релиза по SHA-256.

Номера (U14 …) — журнал проверок в ``app/UPDATER.md``. Сеть не нужна: ``requests.get``
подменяется; файлы пишутся только в ``tmp_path`` (``get_app_dir`` подменён).
"""

import hashlib
import io
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

import app.updater as updater
from app.updater import (
    AppUpdater,
    UpdateApplier,
    UpdateDownloader,
    file_sha256,
    parse_release_hashes,
    release_asset_sha256,
)

SECRET = 'ghp_SECRETSECRETSECRET'
DATA = b'MedicalApp release payload' * 100
DATA_SHA = hashlib.sha256(DATA).hexdigest()
OTHER_SHA = hashlib.sha256(b'other').hexdigest()
EXE = 'MedicalApp.exe'
TGZ = 'MedicalApp-linux.tar.gz'


def _body(
    *lines: str, # строки блока хешей
) -> str: # описание релиза в том виде, как его пишет release.yml
    """Описание релиза: блок хешей (как вывод sha256sum) и заметки GitHub ниже."""
    return (
        '## SHA-256\r\n\r\n```\r\n'
        + '\r\n'.join(lines)
        + '\r\n```\r\n\r\n## What\'s Changed\r\n* fix by @someone in #1\r\n'
    )


# ---------------------------------------------------------------------------
# U14 — разбор хешей из описания релиза
# ---------------------------------------------------------------------------

def test_u14_parse_sha256sum_lines():
    """Строки вида вывода sha256sum (два пробела; '*' — двоичный режим) → имя → хеш."""
    body = _body(f'{DATA_SHA}  {EXE}', f'{OTHER_SHA} *{TGZ}')
    assert parse_release_hashes(body) == {EXE: DATA_SHA, TGZ: OTHER_SHA}


def test_u14_parse_ignores_other_lines():
    """Заметки, ограды ```, короткие и не-hex строки — пропускаются."""
    body = _body(
        'abc  MedicalApp.exe',                     # не 64 знака
        f'{"g" * 64}  MedicalApp.exe',              # не hex
        f'{DATA_SHA}MedicalApp.exe',                # нет пробела
        f'{DATA_SHA}  ',                            # нет имени
    )
    assert parse_release_hashes(body) == {}


def test_u14_parse_uppercase_and_path():
    """Хеш — в нижний регистр; путь перед именем отбрасывается (оба вида косой)."""
    body = f'{DATA_SHA.upper()}  artifacts/MedicalApp-windows/{EXE}\n{OTHER_SHA}  dist\\{TGZ}'
    assert parse_release_hashes(body) == {EXE: DATA_SHA, TGZ: OTHER_SHA}


def test_u14_parse_first_wins():
    """Повтор имени — действует первая строка."""
    body = f'{DATA_SHA}  {EXE}\n{OTHER_SHA}  {EXE}'
    assert parse_release_hashes(body) == {EXE: DATA_SHA}


@pytest.mark.parametrize('body', [None, '', 'Release notes only'])
def test_u14_parse_empty(body):
    """Нет описания или в нём нет хешей — пустой словарь."""
    assert parse_release_hashes(body) == {}


@pytest.mark.parametrize('name, expected', [(EXE, DATA_SHA), (TGZ, OTHER_SHA)])
def test_u14_release_asset_sha256_both_systems(name, expected):
    """Хеш файла релиза по имени — для Windows (.exe) и Linux (.tar.gz)."""
    release = {'body': _body(f'{DATA_SHA}  {EXE}', f'{OTHER_SHA}  {TGZ}')}
    assert release_asset_sha256(release, name) == expected


def test_u14_release_asset_sha256_case_insensitive():
    """Имя файла сравнивается без учёта регистра (как при выборе файла релиза)."""
    release = {'body': f'{DATA_SHA}  {EXE}'}
    assert release_asset_sha256(release, 'medicalapp.EXE') == DATA_SHA


@pytest.mark.parametrize('release', [{}, {'body': None}, {'body': f'{DATA_SHA}  other.exe'}, None])
def test_u14_release_asset_sha256_missing(release):
    """Нет описания или строки для файла — None."""
    assert release_asset_sha256(release, EXE) is None


def test_u14_file_sha256(tmp_path):
    """file_sha256 — как hashlib целиком; порции меньше файла дают тот же результат."""
    path = tmp_path / 'f.bin'
    path.write_bytes(DATA)
    assert file_sha256(str(path)) == DATA_SHA
    assert file_sha256(str(path), chunk_size=7) == DATA_SHA
    empty = tmp_path / 'e.bin'
    empty.write_bytes(b'')
    assert file_sha256(str(empty)) == hashlib.sha256(b'').hexdigest()


# ---------------------------------------------------------------------------
# U14 — сверка хеша при скачивании (до os.replace)
# ---------------------------------------------------------------------------

def _response(
    data: bytes, # тело ответа
) -> MagicMock: # подменённый ответ requests (stream)
    """Подменённый ответ requests с потоком data и верным Content-Length."""
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.headers = {'content-length': str(len(data))}
    response.raw = io.BytesIO(data)
    return response


def _run_downloader(
    tmp_path : Path,            # временная папка теста
    name     : str,             # имя файла обновления
    expected : object,          # ожидаемый хеш (None — без проверки)
    token    : object = None,   # токен GitHub
):
    """UpdateDownloader.run с подменённым requests.get; итоги и сигналы."""
    target = tmp_path / name
    downloader = UpdateDownloader(
        'https://x/asset',              # адрес
        str(target),                    # куда
        token,                          # токен
        expected_sha256 = expected,     # ожидаемый хеш
    )
    downloader.logger = MagicMock()
    finished: List[str] = []
    errors: List[str] = []
    downloader.finished.connect(finished.append)
    downloader.error.connect(errors.append)
    with patch.object(updater.requests, 'get', return_value=_response(DATA)):
        downloader.run()
    return target, finished, errors, downloader.logger


@pytest.mark.parametrize('name', ['MedicalApp_new_1.exe', 'MedicalApp_new_1.tar.gz'])
def test_u14_download_hash_ok(tmp_path, name):
    """Хеш совпал — файл на месте, finished (Windows и Linux)."""
    target, finished, errors, _ = _run_downloader(tmp_path, name, DATA_SHA)
    assert errors == [] and finished == [str(target)]
    assert target.read_bytes() == DATA


def test_u14_download_hash_ok_uppercase(tmp_path):
    """Ожидаемый хеш в верхнем регистре — тоже совпадение."""
    _, finished, errors, _ = _run_downloader(tmp_path, 'a.exe', DATA_SHA.upper())
    assert errors == [] and len(finished) == 1


@pytest.mark.parametrize('name', ['MedicalApp_new_1.exe', 'MedicalApp_new_1.tar.gz'])
def test_u14_download_wrong_hash_rejected(tmp_path, name):
    """Неверный хеш — ошибка с понятным текстом, ни .part, ни файла: установка не пойдёт."""
    target, finished, errors, _ = _run_downloader(tmp_path, name, OTHER_SHA)
    assert finished == []
    assert len(errors) == 1
    assert 'SHA-256' in errors[0] and 'не совпала' in errors[0]
    assert DATA_SHA in errors[0] and OTHER_SHA in errors[0]
    assert not target.exists()
    assert not Path(f'{target}.part').exists()


def test_u14_download_wrong_hash_keeps_existing_target(tmp_path):
    """Неверный хеш не трогает уже лежащий файл с тем же именем."""
    target = tmp_path / 'a.exe'
    target.write_bytes(b'old')
    _run_downloader(tmp_path, 'a.exe', OTHER_SHA)
    assert target.read_bytes() == b'old'


def test_u14_download_without_expected_hash(tmp_path):
    """Без ожидаемого хеша — как раньше: файл принимается."""
    target, finished, errors, _ = _run_downloader(tmp_path, 'a.exe', None)
    assert errors == [] and finished == [str(target)]


# ---------------------------------------------------------------------------
# U14/U15 — UpdateApplier: хеш из описания релиза; релиз без хеша — предупредить
# ---------------------------------------------------------------------------

ASSETS = [
    {'name': TGZ, 'url': 'linux'},
    {'name': EXE, 'url': 'exe'},
]


def _start_applier(
    tmp_path : Path,    # временная папка (вместо папки программы)
    release  : dict,    # данные релиза
    system   : str,     # ОС
):
    """UpdateApplier.start с подменённым UpdateDownloader; ошибки, предупреждения, класс."""
    applier = UpdateApplier(release)
    errors: List[str] = []
    warnings: List[str] = []
    applier.error.connect(errors.append)
    applier.warning.connect(warnings.append)
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value=system), \
         patch.object(updater, 'AUTO_UPDATE_SYSTEMS', frozenset({'windows', 'linux'})), \
         patch.object(updater, 'get_app_dir', return_value=str(tmp_path)), \
         patch('app.config.conf.getenv.get_getenv', return_value=''):
        applier.start()
    return errors, warnings, downloader_cls


@pytest.mark.parametrize('system, name, url', [('windows', EXE, 'exe'), ('linux', TGZ, 'linux')])
def test_u14_applier_passes_expected_hash(tmp_path, system, name, url):
    """Хеш выбранного файла из описания релиза передаётся в скачивание."""
    release = {'assets': ASSETS, 'body': _body(f'{DATA_SHA}  {name}', f'{OTHER_SHA}  other.bin')}
    errors, warnings, downloader_cls = _start_applier(tmp_path, release, system)
    assert errors == [] and warnings == []
    assert downloader_cls.call_args.args[0] == url
    assert downloader_cls.call_args.kwargs['expected_sha256'] == DATA_SHA
    downloader_cls.return_value.start.assert_called_once()


def test_u15_applier_no_hash_warns_and_continues(tmp_path):
    """В описании нет строки для файла — предупреждение (сигнал), скачивание идёт без проверки."""
    release = {'assets': ASSETS, 'body': 'notes only'}
    errors, warnings, downloader_cls = _start_applier(tmp_path, release, 'windows')
    assert errors == []
    assert len(warnings) == 1 and EXE in warnings[0] and 'SHA-256' in warnings[0]
    assert downloader_cls.call_args.kwargs['expected_sha256'] is None
    downloader_cls.return_value.start.assert_called_once()


def test_u15_app_updater_relays_warning():
    """AppUpdater.download_warning — предупреждение установки для окна."""
    app_updater = AppUpdater()
    got: List[str] = []
    app_updater.download_warning.connect(got.append)
    with patch.object(UpdateApplier, 'start'):
        app_updater.apply_update_from_release({})
    app_updater._applier.warning.emit('нет хеша')
    assert got == ['нет хеша']


# ---------------------------------------------------------------------------
# U16 — verify=False при токене: предупреждение в журнал (поведение не меняется)
# ---------------------------------------------------------------------------

def _warnings_text(
    logger: MagicMock, # подменённый логгер
) -> str: # все предупреждения одной строкой
    """Сообщения logger.warning."""
    return ' '.join(str(call.args[0]) for call in logger.warning.call_args_list)


def test_u16_private_download_warns_no_cert_check(tmp_path):
    """Токен задан — в журнале предупреждение, что сертификат не проверяется; токена в нём нет."""
    _, finished, _, logger = _run_downloader(tmp_path, 'a.exe', DATA_SHA, token=SECRET)
    assert len(finished) == 1
    text = _warnings_text(logger)
    assert 'сертификат' in text
    assert SECRET not in text


def test_u16_public_download_no_warning(tmp_path):
    """Без токена — предупреждения о сертификате нет."""
    _, _, _, logger = _run_downloader(tmp_path, 'a.exe', DATA_SHA)
    assert 'сертификат' not in _warnings_text(logger)


# ---------------------------------------------------------------------------
# U17 — release.yml публикует хеши в описании релиза
# ---------------------------------------------------------------------------

RELEASE_YML = Path(__file__).resolve().parents[2] / '.github' / 'workflows' / 'release.yml'


def test_u17_release_yml_publishes_hashes():
    """В create-release: sha256sum обоих файлов → файл описания → body_path вместе с заметками."""
    text = RELEASE_YML.read_text(encoding='utf-8')
    job = text[text.index('create-release:'):]
    assert f'sha256sum {EXE}' in job
    assert f'sha256sum {TGZ}' in job
    assert 'body_path:' in job
    assert 'generate_release_notes: true' in job


def test_u17_sha256sum_format_parses(tmp_path):
    """Строка в формате sha256sum (как пишет release.yml) находится программой."""
    path = tmp_path / TGZ
    path.write_bytes(DATA)
    line = f'{file_sha256(str(path))}  {TGZ}'
    assert release_asset_sha256({'body': _body(line)}, TGZ) == DATA_SHA
