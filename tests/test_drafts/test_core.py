# tests/test_drafts/test_core.py

"""
Ядро черновиков ``app.utils.drafts``: схема, хранилище, объём, план, исполнение.

Номера требований — app/draft/IMPLEMENTATION.md §2; старые проблемы D1–D11 — §3.
"""

import ast
import os
import subprocess
import sys

import pytest

from app.utils.drafts import (
    DraftStore, EntityType, PlanError, RejectChildChangesPolicy, SaveScope, SchemaError,
    StalePlanError, TreeSchema, build_plan, execute_plan,
)

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'app', 'utils', 'drafts')


# ---------------------------------------------------------------------------
# Схема
# ---------------------------------------------------------------------------

def test_schema_depth_and_children(schema):
    assert schema.depth('patient') == 0 and schema.depth('photo') == 2
    assert schema.children_types('patient') == ['appointment']
    assert schema.parent_field('photo') == 'appointment_id'


@pytest.mark.parametrize('types, message', [
    ([EntityType('b', 'a', 'a_id')], "родитель 'a' не описан"),
    ([EntityType('a'), EntityType('b', 'a')], 'parent_field'),
    ([EntityType('a', 'b', 'b_id'), EntityType('b', 'a', 'a_id')], 'цикл'),
    ([EntityType('a'), EntityType('a')], 'уже описан'),
])
def test_schema_validation(types, message):
    with pytest.raises(SchemaError, match=message):
        TreeSchema(types)


def test_schema_dynamic_add_rolls_back_on_error(schema):
    """Типы добавляются во время работы (треб. 1); ошибочный не остаётся в схеме."""
    schema.add(EntityType('note', parent='appointment', parent_field='appointment_id'))
    assert schema.depth('note') == 2
    with pytest.raises(SchemaError):
        schema.add(EntityType('bad', parent='nope', parent_field='x'))
    assert 'bad' not in schema


def test_unknown_type_rejected(store):
    with pytest.raises(SchemaError):
        store.modify('nope', 1, {'a': 1})


# ---------------------------------------------------------------------------
# Хранилище: создание, изменение, повторное изменение
# ---------------------------------------------------------------------------

def test_create_requires_parent(store):
    with pytest.raises(ValueError, match='родитель'):
        store.create('photo', {'path': 'a'})


def test_create_sets_fk_and_temp_ids(store):
    a = store.create('appointment', {'date': 'd'}, parent_id=1)
    p = store.create('photo', {'path': 'x'}, parent_id=a)
    assert (a, p) == (-1, -2)
    assert store.get('photo', p).data == {'path': 'x', 'appointment_id': -1}
    assert store.parent_of('photo', p) == ('appointment', -1)


def test_create_parent_from_fk_in_data(store):
    p = store.create('photo', {'appointment_id': 12})
    assert store.get('photo', p).parent_id == 12


def test_optional_parent_allowed():
    schema = TreeSchema([EntityType('a'), EntityType('b', 'a', 'a_id', parent_required=False)])
    store = DraftStore(schema)
    assert store.create('b', {}) == -1


def test_modify_twice_merges(store):
    """Треб. 3: повторное изменение дополняет черновик."""
    store.modify('appointment', 12, {'cost': 500}, original={'cost': 400, 'note': ''}, parent_id=1)
    store.modify('appointment', 12, {'note': 'x'}, original={'cost': 400, 'note': ''})
    store.modify('appointment', 12, {'cost': 600})
    draft = store.get('appointment', 12)
    assert draft.data == {'cost': 600, 'note': 'x'}
    assert draft.original == {'cost': 400, 'note': ''}


def test_modify_back_to_original_drops_field_and_draft(store, events):
    store.modify('appointment', 12, {'cost': 500}, original={'cost': 400}, parent_id=1)
    store.modify('appointment', 12, {'cost': 400})
    assert not store.has_draft('appointment', 12)
    assert [e.kind for e in events] == ['modified', 'discarded']


def test_modify_new_record_updates_data(store):
    p = store.create('photo', {'path': 'a'}, parent_id=12)
    store.modify('photo', p, {'path': 'b'})
    assert store.get('photo', p).data['path'] == 'b' and store.get('photo', p).is_new


def test_reparent_by_fk_change(store, events):
    """Перенос фото в другой приём: связи и значки обоих родителей обновляются."""
    store.remember_parent('appointment', 12, 1)
    store.remember_parent('appointment', 13, 1)
    store.modify('photo', 3, {'appointment_id': 13}, original={'appointment_id': 12}, parent_id=12)
    assert store.parent_of('photo', 3) == ('appointment', 13)
    assert store.status('appointment', 12) is None
    assert store.status('appointment', 13) == 'child'
    assert events[-1].kind == 'reparented'
    assert ('appointment', 12) in events[-1].affected


