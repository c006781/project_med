# tests/test_dataset_app/test_app_layer.py

"""
Наборы данных в приложении — на настоящей SQLite во временной папке: поля из
field_configs, источник поверх сервисов, запись сразу в БД и через черновики,
связи пациенты → приёмы → фото.
"""

import datetime

import pytest

from app.dataset_app import (
    DraftsWriter, ServiceBackend, create_clinic_datasets, fields_from_config, to_service_filter,
)
from app.dto.dto_all import AppointmentDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, PATIENT_CONFIG
from app.utils.dataset import (
    Condition, FetchMode, FieldKind, Op, Order, Query, State, ValidationError,
)


def keys(ds):
    return [ds.key_at(i) for i in range(ds.row_count)]


# --------------------------------------------------------------------------- поля

def test_fields_from_config():
    from app.database.database_shema.clinic import Appointment
    fields = {f.name: f for f in fields_from_config(APPOINTMENT_CONFIG, AppointmentDTO, Appointment)}
    assert 'photos' not in fields                                  # вложенный список — не поле
    assert fields['patient_id'].references == 'patients' and fields['patient_id'].stored
    assert fields['patient_id'].read_only and fields['patient_id'].required
    assert fields['reason_id'].references is None and not fields['reason_id'].stored  # ссылка на заметку
    assert fields['reason_text'].stored and fields['reason_text'].editable           # заметку сохранит сервис
    assert fields['reason_text'].kind is FieldKind.TEXT
    assert not fields['patient_name'].stored and not fields['patient_name'].editable  # вычисляет сервис
    assert fields['date'].kind is FieldKind.DATE and fields['date'].label == 'Дата приёма' or fields['date'].label
    assert not fields['id'].stored and fields['id'].read_only and not fields['id'].required
    assert fields['has_photos'].extra['config']['virtual']


def test_patient_fields_order_and_visibility():
    names = [f.name for f in fields_from_config(PATIENT_CONFIG, PatientDTO)]
    assert names[:6] == ['id', 'last_name', 'first_name', 'middle_name', 'birth_date', 'phone']
    visible = [f.name for f in fields_from_config(PATIENT_CONFIG, PatientDTO) if f.visible]
    assert 'id' not in visible and 'description_text' in visible


@pytest.mark.parametrize('condition, expected', [
    (Condition('a', Op.EQ, 1), {'column': 'a', 'operator': 'eq', 'value': 1}),
    (Condition('a', Op.EQ, None), {'column': 'a', 'operator': 'is_null', 'value': None}),
    (Condition('a', Op.IN, (1, 2)), {'column': 'a', 'operator': 'in', 'value': [1, 2]}),
    (Condition('a', Op.CONTAINS, 'x'), {'column': 'a', 'operator': 'ilike', 'value': 'x'}),
    (Condition('a', Op.IS_NULL, False), {'column': 'a', 'operator': 'is_not_null', 'value': None}),
])
def test_condition_to_service_filter(condition, expected):
    assert to_service_filter(condition) == expected


def test_startswith_not_silently_replaced():
    with pytest.raises(ValueError, match='startswith'):
        to_service_filter(Condition('a', Op.STARTSWITH, 'x'))


# --------------------------------------------------------------------------- источник

def test_service_backend_reads_and_writes(services, filled):
    fields = fields_from_config(PATIENT_CONFIG, PatientDTO)
    backend = ServiceBackend(lambda: services['patient'], PatientDTO, fields)
    page = backend.fetch(Query(order=(Order('last_name', True),), limit=1))
    assert page.total == 2 and page.rows[0]['last_name'] == 'Петров'
    page = backend.fetch(Query(conditions=(Condition('last_name', Op.CONTAINS, 'иван'),)))
    assert [r['last_name'] for r in page.rows] == ['Иванов']
    assert backend.get(404) is None
    created = backend.insert({'id': None, 'last_name': 'Сидоров', 'first_name': 'С',
                              'birth_date': datetime.date(2000, 1, 1), 'description_text': 'аллергия'})
    assert created['id'] and created['description_text'] == 'аллергия'            # заметку сохранил сервис
    updated = backend.update(created['id'], {'phone': '+7 900'})
    assert updated['phone'] == '+7 900' and updated['description_text'] == 'аллергия'
    backend.delete(created['id'])
    assert backend.get(created['id']) is None


# --------------------------------------------------------------------------- наборы сразу в БД

