# tests/test_updater/test_updater_linux.py

"""
Тесты автообновления Linux-версии (2026-11-07): манифест, распаковка, состав, update.sh, сборка.

Номера (U20 …) — журнал проверок в ``app/UPDATER.md``. Сеть не нужна. Всё пишется в ``tmp_path``:
установка — настоящая папка с пробелом, кириллицей, кавычкой и ``$`` в имени; ``update.sh``
запускается настоящим bash, ``venv_project_med/bin/python`` — заглушка (записывает вызовы;
окно программы не запускается).
"""

import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

import app.updater as updater
from app.updater import (
    LINUX_MANIFEST_FILE,
    LINUX_MANIFEST_HEADER,
    LINUX_MARKER_FILE,
    UpdateApplier,
    UpdateError,
    build_linux_update_script,
    build_windows_update_script,
    check_unpacked_update,
    get_install_root,
    linux_install_unavailable_reason,
    parse_linux_manifest,
    pop_linux_update_failure,
    prepare_linux_update,
    safe_extract_tar,
    validate_manifest_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = PROJECT_ROOT / 'scripts' / 'run_linux.sh'
EVIL_FOLDER = "Моя папка с пробелом 'кавычка' $HOME"

only_linux = pytest.mark.skipif(
    sys.platform != 'linux',
    reason='нужны bash и GNU mv',
)

# Заглушка интерпретатора окружения: записывает вызов; pip управляется файлами рядом с журналом
STUB_PYTHON = r'''#!/bin/bash
RECORD_DIR="$(cat "$(dirname "$0")/record_dir")"
if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then
    echo "pip $*" >> "$RECORD_DIR/pip_calls"
    CALLS=$(wc -l < "$RECORD_DIR/pip_calls")
    if [ -f "$RECORD_DIR/pip_kill_at_call" ] && [ "$CALLS" = "$(cat "$RECORD_DIR/pip_kill_at_call")" ]; then
        kill -9 "$PPID"
        exit 1
    fi
    [ -f "$RECORD_DIR/pip_fail" ] && exit 1
    exit 0
fi
# запуск программы: версия и окружение на момент запуска
echo "$(cat VERSION)|$(pwd)|${DISPLAY:-}" >> "$RECORD_DIR/started"
'''


# ---------------------------------------------------------------------------
# Вспомогательное: дистрибутивы, архивы, установка
# ---------------------------------------------------------------------------

def _write_tree(
    folder  : Path,             # папка дистрибутива
    version : str,              # версия
    files   : Dict[str, str],   # файлы кода: путь → текст
) -> None:
    """Создаёт дистрибутив: файлы кода, run.sh, метка, манифест."""
    content = dict(files)
    content['VERSION'] = f'{version}\n'
    content['run.sh'] = RUN_SCRIPT.read_text(encoding='utf-8')
    content[LINUX_MARKER_FILE] = f'MedicalApp Linux {version}\n'
    for rel, text in content.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    (folder / 'run.sh').chmod(0o755)
    listed = sorted(list(content) + [LINUX_MANIFEST_FILE])
    (folder / LINUX_MANIFEST_FILE).write_text(
        '\n'.join([LINUX_MANIFEST_HEADER, *listed]) + '\n',
        encoding='utf-8',
    )


def _pack(
    folder  : Path,  # папка дистрибутива
    archive : Path,  # файл архива
) -> Path: # файл архива
    """Упаковывает папку в .tar.gz с ней самой на верхнем уровне."""
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(folder, arcname=folder.name)
    return archive


OLD_FILES = {
    'app/__init__.py': 'OLD = 1\n',
    'app/old_only.py': 'OLD_ONLY = 1\n',
    'app/gone_pkg/__init__.py': 'GONE = 1\n',
    'parsers/word_importer.py': 'OLD = 1\n',
    'main_gui_window.py': 'print("old")\n',
    'requirements.txt': 'a==1\n',
}
NEW_FILES = {
    'app/__init__.py': 'NEW = 1\n',
    'app/new_only.py': 'NEW_ONLY = 1\n',
    'parsers/word_importer.py': 'NEW = 1\n',
    'main_gui_window.py': 'print("new")\n',
    'requirements.txt': 'a==1\n',
}
# Данные и окружение установки: обновление их не трогает и в backup_ не переносит
DATA_FILES = {
    '.env': 'SECRET=1\n',
    'config.msgpack': 'cfg',
    'clinic.db': 'db',
    'photos/p.jpg': 'photo',
    'logs/app.log': 'log',
    'parsers/logs/parser.log': 'parser log',
    'parsers/photos/x.jpg': 'parser photo',
    'app/MedicalAppUpdates/keep.bin': 'keep',
    'app/__pycache__/keep.cpython-311.pyc': 'pyc',
    'venv_project_med/lib/keep.txt': 'venv',
}


class Install:
    """Установка в папке с трудным именем и подготовленное обновление."""

    def __init__(
        self,
        tmp_path    : Path,                             # временная папка теста
        new_files   : Optional[Dict[str, str]] = None,  # файлы новой версии; None — NEW_FILES
        new_version : str = '1.1.0',                    # новая версия
    ) -> None:
        self.base = tmp_path
        self.root = tmp_path / EVIL_FOLDER / 'MedicalApp-linux'
        self.record = tmp_path / 'record'
        self.record.mkdir()
        self.root.mkdir(parents=True)
        _write_tree(self.root, '1.0.0', OLD_FILES)
        for rel, text in DATA_FILES.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        venv_bin = self.root / 'venv_project_med' / 'bin'
        venv_bin.mkdir(parents=True)
        (venv_bin / 'python').write_text(STUB_PYTHON, encoding='utf-8')
        (venv_bin / 'python').chmod(0o755)
        (venv_bin / 'record_dir').write_text(str(self.record), encoding='utf-8')
        self.data_before = self.snapshot_data()

        payload = tmp_path / 'build' / 'MedicalApp-linux'
        _write_tree(payload, new_version, NEW_FILES if new_files is None else new_files)
        self.archive = _pack(payload, tmp_path / 'MedicalApp_new_1.tar.gz')

    def snapshot_data(self) -> Dict[str, str]:
        """Содержимое данных и заглушки окружения."""
        return {rel: (self.root / rel).read_text(encoding='utf-8') for rel in DATA_FILES}

    def prepare(
        self,
        wait_pid : Optional[int] = None,  # PID; None — уже завершившийся процесс
        **kwargs,  # другие параметры prepare_linux_update
    ):
        """Готовит обновление с фиксированной меткой."""
        if wait_pid is None:
            finished = subprocess.Popen(['true'])
            finished.wait()
            wait_pid = finished.pid
        return prepare_linux_update(
            archive_path    =   str(self.archive),  # архив
            install_root    =   str(self.root),     # установка
            current_version =   '1.0.0',            # текущая версия
            wait_pid        =   wait_pid,           # PID
            stamp           =   1,                  # метка
            **kwargs,
        )

    def run_script(
        self,
        *args : str,  # параметры update.sh
    ) -> int: # код выхода
        """Запускает update.sh (окружение — с DISPLAY, как у окна)."""
        env = dict(os.environ, DISPLAY=':77')
        return subprocess.run(
            ['bash', str(self.root / 'update.sh'), *args],
            env     =   env,
            timeout =   60,
        ).returncode

    def started_versions(
        self,
        expected : int = 1,  # сколько запусков ждём
    ) -> List[str]: # строки журнала запусков
        """Ждёт запуска программы заглушкой: перезапуск идёт в отдельном сеансе."""
        path = self.record / 'started'
        deadline = time.time() + 20
        while time.time() < deadline:
            if path.exists():
                lines = path.read_text(encoding='utf-8').splitlines()
                if len(lines) >= expected:
                    return lines
            time.sleep(0.05)
        return path.read_text(encoding='utf-8').splitlines() if path.exists() else []

    def pip_calls(self) -> List[str]:
        """Вызовы pip."""
        path = self.record / 'pip_calls'
        return path.read_text(encoding='utf-8').splitlines() if path.exists() else []

    def code(
        self,
        rel : str,  # путь файла кода
    ) -> str: # содержимое файла
        """Текст файла установки."""
        return (self.root / rel).read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# U21 — манифест: только код, не данные и не выход за папку
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path', [
    'app/updater.py',
    'parsers/word_importer.py',
    'interfaces/gui/gui_window/widgets/delegate/photo_edit_dialog.py',
    'app/utils/logger/logger.py',
    '.medicalapp_manifest',
    'run.sh',
])
def test_u21_manifest_accepts_code(path):
    """Пути кода принимаются, включая похожие на данные по части имени (photo_, logger)."""
    assert validate_manifest_path(path) == path


