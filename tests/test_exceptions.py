# tests/test_exceptions.py
import pytest
from app.exceptions import (
    PatientNotFoundError, 
    PatientValidationError,
    AppointmentNotFoundError, 
    # AppointmentNoteNotFoundError,
    # PhotoNotFoundError, 
    PhotoFileError,
    DownloadError, 
    # UploadError, 
    TokenError,
    # DatabaseError, 
    IntegrityError, 
    # ConnectionError
)

def test_patient_not_found_error():
    """
    Тест на исключение PatientNotFoundError.

    Проверяет, что исключение PatientNotFoundError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = PatientNotFoundError(42)
    assert str(exc) == "[1001] Пациент с идентификатором 42 не найден."
    assert exc.code == 1001

def test_patient_validation_error():
    """
    Тест на исключение PatientValidationError.

    Проверяет, что исключение PatientValidationError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = PatientValidationError("first_name", "пустое")
    assert "Ошибка валидации поля 'first_name': пустое." in str(exc)

def test_appointment_not_found_error():
    """
    Тест на исключение AppointmentNotFoundError.

    Проверяет, что исключение AppointmentNotFoundError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = AppointmentNotFoundError(10)
    assert "Приём с идентификатором 10 не найден." in str(exc)

def test_photo_file_error():
    """
    Тест на исключение PhotoFileError.

    Проверяет, что исключение PhotoFileError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = PhotoFileError("/path", "копирование", "нет места")
    assert "Ошибка копирование файла '/path': нет места" in str(exc)

def test_download_error():
    """
    Тест на исключение DownloadError.

    Проверяет, что исключение DownloadError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = DownloadError("Сеть недоступна")
    assert "Ошибка скачивания: Сеть недоступна" in str(exc)

def test_token_error():
    """
    Тест на исключение TokenError.

    Проверяет, что исключение TokenError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = TokenError()
    assert "Неверный или отсутствующий токен Яндекс.Диска." in str(exc)

def test_integrity_error():
    """
    Тест на исключение IntegrityError.

    Проверяет, что исключение IntegrityError корректно создается,
    имеет корректную строку и код ошибки.
    """
    exc = IntegrityError("дубликат ключа")
    assert "Нарушение целостности данных: дубликат ключа" in str(exc)