def test_direct_master_detail_chain(services, providers, filled):
    clinic = create_clinic_datasets(services=providers, fetch_size=10)
    clinic.open()
    assert [clinic.patients.value('last_name', i) for i in range(clinic.patients.row_count)] == ['Иванов', 'Петров']
    assert clinic.appointments.row_count == 2                                      # приёмы Иванова
    assert clinic.appointments.value('date') == datetime.date(2026, 3, 5)          # сортировка -date
    assert clinic.appointments.value('patient_name')                               # вычислил сервис
    clinic.patients.next()
    assert clinic.appointments.row_count == 1 and clinic.photos.row_count == 0
    clinic.appointments.append({'date': datetime.date(2026, 10, 18), 'reason_text': 'контроль'})
    clinic.appointments.post()
    saved = services['appointment'].get_by_id(clinic.appointments.current_key)
    assert saved.patient_id == filled['petrov'] and saved.reason_text == 'контроль'
    clinic.close()


def test_direct_validation_and_service_errors(services, providers, filled):
    clinic = create_clinic_datasets(services=providers)
    clinic.open()
    clinic.patients.set_value('last_name', '')
    with pytest.raises(ValidationError):
        clinic.patients.post()
    clinic.patients.cancel()
    clinic.patients.append({'last_name': 'Без', 'first_name': 'Даты'})            # дата обязательна
    with pytest.raises(ValidationError, match='Дата рождения'):
        clinic.patients.post()
    assert clinic.patients.state is State.INSERT
    clinic.patients.cancel()
    clinic.close()


def test_on_demand_and_all_modes(services, providers, filled):
    p = services['patient']
    for i in range(7):
        p.create(PatientDTO(last_name=f'Ф{i}', first_name='И', birth_date=datetime.date(2000, 1, 1)))
    portions = create_clinic_datasets(services=providers, fetch_size=3)
    portions.open()
    assert portions.patients.row_count == 3 and portions.patients.total == 9 and portions.patients.has_more
    portions.patients.last()
    assert portions.patients.row_count == 9
    everything = create_clinic_datasets(services=providers, fetch_mode=FetchMode.ALL, sizes={'patients': 1})
    everything.open()
    assert everything.patients.row_count == 9 and not everything.patients.has_more


# --------------------------------------------------------------------------- через черновики

def test_drafts_mode_keeps_changes_until_save(services, providers, filled, app_drafts):
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    clinic.patients.set_value('phone', '+7 111')
    clinic.patients.post()
    assert services['patient'].get_by_id(filled['ivanov']).phone is None          # в БД — ещё нет
    assert clinic.patients.row_status(0) == 'modified'
    clinic.appointments.append({'date': datetime.date(2026, 10, 18)})
    clinic.appointments.post()
    new_id = clinic.appointments.current_key
    assert new_id < 0 and clinic.appointments.row_status() == 'new'
    assert clinic.patients.row_status(0) in ('modified',)                          # своё изменение важнее
    clinic.patients.next(); clinic.patients.prior()                                # ушли и вернулись
    assert new_id in keys(clinic.appointments)                                     # черновик виден снова
    result = clinic.save()
    assert result is not None
    assert services['patient'].get_by_id(filled['ivanov']).phone == '+7 111'
    real = [a for a in services['appointment'].get_all() if a.date == datetime.date(2026, 10, 18)]
    assert len(real) == 1 and real[0].patient_id == filled['ivanov']
    assert clinic.appointments.row_count == 3 and all(k > 0 for k in keys(clinic.appointments))
    assert clinic.patients.row_status(0) is None and app_drafts.store.is_empty
    clinic.close()


def test_drafts_new_patient_with_children_saved_from_parents(services, providers, filled, app_drafts):
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    clinic.patients.append({'last_name': 'Новый', 'first_name': 'Н', 'birth_date': datetime.date(2001, 1, 1)})
    clinic.patients.post()
    assert clinic.patients.current_key < 0
    assert clinic.appointments.can_modify and clinic.appointments.row_count == 0  # временный id — можно добавлять
    clinic.appointments.append({'date': datetime.date(2026, 10, 18)})
    clinic.appointments.post()
    assert clinic.appointments.value('patient_id') == clinic.patients.current_key
    clinic.save()
    names = sorted(p.last_name for p in services['patient'].get_all())
    assert names == ['Иванов', 'Новый', 'Петров']
    new = next(p for p in services['patient'].get_all() if p.last_name == 'Новый')
    assert [a.patient_id for a in services['appointment'].get_all() if a.date == datetime.date(2026, 10, 18)] == [new.id]
    assert clinic.patients.current_key == new.id or new.id in keys(clinic.patients)
    clinic.close()


def test_drafts_delete_marks_and_child_status(services, providers, filled, app_drafts):
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    first = clinic.appointments.current_key
    clinic.appointments.delete()
    assert first in keys(clinic.appointments) and clinic.appointments.row_status() == 'deleted'
    assert clinic.patients.row_status(0) == 'child'                               # значок у пациента
    asked = []
    clinic.save(confirm_deletes=lambda branches: asked.append(branches) or True)
    with pytest.raises(Exception, match='не найден'):
        services['appointment'].get_by_id(first)
    assert first not in keys(clinic.appointments) and clinic.patients.row_status(0) is None
    clinic.close()


