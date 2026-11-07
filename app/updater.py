# app/updater.py
"""
Автообновление приложения через GitHub Releases.

Цепочка (окно — ``UpdateMixin`` в ``interfaces/gui/gui_window/main_window.py``)::

    AppUpdater.check_for_updates()
      └─ UpdateChecker (поток): GET /repos/<slug>/releases/latest
           └─ is_newer_version(текущая, из тега) → update_available(tag, url) | no_update()
    AppUpdater.apply_update_from_release(release)
      └─ UpdateApplier.start(): ОС поддерживается? exe собран (Linux — установленный
         дистрибутив, есть права на запись)? → select_release_asset
           → release_asset_sha256 (хеш из описания релиза; нет — warning, без сверки)
           └─ UpdateDownloader (поток): скачивание в файл рядом с exe (с проверкой размера
              и SHA-256 до переименования .part)
                └─ UpdateApplier._apply_update(): скрипт замены (Windows — update.ps1,
                   Linux — распаковка, проверка состава, update.sh) → выход

Логика без Qt вынесена в функции (версии, выбор файла релиза, хеши, заголовки, скрипт
замены) — их легко проверять и дополнять. Подробности и журнал проверок — ``app/UPDATER.md``.

Как добавить ОС (например, macOS):

1. правило выбора файла релиза — в :data:`ASSET_RULES`;
2. расширение файла обновления — в :data:`UPDATE_FILE_EXTENSIONS`;
3. замена файла — ветка в :meth:`UpdateApplier._apply_update` и ОС в
   :data:`AUTO_UPDATE_SYSTEMS`.

Example:
    >>> is_newer_version('1.0.0', 'v1.0.1')
    True
    >>> is_newer_version('2.0', '1.5')
    False
    >>> select_release_asset([{'name': 'MedicalApp.exe', 'url': 'u'}], 'windows')['url']
    'u'
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import shutil
import tarfile
import tempfile
import time
import urllib.request
import platform
import zlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import certifi
import requests


from app.utils.logger.logger import AppLogger

from app.config import APP_VERSION, GITHUB_REPO_SLUG
from app.config.config_manager.manager import AppConfigManager



from PySide6.QtCore import QThread, Signal, QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication


# ----------------------------------------------------------------------------------------
# Настройки обновления (неизменяемые справочники)
# ----------------------------------------------------------------------------------------

# Правила выбора файла релиза для ОС: (слова в имени, окончания имени).
# Сначала ищется файл со словом ИЛИ окончанием, затем (запасной вариант) — только с окончанием.
ASSET_RULES: Mapping[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    'windows': (('windows',), ('.exe',)),
    'linux': (('linux',), ('.tar.gz',)),
}

# Расширение скачанного файла обновления для ОС
UPDATE_FILE_EXTENSIONS: Mapping[str, str] = {
    'windows': '.exe',
    'linux': '.tar.gz',
}

# ОС, для которых реализована автоматическая замена программы
AUTO_UPDATE_SYSTEMS = frozenset({'windows', 'linux'})
# AUTO_UPDATE_SYSTEMS = frozenset({'windows'})
# ↑ до 2026-11-07 (U20): на Linux автообновление только сообщало об отказе

# Размер блока при скачивании (256 КБ)
DOWNLOAD_CHUNK_SIZE = 262144

# Части номера версии: '1.2.3' → (1, 2, 3)
_VERSION_RE = re.compile(r'^\d+(\.\d+)*$')

# Строка хеша в описании релиза — как вывод sha256sum: '<64 hex>  <имя>' или '<64 hex> *<имя>'
_SHA256_LINE_RE = re.compile(r'^\s*([0-9a-fA-F]{64})\s+\*?(\S.*?)\s*$')

# Linux: файлы дистрибутива и самого обновления (метку и манифест пишет scripts/build_linux.sh)
LINUX_MARKER_FILE = '.medicalapp_dist'          # метка «установленный дистрибутив»
LINUX_MANIFEST_FILE = '.medicalapp_manifest'    # список файлов кода
LINUX_MANIFEST_HEADER = '# medicalapp manifest v1'  # первая строка манифеста (формат)
LINUX_VENV_DIR = 'venv_project_med'             # окружение (setup_prod.sh)
LINUX_RUN_SCRIPT = 'run.sh'                     # запуск программы
LINUX_VERSION_FILE = 'VERSION'                  # версия в дистрибутиве
LINUX_REQUIREMENTS_FILE = 'requirements.txt'    # пакеты
LINUX_UPDATE_SCRIPT = 'update.sh'               # скрипт замены
LINUX_UPDATE_LOG = 'update.log'                 # журнал скрипта
LINUX_WORK_PREFIX = '.update_'                  # .update_<метка> — распакованное обновление
LINUX_BACKUP_PREFIX = 'backup_'                 # backup_<версия> — прежний код
LINUX_IN_PROGRESS_FILE = '.update_in_progress'  # замена идёт или прервана
LINUX_FAILURE_FILE = '.update_failed'           # причина неудачи для окна
LINUX_WAIT_TIMEOUT_SEC = 120                    # сколько скрипт ждёт выхода программы
LINUX_MAX_UNPACKED_BYTES = 1024 ** 3            # предел распаковки (1 ГБ)
LINUX_START_CHECK_SEC = 60                      # сколько скрипт следит за запуском новой версии
LINUX_KEEP_MODES = ('count', 'days')            # как чистить старые backup_<версия>
LINUX_KEEP_MODE_DEFAULT = 'count'               # умолчание: по количеству
LINUX_KEEP_COUNT_DEFAULT = 3                    # сколько копий оставить
LINUX_KEEP_DAYS_DEFAULT = 30                    # сколько дней хранить

# Служебное обновления должно быть в любом дистрибутиве: без него скрипт не сработает
_LINUX_REQUIRED_FILES = (
    LINUX_MARKER_FILE,
    LINUX_MANIFEST_FILE,
    LINUX_RUN_SCRIPT,
    LINUX_VERSION_FILE,
)

# Что манифесту запрещено: данные и служебное. Это не список кода — код перечисляет сам манифест.
_LINUX_RESERVED_PARTS = frozenset({
    LINUX_VENV_DIR,
    '.git',
    '__pycache__',
    'photos',
    'logs',
    'logs_parser',
    'MedicalAppUpdates',
})
_LINUX_RESERVED_TOP_NAMES = frozenset({LINUX_UPDATE_SCRIPT, LINUX_UPDATE_LOG})
_LINUX_RESERVED_TOP_PREFIXES = (LINUX_WORK_PREFIX, LINUX_BACKUP_PREFIX)
_LINUX_RESERVED_SUFFIXES = (
    '.env',
    '.db', '.db-wal', '.db-shm', '.db-journal',
    '.sqlite', '.sqlite3',
    '.msgpack',
    '.log',
    '.part',
)
_LINUX_LOG_ROTATION_RE = re.compile(r'\.log\.\d+$')     # журнал после ротации: app.log.1
_LINUX_WORK_DIR_RE = re.compile(r'^\.update_\d+$')      # остаток прерванной попытки

# Тело update.sh; значения и списки путей подставляет build_linux_update_script (в начале файла).
# Все пути относительные: скрипт переходит в свою папку, путь установки в текст не попадает.
_LINUX_UPDATE_SCRIPT_BODY = r"""
RECOVER=0
PIP_STARTED=0
PROGRAM_PID=0
ALL_PATHS=("${NEW_PATHS[@]}" ${REMOVED_PATHS[@]+"${REMOVED_PATHS[@]}"})

log() {
    printf '%s [update.sh] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE" 2>/dev/null
}

# Жив ли процесс: зомби уже завершился (ждёт, пока его заберёт родитель)
process_alive() {
    kill -0 "$1" 2>/dev/null || return 1
    if grep -q '^State:[[:space:]]*Z' "/proc/$1/status" 2>/dev/null; then
        return 1
    fi
    return 0
}

