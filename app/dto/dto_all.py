# app/dto/dto_all.py
"""
DTO (Data Transfer Objects) на базе Pydantic.
Обеспечивают автоматическую валидацию и сериализацию.
"""
import datetime
# from datetime import date
# from datetime import time as time_datetime_dto_all
from typing import Optional, List

from pydantic import BaseModel, ConfigDict , Field # pip install pydantic>=2.0



class PatientDTO(BaseModel):
    """DTO для пациента"""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        # metadata={
        #     'title': 'ID',
        #     'editable': False,
        #     'hide_in_form': True,
        # },
        description='ID пациента (None для нового)',
    )
    first_name: str = Field(
        ...,
        # metadata={
        #     'title': 'Имя',
        #     'editable': True,
        # },
        description='Имя пациента',
    )
    last_name: str = Field(
        ...,
        # metadata={
        #     'title': 'Фамилия',
        #     'editable': True,
        # },
        description='Фамилия пациента',
    )
    birth_date: Optional[datetime.date] = Field(
        None,
        # metadata={
        #     'title': 'Дата рождения',
        #     'editable': True,
        # },
        description='Дата рождения (ГГГГ-ММ-ДД)',

    )
    phone: Optional[str] = Field(
        None,
        # metadata={
        #     'title': 'Телефон',
        #     'editable': True,
        # },
        description='Номер телефона',
    )
    email: Optional[str] = Field(
        None,
        # metadata={
        #     'title': 'Email',
        #     'editable': True,
        # },
        description='Электронная почта',
    )


class AppointmentNoteDTO(BaseModel):
    """DTO для заметки к приёму"""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        # metadata={
        #     'title': 'ID',
        #     'editable': False,
        #     'hide_in_form': True,
        # },
        description='ID заметки (None для новой)'
    )
    text: str = Field(
        ...,
        # metadata={
        #     'title': 'Текст заметки',
        #     'editable': True,
        # },
        description='Содержимое заметки'
    )

class PhotoDTO(BaseModel):
    """
    DTO для фотографии.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        # metadata={
        #     'title': 'ID',
        #     'editable': False,
        #     'hide_in_form': True,  # в форме не показываем
        # },
        description='ID фотографии',
    )
    appointment_id: int = Field(
        ...,
        # metadata={
        #     'title': 'ID приёма',
        #     'editable': False,
        #     'hide_in_form': True,  # или можно оставить только для чтения, но лучше скрыть
        # },
        description='ID приёма, к которому относится фото',
    )
    file_path: str = Field(
        ...,
        # metadata={
        #     'title': 'Путь к файлу',
        #     'editable': False,
        #     'hide_in_form': True,  # путь генерируется автоматически
        # },
        description='Относительный путь к файлу',
    )
    description: Optional[str] = Field(
        None,
        # metadata={
        #     'title': 'Описание',
        #     'editable': True,
        # },
        description='Описание фотографии',
    )

class AppointmentDTO(BaseModel):
    """
    DTO для приёма.
    Содержит как поля из модели Appointment, так и дополнительные
    для отображения (patient_name, note_text).
    """
    
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        # metadata={
        #     'title': 'ID',
        #     'editable': False,
        #     'hide_in_form': True,
        # },
        description='ID приёма (None для нового)',
    )
    patient_id: int = Field(
        ...,
        # metadata={
        #     'title': 'Пациент',
        #     'editable': False,
        #     'hide_in_form': True,
        # },
        description='ID пациента',
    )

    patient_name: Optional[str] = Field(
        None,
        # metadata={
        #     'title': 'Пациент',
        #     'editable': False,
        #     'virtual': True,
        # },
        description='Имя пациента',
    )

    date: datetime.date = Field(
        ...,
        # metadata={
        #     'title': 'Дата',
        #     'editable': True,
        # },
        description='Дата приёма'
    )
    time: Optional[datetime.time] = Field(
        None,
        # metadata={
        #     'title': 'Время',
        #     'editable': True,
        # },
        description='Время приёма',
    )
    note_id: Optional[int] = Field(
        None,
        # metadata={
        #     'hide_in_form': True,
        # },
        description='ID заметки',
    )
    note_text: Optional[str] = Field(
        None,
        # metadata={
        #     # 'title': 'Заметка',
        #     # 'editable': True,
        #     # 'virtual': True,
        #     'title': 'Заметка',
        #     'editable': True,
        #     'virtual': True,
        #     'widget_type': 'completer_with_edit',  # или completer_with_create
        #     'choices_provider': 'note_service.get_choices',
        #     'edit_window': 'note_edit'
        # },
        description='Текст заметки',
    )
    photos: Optional[List['PhotoDTO']] = Field(
        None, 
        description='Фотографии приёма'
    )
    # photos: List[PhotoDTO]