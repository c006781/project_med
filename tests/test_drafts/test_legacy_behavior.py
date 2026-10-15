# tests/test_drafts/test_legacy_behavior.py

"""
Поведение СТАРОЙ системы черновиков «как есть» (до переделки, 2026-10-15).

``DraftRegistry`` (app/draft/draft_registry.py) и ``DraftTreeMixin``
(interfaces/gui/gui_window/mixins/draft_tree_mixin.py) — без окна: QObject работает без
QApplication. Известные ошибки — ``xfail(strict=True)``; номера — app/draft/IMPLEMENTATION.md §3.
Когда страницы переведут на новый механизм, эти тесты фиксируют, от чего ушли.
"""

from typing import Dict, Optional

import pytest
from pydantic import BaseModel
from PySide6.QtCore import QObject, Signal

from app.draft.draft_registry import DraftRegistry
from interfaces.gui.gui_window.mixins.draft_tree_mixin import DraftTreeMixin


class PhotoDTO(BaseModel):
    """DTO для тестов (id + внешний ключ на приём)."""
    id: int
    appointment_id: int


class FakePage(QObject, DraftTreeMixin):
    """
    Страница-заглушка: дерево задаётся словарями ``parents`` (id → id родителя) и
    ``parent_types`` (id → тип родителя), как это делают переопределения страниц.
    """
    draft_modified_changed = Signal(bool)
    entity_status_changed = Signal(int, bool)

    def __init__(self, registry: DraftRegistry, entity_type: str,
                 parents: Optional[Dict[int, int]] = None,
                 parent_types: Optional[Dict[int, str]] = None) -> None:
        super().__init__()
        self._draft_registry = registry
        self._entity_type = entity_type
        self.parents = parents or {}
        self.parent_types = parent_types or {}

    def _get_parent_id(self, child_id: int) -> Optional[int]:
        return self.parents.get(child_id)

    def _get_parent_entity_type(self, child_id: int) -> str:
        return self.parent_types.get(child_id, self._entity_type)


@pytest.fixture
def registry() -> DraftRegistry:
    return DraftRegistry()


# ---------------------------------------------------------------------------
# DraftRegistry — хранилище
# ---------------------------------------------------------------------------

def test_set_get_has_discard(registry):
    registry.set('patient:1:draft', {'dto': {'id': 1}})
    assert registry.has('patient:1:draft')
    assert registry.get('patient:1:draft') == {'dto': {'id': 1}}
    registry.discard('patient:1:draft')
    assert registry.get('patient:1:draft') is None


def test_signal_only_on_appear_and_disappear(registry):
    """Сигнал — при появлении и исчезновении ключа; перезапись — без сигнала."""
    events = []
    registry.draft_changed.connect(lambda k, h: events.append((k, h)))
    registry.set('a:1:draft', {'x': 1})
    registry.set('a:1:draft', {'x': 2})
    registry.discard('a:1:draft')
    registry.discard('a:1:draft')
    assert events == [('a:1:draft', True), ('a:1:draft', False)]


def test_prefix_operations(registry):
    for key in ('appointment:1:draft', 'appointment:1:photos', 'appointment:10:draft'):
        registry.set(key, {})
    assert registry.get_keys_by_prefix('appointment:1:') == {'appointment:1:draft', 'appointment:1:photos'}
    assert registry.has_prefix('appointment:10:')
    registry.discard_by_prefix('appointment:1:')
    assert registry.get_keys_by_prefix('appointment:') == {'appointment:10:draft'}


def test_subscribe_exact_and_prefix(registry):
    exact, prefix = [], []
    registry.subscribe('a:1:draft', lambda k, h: exact.append(k))
    registry.subscribe_prefix('a:', lambda k, h: prefix.append(k))
    registry.set('a:1:draft', {})
    registry.set('a:2:draft', {})
    assert exact == ['a:1:draft']
    assert prefix == ['a:1:draft', 'a:2:draft']


def test_failing_listener_does_not_break_others(registry):
    got = []

    def bad(k, h):
        raise RuntimeError('boom')

    registry.subscribe('k', bad)
    registry.subscribe_prefix('k', lambda k, h: got.append(k))
    registry.set('k', {})
    assert got == ['k']


def test_apply_and_clear(registry):
    applied = []
    registry.set('a:1:draft', {'v': 1})
    registry.apply_and_clear('a:1:draft', applied.append)
    assert applied == [{'v': 1}] and not registry.has('a:1:draft')


def test_apply_and_clear_failure_keeps_draft(registry):
    registry.set('a:1:draft', {'v': 1})

    def fail(data):
        raise ValueError('db')

    with pytest.raises(ValueError):
        registry.apply_and_clear('a:1:draft', fail)
    assert registry.has('a:1:draft')


def test_apply_by_prefix_stops_at_first_failure(registry):
    """Как есть: применение по префиксу не атомарно — успешные до сбоя уже удалены."""
    for i in (1, 2):
        registry.set(f'a:{i}:draft', {'v': i})

    def applier(key, data):
        if data['v'] == 2:
            raise ValueError('db')

    with pytest.raises(ValueError):
        registry.apply_by_prefix('a:', applier)
    # какой из ключей успел примениться, зависит от порядка множества — проверяем инвариант
    assert len(registry.get_keys_by_prefix('a:')) in (1, 2)
    assert registry.has('a:2:draft')


def test_counters_never_negative(registry):
    assert registry.inc_child_counter('appointment', 5) == 1
    assert registry.dec_child_counter('appointment', 5) == 0
    assert registry.dec_child_counter('appointment', 5) == 0
    assert not registry.has('__counter__:appointment:5')


