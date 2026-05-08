# app/config/__init__.py
import os
import sys

def _get_version() -> str:
    """Возвращает версию из файла VERSION (лежит рядом с исполняемым файлом или в корне проекта)."""
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