# tests/test_drafts/conftest.py

"""
Общие фикстуры тестов пакета черновиков: схема пациент → приём → фото и адаптер
хранилища данных в памяти (без БД).
"""

import contextlib
import itertools
from typing import Any, Dict, Hashable, List, Mapping, Tuple

import pytest

from app.utils.drafts import DraftStore, EntityType, TreeSchema


def make_schema() -> TreeSchema:
    """Схема приложения: пациент → приём → фото."""
    return TreeSchema([
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём'),
        EntityType('photo', parent='appointment', parent_field='appointment_id', label='Фото'),
    ])


class MemoryAdapter:
    """
    Хранилище данных в памяти: ``rows[(тип, id)] = поля``; транзакция — копия, при
    исключении откат. ``fail_on`` — (операция, тип) для имитации сбоя.
    """

    def __init__(self) -> None:
        self.rows: Dict[Tuple[str, Hashable], Dict[str, Any]] = {}
        self.log: List[Tuple[str, str, Hashable]] = []
        self.fail_on: Tuple[str, str] = ('', '')
        self._ids = itertools.count(100)

    @contextlib.contextmanager
    def transaction(self):
        snapshot = {k: dict(v) for k, v in self.rows.items()}
        log_len = len(self.log)
        try:
            yield 'tx'
        except BaseException:
            self.rows = snapshot
            del self.log[log_len:]
            raise

    def _maybe_fail(self, op: str, entity: str) -> None:
        if self.fail_on == (op, entity):
            raise RuntimeError(f'сбой {op} {entity}')

    def create(self, entity: str, data: Mapping[str, Any], tx: Any) -> int:
        self._maybe_fail('create', entity)
        new_id = next(self._ids)
        self.rows[(entity, new_id)] = dict(data)
        self.log.append(('create', entity, new_id))
        return new_id

    def update(self, entity: str, entity_id: Hashable, changes: Mapping[str, Any], tx: Any) -> None:
        self._maybe_fail('update', entity)
        self.rows.setdefault((entity, entity_id), {}).update(changes)
        self.log.append(('update', entity, entity_id))

    def delete(self, entity: str, entity_id: Hashable, tx: Any) -> None:
        self._maybe_fail('delete', entity)
        self.rows.pop((entity, entity_id), None)
        self.log.append(('delete', entity, entity_id))

    def referrers(self, entity: str, field: str, ids, tx: Any) -> List[Hashable]:
        """Кто из записей типа ``entity`` ссылается полем ``field`` на ``ids`` (ссылки, 2026-10-18)."""
        wanted = set(ids)
        return [i for (e, i), row in self.rows.items() if e == entity and row.get(field) in wanted]

    def read(self, entity: str, entity_id: Hashable, tx: Any = None):
        """Запись из «БД» (для переиспользуемых данных — что удалять следом)."""
        row = self.rows.get((entity, entity_id))
        return dict(row) if row is not None else None


@pytest.fixture
def schema() -> TreeSchema:
    return make_schema()


@pytest.fixture
def store(schema) -> DraftStore:
    return DraftStore(schema)


@pytest.fixture
def adapter() -> MemoryAdapter:
    return MemoryAdapter()


@pytest.fixture
def events(store) -> list:
    """События хранилища (список DraftEvent)."""
    got: list = []
    store.subscribe(got.append)
    return got