parent_dir() {
    case "$1" in
        */*) printf '%s' "${1%/*}" ;;
        *)   printf '.' ;;
    esac
}

# Перенос одного пути: папка назначения создаётся, файл не попадает внутрь папки (-T)
move_path() {
    mkdir -p -- "$(parent_dir "$2")" 2>> "$LOG_FILE" \
        && mv -f -T -- "$1" "$2" 2>> "$LOG_FILE"
}

# Опустевшие папки вверх от файла: кэш байт-кода не считается, папка с данными остаётся
prune_empty_dirs() {
    local dir
    dir=$(parent_dir "$1")
    while [ "$dir" != "." ]; do
        if [ -d "$dir" ]; then
            if [ -n "$(ls -A -- "$dir" 2>/dev/null | grep -v -x '__pycache__')" ]; then
                return 0
            fi
            rm -rf -- "$dir/__pycache__"
            rmdir -- "$dir" 2>/dev/null || return 0
        fi
        dir=$(parent_dir "$dir")
    done
}

restart_program() {
    if command -v setsid > /dev/null 2>&1; then
        setsid nohup bash "./$RUN_SCRIPT" >> "$LOG_FILE" 2>&1 < /dev/null &
    else
        nohup bash "./$RUN_SCRIPT" >> "$LOG_FILE" 2>&1 < /dev/null &
    fi
    PROGRAM_PID=$!
}

# Запустилась ли новая версия: 0 — работает или закрыта штатно, иначе код её выхода.
# Остановка сигналом извне (закрыт сеанс, Ctrl+C, выключение) сбоем не считается
check_started() {
    local waited=0 status=0
    while [ "$waited" -lt "$((START_CHECK_SEC * 5))" ]; do
        if ! process_alive "$PROGRAM_PID"; then
            wait "$PROGRAM_PID" 2>/dev/null
            status=$?
            case "$status" in
                129|130|143) return 0 ;;
            esac
            return "$status"
        fi
        sleep 0.2
        waited=$((waited + 1))
    done
    return 0
}

# Старые копии кода: только папки вида backup_<версия>[_<метка>] (чужие папки с похожим именем не
# трогаются), текущая остаётся всегда. Ошибка удаления обновлению не мешает
prune_old_backups() {
    local entry name stamp index=0 now remove
    now=$(date +%s)
    while IFS= read -r -d '' entry; do
        stamp=${entry%% *}
        name=${entry#* }
        [[ "$name" =~ ^backup_[0-9]+(\.[0-9]+)*(_[0-9]+)?$ ]] || continue
        [ "$name" != "$BACKUP_DIR" ] || { index=$((index + 1)); continue; }
        index=$((index + 1))
        remove=0
        if [ "$KEEP_MODE" = "days" ]; then
            [ "$(( (now - ${stamp%%.*}) / 86400 ))" -lt "$KEEP_DAYS" ] || remove=1
        else
            [ "$index" -le "$KEEP_COUNT" ] || remove=1
        fi
        if [ "$remove" = 1 ]; then
            rm -rf -- "$name" 2>> "$LOG_FILE" && log "Удалена старая копия кода: $name"
        fi
    done < <(find . -maxdepth 1 -type d -name 'backup_*' -printf '%T@ %f\0' | sort -z -rn)
}

# Возврат прежней версии; повторный вызов безопасен (остановка на середине не портит результат)
rollback() {
    local rel status=0
    for rel in ${ADDED_PATHS[@]+"${ADDED_PATHS[@]}"}; do
        # Файл уже перенесён из обновления и прежнего такого не было — убрать (папка — не наша)
        if [ ! -e "$PAYLOAD_DIR/$rel" ] && [ ! -f "$BACKUP_DIR/$rel" ] && [ ! -L "$BACKUP_DIR/$rel" ] \
            && [ ! -d "$rel" ]; then
            rm -f -- "$rel" 2>> "$LOG_FILE" || status=1
            prune_empty_dirs "$rel"
        fi
    done
    for rel in "${ALL_PATHS[@]}"; do
        # Только файлы: путь может быть и папкой в backup_, если новый файл пришёл на место пакета
        if [ -f "$BACKUP_DIR/$rel" ] || [ -L "$BACKUP_DIR/$rel" ]; then
            move_path "$BACKUP_DIR/$rel" "$rel" || { log "Не возвращён файл: $rel"; status=1; }
        fi
    done
    if [ -d "$BACKUP_DIR" ]; then
        find "$BACKUP_DIR" -depth -type d -empty -delete 2>> "$LOG_FILE"
        [ ! -e "$BACKUP_DIR" ] || status=1
    fi
    if [ "$REQUIREMENTS_CHANGED" = 1 ] && { [ "$PIP_STARTED" = 1 ] || [ "$RECOVER" = 1 ]; } \
        && [ -x "$VENV_PYTHON" ] && [ -f "$REQUIREMENTS_FILE" ]; then
        # pip мог успеть заменить часть пакетов; всё на месте — сеть не нужна. Ошибка не мешает откату
        "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-input --retries 1 --timeout 15 \
            -r "$REQUIREMENTS_FILE" >> "$LOG_FILE" 2>&1 \
            || log "Пакеты прежней версии не восстановлены; при ошибках запуска выполните ./install.sh"
    fi
    return "$status"
}

# Ошибка замены: откат, сообщение для окна, запуск прежней версии
fail_and_rollback() {
    log "Ошибка: $1"
    if rollback; then
        printf 'Обновление до версии %s не установлено: %s. Возвращена версия %s. Подробности: %s\n' \
            "$NEW_VERSION" "$1" "$OLD_VERSION" "$LOG_FILE" > "$FAILURE_FILE"
        rm -rf -- "$WORK_DIR"
        rm -f -- "$IN_PROGRESS_FILE"
        log "Откат выполнен, версия $OLD_VERSION"
        if [ "$RECOVER" = 1 ]; then
            # run.sh сам продолжит запуск восстановленной версии
            rm -f -- "$SCRIPT_FILE"
            exit 0
        fi
        restart_program
        rm -f -- "$SCRIPT_FILE"
        exit 1
    fi
    log "ОТКАТ НЕ ВЫПОЛНЕН: прежний код остался в $BACKUP_DIR; повтор — при запуске $RUN_SCRIPT"
    printf 'Обновление до версии %s не установлено, и прежняя версия возвращена не полностью: прежний код в %s. Подробности: %s\n' \
        "$NEW_VERSION" "$BACKUP_DIR" "$LOG_FILE" > "$FAILURE_FILE"
    exit 2
}

# Запуск из run.sh после сбоя: откат; скрипт ещё работает — не мешать ему
if [ "${1:-}" = "--recover" ]; then
    RECOVER=1
    OWNER=$(head -n 1 "$IN_PROGRESS_FILE" 2>/dev/null)
    case "$OWNER" in
        ''|*[!0-9]*) ;;
        *)
            if [ "$OWNER" != "$$" ] && process_alive "$OWNER" \
                && tr '\0' ' ' < "/proc/$OWNER/cmdline" 2>/dev/null | grep -q "$SCRIPT_FILE"; then
                echo "Идёт обновление программы: дождитесь его окончания." >&2
                exit 3
            fi
            ;;
    esac
    fail_and_rollback "прервано сбоем или выключением"
fi

log "Обновление $OLD_VERSION -> $NEW_VERSION: ожидание выхода программы (PID $WAIT_PID)"
WAITED=0
while process_alive "$WAIT_PID"; do
    if [ "$WAITED" -ge "$((WAIT_TIMEOUT * 5))" ]; then
        # Программа работает: ничего не менялось, повторить можно с первого шага
        log "Программа не завершилась за $WAIT_TIMEOUT с: обновление отменено"
        printf 'Обновление до версии %s отменено: программа не завершилась.\n' "$NEW_VERSION" > "$FAILURE_FILE"
        rm -rf -- "$WORK_DIR"
        rm -f -- "$SCRIPT_FILE"
        exit 1
    fi
    sleep 0.2
    WAITED=$((WAITED + 1))
done

# С этого места сбой обнаружит run.sh: метка пишется на диск раньше первого переноса
if ! printf '%s\n' "$$" > "$IN_PROGRESS_FILE"; then
    log "Нельзя создать $IN_PROGRESS_FILE: обновление отменено"
    rm -rf -- "$WORK_DIR"
    restart_program
    rm -f -- "$SCRIPT_FILE"
    exit 1
fi
sync

mkdir -p -- "$BACKUP_DIR" 2>> "$LOG_FILE" || fail_and_rollback "не создана папка $BACKUP_DIR"
for rel in "${ALL_PATHS[@]}"; do
    # Только файлы и ссылки: папка на месте файла не переносится (внутри могут быть данные)
    if [ -f "$rel" ] || [ -L "$rel" ]; then
        move_path "$rel" "$BACKUP_DIR/$rel" || fail_and_rollback "не перенесён файл $rel"
    fi
done
for rel in ${REMOVED_PATHS[@]+"${REMOVED_PATHS[@]}"}; do
    prune_empty_dirs "$rel"
done
for rel in "${NEW_PATHS[@]}"; do
    move_path "$PAYLOAD_DIR/$rel" "$rel" || fail_and_rollback "не установлен файл $rel"
done
sync

if [ "$REQUIREMENTS_CHANGED" = 1 ]; then
    log "Изменился $REQUIREMENTS_FILE: установка пакетов"
    PIP_STARTED=1
    "$VENV_PYTHON" -m pip install --disable-pip-version-check --no-input --retries 2 --timeout 20 \
        -r "$REQUIREMENTS_FILE" >> "$LOG_FILE" 2>&1 \
        || fail_and_rollback "не удалось установить пакеты (нет сети или ошибка pip)"
fi
sync

rm -rf -- "$WORK_DIR"
rm -f -- "$IN_PROGRESS_FILE"
log "Установлена версия $NEW_VERSION; прежний код: $BACKUP_DIR"
restart_program

check_started
START_STATUS=$?
if [ "$START_STATUS" != 0 ]; then
    # Метка снова на диске: откат, прерванный сбоем, повторит run.sh
    printf '%s\n' "$$" > "$IN_PROGRESS_FILE" 2>> "$LOG_FILE"
    fail_and_rollback "новая версия не запустилась (код $START_STATUS). Если она успела обновить базу, прежняя версия откажется её открывать: копия базы до обновления лежит рядом с файлом базы (*.bak-*)"
fi

log "Новая версия запустилась"
prune_old_backups
rm -f -- "$SCRIPT_FILE"
exit 0
"""


# ----------------------------------------------------------------------------------------
# Функции без Qt
# ----------------------------------------------------------------------------------------

def get_app_dir() -> str:
    """
    Папка программы: где лежит exe (собранная) или этот модуль (из исходников).

    Returns:
        str: Абсолютный путь папки.

    Example:
        >>> os.path.isdir(get_app_dir())
        True
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def is_github_reachable(
    timeout: float = 3.0, # сколько ждать ответа, секунд
) -> bool:
    """
    Доступен ли GitHub API (короткий запрос ``/zen``).

    Блокирует вызывающий поток до ``timeout`` секунд — из потока интерфейса не вызывать.

    Args:
        timeout (float): Таймаут, секунд.

    Returns:
        bool: ``True`` — ответ 200.
    """

    try:
        req = urllib.request.Request(
            "https://api.github.com/zen",
            headers={"User-Agent": "MedicalApp/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200

    except Exception:
        return False


def normalize_version(
    tag: Optional[str], # тег релиза ('v1.2.3') или номер версии
) -> str:
    """
    Номер версии из тега релиза: без ``v``/``V`` впереди и пробелов.

    Args:
        tag (Optional[str]): Тег или номер.

    Returns:
        str: Номер версии (``''`` — тега нет).

    Example:
        >>> normalize_version('v1.2.3')
        '1.2.3'
        >>> normalize_version(' 1.0 ')
        '1.0'
        >>> normalize_version(None)
        ''
    """
    tag = (tag or '').strip()
    if tag[:1] in ('v', 'V'):
        tag = tag[1:]
    return tag


def parse_version(
    version: Optional[str], # номер версии или тег ('1.2.3', 'v1.2')
) -> Optional[Tuple[int, ...]]:
    """
    Номер версии → кортеж чисел для сравнения; завершающие нули отбрасываются.

    Args:
        version (Optional[str]): Номер или тег.

    Returns:
        Optional[Tuple[int, ...]]: Части номера; ``None`` — не номер версии
        (``'1.0-beta'``, ``''``).

    Example:
        >>> parse_version('v1.2.0')
        (1, 2)
        >>> parse_version('1.10')
        (1, 10)
        >>> parse_version('1.0-beta') is None
        True
    """
    text = normalize_version(version)
    if not _VERSION_RE.match(text):
        return None
    parts = [int(part) for part in text.split('.')]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer_version(
    current: str, # текущая версия программы
    latest: str, # версия (тег) последнего релиза
) -> bool:
    """
    Новее ли ``latest`` текущей версии.

    Сравнение по числам (``1.10`` новее ``1.9``), ``1.0`` и ``1.0.0`` — одна версия.
    Непонятный номер (``1.0-beta``) — обновления нет (безопаснее, чем предложить откат).

    Args:
        current (str): Текущая версия.
        latest (str): Версия релиза.

    Returns:
        bool: ``True`` — релиз новее.

    Example:
        >>> is_newer_version('1.9', '1.10')
        True
        >>> is_newer_version('2.0', '1.5')
        False
        >>> is_newer_version('1.0', '1.0.0')
        False
        >>> is_newer_version('1.0', 'beta')
        False
    """
    current_parts = parse_version(current)
    latest_parts = parse_version(latest)
    if current_parts is None or latest_parts is None:
        return False
    return latest_parts > current_parts


def mask_token(
    token: Optional[str], # токен (GitHub, Яндекс.Диск …)
) -> str:
    """
    Токен для журнала: только первые 4 символа и длина.

    Args:
        token (Optional[str]): Токен.

    Returns:
        str: ``'EMPTY'`` или ``'ghp_…(40)'``.

    Example:
        >>> mask_token('ghp_1234567890')
        'ghp_…(14)'
        >>> mask_token('')
        'EMPTY'
    """
    token = (token or '').strip()
    if not token:
        return 'EMPTY'
    return f'{token[:4]}…({len(token)})'


def github_headers(
    token: Optional[str], # токен GitHub (приватный репозиторий) или пусто
    accept: str, # тип ответа (Accept)
    user_agent: str = 'MedicalApp-Updater/1.0', # User-Agent (GitHub его требует)
) -> Dict[str, str]:
    """
    Заголовки запроса к GitHub.

    Args:
        token (Optional[str]): Токен; пустой — без авторизации.
        accept (str): Значение ``Accept``.
        user_agent (str): Значение ``User-Agent``.

    Returns:
        Dict[str, str]: Заголовки.

    Example:
        >>> github_headers('abc', 'application/json')['Authorization']
        'token abc'
        >>> 'Authorization' in github_headers(' ', 'application/json')
        False
    """
    headers = {
        'User-Agent': user_agent,
        'Accept': accept,
    }
    token = (token or '').strip()
    if token:
        headers['Authorization'] = f'token {token}'
    return headers


def current_system() -> str:
    """
    Имя текущей ОС в нижнем регистре (ключ :data:`ASSET_RULES` и др.).

    Returns:
        str: ``'windows'``, ``'linux'``, ``'darwin'`` …

    Example:
        >>> current_system() == platform.system().lower()
        True
    """
    return platform.system().lower()


def select_release_asset(
    assets: Optional[Iterable[Mapping[str, Any]]], # файлы релиза (release['assets'], None — нет)
    system: str, # ОС ('windows', 'linux' — ключ ASSET_RULES)
) -> Optional[Mapping[str, Any]]:
    """
    Файл релиза для ОС по :data:`ASSET_RULES`.

    Сначала — первый файл, в имени которого есть слово ОС или нужное окончание; если
    такого нет — первый файл с окончанием. Регистр не важен.

    Args:
        assets (Optional[Iterable[Mapping[str, Any]]]): Файлы релиза (поля ``name``,
            ``url`` …); ``None`` — файлов нет.
        system (str): ОС.

    Returns:
        Optional[Mapping[str, Any]]: Файл или ``None`` (нет подходящего или ОС неизвестна).

    Example:
        >>> assets = [{'name': 'notes.txt'}, {'name': 'MedicalApp-linux.tar.gz'}]
        >>> select_release_asset(assets, 'linux')['name']
        'MedicalApp-linux.tar.gz'
        >>> select_release_asset(assets, 'windows') is None
        True
    """
    rule = ASSET_RULES.get(system)
    if rule is None:
        return None
    keywords, suffixes = rule
    assets = list(assets or []) # 'assets': null в ответе GitHub — как пустой список

    def _name(
        asset : Mapping[str, Any],  # файл релиза
    ) -> str: # имя файла в нижнем регистре
        """Возвращает имя файла релиза в нижнем регистре (``''`` — имени нет)."""
        return str(asset.get('name', '')).lower()

    for asset in assets:
        name = _name(asset)
        if any(word in name for word in keywords) or name.endswith(suffixes):
            return asset
    for asset in assets:
        if _name(asset).endswith(suffixes):
            return asset
    return None


def update_file_name(
    system: str, # ОС (ключ UPDATE_FILE_EXTENSIONS)
    timestamp: int, # метка времени — уникальность имени
) -> str:
    """
    Имя файла скачанного обновления.

    Args:
        system (str): ОС.
        timestamp (int): Метка времени.

    Returns:
        str: ``MedicalApp_new_<метка><расширение ОС>`` (неизвестная ОС — без расширения).

    Example:
        >>> update_file_name('windows', 1)
        'MedicalApp_new_1.exe'
        >>> update_file_name('linux', 1)
        'MedicalApp_new_1.tar.gz'
    """
    return f'MedicalApp_new_{timestamp}{UPDATE_FILE_EXTENSIONS.get(system, "")}'


def parse_release_hashes(
    body : Optional[str],   # описание релиза GitHub (release['body']); None — описания нет
) -> Dict[str, str]: # хеши SHA-256 файлов релиза по именам
    """
    Находит в описании релиза строки хешей SHA-256 в формате вывода ``sha256sum``.

    Строка — ``<64 hex>  <имя файла>`` (``*<имя>`` — двоичный режим ``sha256sum -b``);
    остальной текст описания (заметки, ограды кода Markdown) пропускается. Путь перед
    именем (``artifacts/…/MedicalApp.exe``, ``dist\\…``) отбрасывается — ключ только имя
    файла. Хеш приводится к нижнему регистру. Имя встречается дважды — действует первая
    строка (строки ниже не могут подменить хеш, опубликованный сборкой).

    Функция только разбирает текст: не проверяет файлы и не ходит в сеть.

    Args:
        body : (str/None) Описание релиза; None или пустое — хешей нет.

    Returns:
        (Dict[str, str]) Имя файла → хеш (64 знака, нижний регистр); пустой — строк нет.

    Example:
        >>> parse_release_hashes(
        ...     body    =   '```\\n' + 'A' * 64 + '  MedicalApp.exe\\n```',  # описание релиза
        ... ) == {'MedicalApp.exe': 'a' * 64}
        True
        >>> parse_release_hashes(None)
        {}
    """
    hashes: Dict[str, str] = {}
    for line in (body or '').splitlines():
        match = _SHA256_LINE_RE.match(line)
        if not match:
            continue
        digest, path = match.groups()
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        if name and name not in hashes: # первая строка для имени — главная
            hashes[name] = digest.lower()
    return hashes


def release_asset_sha256(
    release_data : Optional[Mapping[str, Any]],     # данные релиза GitHub; None — нет данных
    asset_name   : str,                             # имя файла релиза (asset['name'])
) -> Optional[str]: # опубликованный хеш файла релиза
    """
    Возвращает опубликованный в описании релиза хеш SHA-256 файла ``asset_name``.

    Хеши берутся из ``release_data['body']`` (:func:`parse_release_hashes`); имя
    сравнивается без учёта регистра — как при выборе файла (:func:`select_release_asset`).

    Args:
        release_data : (Mapping/None) Данные релиза (поле ``body``); None — хеша нет.
        asset_name   : (str) Имя выбранного файла релиза.

    Returns:
        (str/None) Хеш (64 знака, нижний регистр); None — в описании нет строки для файла.

    Example:
        >>> release_asset_sha256(
        ...     release_data    =   {'body': 'b' * 64 + '  MedicalApp-linux.tar.gz'},  # релиз
        ...     asset_name      =   'MedicalApp-linux.tar.gz',                         # файл
        ... ) == 'b' * 64
        True
        >>> release_asset_sha256({'body': None}, 'MedicalApp.exe') is None
        True
    """
    hashes = parse_release_hashes(
        (release_data or {}).get('body'),  # описание релиза
    )
    wanted = (asset_name or '').lower()
    for name, digest in hashes.items():
        if name.lower() == wanted:
            return digest
    return None


def file_sha256(
    path       : str,                           # файл
    chunk_size : int = DOWNLOAD_CHUNK_SIZE,     # размер порции чтения, байт
) -> str: # хеш SHA-256 файла
    """
    Считает SHA-256 файла порциями (файл обновления целиком в память не читается).

    Args:
        path       : (str) Путь к файлу.
        chunk_size : (int) Размер порции чтения, байт.

    Returns:
        (str) Хеш — 64 знака, нижний регистр.

    Raises:
        OSError: Файла нет или он не читается.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     path = os.path.join(folder, 'f.bin')
        ...     with open(path, 'wb') as f:
        ...         _ = f.write(b'abc')
        ...     file_sha256(
        ...         path        =   path,   # файл
        ...         chunk_size  =   2,      # порция меньше файла
        ...     )
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    """
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_windows_update_script(
    old_exe: str, # имя текущего exe (в папке программы)
    new_exe: str, # имя скачанного exe (в той же папке)
    log_file: str, # имя журнала скрипта
) -> str:
    """
    Скрипт PowerShell замены программы.

    Ждёт 3 с, завершает процессы со старым именем, удаляет старый exe и запускает новый
    с ``--rename-to <старое имя>`` (переименование — ``main_gui_window.handle_rename_argument``),
    затем удаляет себя. Работает в папке программы (относительные имена).

    Args:
        old_exe (str): Имя текущего exe.
        new_exe (str): Имя нового exe.
        log_file (str): Имя журнала.

    Returns:
        str: Текст скрипта.

    Example:
        >>> '--rename-to' in build_windows_update_script('A.exe', 'B.exe', 'u.log')
        True
    """
    return f'''
$old = "{old_exe}"
$new = "{new_exe}"
$log = "{log_file}"

function Write-Log {{ param($msg) Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $msg" }}

Write-Log "Update script started"
Start-Sleep -Seconds 3

Write-Log "Terminating old process(es)"
$proc = Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($old)) -ErrorAction SilentlyContinue
if ($proc) {{
    $proc | Stop-Process -Force
    do {{
        Start-Sleep -Milliseconds 500
        $stillRunning = Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($old)) -ErrorAction SilentlyContinue
        if ($stillRunning) {{ Write-Log "Still waiting..." }}
    }} while ($stillRunning)
    Write-Log "All processes terminated"
}} else {{
    Write-Log "No running process found"
}}

if (Test-Path $old) {{
    Write-Log "Deleting old executable"
    Remove-Item -Path $old -Force
}} else {{
    Write-Log "Old file not found, skipping delete"
}}

Write-Log "Starting new version with rename instruction"
Start-Process -FilePath $new -ArgumentList "--rename-to `"$old`"" -WindowStyle Normal

Write-Log "Cleaning up script"
Start-Sleep -Seconds 2
Remove-Item -Path $MyInvocation.MyCommand.Path -Force
'''


def auto_update_unavailable_reason(
    system: str, # ОС
    frozen: bool, # программа собрана (exe), а не запущена из исходников
) -> Optional[str]:
    """
    Почему автоматическая замена программы невозможна (проверка ДО скачивания).

    Args:
        system (str): ОС.
        frozen (bool): Собранная программа.

    Returns:
        Optional[str]: Текст для пользователя; ``None`` — замена возможна.

    Example:
        >>> auto_update_unavailable_reason('windows', True) is None
        True
        >>> auto_update_unavailable_reason('windows', False)
        'Автообновление работает только в собранном приложении'
        >>> 'собранной Linux-версии' in auto_update_unavailable_reason('linux', True)
        True
    """
    if system == 'linux' and system in AUTO_UPDATE_SYSTEMS: # код заменяется из архива, а не exe
        return linux_install_unavailable_reason(
            install_root    =   get_install_root(),     # папка установки
            frozen          =   frozen,                 # собранная программа
        )
    if not frozen:
        return 'Автообновление работает только в собранном приложении'
    if system not in AUTO_UPDATE_SYSTEMS:
        return (
            f'Автообновление пока доступно только для Windows и Linux (у вас {system or "неизвестная ОС"}). '
            'Скачайте новую версию со страницы релиза.'
        )
    # if not frozen:
    #     return 'Автообновление работает только в собранном приложении'
    # if system not in AUTO_UPDATE_SYSTEMS:
    #     return (
    #         f'Автообновление пока доступно только для Windows (у вас {system or "неизвестная ОС"}). '
    #         'Скачайте новую версию со страницы релиза.'
    #     )
    # ↑ до 2026-11-07 (U20): Linux-версия работает из исходников (нет frozen) — обновление всегда
    #   останавливалось на «только в собранном приложении»
    return None


# ----------------------------------------------------------------------------------------
# Linux: замена кода из архива .tar.gz скриптом после выхода (app/UPDATER.md, раздел 1.3)
# ----------------------------------------------------------------------------------------

class UpdateError(Exception):
    """
    Обновление нельзя установить; текст исключения показывается пользователю.

    Example:
        >>> str(UpdateError('Нет прав на запись'))
        'Нет прав на запись'
    """


# разбор пути файла из архива или манифеста на части
def _relative_path_parts(
    path : str,  # путь внутри архива или манифеста
) -> Tuple[str, ...]: # части пути без '.'
    """
    Разбирает относительный путь на части и отклоняет всё, что может выйти за папку.

    Отклоняются: пустой путь, абсолютный, ``..`` в любом месте, обратная косая черта,
    управляющие символы (манифест построчный) и имена не в UTF-8. Части ``.`` отбрасываются.
    Чтение диска и проверка «данные или код» — не здесь (:func:`validate_manifest_path`).

    Args:
        path : (str) Путь с разделителем ``/``.

    Returns:
        (Tuple[str, ...]) Части пути.

    Raises:
        UpdateError: Путь небезопасен.

    Example:
        >>> _relative_path_parts('app/./a.py')
        ('app', 'a.py')
        >>> _relative_path_parts('../a.py')
        Traceback (most recent call last):
        ...
        app.updater.UpdateError: Недопустимый путь в обновлении: '../a.py'
    """
    error = UpdateError(f'Недопустимый путь в обновлении: {path!r}')
    if not path or path.startswith('/') or '\\' in path:
        raise error
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        raise error
    try:
        path.encode('utf-8')
    except UnicodeEncodeError:
        raise error from None # имя не в UTF-8 (суррогаты tarfile)
    parts = tuple(part for part in path.split('/') if part not in ('', '.'))
    if not parts or '..' in parts:
        raise error
    return parts


# проверка одного пути манифеста: только код, не данные
def validate_manifest_path(
    path : str,  # строка манифеста
) -> str: # тот же путь, если он допустим
    """
    Проверяет путь манифеста: относительный, внутри установки и не указывает на данные.

    Запрещены части ``venv_project_med``, ``.git``, ``photos``, ``logs``, ``logs_parser``,
    ``__pycache__``, ``MedicalAppUpdates``, папки ``photos*``, на верхнем уровне — служебное
    самого обновления (``.update_*``, ``backup_*``, ``update.sh``, ``update.log``), файлы баз,
    настроек и журналов по окончанию (``.db``, ``.env``, ``.msgpack``, ``.log`` и др.). Путь
    должен быть уже приведён: ``a//b`` и ``./a`` отклоняются, потому что их строит только
    чужой манифест, а не ``build_linux.sh``.

    Здесь перечислены данные, а не код: список файлов кода задаёт сам манифест.

    Args:
        path : (str) Путь файла относительно папки установки.

    Returns:
        (str) ``path`` без изменений.

    Raises:
        UpdateError: Путь небезопасен или указывает на данные.

    Example:
        >>> validate_manifest_path('parsers/word_importer.py')
        'parsers/word_importer.py'
        >>> validate_manifest_path('parsers/logs/a.txt')
        Traceback (most recent call last):
        ...
        app.updater.UpdateError: Манифест обновления указывает на данные: 'parsers/logs/a.txt'
    """
    parts = _relative_path_parts(path)
    if '/'.join(parts) != path:
        raise UpdateError(f'Недопустимый путь в обновлении: {path!r}')

    name = parts[-1]
    reserved = (
        any(part in _LINUX_RESERVED_PARTS for part in parts)
        or any(part.startswith('photos') for part in parts[:-1]) # как photos*/ в .gitignore
        or name.endswith(_LINUX_RESERVED_SUFFIXES)
        or _LINUX_LOG_ROTATION_RE.search(name) is not None
        or parts[0] in _LINUX_RESERVED_TOP_NAMES
        or parts[0].startswith(_LINUX_RESERVED_TOP_PREFIXES)
    )
    if reserved:
        raise UpdateError(f'Манифест обновления указывает на данные: {path!r}')
    return path


