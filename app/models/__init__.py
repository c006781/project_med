# /home/admin-rkc/Git/My_cods/project_med/app/models/__init__.py
"""
Пакет app.models — содержит подпакет bd с моделями SQLAlchemy.
"""

# Импортируем модели из подпакета bd
from .bd import (
    Patient, 
    Appointment, 
    AppointmentNote, 
    Photo,
)

# Также можно импортировать функцию генерации тестовых данных, если она нужна на этом уровне
from .bd import (
    generate_test_data,
)

# Определяем публичный интерфейс
__all__ = [
    'Patient',
    'Appointment',
    'AppointmentNote',
    'Photo',
    'generate_test_data',
]
