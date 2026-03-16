# app/dto/__init__.py
"""
Пакет объектов передачи данных (DTO).
DTO используются для безопасной передачи данных между слоями приложения,
особенно в GUI, чтобы избежать проблем с detached-объектами SQLAlchemy.
"""

from app.dto.dto_all import (
    BaseDTO,
    PatientDTO,
    AppointmentDTO,
    AppointmentNoteDTO,
    PhotoDTO,
)
__all__ = [
    'BaseDTO',
    'PatientDTO',
    'AppointmentDTO',
    'AppointmentNoteDTO',
    'PhotoDTO',
]