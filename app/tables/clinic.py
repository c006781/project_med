# app/tables/clinic.py

"""
Таблицы клиники — одно описание на таблицу: пациенты → приёмы → фото.

Добавить таблицу (например, чеки об оплате):
    1. модель (``app/database/database_shema/clinic.py``), DTO, ``field_configs``;
    2. описание ``TableSpec`` здесь (сервис — ``BaseService`` по описанию, свой код не
       нужен; родитель — из внешнего ключа модели);
    3. итог у родителя, если нужен: ``total('receipts_sum', 'Оплачено', 'receipts',
       AggFunc.SUM, 'amount')``.
Миграция БД создастся сама (автомиграции); черновики, наборы, связи, экран — по описанию.

Пример:
    >>> CLINIC.chain()
    ['patients', 'appointments', 'photos']
    >>> CLINIC.get('appointments').columns
    ('date', 'reason_text', 'date_next', 'photo_count')
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable, Mapping, Optional

from app.database.database_shema.clinic import Appointment, Patient, Photo
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG

from .spec import TableRegistry, TableSpec, calc, mark, total


def provider(name: str) -> Callable[[], Any]:
    """
    Поставщик сервиса из ``app.dependencies`` по имени функции — без импорта модуля
    заранее (циклы импортов сервисов) и с актуальным сервисом после смены БД.

    Args:
        name: Имя функции (``'get_patient_service'``).

    Returns:
        Функция без аргументов, возвращающая сервис.

    Пример:
        >>> provider('get_photo_service')()
        <PhotoService ...>
    """
    def get() -> Any:
        """
        Сервис из ``app.dependencies``.

        Returns:
            Сервис.

        Пример:
            >>> get()
        """
        return getattr(importlib.import_module('app.dependencies'), name)()

    get.__name__ = name
    return get


def photo_image(row: Mapping[str, Any], service: Any) -> Optional[str]:
    """
    Полный путь снимка строки фото (для предпросмотра).

    В БД путь — относительно папки снимков сервиса (``app_51\\\\27_….png``); у нового фото
    (черновик, ещё не скопирован в папку снимков) путь уже полный.

    Args:
        row: Строка фото.
        service: Сервис фото (его папка снимков).

    Returns:
        Путь или ``None``.

    Пример:
        >>> photo_image({'file_path': 'app_1/a.png'}, photo_service)
        'C:/data/photos/app_1/a.png'
    """
    path = row.get('file_path')
    if not path:
        return None
    if os.path.isabs(path):
        return path
    # закрытое свойство сервиса: папку снимков он знает сам (из настроек)
    return os.path.join(getattr(service, '_storage_path', None) or '', path)


def photo_count_text(count: Any) -> str:
    """
    Число фото у приёма текстом — как у прежнего столбца ``has_photos``.

    Args:
        count: Число фото.

    Returns:
        ``'3 фото'`` или ``'❌'``.

    Пример:
        >>> photo_count_text(3), photo_count_text(0)
        ('3 фото', '❌')
    """
    return f"{count} фото" if count else '❌'


CLINIC = TableRegistry([
    TableSpec(
        'patients', 'patient', 'Пациенты', 'Пациент', Patient, PatientDTO, PATIENT_CONFIG,
        service=provider('get_patient_service'),
        order=('last_name', 'first_name', 'id'),
        columns=('mark', 'last_name', 'first_name', 'middle_name', 'birth_date', 'phone', 'visits'),
        form=('last_name', 'first_name', 'middle_name', 'birth_date', 'phone',
              'description_text', 'comment_text'),
        extras=(mark(), total('visits', 'Приёмов', 'appointments')),
    ),
    TableSpec(
        'appointments', 'appointment', 'Приёмы', 'Приём', Appointment, AppointmentDTO,
        APPOINTMENT_CONFIG, service=provider('get_appointment_service'),
        order=('-date', '-id'),
        columns=('mark', 'date', 'reason_text', 'date_next', 'photo_count'),
        form=('date', 'date_next', 'reason_text', 'procedure_text', 'recommendations_text',
              'note_text', 'cost_procedure_text'),
        # показ — как у прежнего столбца has_photos (formatter): «N фото» или «❌»; значение —
        # число (сортировка по числу)
        extras=(mark(), total('photo_count', 'Фото', 'photos', display=photo_count_text)),
    ),
    TableSpec(
        'photos', 'photo', 'Фото', 'Фото', Photo, PhotoDTO, PHOTO_CONFIG,
        service=provider('get_photo_service'),
        order=('id',),
        columns=('mark', 'file_path', 'description'),
        form=('image', 'description'),
        extras=(mark(), calc('image', 'Снимок', photo_image, visible=False, widget='image')),
    ),
])
