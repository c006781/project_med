# app/tables/clinic.py

"""
Таблицы клиники — одно описание на таблицу: пациенты → приёмы → фото.

Описания таблиц — ``app/schema/clinic.py`` (``CLINIC_DEFS``): из одного описания —
модель, DTO, ``field_configs`` и набор данных экрана. Здесь описание дополняется готовыми
классами (модель, DTO, настройки — из их модулей) и поставщиком сервиса.

Добавить таблицу (например, чеки об оплате): описание ``TableDef`` в ``app/schema/clinic.py``
и строка в ``CLINIC_DEFS``; модель, DTO и настройки полей — по одной строке в их модулях
(``Receipt = RECEIPTS.build_model(Base, …)`` и т. д.). Миграция БД создастся сама
(автомиграции); черновики, наборы, связи, экран — по описанию.

Пример:
    >>> CLINIC.chain()
    ['patients', 'appointments', 'photos']
    >>> CLINIC.get('appointments').columns
    ('date', 'reason_text', 'date_next', 'photo_count')
"""

from __future__ import annotations

import importlib
# import os
from typing import Any, Callable
# from typing import Any, Callable, Mapping, Optional
# ↑ до 2026-10-19: os, Mapping, Optional нужны были photo_image (перенесена в app/schema/clinic.py)

from app.database.database_shema import clinic as models
from app.dto import dto_all, field_configs
from app.schema.clinic import CLINIC_DEFS, photo_count_text, photo_image  # noqa: F401
from app.schema.define import TableDef

from .spec import TableRegistry, TableSpec
# from .spec import TableRegistry, TableSpec, calc, mark, total
# ↑ до 2026-10-19: mark/calc/total нужны были описаниям здесь; описания — в app/schema/clinic.py


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


# ↓ до 2026-10-19: photo_image и photo_count_text были здесь; перенесены в app/schema/clinic.py
#   (их использует описание таблиц), здесь — повторный экспорт.
# def photo_image(row: Mapping[str, Any], service: Any) -> Optional[str]:
#     """
#     Полный путь снимка строки фото (для предпросмотра).
#
#     В БД путь — относительно папки снимков сервиса (``app_51\\\\27_….png``); у нового фото
#     (черновик, ещё не скопирован в папку снимков) путь уже полный.
#
#     Args:
#         row: Строка фото.
#         service: Сервис фото (его папка снимков).
#
#     Returns:
#         Путь или ``None``.
#
#     Пример:
#         >>> photo_image({'file_path': 'app_1/a.png'}, photo_service)
#         'C:/data/photos/app_1/a.png'
#     """
#     path = row.get('file_path')
#     if not path:
#         return None
#     if os.path.isabs(path):
#         return path
#     # закрытое свойство сервиса: папку снимков он знает сам (из настроек)
#     return os.path.join(getattr(service, '_storage_path', None) or '', path)
#
#
# def photo_count_text(count: Any) -> str:
#     """
#     Число фото у приёма текстом — как у прежнего столбца ``has_photos``.
#
#     Args:
#         count: Число фото.
#
#     Returns:
#         ``'3 фото'`` или ``'❌'``.
#
#     Пример:
#         >>> photo_count_text(3), photo_count_text(0)
#         ('3 фото', '❌')
#     """
#     return f"{count} фото" if count else '❌'


def table_spec(definition: TableDef) -> TableSpec:
    """
    Описание набора экрана из описания таблицы: модель, DTO и настройки полей — готовые
    (из их модулей, по именам описания), сервис — через ``provider``.

    Args:
        definition: Описание таблицы.

    Returns:
        ``TableSpec``.

    Пример:
        >>> table_spec(PHOTOS).model is Photo
        True
    """
    return TableSpec(
        definition.name, definition.entity, definition.title, definition.label,
        getattr(models, definition.model_name), getattr(dto_all, definition.dto_name),
        getattr(field_configs, f'{definition.entity.upper()}_CONFIG'),
        service=provider(definition.service),
        order=definition.order, columns=definition.columns, form=definition.form,
        extras=definition.extras, parent=definition.parent, parent_field=definition.parent_field,
        links=definition.links, skip=definition.skip, fetch_size=definition.fetch_size,
    )


# ↓ до 2026-10-19: описания наборов были написаны здесь (модель, DTO, настройки — отдельно, в
#   своих модулях); теперь всё — из одного описания таблицы app/schema/clinic.py.
# CLINIC = TableRegistry([
#     TableSpec(
#         'patients', 'patient', 'Пациенты', 'Пациент', Patient, PatientDTO, PATIENT_CONFIG,
#         service=provider('get_patient_service'),
#         order=('last_name', 'first_name', 'id'),
#         columns=('mark', 'last_name', 'first_name', 'middle_name', 'birth_date', 'phone', 'visits'),
#         form=('last_name', 'first_name', 'middle_name', 'birth_date', 'phone',
#               'description_text', 'comment_text'),
#         # итоги считает БД отдельным запросом (GROUP BY по подчинённой таблице) — не в запросе
#         # таблицы данных; черновики учитываются поправкой (решение владельца 2026-10-18)
#         extras=(mark(), total('visits', 'Приёмов', 'appointments', by='sql')),
#     ),
#     TableSpec(
#         'appointments', 'appointment', 'Приёмы', 'Приём', Appointment, AppointmentDTO,
#         APPOINTMENT_CONFIG, service=provider('get_appointment_service'),
#         order=('-date', '-id'),
#         columns=('mark', 'date', 'reason_text', 'date_next', 'photo_count'),
#         form=('date', 'date_next', 'reason_text', 'procedure_text', 'recommendations_text',
#               'note_text', 'cost_procedure_text'),
#         # показ — как у прежнего столбца has_photos (formatter): «N фото» или «❌»; значение —
#         # число (сортировка по числу)
#         extras=(mark(), total('photo_count', 'Фото', 'photos', display=photo_count_text, by='sql')),
#         # старый итог has_photos (подзапрос в запросе приёмов) — набору не нужен: его
#         # заменил photo_count (отдельный запрос); старые экраны has_photos показывают по-прежнему
#         skip=('has_photos',),
#     ),
#     TableSpec(
#         'photos', 'photo', 'Фото', 'Фото', Photo, PhotoDTO, PHOTO_CONFIG,
#         service=provider('get_photo_service'),
#         order=('id',),
#         columns=('mark', 'file_path', 'description'),
#         form=('image', 'description'),
#         extras=(mark(), calc('image', 'Снимок', photo_image, visible=False, widget='image')),
#     ),
# ])

CLINIC = TableRegistry([table_spec(definition) for definition in CLINIC_DEFS])
