# tests/test_drafts/test_drafts_shared_targets.py

"""
Черновики: цель ссылок, которую хранилище данных убрало само в той же транзакции
(2026-10-31).

Так ведут себя общие заметки приложения: сервис записи, сменившей текст заметки, сам
удаляет ставшую ненужной прежнюю заметку. Если ту же заметку пометили на удаление в
черновиках, повторное удаление давало «не найдено» и откат всего сохранения.
"""

from typing import Any, Hashable, Mapping

from app.utils.drafts import DraftStore, EntityType, Reference, SaveScope, TreeSchema, build_plan, execute_plan

from .conftest import MemoryAdapter


class CollectingAdapter(MemoryAdapter):
    """Как сервисы приложения: прежняя заметка без ссылок удаляется при правке записи."""

    def update(self, entity: str, entity_id: Hashable, changes: Mapping[str, Any], tx: Any) -> None:
        old = self.rows.get((entity, entity_id), {}).get('note_id')
        super().update(entity, entity_id, changes, tx)
        if old is not None and not self.referrers('patient', 'note_id', [old], tx):
            self.rows.pop(('note', old), None)                 # «сервис» убрал ненужную

    def delete(self, entity: str, entity_id: Hashable, tx: Any) -> None:
        if (entity, entity_id) not in self.rows:
            raise LookupError(f'{entity} {entity_id} не найдена')   # как сервисы: «не найдено»
        super().delete(entity, entity_id, tx)


def schema() -> TreeSchema:
    return TreeSchema([
        EntityType('note', label='Заметка'),
        EntityType('patient', label='Пациент', references=[Reference('note_id', 'note')]),
    ])


def test_target_already_removed_by_data_store_is_not_deleted_again():
    store, adapter = DraftStore(schema()), CollectingAdapter()
    adapter.rows[('note', 1)] = {'text': 'старое'}
    adapter.rows[('note', 2)] = {'text': 'новое'}
    adapter.rows[('patient', 10)] = {'note_id': 1}
    store.modify('patient', 10, {'note_id': 2}, original={'note_id': 1})
    store.delete('note', 1)
    result = execute_plan(store, build_plan(store, None, SaveScope.FULL), adapter)
    assert ('note', 1) in result.deleted and ('note', 1) not in adapter.rows
    assert ('delete', 'note', 1) not in adapter.log                  # удалять было нечего
    assert adapter.rows[('patient', 10)] == {'note_id': 2} and store.is_empty


def test_existing_target_still_deleted():
    store, adapter = DraftStore(schema()), CollectingAdapter()
    adapter.rows[('note', 1)] = {'text': 'ничья'}
    store.delete('note', 1)
    execute_plan(store, build_plan(store, None, SaveScope.FULL), adapter)
    assert adapter.log == [('delete', 'note', 1)] and ('note', 1) not in adapter.rows
