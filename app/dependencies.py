# app/dependencies.py
"""
Модуль зависимостей: фабричные функции для получения сервисов и работы с БД.
"""

import os
# from app.database.database import Database
from app.database import Database
# from .controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import get_config_env
from app.services import (
    PatientService,
    AppointmentService,
    NoteService,
    PhotoService,
    SyncService
)
# from .backend.bd.clinic import create_db
# from .backend.bd.temp_data_bd import generate_test_data
from app.utils.logger import AppLogger


def get_db() -> Database:
    """
    Возвращает экземпляр Database, сконфигурированный из .env.

    Database - это класс, который инкапсулирует логику работы с базой данных.
    Он принимает строку подключения к базе данных в виде url (например, sqlite:///path/to/db.db).

    Returns:
        Database: экземпляр Database, готовый к работе.
    """
    config = get_config_env()
    db_path = config['database_local_path']
    db_url = f"sqlite:///{db_path}"
    
    # Логгирование: информируем о том, какой файл используется для базы данных
    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Возвращает экземпляр Database, сконфигурированный из .env.: {db_path} ({os.path.abspath(db_path)})"
    )

    return Database(db_url)


def get_patient_service() -> PatientService:
    """
    Возвращает экземпляр PatientService, инициализированный с помощью Database.

    Returns:
        PatientService: экземпляр PatientService, готовый к работе.
    """

    return PatientService(get_db())


# def get_appointment_service() -> AppointmentService:
#     db = get_db()
#     note_service = get_note_service()  # можно передать существующий, но проще создать новый
#     return AppointmentService(db, note_service=note_service)

def get_appointment_service() -> AppointmentService:
    """
    Возвращает экземпляр AppointmentService, инициализированный с помощью Database,
    NoteService и PhotoService.

    Returns:
        AppointmentService: экземпляр AppointmentService, готовый к работе.
    """
    db = get_db()
    note_service = get_note_service()
    photo_service = get_photo_service()   
    # Create an instance of AppointmentService with the database, note service, and photo service.
    return AppointmentService(db, note_service=note_service, photo_service=photo_service)


def get_note_service() -> NoteService:
    """
    Возвращает экземпляр NoteService, инициализированный с помощью Database.
    Returns:
        NoteService: экземпляр NoteService, готовый к работе.
    """
    # Create an instance of NoteService with the database.
    return NoteService(get_db())


def get_photo_service() -> PhotoService:
    """
    Возвращает экземпляр PhotoService, инициализированный с помощью Database и пути к хранилищу фотографий.
    """
    config = get_config_env()
    photos_path = config.get('PHOTOS_STORAGE_PATH', './photos')
    return PhotoService(get_db(), photos_path)


def get_sync_service() -> SyncService:
    """
    Возвращает экземпляр SyncService, инициализированный с помощью токена Яндекс.Диска.
    """
    return SyncService()


def init_db(
        recreate: bool = False, 
        test_data: bool = True
    ):
    """
    Инициализировать базу данных (создать таблицы, опционально заполнить тестовыми данными).

    :param recreate: bool, optional
        Если True, то удалить существующую базу данных перед инициализацией.
        Defaults to False.
    :param test_data: bool, optional
        Если True, то заполнить тестовыми данными.
        Defaults to True.
    """
    db = get_db()
    db.create_tables(recreate=recreate)
    if test_data:
        db.fill_test_data()

# def get_key_value_dto(
#         dto, 
#         exclude_fields=None
# )->dict:
#     """
#     Выводит все поля DTO в формате "Название поля: значение".
#     :param dto: экземпляр Pydantic DTO
#     :param exclude_fields: список полей, которые не нужно выводить (например, ['id'])
#     """
#     return_ = {}
#     data = dto.model_dump(exclude_none=True)  # исключаем поля с None
#     for key, value in data.items():
#         if exclude_fields and key in exclude_fields:
#             continue
#         # Преобразуем имя поля в заголовок (например, 'first_name' -> 'First Name')
#         title = key.replace('_', ' ').title()
#         return_[title] = value
#         # click.echo(f"{title}: {value}")
#     return return_

def get_key_value_dto(
        dto, 
        exclude_fields=None
    ):
    """
    Преобразует Pydantic DTO в словарь вида {человеко-читаемое название: значение}.
    
    :param dto: экземпляр Pydantic DTO
    :param exclude_fields: список полей, которые не нужно выводить (например, ['id'])
    """
    data = dto.model_dump(exclude_none=True)
    if exclude_fields:
        data = {k: v for k, v in data.items() if k not in exclude_fields}
    return {k.replace('_', ' ').title(): v for k, v in data.items()}