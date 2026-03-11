# /home/admin-rkc/Git/My_cods/project_med/app/network/__init__.py
"""
Пакет app.network — сетевое взаимодействие и синхронизация.

Содержит:
- thread_network.py: потоки DownloadThread и UploadThread для асинхронной работы.
- dop_yadisk/: функции для прямого вызова Яндекс.Диска (yadisk_download_file, yadisk_upload_file).
"""

# Импортируем классы потоков из thread_network
from .thread_network import (
    DownloadThread, 
    UploadThread,
)

# Импортируем функции работы с Яндекс.Диском из подпакета dop_yadisk
from .dop_yadisk import (
    yadisk_download_file, 
    yadisk_upload_file,
)

# Экспортируем публичный API пакета
__all__ = [
    'DownloadThread',
    'UploadThread',
    'yadisk_download_file',
    'yadisk_upload_file',
]

