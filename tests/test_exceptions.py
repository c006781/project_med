# tests/test_exceptions.py
import pytest
from app.exceptions import (
    PatientNotFoundError, PatientValidationError,
    AppointmentNotFoundError, AppointmentNoteNotFoundError,
    PhotoNotFoundError, PhotoFileError,
    DownloadError, UploadError, TokenError,
    DatabaseError, IntegrityError, ConnectionError
)

def test_patient_not_found_error():
    exc = PatientNotFoundError(42)
    assert str(exc) == "[1001] Пациент с идентификатором 42 не найден."
    assert exc.code == 1001

def test_patient_validation_error():
    exc = PatientValidationError("first_name", "пустое")
    assert "Ошибка валидации поля 'first_name': пустое." in str(exc)

def test_appointment_not_found_error():
    exc = AppointmentNotFoundError(10)
    assert "Приём с идентификатором 10 не найден." in str(exc)

def test_photo_file_error():
    exc = PhotoFileError("/path", "копирование", "нет места")
    assert "Ошибка копирование файла '/path': нет места" in str(exc)

def test_download_error():
    exc = DownloadError("Сеть недоступна")
    assert "Ошибка скачивания: Сеть недоступна" in str(exc)

def test_token_error():
    exc = TokenError()
    assert "Неверный или отсутствующий токен Яндекс.Диска." in str(exc)

def test_integrity_error():
    exc = IntegrityError("дубликат ключа")
    assert "Нарушение целостности данных: дубликат ключа" in str(exc)