# разбор текста манифеста
def parse_linux_manifest(
    text : str,  # содержимое файла манифеста
) -> Tuple[str, ...]: # пути файлов кода
    """
    Разбирает манифест путей кода, который пишет ``scripts/build_linux.sh``.

    Формат: первая строка — :data:`LINUX_MANIFEST_HEADER` (другой формат — отказ), дальше по
    одному пути файла на строку, ``/`` как разделитель. Перечислены только файлы, а не папки:
    в папках кода рядом с модулями лежат данные (``parsers/logs``, ``parsers/photos``), и
    заменяется только то, что перечислено.

    Обязательны служебные файлы обновления (:data:`_LINUX_REQUIRED_FILES`). Запрещены повторы
    и путь, который одновременно файл и папка другого пути.

    Args:
        text : (str) Текст манифеста.

    Returns:
        (Tuple[str, ...]) Пути в порядке манифеста.

    Raises:
        UpdateError: Формат неверен, путь недопустим, нет обязательного файла.

    Example:
        >>> parse_linux_manifest('\\n'.join([
        ...     LINUX_MANIFEST_HEADER,
        ...     LINUX_MANIFEST_FILE,
        ...     LINUX_MARKER_FILE,
        ...     'VERSION',
        ...     'run.sh',
        ...     'app/a.py',
        ... ]))[-1]
        'app/a.py'
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != LINUX_MANIFEST_HEADER:
        raise UpdateError('Манифест обновления имеет неизвестный формат')

    paths = []
    seen = set()
    for line in lines[1:]:
        if not line: # пустая строка в конце файла
            continue
        validate_manifest_path(line)
        if line in seen:
            raise UpdateError(f'Манифест обновления содержит путь дважды: {line!r}')
        seen.add(line)
        paths.append(line)

    for path in paths:
        parts = path.split('/')
        for depth in range(1, len(parts)):
            if '/'.join(parts[:depth]) in seen: # файл и одновременно папка
                raise UpdateError(f'Манифест обновления противоречив: {path!r}')

    missing = [name for name in _LINUX_REQUIRED_FILES if name not in seen]
    if missing:
        raise UpdateError(f'В манифесте обновления нет обязательных файлов: {", ".join(missing)}')
    return tuple(paths)


# чтение манифеста из папки
def read_linux_manifest(
    folder : str,  # папка установки или распакованного обновления
) -> Tuple[str, ...]: # пути файлов кода
    """
    Читает и проверяет манифест из папки (:func:`parse_linux_manifest`).

    Args:
        folder : (str) Папка, в которой лежит :data:`LINUX_MANIFEST_FILE`.

    Returns:
        (Tuple[str, ...]) Пути файлов кода.

    Raises:
        UpdateError: Файла нет, это ссылка, он не читается или неверен.

    Example:
        >>> try:
        ...     read_linux_manifest('/нет/такой/папки')
        ... except UpdateError as e:
        ...     str(e).startswith('Не удалось прочитать манифест')
        True
    """
    path = os.path.join(folder, LINUX_MANIFEST_FILE)
    try:
        if os.path.islink(path):
            raise OSError('ссылка вместо файла')
        with open(path, 'r', encoding='utf-8', newline='\n') as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise UpdateError(f'Не удалось прочитать манифест обновления: {path}') from e
    return parse_linux_manifest(text)


# как чистить старые копии кода: значения из настроек с проверкой
def linux_backup_keep_settings(
    config : Any,  # объект с методом get(ключ, умолчание): настройки программы
) -> Tuple[str, int, int]: # способ, сколько копий, сколько дней
    """
    Читает из настроек, как чистить старые ``backup_<версия>``.

    Неверное значение (испорченный файл настроек) заменяется умолчанием, а не ломает обновление:
    запись обновления важнее, чем очистка старых копий. Меньше одной копии или одного дня быть не
    может: только что созданную копию скрипт оставляет всегда.

    Args:
        config : (Any) Настройки: ``UPDATE_BACKUP_KEEP_MODE``, ``UPDATE_BACKUP_KEEP_COUNT``,
            ``UPDATE_BACKUP_KEEP_DAYS``.

    Returns:
        (Tuple[str, int, int]) Способ (``count`` / ``days``), количество копий, дней.

    Example:
        >>> linux_backup_keep_settings({'UPDATE_BACKUP_KEEP_MODE': 'days', 'UPDATE_BACKUP_KEEP_DAYS': 7})
        ('days', 3, 7)
        >>> linux_backup_keep_settings({'UPDATE_BACKUP_KEEP_MODE': '?', 'UPDATE_BACKUP_KEEP_COUNT': 0})
        ('count', 3, 30)
    """
    # целое не меньше 1; иначе умолчание
    def positive(
        key     : str,  # ключ настройки
        default : int,  # умолчание
    ) -> int:
        try:
            value = int(config.get(key, default))
        except (TypeError, ValueError):
            return default
        return value if value >= 1 else default

    mode = config.get('UPDATE_BACKUP_KEEP_MODE', LINUX_KEEP_MODE_DEFAULT)
    return (
        mode if mode in LINUX_KEEP_MODES else LINUX_KEEP_MODE_DEFAULT,
        positive('UPDATE_BACKUP_KEEP_COUNT', LINUX_KEEP_COUNT_DEFAULT),
        positive('UPDATE_BACKUP_KEEP_DAYS', LINUX_KEEP_DAYS_DEFAULT),
    )


# корень установки: от запущенной программы, путь нигде не зашит
def get_install_root() -> str:
    """
    Возвращает папку установки: родитель ``app/`` (из исходников) или папку exe (собранная).

    Определяется по расположению этого модуля, поэтому не зависит ни от текущей папки, ни от
    того, какой файл запущен, и работает в любой папке, куда разархивировали программу.

    Returns:
        (str) Абсолютный путь папки.

    Example:
        >>> os.path.basename(get_app_dir()) == 'app' and get_install_root() == os.path.dirname(get_app_dir())
        True
    """
    app_dir = get_app_dir()
    if getattr(sys, 'frozen', False):
        return app_dir
    return os.path.dirname(app_dir)


# первая папка кода или сама установка, куда нельзя писать
def _first_unwritable_dir(
    install_root : str,               # папка установки
    paths        : Iterable[str],     # пути файлов кода относительно неё
) -> Optional[str]: # папка без права записи; None — все доступны
    """
    Находит папку, в которой нельзя переносить файлы кода.

    Для папки установки дополнительно создаётся и удаляется пробный файл: ``os.access`` не
    всегда видит файловую систему только для чтения или ограничения доступа.

    Args:
        install_root : (str) Папка установки.
        paths        : (Iterable[str]) Пути файлов кода.

    Returns:
        (str/None) Первая недоступная папка; None — все доступны.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     _first_unwritable_dir(
        ...         install_root    =   folder,         # папка установки
        ...         paths           =   ['app/a.py'],   # папки app ещё нет
        ...     ) is None
        True
    """
    try:
        with tempfile.NamedTemporaryFile(
            dir     =   install_root,       # проверяемая папка
            prefix  =   '.update_probe_',   # не совпадает с остатками .update_<число>
        ):
            pass
    except OSError:
        return install_root

    folders = set()
    for path in paths:
        parts = path.split('/')
        for depth in range(1, len(parts)):
            folders.add(os.path.join(install_root, *parts[:depth]))
    for folder in sorted(folders):
        if os.path.isdir(folder) and not os.access(folder, os.W_OK | os.X_OK):
            return folder
    return None


# проверка возможности автообновления Linux-версии до скачивания
def linux_install_unavailable_reason(
    install_root : str,   # папка установки
    frozen       : bool,  # программа собрана в бинарник
) -> Optional[str]: # текст для пользователя; None — можно обновлять
    """
    Объясняет, почему Linux-версию нельзя обновить автоматически (проверка ДО скачивания).

    Порядок: собранный бинарник (такой сборки нет, заменяется код из архива) → рабочая копия
    разработчика (``.git`` — папка или файл, как в копии ``git worktree``) → нет метки или
    манифеста дистрибутива → незавершённое обновление → нет прав на запись.

    Args:
        install_root : (str) Папка установки.
        frozen       : (bool) Программа собрана в бинарник.

    Returns:
        (str/None) Причина; None — обновление возможно.

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     os.mkdir(os.path.join(folder, '.git'))
        ...     linux_install_unavailable_reason(
        ...         install_root    =   folder,     # папка с .git
        ...         frozen          =   False,      # из исходников
        ...     ).startswith('Это рабочая копия')
        True
    """
    manual = 'Скачайте новую версию со страницы релиза и обновите вручную.'
    if frozen:
        return f'Автообновление собранной Linux-версии не поддерживается. {manual}'
    if os.path.lexists(os.path.join(install_root, '.git')):
        return (
            'Это рабочая копия разработчика (есть .git): автообновление отключено, '
            'обновляйте её через git.'
        )
    marker = os.path.join(install_root, LINUX_MARKER_FILE)
    if os.path.islink(marker) or not os.path.isfile(marker):
        return f'Программа запущена не из установленного дистрибутива. {manual}'
    try:
        paths = read_linux_manifest(install_root)
    except UpdateError as e:
        return f'{e}. {manual}'
    if os.path.lexists(os.path.join(install_root, LINUX_IN_PROGRESS_FILE)):
        return 'Предыдущее обновление не завершено: перезапустите программу через run.sh.'
    unwritable = _first_unwritable_dir(
        install_root    =   install_root,   # папка установки
        paths           =   paths,          # файлы кода
    )
    if unwritable:
        return (
            f'Нет прав на запись в папку программы ({unwritable}): автоматически обновить '
            f'нельзя. {manual}'
        )
    return None


# безопасная распаковка архива обновления
def safe_extract_tar(
    archive_path    : str,                              # файл .tar.gz
    dest_dir        : str,                              # существующая пустая папка
    max_total_bytes : int = LINUX_MAX_UNPACKED_BYTES,   # предел суммарного размера файлов
) -> str: # имя единственной папки верхнего уровня
    """
    Распаковывает архив обновления со своей проверкой (``filter='data'`` есть не во всех 3.10).

    Сначала проверяются ВСЕ записи (ничего не пишется), затем пишутся файлы. Допускаются только
    обычные файлы и папки внутри одной папки верхнего уровня: отклоняются абсолютные пути,
    ``..``, ссылки (символьные и жёсткие — в дистрибутиве их нет, поэтому и наружу они указать
    не могут), устройства, каналы, разреженные файлы, повторы. Запись — с ``O_EXCL`` и
    нормализованными правами (без setuid), время изменения сохраняется.

    Args:
        archive_path    : (str) Файл архива.
        dest_dir        : (str) Папка распаковки.
        max_total_bytes : (int) Предел суммы размеров файлов, байт (защита от распаковки на
            весь диск, если релиз без хеша).

    Returns:
        (str) Имя папки верхнего уровня.

    Raises:
        UpdateError: Архив повреждён или содержит недопустимую запись.

    Example:
        >>> import io, tarfile, tempfile
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     archive = os.path.join(folder, 'a.tar.gz')
        ...     with tarfile.open(archive, 'w:gz') as tar:
        ...         info = tarfile.TarInfo('top/a.txt')
        ...         info.size = 1
        ...         tar.addfile(info, io.BytesIO(b'x'))
        ...     os.mkdir(os.path.join(folder, 'dest'))
        ...     safe_extract_tar(
        ...         archive_path    =   archive,                        # архив
        ...         dest_dir        =   os.path.join(folder, 'dest'),   # куда
        ...     )
        'top'
    """
    try:
        with tarfile.open(
            archive_path,           # архив
            mode    =   'r:gz',     # только сжатый tar
        ) as tar:
            members = tar.getmembers()
            top_names = set()
            seen = set()
            total = 0
            checked = []
            for member in members:
                parts = _relative_path_parts(member.name)
                if not (member.isreg() or member.isdir()) or member.issparse():
                    raise UpdateError(f'Недопустимый тип файла в обновлении: {member.name!r}')
                if member.isreg() and len(parts) < 2:
                    raise UpdateError(f'Файл вне папки дистрибутива: {member.name!r}')
                relative = '/'.join(parts)
                if relative in seen and not member.isdir():
                    raise UpdateError(f'Файл повторяется в обновлении: {member.name!r}')
                seen.add(relative)
                top_names.add(parts[0])
                total += member.size if member.isreg() else 0
                checked.append((member, parts))

            if len(top_names) != 1:
                raise UpdateError('В архиве обновления должна быть одна папка верхнего уровня')
            if total > max_total_bytes:
                raise UpdateError('Архив обновления слишком большой')

            for member, parts in checked:
                target = os.path.join(dest_dir, *parts)
                if member.isdir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise UpdateError(f'Не удалось прочитать файл обновления: {member.name!r}')
                descriptor = os.open(
                    target,                                     # файл
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0),  # только новый файл
                    (member.mode & 0o755) | 0o600,              # без setuid, владелец читает и пишет
                )
                with source, os.fdopen(descriptor, 'wb') as out:
                    shutil.copyfileobj(source, out, DOWNLOAD_CHUNK_SIZE)
                os.utime(target, (member.mtime, member.mtime)) # кэш байт-кода сверяет время файла
    except UpdateError:
        raise
    except (tarfile.TarError, EOFError, OSError, zlib.error) as e:
        raise UpdateError(f'Архив обновления повреждён или не распаковывается: {e}') from e
    return top_names.pop()


# сверка распакованного обновления с его манифестом
def check_unpacked_update(
    payload_dir : str,  # распакованная папка дистрибутива
) -> Tuple[str, ...]: # пути файлов кода из манифеста
    """
    Проверяет состав распакованного обновления: файлы на диске ровно те, что в манифесте.

    Отсутствующий файл сломал бы программу; лишний молча потерялся бы при замене, поэтому оба
    случая — отказ. Метка — обычный файл. Ссылок быть не должно (их не пропускает и
    :func:`safe_extract_tar`; проверка на случай другого способа распаковки).

    Args:
        payload_dir : (str) Папка дистрибутива.

    Returns:
        (Tuple[str, ...]) Пути манифеста.

    Raises:
        UpdateError: Состав не совпал.

    Example:
        >>> try:
        ...     check_unpacked_update('/нет/такой/папки')
        ... except UpdateError as e:
        ...     str(e).startswith('Не удалось прочитать манифест')
        True
    """
    paths = read_linux_manifest(payload_dir)
    on_disk = set()
    for folder, dir_names, file_names in os.walk(payload_dir):
        for name in dir_names + file_names:
            full = os.path.join(folder, name)
            if os.path.islink(full):
                raise UpdateError(f'В обновлении есть ссылка: {name!r}')
        for name in file_names:
            relative = os.path.relpath(os.path.join(folder, name), payload_dir)
            on_disk.add(relative.replace(os.sep, '/'))
    wanted = set(paths)
    missing = sorted(wanted - on_disk)
    extra = sorted(on_disk - wanted)
    if missing:
        raise UpdateError(f'В обновлении нет файлов из манифеста: {", ".join(missing[:5])}')
    if extra:
        raise UpdateError(f'В обновлении есть файлы вне манифеста: {", ".join(extra[:5])}')
    return paths


# строка оболочки: присваивание массива с экранированием каждого значения
def _shell_array(
    name   : str,            # имя массива
    values : Iterable[str],  # значения
) -> str: # строки присваивания
    """
    Строит присваивание массива bash; каждое значение экранируется ``shlex.quote``.

    Args:
        name   : (str) Имя массива.
        values : (Iterable[str]) Значения.

    Returns:
        (str) Текст присваивания.

    Example:
        >>> print(_shell_array('A', ["x y", "o'k"]))
        A=(
            'x y'
            'o'"'"'k'
        )
    """
    lines = [f'{name}=(']
    lines.extend(f'    {shlex.quote(value)}' for value in values)
    lines.append(')')
    return '\n'.join(lines)


# текст скрипта update.sh
def build_linux_update_script(
    wait_pid             : int,            # PID программы, выхода которой ждать
    old_version          : str,            # текущая версия
    new_version          : str,            # устанавливаемая версия
    work_dir             : str,            # .update_<метка> относительно установки
    payload_dir          : str,            # распакованный дистрибутив относительно установки
    backup_dir           : str,            # backup_<версия> относительно установки
    new_paths            : Iterable[str],  # файлы кода новой версии
    removed_paths        : Iterable[str],  # файлы прежней версии, которых нет в новой
    added_paths          : Iterable[str],  # файлы новой версии, которых не было на диске
    requirements_changed : bool,           # requirements.txt изменился — нужен pip
    wait_timeout         : int = LINUX_WAIT_TIMEOUT_SEC,  # сколько ждать выхода, секунд
    keep_mode            : str = LINUX_KEEP_MODE_DEFAULT,   # как чистить старые копии кода
    keep_count           : int = LINUX_KEEP_COUNT_DEFAULT,  # сколько копий оставить (count)
    keep_days            : int = LINUX_KEEP_DAYS_DEFAULT,   # сколько дней хранить (days)
    start_check_sec      : int = LINUX_START_CHECK_SEC,     # сколько следить за запуском, секунд
) -> str: # текст скрипта
    """
    Формирует ``update.sh``: замена кода после выхода программы, откат, перезапуск.

    Порядок работы скрипта:
        1. переходит в свою папку (``${0%/*}``): полный путь установки в текст не попадает,
           поэтому пробел, кириллица, кавычка и ``$`` в нём ничего не ломают, а все дальнейшие
           пути — относительные;
        2. ждёт выхода процесса (зомби считается вышедшим); не дождался за ``wait_timeout`` —
           ничего не меняет, убирает ``.update_<метка>`` и завершается;
        3. создаёт ``.update_in_progress`` (с ним ``run.sh`` после сбоя запускает ``--recover``);
        4. переносит файлы прежней версии в ``backup_<версия>/`` — только файлы из манифестов;
           данные в папках кода остаются на месте;
        5. убирает опустевшие папки удалённых модулей (в папке только ``__pycache__`` — считается
           пустой; папка с данными остаётся) и кладёт новые файлы (``mv -T``);
        6. при ``requirements_changed`` — ``venv_project_med/bin/python -m pip install -r``;
        7. убирает временное, запускает ``run.sh`` (``setsid`` / ``nohup``; ``DISPLAY`` и
           ``WAYLAND_DISPLAY`` наследуются);
        8. следит за процессом ``start_check_sec`` секунд: новая версия сама завершилась с ошибкой
           (не сигналом извне) — откат; работает или закрыта штатно — успех;
        9. при успехе чистит старые копии кода (:func:`linux_backup_keep_settings`), удаляет себя.
    Ошибка на шагах 4–6 и 8 — откат: файлы из ``backup_`` возвращаются, добавленные удаляются,
    пустой ``backup_`` убирается, причина пишется в ``.update_failed``, запускается прежняя
    версия. Откат можно повторять (``--recover`` после сбоя питания посреди шага 4–6). Если
    откат не удался, скрипт, ``.update_in_progress`` и ``backup_`` остаются: ``run.sh`` повторит.

    Note:
        Откат на шаге 8 возвращает только код. База, которую новая версия успела обновить, остаётся
        новой: прежняя версия откажется её открывать с понятным сообщением (``migrate``,
        ``_ensure_known_revision``), а копия базы до обновления лежит рядом с файлом базы.

    ``pip`` вызывается как ``python -m pip``, а не ``bin/pip``: у скрипта ``bin/pip`` в первой
    строке зашит путь, и после переименования папки установки он перестаёт запускаться.

    Функция только строит текст: файлы не трогает, значения экранирует.

    Args:
        wait_pid             : (int) PID программы.
        old_version          : (str) Текущая версия.
        new_version          : (str) Новая версия.
        work_dir             : (str) Временная папка относительно установки.
        payload_dir          : (str) Папка дистрибутива относительно установки.
        backup_dir           : (str) Папка прежней версии относительно установки.
        new_paths            : (Iterable[str]) Файлы новой версии.
        removed_paths        : (Iterable[str]) Файлы, которых в новой версии нет.
        added_paths          : (Iterable[str]) Файлы, которых раньше не было на диске.
        requirements_changed : (bool) Запускать ли pip.
        wait_timeout         : (int) Сколько ждать выхода программы, секунд.
        keep_mode            : (str) Как чистить старые копии: ``count`` или ``days``.
        keep_count           : (int) Сколько копий оставить при ``count``.
        keep_days            : (int) Сколько дней хранить при ``days``.
        start_check_sec      : (int) Сколько следить за запуском новой версии, секунд.

    Returns:
        (str) Текст скрипта bash.

    Example:
        >>> text = build_linux_update_script(
        ...     wait_pid                =   123,                    # PID
        ...     old_version             =   '1.0.0',                # было
        ...     new_version             =   '1.1.0',                # стало
        ...     work_dir                =   '.update_1',            # временная папка
        ...     payload_dir             =   '.update_1/top',        # дистрибутив
        ...     backup_dir              =   'backup_1.0.0',         # прежняя версия
        ...     new_paths               =   ['run.sh', 'a b.py'],   # новые файлы
        ...     removed_paths           =   [],                     # удалённых нет
        ...     added_paths             =   [],                     # добавленных нет
        ...     requirements_changed    =   False,                  # pip не нужен
        ... )
        >>> "'a b.py'" in text and 'WAIT_PID=123' in text
        True
    """
    new_paths = list(new_paths)
    header = [
        '#!/bin/bash',
        '# Замена кода Linux-версии после выхода программы. Сформирован app/updater.py',
        '# (build_linux_update_script); пути относительно папки этого файла.',
        'set -u',
        'case "$0" in */*) cd -- "${0%/*}" || exit 1 ;; esac',
        '',
        f'WAIT_PID={int(wait_pid)}',
        f'WAIT_TIMEOUT={int(wait_timeout)}',
        f'START_CHECK_SEC={int(start_check_sec)}',
        f'KEEP_MODE={shlex.quote(keep_mode)}',
        f'KEEP_COUNT={int(keep_count)}',
        f'KEEP_DAYS={int(keep_days)}',
        f'OLD_VERSION={shlex.quote(old_version)}',
        f'NEW_VERSION={shlex.quote(new_version)}',
        f'WORK_DIR={shlex.quote(work_dir)}',
        f'PAYLOAD_DIR={shlex.quote(payload_dir)}',
        f'BACKUP_DIR={shlex.quote(backup_dir)}',
        f'REQUIREMENTS_CHANGED={1 if requirements_changed else 0}',
        f'LOG_FILE={shlex.quote(LINUX_UPDATE_LOG)}',
        f'IN_PROGRESS_FILE={shlex.quote(LINUX_IN_PROGRESS_FILE)}',
        f'FAILURE_FILE={shlex.quote(LINUX_FAILURE_FILE)}',
        f'SCRIPT_FILE={shlex.quote(LINUX_UPDATE_SCRIPT)}',
        f'RUN_SCRIPT={shlex.quote(LINUX_RUN_SCRIPT)}',
        f'REQUIREMENTS_FILE={shlex.quote(LINUX_REQUIREMENTS_FILE)}',
        f'VENV_PYTHON={shlex.quote(LINUX_VENV_DIR + "/bin/python")}',
        _shell_array('NEW_PATHS', new_paths),
        _shell_array('REMOVED_PATHS', removed_paths),
        _shell_array('ADDED_PATHS', added_paths),
        '',
    ]
    return '\n'.join(header) + _LINUX_UPDATE_SCRIPT_BODY