def test_drafts_undo_refreshes_datasets(services, providers, filled, app_drafts):
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    clinic.patients.set_value('phone', '+7 222'); clinic.patients.post()
    assert clinic.patients.value('phone') == '+7 222'
    app_drafts.store.undo()
    assert clinic.patients.value('phone') is None and clinic.patients.row_status(0) is None
    app_drafts.store.redo()
    assert clinic.patients.value('phone') == '+7 222'
    clinic.close()


def test_drafts_change_elsewhere_while_editing_applied_after(services, providers, filled, app_drafts):
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    clinic.patients.set_value('middle_name', 'Иванович')                           # правка идёт
    app_drafts.store.modify('patient', filled['petrov'], {'phone': '+7 333'}, original={'phone': None})
    assert clinic.patients.state is State.EDIT                                     # правку не сбили
    clinic.patients.post()
    clinic.patients.locate(filled['petrov'])
    assert clinic.patients.value('phone') == '+7 333'                              # перечитали после правки
    clinic.close()


def test_save_without_drafts_refused(services, providers, filled):
    clinic = create_clinic_datasets(services=providers)
    with pytest.raises(RuntimeError, match='без черновиков'):
        clinic.save()


def test_drafts_writer_requires_its_dataset(app_drafts, services):
    from app.utils.dataset import DataSet, MemoryBackend
    writer = DraftsWriter(app_drafts.store, 'patient')
    with pytest.raises(ValueError, match='другой способ записи'):
        writer.attach(DataSet(MemoryBackend([])))


def test_case_insensitive_search_cyrillic(services, filled):
    """APP1: «иван» находит «Иванов» (встроенный lower() SQLite понимает только латиницу)."""
    items, total = services['patient'].get_page_filtered(
        0, 10, [{'column': 'last_name', 'operator': 'ilike', 'value': 'ИВАН'}])
    assert [p.last_name for p in items] == ['Иванов']


def test_patient_name_without_middle_name(services, filled):
    """APP3: у приёма пациента без отчества ФИО есть (раньше — пусто)."""
    items, _ = services['appointment'].get_page_filtered(0, 10, None, None, None)
    assert {a.patient_name for a in items} == {'Иванов Иван', 'Петров Пётр'}


def test_service_backend_get_missing_with_entity_specific_error(services, filled):
    """APP2: сервисы бросают AppointmentNotFoundError (не LookupError) — источник отвечает «нет записи»."""
    fields = fields_from_config(APPOINTMENT_CONFIG, AppointmentDTO)
    backend = ServiceBackend(lambda: services['appointment'], AppointmentDTO, fields)
    assert backend.get(99999) is None


def test_drafts_undelete(services, providers, filled, app_drafts):
    """D5: вернуть строку, помеченную на удаление."""
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    clinic.appointments.delete()
    writer = clinic.writers['appointments']
    assert writer.undelete(clinic.appointments)
    assert clinic.appointments.row_status() is None and app_drafts.store.is_empty
    assert not writer.undelete(clinic.appointments)
    clinic.close()


def test_save_reads_each_dataset_few_times(services, providers, filled, monkeypatch):
    """
    G2: число чтений БД при сохранении черновиков не растёт с числом сохраняемых записей
    (было — по нескольку чтений на каждую: 181 на 15 записей). Наборы и итоги
    (число приёмов, число фото) читаются по разу.
    """
    def reads_for(patients):
        from app.draft.integration import AppDrafts, ServiceAdapter, build_app_schema, make_parent_resolver
        from app.utils.drafts import DraftStore
        adapter = ServiceAdapter({'patient': (providers['patient'], PatientDTO),
                                  'appointment': (providers['appointment'], AppointmentDTO),
                                  'photo': (providers['photo'], PhotoDTO)},
                                 transaction_factory=lambda: services['db'].session_scope())
        schema = build_app_schema()
        drafts = AppDrafts(schema, adapter, DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter)))
        clinic = create_clinic_datasets(services=providers, drafts=drafts)
        clinic.open()
        for i in range(patients):
            clinic.patients.append({'last_name': f'Ф{patients}_{i}', 'first_name': 'И',
                                    'birth_date': datetime.date(2000, 1, 1)})
            clinic.patients.post()
            for j in range(2):
                clinic.appointments.append({'date': datetime.date(2026, 1, j + 1)})
                clinic.appointments.post()
        calls = []
        original = ServiceBackend.fetch
        monkeypatch.setattr(ServiceBackend, 'fetch', lambda self, q: (calls.append(1), original(self, q))[1])
        clinic.save()
        monkeypatch.setattr(ServiceBackend, 'fetch', original)
        assert all(k > 0 for k in keys(clinic.patients))
        clinic.close()
        return len(calls)

    one, five = reads_for(1), reads_for(5)
    assert one == five and five <= 8, (one, five)


