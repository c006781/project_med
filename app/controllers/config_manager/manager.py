# app/controllers/config_manager/manager.py
"""
Модуль управления конфигурацией приложения с использованием MessagePack.

Содержит:
- BaseConfigManager: базовый класс для работы с конфигурацией (загрузка, сохранение, кеширование).
- AppConfigManager: наследник с конкретными настройками приложения и значениями по умолчанию.
- get_instance(): фабрика для получения единственного экземпляра менеджера.
- get_config_env(): функция для получения словаря конфигурации (совместимость со старым кодом).

Пример использования:
    manager = AppConfigManager.get_instance()
    token = manager.get('YANDEX_TOKEN')
    manager.set('LOG_LEVEL', 'DEBUG')
    manager.save()  # сохранить изменения в файл
"""

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from typing import Any, Dict, Optional

import logging

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


# Для получения пути к файлу конфигурации временно используем старую функцию.
try:
    from ..conf.get_config import get_config_env as _old_get_config_env
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..conf.get_config import get_config_env as _old_get_config_env 
    except ImportError as e:
        pass #  raise # e # pass
    
try:
    from ...utils.logger.logger import AppLogger
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 3)
        from ...utils.logger.logger import AppLogger
    except ImportError as e:
        pass #  raise # e # pass



# Сторонние библиотеки

import msgpack # pip install msgpack



