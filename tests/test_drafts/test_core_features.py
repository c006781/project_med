# tests/test_drafts/test_core_features.py

"""
Ядро черновиков: отмена/повтор (undo/redo), отмена отдельных полей, N2 (откат переноса
при отмене новой записи), сводка, конфликты, открытый ``apply_saved``; случайные
последовательности операций с проверкой инвариантов.
"""

import random

import pytest

from app.utils.drafts import (
    DraftStore, SaveScope, build_plan, execute_plan, find_conflicts,
)


# ---------------------------------------------------------------------------
# Отмена / повтор
# ---------------------------------------------------------------------------

def test_undo_redo_single_step(store):
    store.modify('appointment', 12, {'cost': 5}, original={'cost': 1}, parent_id=1)
    assert store.can_undo and not store.can_redo
    assert store.undo() and not store.has_draft('appointment', 12)
    assert store.redo() and store.get('appointment', 12).data == {'cost': 5}
    assert not store.redo()


def test_batch_is_one_step(store):
    with store.batch():
        store.modify('photo', 7, {'a': 1}, parent_id=12)
        store.modify('photo', 8, {'a': 1}, parent_id=12)
    store.undo()
    assert store.is_empty and not store.can_undo


def test_new_action_clears_redo(store):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.undo()
    store.modify('photo', 8, {'a': 1}, parent_id=12)
    assert not store.can_redo


def test_noop_operations_do_not_add_steps(store):
    store.undelete('photo', 99)
    store.discard([('photo', 99)])
    store.revert_field('photo', 99, 'a')
    assert not store.can_undo


def test_history_limit(schema):
    store = DraftStore(schema, history_limit=2)
    for i in range(5):
        store.modify('photo', i, {'a': 1}, parent_id=12)
    assert store.undo() and store.undo() and not store.undo()
    assert len(store.drafted_nodes()) == 3


def test_history_disabled(schema):
    store = DraftStore(schema, history_limit=0)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert not store.can_undo


def test_undo_discard_restores_new_branch(store):
    a = store.create('appointment', {}, parent_id=1)
    p = store.create('photo', {'f': 'x'}, parent_id=a)
    store.discard([('appointment', a)])
    assert store.is_empty
    store.undo()
    assert store.parent_of('photo', p) == ('appointment', a)
    assert store.status('appointment', a) == 'both'


def test_undo_emits_restored_with_ancestors(store, events):
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.undo()
    assert events[-1].kind == 'restored'
    assert ('patient', 1) in events[-1].affected


def test_undo_keeps_links_learned_later(store):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.remember_parent('appointment', 12, 1)          # узнали после шага
    store.undo()
    store.redo()
    assert store.status('patient', 1) == 'child'


def test_undo_forgets_links_of_new_records(store):
    a = store.create('appointment', {}, parent_id=1)
    store.undo()
    assert store.children(('patient', 1)) == set()
    assert store.parent_of('appointment', a) is None


def test_save_clears_history(store, adapter):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    execute_plan(store, build_plan(store), adapter)
    assert not store.can_undo and not store.can_redo


def test_undo_makes_old_plan_stale(store, adapter):
    from app.utils.drafts import StalePlanError
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.modify('photo', 8, {'a': 1}, parent_id=12)
    plan = build_plan(store)
    store.undo()
    with pytest.raises(StalePlanError):
        execute_plan(store, plan, adapter)


# ---------------------------------------------------------------------------
# Отмена отдельных полей
# ---------------------------------------------------------------------------

def test_revert_field_keeps_other_changes(store, events):
    store.modify('appointment', 12, {'cost': 5, 'note': 'x'}, original={'cost': 1, 'note': ''},
                 parent_id=1)
    store.revert_field('appointment', 12, 'cost')
    assert store.get('appointment', 12).data == {'note': 'x'}
    store.revert_field('appointment', 12, 'note')
    assert not store.has_draft('appointment', 12)
    assert events[-1].kind == 'discarded'


def test_revert_fk_moves_back(store):
    store.remember_parent('appointment', 12, 1)
    store.remember_parent('appointment', 13, 1)
    store.modify('photo', 7, {'appointment_id': 13, 'd': 'x'}, original={'appointment_id': 12},
                 parent_id=12)
    store.revert_field('photo', 7, 'appointment_id')
    assert store.parent_of('photo', 7) == ('appointment', 12)
    assert store.status('appointment', 12) == 'child' and store.status('appointment', 13) is None


def test_revert_fk_without_original_rejected(store):
    store.modify('photo', 7, {'appointment_id': 13}, parent_id=12)
    with pytest.raises(ValueError, match='неизвестно'):
        store.revert_field('photo', 7, 'appointment_id')


def test_revert_field_of_new_record(store):
    p = store.create('photo', {'f': 'x', 'd': 'y'}, parent_id=12)
    store.revert_field('photo', p, 'd')
    assert 'd' not in store.get('photo', p).data and store.get('photo', p).is_new
    with pytest.raises(ValueError, match='новой записи'):
        store.revert_field('photo', p, 'appointment_id')


