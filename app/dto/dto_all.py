# app/dto/dto_all.py
"""
DTO (Data Transfer Objects) на базе Pydantic.

Обеспечивают автоматическую валидацию, сериализацию и десериализацию данных
при передаче между слоями приложения (сервисы, GUI, CLI).

Содержатся DTO для:
    - PatientDTO       – пациент
    - AppointmentNoteDTO – заметка к приёму
    - PhotoDTO         – фотография
    - AppointmentDTO   – приём (включая виртуальные поля)

Для каждого DTO установлена конфигурация `from_attributes = True`, что позволяет
создавать DTO из ORM-объектов SQLAlchemy через `model_validate(obj)`.

Пример:
    >>> dto = PatientDTO(first_name="Иван", last_name="Петров")
    >>> print(dto.model_dump())
    {'first_name': 'Иван', 'last_name': 'Петров'}
"""

import datetime

from typing import (
    # Dict, 
    Optional, 
    List, 
    # Tuple
)

from pydantic import ( # pip install pydantic>=2.0
    BaseModel, 
    ConfigDict, 
    Field,
) 
# from app.dto import PhotoDTO  # для аннотации в AppointmentDTO

class PatientDTO(BaseModel):
    """
    DTO для пациента. Используется для передачи данных между слоями.

    Атрибуты:
        id (Optional[int]): Уникальный идентификатор (None для новой записи).
        first_name (str): Имя пациента (обязательное).
        last_name (str): Фамилия пациента (обязательное).
        birth_date (Optional[datetime.date]): Дата рождения.
        phone (Optional[str]): Номер телефона.
        email (Optional[str]): Адрес электронной почты.

    Конфигурация:
        from_attributes = True – позволяет создавать DTO из ORM-объектов SQLAlchemy.

    Пример:
        >>> dto = PatientDTO(
        ...     first_name="Иван",
        ...     last_name="Петров",
        ...     birth_date=datetime.date(1990, 5, 12)
        ... )
        >>> print(dto.model_dump())
        {'first_name': 'Иван', 'last_name': 'Петров', 'birth_date': datetime.date(1990, 5, 12)}
    """

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        description='ID пациента (None для нового)',
    )
    first_name: str = Field(
        ...,
        description='Имя',
    )
    middle_name: Optional[str] = Field(
        None, 
        description='Отчество'
    )
    last_name: str = Field(
        ...,
        description='Фамилия',
    )
    birth_date: Optional[datetime.date] = Field(
        None,
        description='Дата рождения (ГГГГ-ММ-ДД)',
    )
    phone: Optional[str] = Field(
        None,
        description='Номер телефона',
    )
    # email: Optional[str] = Field(
    #     None,
    #     description='Электронная почта',
    # )
    description_text: Optional[str] = Field(
        None, 
        description='Описание пациента (виртуальное)'
    )
    comment_text: Optional[str] = Field(
        None, 
        description='Комментарий к пациенту (виртуальное)'
    )
    # для внутреннего использования (ID заметок) – скрыты
    description_id: Optional[int] = Field(
        None, 
        exclude=True
    )
    comment_id: Optional[int] = Field(
        None, 
        exclude=True
    )


