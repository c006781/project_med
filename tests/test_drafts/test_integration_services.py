# tests/test_drafts/test_integration_services.py

"""
Черновики + сервисы приложения на настоящей SQLite во временной папке.

Проверяется связка ``app/draft/integration.py``: схема приложения, сохранение
нескольких таблиц ОДНОЙ транзакцией (D2), откат при ошибке, определение родителя
через БД, замена временных id во внешних ключах.
"""

import datetime

import pytest

from app.database import Database
from app.draft.integration import ServiceAdapter, build_app_schema, make_parent_resolver
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.services import AppointmentService, NoteService, PatientService, PhotoService
from app.utils.drafts import DraftStore, SaveScope, build_plan, execute_plan


@pytest.fixture
def services(tmp_path):
    """Сервисы на файле SQLite (настоящие commit/rollback) и папке фото — собраны
    так же, как в app/dependencies.py (с конфигурациями полей)."""
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    storage.mkdir()
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    yield {'patient': patient, 'appointment': appointment, 'photo': photo, 'db': db}
    db.close()


@pytest.fixture
def adapter(services):
    return ServiceAdapter({
        'patient': (lambda: services['patient'], PatientDTO),
        'appointment': (lambda: services['appointment'], AppointmentDTO),
        'photo': (lambda: services['photo'], PhotoDTO),
    })


@pytest.fixture
def store(adapter):
    schema = build_app_schema()
    return DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter))


@pytest.fixture
def image(tmp_path):
    path = tmp_path / 'src.jpg'
    path.write_bytes(b'\xff\xd8\xff\xe0fake-jpeg')
    return str(path)


def _patient(services, name='Иван'):
    return services['patient'].create(PatientDTO(first_name=name, last_name='Петров', birth_date=datetime.date(1980, 5, 5)))


def _appointment(services, patient_id):
    return services['appointment'].create(
        AppointmentDTO(patient_id=patient_id, date=datetime.date(2026, 10, 15)))


def test_new_branch_saved_in_one_transaction(services, store, adapter, image):
    """Новый пациент → новый приём → новое фото: одна транзакция, внешние ключи настоящие."""
    p = store.create('patient', {'first_name': 'Анна', 'last_name': 'Сидорова', 'birth_date': datetime.date(1990, 1, 1)})
    a = store.create('appointment', {'date': datetime.date(2026, 10, 15)}, parent_id=p)
    f = store.create('photo', {'file_path': image}, parent_id=a)

    result = execute_plan(store, build_plan(store), adapter)

    real_p, real_a, real_f = (result.id_map[k] for k in (('patient', p), ('appointment', a), ('photo', f)))
    assert services['appointment'].get_by_id(real_a).patient_id == real_p
    assert services['photo'].get_by_id(real_f).appointment_id == real_a
    assert store.is_empty


def test_failure_rolls_back_everything(services, store, adapter, image, monkeypatch):
    """D2: сбой на фото — ни пациента, ни приёма в БД; черновики на месте."""
    p = store.create('patient', {'first_name': 'Анна', 'last_name': 'Сидорова', 'birth_date': datetime.date(1990, 1, 1)})
    a = store.create('appointment', {'date': datetime.date(2026, 10, 15)}, parent_id=p)
    store.create('photo', {'file_path': image}, parent_id=a)

    def boom(dto, session=None):
        raise RuntimeError('диск')

    monkeypatch.setattr(services['photo'], 'create', boom)
    with pytest.raises(RuntimeError, match='диск'):
        execute_plan(store, build_plan(store), adapter)
    assert services['patient'].get_all() == []
    assert len(store.drafted_nodes()) == 3


def test_update_existing_and_resolver(services, store, adapter):
    """Изменение существующих записей; родитель приёма найден через БД (значок пациента)."""
    patient = _patient(services)
    appointment = _appointment(services, patient.id)
    store.modify('appointment', appointment.id, {'date': datetime.date(2026, 1, 2)})
    assert store.parent_of('appointment', appointment.id) == ('patient', patient.id)
    assert store.status('patient', patient.id) == 'child'

    execute_plan(store, build_plan(store, [('patient', patient.id)], SaveScope.BRANCH), adapter)
    assert services['appointment'].get_by_id(appointment.id).date == datetime.date(2026, 1, 2)


def test_delete_branch(services, store, adapter):
    patient = _patient(services)
    appointment = _appointment(services, patient.id)
    store.delete('appointment', appointment.id)
    plan = build_plan(store)
    assert plan.deleted_branches == (('appointment', appointment.id),)
    execute_plan(store, plan, adapter)
    assert services['appointment'].get_all() == []


def test_save_only_parent_then_child_later(services, store, adapter, image):
    """Сохранили только новый приём; фото осталось черновиком со ссылкой на настоящий id."""
    patient = _patient(services)
    a = store.create('appointment', {'date': datetime.date(2026, 10, 15)}, parent_id=patient.id)
    f = store.create('photo', {'file_path': image}, parent_id=a)
    result = execute_plan(store, build_plan(store, [('appointment', a)], SaveScope.SELF), adapter)
    real_a = result.id_map[('appointment', a)]
    assert store.get('photo', f).parent_id == real_a
    execute_plan(store, build_plan(store), adapter)
    assert services['photo'].get_all()[0].appointment_id == real_a


def test_b1_patient_repr_without_middle_name():
    """B1: repr пациента без отчества не падает и не обрезан (вызывается логом при add)."""
    from app.database.database_shema.clinic import Patient
    text = repr(Patient(first_name='Иван', last_name='Петров', middle_name=None))
    assert text == '<Patient(id=None, name=Петров Иван)>'


def test_transaction_factory_used(services, image):
    """Транзакция берётся из переданной фабрики (не из закрытого метода сервиса)."""
    used = []
    db = services['db']

    def factory():
        used.append(1)
        return db.session_scope()

    adapter = ServiceAdapter({
        'patient': (lambda: services['patient'], PatientDTO),
        'appointment': (lambda: services['appointment'], AppointmentDTO),
        'photo': (lambda: services['photo'], PhotoDTO),
    }, transaction_factory=factory)
    store = DraftStore(build_app_schema())
    store.create('patient', {'first_name': 'А', 'last_name': 'Б', 'birth_date': datetime.date(1990, 1, 1)})
    execute_plan(store, build_plan(store), adapter)
    assert used == [1] and len(services['patient'].get_all()) == 1


def test_conflict_detected_on_real_db(services, store, adapter):
    """Запись изменили в БД в обход черновика — конфликт виден до сохранения."""
    from app.utils.drafts import find_conflicts
    patient = _patient(services)
    store.modify('patient', patient.id, {'phone': '111'}, original={'phone': patient.phone})
    changed = patient.model_copy(update={'phone': '999'})
    services['patient'].update(changed)                       # «другой пользователь»
    conflicts = find_conflicts(build_plan(store), adapter.read)
    assert [(c.field, c.current) for c in conflicts] == [('phone', '999')]
    assert adapter.read('patient', 10**6) is None