@pytest.mark.parametrize('path', [
    '',
    '/etc/passwd',
    '../x.py',
    'app/../../x.py',
    'app/..',
    './app/x.py',
    'app//x.py',
    'app\\x.py',
    'app/x\ny.py',
    'venv_project_med/bin/python',
    'app/venv_project_med/x.py',
    '.git/config',
    '.env',
    'prod.env',
    'config.msgpack',
    'clinic.db',
    'clinic.db-wal',
    'photos/a.py',
    'parsers/photos/a.py',
    'parsers/logs/a.py',
    'logs/a.py',
    'photos_old/a.py',
    'app/__pycache__/a.pyc',
    'app/MedicalAppUpdates/a.py',
    'app/a.log',
    'app/a.log.1',
    'update.sh',
    'update.log',
    '.update_1/a.py',
    '.update_in_progress',
    'backup_1.0.0/a.py',
])
def test_u21_manifest_rejects_data_and_escape(path):
    """Данные, venv, служебное обновления, выход за папку — отказ."""
    with pytest.raises(UpdateError):
        validate_manifest_path(path)


REQUIRED = [LINUX_MANIFEST_FILE, LINUX_MARKER_FILE, 'VERSION', 'run.sh']


def test_u21_parse_manifest_ok():
    """Заголовок и пути; пустая строка в конце не мешает."""
    text = '\n'.join([LINUX_MANIFEST_HEADER, *REQUIRED, 'app/a.py', ''])
    assert parse_linux_manifest(text) == (*REQUIRED, 'app/a.py')


@pytest.mark.parametrize('lines', [
    [],                                                         # пусто
    ['# другой формат', *REQUIRED],                             # неизвестный формат
    [LINUX_MANIFEST_HEADER, *REQUIRED, 'a.py', 'a.py'],         # повтор
    [LINUX_MANIFEST_HEADER, *REQUIRED, 'a', 'a/b.py'],          # файл и папка сразу
    [LINUX_MANIFEST_HEADER, LINUX_MARKER_FILE, 'VERSION'],      # нет обязательных
    [LINUX_MANIFEST_HEADER, *REQUIRED, '../x'],                 # выход наверх
])
def test_u21_parse_manifest_rejects(lines):
    """Неверный манифест — отказ."""
    with pytest.raises(UpdateError):
        parse_linux_manifest('\n'.join(lines))


# ---------------------------------------------------------------------------
# U22 — распаковка со своей проверкой
# ---------------------------------------------------------------------------

