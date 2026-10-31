# tests/test_dataset_app/test_notes_links.py

"""
Заметки как ссылки в реестре таблиц и черновиках (2026-10-31) — на настоящей SQLite во
временной папке.

Заметки (``appointments_notes``) — общие данные: одну заметку используют многие записи
(пациенты, приёмы). Черновики знают об этом: удалить заметку, на которую ссылаются
(записи БД или несохранённые черновики), нельзя — отказ с откатом всего сохранения;
заметка, которая больше ни на что не завязана, удаляется. Ставшие ненужными заметки при
удалении и правке записей убирает сервис (``NoteService.cleanup_unused_note``), общая
заметка при этом остаётся у остальных записей.
"""

import datetime

import pytest

from app.draft.integration import AppDrafts, make_parent_resolver
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.tables import CLINIC, SpecError, TableRegistry, TableSpec
from app.utils.drafts import DeleteBlocked, DraftStore, SaveScope

NOTES = 'appointments_notes'


def drafts_for(services, providers):
    """Черновики по реестру клиники с сервисами теста (как ``create_app_drafts``)."""
    schema = CLINIC.drafts_schema()
    adapter = CLINIC.service_adapter(
        transaction_factory   =   lambda: services['db'].session_scope(),   # одна транзакция
        services              =   providers,                                # сервисы теста
    )
    store = DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter))
    return AppDrafts(schema, adapter, store)


def note_texts(services):
    """Тексты всех заметок в БД (по алфавиту)."""
    return sorted(n.text for n in services['note'].get_all())


@pytest.fixture
def shared(services):
    """Одна заметка «боль» у двух приёмов и описания пациента; второй пациент без заметок."""
    p, a = services['patient'], services['appointment']
    ivanov = p.create(PatientDTO(last_name='Иванов', first_name='Иван', description_text='боль'))
    first = a.create(AppointmentDTO(patient_id=ivanov.id, date=datetime.date(2026, 1, 10), reason_text='боль'))
    second = a.create(AppointmentDTO(patient_id=ivanov.id, date=datetime.date(2026, 2, 10), reason_text='боль',
                                     note_text='своя'))
    note_id = services['note'].get_or_create_note('боль').id
    assert first.reason_id == second.reason_id == note_id                 # заметка переиспользуется
    return {'patient': ivanov.id, 'first': first.id, 'second': second.id, 'note': note_id}


def test_notes_are_shared_data_in_registry():
    assert CLINIC.names() == ['patients', 'appointments', 'photos']         # дерево — как было
    assert CLINIC.shared_names() == [NOTES] and CLINIC.parent(NOTES) is None
    assert [(l.field, l.table, l.on_delete, l.collect) for l in CLINIC.links('patients')] == [
        ('description_id', NOTES, 'restrict', False), ('comment_id', NOTES, 'restrict', False)]
    assert {l.field for l in CLINIC.links('appointments')} == {
        'reason_id', 'procedure_id', 'recommendations_id', 'note_id', 'cost_procedure_id'}
    assert CLINIC.parent('appointments') == 'patients'                     # заметка — не родитель
    schema = CLINIC.drafts_schema()
    assert schema.names() == ['patient', 'appointment', 'photo', 'note']
    assert {t for t, _ in schema.referrers('note')} == {'patient', 'appointment'}
    assert CLINIC.service_adapter().entities() == ['patient', 'appointment', 'photo', 'note']


def test_shared_table_cannot_be_parent_or_have_parent():
    base = [CLINIC.get(n) for n in CLINIC.names()]
    notes = CLINIC.get(NOTES)
    with pytest.raises(SpecError, match='общие данные'):
        TableRegistry(base + [TableSpec(**{**notes.__dict__, 'parent': 'patients'})])
    photos = TableSpec(**{**base[2].__dict__, 'parent': NOTES, 'parent_field': 'appointment_id'})
    with pytest.raises(SpecError, match='общие данные'):
        TableRegistry(base[:2] + [photos, notes])


def test_build_has_no_notes_dataset(services, providers, shared):
    built = CLINIC.build(services=providers)
    built.open()
    assert [d.name for d in built.datasets] == ['patients', 'appointments', 'photos']
    assert built.patients.fields['description_id'].extra['link'].table == NOTES
    built.patients.locate(shared['patient'])
    assert built.patients.value('description_text') == 'боль'              # текст — поле записи
    built.close()


def test_delete_shared_note_rejected_with_rollback(services, providers, shared):
    drafts = drafts_for(services, providers)
    drafts.store.modify('patient', shared['patient'], {'phone': '+7 1'}, original={'phone': None})
    drafts.store.delete('note', shared['note'])
    with pytest.raises(DeleteBlocked, match=r'Нельзя удалить «Заметка #\d+»: на неё ссылаются записи: .*Пациент'):
        drafts.save()
    assert 'боль' in note_texts(services)                                   # заметка на месте
    assert services['patient'].get_by_id(shared['patient']).phone is None   # откат ВСЕГО
    assert not drafts.store.is_empty                                        # черновики целы


def test_delete_note_used_by_unsaved_draft_rejected_before_db(services, providers):
    free = services['note'].create_note('ничья')
    drafts = drafts_for(services, providers)
    patient = drafts.store.create('patient', {'last_name': 'Сидоров', 'first_name': 'Пётр',
                                              'description_id': free.id})
    drafts.store.delete('note', free.id)
    with pytest.raises(DeleteBlocked, match='несохранённые изменения: «Пациент #-1»'):
        drafts.save([('note', free.id)], SaveScope.SELF)                  # только заметку
    assert note_texts(services) == ['ничья'] and patient == -1
    with pytest.raises(DeleteBlocked, match='на неё ссылаются записи: «Пациент #1»'):
        drafts.save()                                                   # всё: пациент записан раньше
    assert note_texts(services) == ['ничья'] and services['patient'].get_page(0, 10)[1] == 0


def test_delete_unused_note_allowed(services, providers):
    free = services['note'].create_note('ничья')
    drafts = drafts_for(services, providers)
    drafts.store.delete('note', free.id)
    result = drafts.save()
    assert result.deleted == (('note', free.id),) and note_texts(services) == []


def test_delete_note_freed_in_same_save(services, providers):
    """Запись сменила текст, прежняя заметка помечена на удаление — сохраняется без отказа."""
    patient = services['patient'].create(PatientDTO(last_name='Иванов', first_name='Иван',
                                                    description_text='старое'))
    old_note = services['patient'].get_by_id(patient.id).description_id
    drafts = drafts_for(services, providers)
    drafts.store.modify('patient', patient.id, {'description_text': 'новое'},
                        original={'description_text': 'старое'})
    drafts.store.delete('note', old_note)
    drafts.save()                                                       # было: «не найдена», откат
    assert note_texts(services) == ['новое'] and drafts.store.is_empty


def test_deleting_records_keeps_shared_note_and_drops_unused(services, providers, shared):
    """Удаление записей через черновики: общая заметка остаётся, пока на неё ссылаются."""
    drafts = drafts_for(services, providers)
    built = CLINIC.build(services=providers, drafts=drafts)
    built.open()
    built.patients.locate(shared['patient'])
    built.appointments.locate(shared['second'])
    built.appointments.delete()
    built.save()
    assert note_texts(services) == ['боль']                                 # «своя» — никому не нужна
    built.appointments.locate(shared['first'])
    built.appointments.delete()
    built.save()
    assert note_texts(services) == ['боль']                                 # у пациента — описание
    built.patients.delete()
    built.save()
    assert note_texts(services) == [] and drafts.store.is_empty
    built.close()
