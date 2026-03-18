# app/dto/__init__.py
"""
Пакет объектов передачи данных (DTO) на Pydantic.
"""
from .dto_all import (
    PatientDTO,
    AppointmentDTO,
    AppointmentNoteDTO,
    PhotoDTO,
)

__all__ = [
    'PatientDTO',
    'AppointmentDTO',
    'AppointmentNoteDTO',
    'PhotoDTO',
]