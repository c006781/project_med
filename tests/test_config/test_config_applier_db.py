# tests/test_config/test_config_applier_db.py

"""
``ConfigApplier.apply_database`` и общий ``Database`` приложения (ТД-6, 2026-10-31).

Смена пути базы (или ``LOG_SQL_PARAMS``) на экране настроек: применитель из
``app.dependencies.create_config_applier()`` сначала переоткрывает общую базу
(``ServiceHooks.reopen_database`` → ``reopen_db``), потом перезагружает ТЕ ЖЕ объекты
сервисов — все переходят на одну новую базу, прежняя закрыта. Новая не открылась — ошибка в
``errors['database']``, сервисы остаются на прежней, открытой.
"""

import logging
from pathlib import Path
from typing import Any, List

import pytest

from app.dto.dto_all import PatientDTO
from tests.test_dependencies_shared_db import app_db  # noqa: F401 — фикстура


def _patient_dto(
    last_name : str,   # фамилия
) -> PatientDTO: # пациент для записи
    """Пациент с обязательными полями."""
    import datetime
    return PatientDTO(
        first_name = 'Иван',                      # имя
        last_name  = last_name,                   # фамилия
        birth_date = datetime.date(1980, 5, 5),   # дата рождения
    )


def test_apply_database_reopens_shared_database(
    app_db,           # noqa: F811 — сборка на временной базе
    tmp_path : Path,  # папка новой базы
) -> None:
    """Смена пути: одна новая база у всех сервисов реестра (те же объекты), прежняя закрыта."""
    deps, config = app_db
    services = [provider() for provider in deps._SERVICE_PROVIDERS]
    old_db = deps.get_db()
    services[0].create(
        _patient_dto('Старый'),
    )

    old_config = dict(config)
    config['database_local_path'] = str(tmp_path / 'b.db')
    applier = deps.create_config_applier()
    assert applier.apply_database(dict(config), old_config) is True

    new_db = deps.get_db()
    assert new_db is not old_db
    assert old_db.closed and not new_db.closed
    assert Path(new_db.engine.url.database) == tmp_path / 'b.db'
    assert [provider() for provider in deps._SERVICE_PROVIDERS] == services   # кэш не сброшен
    assert all(service._db is new_db for service in services)

    # Сервисы пишут в новый файл: в новой базе только новый пациент
    services[0].create(
        _patient_dto('Новый'),
    )
    names = [patient.last_name for patient in services[0].get_all()]
    assert names == ['Новый']


def test_apply_database_reopens_on_log_sql_params_flag(
    app_db,   # noqa: F811 — сборка на временной базе
) -> None:
    """Смена только LOG_SQL_PARAMS — новая общая база с флагом, сервисы на ней."""
    deps, config = app_db
    services = [provider() for provider in deps._SERVICE_PROVIDERS]
    old_db = deps.get_db()

    old_config = dict(config)
    config['LOG_SQL_PARAMS'] = True
    assert deps.create_config_applier().apply_database(dict(config), old_config) is True

    new_db = deps.get_db()
    assert new_db.log_sql_params is True and old_db.closed
    assert all(service._db is new_db for service in services)


def test_apply_database_failure_keeps_services_on_old_database(
    app_db,                          # noqa: F811 — сборка на временной базе
    tmp_path    : Path,              # папка новой базы
    monkeypatch : pytest.MonkeyPatch,  # ошибка открытия новой базы
) -> None:
    """Новая база не открылась: ошибка в errors, сервисы не перезагружались, прежняя открыта."""
    deps, config = app_db
    services = [provider() for provider in deps._SERVICE_PROVIDERS]
    old_db = deps.get_db()

    def failing_open(*args: Any, **kwargs: Any) -> None:
        """Открытие новой базы — ошибка (занята, нет доступа)."""
        raise RuntimeError('база занята')

    monkeypatch.setattr(
        deps,
        '_open_db',       # открытие базы
        failing_open,     # всегда ошибка
    )
    old_config = dict(config)
    config['database_local_path'] = str(tmp_path / 'b.db')
    applier = deps.create_config_applier()
    applier.apply_changes(
        {'database_local_path': old_config['database_local_path']},   # до сохранения
        {'database_local_path': config['database_local_path']},       # после
    )
    assert 'база занята' in str(applier.errors['database'])
    assert not old_db.closed
    assert all(service._db is old_db for service in services)
    services[0].create(
        _patient_dto('Петров'),
    )   # прежняя база работает


def test_apply_database_reopens_before_reloading_services() -> None:
    """Порядок: сначала переоткрыть общую базу, потом перезагружать сервисы."""
    from app.config.config_applier import ConfigApplier, ServiceHooks

    calls: List[str] = []
    service = type(
        'S',                                                    # заглушка сервиса
        (),
        {'reload_config': lambda self: calls.append('reload')},  # перезагрузка
    )()
    applier = ConfigApplier.__new__(ConfigApplier)
    applier.logger = logging.getLogger('test.applier')
    applier.services = ServiceHooks(
        service_providers   =   lambda: [lambda: service, lambda: service],   # два сервиса
        photo_service       =   lambda: None,                                 # не нужен
        sync_service        =   lambda: None,                                 # не нужен
        reopen_database     =   lambda: calls.append('reopen'),               # общая база
    )
    assert applier.apply_database(
        {'database_local_path': 'b.db'},   # после сохранения
        {'database_local_path': 'a.db'},   # до сохранения
    ) is True
    assert calls == ['reopen', 'reload', 'reload']


def test_create_config_applier_passes_reopen_db() -> None:
    """Применитель приложения переоткрывает общую базу через reopen_db."""
    import app.dependencies as deps
    assert deps.create_config_applier().services.reopen_database is deps.reopen_db
