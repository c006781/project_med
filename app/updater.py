# app/updater.py
"""
Модуль для автоматического обновления приложения через GitHub Releases.
Использует GitHub API для проверки версии и скачивания нового EXE.
"""

import json
import os
import subprocess
import sys
import shutil
import tempfile
import urllib.request
import platform
from typing import Optional, Tuple

import certifi
import requests


from app.utils.logger.logger import AppLogger

from app.config import APP_VERSION, GITHUB_REPO_SLUG
from app.config.config_manager.manager import AppConfigManager



from PySide6.QtCore import QThread, Signal, QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication


def get_app_dir() -> str:
    """Возвращает директорию, где находится исполняемый файл (или скрипт)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

class UpdateChecker(QThread):
    """
    Поток для проверки наличия новой версии на GitHub.
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
    def __init__(self, current_version: str, repo_slug: str):
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
        """Получает токен из окружения (через getenv)."""
        from app.config.conf.getenv import get_getenv
        token = get_getenv(key='GITHUB_TOKEN', start_value='')

        self.logger.debug(
            f"DEBUG: "
            f"Token length = {len(token)}, "
            f"first 5 chars = {token[:5] if token else 'EMPTY'}"
        )
        return token

    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _build_request(self, token: str = None):
        """Формирует Request объект для GitHub API."""
        url = f"https://api.github.com/repos/{self.repo_slug}/releases/latest"
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token and token.strip():
            headers["Authorization"] = f"token {token.strip()}"
        
        self.logger.debug(
            f"url = {url}, "
            f"token = {token and token.strip()}"
            f"headers = {headers is not None} "
        ) 

        return urllib.request.Request(url, headers=headers)

    # @AppLogger.get_instance(
    #     name='UpdateChecker',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    @staticmethod
    def _parse_version(v_now: str, v_new: str) -> bool:
        """Сравнивает версии (True, если v_new > v_now)."""
        v_now = v_now.split('.')
        v_new = v_new.split('.')
        len_v_now = len(v_now)
        len_v_new = len(v_new)
        for i in range(min(len_v_now, len_v_new)):
            try:
                if int(v_now[i]) < int(v_new[i]):
                    return True
            except Exception as e:
                # self.logger.error(
                #     f"v_now = {v_now}, "
                #     f"v_new = {v_new}, "
                #     f"i = {i}"
                #     f"err: {e}"
                # )
                return False
            
        if len_v_now < len_v_new:
            return True

        return False

    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _process_response(self, data: dict):
        """Извлекает и сравнивает версии из данных релиза."""
        latest_tag = data.get("tag_name", "")

        if latest_tag.startswith("v"):
            latest_version = latest_tag[1:]
        else:
            latest_version = latest_tag

        release_url = data.get("html_url", "")

        has_update = self._parse_version(self.current_version, latest_version)

        return has_update, latest_version, release_url, data


    @AppLogger.get_instance(
        name='UpdateChecker',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self):

        try:
            token = self._get_token()
            self.logger.debug(f"Token length = {len(token)}, first 5 chars = {token[:5] if token else 'EMPTY'}")

            req = self._build_request(token)
            self.logger.debug(f"Request URL: {req.full_url}")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            has_update, latest_version, release_url, full_data = self._process_response(data)
            self.logger.debug(f"has_update = {has_update}, latest_version = {latest_version}, release_url = {release_url}")

            self.finished.emit(has_update, full_data)
        except urllib.error.HTTPError as e:
            self.logger.error(f"Ошибка HTTP {e.code}: {e.reason}")
            self.error.emit(f"Ошибка HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.logger.error(f"Произошла ошибка: {e}")
            self.error.emit(str(e))
            


class UpdateDownloader(QThread):
    """
    Поток для скачивания нового исполняемого файла.
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
        download_url: str, 
        dest_dir: str,
        token: str = None

    ):
        super().__init__()
        
        self.logger = AppLogger.get_instance(
            name='app.UpdateDownloader',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )

        self.download_url = download_url
        self.dest_dir = dest_dir
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
        """Формирует заголовки запроса для GitHub."""
        headers = {
            'User-Agent': 'MedicalApp-Updater/1.0',
            'Accept': 'application/octet-stream'
        }
        if self.token and self.token.strip():
            headers['Authorization'] = f'token {self.token.strip()}'

        self.logger.debug(f"token = {self.token and self.token.strip()}")

        return headers

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_temp_file_path(self) -> str:
        """Создаёт временный файл с правильным расширением."""
        # os.makedirs(self.dest_dir, exist_ok=True)
        system = platform.system().lower()
        file_ext = ".exe" if system == "windows" else ".tar.gz"

        self.logger.debug(f"dest_dir = {self.dest_dir} file_ext = {file_ext}")

        fd, temp_path = tempfile.mkstemp(
            suffix=file_ext,
            prefix="MedicalApp_update_",
            dir=self.dest_dir,
            # dir=tempfile.gettempdir()   # <-- явно указываем системную временную папку,
            # mode=0o777, 
            # exist_ok=True
        )
        os.close(fd)
        return temp_path

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _download_stream(self, temp_path: str, total_size: int, response):
        """Потоково записывает данные в файл и обновляет прогресс."""
        downloaded = 0
        self.logger.debug(f"total_size = {total_size}")
        
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                # Добавим проверку существования файла перед записью
                if not os.path.exists(temp_path):
                    self.logger.warning(f"Файл {temp_path} исчез, пересоздаём")
                    # Пересоздаём файл (затираем старый)
                    with open(temp_path, 'wb'):
                        pass
                with open(temp_path, 'ab') as out_file:
                    out_file.write(chunk)
                    out_file.flush()
                    os.fsync(out_file.fileno())
                    
                downloaded += len(chunk)
                if total_size > 0:
                    self.progress.emit(downloaded, total_size)

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self):
        if_private = self.token is not None and self.token.strip()


        self.logger.debug(f"Download URL: {self.download_url}")
        try:
            # 1. Сначала создаём директорию (если её нет)
            if not os.path.exists(self.dest_dir):
                os.makedirs(self.dest_dir, exist_ok=True)
                self.logger.debug(f"Created dest dir: {self.dest_dir}")

            # 2. Подготовка заголовков и временного файла
            headers = self._get_headers()
            temp_path = self._get_temp_file_path()

            self.logger.debug(f"Temp file path: {temp_path}")
            

            param = {
                'url' : self.download_url, 
                'headers':headers, 
                'stream':True, 
                # 'timeout':30,
                'timeout': (5, 120),   # (таймаут подключения, таймаут чтения)
            }

            if if_private:
                # Для приватного репозитория отключаем проверку SSL (иначе SSLEOFError в сборке PyInstaller)
                param['verify'] = False
            else:
                # Для публичного используем сертификаты certifi
                param['verify'] = certifi.where()   # явно указываем путь к сертификатам

            # 2. Выполнение запроса
            response = requests.get(
                **param
            )

            self.logger.debug(f"Response status: {response.status_code}, if_private = {if_private}")
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            self.logger.debug(f"Total size: {total_size} bytes")

            # 3. Скачивание с прогрессом
            self._download_stream(temp_path, total_size, response)

            # 4. Успешное завершение
            self.finished.emit(temp_path)

        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Ошибка соединения: {e}")
            self.error.emit(str(e))
        except OSError as e:
            self.logger.error(f"Ошибка файловой системы: {e}")
            self.error.emit(str(e))
        except Exception as e:
            self.logger.error(f"Произошла ошибка: {e}")
            self.error.emit(str(e))

class AppUpdater(QObject):
    """
    Главный класс, управляющий обновлением. Используется из MainWindow.
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_version = APP_VERSION
        self.repo_slug = GITHUB_REPO_SLUG
        self._checker = None
        self._downloader = None
        self._pending_download_url = None
        self._pending_release_url = None

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def check_for_updates(self):
        """Асинхронно проверяет наличие обновлений."""
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
    def apply_update_from_release(self, release_data: dict):
        """Запускает процесс обновления на основе данных релиза."""
        self._applier = UpdateApplier(release_data, self)
        self._applier.progress.connect(self.download_progress.emit)
        self._applier.finished.connect(self.download_finished.emit)  # или свой сигнал
        self._applier.error.connect(self.download_error.emit)
        self._applier.start()

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_check_finished(self, has_update: bool, release_data: dict):
        if has_update:
            self._pending_release_data = release_data
            self.update_available.emit(release_data['tag_name'], release_data['html_url'])
        else:
            self.no_update.emit()
    # def _on_check_finished(self, has_update: bool, latest_version: str, release_url: str):
    #     if has_update:
    #         self._pending_release_url = release_url
    #         self.update_available.emit(latest_version, release_url)
    #     else:
    #         self.no_update.emit()

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def download_update(self, download_url: str):
        """
        Скачивает обновление по указанному URL.
        Обычно download_url берётся из assets релиза.
        """
        if self._downloader and self._downloader.isRunning():
            return
        # Временная директория в папке пользователя
        # temp_dir = os.path.join(tempfile.gettempdir(), "MedicalAppUpdates")
        temp_dir = os.path.join(get_app_dir(), "MedicalAppUpdates")
        os.makedirs(temp_dir, exist_ok=True)

        self._downloader = UpdateDownloader(download_url, temp_dir)
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
    def _on_download_finished(self, file_path: str):
        self.download_finished.emit(file_path)

    @AppLogger.get_instance(
        name='AppUpdater',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def apply_update(self, downloaded_file: str):
        """
        Применяет обновление: заменяет текущий исполняемый файл на новый.
        На практике требует перезапуска и вспомогательного скрипта.
        Здесь мы просто покажем инструкцию и откроем папку с файлом.
        Более продвинутый вариант — создать скрипт-загрузчик.
        """
        # Простейший вариант: открыть папку с файлом и показать сообщение
        import platform
        if platform.system() == "Windows":
            # Для Windows можно запустить команду замены после закрытия приложения
            # Сложно, поэтому пока предлагаем ручную замену
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(downloaded_file)))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(downloaded_file)))

        # Здесь можно было бы запустить вспомогательный скрипт, но для простоты ограничимся этим.


