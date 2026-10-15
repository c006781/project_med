# app/config/__init__.py

"""
Пакет конфигурации приложения.

Экспортирует ``APP_VERSION`` (из файла ``VERSION``) и ``GITHUB_REPO_SLUG``.
Устройство конфигурации — ``app/config/IMPLEMENTATION.md``.

Пример:
    >>> from app.config import APP_VERSION
    >>> APP_VERSION
    '1.4.2'
"""

import os
import sys

def _get_version() -> str:
    """
    Версия приложения из файла ``VERSION``.

    Ищется рядом с exe (``sys._MEIPASS`` в сборке PyInstaller) или в корне проекта.
    Файла нет или он не читается — ``'0.0.0-dev'``.

    Returns:
        Строка версии.

    Пример:
        >>> _get_version()
        '1.4.2'
    """
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    version_file = os.path.join(base_dir, 'VERSION')
    try:
        with open(version_file, 'r') as f:
            return f.read().strip()
    except Exception:
        # fallback для разработки (файл VERSION может отсутствовать)
        return "0.0.0-dev"

APP_VERSION = _get_version()
GITHUB_REPO_SLUG = "c006781/project_med"