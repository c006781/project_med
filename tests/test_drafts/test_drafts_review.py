# tests/test_drafts/test_drafts_review.py

"""
Ядро черновиков ``app.utils.drafts`` — находки сверки модуля (М4, 2026-10-25): DR1–DR3, DR7.

Каждый тест падает на коде до исправления (журнал — ``app/utils/drafts/IMPLEMENTATION.md``).
"""

import pytest

from app.utils.drafts import (
    DraftStore, EntityType, PlanError, Reference, SaveScope, TreeSchema, build_plan,
    execute_plan,
)

from .conftest import MemoryAdapter


# ---------------------------------------------------------------------------
# DR1: нужная новая запись помечена на удаление — не должна попасть в «создать»
# ---------------------------------------------------------------------------

def _schema_ref_of_ref() -> TreeSchema:
    """Приём → врач → шаблон: ссылки второго уровня (не владение)."""
    return TreeSchema([
        EntityType('template', label='Шаблон'),
        EntityType('doctor', label='Врач', references=[Reference('template_id', 'template')]),
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём',
                   references=[Reference('doctor_id', 'doctor')]),
    ])


def _schema_parent_of_ref() -> TreeSchema:
    """Приём → врач (ссылка); врач — ребёнок клиники (владение)."""
    return TreeSchema([
        EntityType('clinic', label='Клиника'),
        EntityType('doctor', parent='clinic', parent_field='clinic_id', label='Врач'),
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём',
                   references=[Reference('doctor_id', 'doctor')]),
    ])


def test_dr1_deleted_new_target_of_required_record_is_never_created():
    """Новый врач (нужен приёму) ссылается на новый шаблон, помеченный на удаление."""
    store = DraftStore(_schema_ref_of_ref())
    template = store.create('template', {'text': 'т'})
    doctor = store.create('doctor', {'template_id': template})
    store.modify('appointment', 12, {'doctor_id': doctor}, original={'doctor_id': None}, parent_id=1)
    store.delete('template', template)
    with pytest.raises(PlanError):
        build_plan(store, [('appointment', 12)], SaveScope.SELF, include_new_ancestors=True)
    with pytest.raises(PlanError):
        build_plan(store, [('appointment', 12)], SaveScope.SELF)


def test_dr1_required_record_under_deleted_new_parent_is_refused():
    """Новый врач (нужен приёму) — ребёнок новой клиники, помеченной на удаление."""
    store = DraftStore(_schema_parent_of_ref())
    clinic = store.create('clinic', {'name': 'К'})
    doctor = store.create('doctor', {'name': 'В'}, parent_id=clinic)
    store.modify('appointment', 12, {'doctor_id': doctor}, original={'doctor_id': None}, parent_id=1)
    store.delete('clinic', clinic)
    with pytest.raises(PlanError, match='Врач'):
        build_plan(store, [('appointment', 12)], SaveScope.SELF, include_new_ancestors=True)


def test_dr1_whole_store_save_still_works_with_deleted_new_branch():
    """Сохранение «всего» без ссылок на удаляемое: новая клиника, помеченная на удаление,
    поглощается вместе с новым врачом (проверка DR1 не мешает обычному случаю)."""
    store, adapter = DraftStore(_schema_parent_of_ref()), MemoryAdapter()
    clinic = store.create('clinic', {'name': 'К'})
    store.create('doctor', {'name': 'В'}, parent_id=clinic)
    store.delete('clinic', clinic)
    result = execute_plan(store, build_plan(store), adapter)
    assert adapter.rows == {} and store.is_empty and len(result.dropped) == 2


# ---------------------------------------------------------------------------
# DR2: «сведения о родителе» в modify/delete не затирают перенос, сделанный черновиком
# ---------------------------------------------------------------------------

def test_dr2_modify_with_stale_parent_keeps_moved_record_under_new_parent(store):
    store.modify('photo', 7, {'appointment_id': 13}, original={'appointment_id': 12}, parent_id=12)
    # таблица старого приёма передаёт родителя из строки БД (12) при правке другого поля
    store.modify('photo', 7, {'note': 'x'}, original={'note': None}, parent_id=12)
    assert store.parent_of('photo', 7) == ('appointment', 13)
    assert store.status('appointment', 13) == 'child'
    assert store.status('appointment', 12) is None


