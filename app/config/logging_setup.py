# app/config/logging_setup.py

"""
Настройка логирования приложения из конфигурации.

Связывает два модуля, которые сами друг о друге не знают в обратную сторону:

    app.config.config_manager  ──читает──▶  config.msgpack (+ .env)
              │
              ▼
    setup_logging()  ──AppLogger.configure(config)──▶  app.utils.logger

Логгер конфиг не читает (см. app/utils/logger/IMPLEMENTATION.md §7.1), поэтому
настройки ему передаёт этот модуль. Зависимость только одна: config → logger.

Когда вызывать:
    Первой строкой в каждой точке входа — ДО любой работы, которую нужно логировать.
    Всё, что залогировано раньше, идёт по настройкам по умолчанию (только консоль)
    и в файл не попадает.

Пример (main_gui_window.py):
    >>> from app.config.logging_setup import setup_logging
    >>> setup_logging()
    >>> main()

Пример (тест с отдельным файлом конфигурации):
    >>> setup_logging(config_path='tmp/config.msgpack')
"""

# Стандартные библиотеки Python
from typing import Any, Dict, Optional

# Импорты модулей
from app.config.config_manager.manager import get_config_env
from app.utils.logger.logger import AppLogger


def setup_logging(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Читает конфиг приложения и настраивает по нему все логгеры.

    Шаги:
        1. ``get_config_env(config_path)`` — словарь из ``config.msgpack``
           (если файла нет — значения по умолчанию ``AppConfigManager``).
        2. ``AppLogger.configure(config)`` — запоминает конфиг для логгеров,
           которые будут созданы позже, и перенастраивает уже созданные
           (``system``, ``user`` и всех, кого создали импорты до этого вызова).

    Безопасно вызывать повторно: каждый вызов перечитывает конфиг и применяет его.

    Args:
        config_path: Путь к файлу конфигурации. ``None`` — путь по умолчанию
            (``APP_CONFIG_PATH`` из ``.env``, иначе ``config.msgpack``).

    Returns:
        Применённый словарь конфигурации (копия; изменения не влияют на логгеры).

    Пример:
        >>> config = setup_logging()
        >>> config['LOG_LEVEL']
        'INFO'
    """
    config = get_config_env(config_path)
    AppLogger.configure(config)
    return dict(config)


__all__ = ['setup_logging']
