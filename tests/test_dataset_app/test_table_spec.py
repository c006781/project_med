# tests/test_dataset_app/test_table_spec.py

"""
Одно описание таблицы (app.tables): дерево, черновики, наборы, свои столбцы — из описаний;
новая таблица подключается ОДНИМ описанием (раньше — правки в 4 местах).
"""

import datetime

import pytest

from app.database.database_shema.clinic import Appointment, Base, Patient
from app.draft.integration import AppDrafts, build_app_schema, make_parent_resolver
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, PATIENT_CONFIG
from app.services.services_all import BaseService
from app.tables import CLINIC, SpecError, TableRegistry, TableSpec, calc, total
from app.utils.dataset import AggFunc, Condition, Op
from app.utils.drafts import DraftStore

# относительный импорт — тот же модуль, под тем же именем, что импортирует pytest (имя
# зависит от пакетов выше tests; абсолютный путь дал бы второй модуль и модель объявилась
# бы дважды — «Table 'test_prescriptions' is already defined»)
from ..test_services.test_new_table_by_config import (  # noqa: E402
    PRESCRIPTION_CONFIG, Prescription, PrescriptionDTO,
)


def keys(ds):
    return [ds.key_at(i) for i in range(ds.row_count)]


# --------------------------------------------------------------------------- реестр

def test_clinic_tree_and_schema_same_as_before():
    assert CLINIC.names() == ['patients', 'appointments', 'photos']
    assert CLINIC.chain() == ['patients', 'appointments', 'photos']
    assert (CLINIC.parent('photos'), CLINIC.parent_field('photos')) == ('appointments', 'appointment_id')
    assert CLINIC.parent('patients') is None and CLINIC.children('patients') == ['appointments']
    described = [(t.name, t.parent, t.parent_field, t.label) for t in CLINIC.drafts_schema()]
    # assert described == [('patient', None, None, 'Пациент'),
    #                      ('appointment', 'patient', 'patient_id', 'Приём'),
    #                      ('photo', 'appointment', 'appointment_id', 'Фото')]
    # ↑ до 2026-10-31 (Ф1.3.4): заметок в схеме черновиков не было; теперь — корневой тип
    #   общих данных после дерева (test_notes_links.py)
    assert described == [('patient', None, None, 'Пациент'),
                         ('appointment', 'patient', 'patient_id', 'Приём'),
                         ('photo', 'appointment', 'appointment_id', 'Фото'),
                         ('note', None, None, 'Заметка')]
    assert [(t.name, t.parent) for t in build_app_schema()] == [(n, p) for n, p, _, _ in described]
    # assert CLINIC.service_adapter().entities() == ['patient', 'appointment', 'photo']
    assert CLINIC.service_adapter().entities() == ['patient', 'appointment', 'photo', 'note']


def spec(name, entity, model, dto, config, service=lambda: None, **kw):
    return TableSpec(name, entity, name, entity, model, dto, config, service=service, **kw)


def test_registry_errors():
    patients = spec('patients', 'patient', Patient, PatientDTO, PATIENT_CONFIG)
    with pytest.raises(SpecError, match='дважды'):
        TableRegistry([patients, patients])
    with pytest.raises(SpecError, match='не описан'):
        TableRegistry([spec('appointments', 'appointment', Appointment, AppointmentDTO, APPOINTMENT_CONFIG,
                            parent='doctors')])
    with pytest.raises(SpecError, match='не описана'):
        TableRegistry([spec('patients', 'patient', Patient, PatientDTO, PATIENT_CONFIG,
                            extras=(total('x', 'X', 'nowhere'),))])
    with pytest.raises(SpecError, match='не подчинена'):
        TableRegistry([spec('patients', 'patient', Patient, PatientDTO, PATIENT_CONFIG),
                       spec('appointments', 'appointment', Appointment, AppointmentDTO, APPOINTMENT_CONFIG,
                            extras=(total('x', 'X', 'patients'),))])
    with pytest.raises(KeyError, match='нет таблицы'):
        CLINIC.get('nowhere')


# --------------------------------------------------------------------------- свои столбцы клиники

def test_clinic_extras_marks_and_totals(services, providers, filled):
    built = CLINIC.build(services=providers)
    built.open()
    patients, visits = built.patients, built['appointments']
    assert [patients.value('visits', i) for i in range(patients.row_count)] == [2, 1]
    assert patients.fields['mark'].local and patients.fields['visits'].aggregate is not None
    assert visits.value('photo_count') == 0
    patients.set_local('mark', True, index=1)
    assert patients.local_keys('mark') == [filled['petrov']]
    visits.append({'date': datetime.date(2026, 10, 18)}); visits.post()
    assert patients.value('visits') == 3                         # итог — сразу (через связь)
    assert built.photos.fields['image'].extra == {'widget': 'image'}
    built.close()


def test_build_subset_with_parents(services, providers, filled):
    built = CLINIC.build(services=providers, tables=['appointments'])
    assert [d.name for d in built.datasets] == ['patients', 'appointments']
    assert 'visits' in built.patients.fields                       # итог по собранной подчинённой
    only = CLINIC.build(services=providers, tables=['patients'])
    assert 'visits' not in only.patients.fields                    # подчинённой нет — итога нет


# --------------------------------------------------------------------------- новая таблица одним описанием

