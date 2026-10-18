# app/dataset_app/__init__.py

"""
Наборы данных (``app.utils.dataset``) в приложении клиники: поля из ``field_configs``,
источник поверх сервисов, мост к черновикам, готовые наборы пациенты → приёмы → фото.

Здесь — всё, что знает о приложении; переносимые пакеты ``app.utils.dataset`` и
``app.utils.dataset_qt`` о нём не знают. Устройство — ``IMPLEMENTATION.md`` рядом.

Пример:
    >>> from app.dataset_app import create_clinic_datasets
    >>> clinic = create_clinic_datasets(); clinic.open()
"""

from .drafts_writer import DraftsWriter
from .factory import SPECS, ClinicDataSets, create_clinic_datasets, default_services
from .fields import fields_from_config, kind_of, references_of
from .service_backend import ServiceBackend, to_service_filter
from .sql_totals import SqlTotals

__all__ = [
    'DraftsWriter',
    'SPECS', 'ClinicDataSets', 'create_clinic_datasets', 'default_services',
    'fields_from_config', 'kind_of', 'references_of',
    'ServiceBackend', 'to_service_filter',
    'SqlTotals',
]
