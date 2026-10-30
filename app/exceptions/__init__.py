# app/exceptions/__init__.py

"""
Исключения приложения — экспорт из ``app/exceptions/exceptions_all.py``.

Иерархия, коды и правила выбора исключения — в описании ``exceptions_all``; заметки и
журнал проверок — ``app/exceptions/IMPLEMENTATION.md``. Бросают их сервисы
(``app/services``), ловят командная строка и окно.

``__all__`` — все классы и ``photo_error_from_os_error``, кроме прежних имён
``ConnectionError`` (псевдоним ``DatabaseConnectionError``) и ``IntegrityError`` (псевдоним
``DbIntegrityError``): ``from app.exceptions import *`` не перекрывает встроенный
``ConnectionError`` и ``sqlalchemy.exc.IntegrityError``; явный импорт прежнего имени
(``from app.exceptions import ConnectionError``) по-прежнему работает.

У каждого исключения — текст пользователю (``str(exc)``), подробности (``details``) и
исходная ошибка (``original``) для журнала; всё вместе — ``exc.log_text()``.

Example:
    >>> from app.exceptions import EntityNotFoundError, PatientNotFoundError
    >>> isinstance(PatientNotFoundError(1), EntityNotFoundError)
    True
    >>> 'ConnectionError' in __all__, 'IntegrityError' in __all__
    (False, False)
    >>> print(PatientNotFoundError(1, details='поиск по карточке').log_text())
    [1001] Пациент с идентификатором 1 не найден.
      Подробности: поиск по карточке
"""


from app.exceptions.exceptions_all import (
    # Базовое исключение
    AppException,

    # Общие исключения записей (любая таблица)
    EntityNotFoundError, # «не найдено» (+ LookupError)
    EntityValidationError, # ошибка проверки поля (+ ValueError)

    # Пациенты
    PatientNotFoundError, PatientValidationError,

    # Приёмы
    AppointmentNotFoundError, AppointmentValidationError,

    # Заметки
    AppointmentNoteNotFoundError, AppointmentNoteValidationError,

    # Фото
    PhotoNotFoundError, PhotoValidationError, PhotoFileError,
    PhotoStoragePermissionError, PhotoStorageNoSpaceError,
    photo_error_from_os_error, # ошибка ОС → исключение файла фото

    # Синхронизация
    SyncError, DownloadError, UploadError, TokenError,

    # База данных
    # DatabaseError, IntegrityError, DatabaseConnectionError,
    # ↑ до 2026-10-31 (Ф1.6.8а): IntegrityError → DbIntegrityError (имя совпадало с
    #   sqlalchemy.exc.IntegrityError); прежнее имя — присваиванием ниже.
    DatabaseError, DbIntegrityError, DatabaseConnectionError,
    # ConnectionError, # прежнее имя DatabaseConnectionError (импорт по имени; в __all__ нет)
    # ↑ до 2026-10-25 (E11): pyflakes — «imported but unused» (имени нет в __all__).
)

# Прежнее имя DatabaseConnectionError (импорт по имени; в __all__ нет — import * не
# перекрывает встроенный ConnectionError). Присваивание, а не импорт: pyflakes без замечаний.
ConnectionError = DatabaseConnectionError

# Прежнее имя DbIntegrityError — так же: в __all__ нет, import * не перекрывает
# sqlalchemy.exc.IntegrityError
IntegrityError = DbIntegrityError

# Что экспортируется при импорте * (без прежних имён ConnectionError, IntegrityError —
# не перекрывать встроенный и драйверный)
__all__ = [
    'AppException',
    'EntityNotFoundError', 'EntityValidationError',
    'PatientNotFoundError', 'PatientValidationError',
    'AppointmentNotFoundError', 'AppointmentValidationError',
    'AppointmentNoteNotFoundError', 'AppointmentNoteValidationError',
    'PhotoNotFoundError', 'PhotoValidationError', 'PhotoFileError',
    'PhotoStoragePermissionError', 'PhotoStorageNoSpaceError',
    'photo_error_from_os_error',
    'SyncError', 'DownloadError', 'UploadError', 'TokenError',
    'DatabaseError', 'DbIntegrityError', 'DatabaseConnectionError',
]

# ↓ до rework-exceptions (2026-10-21): импорт и __all__ — без общих EntityValidationError,
#   PhotoStorage*Error; ConnectionError в __all__ (import * перекрывал встроенный).
# from app.exceptions.exceptions_all import(
#     # Импортируем базовое исключение
#     AppException,
#
#     # Импортируем исключения пациентов
#
#     PatientNotFoundError, PatientValidationError,
#     EntityNotFoundError,  # DYN9 (2026-10-16): общее «не найдено»
#     # Импортируем исключения приёмов
#     AppointmentNotFoundError, AppointmentValidationError,
#
#     # Импортируем исключения заметок
#     AppointmentNoteNotFoundError, AppointmentNoteValidationError,
#
#     # Импортируем исключения фото
#     PhotoNotFoundError, PhotoValidationError, PhotoFileError,
#
#     # Импортируем исключения синхронизации
#     SyncError, DownloadError, UploadError, TokenError,
#
#     # Импортируем исключения базы данных
#     DatabaseError, IntegrityError, ConnectionError,
#
# )
#
# # Определяем, что экспортируется при импорте *
# __all__ = [
#     'EntityNotFoundError',
#     'AppException',
#     'PatientNotFoundError', 'PatientValidationError',
#     'AppointmentNotFoundError', 'AppointmentValidationError',
#     'AppointmentNoteNotFoundError', 'AppointmentNoteValidationError',
#     'PhotoNotFoundError', 'PhotoValidationError', 'PhotoFileError',
#     'SyncError', 'DownloadError', 'UploadError', 'TokenError',
#     'DatabaseError', 'IntegrityError', 'ConnectionError',
# ]
