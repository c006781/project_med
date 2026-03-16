# app/dependencies.py
"""
Модуль зависимостей: фабричные функции для получения сервисов и работы с БД.
"""

import os
from .backend.database import Database
from .controllers.conf.get_config import get_config_env
# from .controllers.config_manager.manager import get_config_env
from .services import (
    PatientService,
    AppointmentService,
    NoteService,
    PhotoService,
    SyncService,
)
from .models.bd.models import create_db
from .models.bd.temp_data_bd import generate_test_data
from .utils.logger import AppLogger


def get_db() -> Database:
    """Возвращает экземпляр Database, сконфигурированный из .env."""

    config = get_config_env()
    db_path = config['database_local_path']
    db_url = f"sqlite:///{db_path}"

    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Возвращает экземпляр Database, сконфигурированный из .env.: {db_path} ({os.path.abspath(db_path)})"
    )

    return Database(db_url)


def get_patient_service() -> PatientService:
    return PatientService(get_db())


def get_appointment_service() -> AppointmentService:
    db = get_db()
    note_service = get_note_service()  # можно передать существующий, но проще создать новый
    return AppointmentService(db, note_service=note_service)


def get_note_service() -> NoteService:
    return NoteService(get_db())


def get_photo_service() -> PhotoService:
    config = get_config_env()
    photos_path = config.get('PHOTOS_STORAGE_PATH', './photos')
    return PhotoService(get_db(), photos_path)


def get_sync_service() -> SyncService:
    return SyncService()


def init_db(recreate: bool = False, test_data: bool = True):
    db = get_db()
    db.create_tables(recreate=recreate)
    if test_data:
        db.fill_test_data()