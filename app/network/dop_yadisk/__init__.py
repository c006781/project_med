# /home/admin-rkc/Git/My_cods/project_med/app/network/dop_yadisk/__init__.py
"""
Пакет app.network.dop_yadisk — вспомогательные функции для работы с Яндекс.Диском.

Содержит:
- ya_dop.py: функции yadisk_download_file, yadisk_upload_file с поддержкой прогресса.
"""

# Импортируем функции для скачивания и загрузки из модуля ya_dop
from .ya_dop import (
    yadisk_download_file, 
    yadisk_upload_file,
)
# Экспортируем публичные имена
__all__ = [
    'yadisk_download_file',
    'yadisk_upload_file',
]

# Примечание: функции принимают необязательный callback для прогресса,
