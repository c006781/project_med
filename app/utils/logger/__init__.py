# app/backend/repositories/__init__.py
"""
Класс логера 
"""

from .logger import( 
    AppLogger,
)

__all__ = [
    'AppLogger', 
]

if not AppLogger.thec_craete('system'):
    AppLogger.get_instance(
        name='system',
        enable_file_logging=False,
        # enable_file_logging=True,
        use_name_in_filename=False   # используем общий файл из конфига
    )

if not AppLogger.thec_craete('user'):
    AppLogger.get_instance(
        name='user',
        enable_file_logging=False,    
        # enable_file_logging=True,    
        use_name_in_filename=False # используем общий файл из конфига
    )