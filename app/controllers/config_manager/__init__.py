# app/controllers/config_manager/__init__.py
"""
Пакет для управления конфигурацией приложения с использованием MessagePack.
Предоставляет базовый класс BaseConfigManager и наследника AppConfigManager
с конкретными полями и значениями по умолчанию.
"""

# from .base_manager import BaseConfigManager
from .manager import BaseConfigManager, AppConfigManager, get_config_manager

__all__ = [
    'BaseConfigManager',
    'AppConfigManager',
    'get_config_manager',
]