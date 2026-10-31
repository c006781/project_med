# tests/test_drafts/test_integration_services.py

"""
Черновики + сервисы приложения на настоящей SQLite во временной папке.

Проверяется связка ``app/draft/integration.py``: схема приложения, сохранение
нескольких таблиц ОДНОЙ транзакцией (D2), откат при ошибке, определение родителя
через БД, замена временных id во внешних ключах.
"""

import datetime

import pytest

from app.draft.integration import ServiceAdapter, build_app_schema, make_parent_resolver
from app.dto.dto_all import AppointmentDTO, AppointmentNoteDTO, PatientDTO, PhotoDTO
from app.exceptions import PatientNotFoundError
from app.utils.drafts import DraftStore, SaveScope, build_plan, execute_plan

# Фикстура services (сервисы на временной SQLite) — в tests/test_drafts/conftest.py
# (с 2026-10-31, М16: общая с test_app_pages.py).


@pytest.fixture
def adapter(services):
    return ServiceAdapter({
        'patient': (lambda: services['patient'], PatientDTO),
        'appointment': (lambda: services['appointment'], AppointmentDTO),
        'photo': (lambda: services['photo'], PhotoDTO),
        'note': (lambda: services['note'], AppointmentNoteDTO),
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
        'note': (lambda: services['note'], AppointmentNoteDTO),
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


def test_reparent_photo_through_drafts_saved(services, store, adapter, image):
    """Перенос фото в другой приём через черновики сохраняется (раньше сервис молча
    отбрасывал изменение appointment_id — решение владельца 2026-10-16: перенос разрешён)."""
    patient = _patient(services)
    a1, a2 = _appointment(services, patient.id), _appointment(services, patient.id)
    photo = services['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=image))
    store.modify('photo', photo.id, {'appointment_id': a2.id},
                 original={'appointment_id': a1.id}, parent_id=a1.id)
    assert store.status('appointment', a2.id) == 'child'
    execute_plan(store, build_plan(store), adapter)
    assert services['photo'].get_by_id(photo.id).appointment_id == a2.id


# ---------------------------------------------------------------------------
# М16 (2026-10-31): «не найдено» — по типу исключения (DB2, DB3)
# ---------------------------------------------------------------------------

class _RaisingService:
    """Сервис-заглушка: get_by_id выбрасывает заданное исключение."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_by_id(self, entity_id, session=None):
        raise self.error


def test_read_missing_record_is_none(adapter):
    """DB2: записи нет в БД — read возвращает None (исключение сервиса «не найдено»)."""
    assert adapter.read('patient', 999) is None


def test_read_not_found_by_type_not_by_name():
    """DB2: «не найдено» — только EntityNotFoundError и наследники; FileNotFoundError
    (в имени тоже есть «NotFound») — ошибка, а не «записи нет»."""
    adapter = ServiceAdapter({'patient': (lambda: _RaisingService(PatientNotFoundError(5)), PatientDTO)})
    assert adapter.read('patient', 5) is None
    adapter = ServiceAdapter({'patient': (lambda: _RaisingService(FileNotFoundError('a.jpg')), PatientDTO)})
    with pytest.raises(FileNotFoundError):
        adapter.read('patient', 5)


def test_parent_resolver_missing_record_logs_without_traceback(caplog):
    """DB3: записи уже нет — None и строка журнала без трассировки; прочая ошибка —
    None и запись с трассировкой."""
    schema = build_app_schema()
    missing = ServiceAdapter({'appointment': (lambda: _RaisingService(PatientNotFoundError(7)), AppointmentDTO)})
    broken = ServiceAdapter({'appointment': (lambda: _RaisingService(RuntimeError('сбой БД')), AppointmentDTO)})
    with caplog.at_level('DEBUG', logger='app.draft.integration'):
        assert make_parent_resolver(schema, missing)('appointment', 7) is None
        assert make_parent_resolver(schema, broken)('appointment', 8) is None
    records = [r for r in caplog.records if r.name == 'app.draft.integration']
    assert [(r.levelname, r.exc_info is not None) for r in records] == [
        ('WARNING', False), ('ERROR', True)]

