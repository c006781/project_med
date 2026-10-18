# app/dataset_app/drafts_writer.py

"""
Мост «наборы данных ↔ черновики»: правки набора копятся в черновиках (аналог
``CachedUpdates`` RAD Studio) и сохраняются разом — через уже готовый план черновиков.

Ядро наборов о черновиках не знает (решение 2026-10-18): мост — обычный способ записи
(``DataWriter``) + показ несохранённого (``RowOverlay``) и живёт в слое приложения.

* ``post()`` новой строки → ``store.create`` (временный id < 0), правки → ``store.modify``
  (с исходными значениями: вернули как было — черновик исчезает), удаление →
  ``store.delete`` (существующая строка остаётся видна с пометкой «удалена»; новая —
  просто исчезает).
* После каждого чтения поверх строк из БД — значения черновиков, а в первое окно —
  новые строки этого родителя (по условию связи ``parent_field``).
* Состояние строки для подсветки: ``new`` / ``modified`` / ``deleted`` / ``child``
  (изменены подчинённые записи).
* Изменения черновиков из ДРУГИХ мест (другой экран, отмена/повтор, сохранение,
  временные id → настоящие) — подключённые наборы перечитываются (если не в правке —
  иначе после неё); значки предков перерисовываются (``DataSet.touch``).

Пример:
    >>> writer = DraftsWriter(app_drafts.store, 'appointment')
    >>> appointments = writer.attach(DataSet(backend, writer=writer, name='appointments'))
    >>> appointments.append({'date': date.today()}); appointments.post()   # черновик, не БД
    >>> app_drafts.save()                                                   # всё разом
"""

from __future__ import annotations

import contextlib
import weakref
from typing import Any, Dict, Hashable, Iterator, List, Mapping, Optional

from app.utils.dataset import DataEvent, DataSet, EventKind, Op, Query, State
from app.utils.drafts import MISSING, DraftEvent, DraftStore

# События черновиков, после которых наборы этого типа перечитываются целиком
_GLOBAL_KINDS = frozenset({'saved', 'remapped', 'cleared', 'restored'})