class UpdateApplier(QObject):
    """
    Класс для применения обновления: скачивание, замена файла, перезапуск.
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
    def __init__(self, release_data: dict, parent=None):
        super().__init__(parent)
        self.release_data = release_data
        self._downloader = None
        self._downloaded_file = None

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def start(self):
        """Начинает процесс обновления: определяет asset, скачивает, затем заменяет."""
        logger = AppLogger.get_instance(
            name='api.UpdateApplier',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )

        
        # Получаем токен для авторизации (если репозиторий приватный)
        from app.config.conf.getenv import get_getenv
        token = get_getenv(key='GITHUB_TOKEN', start_value='')
        
        # Определяем, есть ли токен (приватный режим)
        is_private = bool(token and token.strip())

        # Определяем URL бинарного файла для текущей ОС
        system = platform.system().lower()
        asset_url = None

        def _tt (
            asset ,
            is_private = is_private       
        ):            
            # if not is_private:
            #     asset_url = asset['browser_download_url']
            # else:
            #     asset_url = asset['url']

            asset_url = asset['url']
            return asset_url

        for asset in self.release_data.get('assets', []):
            logger.debug(f"asset = {asset}")
            
            name = asset['name'].lower()
            logger.debug(f"Checking asset: {name}")

            if system == 'windows' and ('windows' in name or name.endswith('.exe')):
                asset_url = _tt(asset, is_private)
                logger.debug(f"Windows asset found: {asset_url}")
                break

            elif system == 'linux' and ('linux' in name or name.endswith('.tar.gz')):
                asset_url = _tt(asset, is_private)
                logger.debug(f"Linux asset found: {asset_url}")
                break
        else:
            # Если не нашли по условию, попробуем взять первый .exe или .tar.gz
            for asset in self.release_data.get('assets', []):
                logger.debug(f"asset = {asset}")

                name = asset['name'].lower()
                logger.debug(f"Checking asset: {name}")

                if system == 'windows' and name.endswith('.exe'):
                    asset_url = _tt(asset, is_private)
                    logger.debug(f"Fallback Windows asset: {asset_url}")
                    break
                elif system == 'linux' and name.endswith('.tar.gz'):
                    asset_url = _tt(asset, is_private)
                    logger.debug(f"Fallback Linux asset: {asset_url}")
                    break

        if not asset_url:
            logger.error("No suitable asset found in release")
            self.error.emit("Не найден подходящий файл обновления для вашей ОС")
            return

        logger.debug("start download")
        # Скачиваем
        # temp_dir = os.path.join(tempfile.gettempdir(), "MedicalAppUpdates")
        temp_dir = os.path.join(get_app_dir(), "MedicalAppUpdates")
        logger.debug(f"temp_dir = {temp_dir}")

        os.makedirs(temp_dir, exist_ok=True)

        self._downloader = UpdateDownloader(asset_url, temp_dir, token)
        self._downloader.progress.connect(self.progress.emit)
        self._downloader.finished.connect(self._on_downloaded)
        self._downloader.error.connect(self.error.emit)
        self._downloader.start()
        logger.debug("end download")

    @AppLogger.get_instance(
        name='UpdateApplier',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_downloaded(self, file_path: str):
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
    def _apply_update(self):
        """Заменяет текущий исполняемый файл на новый и перезапускает приложение."""
        if not getattr(sys, 'frozen', False):
            self.error.emit("Автообновление работает только в собранном приложении")
            return

        current_exe = sys.executable
        new_file = self._downloaded_file
        system = platform.system().lower()

        if system == "windows":
            source_escaped = json.dumps(new_file)
            dest_escaped = json.dumps(current_exe)
            log_file = os.path.join(tempfile.gettempdir(), "MedicalApp_update.log")
            log_escaped = json.dumps(log_file)

            ps_script = f"""$source = {source_escaped}