# итог подготовки обновления
@dataclass(frozen=True)
class LinuxUpdatePlan:
    """
    Подготовленное обновление Linux-версии (результат :func:`prepare_linux_update`).

    Attributes:
        script_path          : (str) Полный путь ``update.sh``.
        work_dir             : (str) Полный путь ``.update_<метка>``.
        backup_dir           : (str) Полный путь ``backup_<версия>`` (ещё не создан).
        new_version          : (str) Устанавливаемая версия.
        new_paths            : (Tuple[str, ...]) Файлы кода новой версии.
        removed_paths        : (Tuple[str, ...]) Файлы прежней версии, которых нет в новой.
        added_paths          : (Tuple[str, ...]) Файлы, которых на диске не было.
        requirements_changed : (bool) Изменился ``requirements.txt``.

    Example:
        >>> LinuxUpdatePlan('s', 'w', 'b', '1.1', ('a',), (), (), False).new_version
        '1.1'
    """
    script_path          : str               # update.sh
    work_dir             : str               # .update_<метка>
    backup_dir           : str               # backup_<версия>
    new_version          : str               # устанавливаемая версия
    new_paths            : Tuple[str, ...]   # файлы новой версии
    removed_paths        : Tuple[str, ...]   # удалённые файлы
    added_paths          : Tuple[str, ...]   # добавленные файлы
    requirements_changed : bool              # нужен pip


