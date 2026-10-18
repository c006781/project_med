# app/dataset_app/factory.py

"""
Готовые наборы данных клиники: пациенты → приёмы → фото, со связями.

Режимы записи:
    * без черновиков — ``post()`` сразу в БД (через сервисы);
    * с черновиками (``drafts=AppDrafts``) — правки копятся (``DraftsWriter``),
      сохранение разом — ``ClinicDataSets.save(...)`` (тот же план и вопросы, что у
      экранов черновиков).

Загрузка — параметрами: ``fetch_mode`` (всё сразу / порциями), ``fetch_size``.

Пример:
    >>> clinic = create_clinic_datasets(drafts=create_app_drafts(), fetch_size=50)
    >>> clinic.open()
    >>> clinic.patients.locate(5); clinic.appointments.row_count
    3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Type

import os

from app.utils.dataset import DataSet, DataSource, FetchMode, FieldDef, MasterDetailLink

# from .fields import fields_from_config
# from .service_backend import ServiceBackend
# ↑ до 2026-10-18: нужны были сборке наборов здесь — теперь её делает app.tables

# Набор: (имя набора = таблица, тип записи черновиков, сортировка по умолчанию)
SPECS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    ('patients', 'patient', ('last_name', 'first_name', 'id')),
    ('appointments', 'appointment', ('-date', '-id')),
    ('photos', 'photo', ('id',)),
)


def default_services() -> Dict[str, Callable[[], Any]]:
    """
    Поставщики сервисов приложения (``app.dependencies``) — берутся при каждой операции.

    Returns:
        «тип записи → функция, возвращающая сервис».

    Пример:
        >>> sorted(default_services())
        ['appointment', 'patient', 'photo']
    """
    from app.dependencies import (  # здесь, а не наверху: циклы импортов сервисов
        get_appointment_service, get_patient_service, get_photo_service,
    )
    return {'patient': get_patient_service, 'appointment': get_appointment_service,
            'photo': get_photo_service}


def photo_image_field(photo_service: Callable[[], Any]) -> FieldDef:
    """
    Вычисляемое поле ``image`` набора фото — полный путь к файлу снимка (для
    предпросмотра, аналог ``TDBImage``).

    В БД путь хранится относительно папки снимков сервиса (``app_51\27_….png``); у
    нового фото (черновик, ещё не скопирован в папку снимков) путь уже полный.

    Args:
        photo_service: Поставщик сервиса фото (его папка снимков — на момент показа).

    Returns:
        ``FieldDef('image', calculated=...)``.

    Пример:
        >>> photo_image_field(get_photo_service).calculated({'file_path': 'app_1/a.png'})
        'C:/data/photos/app_1/a.png'
    """
    def resolve(row: Mapping[str, Any]) -> Optional[str]:
        """
        Полный путь снимка строки фото.

        Args:
            row: Строка фото.

        Returns:
            Путь или ``None`` (пути нет).

        Пример:
            >>> resolve({'file_path': 'app_1/a.png'})
            'C:/data/photos/app_1/a.png'
        """
        path = row.get('file_path')
        if not path:
            return None
        if os.path.isabs(path):
            return path
        # закрытое свойство сервиса: папку снимков он знает сам (из настроек)
        storage = getattr(photo_service(), '_storage_path', None) or ''
        return os.path.join(storage, path)

    return FieldDef('image', 'Снимок', calculated=resolve, visible=False)


def _table_parts(entity: str) -> Tuple[Type[Any], Mapping[str, Any], Any]:
    """
    DTO, настройки полей и модель типа записи.

    Args:
        entity: Тип записи.

    Returns:
        ``(класс DTO, field_configs, модель SQLAlchemy)``.

    Пример:
        >>> _table_parts('photo')[0].__name__
        'PhotoDTO'
    """
    from app.database.database_shema.clinic import Appointment, Patient, Photo
    from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
    from app.dto.field_configs import APPOINTMENT_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
    return {
        'patient': (PatientDTO, PATIENT_CONFIG, Patient),
        'appointment': (AppointmentDTO, APPOINTMENT_CONFIG, Appointment),
        'photo': (PhotoDTO, PHOTO_CONFIG, Photo),
    }[entity]


@dataclass
class ClinicDataSets:
    """
    (не используется с 2026-10-18: наборы собирает ``app.tables`` — ``BuiltTables``;
    оставлен как было, по правилу проекта)

    Наборы клиники и всё, что их связывает.

    Attributes:
        patients / appointments / photos: Наборы.
        sources: «имя набора → DataSource» (для экрана).
        links: Связи пациенты → приёмы → фото.
        drafts: Черновики приложения (``None`` — запись сразу в БД).
        writers: Мосты к черновикам по именам наборов (пусто без черновиков).

    Пример:
        >>> clinic.sources['patients'].dataset is clinic.patients
        True
    """

    patients: DataSet
    appointments: DataSet
    photos: DataSet
    sources: Dict[str, DataSource]
    links: List[MasterDetailLink]
    drafts: Any = None
    writers: Dict[str, Any] = field(default_factory=dict)

    @property
    def datasets(self) -> List[DataSet]:
        """
        Наборы сверху вниз по дереву.

        Returns:
            ``[patients, appointments, photos]``.

        Пример:
            >>> [d.name for d in clinic.datasets]
            ['patients', 'appointments', 'photos']
        """
        return [self.patients, self.appointments, self.photos]

    def open(self) -> None:
        """
        Открывает наборы сверху вниз (подчинённые сразу получают условие связи).

        Returns:
            None

        Пример:
            >>> clinic.open()
        """
        for dataset in self.datasets:
            dataset.open()

    def close(self) -> None:
        """
        Закрывает наборы снизу вверх и отключает мосты к черновикам.

        Returns:
            None

        Пример:
            >>> clinic.close()
        """
        for dataset in reversed(self.datasets):
            dataset.close()
        for writer in self.writers.values():
            writer.close()

    def post_all(self) -> None:
        """
        Завершает незавершённые правки всех наборов (перед сохранением черновиков).

        Returns:
            None

        Raises:
            ValidationError: Строка не прошла проверку.

        Пример:
            >>> clinic.post_all()
        """
        for dataset in self.datasets:
            if dataset.active:
                dataset.post()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        """
        Сохраняет черновики (см. ``AppDrafts.save``); перед этим — ``post_all``.

        Args:
            *args: Аргументы ``AppDrafts.save`` (цели, направления, вопросы…).
            **kwargs: То же.

        Returns:
            Итог сохранения или ``None`` (отказ пользователя).

        Raises:
            RuntimeError: Наборы без черновиков (сохранять нечего — всё уже в БД).

        Пример:
            >>> clinic.save(confirm_new_ancestors=ask, confirm_deletes=ask)
        """
        if self.drafts is None:
            raise RuntimeError("наборы без черновиков: правки уже в БД")
        self.post_all()
        return self.drafts.save(*args, **kwargs)


def create_clinic_datasets(
    *,
    drafts: Any = None,
    services: Optional[Mapping[str, Callable[[], Any]]] = None,
    fetch_mode: FetchMode = FetchMode.ON_DEMAND,
    fetch_size: int = 50,
    sizes: Optional[Mapping[str, int]] = None,
) -> Any:
    """
    Собирает наборы клиники со связями — по описаниям таблиц (``app.tables.CLINIC``).

    Args:
        drafts: Черновики (``AppDrafts``); ``None`` — запись сразу в БД.
        services: «тип записи → поставщик сервиса» (по умолчанию — ``app.dependencies``).
        fetch_mode: Всё сразу или порциями.
        fetch_size: Размер порции.
        sizes: Свой размер порции для отдельных наборов («имя → размер»).

    Returns:
        ``BuiltTables`` (наборы ещё закрыты — ``open()``): ``clinic.patients``,
        ``clinic['appointments']``, ``clinic.sources``, ``clinic.writers``…

    Пример:
        >>> clinic = create_clinic_datasets(fetch_mode=FetchMode.ALL)
    """
    # providers = dict(services or default_services())
    # built: Dict[str, DataSet] = {}
    # writers: Dict[str, Any] = {}
    # for name, entity, order in SPECS:
    #     dto_class, config, model = _table_parts(entity)
    #     fields = fields_from_config(config, dto_class, model)
    #     if entity == 'photo':
    #         fields.append(photo_image_field(providers['photo']))
    #     backend = ServiceBackend(providers[entity], dto_class, fields)
    #     writer = None
    #     if drafts is not None:
    #         from .drafts_writer import DraftsWriter
    #         writer = DraftsWriter(drafts.store, entity)
    #         writers[name] = writer
    #     dataset = DataSet(backend, name=name, writer=writer, order=order,
    #                       fetch_mode=fetch_mode, fetch_size=(sizes or {}).get(name, fetch_size))
    #     if writer is not None:
    #         writer.attach(dataset)
    #     built[name] = dataset
    # sources = {name: DataSource(ds) for name, ds in built.items()}
    # links = [
    #     MasterDetailLink(sources['patients'], built['appointments']),
    #     MasterDetailLink(sources['appointments'], built['photos']),
    # ]
    # return ClinicDataSets(built['patients'], built['appointments'], built['photos'],
    #                       sources, links, drafts, writers)
    # ↑ до 2026-10-18: таблицы, поля, связи перечислялись здесь вручную (три таблицы клиники) —
    #   новая таблица требовала правки этого файла. Теперь всё — из описаний таблиц
    #   (app/tables: одно описание на таблицу; свои столбцы — отметки, итоги по подчинённым).
    from app.tables import CLINIC         # здесь, а не наверху: app.tables импортирует этот пакет
    return CLINIC.build(drafts=drafts, services=services, fetch_mode=fetch_mode,
                        fetch_size=fetch_size, sizes=sizes)
