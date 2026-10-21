# app/exceptions/__init__.py

"""
Пакет кастомных исключений приложения.
Здесь собраны все исключения, которые могут возникать в процессе работы.
Используются в сервисах и других слоях для передачи специфических ошибок.
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

    # Синхронизация
    SyncError, DownloadError, UploadError, TokenError,

    # База данных
    DatabaseError, IntegrityError, DatabaseConnectionError,
    ConnectionError, # прежнее имя DatabaseConnectionError (импорт по имени; в __all__ нет)
)

# Что экспортируется при импорте * (без ConnectionError — не перекрывать встроенный)
__all__ = [
    'AppException',
    'EntityNotFoundError', 'EntityValidationError',
    'PatientNotFoundError', 'PatientValidationError',
    'AppointmentNotFoundError', 'AppointmentValidationError',
    'AppointmentNoteNotFoundError', 'AppointmentNoteValidationError',
    'PhotoNotFoundError', 'PhotoValidationError', 'PhotoFileError',
    'PhotoStoragePermissionError', 'PhotoStorageNoSpaceError',
    'SyncError', 'DownloadError', 'UploadError', 'TokenError',
    'DatabaseError', 'IntegrityError', 'DatabaseConnectionError',
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