def _tar_with(
    archive : Path,          # файл архива
    entries : List[tarfile.TarInfo],  # записи
) -> Path: # файл архива
    """Архив из готовых записей; у обычных файлов — содержимое из нулей по размеру."""
    with tarfile.open(archive, 'w:gz') as tar:
        for info in entries:
            tar.addfile(info, io.BytesIO(b'x' * info.size) if info.isreg() else None)
    return archive


def _info(
    name : str,                         # имя записи
    kind : bytes = tarfile.REGTYPE,     # тип записи
    link : str = '',                    # цель ссылки
    size : int = 0,                     # размер
) -> tarfile.TarInfo: # запись архива
    """Запись архива."""
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = link
    info.size = size
    return info


@pytest.mark.parametrize('entries', [
    [_info('/etc/evil')],                                       # абсолютный
    [_info('top/../../evil')],                                  # наверх
    [_info('../evil')],                                         # наверх сразу
    [_info('top/link', tarfile.SYMTYPE, '/etc/passwd')],        # ссылка наружу
    [_info('top/link', tarfile.SYMTYPE, '../../x')],            # относительная ссылка наружу
    [_info('top/a'), _info('top/l', tarfile.LNKTYPE, 'top/a')], # жёсткая ссылка
    [_info('top/fifo', tarfile.FIFOTYPE)],                      # канал
    [_info('top/dev', tarfile.CHRTYPE)],                        # устройство
    [_info('top/a'), _info('other/b')],                         # две папки верхнего уровня
    [_info('file_on_top')],                                     # файл вне папки
    [_info('top/a'), _info('top/a')],                           # повтор
    [_info('top/a\nb')],                                        # перевод строки в имени
])
def test_u22_extract_rejects_and_writes_nothing(tmp_path, entries):
    """Недопустимая запись — отказ; в папке распаковки ничего не появилось."""
    archive = _tar_with(tmp_path / 'a.tar.gz', entries)
    dest = tmp_path / 'dest'
    dest.mkdir()
    with pytest.raises(UpdateError):
        safe_extract_tar(
            archive_path    =   str(archive),   # архив
            dest_dir        =   str(dest),      # куда
        )
    assert list(dest.iterdir()) == []
    assert not (tmp_path / 'evil').exists()


def test_u22_extract_regular(tmp_path):
    """Обычный архив: файлы на месте, права без setuid, время сохранено."""
    info = _info('top/sub/a.txt', size=3)
    info.mode = 0o4755
    info.mtime = 1000000
    archive = _tar_with(tmp_path / 'a.tar.gz', [_info('top', tarfile.DIRTYPE), info])
    dest = tmp_path / 'dest'
    dest.mkdir()
    assert safe_extract_tar(str(archive), str(dest)) == 'top'
    target = dest / 'top' / 'sub' / 'a.txt'
    assert target.read_bytes() == b'xxx'
    assert stat.S_IMODE(target.stat().st_mode) & 0o4000 == 0
    assert int(target.stat().st_mtime) == 1000000


def test_u22_extract_size_limit(tmp_path):
    """Сумма размеров больше предела — отказ до записи."""
    archive = _tar_with(tmp_path / 'a.tar.gz', [_info('top/a', size=100)])
    dest = tmp_path / 'dest'
    dest.mkdir()
    with pytest.raises(UpdateError, match='слишком большой'):
        safe_extract_tar(
            archive_path    =   str(archive),   # архив
            dest_dir        =   str(dest),      # куда
            max_total_bytes =   10,             # предел
        )
    assert list(dest.iterdir()) == []


@pytest.mark.parametrize('data', [b'not a tar at all', b''])
def test_u22_extract_broken_archive(tmp_path, data):
    """Испорченный архив — понятная ошибка, а не исключение tarfile."""
    archive = tmp_path / 'a.tar.gz'
    archive.write_bytes(data)
    dest = tmp_path / 'dest'
    dest.mkdir()
    with pytest.raises(UpdateError, match='повреждён'):
        safe_extract_tar(str(archive), str(dest))


# ---------------------------------------------------------------------------
# U23 — состав и подготовка
# ---------------------------------------------------------------------------

def test_u23_check_unpacked_missing_and_extra(tmp_path):
    """Файла нет или есть лишний — отказ; совпало — пути манифеста."""
    payload = tmp_path / 'p'
    _write_tree(payload, '1.1.0', {'app/a.py': ''})
    assert 'app/a.py' in check_unpacked_update(str(payload))

    (payload / 'extra.py').write_text('', encoding='utf-8')
    with pytest.raises(UpdateError, match='вне манифеста'):
        check_unpacked_update(str(payload))
    (payload / 'extra.py').unlink()

    (payload / 'app' / 'a.py').unlink()
    with pytest.raises(UpdateError, match='нет файлов из манифеста'):
        check_unpacked_update(str(payload))


@only_linux
def test_u23_check_unpacked_symlink(tmp_path):
    """Ссылка в распакованной папке — отказ."""
    payload = tmp_path / 'p'
    _write_tree(payload, '1.1.0', {'app/a.py': ''})
    (payload / 'app' / 'l').symlink_to('/etc')
    with pytest.raises(UpdateError, match='ссылка'):
        check_unpacked_update(str(payload))


def test_u23_manifest_with_data_in_archive_rejected(tmp_path):
    """Манифест в архиве указывает на данные — отказ, код не менялся, архив и .update_ убраны."""
    install = Install(tmp_path)
    payload = tmp_path / 'bad' / 'MedicalApp-linux'
    _write_tree(payload, '1.1.0', {'parsers/photos/x.py': ''})
    archive = _pack(payload, tmp_path / 'bad.tar.gz')
    with pytest.raises(UpdateError, match='данные'):
        prepare_linux_update(str(archive), str(install.root), '1.0.0', 1, stamp=1)
    assert not archive.exists()
    assert not (install.root / '.update_1').exists()
    assert not (install.root / 'update.sh').exists()
    assert install.code('app/__init__.py') == 'OLD = 1\n'


