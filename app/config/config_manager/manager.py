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

from typing import Any, Dict, Optional


# Импорты модулей
from app.config.conf.get_config import get_config_env as _old_get_config_env




# Сторонние библиотеки

import msgpack # pip install msgpack

# from cryptography.fernet import Fernet # pip install cryptography



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

    _listeners = []   # список callable-функций

    @classmethod
    def add_change_listener(cls, callback):
        """Добавляет слушатель, вызываемый при сохранении конфигурации."""
        if callback not in cls._listeners:
            cls._listeners.append(callback)

    @classmethod
    def remove_change_listener(cls, callback):
        """Удаляет слушатель."""
        if callback in cls._listeners:
            cls._listeners.remove(callback)

    @classmethod
    def _notify_change(cls):
        """Оповещает всех зарегистрированных слушателей об изменении конфига."""
        for cb in cls._listeners:
            try:
                cb()
            except Exception as e:
                # Логируем ошибку, но не прерываем цепочку
                print(f"Ошибка в слушателе конфигурации: {e}")

                
    def __init__(
        self, 
        config_path: str = None, 
        defaults: Dict[str, Any] = None,
        # logger:logging = None,
        encrypt: bool = True, # по умолчанию включено шифрование
    ):
        """
        Инициализирует менеджер.

        :param config_path: путь к файлу конфигурации.
        :param defaults: словарь значений по умолчанию.
        """
        self._config_path = config_path or self._config_path
        self._defaults = (defaults or self._defaults).copy() # копируем, чтобы не изменять оригинал
        self._config = self._defaults.copy()  # начинаем с умолчаний

        # # Определяем, нужно ли шифрование
        # self._encrypt_enabled = encrypt

        # # Инициализируем шифратор
        # self._cipher = None
        # if self._encrypt_enabled:
        #     self._setup_cipher()

        self._load()  # загружаем из файла, если он существует
    
    def _load(self) -> None:
        """
        Загружает конфигурацию из файла и обновляет кеш (_config).
        Если файл не существует или повреждён, остаются значения по умолчанию.
        При успешной загрузке значения из файла имеют приоритет над defaults.
        """
        if not os.path.exists(self._config_path):
            # Файла нет – используем defaults, файл не создаём до первого сохранения
            return

        # try:
        with open(self._config_path, 'rb') as f:
            data = msgpack.unpack(f, raw=False)  # raw=False для получения строк, а не байт

        if not isinstance(data, dict):
            # Если файл содержит не словарь, игнорируем его
            return
        # Обновляем кеш: значения из файла перезаписывают defaults
        self._config.update(data)
        # 0==0
        # except (msgpack.UnpackException, EOFError, OSError) as e:
        #     # В случае ошибки чтения (повреждённый файл) оставляем defaults
        #     self.logger.error(f"Ошибка при чтении файла конфигурации: {e}")
        #     pass

    def save(self) -> None:
        """
        Сохраняет текущий кеш конфигурации в файл (формат MessagePack).
        Создаёт родительские папки, если их нет.
        """
        # # # Создаём директорию, если не существует
        # os.makedirs(os.path.dirname(self._config_path), exist_ok=True)

        """Сохраняет текущий кеш конфигурации в файл."""
        dirname = os.path.dirname(self._config_path)
        if dirname:  # только если есть директория
            os.makedirs(dirname, exist_ok=True)

        # Сохраняем в бинарном режиме
        with open(self._config_path, 'wb') as f:
            msgpack.pack(self._config, f)
        
        # Уведомляем всех подписчиков
        self.__class__._notify_change()

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
    # _defaults = {}
    # Значения по умолчанию (копия того, что сейчас возвращает get_config_env)
    # _defaults = {
    #     'YANDEX_TOKEN': '----',
    #     # 'database_local_path': './clinic.db',
    #     'database_local_path': os.path.join(
    #         '.',
    #         'clinic.db'
    #     ),
    #     'database_remote_path': 'Проекты/test/bd/clinic.db',
    #     # 'database_remote_path': 'Проекты/test/bd/clinic.db',
    #     'LOG_LEVEL': 'DEBUG',
    #     # 'LOG_LEVEL': 'INFO',
    #     # 'LOG_FILE': './logs/app.log',
    #     'LOG_FILE': os.path.join(
    #         '.',
    #         'logs',
    #         'app.log'
    #     ),
    #     'LOG_MAX_BYTES': str(10 * 1024 * 1024),  # 10 MB
    #     'LOG_BACKUP_COUNT': '5',
    #     # 'PHOTOS_STORAGE_PATH': './photos',
    #     'PHOTOS_STORAGE_PATH': os.path.join(
    #         '.', 
    #         'photos'
    #     ),
    #     # 'APP_CONFIG_PATH': 'config.msgpack',  # путь по умолчанию для файла конфигурации
    #     'LOG_ARGS': 'False',   # или False, но в msgpack можно хранить bool
    # }

    _defaults = {
        'YANDEX_TOKEN': '----',
        'database_local_path': os.path.join('.', 'clinic.db'),
        'database_remote_path': 'Проекты/test/bd/clinic.db',
        
        # === НАСТРОЙКИ ЛОГИРОВАНИЯ ===
        'LOG_DIR': os.path.join('.', 'logs'),          # вместо LOG_FILE
        # 'LOG_LEVEL': 'DEBUG',
        'LOG_LEVEL': 'INFO',
        'LOG_MAX_BYTES': str(10 * 1024 * 1024),       # 10 MB
        'LOG_BACKUP_COUNT': '5',
        'LOG_ARGS': 'False',
        
        
        # Для системного логгера
        'system_enabled': 'True', 
        'system_console_enabled': 'True',
        'system_file_enabled': 'True',
        'system_LEVEL': 'DEBUG',
        # 'system_enabled': 'False', 
        # 'system_console_enabled': 'False',
        # 'system_file_enabled': 'False',
        # 'system_LEVEL': 'INFO',
        
        # Для пользовательского логгера
        'user_enabled': 'True',
        'user_console_enabled': 'True',
        'user_file_enabled': 'True',
        'user_LEVEL': 'DEBUG',
        # 'user_enabled': 'False',
        # 'user_console_enabled': 'False',
        # 'user_file_enabled': 'False',
        # 'user_LEVEL': 'INFO',
        
        # Общие флаги (могут быть переопределены специфичными)
        'enabled': 'True',
        'console_enabled': 'True',
        'file_enabled': 'True',
        # 'enabled': 'False',
        # 'console_enabled': 'False',
        # 'file_enabled': 'False',

        'use_timestamp': 'False',      # добавлять ли дату в имя файла лога
        
        # Остальные настройки
        'PHOTOS_STORAGE_PATH': os.path.join('.', 'photos'),
        'APP_CONFIG_PATH': 'config.msgpack', # путь по умолчанию для файла конфигурации
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
def get_config_env(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Возвращает словарь с текущей конфигурацией, используя новый менеджер.

    Ранее мы использовали функцию get_config_env из conf.get_config, которая
    возвращала словарь с конфигурацией. Теперь мы используем новый менеджер
    AppConfigManager, который хранит конфигурацию в формате MessagePack.

    Мы получаем экземпляр менеджера с помощью AppConfigManager.get_instance(),
    а затем вызываем у него метод get_all(), который возвращает копию текущего
    кеша конфигурации.
    """
    manager = AppConfigManager.get_instance(
        config_path=config_path,
    )
    return manager.get_all()

if __name__ == '__main__':

    global env_key
    env_key = get_config_env()

    # 0==0
    pass