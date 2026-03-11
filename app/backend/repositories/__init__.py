# app/backend/repositories/__init__.py
"""
Все репозитории для работы с БД
"""

from .repositories_all import( 
    PatientRepository, 
    AppointmentRepository, 
    AppointmentNoteRepository,
    PhotoRepository
)

__all__ = [
    'PatientRepository', 
    'AppointmentRepository', 
    'AppointmentNoteRepository', 
    'PhotoRepository'
]