def test_u23_version_not_newer_rejected(tmp_path):
    """Версия в архиве не новее — отказ: иначе обновление предлагалось бы бесконечно."""
    install = Install(tmp_path, new_version='1.0.0')
    with pytest.raises(UpdateError, match='не новее'):
        install.prepare()
    assert not (install.root / '.update_1').exists()


def test_u23_prepare_plan(tmp_path):
    """План: удалённые, добавленные, архив убран, код на месте, скрипт исполняемый."""
    install = Install(tmp_path)
    plan = install.prepare()
    assert set(plan.removed_paths) == {'app/old_only.py', 'app/gone_pkg/__init__.py'}
    assert plan.added_paths == ('app/new_only.py',)
    assert plan.new_version == '1.1.0'
    assert plan.requirements_changed is False
    assert not install.archive.exists()
    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert os.access(plan.script_path, os.X_OK)
    assert not (install.root / 'update.sh.tmp').exists()


def test_u23_prepare_removes_stale_work_dirs(tmp_path):
    """Остатки прерванной попытки убираются; похожие имена не трогаются."""
    install = Install(tmp_path)
    (install.root / '.update_999').mkdir()
    (install.root / '.update_notes').mkdir()
    install.prepare()
    assert not (install.root / '.update_999').exists()
    assert (install.root / '.update_notes').exists()


def test_u23_existing_backup_not_overwritten(tmp_path):
    """Папка backup_<версия> уже есть — берётся другое имя, старая не трогается."""
    install = Install(tmp_path)
    (install.root / 'backup_1.0.0').mkdir()
    plan = install.prepare()
    assert os.path.basename(plan.backup_dir) == 'backup_1.0.0_1'


@only_linux
def test_u23_symlinked_code_dir_rejected(tmp_path):
    """Папка кода — ссылка наружу: отказ, чтобы перенос не ушёл за пределы установки."""
    install = Install(tmp_path)
    outside = tmp_path / 'outside'
    shutil.move(str(install.root / 'parsers'), str(outside))
    (install.root / 'parsers').symlink_to(outside)
    with pytest.raises(UpdateError, match='ссылка'):
        install.prepare()


def test_u23_requirements_changed_without_venv_rejected(tmp_path):
    """Пакеты изменились, а окружения нет — отказ до выхода из программы."""
    files = dict(NEW_FILES)
    files['requirements.txt'] = 'a==2\n'
    install = Install(tmp_path, new_files=files)
    shutil.rmtree(install.root / 'venv_project_med' / 'bin')
    with pytest.raises(UpdateError, match='install.sh'):
        install.prepare()


# ---------------------------------------------------------------------------
# U24 — метка и причины отказа до скачивания
# ---------------------------------------------------------------------------

def test_u24_reason_ok_on_installed(tmp_path):
    """Установленный дистрибутив с правом записи — обновлять можно."""
    install = Install(tmp_path)
    assert linux_install_unavailable_reason(str(install.root), False) is None


@pytest.mark.parametrize('as_file', [False, True])
def test_u24_reason_dev_copy(tmp_path, as_file):
    """.git (папка или файл копии worktree) — рабочая копия не обновляется, даже с меткой."""
    install = Install(tmp_path)
    git = install.root / '.git'
    if as_file:
        git.write_text('gitdir: /x', encoding='utf-8')
    else:
        git.mkdir()
    assert 'рабочая копия' in linux_install_unavailable_reason(str(install.root), False)


def test_u24_reason_no_marker(tmp_path):
    """Нет метки — не дистрибутив."""
    install = Install(tmp_path)
    (install.root / LINUX_MARKER_FILE).unlink()
    assert 'не из установленного' in linux_install_unavailable_reason(str(install.root), False)


def test_u24_reason_bad_manifest(tmp_path):
    """Манифест испорчен — отказ со ссылкой на ручное обновление."""
    install = Install(tmp_path)
    (install.root / LINUX_MANIFEST_FILE).write_text('мусор', encoding='utf-8')
    assert 'вручную' in linux_install_unavailable_reason(str(install.root), False)


def test_u24_reason_in_progress(tmp_path):
    """Метка незавершённого обновления — отказ."""
    install = Install(tmp_path)
    (install.root / '.update_in_progress').write_text('1\n', encoding='utf-8')
    assert 'не завершено' in linux_install_unavailable_reason(str(install.root), False)


@only_linux
@pytest.mark.skipif(
    hasattr(os, 'geteuid') and os.geteuid() == 0,
    reason='root пишет куда угодно',
)
@pytest.mark.parametrize('folder', ['.', 'parsers'])
def test_u24_reason_not_writable(tmp_path, folder):
    """Нет прав на запись в папку установки или папку кода — понятная ошибка «вручную»."""
    install = Install(tmp_path)
    target = install.root / folder
    target.chmod(0o555)
    try:
        reason = linux_install_unavailable_reason(str(install.root), False)
    finally:
        target.chmod(0o755)
    assert 'Нет прав на запись' in reason and 'вручную' in reason


def test_u24_install_root_is_parent_of_app():
    """Корень — родитель app/, вычислен от программы, а не зашит."""
    assert Path(get_install_root()) == Path(updater.__file__).resolve().parents[1]


def test_u24_real_project_refuses():
    """Рабочая копия проекта: отказ (нет метки или есть .git), причина через общую функцию."""
    assert updater.auto_update_unavailable_reason('linux', False) is not None