def test_snapshots_are_copies(store):
    store.modify('photo', 3, {'a': 1}, parent_id=12)
    draft = store.get('photo', 3)
    with pytest.raises(Exception):
        draft.id = 4                        # frozen
    dict(draft.data)['a'] = 2
    assert store.get('photo', 3).data == {'a': 1}


# ---------------------------------------------------------------------------
# Статусы (вычисляются — D4, D5, D6, D11 старой системы)
# ---------------------------------------------------------------------------

def test_status_three_levels(store):
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert store.status('photo', 7) == 'own'
    assert store.status('appointment', 12) == 'child'
    assert store.status('patient', 1) == 'child'
    store.modify('patient', 1, {'name': 'X'})
    assert store.status('patient', 1) == 'both'


def test_status_cleared_when_child_discarded(store):
    """D11: после отмены изменения ребёнка значок родителя гаснет."""
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.modify('photo', 8, {'a': 1}, parent_id=12)
    store.discard([('photo', 7)])
    assert store.status('appointment', 12) == 'child'
    store.discard([('photo', 8)])
    assert store.status('appointment', 12) is None and store.status('patient', 1) is None


def test_same_id_different_types_independent(store):
    """D5: приём 5 и фото 5 — разные узлы."""
    store.modify('appointment', 5, {'a': 1}, parent_id=1)
    store.modify('photo', 5, {'a': 1}, parent_id=9)
    assert store.status('photo', 5) == 'own'
    assert store.status('appointment', 9) == 'child'
    assert store.status('appointment', 5) == 'own'


def test_parent_resolver_used_and_cached(schema):
    calls = []

    def resolver(entity, entity_id):
        calls.append((entity, entity_id))
        return {('appointment', 12): 1}.get((entity, entity_id))

    store = DraftStore(schema, parent_resolver=resolver)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert store.status('patient', 1) == 'child'
    store.status('patient', 1)
    assert calls.count(('appointment', 12)) == 1


def test_resolver_failure_does_not_break(schema):
    def resolver(entity, entity_id):
        raise RuntimeError('db down')

    store = DraftStore(schema, parent_resolver=resolver)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert store.status('appointment', 12) == 'child'


def test_events_affect_node_and_ancestors(store, events):
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert events[-1].affected == (('photo', 7), ('appointment', 12), ('patient', 1))


def test_batch_defers_events(store, events):
    with store.batch():
        store.modify('photo', 7, {'a': 1}, parent_id=12)
        store.modify('photo', 8, {'a': 1}, parent_id=12)
        assert events == []
    assert [e.node for e in events] == [('photo', 7), ('photo', 8)]


def test_failing_listener_isolated(store):
    got = []
    store.subscribe(lambda e: 1 / 0)
    store.subscribe(got.append)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert len(got) == 1


# ---------------------------------------------------------------------------
# Удаление и отмена
# ---------------------------------------------------------------------------

def test_delete_keeps_changes_and_undelete_restores(store):
    store.modify('appointment', 12, {'cost': 1}, parent_id=1)
    store.delete('appointment', 12)
    assert store.get('appointment', 12).deleted
    store.undelete('appointment', 12)
    assert store.get('appointment', 12).data == {'cost': 1}
    store.delete('appointment', 13, parent_id=1)
    store.undelete('appointment', 13)
    assert not store.has_draft('appointment', 13)


def test_discard_new_parent_discards_new_children(store):
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    store.discard([('appointment', a)], SaveScope.SELF)
    assert not store.has_draft('photo', p)
    assert store.is_empty


