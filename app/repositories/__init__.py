# app/repositories/__init__.py

"""
Все репозитории для работы с БД (реализация — ``repositories_all.py``).

Наружу — четыре репозитория таблиц; базовый ``BaseRepository`` импортируется из
``app.repositories.repositories_all``. Слои ``app.schema`` и ``app.dto`` этот пакет не
импортируют (проверяют ``tests/test_dto_layers.py``, ``tests/test_schema/test_schema_layers.py``).

Example:
    >>> from app.repositories import PatientRepository
    >>> with db.session_scope() as session:
    ...     PatientRepository(session).count()
    3
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