# ---------------------------------------------------------------------------
# U20 — окно: старт и применение на Linux
# ---------------------------------------------------------------------------

TGZ_ASSET = {'name': 'MedicalApp-linux.tar.gz', 'url': 'file-url'}


def test_u20_start_refusal_before_download(tmp_path):
    """Нет метки — ошибка до скачивания."""
    applier = UpdateApplier({'assets': [TGZ_ASSET]})
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater, 'current_system', return_value='linux'), \
         patch.object(updater, 'get_install_root', return_value=str(tmp_path)):
        applier.start()
    downloader_cls.assert_not_called()
    assert len(errors) == 1 and 'не из установленного' in errors[0]


def test_u20_start_downloads_into_install_root(tmp_path):
    """Установленный дистрибутив: файл качается в корень установки, а не в app/."""
    install = Install(tmp_path)
    applier = UpdateApplier({'assets': [TGZ_ASSET], 'body': ''})
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater, 'current_system', return_value='linux'), \
         patch.object(updater, 'get_install_root', return_value=str(install.root)), \
         patch('app.config.conf.getenv.get_getenv', return_value=''):
        applier.start()
    assert errors == []
    path = downloader_cls.call_args.args[1]
    assert os.path.dirname(path) == str(install.root) and path.endswith('.tar.gz')


def test_u20_apply_launches_script_and_exits(tmp_path):
    """После подготовки — запуск скрипта, выход из программы; ошибок нет."""
    install = Install(tmp_path)
    applier = UpdateApplier({'assets': [TGZ_ASSET]})
    applier._downloaded_file = str(install.archive)
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'current_system', return_value='linux'), \
         patch.object(updater, 'get_install_root', return_value=str(install.root)), \
         patch.object(updater, 'APP_VERSION', '1.0.0'), \
         patch.object(updater, 'launch_linux_update_script') as launch, \
         patch.object(updater.QApplication, 'quit') as quit_app, \
         pytest.raises(SystemExit):
        applier._apply_update()
    assert errors == []
    launch.assert_called_once()
    assert launch.call_args.kwargs['script_path'] == str(install.root / 'update.sh')
    quit_app.assert_called_once()


def test_u20_apply_bad_archive_keeps_running(tmp_path):
    """Обновление не прошло проверку — error, скрипт не запускается, программа работает."""
    install = Install(tmp_path)
    install.archive.write_bytes(b'broken')
    applier = UpdateApplier({'assets': [TGZ_ASSET]})
    applier._downloaded_file = str(install.archive)
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'current_system', return_value='linux'), \
         patch.object(updater, 'get_install_root', return_value=str(install.root)), \
         patch.object(updater, 'APP_VERSION', '1.0.0'), \
         patch.object(updater, 'launch_linux_update_script') as launch:
        applier._apply_update()
    launch.assert_not_called()
    assert len(errors) == 1 and 'повреждён' in errors[0]


def test_u20_apply_launch_failure_cleans_up(tmp_path):
    """bash не запустился — error, временное убрано."""
    install = Install(tmp_path)
    applier = UpdateApplier({'assets': [TGZ_ASSET]})
    applier._downloaded_file = str(install.archive)
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'current_system', return_value='linux'), \
         patch.object(updater, 'get_install_root', return_value=str(install.root)), \
         patch.object(updater, 'APP_VERSION', '1.0.0'), \
         patch.object(updater, 'launch_linux_update_script', side_effect=OSError('нет bash')):
        applier._apply_update()
    assert len(errors) == 1 and 'нет bash' in errors[0]
    assert not (install.root / '.update_1').exists()
    assert not (install.root / 'update.sh').exists()


def test_u20_windows_script_unchanged():
    """Скрипт Windows не менялся: ключевые шаги на месте."""
    text = build_windows_update_script('A.exe', 'B.exe', 'u.log')
    assert '--rename-to' in text and 'Stop-Process' in text and '$old = "A.exe"' in text


# ---------------------------------------------------------------------------
# U25 — текст скрипта
# ---------------------------------------------------------------------------

def _script(
    **overrides,  # отличия от значений по умолчанию
) -> str: # текст update.sh
    """Скрипт с обычными значениями."""
    values = dict(
        wait_pid                =   123,                # PID
        old_version             =   '1.0.0',            # было
        new_version             =   '1.1.0',            # стало
        work_dir                =   '.update_1',        # временная папка
        payload_dir             =   '.update_1/top',    # дистрибутив
        backup_dir              =   'backup_1.0.0',     # прежняя версия
        new_paths               =   ['run.sh'],         # новые
        removed_paths           =   [],                 # удалённые
        added_paths             =   [],                 # добавленные
        requirements_changed    =   False,              # pip
    )
    values.update(overrides)
    return build_linux_update_script(**values)


@only_linux
@pytest.mark.parametrize('overrides', [
    {},
    {'requirements_changed': True},
    {'removed_paths': ['a.py'], 'added_paths': ['b.py']},
    {'new_paths': ["с пробелом и 'кавычкой' $HOME `x`.py"]},
])
def test_u25_script_syntax(tmp_path, overrides):
    """bash -n: синтаксис верен при любых значениях."""
    path = tmp_path / 'update.sh'
    path.write_text(_script(**overrides), encoding='utf-8')
    subprocess.run(['bash', '-n', str(path)], check=True)


def test_u25_script_has_no_install_path_and_quotes_values():
    """Путь установки в текст не попадает; значения экранированы."""
    text = _script(new_paths=["a'b $c.py"], new_version="1'; rm -rf x #")
    assert '/home' not in text
    assert """'a'"'"'b $c.py'""" in text
    assert """NEW_VERSION='1'"'"'; rm -rf x #'""" in text


