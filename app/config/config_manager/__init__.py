# app/config/config_manager/__init__.py

"""
Пакет для управления конфигурацией приложения с использованием MessagePack.
Предоставляет базовый класс BaseConfigManager и наследника AppConfigManager
с конкретными полями и значениями по умолчанию; ``WORD_DOCUMENTS_PATH_KEY`` — ключ
настройки «Папка документов Word» (M17, 2026-10-25).

Пример:
    >>> from app.config.config_manager import AppConfigManager, WORD_DOCUMENTS_PATH_KEY
    >>> AppConfigManager.get_instance().get(WORD_DOCUMENTS_PATH_KEY)
    ''
"""

# from .base_manager import BaseConfigManager
# import sys
# tt = sys.modules['app.config.config_manager.manager'] 
from .manager import BaseConfigManager, AppConfigManager, get_config_env
from .manager import WORD_DOCUMENTS_PATH_KEY   # ключ «Папка документов Word» (M17)

__all__ = [
    'BaseConfigManager',
    'AppConfigManager',
    'get_config_env',
    'WORD_DOCUMENTS_PATH_KEY',
]