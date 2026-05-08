# app/updater.py
"""
Модуль для автоматического обновления приложения через GitHub Releases.
Использует GitHub API для проверки версии и скачивания нового EXE.
"""

import json
import os
import sys
import shutil
import tempfile
import urllib.request
import platform
from typing import Optional, Tuple


from app.config.config_manager.manager import AppConfigManager
from app.utils.logger.logger import AppLogger


from PySide6.QtCore import QThread, Signal, QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from app.config import APP_VERSION, GITHUB_REPO_SLUG

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
    def run(self):

        logger = AppLogger.get_instance(
            name='app.UpdateChecker',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system'
        )
        try:
            # # Получаем токен из глобальной конфигурации
            # # from app.config.config_manager.manager import AppConfigManager
            # config = AppConfigManager.get_instance()
            # token = config.get('GITHUB_TOKEN', '')


            # Получаем токен из окружения
            from app.config.conf.getenv import get_getenv as get_getenv
            token = get_getenv(
                key = 'GITHUB_TOKEN',
                start_value=''
            )

            logger.debug(
                f"DEBUG: "
                f"Token length = {len(token)}, "
                f"first 5 chars = {token[:5] if token else 'EMPTY'}"
            )
            # Запрашиваем информацию о последнем релизе
            url = f"https://api.github.com/repos/{self.repo_slug}/releases/latest"
            headers = {"Accept": "application/vnd.github.v3+json"}
            if token and token.strip():
                headers["Authorization"] = f"token {token.strip()}"
                
            logger.debug(f"url = {url}, headers = {headers is not None}")

            req = urllib.request.Request(url, headers=headers)

            logger.debug(f"req = {req is not None}, headers = {headers is not None}")
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            latest_tag = data.get("tag_name", "")
            logger.debug(f"latest_tag = {latest_tag}")
            if latest_tag.startswith("v"):
                latest_version = latest_tag[1:]  # убираем префикс 'v'
            else:
                latest_version = latest_tag
            
            logger.debug(f"latest_version = {latest_version}")

            release_url = data.get("html_url", "")
            logger.debug(f"release_url = {release_url}")

            # Сравниваем версии (простое строковое сравнение, но лучше использовать packaging.version)
            # Для простоты используем tuple сравнение
            # def parse_version(v):
            #     return tuple(map(int, v.split('.')))
            

            def parse_version(v_now, v_new):

                v_now = v_now.split('.')
                v_new = v_new.split('.')
                len_v_now = len(v_now)
                len_v_new = len(v_new)
                for i in range(min(len_v_now, len_v_new)):
                    try:
                        if int(v_now[i]) < int(v_new[i]):
                            return True
                    except Exception as e:
                        logger.error(
                            f"v_now = {v_now}, "
                            f"v_new = {v_new}, "
                            f"i = {i}"
                            f"err: {e}"
                        )
                        return False
                    
                if len_v_now < len_v_new:
                    return True

                return False

            has_update = False
            # if parse_version(latest_version) > parse_version(self.current_version):
            if parse_version(self.current_version, latest_version) :
                has_update = True

            logger.debug(
                f"has_update = {has_update}, "
                f"latest_version = {latest_version}, "
                f"release_url = {release_url}"
            )            

            # self.finished.emit(has_update, latest_version, release_url)
            self.finished.emit(has_update, data)
        except urllib.error.HTTPError as e:
            logger.error(f"Ошибка HTTP {e.code}: {e.reason}")
            self.error.emit(f"Ошибка HTTP {e.code}: {e.reason}")

        except Exception as e:
            logger.error(f"Произошла ошибка: {e}")
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
    def __init__(self, download_url: str, dest_dir: str):
        super().__init__()
        self.download_url = download_url
        self.dest_dir = dest_dir

    @AppLogger.get_instance(
        name='UpdateDownloader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self):
        try:
            # Определяем имя файла из URL или формируем сами
            # Для Windows ищем asset с "windows" в имени, для Linux - "linux"
            system = platform.system().lower()
            if system == "windows":
                asset_pattern = "windows"
                file_ext = ".exe"
            else:
                asset_pattern = "linux"
                file_ext = ".tar.gz"

            # Чтобы не скачивать всё подряд, нужно сначала получить список assets из API релиза.
            # Упростим: передадим прямую ссылку на бинарник (её мы получим при проверке).
            # В нашем случае мы будем передавать URL уже готового asset.
            # Поэтому здесь просто скачиваем по переданному URL.

            # Создаём временный файл
            fd, temp_path = tempfile.mkstemp(suffix=file_ext, prefix="MedicalApp_update_", dir=self.dest_dir)
            os.close(fd)

            req = urllib.request.Request(self.download_url)
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                with open(temp_path, 'wb') as out_file:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.progress.emit(downloaded, total_size)

            self.finished.emit(temp_path)
        # except urllib.error.HTTPError as e:
        #     if e.code == 404:
        #         self.error.emit("Релизы не найдены. Создайте первый релиз на GitHub.")
        #     else:
        #         self.error.emit(f"Ошибка HTTP {e.code}: {e.reason}")
        except Exception as e:
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
        temp_dir = os.path.join(tempfile.gettempdir(), "MedicalAppUpdates")
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
        # Определяем URL бинарного файла для текущей ОС
        system = platform.system().lower()
        asset_url = None
        for asset in self.release_data.get('assets', []):
            name = asset['name'].lower()
            if system == 'windows' and ('windows' in name or name.endswith('.exe')):
                asset_url = asset['browser_download_url']
                break
            elif system == 'linux' and ('linux' in name or name.endswith('.tar.gz')):
                asset_url = asset['browser_download_url']
                break

        if not asset_url:
            self.error.emit("Не найден подходящий файл обновления для вашей ОС")
            return

        # Скачиваем
        temp_dir = os.path.join(tempfile.gettempdir(), "MedicalAppUpdates")
        os.makedirs(temp_dir, exist_ok=True)
        self._downloader = UpdateDownloader(asset_url, temp_dir)
        self._downloader.progress.connect(self.progress.emit)
        self._downloader.finished.connect(self._on_downloaded)
        self._downloader.error.connect(self.error.emit)
        self._downloader.start()

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
            # Создаём bat-скрипт
            script_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.bat")
            content = f"""@echo off
timeout /t 2 /nobreak > nul
copy /Y "{new_file}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
            with open(script_path, "w") as f:
                f.write(content)
            # Запускаем скрипт и выходим
            os.startfile(script_path)
        elif system == "linux":
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
            os.system(f"nohup {script_path} > /dev/null 2>&1 &")
        else:
            self.error.emit(f"Автообновление не поддерживается на {system}")
            return

        # Завершаем текущее приложение
        QApplication.quit()