# ---------------------------------------------------------------------------
# N2: отмена новой записи возвращает перенесённые в неё существующие
# ---------------------------------------------------------------------------

def test_n2_discard_new_parent_moves_existing_back(store):
    store.remember_parent('appointment', 12, 1)
    a = store.create('appointment', {}, parent_id=1)
    store.modify('photo', 7, {'appointment_id': a, 'd': 'x'}, original={'appointment_id': 12},
                 parent_id=12)
    store.modify('photo', 8, {'appointment_id': a}, original={'appointment_id': 12}, parent_id=12)
    store.discard([('appointment', a)])
    assert store.get('photo', 7).data == {'d': 'x'}                # правка осталась
    assert store.parent_of('photo', 7) == ('appointment', 12)
    assert not store.has_draft('photo', 8)                         # был только перенос
    assert not store.has_draft('appointment', a)


def test_n2_without_original_discards_whole(store):
    a = store.create('appointment', {}, parent_id=1)
    store.modify('photo', 7, {'appointment_id': a, 'd': 'x'}, parent_id=12)
    store.discard([('appointment', a)])
    assert not store.has_draft('photo', 7)


# ---------------------------------------------------------------------------
# Сводка, apply_saved, конфликты
# ---------------------------------------------------------------------------

def test_counts(store):
    store.create('appointment', {}, parent_id=1)
    store.modify('appointment', 12, {'c': 1}, parent_id=1)
    store.delete('appointment', 13, parent_id=1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert store.counts() == {'appointment': {'new': 1, 'modified': 1, 'deleted': 1},
                              'photo': {'new': 0, 'modified': 1, 'deleted': 0}}


def test_apply_saved_public_and_alias(store):
    assert DraftStore._commit is DraftStore.apply_saved
    p = store.create('photo', {}, parent_id=12)
    store.apply_saved({('photo', p)}, {('photo', p): 77})
    assert store.is_empty


def test_conflicts(store):
    store.modify('appointment', 12, {'cost': 5, 'note': 'n'}, original={'cost': 1, 'note': ''},
                 parent_id=1)
    store.modify('appointment', 12, {'note': ''})                   # note вернули
    store.delete('appointment', 13, parent_id=1)
    store.modify('photo', 7, {'a': 2}, original={'a': 1}, parent_id=12)
    store.create('photo', {}, parent_id=12)                          # новые не проверяются
    db = {('appointment', 12): {'cost': 3, 'note': 'changed'},      # cost изменили в БД
          ('photo', 7): {'a': 1}}                                    # 13 удалили в БД
    conflicts = find_conflicts(build_plan(store), lambda t, i: db.get((t, i)))
    assert {(c.node, c.field) for c in conflicts} == {(('appointment', 12), 'cost'),
                                                      (('appointment', 13), None)}
    cost = next(c for c in conflicts if c.field == 'cost')
    assert (cost.original, cost.current, cost.draft) == (1, 3, 5)
    assert next(c for c in conflicts if c.field is None).record_gone


# ---------------------------------------------------------------------------
# Случайные последовательности операций — инварианты
# ---------------------------------------------------------------------------

def _brute_status(store, node):
    """Статус «в лоб»: свои черновики + обход ВСЕХ черновиков вверх по связям."""
    own = store.has_draft(*node)
    child = False
    for other in store.drafted_nodes():
        if other != node and node in store.ancestors(other):
            child = True
    return {(True, True): 'both', (True, False): 'own', (False, True): 'child'}.get((own, child))


def _check_invariants(store):
    # индекс детей согласован со связями
    for parent, kids in store._children.items():
        for kid in kids:
            assert store._parent_key(kid) == parent
    for node in store._parents:
        parent = store._parent_key(node)
        if parent is not None:
            assert node in store._children.get(parent, set())
    # значки совпадают с подсчётом «в лоб»
    nodes = set(store.drafted_nodes()) | set(store._parents) | set(store._children)
    for node in nodes:
        assert store.status(*node) == _brute_status(store, node), node
    # у черновиков нет пустых записей
    for node in store.drafted_nodes():
        assert store.get(*node).has_own_changes


@pytest.mark.parametrize('seed', range(20))
def test_random_operations_keep_invariants(schema, seed):
    rnd = random.Random(seed)
    store = DraftStore(schema, history_limit=1000)
    for pid in (1, 2):
        for aid in (10 * pid, 10 * pid + 1):
            store.remember_parent('appointment', aid, pid)
    appointments = [10, 11, 20, 21]
    photos = list(range(100, 108))
    for photo in photos:
        store.remember_parent('photo', photo, rnd.choice(appointments))
    steps = 0
    for _ in range(150):
        op = rnd.choice(['modify', 'create_app', 'create_photo', 'delete', 'undelete', 'discard',
                         'move', 'revert', 'undo', 'redo', 'remember'])
        if op == 'modify':
            entity, eid = rnd.choice([('patient', rnd.choice([1, 2])), ('appointment', rnd.choice(appointments)),
                                      ('photo', rnd.choice(photos))])
            store.modify(entity, eid, {'f': rnd.choice([0, 1, 2])}, original={'f': 0})
        elif op == 'create_app':
            appointments.append(store.create('appointment', {}, parent_id=rnd.choice([1, 2])))
        elif op == 'create_photo':
            photos.append(store.create('photo', {}, parent_id=rnd.choice(appointments)))
        elif op == 'delete':
            store.delete('photo', rnd.choice(photos))
        elif op == 'undelete':
            store.undelete('photo', rnd.choice(photos))
        elif op == 'discard':
            target = rnd.choice([('appointment', rnd.choice(appointments)), ('photo', rnd.choice(photos))])
            store.discard([target], rnd.choice([SaveScope.SELF, SaveScope.BRANCH, SaveScope.FULL]))
        elif op == 'move':
            photo = rnd.choice(photos[:8])
            current = store.parent_of('photo', photo)
            if current is not None:
                original = store.get('photo', photo).original.get('appointment_id', current[1]) \
                    if store.has_draft('photo', photo) else current[1]
                store.modify('photo', photo, {'appointment_id': rnd.choice(appointments)},
                             original={'appointment_id': original})
        elif op == 'revert':
            node = rnd.choice(store.drafted_nodes()) if not store.is_empty else None
            if node is not None:
                try:
                    store.revert_field(*node, 'f')
                except ValueError:
                    pass
        elif op == 'remember':
            store.remember_parent('appointment', rnd.choice([10, 11, 20, 21]), rnd.choice([1, 2]))
        elif op == 'undo':
            store.undo()
        elif op == 'redo':
            store.redo()
        steps += 1
        appointments = [a for a in appointments if not (isinstance(a, int) and a < 0)
                        or store.has_draft('appointment', a)] or [10]
        photos = [p for p in photos if p >= 100 or store.has_draft('photo', p)]
        _check_invariants(store)
    while store.undo():
        pass
    assert store.is_empty



# ---------------------------------------------------------------------------
# Финальный проход (R4, R6, R7, R11)
# ---------------------------------------------------------------------------

def test_r4_remember_parent_reports_new_ancestors(store, events):
    """Строки приёмов загрузились ПОСЛЕ правки фото — пациент получает значок (событие)."""
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.remember_parent('appointment', 12, 1)
    assert events[-1].kind == 'linked' and ('patient', 1) in events[-1].affected
    assert store.status('patient', 1) == 'child'
    count = len(events)
    store.remember_parent('appointment', 12, 1)            # то же самое — без события
    store.remember_parent('appointment', 99, 1)            # нет черновиков — без события
    assert len(events) == count


def test_r4_reparent_known_reports_old_ancestors(store, events):
    store.remember_parent('appointment', 12, 1)
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    store.remember_parent('appointment', 12, 2)            # приём «переехал» к пациенту 2
    assert ('patient', 1) in events[-1].affected and ('patient', 2) in events[-1].affected
    assert store.status('patient', 1) is None and store.status('patient', 2) == 'child'


def test_r6_empty_operations_are_silent(store, events):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    version, count, steps = store.version, len(events), len(store._undo)
    store.modify('photo', 7, {})
    store.revert_field('photo', 7, 'nope')
    assert (store.version, len(events), len(store._undo)) == (version, count, steps)
    store.modify('photo', 8, {}, parent_id=13)             # только сведения о родителе
    assert store.parent_of('photo', 8) == ('appointment', 13) and not store.has_draft('photo', 8)


def test_r7_undo_drops_links_to_vanished_new_records(store):
    store.remember_parent('appointment', 12, 1)
    a = store.create('appointment', {}, parent_id=1)
    store.modify('photo', 7, {'appointment_id': a}, original={'appointment_id': 12})
    store.undo()                                           # перенос
    store.undo()                                           # создание приёма
    assert store.parent_of('photo', 7) != ('appointment', a)
    store.modify('photo', 7, {'b': 1}, parent_id=12)
    assert store.status('appointment', 12) == 'child'


def test_r11_status_cache_invalidated(store):
    store.remember_parent('appointment', 12, 1)
    assert store.status('patient', 1) is None              # закешировано
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    assert store.status('patient', 1) == 'child'           # версия сменилась
    store.remember_parent('appointment', 12, 2)
    assert store.status('patient', 1) is None              # связи сменились


def test_r11_status_computed_once_per_state(store, monkeypatch):
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    calls = []
    real = store.has_descendant_changes
    monkeypatch.setattr(store, 'has_descendant_changes', lambda *a: calls.append(a) or real(*a))
    for _ in range(50):                                  # 50 ячеек строки при перерисовке
        store.status('appointment', 12)
    assert len(calls) == 1


def test_q3_linking_does_not_create_undo_step(store):
    """Q3: загрузка строк (remember_parent → 'linked') не добавляет пустой шаг отмены."""
    store.modify('photo', 7, {'a': 1}, parent_id=12)
    steps = len(store._undo)
    version = store.version
    with store.batch():
        store.remember_parent('appointment', 12, 1)
    assert store.version > version                       # план устаревает (связи поменялись)
    assert len(store._undo) == steps                     # а шага отмены нет
    store.modify('photo', 8, {}, parent_id=13)
    assert len(store._undo) == steps
