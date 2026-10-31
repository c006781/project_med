# tests/test_dependencies_shared_db.py

"""
Один ``Database`` на приложение (``app/dependencies.py``, ТД-6, 2026-10-31).

``get_db()`` отдаёт общий объект: все сервисы работают через один движок и одну сессию
потока (``scoped_session``). Новая база — если общая закрыта или сменились настройки;
``reopen_db()`` открывает новую и закрывает прежнюю (новая не открылась — прежняя остаётся);
``close_db()`` закрывает и забывает. Сценарий «сервис фото + сервис приёмов в одном
потоке» — общие списки отложенных удалений сессии не выполняются чужой транзакцией (ТД-9).
"""

import datetime
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import pytest

from app.dto.dto_all import AppointmentDTO, PatientDTO


@pytest.fixture
def app_db(
    tmp_path    : Path,                 # папка временной базы и фото
    monkeypatch : pytest.MonkeyPatch,   # подмена настроек и общей базы
) -> Iterator[Tuple[Any, Dict[str, Any]]]:
    """
    Сборка приложения на временной базе: свои настройки, пустая общая база, сброшенный
    кэш сервисов (до и после теста).
    """
    import app.dependencies as deps

    config: Dict[str, Any] = {
        'database_local_path' : str(tmp_path / 'a.db'),     # база
        'PHOTOS_STORAGE_PATH' : str(tmp_path / 'photos'),   # фото
    }
    monkeypatch.setattr(
        deps,
        'get_config_env',          # настройки сборки
        lambda: dict(config),      # текущие значения словаря теста
    )
    monkeypatch.setattr(
        deps,
        '_shared_db',                  # общая база
        deps._SharedDatabase(),        # пустая — своя на тест
    )
    deps.clear_services_cache()
    yield deps, config
    deps.clear_services_cache()
    deps.close_db()


def test_get_db_returns_one_object(app_db) -> None:
    """ТД-6: повторный вызов — тот же объект (раньше — новый Database на каждый вызов)."""
    deps, _ = app_db
    db = deps.get_db()
    assert deps.get_db() is db
    assert not db.closed


def test_services_share_one_database(app_db) -> None:
    """Все сервисы реестра держат одну и ту же базу."""
    deps, _ = app_db
    db = deps.get_db()
    services = [provider() for provider in deps._SERVICE_PROVIDERS]
    assert len(services) == 4
    assert all(service._db is db for service in services)
    assert deps.get_patient_merge_service()._db is db


def test_closed_database_replaced(app_db) -> None:
    """Закрытую общую базу (сервис закрыл в reload_config) get_db не отдаёт — открывает новую."""
    deps, _ = app_db
    db = deps.get_db()
    db.close()
    assert db.closed
    new = deps.get_db()
    assert new is not db and not new.closed


def test_settings_change_opens_new_database(app_db, tmp_path) -> None:
    """Сменились путь или LOG_SQL_PARAMS без reopen_db — новая база по текущим настройкам."""
    deps, config = app_db
    first = deps.get_db()

    config['database_local_path'] = str(tmp_path / 'b.db')
    second = deps.get_db()
    assert second is not first
    assert Path(second.engine.url.database) == tmp_path / 'b.db'

    config['LOG_SQL_PARAMS'] = True
    third = deps.get_db()
    assert third is not second and third.log_sql_params is True
    assert deps.get_db() is third


def test_reopen_db_opens_new_and_closes_old(app_db, tmp_path) -> None:
    """reopen_db: новая база по настройкам становится общей, прежняя закрыта."""
    deps, config = app_db
    old = deps.get_db()
    config['database_local_path'] = str(tmp_path / 'b.db')
    new = deps.reopen_db()
    assert old.closed and not new.closed
    assert deps.get_db() is new
    assert Path(new.engine.url.database) == tmp_path / 'b.db'