# удаление следа файла или папки: ошибки не мешают сообщить исходную
def _remove_tree_quietly(
    path : str,  # файл, ссылка или папка
) -> None:
    """
    Удаляет файл, ссылку или папку, если они есть; ошибки удаления пропускаются.

    Args:
        path : (str) Что удалить.

    Example:
        >>> _remove_tree_quietly('/нет/такого/файла') is None
        True
    """
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    except OSError:
        pass


# содержимое файла как байты; нет файла — None
def _read_bytes_or_none(
    path : str,  # файл
) -> Optional[bytes]: # содержимое; None — файла нет
    """
    Читает файл целиком; файла нет — ``None``.

    Args:
        path : (str) Файл.

    Returns:
        (bytes/None) Содержимое; None — файла нет.

    Example:
        >>> _read_bytes_or_none('/нет/такого/файла') is None
        True
    """
    try:
        with open(path, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        return None


# подготовка обновления: распаковка, проверка, скрипт
def prepare_linux_update(
    archive_path    : str,                         # скачанный .tar.gz
    install_root    : str,                         # папка установки
    current_version : str,                         # текущая версия
    wait_pid        : int,                         # PID программы, выхода которой ждать
    stamp           : Optional[int] = None,        # метка папки; None — текущее время
    wait_timeout    : int = LINUX_WAIT_TIMEOUT_SEC,  # сколько скрипту ждать выхода, секунд
    keep_mode       : str = LINUX_KEEP_MODE_DEFAULT,   # как чистить старые копии кода
    keep_count      : int = LINUX_KEEP_COUNT_DEFAULT,  # сколько копий оставить (count)
    keep_days       : int = LINUX_KEEP_DAYS_DEFAULT,   # сколько дней хранить (days)
    start_check_sec : int = LINUX_START_CHECK_SEC,     # сколько следить за запуском, секунд
) -> LinuxUpdatePlan: # что подготовлено
    """
    Распаковывает обновление, проверяет состав и пишет ``update.sh``; код ещё не меняется.

    Порядок: остатки прошлых попыток ``.update_<число>`` убираются → распаковка в новую
    ``.update_<метка>`` (:func:`safe_extract_tar`) → сверка с манифестом
    (:func:`check_unpacked_update`) → версия в архиве новее текущей (иначе обновление
    предлагалось бы снова после каждого запуска) → манифест установленной версии → в пути кода
    нет ссылок на папки → сравнение ``requirements.txt`` → запись ``update.sh``.

    Ошибка — :class:`UpdateError`, временная папка удалена, код не менялся. Скачанный архив
    удаляется в любом случае: после распаковки он не нужен, а битый повторно не пригодится.

    Note:
        ``backup_<версия>`` здесь не создаётся. Папка с таким именем уже есть (та же версия
        обновлялась раньше) — берётся ``backup_<версия>_<метка>``, старый бэкап не трогается.

    Args:
        archive_path    : (str) Скачанный архив.
        install_root    : (str) Папка установки.
        current_version : (str) Текущая версия программы.
        wait_pid        : (int) PID программы.
        stamp           : (int/None) Метка временной папки; None — текущее время.
        wait_timeout    : (int) Сколько скрипту ждать выхода программы, секунд.
        keep_mode       : (str) Как чистить старые копии: ``count`` или ``days``.
        keep_count      : (int) Сколько копий оставить при ``count``.
        keep_days       : (int) Сколько дней хранить при ``days``.
        start_check_sec : (int) Сколько следить за запуском новой версии, секунд.

    Returns:
        (LinuxUpdatePlan) Подготовленное обновление.

    Raises:
        UpdateError: Обновление нельзя установить (текст — для пользователя).

    Example:
        >>> try:
        ...     prepare_linux_update(
        ...         archive_path    =   '/нет/архива.tar.gz',   # архива нет
        ...         install_root    =   '/нет/папки',           # установки нет
        ...         current_version =   '1.0.0',                # версия
        ...         wait_pid        =   1,                      # PID
        ...     )
        ... except UpdateError as e:
        ...     str(e).startswith('Не удалось подготовить обновление')
        True
    """
    stamp = int(time.time()) if stamp is None else int(stamp)
    work_name = f'{LINUX_WORK_PREFIX}{stamp}'
    work_dir = os.path.join(install_root, work_name)
    try:
        for name in os.listdir(install_root) if os.path.isdir(install_root) else ():
            if _LINUX_WORK_DIR_RE.match(name): # остаток прерванной попытки
                _remove_tree_quietly(os.path.join(install_root, name))
        os.mkdir(work_dir)

        top_name = safe_extract_tar(
            archive_path    =   archive_path,   # архив
            dest_dir        =   work_dir,       # временная папка
        )
        payload_dir = os.path.join(work_dir, top_name)
        new_paths = check_unpacked_update(payload_dir)

        version_bytes = _read_bytes_or_none(
            os.path.join(payload_dir, LINUX_VERSION_FILE),  # версия в архиве
        )
        new_version = (version_bytes or b'').decode('utf-8-sig', errors='replace').strip()
        if not is_newer_version(current_version, new_version):
            raise UpdateError(
                f'Версия в архиве ({new_version or "нет"}) не новее установленной ({current_version})'
            )

        old_paths = read_linux_manifest(install_root)
        new_set = set(new_paths)
        all_paths = new_set | set(old_paths)
        for path in sorted(all_paths):
            parts = path.split('/')
            for depth in range(1, len(parts)):
                folder = os.path.join(install_root, *parts[:depth])
                if os.path.islink(folder):
                    raise UpdateError(f'Папка кода — ссылка, обновите вручную: {folder}')

        removed_paths = tuple(sorted(set(old_paths) - new_set))
        # Папка на месте нового файла тоже «файла не было»: при откате файл убирается, пакет возвращается
        added_paths = tuple(
            path for path in new_paths
            if not os.path.lexists(os.path.join(install_root, path))
            or (os.path.isdir(os.path.join(install_root, path))
                and not os.path.islink(os.path.join(install_root, path)))
        )

        new_requirements = _read_bytes_or_none(
            os.path.join(payload_dir, LINUX_REQUIREMENTS_FILE),  # пакеты новой версии
        )
        old_requirements = _read_bytes_or_none(
            os.path.join(install_root, LINUX_REQUIREMENTS_FILE),  # пакеты прежней версии
        )
        requirements_changed = new_requirements is not None and new_requirements != old_requirements
        venv_python = os.path.join(install_root, LINUX_VENV_DIR, 'bin', 'python')
        if requirements_changed and not os.path.exists(venv_python):
            raise UpdateError(
                f'Нужно обновить пакеты, но нет окружения {LINUX_VENV_DIR}: обновите вручную (./install.sh)'
            )

        backup_name = LINUX_BACKUP_PREFIX + re.sub(r'[^0-9A-Za-z._-]', '_', current_version)
        if os.path.lexists(os.path.join(install_root, backup_name)):
            backup_name = f'{backup_name}_{stamp}'

        script = build_linux_update_script(
            wait_pid                =   wait_pid,                       # PID программы
            old_version             =   current_version,                # было
            new_version             =   new_version,                    # стало
            work_dir                =   work_name,                      # временная папка
            payload_dir             =   f'{work_name}/{top_name}',      # дистрибутив
            backup_dir              =   backup_name,                    # прежняя версия
            new_paths               =   new_paths,                      # новые файлы
            removed_paths           =   removed_paths,                  # удалённые
            added_paths             =   added_paths,                    # добавленные
            requirements_changed    =   requirements_changed,           # pip
            wait_timeout            =   wait_timeout,                   # ожидание выхода
            keep_mode               =   keep_mode,                      # как чистить копии
            keep_count              =   keep_count,                     # сколько копий
            keep_days               =   keep_days,                      # сколько дней
            start_check_sec         =   start_check_sec,                # проверка запуска
        )
        script_path = os.path.join(install_root, LINUX_UPDATE_SCRIPT)
        temporary_path = f'{script_path}.tmp'
        with open(temporary_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(script)
        os.chmod(temporary_path, 0o700)
        os.replace(temporary_path, script_path)
    except UpdateError:
        _remove_tree_quietly(work_dir)
        raise
    except OSError as e:
        _remove_tree_quietly(work_dir)
        raise UpdateError(f'Не удалось подготовить обновление: {e}') from e
    finally:
        _remove_tree_quietly(archive_path)

    return LinuxUpdatePlan(
        script_path             =   script_path,                                # update.sh
        work_dir                =   work_dir,                                   # временная папка
        backup_dir              =   os.path.join(install_root, backup_name),    # прежняя версия
        new_version             =   new_version,                                # стало
        new_paths               =   new_paths,                                  # новые файлы
        removed_paths           =   removed_paths,                              # удалённые
        added_paths             =   added_paths,                                # добавленные
        requirements_changed    =   requirements_changed,                       # pip
    )


# запуск update.sh отдельно от программы
def launch_linux_update_script(
    script_path  : str,  # полный путь update.sh
    install_root : str,  # папка установки
) -> None:
    """
    Запускает ``update.sh`` в отдельном сеансе: он переживает выход программы.

    Окружение наследуется — в нём ``DISPLAY`` и ``WAYLAND_DISPLAY`` для перезапуска окна. Вывод
    скрипта не нужен: он сам пишет ``update.log``.

    Args:
        script_path  : (str) Скрипт.
        install_root : (str) Папка установки (текущая папка процесса).

    Raises:
        OSError: Скрипт не запустился (нет bash).

    Example:
        >>> try:
        ...     launch_linux_update_script('/нет/такого.sh', '/нет/такой/папки')
        ... except FileNotFoundError:
        ...     'папки установки нет'
        'папки установки нет'
    """
    subprocess.Popen(
        ['bash', script_path],                      # без оболочки: пробелы в пути не мешают
        cwd                 =   install_root,       # папка установки
        stdin               =   subprocess.DEVNULL, # без терминала
        stdout              =   subprocess.DEVNULL, # журнал ведёт сам скрипт
        stderr              =   subprocess.DEVNULL, # журнал ведёт сам скрипт
        start_new_session   =   True,               # не закроется вместе с программой
    )


# текст о неудачном обновлении: прочитать один раз
def pop_linux_update_failure(
    install_root : Optional[str] = None,  # папка установки; None — текущая программа
) -> Optional[str]: # причина для показа пользователю; None — сбоя не было
    """
    Возвращает и убирает сообщение скрипта о неудачном обновлении (``.update_failed``).

    После отката ``update.sh`` снова запускает прежнюю версию; без этого сообщения окно просто
    открылось бы с той же версией и пользователь не понял бы, что случилось. Окно вызывает
    функцию при старте и показывает текст. Ошибки чтения — как «сообщения нет».

    Args:
        install_root : (str/None) Папка установки; None — :func:`get_install_root`.

    Returns:
        (str/None) Текст; None — сообщения нет.

    Example:
        >>> pop_linux_update_failure('/нет/такой/папки') is None
        True
    """
    root = install_root if install_root is not None else get_install_root()
    path = os.path.join(root, LINUX_FAILURE_FILE)
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read().strip()
        os.remove(path)
    except OSError:
        return None
    return text or None


# ----------------------------------------------------------------------------------------
# Потоки и объекты Qt
# ----------------------------------------------------------------------------------------

class UpdateChecker(QThread):
    """
    Поток проверки новой версии на GitHub.

    Attributes:
        finished (Signal): ``(bool, dict)`` — есть ли обновление, данные релиза.
            Объявлен поверх ``QThread.finished()`` (как у потоков Яндекс.Диска).
        error (Signal): ``(str)`` — текст ошибки.
    """
    finished = Signal(bool, dict)  # (есть_обновление, data_релиза)
    error = Signal(str)                # сообщение об ошибке


    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        current_version: str, # текущая версия программы
        repo_slug: str, # репозиторий 'владелец/имя'
    ) -> None:
        """
        Args:
            current_version (str): Текущая версия.
            repo_slug (str): Репозиторий GitHub.
        """
        super().__init__()

        self.logger = AppLogger.get_instance(
            name='app.UpdateChecker',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )

        self.current_version = current_version
        self.repo_slug = repo_slug

    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_token(self) -> str:
        """
        Токен GitHub из ``.env`` (для приватного репозитория).

        Returns:
            str: Токен или ``''``.
        """

        token = ''
        try:
            from app.config.conf.getenv import get_getenv
            token = get_getenv(key='GITHUB_TOKEN', start_value='')
        except Exception as e:
            self.logger.error(f"Произошла ошибка получения токена: {e}")

        self.logger.debug(f"token = {mask_token(token)}")
        return token

    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _build_request(
        self,
        token: Optional[str] = None, # токен GitHub или пусто
    ) -> urllib.request.Request:
        """
        Запрос «последний релиз» к GitHub API.

        Args:
            token (Optional[str]): Токен.

        Returns:
            urllib.request.Request: Запрос.
        """
        url = f"https://api.github.com/repos/{self.repo_slug}/releases/latest"
        headers = github_headers(
            token=token, # авторизация (приватный репозиторий)
            accept="application/vnd.github.v3+json", # JSON API v3
        )
        self.logger.debug(f"url = {url}, token = {mask_token(token)}")
        return urllib.request.Request(url, headers=headers)

    @staticmethod
    def _parse_version(
        v_now: str, # текущая версия
        v_new: str, # версия релиза
    ) -> bool:
        """
        Новее ли ``v_new`` (прежнее имя; логика — :func:`is_newer_version`).

        Args:
            v_now (str): Текущая версия.
            v_new (str): Версия релиза.

        Returns:
            bool: ``True`` — релиз новее.

        Example:
            >>> UpdateChecker._parse_version('2.0', 'v1.5')
            False
        """
        return is_newer_version(v_now, v_new)

    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _process_response(
        self,
        data: dict, # ответ GitHub (последний релиз)
    ) -> Tuple[bool, str, str, dict]:
        """
        Версия релиза и сравнение с текущей.

        Args:
            data (dict): Данные релиза.

        Returns:
            Tuple[bool, str, str, dict]: (есть обновление, версия, страница релиза, данные).
        """
        latest_version = normalize_version(data.get("tag_name", ""))
        release_url = data.get("html_url", "")
        has_update = is_newer_version(self.current_version, latest_version)
        return has_update, latest_version, release_url, data


    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self) -> None:
        """Запрос к GitHub → ``finished(есть_обновление, релиз)`` или ``error(текст)``."""

        try:
            token = self._get_token()
            req = self._build_request(token)
            self.logger.debug(f"Request URL: {req.full_url}")
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                err = f"Ошибка соединения с сервером обновления ({e.code}): {e.reason}"
                self.logger.error(err)
                self.error.emit(err)
                return

            if not isinstance(data, dict):
                raise ValueError("Сервер обновлений вернул неожиданный ответ")

            has_update, latest_version, release_url, full_data = self._process_response(data)
            self.logger.debug(f"has_update = {has_update}, latest_version = {latest_version}, release_url = {release_url}")

            self.finished.emit(has_update, full_data)
        except Exception as e:
            self.logger.error(f"Произошла ошибка: {e}")
            self.error.emit(str(e) or type(e).__name__)



