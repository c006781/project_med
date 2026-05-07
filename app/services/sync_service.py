# app/services/sync_service.py

# # Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


# import shutil

# from typing import Type, TypeVar, Generic, List

# from datetime import time

# Импорты модулей
# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None





from app.utils.logger.logger import AppLogger

# try:
from app.network.thread_network import DownloadThread, UploadThread
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..network.thread_network import DownloadThread, UploadThread
#     except ImportError as e:
#         pass #  raise # e # pass


# try:
from app.network.ya_dop import yadisk_download_file, yadisk_upload_file
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..network.ya_dop import yadisk_download_file, yadisk_upload_file
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
    # from ..controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import AppConfigManager, get_config_env
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         # from ..controllers.conf.get_config import get_config_env
#         from ..controllers.config_manager.manager import get_config_env
#     except ImportError as e:
#         pass #  raise # e # pass







class SyncService:

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self):
        """
        Инициализация объекта SyncService:
            - получение токена Яндекс.Диска из .env
            - получение пути к файлу на Яндекс.Диске
            - получение пути к локальному файлу
        """

        config = get_config_env()

        # получение токена Яндекс.Диска из .env
        self.token = config['YANDEX_TOKEN']

        # получение пути к файлу на Яндекс.Диске
        self.remote_path = config['database_remote_path']

        # получение пути к локальному файлу
        self.local_path = config['database_local_path']

        self.logger = AppLogger.get_instance(
            name='api.SyncService',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        # Подписываемся на изменения конфига
        AppConfigManager.add_change_listener(self.reload_config)

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def download_sync(self, progress_callback=None):
        """
        Синхронное скачивание файла с Яндекс.Диска.

        :param progress_callback: Функция, вызываемая для обновления прогресса.
                              Принимает два аргумента: (already_done, total)

        :return: 0 при успехе, -1 при проблеме с токеном, -2 если файл не существует на диске,
                 -3 при другой ошибке.
        """
        # вызов функции yadisk_download_file с параметрами, сохраненными в __init__
        # return yadisk_download_file(
        #     ya_token=self.token,
        #     ya_file_path=self.remote_path,
        #     local_file_path=self.local_path,
        #     if_err=True,
        #     progress_callback=progress_callback
        # )

        # yadisk_download_file вызывает функцию yadisk_download_file с параметрами,
        # сохраненными в __init__, и передает прогресс загрузки
        # в колбэк _progress_callback.
        # Если возникнет какая-либо ошибка, то сообщение об ошибке
        # передается в колбэк error.
        return yadisk_download_file(
            ya_token=self.token,
            ya_file_path=self.remote_path,
            local_file_path=self.local_path,
            if_err=True,
            progress_callback=progress_callback
        )

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def upload_sync(self, progress_callback=None):
        """
        Синхронная загрузка файла на Яндекс.Диск.

        :param progress_callback: Функция, вызываемая для обновления прогресса.
                              Принимает два аргумента: (already_done, total)

        :return: 0 при успехе, -1 при проблеме с токеном, -2 если файл не существует на локальном диске,
                 -3 при другой ошибке.
        """
        # вызов функции yadisk_upload_file с параметрами, сохраненными в __init__
        # return yadisk_upload_file(
        #     ya_token=self.token,
        #     local_file_path=self.local_path,
        #     ya_file_path=self.remote_path,
        #     if_err=True,
        #     progress_callback=progress_callback
        # )

        # yadisk_upload_file вызывает функцию yadisk_upload_file с параметрами,
        # сохраненными в __init__, и передает прогресс загрузки
        # в колбэк _progress_callback.
        # Если возникнет какая-либо ошибка, то сообщение об ошибке
        # передается в колбэк error.
        return yadisk_upload_file(
            ya_token=self.token,
            local_file_path=self.local_path,
            ya_file_path=self.remote_path,
            if_err=True,
            progress_callback=progress_callback
        )
    
    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def prepare_download(self) -> DownloadThread:
        """
        Возвращает настроенный, но ещё не запущенный поток для скачивания.
        
        Это метод возвращает настроенный, но не запущенный поток DownloadThread.
        Поток будет скачивать файл с Яндекс.Диска в локальную файловую систему.
        Он будет вызывать функцию _progress_callback для обновления прогресса.
        """
        # Создаем настроенный, но не запущенный поток DownloadThread
        thread = DownloadThread(
            token=self.token, 
            remote_path=self.remote_path, 
            local_path=self.local_path
        )

        # Можно добавить общие обработчики, но лучше оставить GUI подключаться
        # к сигналам и слотам потока
        
        return thread

    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def prepare_upload(self) -> UploadThread:
        """
        Возвращает настроенный, но ещё не запущенный поток для загрузки.

        Это метод возвращает настроенный, но не запущенный поток UploadThread.
        Поток будет загружать файл из локальной файловой системы на Яндекс.Диск.
        Он будет вызывать функцию _progress_callback для обновления прогресса.
        """
        thread = UploadThread(
            token=self.token, 
            local_path=self.local_path, 
            remote_path=self.remote_path
        )

        return thread
    
    @AppLogger.get_instance(
        name='SyncService',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def reload_config(self) -> None:
        """Перезагружает токен и пути из текущей конфигурации."""
        # from app.config.config_manager.manager import AppConfigManager
        
        config = AppConfigManager.get_instance()

        self.token = config.get('YANDEX_TOKEN')
        self.remote_path = config.get('database_remote_path')
        self.local_path = config.get('database_local_path')

        self.logger.info("Конфигурация SyncService обновлена")
