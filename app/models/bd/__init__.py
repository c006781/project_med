# /home/admin-rkc/Git/My_cods/project_med/app/models/bd/__init__.py
"""
Пакет app.models.bd — модели базы данных (SQLAlchemy).

Содержит:
- models.py: ORM-классы Patient, Appointment, AppointmentNote, Photo.
- temp_data_bd.py: функции для заполнения тестовыми данными (generate_test_data).
"""

# Импортируем классы моделей из модуля models
from .models import (
    Patient, 
    Appointment, 
    AppointmentNote, 
    Photo,
)

# Импортируем функцию генерации тестовых данных из temp_data_bd
from .temp_data_bd import (
    generate_test_data,
)

# Экспортируем публичный интерфейс пакета
__all__ = [
    'Patient',
    'Appointment',
    'AppointmentNote',
    'Photo',
    'generate_test_data',
]

# Примечание: Функции create_db, init_db определены в models.py, но они скорее служебные.