def test_reopen_db_failure_keeps_old_open(app_db, monkeypatch) -> None:
    """Новая база не открылась — исключение, общей остаётся прежняя, открытая."""
    deps, _ = app_db
    old = deps.get_db()

    def failing_open(*args: Any, **kwargs: Any) -> None:
        """Открытие новой базы — ошибка (занята, нет доступа)."""
        raise RuntimeError('база занята')

    monkeypatch.setattr(
        deps,
        '_open_db',       # открытие базы
        failing_open,     # всегда ошибка
    )
    with pytest.raises(RuntimeError, match='база занята'):
        deps.reopen_db()
    assert not old.closed
    assert deps.get_db() is old


def test_close_db_forgets_database(app_db) -> None:
    """close_db закрывает общую базу; следующий get_db открывает новую; повтор безопасен."""
    deps, _ = app_db
    db = deps.get_db()
    deps.close_db()
    deps.close_db()
    assert db.closed
    assert deps.get_db() is not db


def test_database_close_twice_safe(app_db) -> None:
    """Database.close — повторный вызов без ошибки (сервисы закрывают уже закрытую базу)."""
    deps, _ = app_db
    db = deps.get_db()
    db.close()
    db.close()
    assert db.closed


def test_get_db_threads_get_one_object(app_db) -> None:
    """Одновременный первый вызов из нескольких потоков — одна база (под блокировкой)."""
    deps, _ = app_db
    results: List[Any] = []
    barrier = threading.Barrier(4)

    def worker() -> None:
        """Ждёт остальных и берёт базу."""
        barrier.wait()
        results.append(
            deps.get_db(),
        )

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 4
    assert all(db is results[0] for db in results)


def test_photo_and_appointment_services_one_thread(app_db, tmp_path) -> None:
    """
    ТД-6 + ТД-9: сервис фото и сервис приёмов в одном потоке — одна сессия (scoped_session)
    и общие списки отложенных удалений. Чужая транзакция не выполняет чужой список:
    копия фото из закоммиченной транзакции не удаляется откатом сервиса приёмов, файл фото
    из откатившегося удаления не удаляется коммитом сервиса приёмов.
    """
    from app.exceptions.exceptions_all import PatientNotFoundError

    deps, _ = app_db
    db = deps.get_db()
    patients = deps.get_patient_service()
    appointments = deps.get_appointment_service()
    photos = deps.get_photo_service()
    assert patients._db is appointments._db is photos._db is db

    patient = patients.create(
        PatientDTO(
            first_name = 'Иван',                          # имя
            last_name  = 'Петров',                        # фамилия
            birth_date = datetime.date(1980, 5, 5),       # дата рождения
        ),
    )
    appointment = appointments.create(
        AppointmentDTO(
            patient_id = patient.id,                      # пациент
            date       = datetime.date(2026, 10, 16),     # дата приёма
        ),
    )
    source = tmp_path / 'src.jpg'
    source.write_bytes(b'img')

    # 1. Фото добавлено (коммит): удаление копии «при откате» отброшено своим коммитом
    photo = photos.add_photo_to_appointment(
        appointment.id,   # приём
        str(source),      # исходный файл
        'описание',       # описание
    )
    stored = Path(photos._storage_path) / photo.file_path
    assert stored.exists()

    # Откат сервиса приёмов в том же потоке (той же сессии) — копию фото не трогает
    with pytest.raises(PatientNotFoundError):
        appointments.create(
            AppointmentDTO(
                patient_id = 999,                         # нет такого пациента
                date       = datetime.date(2026, 10, 17), # дата приёма
            ),
        )
    assert stored.exists(), 'копию фото удалил откат чужой транзакции'

    # 2. Удаление фото откатилось: удаление файла «после коммита» отброшено своим откатом
    with pytest.raises(RuntimeError):
        with db.session_scope() as session:
            photos.delete_photo(
                photo.id,
                session = session,   # внешняя транзакция
            )
            raise RuntimeError('сбой после удаления')

    # Коммит сервиса приёмов в том же потоке — файл фото не удаляет
    appointments.create(
        AppointmentDTO(
            patient_id = patient.id,                      # пациент
            date       = datetime.date(2026, 10, 18),     # дата приёма
        ),
    )
    assert stored.exists(), 'файл фото удалил коммит чужой транзакции'
    assert photos.get_by_id(photo.id) is not None
