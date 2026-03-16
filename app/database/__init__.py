# app/database/__init__.py



# Импортируем модели из подпакета bd
from app.database.database_shema import (
    Patient, 
    Appointment, 
    AppointmentNote, 
    Photo,
)

# Также можно импортировать функцию генерации тестовых данных, если она нужна на этом уровне
from app.database.database_shema import (
    generate_test_data,
)


from app.database.database import Database

__all__ = [
    'Patient',
    'Appointment',
    'AppointmentNote',
    'Photo',
    'generate_test_data',

    'Database',
]