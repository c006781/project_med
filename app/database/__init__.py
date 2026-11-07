# app/database/__init__.py
"""
База данных клиники: ``Database`` (подключение, сессии, миграции при открытии), модели
``Patient``, ``Appointment``, ``AppointmentNote``, ``Photo``, ``PhotoFile`` и ``generate_test_data``.

Миграции — ``app.database.migrate`` (не импортируется пакетом; ``Database`` зовёт его
сам), встроенные триггеры SQLite — ``app.database.sqlite_triggers``. Устройство —
``app/database/IMPLEMENTATION.md``.

Example:
    >>> from app.database import Database, Patient
    >>> db = Database(
    ...     'sqlite:///clinic.db',   # файл базы
    ... )
"""
# ↑ до 2026-10-31 (М8): описания пакета не было.

# Импортируем модели из подпакета bd
from .database_shema import (
    Patient, 
    Appointment, 
    AppointmentNote, 
    Photo,
    PhotoFile,      # файлы фото (Ф1.6.7б)
)

# Также можно импортировать функцию генерации тестовых данных, если она нужна на этом уровне
from .database_shema import (
    generate_test_data,
)


# from app.database.database import Database
# from app.database import Database
from .database import Database

__all__ = [
    'Patient',
    'Appointment',
    'AppointmentNote',
    'Photo',
    'PhotoFile',
    'generate_test_data',

    'Database',
]