class UpdateDownloader(QThread):
    """
    Поток скачивания файла обновления.

    Пишет во временный файл ``<target_path>.part``; только целиком скачанный файл
    (размер совпал с ``Content-Length``, а при заданном ``expected_sha256`` — и хеш SHA-256)
    переименовывается в ``target_path``. При ошибке временный файл удаляется —
    недокачанный или подменённый файл не запустится.

    Attributes:
        progress (Signal): ``(int, int)`` — скачано / всего байт.
        finished (Signal): ``(str)`` — путь к скачанному файлу.
        error (Signal): ``(str)`` — текст ошибки.
    """
    progress = Signal(int, int)   # (current, total)
    finished = Signal(str)        # путь к скачанному файлу
    error = Signal(str)

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        download_url    : str,                      # адрес файла (API-адрес файла релиза)
        target_path     : str,                      # путь, куда сохранить (полный путь файла)
        token           : Optional[str] = None,     # токен GitHub (приватный репозиторий)
        expected_sha256 : Optional[str] = None,     # опубликованный хеш файла; None — без сверки
    ) -> None: # поток скачивания файла обновления
        """
        Создаёт поток скачивания; само скачивание — :meth:`run` (``start()``).

        Args:
            download_url    : (str) Адрес файла.
            target_path     : (str) Куда сохранить.
            token           : (str/None) Токен GitHub; None или пустой — без авторизации.
            expected_sha256 : (str/None) Хеш SHA-256 из описания релиза (регистр не важен);
                None — хеш не сверяется (релиз без хеша, :meth:`AppUpdater.download_update`).

        Example:
            >>> downloader = UpdateDownloader(
            ...     'https://api.github.com/repos/o/r/releases/assets/1',  # адрес
            ...     '/tmp/MedicalApp_new_1.exe',                           # куда
            ...     expected_sha256 =   'a' * 64,                          # хеш из релиза
            ... )
            >>> downloader.expected_sha256 == 'a' * 64
            True
        """
        super().__init__()

        self.logger = AppLogger.get_instance(
            name='app.UpdateDownloader',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )

        self.download_url = download_url
        self.target_path = target_path
        self.token = token
        self.expected_sha256 = (expected_sha256 or '').strip().lower() or None


    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_headers(self) -> dict:
        """
        Заголовки запроса файла (двоичный поток).

        Returns:
            dict: Заголовки.
        """
        self.logger.debug(f"token = {mask_token(self.token)}")
        return github_headers(
            token=self.token, # авторизация (приватный репозиторий)
            accept='application/octet-stream', # файл, а не описание файла
        )

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _download_file(
        self,
        response: requests.Response, # ответ с потоком файла (stream=True)
        target_path: str, # куда писать
        total_size: int, # ожидаемый размер (0 — неизвестен)
    ) -> int:
        """
        Пишет поток ответа в файл блоками с прогрессом.

        Args:
            response (requests.Response): Ответ.
            target_path (str): Файл.
            total_size (int): Ожидаемый размер.

        Returns:
            int: Записано байт.
        """
        downloaded = 0
        with open(target_path, 'wb') as f:
            # Ручной цикл (copyfileobj не даёт прогресса)
            while True:
                chunk = response.raw.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    self.progress.emit(downloaded, total_size)
        return downloaded

    @staticmethod
    def _remove_quietly(
        path: str, # файл для удаления
    ) -> None:
        """
        Удаляет файл, если он есть; ошибки удаления не мешают сообщить исходную ошибку.

        Example:
            >>> UpdateDownloader._remove_quietly('/нет/такого/файла.part') is None
            True
        """
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self) -> None:
        """
        Скачивает файл → ``finished(путь)`` или ``error(текст)`` (временный файл удаляется).

        Порядок: ``.part`` → проверка размера (``Content-Length``) → сверка SHA-256 с
        ``expected_sha256`` (если задан) → ``os.replace`` в ``target_path``.
        """
        if_private = bool(self.token and self.token.strip())
        part_path = f'{self.target_path}.part'

        self.logger.debug(f"Download URL: {self.download_url}")
        try:
            # Папка файла (если её нет)
            dest_dir = os.path.dirname(self.target_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)

            param = {
                'url' : self.download_url,
                'headers': self._get_headers(),
                'stream': True,
                'timeout': (5, 120),   # (таймаут подключения, таймаут чтения)
            }

            if if_private:
                # Для приватного репозитория отключаем проверку SSL (иначе SSLEOFError в сборке PyInstaller)
                # Техдолг ТД-4 (_dev/ТЕХДОЛГ.md): без проверки сертификата токен и exe можно подменить.
                # Токен — только для тестирования; рабочие программы качают из открытого репозитория.
                param['verify'] = False
                self.logger.warning(
                    "Задан GITHUB_TOKEN: проверка сертификата HTTPS при скачивании обновления "
                    "отключена (режим тестирования); защита от подмены — только сверка SHA-256"
                )
            else:
                # Для публичного используем сертификаты certifi
                param['verify'] = certifi.where()   # явно указываем путь к сертификатам

            with requests.get(**param) as response:
                self.logger.debug(f"Response status: {response.status_code}, if_private = {if_private}")
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0) or 0)
                self.logger.debug(f"Total size: {total_size} bytes")

                downloaded = self._download_file(response, part_path, total_size)

            if total_size > 0 and downloaded != total_size:
                raise IOError(
                    f"Файл обновления скачан не полностью: {downloaded} из {total_size} байт"
                )

            # Сверка с хешем из описания релиза — ДО os.replace: подменённый или испорченный
            # файл остаётся .part и удаляется в except, установка не начинается
            if self.expected_sha256: # хеш опубликован в релизе
                actual_sha256 = file_sha256(part_path)
                if actual_sha256 != self.expected_sha256:
                    raise ValueError(
                        "Файл обновления повреждён или подменён: контрольная сумма SHA-256 "
                        f"не совпала (ожидалась {self.expected_sha256}, получена "
                        f"{actual_sha256}). Установка отменена."
                    )
                self.logger.debug(f"SHA-256 совпал: {actual_sha256}")

            os.replace(part_path, self.target_path)
            self.logger.debug(f"Download finished, saved to {self.target_path}")
            self.finished.emit(self.target_path)

        except requests.exceptions.ConnectionError as e:
            self._remove_quietly(part_path)
            self.logger.error(f"Ошибка соединения: {e}")
            self.error.emit(f"Нет соединения с сервером обновлений: {e}")
        except OSError as e:
            self._remove_quietly(part_path)
            self.logger.error(f"Ошибка файловой системы: {e}")
            self.error.emit(str(e) or type(e).__name__)
        except Exception as e:
            self._remove_quietly(part_path)
            self.logger.error(f"Произошла ошибка: {e}")
            self.error.emit(str(e) or type(e).__name__)


class AppUpdater(QObject):
    """
    Управление обновлением для окна.

    Attributes:
        update_available (Signal): ``(str, str)`` — тег новой версии, страница релиза.
        no_update (Signal): Обновления нет.
        check_error (Signal): ``(str)`` — ошибка проверки.
        download_progress (Signal): ``(int, int)`` — прогресс скачивания.
        download_finished (Signal): ``(str)`` — путь к скачанному файлу (только
            :meth:`download_update`; при :meth:`apply_update_from_release` программа
            заменяется и закрывается сама).
        download_error (Signal): ``(str)`` — ошибка скачивания/установки.
        download_warning (Signal): ``(str)`` — предупреждение установки (например, в
            описании релиза нет хеша SHA-256 файла — установка продолжается без сверки).
    """
    # Сигналы для UI
    update_available = Signal(str, str)   # (new_version, release_url)
    no_update = Signal()
    check_error = Signal(str)
    download_progress = Signal(int, int)
    download_finished = Signal(str)       # путь к скачанному файлу
    download_error = Signal(str)
    download_warning = Signal(str)        # предупреждение (установка продолжается)

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        parent: Optional[QObject] = None, # родитель Qt (окно)
    ) -> None:
        """
        Args:
            parent (Optional[QObject]): Родитель Qt.
        """
        super().__init__(parent)
        self.current_version = APP_VERSION
        self.repo_slug = GITHUB_REPO_SLUG
        self._checker = None
        self._downloader = None
        self._applier = None
        self._pending_download_url = None
        self._pending_release_url = None
        # Данные релиза последней успешной проверки (окно читает через pending_release_data)
        self._pending_release_data: Optional[dict] = None

    @property
    def pending_release_data(self) -> Optional[dict]:
        """
        Данные релиза, найденного последней проверкой (``None`` — не найден).

        Returns:
            Optional[dict]: Данные релиза GitHub.

        Example:
            >>> AppUpdater().pending_release_data is None
            True
        """
        return self._pending_release_data

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def check_for_updates(self) -> None:
        """Асинхронно проверяет наличие обновлений (повторный вызов во время проверки — пропуск)."""
        if self._checker and self._checker.isRunning():
            return
        self._checker = UpdateChecker(self.current_version, self.repo_slug)
        self._checker.finished.connect(self._on_check_finished)
        self._checker.error.connect(self.check_error.emit)
        self._checker.start()

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def apply_update_from_release(
        self,
        release_data: dict, # данные релиза GitHub (из проверки)
    ) -> None:
        """
        Скачивает и устанавливает обновление из релиза.

        Повторный вызов во время скачивания — пропуск (второго скачивания нет).

        Args:
            release_data (dict): Данные релиза.
        """
        if self._applier is not None and self._applier.is_running():
            return
        self._applier = UpdateApplier(release_data, self)
        self._applier.progress.connect(self.download_progress.emit)
        self._applier.error.connect(self.download_error.emit)
        self._applier.warning.connect(self.download_warning.emit)
        self._applier.start()
        # self._applier.finished.connect(self.download_finished.emit)  # или свой сигнал
        # ↑ до rework-updater (2026-10-21): UpdateApplier.finished() без аргументов, а
        #   download_finished(str) — путь; applier его не испускает (программа закрывается сама)

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_check_finished(
        self,
        has_update: bool, # есть ли новая версия
        release_data: dict, # данные релиза
    ) -> None:
        """Итог проверки → ``update_available`` или ``no_update``."""
        if has_update:
            self._pending_release_data = release_data
            self.update_available.emit(
                str(release_data.get('tag_name', '')), # тег новой версии
                str(release_data.get('html_url', '')), # страница релиза
            )
        else:
            self._pending_release_data = None
            self.no_update.emit()

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def download_update(
        self,
        download_url: str, # адрес файла обновления
    ) -> None:
        """
        Только скачивает файл обновления (без установки) → ``download_finished(путь)``.

        Args:
            download_url (str): Адрес файла (обычно из ``assets`` релиза).
        """
        if self._downloader and self._downloader.isRunning():
            return
        temp_dir = os.path.join(get_app_dir(), "MedicalAppUpdates")
        os.makedirs(temp_dir, exist_ok=True)
        target_path = os.path.join(
            temp_dir, # папка обновлений
            update_file_name(current_system(), int(time.time())), # имя файла
        )
        # self._downloader = UpdateDownloader(download_url, temp_dir)
        # ↑ до rework-updater (2026-10-21): путём файла передавалась папка — open(папка) падал
        self._downloader = UpdateDownloader(download_url, target_path)
        self._downloader.progress.connect(self.download_progress.emit)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.error.connect(self.download_error.emit)
        self._downloader.start()

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_download_finished(
        self,
        file_path: str, # скачанный файл
    ) -> None:
        """Скачивание (:meth:`download_update`) завершено → ``download_finished``."""
        self.download_finished.emit(file_path)

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def apply_update(
        self,
        downloaded_file: str, # скачанный файл обновления
    ) -> None:
        """
        Ручная установка: открывает папку со скачанным файлом.

        Args:
            downloaded_file (str): Скачанный файл.
        """
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(downloaded_file)))


