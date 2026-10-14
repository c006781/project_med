# app/utils/logger/__init__.py

"""
Пакет логирования.

Самостоятельный: зависит только от стандартной библиотеки, импорты внутри
относительные — папку пакета можно скопировать в другой проект под любым именем.

Модули:
    base_logger.py     — BaseAppLogger (собирается из частей ниже); точка импорта ядра.
    handlers.py        — RobustRotatingFileHandler, CallableHandler.
    logger.py          — AppLogger: конфиг приложения через configure().
    _registry.py, _config.py, _handlers_mgmt.py, _sharing.py, _modes.py,
    _outputs.py, _emit.py, _decorator.py — части BaseAppLogger (примеси).
    _common.py         — общие служебные объекты.

Экспорт:
    AppLogger        — логгер приложения: получает конфиг через AppLogger.configure().
    BaseAppLogger    — ядро без привязки к конфигу; наследуйтесь от него в других проектах.
    CallableHandler  — обработчик logging, передающий записи в функцию вида print(text).

Пример:
    >>> from app.utils.logger import AppLogger
    >>> AppLogger.configure({'LOG_DIR': 'logs'})
    >>> log = AppLogger.get_instance('worker')
    >>> log.add_output(print, level='ERROR')
    >>> log.error('видно в консоли, файле и через print')

Подробности устройства — IMPLEMENTATION.md рядом с этим файлом.
"""

from .logger import(
    AppLogger
)
from .base_logger import (
    BaseAppLogger,
    CallableHandler,
)




__all__ = [
    'AppLogger',
    'BaseAppLogger',
    'CallableHandler',
]
