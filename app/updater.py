# app/updater.py
"""
Автообновление приложения через GitHub Releases.

Цепочка (окно — ``UpdateMixin`` в ``interfaces/gui/gui_window/main_window.py``)::

    AppUpdater.check_for_updates()
      └─ UpdateChecker (поток): GET /repos/<slug>/releases/latest
           └─ is_newer_version(текущая, из тега) → update_available(tag, url) | no_update()
    AppUpdater.apply_update_from_release(release)
      └─ UpdateApplier.start(): ОС поддерживается? exe собран? → select_release_asset
           └─ UpdateDownloader (поток): скачивание в файл рядом с exe (с проверкой размера)
                └─ UpdateApplier._apply_update(): скрипт замены (Windows) → выход

Логика без Qt вынесена в функции (версии, выбор файла релиза, заголовки, скрипт замены) —
их легко проверять и дополнять. Подробности и журнал проверок — ``app/UPDATER.md``.

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

import json
import os
import re
import subprocess
import sys
import shutil
import tempfile
import time
import urllib.request
import platform
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
AUTO_UPDATE_SYSTEMS = frozenset({'windows'})

# Размер блока при скачивании (256 КБ)
DOWNLOAD_CHUNK_SIZE = 262144

# Части номера версии: '1.2.3' → (1, 2, 3)
_VERSION_RE = re.compile(r'^\d+(\.\d+)*$')


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

    def _name(asset: Mapping[str, Any]) -> str:
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
    """
    if not frozen:
        return 'Автообновление работает только в собранном приложении'
    if system not in AUTO_UPDATE_SYSTEMS:
        return (
            f'Автообновление пока доступно только для Windows (у вас {system or "неизвестная ОС"}). '
            'Скачайте новую версию со страницы релиза.'
        )
    return None


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
    ):
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
    (размер совпал с ``Content-Length``) переименовывается в ``target_path``. При ошибке
    временный файл удаляется — недокачанный exe не запустится.

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
        download_url: str, # адрес файла (API-адрес файла релиза)
        target_path: str, # путь, куда сохранить (полный путь файла)
        token: Optional[str] = None, # токен GitHub (приватный репозиторий)
    ):
        """
        Args:
            download_url (str): Адрес файла.
            target_path (str): Куда сохранить.
            token (Optional[str]): Токен GitHub.
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
        """Удаляет файл, если он есть; ошибки удаления не мешают сообщить исходную ошибку."""
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
        """Скачивание → ``finished(путь)`` или ``error(текст)`` (временный файл удаляется)."""
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
                # Техдолг ТД-4 (ТЕХДОЛГ.txt): без проверки сертификата токен и exe можно подменить.
                param['verify'] = False
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
    """
    # Сигналы для UI
    update_available = Signal(str, str)   # (new_version, release_url)
    no_update = Signal()
    check_error = Signal(str)
    download_progress = Signal(int, int)
    download_finished = Signal(str)       # путь к скачанному файлу
    download_error = Signal(str)

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
    ):
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
    """
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)

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
    ):
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

        Ошибки (не та ОС, не собранная программа, нет файла для ОС) — в ``error`` ДО
        скачивания.
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

        # Новый файл — рядом с exe, уникальное имя (метка времени)
        exe_dir = get_app_dir()
        new_exe_name = update_file_name(system, int(time.time()))
        new_exe_path = os.path.join(exe_dir, new_exe_name)

        self._new_exe_name = new_exe_name   # сохраняем для использования в _apply_update
        self._downloader = UpdateDownloader(asset_url, new_exe_path, token)

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
        Замена программы: скрипт PowerShell (Windows) в папке программы и выход.

        Ошибки (ОС, не собранная программа, нет скачанного файла) — в ``error``.
        """
        reason = auto_update_unavailable_reason(
            system=current_system(), # ОС
            frozen=bool(getattr(sys, 'frozen', False)), # собранная программа
        )
        if reason:
            self.error.emit(reason)
            return

        if not self._downloaded_file or not os.path.exists(self._downloaded_file):
            self.error.emit("Новый файл не найден")
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