class UpdateApplier(QObject):
    """
    Установка обновления: проверка возможности → скачивание → замена файла → выход.

    Attributes:
        progress (Signal): ``(int, int)`` — прогресс скачивания.
        finished (Signal): Не испускается (программа закрывается сама); оставлен для
            совместимости.
        error (Signal): ``(str)`` — текст ошибки.
        warning (Signal): ``(str)`` — предупреждение; установка продолжается (в описании
            релиза нет хеша SHA-256 выбранного файла).
    """
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)
    warning = Signal(str)

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        release_data: Optional[dict], # данные релиза GitHub (None — нет данных)
        parent: Optional[QObject] = None, # родитель Qt
    ) -> None:
        """
        Args:
            release_data (Optional[dict]): Данные релиза; ``None`` — ошибка «нет файла
                обновления» при :meth:`start`, а не падение.
            parent (Optional[QObject]): Родитель Qt.
        """
        super().__init__(parent)
        self.release_data = release_data or {} # None (нет данных релиза) — как пустой релиз
        self._downloader = None
        self._downloaded_file = None
        self._new_exe_name = None

    def is_running(self) -> bool:
        """
        Идёт ли скачивание.

        Returns:
            bool: ``True`` — поток скачивания работает.

        Example:
            >>> UpdateApplier(None).is_running()
            False
        """
        return bool(self._downloader is not None and self._downloader.isRunning())

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def start(self) -> None:
        """
        Проверяет, возможна ли установка, выбирает файл релиза и запускает скачивание.

        Ошибки (не та ОС, не собранная программа; на Linux — не установленный дистрибутив, рабочая
        копия с ``.git``, нет прав на запись; нет файла для ОС) — в ``error`` ДО скачивания. Хеш SHA-256 выбранного файла берётся из описания релиза
        (:func:`release_asset_sha256`) и сверяется после скачивания; хеша нет — ``warning``
        и журнал, установка продолжается без сверки.
        """
        logger = AppLogger.get_instance(
            name='api.UpdateApplier',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )

        system = current_system()
        reason = auto_update_unavailable_reason(
            system=system, # ОС
            frozen=bool(getattr(sys, 'frozen', False)), # собранная программа
        )
        if reason:
            logger.error(reason)
            self.error.emit(reason)
            return

        # Токен для авторизации (если репозиторий приватный)
        from app.config.conf.getenv import get_getenv
        token = get_getenv(key='GITHUB_TOKEN', start_value='')

        asset = select_release_asset(self.release_data.get('assets', []), system)
        asset_url = asset.get('url') if asset else None
        logger.debug(f"asset for {system}: {asset.get('name') if asset else None}")

        if not asset_url:
            logger.error("No suitable asset found in release")
            self.error.emit("Не найден подходящий файл обновления для вашей ОС")
            return

        # Новый файл — рядом с exe, уникальное имя (метка времени); Linux — в корне установки
        exe_dir = get_install_root() if system == 'linux' else get_app_dir()
        # exe_dir = get_app_dir()
        # ↑ до 2026-11-07 (U20): из исходников это <установка>/app — папка кода, а не папка программы
        new_exe_name = update_file_name(system, int(time.time()))
        new_exe_path = os.path.join(exe_dir, new_exe_name)

        # Хеш выбранного файла из описания релиза (release.yml); нет — предупредить и продолжить
        asset_name = str(asset.get('name', ''))
        expected_sha256 = release_asset_sha256(
            release_data    =   self.release_data,  # описание релиза (body)
            asset_name      =   asset_name,         # выбранный файл
        )
        if expected_sha256 is None: # релиз без хеша — установка без сверки
            warning = (
                f"В описании релиза нет контрольной суммы SHA-256 файла {asset_name}: "
                "целостность обновления не проверяется"
            )
            logger.warning(warning)
            self.warning.emit(warning)

        self._new_exe_name = new_exe_name   # сохраняем для использования в _apply_update
        self._downloader = UpdateDownloader(
            asset_url,                              # адрес файла релиза
            new_exe_path,                           # куда сохранить
            token,                                  # токен GitHub
            expected_sha256 =   expected_sha256,    # хеш из описания релиза; None — без сверки
        )
        # self._downloader = UpdateDownloader(asset_url, new_exe_path, token)
        # ↑ до 2026-10-31 (U14): файл не сверялся с хешем — подменённый или испорченный
        #   файл релиза устанавливался

        self._downloader.progress.connect(self.progress.emit)
        self._downloader.finished.connect(self._on_downloaded)
        self._downloader.error.connect(self.error.emit)
        self._downloader.start()
        logger.debug("download started")

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_downloaded(
        self,
        file_path: str, # скачанный файл
    ) -> None:
        """Скачано → установка."""
        self._downloaded_file = file_path
        self._apply_update()

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_update(self) -> None:
        """
        Замена программы: скрипт в папке программы (PowerShell — Windows, bash — Linux) и выход.

        Ошибки (ОС, не собранная программа, нет скачанного файла, обновление не прошло
        проверку) — в ``error``, программа продолжает работать.
        """
        system = current_system()
        reason = auto_update_unavailable_reason(
            system=system, # ОС
            frozen=bool(getattr(sys, 'frozen', False)), # собранная программа
        )
        if reason:
            self.error.emit(reason)
            return

        if not self._downloaded_file or not os.path.exists(self._downloaded_file):
            self.error.emit("Новый файл не найден")
            return

        if system == 'linux':
            self._apply_update_linux()
            return

        app_dir = get_app_dir()
        os.chdir(app_dir)

        old_exe = os.path.basename(sys.executable)           # динамическое имя текущего EXE (например, "MedicalApp.exe")
        new_exe = os.path.basename(self._downloaded_file)    # имя скачанного файла (например, "MedicalApp_new_12345.exe")
        ps_script = "update.ps1"
        log_file = "update.log"

        with open(ps_script, "w", encoding="utf-8") as f:
            f.write(build_windows_update_script(
                old_exe=old_exe, # текущий exe
                new_exe=new_exe, # скачанный exe
                log_file=log_file, # журнал скрипта
            ))

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

        subprocess.Popen(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps_script],
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        QApplication.quit()
        sys.exit(0)

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_update_linux(self) -> None:
        """
        Linux: распаковывает архив, проверяет состав, запускает ``update.sh`` и выходит.

        Распаковка идёт в потоке окна (архив — несколько МБ исходников, доли секунды). Ошибка —
        в ``error``, код не менялся, программа продолжает работать. Заменяет код уже сам скрипт,
        после выхода программы.
        """
        install_root = get_install_root()
        keep_mode, keep_count, keep_days = linux_backup_keep_settings(
            AppConfigManager.get_instance(),
        )
        try:
            plan = prepare_linux_update(
                archive_path    =   self._downloaded_file,  # скачанный архив
                install_root    =   install_root,           # папка установки
                current_version =   APP_VERSION,            # текущая версия
                wait_pid        =   os.getpid(),            # этот процесс
                keep_mode       =   keep_mode,              # как чистить старые копии
                keep_count      =   keep_count,             # сколько копий
                keep_days       =   keep_days,              # сколько дней
            )
        except UpdateError as e:
            self.error.emit(str(e))
            return

        try:
            launch_linux_update_script(
                script_path     =   plan.script_path,   # update.sh
                install_root    =   install_root,       # папка установки
            )
        except OSError as e:
            _remove_tree_quietly(plan.work_dir)
            _remove_tree_quietly(plan.script_path)
            self.error.emit(f'Не удалось запустить скрипт обновления: {e}')
            return

        QApplication.quit()
        sys.exit(0)