@pytest.mark.parametrize('scope, expected', [
    (SaveScope.SELF, {('appointment', 12)}),
    (SaveScope.DESCENDANTS, {('photo', 7)}),
    (SaveScope.ANCESTORS, {('patient', 1)}),
    (SaveScope.BRANCH, {('appointment', 12), ('photo', 7)}),
    (SaveScope.PATH, {('patient', 1), ('appointment', 12)}),
    (SaveScope.FULL, {('patient', 1), ('appointment', 12), ('photo', 7)}),
])
def test_discard_by_scope(store, scope, expected):
    store.modify('patient', 1, {'n': 1})
    store.modify('appointment', 12, {'c': 1}, parent_id=1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.modify('appointment', 13, {'c': 1}, parent_id=1)      # соседняя ветка не трогается
    assert store.discard([('appointment', 12)], scope) == expected
    assert store.has_draft('appointment', 13)


# ---------------------------------------------------------------------------
# План
# ---------------------------------------------------------------------------

@pytest.fixture
def tree(store):
    """пациент 1 (изменён) → приём 12 (изменён) → фото 7 (изменено), новое фото;
    соседний приём 13 (изменён)."""
    store.modify('patient', 1, {'name': 'N'})
    store.modify('appointment', 12, {'cost': 5}, parent_id=1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    new_photo = store.create('photo', {'path': 'p'}, parent_id=12)
    store.modify('appointment', 13, {'cost': 6}, parent_id=1)
    return store, new_photo


def keys(drafts):
    return {d.key for d in drafts}


def test_plan_all(tree):
    store, new_photo = tree
    plan = build_plan(store)
    assert keys(plan.creates) == {('photo', new_photo)}
    assert keys(plan.updates) == {('patient', 1), ('appointment', 12), ('photo', 7), ('appointment', 13)}


@pytest.mark.parametrize('scope, expected', [
    (SaveScope.SELF, {('appointment', 12)}),
    (SaveScope.BRANCH, {('appointment', 12), ('photo', 7), ('photo', -1)}),
    (SaveScope.PATH, {('patient', 1), ('appointment', 12)}),
    (SaveScope.FULL, {('patient', 1), ('appointment', 12), ('photo', 7), ('photo', -1)}),
    (SaveScope.DESCENDANTS, {('photo', 7), ('photo', -1)}),
])
def test_plan_row_target_scopes(tree, scope, expected):
    store, _ = tree
    plan = build_plan(store, [('appointment', 12)], scope)
    assert keys(plan.creates) | keys(plan.updates) == expected


def test_plan_frame_target_several_branches(tree):
    """Цель — выборка фрейма (несколько веток)."""
    store, _ = tree
    plan = build_plan(store, [('appointment', 12), ('appointment', 13)], SaveScope.SELF)
    assert keys(plan.updates) == {('appointment', 12), ('appointment', 13)}


def test_plan_order_parents_first(store):
    a = store.create('appointment', {}, parent_id=1)
    store.create('photo', {}, parent_id=a)
    plan = build_plan(store)
    assert [d.entity for d in plan.creates] == ['appointment', 'photo']


def test_plan_new_ancestor_outside_scope_needs_confirmation(store):
    """Треб. 6: сохраняем фото, а его приём — новый и не в объёме."""
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    plan = build_plan(store, [('photo', p)], SaveScope.SELF)
    assert plan.missing_new_ancestors == (('appointment', a),)
    assert plan.needs_confirmation
    plan = build_plan(store, [('photo', p)], SaveScope.SELF, include_new_ancestors=True)
    assert [d.key for d in plan.creates] == [('appointment', a), ('photo', p)]


def test_plan_include_new_ancestors_only_ancestors_not_siblings(store):
    a = store.create('appointment', {}, parent_id=1)
    p1 = store.create('photo', {}, parent_id=a)
    p2 = store.create('photo', {}, parent_id=a)
    plan = build_plan(store, [('photo', p1)], SaveScope.SELF, include_new_ancestors=True)
    assert ('photo', p2) not in keys(plan.creates)


def test_plan_deleted_branch_cascade(tree):
    """Треб. 7: родитель на удаление — удаляется вся ветка, черновики детей поглощаются."""
    store, new_photo = tree
    store.delete('appointment', 12)
    plan = build_plan(store, [('appointment', 12)], SaveScope.SELF)
    assert keys(plan.deletes) == {('appointment', 12)}
    assert keys(plan.dropped) == {('photo', 7), ('photo', new_photo)}
    assert plan.deleted_branches == (('appointment', 12),)
    assert plan.needs_confirmation


def test_plan_child_of_deleted_parent_blocked(tree):
    store, _ = tree
    store.delete('appointment', 12)
    plan = build_plan(store, [('photo', 7)], SaveScope.SELF)
    assert plan.blocked == (('photo', 7),) and plan.is_empty


def test_plan_reject_policy(tree):
    store, _ = tree
    store.delete('appointment', 12)
    with pytest.raises(PlanError, match='несохранённые'):
        build_plan(store, [('appointment', 12)], SaveScope.SELF, delete_policy=RejectChildChangesPolicy())


def test_plan_new_deleted_record_dropped(store):
    a = store.create('appointment', {}, parent_id=1)
    store.delete('appointment', a)
    plan = build_plan(store)
    assert keys(plan.dropped) == {('appointment', a)} and not plan.deletes


# ---------------------------------------------------------------------------
# Исполнение
# ---------------------------------------------------------------------------

def test_execute_maps_temp_ids_into_fk(store, adapter):
    a = store.create('appointment', {'date': 'd'}, parent_id=1)
    p = store.create('photo', {'path': 'x'}, parent_id=a)
    result = execute_plan(store, build_plan(store), adapter)
    real_a, real_p = result.id_map[('appointment', a)], result.id_map[('photo', p)]
    assert adapter.rows[('photo', real_p)]['appointment_id'] == real_a
    assert adapter.rows[('appointment', real_a)]['patient_id'] == 1
    assert store.is_empty


def test_execute_partial_remaps_remaining_children(store, adapter):
    """Сохранили только новый приём — у оставшегося черновика фото родитель стал настоящим (D10)."""
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    result = execute_plan(store, build_plan(store, [('appointment', a)], SaveScope.SELF), adapter)
    real_a = result.id_map[('appointment', a)]
    assert store.get('photo', p).parent_id == real_a
    assert store.get('photo', p).data['appointment_id'] == real_a
    assert store.status('appointment', real_a) == 'child'


def test_execute_failure_rolls_back_and_keeps_drafts(tree, adapter):
    """D2: сбой — ничего не записано, черновики на месте."""
    store, _ = tree
    adapter.fail_on = ('create', 'photo')
    before = store.drafted_nodes()
    with pytest.raises(RuntimeError):
        execute_plan(store, build_plan(store), adapter)
    assert adapter.rows == {} and adapter.log == []
    assert store.drafted_nodes() == before


def test_execute_refuses_missing_ancestors(store, adapter):
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {}, parent_id=a)
    with pytest.raises(PlanError, match='родител'):
        execute_plan(store, build_plan(store, [('photo', p)], SaveScope.SELF), adapter)


def test_execute_refuses_stale_plan(store, adapter):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    plan = build_plan(store)
    store.modify('photo', 8, {'a': 1}, parent_id=12)
    with pytest.raises(StalePlanError):
        execute_plan(store, plan, adapter)


def test_execute_delete_order_and_forget(tree, adapter):
    store, _ = tree
    store.delete('appointment', 12)
    store.delete('appointment', 13)
    result = execute_plan(store, build_plan(store, [('appointment', 12), ('appointment', 13)],
                                            SaveScope.SELF), adapter)
    assert set(result.deleted) == {('appointment', 12), ('appointment', 13)}
    assert [op for op, _, _ in adapter.log] == ['delete', 'delete']
    assert store.status('patient', 1) == 'own'          # остались только изменения пациента


def test_execute_reparent_to_new_parent_maps_fk(store, adapter):
    """Фото перенесено в НОВЫЙ приём: при сохранении внешний ключ — настоящий id."""
    a = store.create('appointment', {}, parent_id=1)
    store.modify('photo', 7, {'appointment_id': a}, original={'appointment_id': 12}, parent_id=12)
    result = execute_plan(store, build_plan(store), adapter)
    assert adapter.rows[('photo', 7)]['appointment_id'] == result.id_map[('appointment', a)]


# ---------------------------------------------------------------------------
# Сценарий владельца (треб. 2): фреймы, строки, возвраты — сохранение разом
# ---------------------------------------------------------------------------

def test_owner_scenario_multi_frame(store, adapter, events):
    # фрейм 1 (пациенты): изменили пациента 1
    store.modify('patient', 1, {'name': 'Иванов'}, original={'name': 'Иванов И.'})
    # фрейм 2 (приёмы + фото): приём 12 пациента 1 и его фото
    store.modify('appointment', 12, {'cost': 500}, parent_id=1)
    store.create('photo', {'path': 'a.jpg'}, parent_id=12)
    # назад на фрейм 1, другая строка — пациент 2
    store.modify('patient', 2, {'name': 'Петров'})
    # снова фрейм 2: новый приём пациента 2 и его фото; повторно меняем приём 12
    new_app = store.create('appointment', {'date': '2026-10-15'}, parent_id=2)
    store.create('photo', {'path': 'b.jpg'}, parent_id=new_app)
    store.modify('appointment', 12, {'cost': 550})
    assert store.status('patient', 1) == 'both' and store.status('patient', 2) == 'both'

    result = execute_plan(store, build_plan(store), adapter)
    assert store.is_empty
    assert len(result.created) == 3 and len(result.updated) == 3
    assert adapter.rows[('appointment', 12)] == {'cost': 550}
    real_app = result.id_map[('appointment', new_app)]
    assert adapter.rows[('appointment', real_app)]['patient_id'] == 2
    assert any(row.get('appointment_id') == real_app for row in adapter.rows.values())
    assert any(e.kind == 'remapped' for e in events)


# ---------------------------------------------------------------------------
# Переносимость
# ---------------------------------------------------------------------------

def test_package_has_no_project_or_qt_imports():
    """Пакет — только стандартная библиотека и относительные импорты (перенос в другие проекты)."""
    stdlib = set(sys.stdlib_module_names)
    for name in os.listdir(PKG):
        if not name.endswith('.py'):
            continue
        tree = ast.parse(open(os.path.join(PKG, name), encoding='utf-8').read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [a.name.split('.')[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:          # относительный — внутри пакета
                    continue
                roots = [node.module.split('.')[0]]
            else:
                continue
            assert all(r in stdlib for r in roots), (name, roots)


def test_package_works_when_copied_elsewhere(tmp_path):
    """Копия пакета под другим именем работает без проекта."""
    import shutil
    shutil.copytree(PKG, tmp_path / 'mydrafts', ignore=shutil.ignore_patterns('__pycache__'))
    code = (
        "from mydrafts import *\n"
        "s = DraftStore(TreeSchema([EntityType('a'), EntityType('b', 'a', 'a_id')]))\n"
        "s.create('b', {}, parent_id=1)\n"
        "print(s.status('a', 1))\n"
    )
    out = subprocess.run([sys.executable, '-c', code], cwd=str(tmp_path),
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == 'child'


# ---------------------------------------------------------------------------
# Чтение для интерфейса и прочие операции
# ---------------------------------------------------------------------------

def test_discard_new_record_event_reaches_ancestors(store, events):
    """N1: отмена новой записи — событие называет и предков (значок родителя обновится)."""
    store.remember_parent('appointment', 12, 1)
    p = store.create('photo', {}, parent_id=12)
    store.discard([('photo', p)])
    assert events[-1].kind == 'discarded'
    assert ('appointment', 12) in events[-1].affected and ('patient', 1) in events[-1].affected


def test_drafts_filters(store):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    new_photo = store.create('photo', {}, parent_id=12)
    store.create('photo', {}, parent_id=13)
    store.modify('appointment', 12, {'c': 1}, parent_id=1)
    assert [d.id for d in store.drafts('photo', parent_id=12)] == [7, new_photo]
    assert [d.id for d in store.drafts('photo', parent_id=12, new_only=True)] == [new_photo]
    assert [d.key for d in store.drafts()][-1] == ('appointment', 12)


def test_effective_merges_base_and_changes(store):
    store.modify('appointment', 12, {'cost': 5}, parent_id=1)
    assert store.effective('appointment', 12, {'cost': 1, 'date': 'd'}) == {'cost': 5, 'date': 'd'}
    assert store.effective('appointment', 99, {'cost': 1}) == {'cost': 1}


def test_has_changes_scopes(store):
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert store.has_changes() and store.has_changes([('patient', 1)])
    assert not store.has_changes([('patient', 1)], SaveScope.SELF)
    assert not store.has_changes([('patient', 2)])


def test_clear_and_unsubscribe(store, events):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.clear()
    assert store.is_empty and store.children(('appointment', 12)) == set()
    assert events[-1].kind == 'cleared'
    store.unsubscribe(events.append)
    store.unsubscribe(events.append)         # повторно — без ошибки
    store.modify('photo', 8, {'a': 1}, parent_id=12)
    assert events[-1].kind == 'cleared'


def test_duplicate_temp_id_rejected(store):
    store.create('photo', {}, parent_id=12, temp_id=-50)
    with pytest.raises(ValueError, match='уже есть'):
        store.create('photo', {}, parent_id=12, temp_id=-50)


def test_delete_twice_and_undelete_noop(store, events):
    store.delete('photo', 7, parent_id=12)
    store.delete('photo', 7)
    store.undelete('photo', 99)
    assert [e.kind for e in events] == ['deleted']


def test_custom_temp_id_factory(schema):
    import uuid
    store = DraftStore(schema, temp_id_factory=lambda: f'tmp-{uuid.uuid4().hex[:6]}')
    assert str(store.create('patient', {})).startswith('tmp-')