def test_dr2_delete_with_stale_parent_keeps_moved_record_under_new_parent(store, adapter):
    store.modify('photo', 7, {'appointment_id': 13}, original={'appointment_id': 12}, parent_id=12)
    store.delete('photo', 7, parent_id=12)
    assert store.parent_of('photo', 7) == ('appointment', 13)


def test_dr2_moved_record_survives_deleting_old_parent_after_stale_edit(store, adapter):
    """Как L1, но через modify: удаление старого родителя не уносит перенесённую запись."""
    adapter.rows[('appointment', 12)] = {'patient_id': 1}
    adapter.rows[('appointment', 13)] = {'patient_id': 1}
    adapter.rows[('photo', 7)] = {'appointment_id': 12}
    store.modify('photo', 7, {'appointment_id': 13}, original={'appointment_id': 12}, parent_id=12)
    store.modify('photo', 7, {'note': 'x'}, original={'note': None}, parent_id=12)
    store.delete('appointment', 12, parent_id=1)
    plan = build_plan(store)
    assert ('photo', 7) in {d.key for d in plan.updates}
    assert ('photo', 7) not in {d.key for d in plan.dropped}


def test_dr2_parent_info_still_applies_without_moved_fk(store):
    """Без переноса в черновике сведения о родителе по-прежнему запоминаются."""
    store.modify('photo', 7, {'note': 'x'}, parent_id=12)
    assert store.parent_of('photo', 7) == ('appointment', 12)
    store.delete('photo', 8, parent_id=12)
    assert store.parent_of('photo', 8) == ('appointment', 12)


# ---------------------------------------------------------------------------
# DR3: после сохранения не остаётся связей с новыми записями, которые не создавались
# ---------------------------------------------------------------------------

def test_dr3_dropped_new_records_forget_their_links(store, adapter):
    appointment = store.create('appointment', {'date': 'd'}, parent_id=1)
    photo = store.create('photo', {'path': 'a'}, parent_id=appointment)
    store.delete('appointment', appointment)
    result = execute_plan(store, build_plan(store), adapter)
    assert set(result.dropped) == {('appointment', appointment), ('photo', photo)}
    assert store.children(('patient', 1)) == set()
    assert store.descendants(('patient', 1)) == set()
    assert store.parent_of('appointment', appointment) is None


def test_dr3_created_records_keep_links_after_save(store, adapter):
    appointment = store.create('appointment', {'date': 'd'}, parent_id=1)
    result = execute_plan(store, build_plan(store), adapter)
    real = result.id_map[('appointment', appointment)]
    assert store.children(('patient', 1)) == {('appointment', real)}


# ---------------------------------------------------------------------------
# DR7: «переиспользуемые данные» описаны, а адаптер не умеет читать запись — отказ
# ---------------------------------------------------------------------------

class _NoReadAdapter(MemoryAdapter):
    """Адаптер без ``read``: найти, что удалять следом (``collect``), нельзя."""

    def __getattribute__(self, name: str):
        if name == 'read':
            raise AttributeError(name)
        return super().__getattribute__(name)


def test_dr7_collect_without_read_is_refused_and_rolled_back():
    schema = TreeSchema([
        EntityType('template', label='Шаблон'),
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём',
                   references=[Reference('template_id', 'template', collect=True)]),
    ])
    store, adapter = DraftStore(schema), _NoReadAdapter()
    assert not hasattr(adapter, 'read')
    adapter.rows[('template', 5)] = {'text': 'т'}
    adapter.rows[('appointment', 12)] = {'patient_id': 1, 'template_id': 5}
    store.delete('appointment', 12, parent_id=1)
    with pytest.raises(PlanError, match='read'):
        execute_plan(store, build_plan(store), adapter)
    assert ('appointment', 12) in adapter.rows and ('template', 5) in adapter.rows   # откат
    assert store.get('appointment', 12).deleted                                       # черновик на месте


def test_dr7_adapter_with_read_collects_as_before():
    schema = TreeSchema([
        EntityType('template', label='Шаблон'),
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём',
                   references=[Reference('template_id', 'template', collect=True)]),
    ])
    store, adapter = DraftStore(schema), MemoryAdapter()
    adapter.rows[('template', 5)] = {'text': 'т'}
    adapter.rows[('appointment', 12)] = {'patient_id': 1, 'template_id': 5}
    store.delete('appointment', 12, parent_id=1)
    result = execute_plan(store, build_plan(store), adapter)
    assert set(result.deleted) == {('appointment', 12), ('template', 5)}