$dest = {dest_escaped}
$logFile = {log_escaped}
$processName = "MedicalApp"

Write-Output "$(Get-Date) - Starting update script" | Out-File $logFile

# Ждём 2 секунды, чтобы приложение успело закрыться само
Start-Sleep -Seconds 2

# Если процесс ещё висит – убиваем его
$proc = Get-Process -Name $processName -ErrorAction SilentlyContinue
if ($proc) {{
    Write-Output "$(Get-Date) - Process still running, killing it" | Out-File $logFile -Append
    Stop-Process -Name $processName -Force
    Start-Sleep -Seconds 1
}}

# Ждём, пока файл назначения разблокируется (максимум 10 секунд)
$maxAttempts = 10
$attempt = 0
while ($attempt -lt $maxAttempts) {{
    try {{
        $stream = [System.IO.File]::OpenWrite($dest)
        $stream.Close()
        break
    }} catch {{
        Write-Output "$(Get-Date) - Destination file still locked, waiting..." | Out-File $logFile -Append
        Start-Sleep -Seconds 1
        $attempt++
    }}
}}

if ($attempt -eq $maxAttempts) {{
    Write-Output "$(Get-Date) - ERROR: Destination file still locked after waiting" | Out-File $logFile -Append
    Read-Host "Press Enter to exit"
    exit 1
}}

