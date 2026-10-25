# app/config/conf/__init__.py
"""
Пакет app.config.conf — конфигурация приложения.

Содержит модули:
- getenv.py: функции для работы с .env файлом (загрузка, создание, запись ключей).
- get_config.py: функция get_config_env() — «загрузочный» конфиг из .env
  (APP_CONFIG_PATH, GITHUB_TOKEN).

Пример:
    >>> from app.config.conf import get_getenv
    >>> get_getenv('APP_CONFIG_PATH', start_value='config.msgpack')
    'config.msgpack'
"""

# Импортируем функцию получения всех настроек из модуля get_config
from app.config.conf.get_config import (
     # главная функция для получения словаря конфигурации
    get_config_env,
)

# Импортируем основные функции для работы с .env из модуля getenv
from app.config.conf.getenv import( 
    # получить значение ключа из окружения (с созданием, если отсутствует)
    get_getenv, 
    # получить путь к .env файлу
    get_dotenv_path, 
    # сохранить словарь ключей в .env (
    save_env_file, 
    # создать пустой .env файл, если его нет
    crete_env_file,
)

# Определяем список публичных имён, которые будут импортированы при "from module import *"
__all__ = [
    'get_config_env',      # главная функция для получения словаря конфигурации
    'get_getenv',          # получить значение ключа из окружения (с созданием, если отсутствует)
    'get_dotenv_path',     # получить путь к .env файлу
    'save_env_file',       # сохранить словарь ключей в .env 
    'crete_env_file',      # создать пустой .env файл, если его нет
]

