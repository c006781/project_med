# exceptions/__init__.py
"""
Пакет кастомных исключений приложения.
Здесь собраны все исключения, которые могут возникать в процессе работы.
Используются в сервисах и других слоях для передачи специфических ошибок.
"""


from .exceptions_all import(
    # Импортируем базовое исключение
    AppException,

    # Импортируем исключения пациентов

    PatientNotFoundError, PatientValidationError,
    # Импортируем исключения приёмов
    AppointmentNotFoundError, AppointmentValidationError,

    # Импортируем исключения заметок
    AppointmentNoteNotFoundError, AppointmentNoteValidationError,

    # Импортируем исключения фото
    PhotoNotFoundError, PhotoValidationError, PhotoFileError,

    # Импортируем исключения синхронизации
    SyncError, DownloadError, UploadError, TokenError,

    # Импортируем исключения базы данных
    DatabaseError, IntegrityError, ConnectionError,

)

# Определяем, что экспортируется при импорте *
__all__ = [
    'AppException',
    'PatientNotFoundError', 'PatientValidationError',
    'AppointmentNotFoundError', 'AppointmentValidationError',
    'AppointmentNoteNotFoundError', 'AppointmentNoteValidationError',
    'PhotoNotFoundError', 'PhotoValidationError', 'PhotoFileError',
    'SyncError', 'DownloadError', 'UploadError', 'TokenError',
    'DatabaseError', 'IntegrityError', 'ConnectionError',
]