def test_u25_script_key_steps():
    """Шаги замены: перенос без попадания внутрь папки, python -m pip, отвязанный запуск."""
    text = _script(requirements_changed=True)
    assert 'mv -f -T --' in text
    assert '"$VENV_PYTHON" -m pip install' in text
    assert 'REQUIREMENTS_CHANGED=1' in text
    assert 'setsid nohup bash' in text
    assert 'VENV_PYTHON=venv_project_med/bin/python' in text


def test_u25_script_unix_line_endings():
    """Только LF: иначе bash на Linux не разберёт скрипт."""
    assert '\r' not in _script()


# ---------------------------------------------------------------------------
# U20 — update.sh вживую, настоящий bash в папке с трудным именем
# ---------------------------------------------------------------------------

@only_linux
def test_u20_update_success(tmp_path):
    """Код заменён, удалённый модуль — в backup_, данные и venv нетронуты, новая версия запущена."""
    install = Install(tmp_path)
    plan = install.prepare()
    assert install.run_script() == 0

    assert install.code('app/__init__.py') == 'NEW = 1\n'
    assert install.code('app/new_only.py') == 'NEW_ONLY = 1\n'
    assert install.code('VERSION') == '1.1.0\n'
    assert not (install.root / 'app' / 'old_only.py').exists()
    assert not (install.root / 'app' / 'gone_pkg').exists() # папка удалённого пакета
    assert install.snapshot_data() == install.data_before

    backup = Path(plan.backup_dir)
    assert (backup / 'app' / 'old_only.py').read_text(encoding='utf-8') == 'OLD_ONLY = 1\n'
    assert (backup / 'app' / '__init__.py').read_text(encoding='utf-8') == 'OLD = 1\n'
    assert (backup / 'VERSION').read_text(encoding='utf-8') == '1.0.0\n'
    in_backup = {str(p.relative_to(backup)) for p in backup.rglob('*') if p.is_file()}
    assert not any(
        rel.startswith(('parsers/logs', 'parsers/photos', 'venv_project_med', 'photos', 'logs'))
        or rel.endswith(('.db', '.env', '.msgpack', '.pyc'))
        for rel in in_backup
    )

    assert not (install.root / '.update_1').exists()
    assert not (install.root / 'update.sh').exists()
    assert not (install.root / '.update_in_progress').exists()
    assert not (install.root / '.update_failed').exists()
    assert install.pip_calls() == [] # requirements.txt не менялся

    started = install.started_versions()
    assert len(started) == 1
    version, cwd, display = started[0].split('|')
    assert version == '1.1.0'
    assert cwd == str(install.root) and display == ':77'


@only_linux
def test_u20_requirements_changed_runs_pip(tmp_path):
    """requirements.txt изменился — pip окружения установки с новым файлом."""
    files = dict(NEW_FILES)
    files['requirements.txt'] = 'a==2\n'
    install = Install(tmp_path, new_files=files)
    assert install.prepare().requirements_changed is True
    assert install.run_script() == 0
    calls = install.pip_calls()
    assert len(calls) == 1 and '-r requirements.txt' in calls[0]
    assert install.started_versions()[0].startswith('1.1.0|')


@only_linux
def test_u20_pip_failure_rolls_back(tmp_path):
    """pip упал: прежний код, добавленного нет, backup_ убран, причина для окна, старая версия."""
    files = dict(NEW_FILES)
    files['requirements.txt'] = 'a==2\n'
    install = Install(tmp_path, new_files=files)
    (install.record / 'pip_fail').write_text('', encoding='utf-8')
    plan = install.prepare()
    assert install.run_script() == 1

    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert install.code('app/old_only.py') == 'OLD_ONLY = 1\n'
    assert install.code('app/gone_pkg/__init__.py') == 'GONE = 1\n'
    assert install.code('VERSION') == '1.0.0\n'
    assert install.code('requirements.txt') == 'a==1\n'
    assert not (install.root / 'app' / 'new_only.py').exists()
    assert install.snapshot_data() == install.data_before

    assert not os.path.exists(plan.backup_dir)
    assert not (install.root / '.update_1').exists()
    assert not (install.root / 'update.sh').exists()
    assert not (install.root / '.update_in_progress').exists()

    assert install.started_versions()[0].startswith('1.0.0|')

    message = pop_linux_update_failure(str(install.root))
    assert '1.1.0' in message and '1.0.0' in message and 'пакеты' in message
    assert pop_linux_update_failure(str(install.root)) is None # показывается один раз


@only_linux
def test_u20_failure_while_placing_rolls_back(tmp_path):
    """Файл обновления пропал посреди замены — откат, прежний код на месте."""
    install = Install(tmp_path)
    install.prepare()
    (install.root / '.update_1' / 'MedicalApp-linux' / 'parsers' / 'word_importer.py').unlink()
    assert install.run_script() == 1
    assert install.code('parsers/word_importer.py') == 'OLD = 1\n'
    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert not (install.root / 'app' / 'new_only.py').exists()
    assert not (install.root / 'backup_1.0.0').exists()
    assert install.snapshot_data() == install.data_before
    assert 'word_importer' in pop_linux_update_failure(str(install.root))


@only_linux
def test_u20_module_becomes_package_and_back(tmp_path):
    """Пакет стал модулем и наоборот: mv -T и уборка пустых папок не мешают."""
    files = dict(NEW_FILES)
    files['app/gone_pkg.py'] = 'NOW_MODULE = 1\n'           # был пакет app/gone_pkg/
    files['app/old_only/__init__.py'] = 'NOW_PACKAGE = 1\n' # был модуль app/old_only.py
    install = Install(tmp_path, new_files=files)
    # кэш байт-кода в папке удаляемого пакета: не мешает убрать её
    cache = install.root / 'app' / 'gone_pkg' / '__pycache__'
    cache.mkdir()
    (cache / 'x.pyc').write_text('pyc', encoding='utf-8')
    install.prepare()
    assert install.run_script() == 0
    assert install.code('app/gone_pkg.py') == 'NOW_MODULE = 1\n'
    assert install.code('app/old_only/__init__.py') == 'NOW_PACKAGE = 1\n'


