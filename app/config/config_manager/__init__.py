# app/config/config_manager/__init__.py

"""
Пакет для управления конфигурацией приложения с использованием MessagePack.
Предоставляет базовый класс BaseConfigManager и наследника AppConfigManager
с конкретными полями и значениями по умолчанию.
"""

# from .base_manager import BaseConfigManager
# import sys
# tt = sys.modules['app.config.config_manager.manager']
from .manager import BaseConfigManager, AppConfigManager, get_config_env

__all__ = [
    'BaseConfigManager',
    'AppConfigManager',
    'get_config_env',
]