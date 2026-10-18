# tests/test_drafts/test_references.py

"""
Черновики: ссылки (не владение) — порядок записи, замена временных id, правила удаления
(запрет / обнуление / каскад), «переиспользуемые данные» (удаляются, когда никому не нужны).
"""

import pytest

from app.utils.drafts import (
    DeleteBlocked, DraftStore, EntityType, PlanError, Reference, SaveScope, SchemaError, TreeSchema,
    build_plan, execute_plan,
)

from .conftest import MemoryAdapter


def make(on_delete='restrict'):
    """Пациент → приём; приём ссылается на врача (правило on_delete) и на шаблон (переиспользуемый)."""
    return TreeSchema([
        EntityType('doctor', label='Врач'),
        EntityType('template', label='Шаблон'),
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём', references=[
            Reference('doctor_id', 'doctor', on_delete=on_delete),
            Reference('template_id', 'template', collect=True),
        ]),
    ])


def save(store, adapter, targets=None, scope=SaveScope.BRANCH, include=False):
    return execute_plan(store, build_plan(store, targets, scope, include_new_ancestors=include), adapter)


def test_schema_validation():
    with pytest.raises(SchemaError, match='неописанный'):
        TreeSchema([EntityType('a', references=[Reference('b_id', 'b')])])
    with pytest.raises(SchemaError, match='связь'):
        TreeSchema([EntityType('p'), EntityType('c', parent='p', parent_field='p_id',
                                                references=[Reference('p_id', 'p')])])
    with pytest.raises(SchemaError, match='правило'):
        Reference('x', 'y', on_delete='drop')
    schema = make()
    assert [t for t, _ in schema.referrers('doctor')] == ['appointment']
    assert schema.references('appointment')[1].collect


def test_new_target_created_first_and_id_mapped():
    store, adapter = DraftStore(make()), MemoryAdapter()
    patient = store.create('patient', {'name': 'П'})
    appointment = store.create('appointment', {'date': 'x'}, parent_id=patient)
    doctor = store.create('doctor', {'name': 'Врач'})                     # создан ПОСЛЕ приёма
    store.modify('appointment', appointment, {'doctor_id': doctor})
    result = save(store, adapter)
    order = [e for op, e, _ in adapter.log if op == 'create']
    assert order.index('doctor') < order.index('appointment')
    real_appointment = result.id_map[('appointment', appointment)]
    assert adapter.rows[('appointment', real_appointment)]['doctor_id'] == result.id_map[('doctor', doctor)]


def test_new_target_outside_scope_is_required():
    store, adapter = DraftStore(make()), MemoryAdapter()
    adapter.rows[('patient', 1)] = {'name': 'П'}
    doctor = store.create('doctor', {'name': 'Врач'})
    appointment = store.create('appointment', {'doctor_id': doctor}, parent_id=1)
    plan = build_plan(store, [('appointment', appointment)], SaveScope.SELF)
    assert plan.missing_new_ancestors == (('doctor', doctor),)            # спросить «и врача?»
    save(store, adapter, [('appointment', appointment)], SaveScope.SELF, include=True)
    assert store.is_empty


def test_unsaved_reference_remapped_after_target_saved():
    store, adapter = DraftStore(make()), MemoryAdapter()
    adapter.rows[('patient', 1)] = {'name': 'П'}
    doctor = store.create('doctor', {'name': 'Врач'})
    appointment = store.create('appointment', {'doctor_id': doctor}, parent_id=1)
    result = save(store, adapter, [('doctor', doctor)], SaveScope.SELF)  # только врача
    real = result.id_map[('doctor', doctor)]
    assert store.get('appointment', appointment).data['doctor_id'] == real


def db_with_doctor(on_delete):
    store, adapter = DraftStore(make(on_delete)), MemoryAdapter()
    adapter.rows.update({('doctor', 5): {'name': 'Врач'}, ('patient', 1): {'name': 'П'},
                         ('appointment', 12): {'patient_id': 1, 'doctor_id': 5}})
    return store, adapter


def test_restrict_blocks_and_rolls_back():
    store, adapter = db_with_doctor('restrict')
    store.modify('patient', 1, {'name': 'Новое'}, original={'name': 'П'})
    store.delete('doctor', 5)
    with pytest.raises(DeleteBlocked) as info:
        save(store, adapter)
    assert info.value.referrers == [('appointment', 12)]
    assert str(info.value) == 'Нельзя удалить «Врач #5»: на неё ссылаются записи: «Приём #12»'
    assert ('doctor', 5) in adapter.rows and adapter.rows[('patient', 1)]['name'] == 'П'   # откат всего
    assert not store.is_empty


