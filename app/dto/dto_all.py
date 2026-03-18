# app/dto/dto_all.py
"""
DTO (Data Transfer Objects) на базе Pydantic.
Обеспечивают автоматическую валидацию и сериализацию.
"""
import datetime
# from datetime import date
# from datetime import time as time_datetime_dto_all
from typing import Optional
from pydantic import BaseModel, ConfigDict # pip install pydantic>=2.0


class PatientDTO(BaseModel):
    """
    DTO для пациента.
    Соответствует модели Patient, но может содержать дополнительные вычисляемые поля.
    """
    # Конфигурация: разрешаем создание объекта из ORM-модели (from_attributes=True)
    model_config = ConfigDict(from_attributes=True) # включает режим, при котором можно создать DTO из ORM-объекта через

    id: Optional[int] = None          # ID пациента (None для нового)
    first_name: str                    # Имя (обязательно)
    last_name: str                      # Фамилия (обязательно)
    birth_date: Optional[datetime.date] = None   # Дата рождения
    phone: Optional[str] = None          # Телефон
    email: Optional[str] = None          # Email


class AppointmentNoteDTO(BaseModel):
    """DTO для заметки приёма."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    text: str


class PhotoDTO(BaseModel):
    """DTO для фотографии."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    appointment_id: int
    file_path: str
    description: Optional[str] = None


class AppointmentDTO(BaseModel):
    """
    DTO для приёма.
    Содержит как поля из модели Appointment, так и дополнительные
    для отображения (patient_name, note_text).
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    patient_id: int
    date: datetime.date
    time: Optional[datetime.time] = None
    # time: time = None
    note_id: Optional[int] = None

    # Виртуальные поля (не хранятся в БД, но удобны для отображения)
    patient_name: Optional[str] = None
    note_text: Optional[str] = None