# ↓ до rework-updater, проход 1 (2026-10-21): прежняя реализация модуля целиком
#   (U1–U9 — app/UPDATER.md, «Журнал проверок»).
# # app/updater.py
# """
# Модуль для автоматического обновления приложения через GitHub Releases.
# Использует GitHub API для проверки версии и скачивания нового EXE.
# """
#
# import json
# import os
# import subprocess
# import sys
# import shutil
# import tempfile
# import time
# import urllib.request
# import platform
# from typing import Optional, Tuple
#
# import certifi
# import requests
#
#
# from app.utils.logger.logger import AppLogger
#
# from app.config import APP_VERSION, GITHUB_REPO_SLUG
# from app.config.config_manager.manager import AppConfigManager
#
#
#
# from PySide6.QtCore import QThread, Signal, QObject, QUrl
# from PySide6.QtGui import QDesktopServices
# from PySide6.QtWidgets import QApplication
#
#
# def get_app_dir() -> str:
#     """Возвращает директорию, где находится исполняемый файл (или скрипт)."""
#     if getattr(sys, 'frozen', False):
#         return os.path.dirname(sys.executable)
#     else:
#         return os.path.dirname(os.path.abspath(__file__))
#
# def is_github_reachable(timeout: float = 3.0) -> bool:
#     """
#     Проверяет доступность GitHub API через HTTP-запрос.
#     """
#
#     try:
#         req = urllib.request.Request(
#             "https://api.github.com/zen",
#             headers={"User-Agent": "MedicalApp/1.0"}
#         )
#         with urllib.request.urlopen(req, timeout=timeout) as resp:
#             return resp.status == 200
#
#     except Exception:
#         return False
#
# class UpdateChecker(QThread):
#     """
#     Поток для проверки наличия новой версии на GitHub.
#     """
#     finished = Signal(bool, dict)  # (есть_обновление, data_релиза)
#     error = Signal(str)                # сообщение об ошибке
#
#
#     @AppLogger.get_instance(
#         name='UpdateChecker',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def __init__(self, current_version: str, repo_slug: str):
#         super().__init__()
#
#         self.logger = AppLogger.get_instance(
#             name='app.UpdateChecker',
#             # share_file_with = 'system',
#             enable_file_logging = 'user',
#             use_name_in_filename = False, # 'system'
#         )
#
#         self.current_version = current_version
#         self.repo_slug = repo_slug
#     
#     @AppLogger.get_instance(
#         name='UpdateChecker',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _get_token(self) -> str:
#         """Получает токен из окружения (через getenv)."""
#
#         token = ''
#         try:
#             from app.config.conf.getenv import get_getenv
#             token = get_getenv(key='GITHUB_TOKEN', start_value='')
#         except Exception as e:
#             self.logger.error(f"Произошла ошибка получения токена: {e}")
#
#         self.logger.debug(
#             f"DEBUG: "
#             f"Token length = {len(token)}, "
#             f"first 5 chars = {token[:5] if token else 'EMPTY'}"
#         )
#         return token
#
#     @AppLogger.get_instance(
#         name='UpdateChecker',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _build_request(self, token: str = None):
#         """Формирует Request объект для GitHub API."""
#         url = f"https://api.github.com/repos/{self.repo_slug}/releases/latest"
#         headers = {"Accept": "application/vnd.github.v3+json"}
#         if token and token.strip():
#             headers["Authorization"] = f"token {token.strip()}"
#         
#         self.logger.debug(
#             f"url = {url}, "
#             f"token = {token and token.strip()}"
#             f"headers = {headers is not None} "
#         ) 
#
#         return urllib.request.Request(url, headers=headers)
#
#     # @AppLogger.get_instance(
#     #     name='UpdateChecker',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     @staticmethod
#     def _parse_version(v_now: str, v_new: str) -> bool:
#         """Сравнивает версии (True, если v_new > v_now)."""
#         v_now = v_now.split('.')
#         v_new = v_new.split('.')
#         len_v_now = len(v_now)
#         len_v_new = len(v_new)
#         for i in range(min(len_v_now, len_v_new)):
#             try:
#                 if int(v_now[i]) < int(v_new[i]):
#                     return True
#             except Exception as e:
#                 # self.logger.error(
#                 #     f"v_now = {v_now}, "
#                 #     f"v_new = {v_new}, "
#                 #     f"i = {i}"
#                 #     f"err: {e}"
#                 # )
#                 return False
#             
#         if len_v_now < len_v_new:
#             return True
#
#         return False
#
#     @AppLogger.get_instance(
#         name='UpdateChecker',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _process_response(self, data: dict):
#         """Извлекает и сравнивает версии из данных релиза."""
#         latest_tag = data.get("tag_name", "")
#
#         if latest_tag.startswith("v"):
#             latest_version = latest_tag[1:]
#         else:
#             latest_version = latest_tag
#
#         release_url = data.get("html_url", "")
#
#         has_update = self._parse_version(self.current_version, latest_version)
#
#         return has_update, latest_version, release_url, data
#
#
#     @AppLogger.get_instance(
#         name='UpdateChecker',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def run(self):
#
#         try:
#             token = self._get_token()
#             self.logger.debug(
#                 f"Token length = {len(token)}, "
#                 f"first 5 chars = {token[:5] if token else 'EMPTY'}"
#             )
#
#             req = self._build_request(token)
#             self.logger.debug(f"Request URL: {req.full_url}")
#             try:
#                 with urllib.request.urlopen(req, timeout=10) as response:
#                     data = json.loads(response.read().decode('utf-8'))
#             except urllib.error.HTTPError as e:
#                 err = f"Ошибка соединения с сервером обновления ({e.code}): {e.reason}"
#                 self.logger.error(err)
#                 self.error.emit(err)
#                 return
#
#
#             has_update, latest_version, release_url, full_data = self._process_response(data)
#             self.logger.debug(f"has_update = {has_update}, latest_version = {latest_version}, release_url = {release_url}")
#
#             self.finished.emit(has_update, full_data)
#         except urllib.error.HTTPError as e:
#             self.logger.error(f"Ошибка HTTP1 {e.code}: {e.reason}")
#             self.error.emit(f"Ошибка HTTP1 {e.code}: {e.reason}")
#         except Exception as e:
#             self.logger.error(f"Произошла ошибка: {e}")
#             self.error.emit(str(e))
#             
#
#
# class UpdateDownloader(QThread):
#     """
#     Поток для скачивания нового исполняемого файла.
#     """
#     progress = Signal(int, int)   # (current, total)
#     finished = Signal(str)        # путь к скачанному файлу
#     error = Signal(str)
#
#     @AppLogger.get_instance(
#         name='UpdateDownloader',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def __init__(
#         self, 
#         download_url: str, 
#         target_path: str,
#         token: str = None
#
#     ):
#         super().__init__()
#         
#         self.logger = AppLogger.get_instance(
#             name='app.UpdateDownloader',
#             # share_file_with = 'system',
#             enable_file_logging = 'user',
#             use_name_in_filename = False, # 'system'
#         )
#
#         self.download_url = download_url
#         self.target_path = target_path
#         self.token = token
#
#
#     @AppLogger.get_instance(
#         name='UpdateDownloader',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _get_headers(self) -> dict:
#         """Формирует заголовки запроса для GitHub."""
#         headers = {
#             'User-Agent': 'MedicalApp-Updater/1.0',
#             'Accept': 'application/octet-stream'
#         }
#         if self.token and self.token.strip():
#             headers['Authorization'] = f'token {self.token.strip()}'
#
#         self.logger.debug(f"token = {self.token and self.token.strip()}")
#
#         return headers
#
#     # @AppLogger.get_instance(
#     #     name='UpdateDownloader',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     # def _get_temp_file_path(self) -> str:
#     #     """Создаёт временный файл с правильным расширением."""
#     #     # os.makedirs(self.dest_dir, exist_ok=True)
#     #     system = platform.system().lower()
#     #     file_ext = ".exe" if system == "windows" else ".tar.gz"
#
#     #     self.logger.debug(f"dest_dir = {self.dest_dir} file_ext = {file_ext}")
#
#     #     fd, temp_path = tempfile.mkstemp(
#     #         suffix=file_ext,
#     #         prefix="MedicalApp_update_",
#     #         dir=self.dest_dir,
#     #         # dir=tempfile.gettempdir()   # <-- явно указываем системную временную папку,
#     #         # mode=0o777, 
#     #         # exist_ok=True
#     #     )
#     #     os.close(fd)
#     #     return temp_path
#
#     # @AppLogger.get_instance(
#     #     name='UpdateDownloader',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     # def _download_stream(self, temp_path: str, total_size: int, response):
#     #     """Потоково записывает данные в файл и обновляет прогресс."""
#     #     downloaded = 0
#     #     self.logger.debug(f"total_size = {total_size}")
#         
#     #     for chunk in response.iter_content(chunk_size=8192):
#     #         if chunk:
#     #             # Добавим проверку существования файла перед записью
#     #             if not os.path.exists(temp_path):
#     #                 self.logger.warning(f"Файл {temp_path} исчез, пересоздаём")
#     #                 # Пересоздаём файл (затираем старый)
#     #                 with open(temp_path, 'wb'):
#     #                     pass
#     #             with open(temp_path, 'ab') as out_file:
#     #                 out_file.write(chunk)
#     #                 out_file.flush()
#     #                 os.fsync(out_file.fileno())
#                     
#     #             downloaded += len(chunk)
#     #             if total_size > 0:
#     #                 self.progress.emit(downloaded, total_size)
#
#     @AppLogger.get_instance(
#         name='UpdateDownloader',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _download_file(self, response, target_path, total_size):
#         """
#         Сохраняет содержимое response в файл с прогрессом.
#         Использует буфер записи для повышения скорости.
#         """
#         buffer_size = 262144  # 256 КБ (можно увеличить до 1 МБ)
#         downloaded = 0
#         with open(target_path, 'wb') as f:
#             # Используем raw-поток response для более эффективного чтения
#             from shutil import copyfileobj
#             # Но copyfileobj не даёт прогресса, поэтому делаем ручной цикл с буфером
#             while True:
#                 chunk = response.raw.read(buffer_size)
#                 if not chunk:
#                     break
#                 f.write(chunk)
#                 downloaded += len(chunk)
#                 if total_size > 0:
#                     self.progress.emit(downloaded, total_size)
#         return True
#
#     @AppLogger.get_instance(
#         name='UpdateDownloader',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def run(self):
#         if_private = self.token is not None and self.token.strip()
#
#
#         self.logger.debug(f"Download URL: {self.download_url}")
#         try:
#             # Создаём директорию для target_path, если её нет
#             dest_dir = os.path.dirname(self.target_path)
#             if not os.path.exists(dest_dir):
#                 os.makedirs(dest_dir, exist_ok=True)
#
#             # 2. Подготовка заголовков и временного файла
#             headers = self._get_headers()
#             # temp_path = self._get_temp_file_path()
#
#             # self.logger.debug(f"Temp file path: {temp_path}")
#             
#
#             param = {
#                 'url' : self.download_url, 
#                 'headers':headers, 
#                 'stream':True, 
#                 # 'timeout':30,
#                 'timeout': (5, 120),   # (таймаут подключения, таймаут чтения)
#             }
#
#             if if_private:
#                 # Для приватного репозитория отключаем проверку SSL (иначе SSLEOFError в сборке PyInstaller)
#                 param['verify'] = False
#             else:
#                 # Для публичного используем сертификаты certifi
#                 param['verify'] = certifi.where()   # явно указываем путь к сертификатам
#
#             # 2. Выполнение запроса
#             response = requests.get(
#                 **param
#             )
#
#             self.logger.debug(f"Response status: {response.status_code}, if_private = {if_private}")
#             response.raise_for_status()
#
#             total_size = int(response.headers.get('content-length', 0))
#             self.logger.debug(f"Total size: {total_size} bytes")
#
#             # # 3. Скачивание с прогрессом
#             # self._download_stream(temp_path, total_size, response)
#
#             # Пишем сразу в целевой файл (перезаписываем, если существует)
#             self._download_file(response, self.target_path, total_size)
#
#             # 4. Успешное завершение
#             self.logger.debug(f"Download finished, saved to {self.target_path}")
#             self.finished.emit(self.target_path)
#
#         except requests.exceptions.ConnectionError as e:
#             self.logger.error(f"Ошибка соединения: {e}")
#             self.error.emit(str(e))
#         except OSError as e:
#             self.logger.error(f"Ошибка файловой системы: {e}")
#             self.error.emit(str(e))
#         except Exception as e:
#             self.logger.error(f"Произошла ошибка: {e}")
#             self.error.emit(str(e))
#
# class AppUpdater(QObject):
#     """
#     Главный класс, управляющий обновлением. Используется из MainWindow.
#     """
#     # Сигналы для UI
#     update_available = Signal(str, str)   # (new_version, release_url)
#     no_update = Signal()
#     check_error = Signal(str)
#     download_progress = Signal(int, int)
#     download_finished = Signal(str)       # путь к скачанному файлу
#     download_error = Signal(str)
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.current_version = APP_VERSION
#         self.repo_slug = GITHUB_REPO_SLUG
#         self._checker = None
#         self._downloader = None
#         self._pending_download_url = None
#         self._pending_release_url = None
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def check_for_updates(self):
#         """Асинхронно проверяет наличие обновлений."""
#         if self._checker and self._checker.isRunning():
#             return
#         self._checker = UpdateChecker(self.current_version, self.repo_slug)
#         self._checker.finished.connect(self._on_check_finished)
#         self._checker.error.connect(self.check_error.emit)
#         self._checker.start()
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def apply_update_from_release(self, release_data: dict):
#         """Запускает процесс обновления на основе данных релиза."""
#         self._applier = UpdateApplier(release_data, self)
#         self._applier.progress.connect(self.download_progress.emit)
#         self._applier.finished.connect(self.download_finished.emit)  # или свой сигнал
#         self._applier.error.connect(self.download_error.emit)
#         self._applier.start()
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _on_check_finished(self, has_update: bool, release_data: dict):
#         if has_update:
#             self._pending_release_data = release_data
#             self.update_available.emit(release_data['tag_name'], release_data['html_url'])
#         else:
#             self.no_update.emit()
#     # def _on_check_finished(self, has_update: bool, latest_version: str, release_url: str):
#     #     if has_update:
#     #         self._pending_release_url = release_url
#     #         self.update_available.emit(latest_version, release_url)
#     #     else:
#     #         self.no_update.emit()
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def download_update(self, download_url: str):
#         """
#         Скачивает обновление по указанному URL.
#         Обычно download_url берётся из assets релиза.
#         """
#         if self._downloader and self._downloader.isRunning():
#             return
#         # Временная директория в папке пользователя
#         # temp_dir = os.path.join(tempfile.gettempdir(), "MedicalAppUpdates")
#         temp_dir = os.path.join(get_app_dir(), "MedicalAppUpdates")
#         os.makedirs(temp_dir, exist_ok=True)
#
#         self._downloader = UpdateDownloader(download_url, temp_dir)
#         self._downloader.progress.connect(self.download_progress.emit)
#         self._downloader.finished.connect(self._on_download_finished)
#         self._downloader.error.connect(self.download_error.emit)
#         self._downloader.start()
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _on_download_finished(self, file_path: str):
#         self.download_finished.emit(file_path)
#
#     @AppLogger.get_instance(
#         name='AppUpdater',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def apply_update(self, downloaded_file: str):
#         """
#         Применяет обновление: заменяет текущий исполняемый файл на новый.
#         На практике требует перезапуска и вспомогательного скрипта.
#         Здесь мы просто покажем инструкцию и откроем папку с файлом.
#         Более продвинутый вариант — создать скрипт-загрузчик.
#         """
#         # Простейший вариант: открыть папку с файлом и показать сообщение
#         import platform
#         if platform.system() == "Windows":
#             # Для Windows можно запустить команду замены после закрытия приложения
#             # Сложно, поэтому пока предлагаем ручную замену
#             QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(downloaded_file)))
#         else:
#             QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(downloaded_file)))
#
#         # Здесь можно было бы запустить вспомогательный скрипт, но для простоты ограничимся этим.
#
#
# class UpdateApplier(QObject):
#     """
#     Класс для применения обновления: скачивание, замена файла, перезапуск.
#     """
#     progress = Signal(int, int)
#     finished = Signal()
#     error = Signal(str)
#
#     @AppLogger.get_instance(
#         name='UpdateApplier',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def __init__(self, release_data: dict, parent=None):
#         super().__init__(parent)
#         self.release_data = release_data
#         self._downloader = None
#         self._downloaded_file = None
#
#     @AppLogger.get_instance(
#         name='UpdateApplier',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def start(self):
#         """Начинает процесс обновления: определяет asset, скачивает, затем заменяет."""
#         logger = AppLogger.get_instance(
#             name='api.UpdateApplier',
#             # share_file_with = 'system',
#             enable_file_logging = 'user',
#             use_name_in_filename = False, # 'system'
#         )
#
#         
#         # Получаем токен для авторизации (если репозиторий приватный)
#         from app.config.conf.getenv import get_getenv
#         token = get_getenv(key='GITHUB_TOKEN', start_value='')
#         
#         # Определяем, есть ли токен (приватный режим)
#         is_private = bool(token and token.strip())
#
#         # Определяем URL бинарного файла для текущей ОС
#         system = platform.system().lower()
#         asset_url = None
#
#         def _tt (
#             asset ,
#             is_private = is_private       
#         ):            
#             # if not is_private:
#             #     asset_url = asset['browser_download_url']
#             # else:
#             #     asset_url = asset['url']
#
#             asset_url = asset['url']
#             return asset_url
#
#         for asset in self.release_data.get('assets', []):
#             logger.debug(f"asset = {asset}")
#             
#             name = asset['name'].lower()
#             logger.debug(f"Checking asset: {name}")
#
#             if system == 'windows' and ('windows' in name or name.endswith('.exe')):
#                 asset_url = _tt(asset, is_private)
#                 logger.debug(f"Windows asset found: {asset_url}")
#                 break
#
#             elif system == 'linux' and ('linux' in name or name.endswith('.tar.gz')):
#                 asset_url = _tt(asset, is_private)
#                 logger.debug(f"Linux asset found: {asset_url}")
#                 break
#         else:
#             # Если не нашли по условию, попробуем взять первый .exe или .tar.gz
#             for asset in self.release_data.get('assets', []):
#                 logger.debug(f"asset = {asset}")
#
#                 name = asset['name'].lower()
#                 logger.debug(f"Checking asset: {name}")
#
#                 if system == 'windows' and name.endswith('.exe'):
#                     asset_url = _tt(asset, is_private)
#                     logger.debug(f"Fallback Windows asset: {asset_url}")
#                     break
#                 elif system == 'linux' and name.endswith('.tar.gz'):
#                     asset_url = _tt(asset, is_private)
#                     logger.debug(f"Fallback Linux asset: {asset_url}")
#                     break
#
#         if not asset_url:
#             logger.error("No suitable asset found in release")
#             self.error.emit("Не найден подходящий файл обновления для вашей ОС")
#             return
#
#         logger.debug("start download")
#         # Скачиваем
#         # temp_dir = os.path.join(tempfile.gettempdir(), "MedicalAppUpdates")
#         # temp_dir = os.path.join(get_app_dir(), "MedicalAppUpdates")
#         # logger.debug(f"temp_dir = {temp_dir}")
#
#         # os.makedirs(temp_dir, exist_ok=True)
#
#         # self._downloader = UpdateDownloader(asset_url, temp_dir, token)
#
#         # Вместо временной папки
#         # Генерируем уникальное имя для нового файла (например, с меткой времени)
#         exe_dir = get_app_dir()
#         # import time
#         timestamp = int(time.time())
#         new_exe_name = f"MedicalApp_new_{timestamp}.exe"
#         new_exe_path = os.path.join(exe_dir, new_exe_name)
#         
#         self._new_exe_name = new_exe_name   # сохраняем для использования в _apply_update
#         self._downloader = UpdateDownloader(asset_url, new_exe_path, token)
#
#         self._downloader.progress.connect(self.progress.emit)
#         self._downloader.finished.connect(self._on_downloaded)
#         self._downloader.error.connect(self.error.emit)
#         self._downloader.start()
#         logger.debug("end download")
#
#     @AppLogger.get_instance(
#         name='UpdateApplier',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _on_downloaded(self, file_path: str):
#         self._downloaded_file = file_path
#         self._apply_update()
#
#     @AppLogger.get_instance(
#         name='UpdateApplier',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _apply_update(self):
#         if not getattr(sys, 'frozen', False):
#             self.error.emit("Автообновление работает только в собранном приложении")
#             return
#
#         app_dir = get_app_dir()
#         os.chdir(app_dir)
#
#         old_exe = os.path.basename(sys.executable)           # динамическое имя текущего EXE (например, "MedicalApp.exe")
#         new_exe = os.path.basename(self._downloaded_file)    # имя скачанного файла (например, "MedicalApp_new_12345.exe")
#         ps_script = "update.ps1"
#         log_file = "update.log"
#
#         if not os.path.exists(self._downloaded_file):
#             self.error.emit("Новый файл не найден")
#             return
#
#         ps_content = f'''
# $old = "{old_exe}"
# $new = "{new_exe}"
# $log = "{log_file}"
#
# function Write-Log {{ param($msg) Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $msg" }}
#
# Write-Log "Update script started"
# Start-Sleep -Seconds 3
#
# Write-Log "Terminating old process(es)"
# $proc = Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($old)) -ErrorAction SilentlyContinue
# if ($proc) {{
#     $proc | Stop-Process -Force
#     do {{
#         Start-Sleep -Milliseconds 500
#         $stillRunning = Get-Process -Name ([System.IO.Path]::GetFileNameWithoutExtension($old)) -ErrorAction SilentlyContinue
#         if ($stillRunning) {{ Write-Log "Still waiting..." }}
#     }} while ($stillRunning)
#     Write-Log "All processes terminated"
# }} else {{
#     Write-Log "No running process found"
# }}
#
# if (Test-Path $old) {{
#     Write-Log "Deleting old executable"
#     Remove-Item -Path $old -Force
# }} else {{
#     Write-Log "Old file not found, skipping delete"
# }}
#
# Write-Log "Starting new version with rename instruction"
# Start-Process -FilePath $new -ArgumentList "--rename-to `"$old`"" -WindowStyle Normal
#
# Write-Log "Cleaning up script"
# Start-Sleep -Seconds 2
# Remove-Item -Path $MyInvocation.MyCommand.Path -Force
# '''
#         with open(ps_script, "w", encoding="utf-8") as f:
#             f.write(ps_content)
#
#         startupinfo = subprocess.STARTUPINFO()
#         startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
#         startupinfo.wShowWindow = subprocess.SW_HIDE
#
#         subprocess.Popen(
#             ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps_script],
#             startupinfo=startupinfo,
#             creationflags=subprocess.CREATE_NO_WINDOW
#         )
#         QApplication.quit()
#         sys.exit(0)
#
#
# #     def _apply_update(self):
# #         """Заменяет текущий исполняемый файл на новый и перезапускает приложение."""
# #         if not getattr(sys, 'frozen', False):
# #             self.error.emit("Автообновление работает только в собранном приложении")
# #             return
#
# #         current_exe = sys.executable
# #         new_file = self._downloaded_file
# #         system = platform.system().lower()
#
# #         if system == "windows":
# #             source_escaped = json.dumps(new_file)
# #             dest_escaped = json.dumps(current_exe)
# #             log_file = os.path.join(tempfile.gettempdir(), "MedicalApp_update.log")
# #             log_escaped = json.dumps(log_file)
#
# #             ps_script = f"""$source = {source_escaped}
# # $dest = {dest_escaped}
# # $logFile = {log_escaped}
# # $processName = "MedicalApp"
#
# # Write-Output "$(Get-Date) - Starting update script" | Out-File $logFile
#
# # # Ждём 2 секунды, чтобы приложение успело закрыться само
# # Start-Sleep -Seconds 2
#
# # # Если процесс ещё висит – убиваем его
# # $proc = Get-Process -Name $processName -ErrorAction SilentlyContinue
# # if ($proc) {{
# #     Write-Output "$(Get-Date) - Process still running, killing it" | Out-File $logFile -Append
# #     Stop-Process -Name $processName -Force
# #     Start-Sleep -Seconds 1
# # }}
#
# # # Ждём, пока файл назначения разблокируется (максимум 10 секунд)
# # $maxAttempts = 10
# # $attempt = 0
# # while ($attempt -lt $maxAttempts) {{
# #     try {{
# #         $stream = [System.IO.File]::OpenWrite($dest)
# #         $stream.Close()
# #         break
# #     }} catch {{
# #         Write-Output "$(Get-Date) - Destination file still locked, waiting..." | Out-File $logFile -Append
# #         Start-Sleep -Seconds 1
# #         $attempt++
# #     }}
# # }}
#
# # if ($attempt -eq $maxAttempts) {{
# #     Write-Output "$(Get-Date) - ERROR: Destination file still locked after waiting" | Out-File $logFile -Append
# #     Read-Host "Press Enter to exit"
# #     exit 1
# # }}
#
# # try {{
# #     Copy-Item -Path $source -Destination $dest -Force -ErrorAction Stop
# #     Write-Output "$(Get-Date) - OK: File replaced successfully" | Out-File $logFile -Append
# #     Start-Process -FilePath $dest
# #     Write-Output "$(Get-Date) - New process started" | Out-File $logFile -Append
# # }} catch {{
# #     $errorMsg = $_.Exception.Message
# #     Write-Output "$(Get-Date) - ERROR: $errorMsg" | Out-File $logFile -Append
# #     Read-Host "Press Enter to exit"
# # }}
#
# # Remove-Item -Path $MyInvocation.MyCommand.Path -Force
# # """
# #             script_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.ps1")
# #             with open(script_path, "w", encoding="utf-8") as f:
# #                 f.write(ps_script)
#
# #             # Запуск PowerShell полностью скрыто (без окна)
# #             startupinfo = subprocess.STARTUPINFO()
# #             startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
# #             startupinfo.wShowWindow = subprocess.SW_HIDE
#
# #             subprocess.Popen(
# #                 ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script_path],
# #                 startupinfo=startupinfo,
# #                 creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
# #             )
# #             QApplication.quit()
# #             sys.exit(0)
#
# #         elif system == "linux":
# #             # Linux скрипт оставляем как есть (он работает с путями UTF-8)
# #             script_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.sh")
# #             content = f"""#!/bin/bash
# #     sleep 2
# #     cp "{new_file}" "{current_exe}"
# #     chmod +x "{current_exe}"
# #     "{current_exe}" &
# #     rm "$0"
# #     """
# #             with open(script_path, "w") as f:
# #                 f.write(content)
# #             os.chmod(script_path, 0o755)
# #             subprocess.Popen([script_path])
# #             QApplication.quit()
# #             sys.exit(0)
# #         else:
# #             self.error.emit(f"Автообновление не поддерживается на {system}")