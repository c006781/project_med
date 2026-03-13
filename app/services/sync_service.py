

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


import shutil

from typing import Type, TypeVar, Generic, List

from datetime import time

# Импорты модулей
def _add_package_name(
    file_module: str = None,
    levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
) -> None:
    
    """
    Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

    :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
                       (подберите под структуру вашего проекта)
                       Примеры:
                         2 → до папки app
    """
    if file_module is None:
        file_module = __file__

    # Получаем директорию текущего файла
    current_dir = os.path.dirname(os.path.abspath(file_module))

    # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
    project_root = current_dir
    for _ in range(levels_up):
        project_root = os.path.dirname(project_root)

    # Добавляем корень проекта в начало sys.path (высокий приоритет)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Вычисляем правильное значение __package__
    # Пример: /project_med/app/models/bd → "app.models.bd"
    rel_path = os.path.relpath(current_dir, project_root)
    
    if rel_path == '.':
        package_name = ''
    else:
        package_name = rel_path.replace(os.sep, '.').strip('.')

    # Устанавливаем __package__
    global __package__
    if package_name:
        __package__ = package_name
    else:
        # Если мы в корне — можно оставить None или пустую строку
        __package__ = None

try:
    from ..network.thread_network import DownloadThread, UploadThread
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..network.thread_network import DownloadThread, UploadThread
    except ImportError as e:
        pass #  raise # e # pass


try:
    from ..network.dop_yadisk.ya_dop import yadisk_download_file, yadisk_upload_file
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..network.dop_yadisk.ya_dop import yadisk_download_file, yadisk_upload_file
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..controllers.conf.get_config import get_config_env
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..controllers.conf.get_config import get_config_env
    except ImportError as e:
        pass #  raise # e # pass





# Сторонние библиотеки


# class SyncService:
#     def __init__(self):
#         # Загружаем настройки при инициализации (можно передавать извне)
#         config = get_config_env()
#         self.token = config['YANDEX_TOKEN']
#         self.remote_path = config['database_remote_path']
#         self.local_path = config['database_local_path']

class SyncService:
    def __init__(self):
        config = get_config_env()
        self.token = config['YANDEX_TOKEN']
        self.remote_path = config['database_remote_path']
        self.local_path = config['database_local_path']

    def download_sync(self, progress_callback=None):
        """Синхронное скачивание файла с Диска."""
        return yadisk_download_file(
            ya_token=self.token,
            ya_file_path=self.remote_path,
            local_file_path=self.local_path,
            if_err=True,
            progress_callback=progress_callback
        )

    def upload_sync(self, progress_callback=None):
        """Синхронная загрузка файла на Диск."""
        return yadisk_upload_file(
            ya_token=self.token,
            local_file_path=self.local_path,
            ya_file_path=self.remote_path,
            if_err=True,
            progress_callback=progress_callback
        )
    def prepare_download(self) -> DownloadThread:
        """Возвращает настроенный, но ещё не запущенный поток для скачивания."""
        thread = DownloadThread(self.token, self.remote_path, self.local_path)
        # Можно добавить общие обработчики, но лучше оставить GUI подключаться
        return thread

    def prepare_upload(self) -> UploadThread:
        thread = UploadThread(self.token, self.local_path, self.remote_path)
        return thread