def test_mark_follows_new_record_after_drafts_save(services, providers, filled, app_drafts):
    """Отметка новой записи (временный id) после сохранения черновиков — у той же записи (настоящий id)."""
    from app.utils.dataset import DataSet, FieldDef, FieldKind
    fields = fields_from_config(PATIENT_CONFIG, PatientDTO)
    backend = ServiceBackend(providers['patient'], PatientDTO, fields)
    writer = DraftsWriter(app_drafts.store, 'patient')
    ds = writer.attach(DataSet(backend, writer=writer, name='patients',
                               fields=fields + [FieldDef('mark', kind=FieldKind.BOOLEAN, local=True, default=False)]))
    ds.open()
    ds.append({'last_name': 'Отмеченный', 'first_name': 'О', 'birth_date': datetime.date(2000, 1, 1)})
    ds.post()
    ds.set_local('mark', True)
    app_drafts.save()
    real = next(p.id for p in services['patient'].get_all() if p.last_name == 'Отмеченный')
    assert ds.local_keys('mark') == [real]
    assert ds.locate(real) and ds.value('mark') is True


def test_program_side_photo_count_with_drafts(services, providers, filled, app_drafts, tmp_path):
    """Число фото у приёма считает программа: черновик фото виден сразу, отмена/повтор — тоже, после сохранения — верно."""
    from app.utils.dataset import AggregateDef, DataSet, FieldDef, MasterDetailLink
    image = tmp_path / 'x.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\n')
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    fields = fields_from_config(APPOINTMENT_CONFIG, AppointmentDTO)
    writer = DraftsWriter(app_drafts.store, 'appointment')
    visits = writer.attach(DataSet(
        ServiceBackend(providers['appointment'], AppointmentDTO, fields), writer=writer, name='appointments',
        fields=fields + [FieldDef('photo_count', 'Фото', aggregate=AggregateDef(clinic.photos, 'appointment_id'))]))
    MasterDetailLink(visits, clinic.photos)
    visits.open(); clinic.photos.open()
    assert [visits.value('photo_count', i) for i in range(visits.row_count)] == [0, 0, 0]
    clinic.photos.append({'file_path': str(image)}); clinic.photos.post()
    assert visits.value('photo_count') == 1                            # черновик фото — уже в числе
    assert services['photo'].get_by_parent(visits.current_key) == []
    app_drafts.store.undo()
    assert visits.value('photo_count') == 0
    app_drafts.store.redo()
    assert visits.value('photo_count') == 1
    app_drafts.save()
    assert len(services['photo'].get_by_parent(visits.current_key)) == 1
    assert visits.value('photo_count') == 1


def test_children_of_deleted_parent_shown_but_editable(services, providers, filled, app_drafts, tmp_path):
    """Дети записи, помеченной на удаление: показываются как удаляемые, но правка разрешена (метку могут снять)."""
    image = tmp_path / 'a.png'; image.write_bytes(b'x')
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    clinic.photos.append({'file_path': str(image)}); clinic.photos.post()
    clinic.appointments.delete()
    assert clinic.photos.row_status(0) == 'parent_deleted'
    clinic.photos.set_value('description', 'правка разрешена'); clinic.photos.post()
    clinic.photos.append({'file_path': str(image)}); clinic.photos.post()
    clinic.writers['appointments'].undelete(clinic.appointments)
    assert {clinic.photos.row_status(i) for i in range(clinic.photos.row_count)} == {'new'}
    clinic.close()


def test_moved_child_survives_deleting_old_parent(services, providers, filled, app_drafts):
    """Приём перенесли к другому пациенту, старого пациента удалили — приём уцелел (перенос пишется раньше удаления)."""
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    moved = clinic.appointments.current_key                       # приём Иванова
    other = keys(clinic.appointments)[1]
    writer = clinic.writers['appointments']
    row = clinic.appointments.row()
    writer.update(clinic.appointments, moved, {'patient_id': filled['petrov']},
                  dict(row, patient_id=filled['petrov']), row)
    clinic.patients.delete()                                      # Иванов — на удаление
    clinic.save(confirm_deletes=lambda plan: True)
    assert services['appointment'].get_by_id(moved).patient_id == filled['petrov']
    with pytest.raises(Exception, match='не найден'):
        services['appointment'].get_by_id(other)                 # оставшийся — удалён с пациентом
    clinic.close()