try {{
    Copy-Item -Path $source -Destination $dest -Force -ErrorAction Stop
    Write-Output "$(Get-Date) - OK: File replaced successfully" | Out-File $logFile -Append
    Start-Process -FilePath $dest
    Write-Output "$(Get-Date) - New process started" | Out-File $logFile -Append
}} catch {{
    $errorMsg = $_.Exception.Message
    Write-Output "$(Get-Date) - ERROR: $errorMsg" | Out-File $logFile -Append
    Read-Host "Press Enter to exit"
}}

Remove-Item -Path $MyInvocation.MyCommand.Path -Force
"""
            script_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.ps1")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(ps_script)

            # Запуск PowerShell полностью скрыто (без окна)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            subprocess.Popen(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script_path],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            QApplication.quit()
            sys.exit(0)

        elif system == "linux":
            # Linux скрипт оставляем как есть (он работает с путями UTF-8)
            script_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.sh")
            content = f"""#!/bin/bash
    sleep 2
    cp "{new_file}" "{current_exe}"
    chmod +x "{current_exe}"
    "{current_exe}" &
    rm "$0"
    """
            with open(script_path, "w") as f:
                f.write(content)
            os.chmod(script_path, 0o755)
            subprocess.Popen([script_path])
            QApplication.quit()
            sys.exit(0)
        else:
            self.error.emit(f"Автообновление не поддерживается на {system}")