@only_linux
def test_u20_module_becomes_package_rollback(tmp_path):
    """Откат после смены пакета на модуль и обратно: прежние пути вернулись."""
    files = dict(NEW_FILES)
    files['requirements.txt'] = 'a==2\n'
    files['app/gone_pkg'] = 'NOW_FILE = 1\n'                # был пакет app/gone_pkg/
    files['app/old_only/__init__.py'] = 'NOW_PACKAGE = 1\n' # был модуль app/old_only.py
    install = Install(tmp_path, new_files=files)
    (install.record / 'pip_fail').write_text('', encoding='utf-8')
    plan = install.prepare()
    assert install.run_script() == 1
    assert install.code('app/gone_pkg/__init__.py') == 'GONE = 1\n'
    assert install.code('app/old_only.py') == 'OLD_ONLY = 1\n'
    assert not os.path.exists(plan.backup_dir)


@only_linux
def test_u20_data_in_folder_of_removed_package_stays(tmp_path):
    """В папке удалённого пакета есть данные: папка остаётся вместе с ними."""
    install = Install(tmp_path)
    keep = install.root / 'app' / 'gone_pkg' / 'user_data.txt'
    keep.write_text('данные', encoding='utf-8')
    install.prepare()
    assert install.run_script() == 0
    assert keep.read_text(encoding='utf-8') == 'данные'
    assert not (install.root / 'app' / 'gone_pkg' / '__init__.py').exists()


@only_linux
def test_u20_module_replaced_by_folder_with_data_rolls_back(tmp_path):
    """Новый файл на месте папки с данными: откат, данные целы, не переезжают в backup_."""
    files = dict(NEW_FILES)
    files['app/gone_pkg'] = 'теперь файл\n'
    install = Install(tmp_path, new_files=files)
    keep = install.root / 'app' / 'gone_pkg' / 'user_data.txt'
    keep.write_text('данные', encoding='utf-8')
    install.prepare()
    assert install.run_script() == 1
    assert keep.read_text(encoding='utf-8') == 'данные'
    assert install.code('app/gone_pkg/__init__.py') == 'GONE = 1\n'
    assert install.code('app/__init__.py') == 'OLD = 1\n'


@only_linux
def test_u20_waits_for_program_exit(tmp_path):
    """Пока программа работает, код не меняется; вышла — замена."""
    install = Install(tmp_path)
    program = subprocess.Popen(['sleep', '30'])
    try:
        install.prepare(wait_pid=program.pid)
        script = subprocess.Popen(['bash', str(install.root / 'update.sh')])
        time.sleep(0.6)
        assert install.code('app/__init__.py') == 'OLD = 1\n'
        assert script.poll() is None
    finally:
        program.kill()
        program.wait()
    assert script.wait(timeout=30) == 0
    assert install.code('app/__init__.py') == 'NEW = 1\n'


@only_linux
def test_u20_zombie_counts_as_exited(tmp_path):
    """Процесс завершился, но родитель его не забрал (зомби): замена идёт, ожидания до таймаута нет."""
    install = Install(tmp_path)
    zombie = subprocess.Popen(['true'])
    time.sleep(0.2)
    try:
        install.prepare(wait_pid=zombie.pid, wait_timeout=30)
        started = time.time()
        assert install.run_script() == 0
        assert time.time() - started < 15
    finally:
        zombie.wait()
    assert install.code('app/__init__.py') == 'NEW = 1\n'


@only_linux
def test_u20_program_not_exiting_cancels_update(tmp_path):
    """Программа не вышла за отведённое время: ничего не изменено, запуска нет."""
    install = Install(tmp_path)
    program = subprocess.Popen(['sleep', '30'])
    try:
        plan = install.prepare(wait_pid=program.pid, wait_timeout=1)
        assert install.run_script() == 1
    finally:
        program.kill()
        program.wait()
    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert not os.path.exists(plan.backup_dir)
    assert not (install.root / '.update_1').exists()
    assert not (install.root / 'update.sh').exists()
    assert not (install.record / 'started').exists()
    assert 'отменено' in pop_linux_update_failure(str(install.root))


@only_linux
def test_u20_recover_after_crash_via_run_sh(tmp_path):
    """Скрипт убит посреди pip (как сбой питания): run.sh откатывает и запускает прежнюю версию."""
    files = dict(NEW_FILES)
    files['requirements.txt'] = 'a==2\n'
    install = Install(tmp_path, new_files=files)
    (install.record / 'pip_kill_at_call').write_text('1', encoding='utf-8')
    plan = install.prepare()
    assert install.run_script() != 0

    # состояние после сбоя: новый код, метка незавершённого обновления, бэкап
    assert install.code('app/__init__.py') == 'NEW = 1\n'
    assert (install.root / '.update_in_progress').exists()
    assert (install.root / 'update.sh').exists()
    assert os.path.isdir(plan.backup_dir)

    subprocess.run(['bash', str(install.root / 'run.sh')], check=True, timeout=30)

    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert install.code('app/old_only.py') == 'OLD_ONLY = 1\n'
    assert not (install.root / 'app' / 'new_only.py').exists()
    assert not os.path.exists(plan.backup_dir)
    assert not (install.root / '.update_in_progress').exists()
    assert not (install.root / 'update.sh').exists()
    assert install.snapshot_data() == install.data_before
    assert install.started_versions()[0].startswith('1.0.0|')
    assert 'прервано' in pop_linux_update_failure(str(install.root))