def test_restrict_passes_when_reference_removed_in_same_save():
    """Ссылку на врача сняли в той же правке — удаление разрешено (правки пишутся раньше удаления)."""
    store, adapter = db_with_doctor('restrict')
    store.modify('appointment', 12, {'doctor_id': None}, original={'doctor_id': 5}, parent_id=1)
    store.delete('doctor', 5)
    save(store, adapter)
    assert ('doctor', 5) not in adapter.rows and adapter.rows[('appointment', 12)]['doctor_id'] is None


def test_set_null_and_cascade():
    store, adapter = db_with_doctor('set_null')
    store.delete('doctor', 5)
    save(store, adapter)
    assert adapter.rows[('appointment', 12)]['doctor_id'] is None
    store, adapter = db_with_doctor('cascade')
    store.delete('doctor', 5)
    result = save(store, adapter)
    assert ('appointment', 12) not in adapter.rows
    assert result.deleted == (('appointment', 12), ('doctor', 5))      # ссылающиеся — раньше цели


def test_unsaved_draft_referencing_deleted_blocks_before_db():
    store, adapter = db_with_doctor('set_null')
    store.create('appointment', {'doctor_id': 5}, parent_id=1)          # новый, не сохраняется
    store.delete('doctor', 5)
    with pytest.raises(DeleteBlocked, match='несохранённые'):
        save(store, adapter, [('doctor', 5)], SaveScope.SELF)
    assert adapter.log == []                                            # до БД не дошло


def test_collect_deletes_unused_shared_data_recursively():
    store, adapter = DraftStore(make()), MemoryAdapter()
    adapter.rows.update({('patient', 1): {}, ('template', 7): {'text': 'общий'},
                         ('appointment', 11): {'patient_id': 1, 'template_id': 7},
                         ('appointment', 12): {'patient_id': 1, 'template_id': 7}})
    store.delete('appointment', 11)
    save(store, adapter)
    assert ('template', 7) in adapter.rows                               # ещё нужен приёму 12
    store.delete('appointment', 12)
    result = save(store, adapter)
    assert ('template', 7) not in adapter.rows and ('template', 7) in result.deleted


def test_cycle_of_new_records_refused():
    schema = TreeSchema([
        EntityType('a', references=[Reference('b_id', 'b')]),
        EntityType('b', references=[Reference('a_id', 'a')]),
    ])
    store = DraftStore(schema)
    a = store.create('a', {})
    b = store.create('b', {'a_id': a})
    store.modify('a', a, {'b_id': b})
    with pytest.raises(PlanError, match='по кругу'):
        build_plan(store)


class PlainAdapter:
    """Адаптер без поиска ссылок (как до 2026-10-18)."""

    def __init__(self, inner: MemoryAdapter) -> None:
        self.inner = inner

    def transaction(self):
        return self.inner.transaction()

    def create(self, entity, data, tx):
        return self.inner.create(entity, data, tx)

    def update(self, entity, entity_id, changes, tx):
        return self.inner.update(entity, entity_id, changes, tx)

    def delete(self, entity, entity_id, tx):
        return self.inner.delete(entity, entity_id, tx)


def test_adapter_without_reference_lookup_refused():
    """Ссылки описаны, а адаптер искать их не умеет — отказ (а не тихое удаление без проверки)."""
    store, adapter = db_with_doctor('restrict')
    store.delete('doctor', 5)
    with pytest.raises(PlanError, match='не умеет'):
        execute_plan(store, build_plan(store), PlainAdapter(adapter))
    assert ('doctor', 5) in adapter.rows


def test_schema_without_references_works_with_plain_adapter():
    """Схема без ссылок — старые адаптеры работают как раньше."""
    schema = TreeSchema([EntityType('patient'), EntityType('appointment', parent='patient',
                                                           parent_field='patient_id')])
    store, adapter = DraftStore(schema), MemoryAdapter()
    adapter.rows[('patient', 1)] = {}
    store.delete('patient', 1)
    execute_plan(store, build_plan(store), PlainAdapter(adapter))
    assert ('patient', 1) not in adapter.rows