class BaseConfigManager:
    """
    Базовый класс менеджера конфигурации.

    Атрибуты:
        _config_path (str): путь к файлу конфигурации (формат MessagePack).
        _defaults (dict): словарь со значениями по умолчанию.
        _config (dict): кеш текущих настроек (объединение defaults и загруженных из файла).
    """

    _config_path = 'config.msgpack'
    _defaults = {}
    
    def __init__(
        self, 
        config_path: str = None, 
        defaults: Dict[str, Any] = None,
        logger:logging = None,
    ):
        """
        Инициализирует менеджер.

        :param config_path: путь к файлу конфигурации.
        :param defaults: словарь значений по умолчанию.
        """
        self._config_path = config_path or self._config_path
        self._defaults = (defaults or self._defaults).copy() # копируем, чтобы не изменять оригинал
        self._config = self._defaults.copy()  # начинаем с умолчаний
        self._load()  # загружаем из файла, если он существует
         # Логирование, если доступно
        self.logger = logger or AppLogger.get_instance(f"{self.__class__.__name__}_{self._config_path}")

    def _load(self) -> None:
        """
        Загружает конфигурацию из файла и обновляет кеш (_config).
        Если файл не существует или повреждён, остаются значения по умолчанию.
        При успешной загрузке значения из файла имеют приоритет над defaults.
        """
        if not os.path.exists(self._config_path):
            # Файла нет – используем defaults, файл не создаём до первого сохранения
            return

        try:
            with open(self._config_path, 'rb') as f:
                data = msgpack.unpack(f, raw=False)  # raw=False для получения строк, а не байт
            if not isinstance(data, dict):
                # Если файл содержит не словарь, игнорируем его
                return
            # Обновляем кеш: значения из файла перезаписывают defaults
            self._config.update(data)
        except (msgpack.UnpackException, EOFError, OSError) as e:
            # В случае ошибки чтения (повреждённый файл) оставляем defaults
            self.logger.error(f"Ошибка при чтении файла конфигурации: {e}")
            pass

    def save(self) -> None:
        """
        Сохраняет текущий кеш конфигурации в файл (формат MessagePack).
        Создаёт родительские папки, если их нет.
        """
        # Создаём директорию, если не существует
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        # Сохраняем в бинарном режиме
        with open(self._config_path, 'wb') as f:
            msgpack.pack(self._config, f)

    def load(self) -> Dict[str, Any]:
        """
        Принудительно перезагружает конфигурацию из файла и возвращает копию кеша.
        Используется, если файл мог быть изменён внешними средствами.
        """
        self._load()
        return self.get_all()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Возвращает значение по ключу. Если ключ отсутствует, возвращает default.
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Устанавливает значение в кеше. Не сохраняет в файл автоматически.
        Чтобы сохранить, нужно вызвать save().
        """
        self._config[key] = value

    def update(self, data: Dict[str, Any]) -> None:
        """
        Обновляет кеш несколькими значениями (аналог dict.update).
        """
        self._config.update(data)

    def reset_to_defaults(self) -> None:
        """
        Сбрасывает кеш к значениям по умолчанию (без сохранения в файл).
        """
        self._config = self._defaults.copy()

    def get_all(self) -> Dict[str, Any]:
        """
        Возвращает копию текущего кеша (словарь).
        """
        return self._config.copy()
    
    @property
    def config_exists(self) -> bool:
        """Возвращает True, если файл конфигурации существует на диске."""
        return os.path.exists(self._config_path)

class AppConfigManager(BaseConfigManager):
    """
    Менеджер конфигурации для конкретного приложения.
    Определяет набор настроек по умолчанию, которые берутся из текущей
    конфигурации .env (старый способ), но могут быть переопределены в файле.
    """
    _config_path = 'config.msgpack'
    _defaults = {}
    # Значения по умолчанию (копия того, что сейчас возвращает get_config_env)
    _defaults = {
        'YANDEX_TOKEN': '----',
        'database_local_path': './clinic.db',
        'database_remote_path': 'Проекты/test/bd/clinic.db',
        'LOG_LEVEL': 'DEBUG',
        'LOG_FILE': './logs/app.log',
        'LOG_MAX_BYTES': str(10 * 1024 * 1024),  # 10 MB
        'LOG_BACKUP_COUNT': '5',
        'PHOTOS_STORAGE_PATH': './photos',
        # 'APP_CONFIG_PATH': 'config.msgpack',  # путь по умолчанию для файла конфигурации
    }

    # Хранилище для экземпляров (Multiton)
    _instances = {}

    def __init__(self, config_path: str = None):
        """
        Инициализирует менеджер с путём к файлу и значениями по умолчанию.
        Вызывать напрямую не рекомендуется – используйте get_instance().
        """
        super().__init__(config_path or self._config_path, self._defaults)

    @classmethod
    def get_instance(
        cls, 
        force_new: bool = False, 
        config_path: Optional[str] = None,
        create_if_missing: bool = False
    ) -> 'AppConfigManager':
        """
        Возвращает экземпляр менеджера конфигурации (паттерн Multiton).

        :param force_new: если True, создаёт новый экземпляр даже если уже есть.
        :param config_path: путь к файлу конфигурации. Если не указан,
                            берётся из старой функции get_config_env() по ключу 'APP_CONFIG_PATH'.
        :return: экземпляр AppConfigManager.
        """
        if config_path is None:
            # Получаем путь из старой конфигурации (там он уже должен быть)
            config_path = _old_get_config_env().get('APP_CONFIG_PATH', cls._config_path)

        # Если не требуем новый экземпляр и такой уже есть – возвращаем его
        if not force_new and config_path in cls._instances:
            return cls._instances[config_path]

        # Создаём новый экземпляр
        instance = cls(config_path)
        cls._instances[config_path] = instance

        if create_if_missing and not instance.config_exists:  # config_exists добавим позже
            instance.save()  # сохраняем умолчания

        return instance


# ----------------------------------------------------------------------
# Функция для обратной совместимости со старым кодом
# ----------------------------------------------------------------------
def get_config_env() -> Dict[str, Any]:
    """
    Возвращает словарь с текущей конфигурацией, используя новый менеджер.
    Эта функция предназначена для замены старой get_config_env из conf.get_config.
    """
    manager = AppConfigManager.get_instance()
    return manager.get_all()

if __name__ == '__main__':
    global env_key
    env_key = get_config_env()
    0==0
    pass