@only_linux
def test_u20_recover_interrupted_twice(tmp_path):
    """Сбой и во время отката (pip в откате): повторный запуск завершает откат, файлы целы."""
    files = dict(NEW_FILES)
    files['requirements.txt'] = 'a==2\n'
    install = Install(tmp_path, new_files=files)
    (install.record / 'pip_kill_at_call').write_text('1', encoding='utf-8')
    install.prepare()
    install.run_script() # сбой в pip обновления

    (install.record / 'pip_kill_at_call').write_text('2', encoding='utf-8')
    assert install.run_script('--recover') != 0 # сбой в pip отката

    (install.record / 'pip_kill_at_call').unlink()
    subprocess.run(['bash', str(install.root / 'run.sh')], check=True, timeout=30)
    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert install.code('app/old_only.py') == 'OLD_ONLY = 1\n'
    assert install.code('requirements.txt') == 'a==1\n'
    assert not (install.root / 'app' / 'new_only.py').exists()
    assert not (install.root / '.update_in_progress').exists()


@only_linux
def test_u20_recover_refuses_while_script_alive(tmp_path):
    """Обновление ещё идёт (скрипт жив): --recover не вмешивается, run.sh программу не запускает."""
    install = Install(tmp_path)
    install.prepare()
    alive = subprocess.Popen(
        ['bash', '-c', 'exec -a "bash update.sh" sleep 30'],  # процесс с «update.sh» в командной строке
    )
    try:
        time.sleep(0.2)
        (install.root / '.update_in_progress').write_text(f'{alive.pid}\n', encoding='utf-8')
        assert install.run_script('--recover') == 3
        result = subprocess.run(
            ['bash', str(install.root / 'run.sh')],
            timeout =   30,
        )
        assert result.returncode == 1
    finally:
        alive.kill()
        alive.wait()
    assert install.code('app/__init__.py') == 'OLD = 1\n'
    assert not (install.record / 'started').exists()


# ---------------------------------------------------------------------------
# U26 — run.sh
# ---------------------------------------------------------------------------

@only_linux
def test_u26_run_sh_from_any_folder_and_symlink(tmp_path):
    """run.sh работает из другой папки и по символьной ссылке (папка с трудным именем)."""
    install = Install(tmp_path)
    link = tmp_path / 'ярлык'
    link.symlink_to(install.root / 'run.sh')
    subprocess.run(['bash', str(install.root / 'run.sh')], cwd=tmp_path, check=True, timeout=30)
    subprocess.run(['bash', str(link)], cwd='/', check=True, timeout=30)
    lines = install.started_versions(expected=2)
    assert len(lines) == 2
    assert all(line.split('|')[1] == str(install.root) for line in lines)


@only_linux
def test_u26_run_sh_without_venv(tmp_path):
    """Нет окружения — понятное сообщение и ненулевой код."""
    install = Install(tmp_path)
    shutil.rmtree(install.root / 'venv_project_med')
    result = subprocess.run(
        ['bash', str(install.root / 'run.sh')],
        capture_output  =   True,
        text            =   True,
        timeout         =   30,
    )
    assert result.returncode == 1 and 'install.sh' in result.stderr


# ---------------------------------------------------------------------------
# U27 — настоящая сборка: манифест проходит проверку обновления
# ---------------------------------------------------------------------------

@only_linux
def test_u27_build_produces_valid_update(tmp_path):
    """build_linux.sh на копии: метка, манифест, данные из рабочей папки в архив не попали."""
    copy = tmp_path / 'проект с пробелом'
    copy.mkdir()
    ignore = shutil.ignore_patterns('__pycache__')
    for folder in ('app', 'interfaces', 'parsers', 'scripts'):
        shutil.copytree(PROJECT_ROOT / folder, copy / folder, ignore=ignore)
    for name in ('main_gui_window.py', 'main_cli.py', 'requirements.txt', 'VERSION'):
        shutil.copy2(PROJECT_ROOT / name, copy / name)
    # данные, которые остаются в папках кода после запусков
    for rel in ('parsers/logs/p.log', 'parsers/photos/x.jpg', 'app/logs/a.txt',
                'app/MedicalAppUpdates/n.bin', 'interfaces/a.log', 'interfaces/b.db'):
        path = copy / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('data', encoding='utf-8')

    subprocess.run(['bash', str(copy / 'scripts' / 'build_linux.sh')], check=True, timeout=120)
    assert not (copy / 'MedicalApp-linux.manifest.tmp').exists()

    dest = tmp_path / 'dest'
    dest.mkdir()
    top = safe_extract_tar(str(copy / 'MedicalApp-linux.tar.gz'), str(dest))
    paths = check_unpacked_update(str(dest / top))

    assert LINUX_MARKER_FILE in paths and LINUX_MANIFEST_FILE in paths
    for rel in ('run.sh', 'install.sh', 'setup_prod.sh', 'find_python.sh', 'VERSION',
                'requirements.txt', 'main_gui_window.py', 'main_cli.py',
                'app/updater.py', 'parsers/word_importer.py'):
        assert rel in paths
    assert not any(
        rel.startswith(('parsers/logs', 'parsers/photos', 'app/logs', 'app/MedicalAppUpdates'))
        or rel.endswith(('.log', '.db'))
        for rel in paths
    )
    assert os.access(dest / top / 'run.sh', os.X_OK)
    assert list(paths) == sorted(paths, key=lambda rel: rel.encode('utf-8')) # порядок без локали