def test_entity_status_roundtrip(registry):
    registry.set_entity_status('patient', 1, 'own')
    assert registry.get_entity_status('patient', 1) == 'own'
    registry.set_entity_status('patient', 1, None)
    assert registry.get_entity_status('patient', 1) is None


def test_discard_entity_subtree_registry_level_not_recursive(registry):
    """Как есть: уровень реестра чистит только саму сущность, не детей."""
    registry.set('appointment:5:draft', {})
    registry.set_entity_status('appointment', 5, 'both')
    registry.set_entity_status('photo', 7, 'own')
    registry.discard_entity_subtree('appointment', 5)
    assert not registry.has('appointment:5:draft')
    assert registry.get_entity_status('photo', 7) == 'own'


# ---------------------------------------------------------------------------
# DraftRegistry — DTO
# ---------------------------------------------------------------------------

def test_save_load_dto_excludes_virtual_and_computed(registry):
    class Dto(BaseModel):
        id: int
        name: str
        age_view: str = ''
        note_text: str = ''

    configs = {'age_view': {'virtual': True}, 'note_text': {'virtual': True, 'is_note': True}}
    registry.save_draft_dto(Dto(id=1, name='A', age_view='9', note_text='n'), 'patient', 1, configs)
    assert registry.get('patient:1:draft') == {'dto': {'id': 1, 'name': 'A', 'note_text': 'n'}}
    assert registry.load_draft_dto('patient', 1, Dto).name == 'A'
    registry.clear_draft_dto('patient', 1)
    assert registry.load_draft_dto('patient', 1, Dto) is None


def test_save_dto_mutates_passed_exclude_set(registry):
    """Как есть: переданный exclude_fields дополняется на месте (побочный эффект)."""
    class Dto(BaseModel):
        id: int
        v: str = ''

    exclude = set()
    registry.save_draft_dto(Dto(id=1), 'x', 1, {'v': {'virtual': True}}, exclude)
    assert exclude == {'v'}


def test_new_dtos_merged_without_duplicates(registry):
    registry.set('__new__:photo:-1', {'dto': {'id': -1, 'appointment_id': 5}})
    page = [PhotoDTO(id=3, appointment_id=5)]
    merged = registry.merge_new_dtos('photo', page, PhotoDTO)
    assert [d.id for d in merged] == [-1, 3]


@pytest.mark.xfail(strict=True, reason='D10: DTO в реестре — словарь, а замена ищет атрибут')
def test_foreign_key_of_new_children_replaced_after_parent_saved(registry):
    """Новое фото нового приёма: после сохранения приёма (-5 → 55) ссылка должна смениться."""
    registry.set('__new__:photo:-1', {'dto': {'id': -1, 'appointment_id': -5}})
    assert registry.update_foreign_key_in_new_dtos(-5, 55, 'appointment_id') == 1
    assert registry.get('__new__:photo:-1')['dto']['appointment_id'] == 55


# ---------------------------------------------------------------------------
# DraftTreeMixin — статусы
# ---------------------------------------------------------------------------

def test_own_change_marks_parent_child(registry):
    """Два уровня: фото изменено → у приёма статус child и счётчик 1."""
    page = FakePage(registry, 'photo', parents={7: 5}, parent_types={7: 'appointment'})
    page.mark_own_change(7)
    assert registry.get_entity_status('photo', 7) == 'own'
    assert registry.get_entity_status('appointment', 5) == 'child'
    assert registry.get_child_counter('appointment', 5) == 1


@pytest.mark.xfail(strict=True, reason='D11: статус родителя не снимается — кеш и реестр расходятся')
def test_clear_own_change_restores_parent(registry):
    page = FakePage(registry, 'photo', parents={7: 5}, parent_types={7: 'appointment'})
    page.mark_own_change(7)
    page.clear_own_change(7)
    assert registry.get_entity_status('photo', 7) is None
    assert registry.get_entity_status('appointment', 5) is None
    assert registry.get_child_counter('appointment', 5) == 0


@pytest.mark.xfail(strict=True, reason='D11: статус родителя не снимается — кеш и реестр расходятся')
def test_two_children_parent_stays_until_both_cleared(registry):
    page = FakePage(registry, 'photo', parents={7: 5, 8: 5}, parent_types={7: 'appointment', 8: 'appointment'})
    page.mark_own_change(7)
    page.mark_own_change(8)
    page.clear_own_change(7)
    assert registry.get_entity_status('appointment', 5) == 'child'
    page.clear_own_change(8)
    assert registry.get_entity_status('appointment', 5) is None


def test_status_from_flags():
    assert DraftTreeMixin._status_from_flags(True, True) == 'both'
    assert DraftTreeMixin._status_from_flags(True, False) == 'own'
    assert DraftTreeMixin._status_from_flags(False, True) == 'child'
    assert DraftTreeMixin._status_from_flags(False, False) is None


@pytest.mark.xfail(strict=True, reason='D4: при подъёме тип родителя теряется (ключ __status__:None:…)')
def test_three_levels_status_reaches_root(registry):
    """фото 7 → приём 5 → пациент 1: изменение фото помечает и приём, и пациента."""
    page = FakePage(registry, 'photo', parents={7: 5, 5: 1},
                    parent_types={7: 'appointment', 5: 'patient'})
    page.mark_own_change(7)
    assert registry.get_entity_status('appointment', 5) == 'child'
    assert registry.get_entity_status('patient', 1) == 'child'


@pytest.mark.xfail(strict=True, reason='D5: кеш статусов — по id без типа таблицы')
def test_same_id_in_two_tables_independent(registry):
    page = FakePage(registry, 'appointment')
    page.mark_own_change(5)
    page._entity_type = 'photo'
    page.mark_own_change(5)
    assert registry.get_entity_status('photo', 5) == 'own'