def clinic_with_prescriptions(rx_service):
    """Реестр клиники + назначения: ОДНО описание; у приёма — итог «Назначений»."""
    base = [CLINIC.get(n) for n in CLINIC.names()]
    appointments = base[1]
    appointments = TableSpec(**{**appointments.__dict__,
                                'extras': appointments.extras + (total('rx_count', 'Назначений',
                                                                      'test_prescriptions'),)})
    return TableRegistry([base[0], appointments, base[2], TableSpec(
        'test_prescriptions', 'prescription', 'Назначения', 'Назначение', Prescription, PrescriptionDTO,
        PRESCRIPTION_CONFIG, service=lambda: rx_service, order=('id',),
        extras=(calc('dose_upper', 'ДОЗА', lambda row: (row.get('dosage') or '').upper()),),
    )])


@pytest.fixture
def rx(services):
    Base.metadata.create_all(services['db'].engine)              # тестовая модель — без миграции
    from app.services import NoteService
    from app.dto.field_configs import NOTE_CONFIG
    return BaseService(services['db'], None, Prescription, PrescriptionDTO, PRESCRIPTION_CONFIG,
                       note_service=NoteService(services['db'], field_configs=NOTE_CONFIG))


def test_new_table_by_one_description(services, providers, filled, rx):
    registry = clinic_with_prescriptions(rx)
    assert registry.parent('test_prescriptions') == 'appointments'          # из внешнего ключа
    assert registry.chain() == ['patients', 'appointments', 'photos']
    assert registry.children('appointments') == ['photos', 'test_prescriptions']
    assert [t.name for t in registry.drafts_schema()] == ['patient', 'appointment', 'photo', 'prescription']
    built = registry.build(services=providers)
    built.open()
    prescriptions, visits = built['test_prescriptions'], built.appointments
    prescriptions.append({'dosage': '1 т.', 'instruction_text': 'после еды'}); prescriptions.post()
    saved = rx.get_page(0, 10)[0][0]
    assert saved.appointment_id == visits.current_key and saved.instruction_text == 'после еды'
    assert prescriptions.value('dose_upper') == '1 Т.' and visits.value('rx_count') == 1


def test_new_table_in_drafts_mode(services, providers, filled, rx):
    """Раньше: SchemaError «неизвестный тип сущности 'prescription'» — теперь черновики по описанию."""
    registry = clinic_with_prescriptions(rx)
    schema = registry.drafts_schema()
    adapter = registry.service_adapter(transaction_factory=lambda: services['db'].session_scope(),
                                       services={**providers, 'prescription': lambda: rx})
    drafts = AppDrafts(schema, adapter, DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter)))
    built = registry.build(services=providers, drafts=drafts)
    built.open()
    prescriptions, visits = built['test_prescriptions'], built.appointments
    prescriptions.append({'dosage': '2 т.'}); prescriptions.post()
    assert prescriptions.current_key < 0 and rx.get_page(0, 10)[1] == 0      # в БД — ещё нет
    assert visits.value('rx_count') == 1                                    # итог видит черновик
    built.save()
    items, total_rows = rx.get_page(0, 10)
    assert total_rows == 1 and items[0].dosage == '2 т.' and items[0].appointment_id == visits.current_key
    assert visits.value('rx_count') == 1 and prescriptions.current_key > 0


def test_total_with_where_and_sum(services, providers, filled, rx):
    base = [CLINIC.get(n) for n in CLINIC.names()]
    appointments = TableSpec(**{**base[1].__dict__, 'extras': (
        total('long_doses', 'Длинных', 'test_prescriptions', where=(Condition('dosage', Op.CONTAINS, 'таб'),)),
        total('max_id', 'Последнее', 'test_prescriptions', AggFunc.MAX, 'id'))})
    registry = TableRegistry([base[0], appointments, TableSpec(
        'test_prescriptions', 'prescription', 'Назначения', 'Назначение', Prescription, PrescriptionDTO,
        PRESCRIPTION_CONFIG, service=lambda: rx)])
    built = registry.build(services=providers)
    built.open()
    for dosage in ('1 таб.', '2 таб.', '5 мл'):
        built['test_prescriptions'].append({'dosage': dosage}); built['test_prescriptions'].post()
    assert built.appointments.value('long_doses') == 2
    assert built.appointments.value('max_id') == max(p.id for p in rx.get_page(0, 10)[0])


def test_custom_total_logic_and_initial_photo_text(services, providers, filled, rx):
    """Итоги настраиваемые: своя функция от подчинённых строк; число фото — показ как прежде («❌»/«N фото»)."""
    built = CLINIC.build(services=providers)
    built.open()
    assert built.appointments.value('photo_count') == 0 and built.appointments.text('photo_count') == '❌'
    base = [CLINIC.get(n) for n in CLINIC.names()]
    appointments = TableSpec(**{**base[1].__dict__, 'extras': (
        total('doses', 'Дозы', 'test_prescriptions',
              lambda rows: ', '.join(sorted(r['dosage'] for r in rows)) or '—'),)})
    registry = TableRegistry([base[0], appointments, TableSpec(
        'test_prescriptions', 'prescription', 'Назначения', 'Назначение', Prescription, PrescriptionDTO,
        PRESCRIPTION_CONFIG, service=lambda: rx)])
    built = registry.build(services=providers)
    built.open()
    assert built.appointments.value('doses') == '—'
    for dosage in ('2 т.', '1 т.'):
        built['test_prescriptions'].append({'dosage': dosage}); built['test_prescriptions'].post()
    assert built.appointments.value('doses') == '1 т., 2 т.'
