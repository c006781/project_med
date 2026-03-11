# app/backend/__init__.py

"""
Пакет backend предоставляет слой доступа к данным и бизнес-логику приложения.

Он содержит:
- Database: класс для управления подключением к базе данных (движок, сессии).
- Репозитории (PatientRepository, AppointmentRepository, NoteRepository, PhotoRepository):
    инкапсулируют запросы к соответствующим таблицам, работают через сессию SQLAlchemy.

Использование:
    from app.backend import Database, PatientRepository

    # Создаём подключение (URL можно взять из конфига)
    db = Database("sqlite:///clinic.db")

    # Работаем в контексте сессии
    with db.session_scope() as session:
        repo = PatientRepository(session)
        patients = repo.get_all()
        ...

    # При завершении приложения можно закрыть пул сессий
    db.close()

Примечание: репозитории не управляют транзакциями самостоятельно — commit/rollback
выполняются на уровне session_scope или явным вызовом session.commit().
"""

from .database import Database

from .repositories.repositories_all import(
    PatientRepository,
    AppointmentRepository,
    AppointmentNoteRepository,
    PhotoRepository,
)

__all__ = [
    'Database',
    'BaseRepository',
    'PatientRepository',
    'AppointmentRepository',
    'AppointmentNoteRepository',
    'PhotoRepository'
]