class AppointmentDTO(BaseModel):
    """
    DTO для приёма (визита) пациента.

    Содержит как основные поля модели Appointment, так и дополнительные
    виртуальные поля (`patient_name`, `note_text`, `has_photos`), которые
    вычисляются на основе связанных объектов (пациент, заметка, фото).

    Атрибуты:
        id (Optional[int]): Уникальный идентификатор приёма (None – для нового).
        patient_id (int): ID пациента (обязательный).
        patient_name (Optional[str]): Виртуальное поле – ФИО пациента.
        date (datetime.date): Дата приёма.
        time (Optional[datetime.time]): Время приёма.
        note_id (Optional[int]): ID заметки (если есть).
        note_text (Optional[str]): Виртуальное поле – текст заметки.
        photos (Optional[List[PhotoDTO]]): Список фотографий, привязанных к приёму.
        has_photos (Optional[str]): Виртуальное поле – индикатор наличия фото
            (например, "3 фото" или "❌").

    Конфигурация:
        model_config = ConfigDict(from_attributes=True).

    Примечания:
        - Поля `patient_name`, `note_text`, `has_photos` не сохраняются в БД,
          они заполняются при формировании DTO из ORM-объекта.
        - При создании/обновлении через `AppointmentService` поле `note_text`
          может использоваться для автоматического поиска/создания заметки.

    Пример:
        >>> app_dto = AppointmentDTO(
        ...     patient_id=1,
        ...     date=datetime.date(2025, 3, 10),
        ...     time=datetime.time(10, 30),
        ...     note_text="Первичный осмотр"
        ... )
        >>> # при сохранении заметка будет найдена или создана автоматически
    """
    
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        description='ID приёма (None для нового)',
    )
    patient_id: int = Field(
        ...,
        description='ID пациента',
    )
    patient_name: Optional[str] = Field(
        None,
        description='Имя пациента',
    )
    date: datetime.date = Field(
        ...,
        description='Дата приёма'
    )
    date_next: Optional[datetime.date] = Field(
        None, 
        description='Дата следующего приёма'
    )
    # time: Optional[datetime.time] = Field(
    #     None,
    #     description='Время приёма',
    # )
    # note_id: Optional[int] = Field(
    #     None,
    #     description='ID заметки',
    # )
    # note_text: Optional[str] = Field(
    #     None,
    #     description='Текст заметки',
    # )

    # Виртуальные поля для текстов (берутся из связанных заметок)
    reason_text: Optional[str] = Field(
        None, 
        description='Причина обращения'
    )
    procedure_text: Optional[str] = Field(
        None, 
        description='Выполненная процедура'
    )
    recommendations_text: Optional[str] = Field(
        None, 
        description='Рекомендации'
    )
    note_text: Optional[str] = Field(
        None, 
        description='Примечание'
    )
    cost_procedure_text: Optional[str] = Field(
        None, 
        description='Стоимость процедуры'
    )

    # # Также можно добавить виртуальное поле для заметки (оставляем совместимость)
    # note_text: Optional[str] = Field(
    #     None, 
    #     description='Примечание (синоним note)'
    # )

    # Скрытые ID заметок (для внутреннего использования)
    reason_id: Optional[int] = Field(
        None, 
        exclude=True
    )
    procedure_id: Optional[int] = Field(
        None, 
        exclude=True
    )
    recommendations_id: Optional[int] = Field(
        None, 
        exclude=True
    )
    note_id: Optional[int] = Field(
        None, 
        exclude=True
    )
    cost_procedure_id: Optional[int] = Field(
        None, 
        exclude=True
    )

    photos: Optional[List['PhotoDTO']] = Field(
        None, 
        description='Фотографии приёма'
    )
    has_photos: Optional[str] = Field(
        None, 
        description='Наличие фото'
    )


class PhotoDTO(BaseModel):
    """
    DTO для фотографии, прикреплённой к приёму.

    Содержит информацию о файле и его описании. Путь к файлу хранится
    относительно папки `PHOTOS_STORAGE_PATH` (настраивается в конфигурации).

    Атрибуты:
        id (Optional[int]): Уникальный идентификатор фотографии.
        appointment_id (int): ID приёма, к которому относится фото.
        file_path (str): Относительный путь к файлу.
        description (Optional[str]): Описание фотографии.

    Конфигурация:
        model_config = ConfigDict(from_attributes=True).

    Примечание:
        В формах и таблицах это поле используется только для чтения;
        для загрузки новых фото используется отдельный механизм.

    Пример:
        >>> photo = PhotoDTO(
        ...     id=5,
        ...     appointment_id=10,
        ...     file_path="app_10/5_face.jpg",
        ...     description="Лицо"
        ... )
    """

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        description='ID фотографии',
    )
    appointment_id: int = Field(
        ...,
        description='ID приёма, к которому относится фото',
    )
    file_path: str = Field(
        ...,
        description='Относительный путь к файлу',
    )
    description: Optional[str] = Field(
        None,
        description='Описание фотографии',
    )


class AppointmentNoteDTO(BaseModel):
    """
    DTO для заметки приёма.

    Используется для передачи текста заметки, которая может быть привязана
    к одному или нескольким приёмам.

    Атрибуты:
        id (Optional[int]): Уникальный идентификатор заметки (None – для новой).
        text (str): Содержимое заметки (обязательное).

    Конфигурация:
        model_config = ConfigDict(from_attributes=True).

    Пример:
        >>> note_dto = AppointmentNoteDTO(text="Первичный осмотр. Жалобы на головную боль.")
        >>> print(note_dto.text)
        'Первичный осмотр. Жалобы на головную боль.'
    """

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None,
        description='ID заметки (None для новой)'
    )
    text: str = Field(
        ...,
        description='Содержимое заметки'
    )