class DraftsWriter:
    """
    Способ записи набора в черновики одного типа записей.

    Attributes:
        store: Хранилище черновиков.
        entity: Тип записи в схеме черновиков (``'patient'``…).
        key_field: Поле-ключ.
        parent_field: Поле-ссылка на родителя (из схемы черновиков; у корня — ``None``).

    Пример:
        >>> DraftsWriter(store, 'photo').parent_field
        'appointment_id'
    """

    def __init__(self, store: DraftStore, entity: str, *, key_field: str = 'id') -> None:
        """
        Args:
            store: Хранилище черновиков (общее для экранов — D1 черновиков).
            entity: Тип записи.
            key_field: Поле-ключ.

        Raises:
            Exception: Тип не описан в схеме черновиков (ошибка схемы).

        Пример:
            >>> DraftsWriter(store, 'patient')
            <DraftsWriter patient>
        """
        self.store = store
        self.entity = entity
        self.key_field = key_field
        self.parent_field: Optional[str] = store.schema.parent_field(entity)
        store.schema.get(entity)                       # тип должен быть в схеме
        self._datasets: 'weakref.WeakSet[DataSet]' = weakref.WeakSet()
        self._stale: 'weakref.WeakSet[DataSet]' = weakref.WeakSet()
        self._own = 0
        store.subscribe(self._on_store)

    def __repr__(self) -> str:
        """
        Кратко.

        Returns:
            Строка.

        Пример:
            >>> writer
            <DraftsWriter appointment>
        """
        return f"<DraftsWriter {self.entity}>"

    # ------------------------------------------------------------------ подключение

    def attach(self, dataset: DataSet) -> DataSet:
        """
        Подключает набор: он будет перечитываться при изменениях черновиков извне.

        Args:
            dataset: Набор (его ``writer`` должен быть этим мостом).

        Returns:
            Тот же набор.

        Raises:
            ValueError: У набора другой способ записи.

        Пример:
            >>> ds = writer.attach(DataSet(backend, writer=writer))
        """
        if dataset.writer is not self:
            raise ValueError("у набора другой способ записи — передайте writer=этот мост")
        self._datasets.add(dataset)
        dataset.subscribe(self._on_dataset)
        return dataset

    def detach(self, dataset: DataSet) -> None:
        """
        Отключает набор от извещений черновиков.

        Args:
            dataset: Набор.

        Returns:
            None

        Пример:
            >>> writer.detach(ds)
        """
        self._datasets.discard(dataset)
        self._stale.discard(dataset)
        dataset.unsubscribe(self._on_dataset)

    def close(self) -> None:
        """
        Отписывается от хранилища (мост больше не нужен).

        Returns:
            None

        Пример:
            >>> writer.close()
        """
        self.store.unsubscribe(self._on_store)
        for dataset in list(self._datasets):
            self.detach(dataset)

    @contextlib.contextmanager
    def _mine(self) -> Iterator[None]:
        """
        Пометка «это изменение сделал сам набор» (его строку перечитывать не нужно).

        Returns:
            Контекст.

        Пример:
            >>> with writer._mine(): store.modify(...)
        """
        self._own += 1
        try:
            yield
        finally:
            self._own -= 1

    def _parent(self, row: Mapping[str, Any]) -> Any:
        """
        Родитель строки для черновиков (нет поля-ссылки или значения — ``MISSING``).

        Args:
            row: Строка.

        Returns:
            Id родителя или ``MISSING``.

        Пример:
            >>> writer._parent({'patient_id': 5})
            5
        """
        if not self.parent_field:
            return MISSING
        value = row.get(self.parent_field)
        return MISSING if value is None else value

    # ------------------------------------------------------------------ DataWriter

    def insert(self, dataset: DataSet, values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Новая запись — черновик с временным id (< 0).

        Args:
            dataset: Набор.
            values: Значения.

        Returns:
            Строка с временным id.

        Пример:
            >>> writer.insert(ds, {'patient_id': 5, 'date': date(2026, 10, 18)})['id']
            -1
        """
        data = {k: v for k, v in values.items() if k != self.key_field}
        with self._mine():
            temp_id = self.store.create(self.entity, data, parent_id=self._parent(data))
        return dict(data, **{self.key_field: temp_id})

    def update(self, dataset: DataSet, key: Hashable, changes: Mapping[str, Any],
               row: Mapping[str, Any], original: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Правка — черновик (вернули исходное — черновик поля исчезает).

        Args:
            dataset: Набор.
            key: Ключ.
            changes: Изменения.
            row: Строка после правки.
            original: Строка до правки (исходные значения для черновика).

        Returns:
            Строка для показа.

        Пример:
            >>> writer.update(ds, 12, {'cost': 500}, row, {'cost': 400})
        """
        draft = self.store.get(self.entity, key)
        base = None if draft is not None and draft.is_new else {k: original.get(k) for k in changes}
        with self._mine():
            self.store.modify(self.entity, key, dict(changes), original=base,
                              parent_id=self._parent(row))
        return dict(row)

    def delete(self, dataset: DataSet, key: Hashable, row: Mapping[str, Any]) -> None:
        """
        Удаление — пометка в черновиках (новая запись — просто убирается).

        Args:
            dataset: Набор.
            key: Ключ.
            row: Строка.

        Returns:
            None

        Пример:
            >>> writer.delete(ds, 12, row)
        """
        with self._mine():
            self.store.delete(self.entity, key, parent_id=self._parent(row))

    # ------------------------------------------------------------------ RowOverlay

    def _parent_condition(self, query: Query) -> Any:
        """
        Родитель из условия связи запроса (``parent_field = значение``).

        Args:
            query: Запрос.

        Returns:
            Id родителя или ``MISSING`` (условия нет — все новые записи типа).

        Пример:
            >>> writer._parent_condition(Query(conditions=(Condition('patient_id', Op.EQ, 5),)))
            5
        """
        for condition in query.conditions:
            if condition.field == self.parent_field and condition.op is Op.EQ:
                return condition.value
        return MISSING

    def overlay(self, dataset: DataSet, rows: List[Dict[str, Any]], query: Query,
                first: bool) -> List[Dict[str, Any]]:
        """
        Строки из БД + черновики; в первое окно — новые записи (того же родителя, под
        условия запроса).

        Args:
            dataset: Набор.
            rows: Строки окна из БД.
            query: Запрос.
            first: Первое окно.

        Returns:
            Строки для показа.

        Пример:
            >>> writer.overlay(ds, [{'id': 12, 'cost': 400}], Query(), True)
            [{'patient_id': 5, 'id': -1}, {'id': 12, 'cost': 500}]
        """
        result = []
        for row in rows:
            key = row.get(self.key_field)
            parent = self._parent(row)
            if parent is not MISSING and key is not None:
                # для значков предков; «своё» — событие 'linked' не должно перечитывать
                # набор, который сейчас как раз читается (повторный вход в чтение)
                with self._mine():
                    self.store.remember_parent(self.entity, key, parent)
            result.append(self.store.effective(self.entity, key, row)
                          if self.store.has_draft(self.entity, key) else row)
        if first:
            new_rows = []
            for draft in self.store.drafts(self.entity, parent_id=self._parent_condition(query),
                                           new_only=True):
                if draft.deleted:
                    continue
                row = dict(draft.data, **{self.key_field: draft.id})
                if self.parent_field and draft.parent_id is not None:
                    row.setdefault(self.parent_field, draft.parent_id)
                if all(c.matches(row) for c in query.conditions):
                    new_rows.append(row)
            result = new_rows + result
        return result

    def row_status(self, dataset: DataSet, key: Hashable) -> Optional[str]:
        """
        Состояние строки: ``new`` / ``modified`` / ``deleted`` / ``child`` / ``None``.

        Args:
            dataset: Набор.
            key: Ключ.

        Returns:
            Состояние.

        Пример:
            >>> writer.row_status(ds, -1)
            'new'
        """
        draft = self.store.get(self.entity, key)
        if draft is not None:
            if draft.deleted:
                return 'deleted'
            return 'new' if draft.is_new else 'modified'
        return 'child' if self.store.status(self.entity, key) else None

    # ------------------------------------------------------------------ извещения

    def _refresh(self, dataset: DataSet) -> None:
        """
        Перечитывает набор (в правке — после неё).

        Args:
            dataset: Набор.

        Returns:
            None

        Пример:
            >>> writer._refresh(ds)
        """
        if not dataset.active:
            return
        if dataset.state is not State.BROWSE:
            self._stale.add(dataset)
            return
        self._stale.discard(dataset)
        dataset.refresh()

    def _on_store(self, event: DraftEvent) -> None:
        """
        Событие черновиков → перечитать наборы этого типа или перерисовать значки.

        Args:
            event: Событие хранилища.

        Returns:
            None

        Пример:
            >>> writer._on_store(DraftEvent('restored', None, ()))
        """
        mine = [node[1] for node in (event.affected or ()) if node and node[0] == self.entity]
        own_node = event.node is not None and event.node[0] == self.entity
        if event.kind in _GLOBAL_KINDS or (own_node and not self._own):
            for dataset in list(self._datasets):
                self._refresh(dataset)
            return
        if mine:                                           # значки предков / своей строки
            for dataset in list(self._datasets):
                dataset.touch(mine)

    def _on_dataset(self, event: DataEvent) -> None:
        """
        Набор вышел из правки — перечитать, если черновики менялись, пока он правился.

        Args:
            event: Событие набора.

        Returns:
            None

        Пример:
            >>> writer._on_dataset(DataEvent(EventKind.STATE_CHANGED, ds, new=State.BROWSE))
        """
        if (event.kind is EventKind.STATE_CHANGED and event.new is State.BROWSE
                and event.dataset in self._stale):
            self._refresh(event.dataset)
