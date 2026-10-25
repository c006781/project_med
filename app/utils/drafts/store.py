# app/utils/drafts/store.py

"""
Хранилище черновиков: несохранённые изменения записей, связанных деревом.

Главное отличие от старого ``DraftRegistry`` (app/draft/IMPLEMENTATION.md §3):
    * каждый черновик сам знает родителя (``parent_id``), тип родителя — из схемы:
      дерево не зависит от строк, загруженных в таблицы (D3), типы не смешиваются (D5);
    * «есть изменения у себя / в ветке» ВЫЧИСЛЯЕТСЯ по индексу родитель → дети,
      счётчиков ``±1`` нет — нечему расходиться (D4, D6, D11);
    * одно хранилище на всё приложение — изменения со всех экранов сохраняются вместе (D1).

Хранилище не знает ни про Qt, ни про БД: интерфейс подписывается на события
(``subscribe``), сохранение — ``plan.build_plan`` + ``executor.execute_plan``.

Не потокобезопасно: рассчитано на один поток (поток интерфейса).

Пример:
    >>> store = DraftStore(schema)
    >>> photo_id = store.create('photo', parent_id=12, data={'path': 'a.jpg'})
    >>> store.modify('appointment', 12, {'cost': 500}, original={'cost': 400}, parent_id=1)
    >>> store.status('patient', 1)          # изменения только у потомков
    'child'
"""

from __future__ import annotations

import contextlib
import functools
import itertools
import logging
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, Hashable, Iterable, Iterator, List, Mapping, Optional, Set, Tuple,
)

from ._model import MISSING, Draft, DraftEvent, NodeKey
from .schema import TreeSchema
from .scope import SaveScope, select_nodes

_log = logging.getLogger(__name__)

# Подписчик на события хранилища
Listener = Callable[[DraftEvent], None]
# Определитель родителя записи без черновика: (тип, id) -> id родителя или None
ParentResolver = Callable[[str, Hashable], Optional[Hashable]]


def negative_ids(start: int = -1) -> Callable[[], int]:
    """
    Генератор временных id новых записей: -1, -2, -3 …

    Отрицательные — не пересекаются с id из БД (автоинкремент > 0); так же было в
    старой системе (``temp_id < 0``).

    Args:
        start: Первый id.

    Returns:
        Функция без аргументов, возвращающая следующий id.

    Пример:
        >>> next_id = negative_ids()
        >>> next_id(), next_id()
        (-1, -2)
    """
    counter = itertools.count(start, -1)
    return lambda: next(counter)


def _undoable(method: Callable[..., Any]) -> Callable[..., Any]:
    """
    Делает публичную операцию хранилища одним шагом истории отмены (undo).

    Вложенные вызовы (операция внутри ``batch`` или другой операции) — тот же шаг.

    Args:
        method: Метод ``DraftStore``.

    Returns:
        Обёртка.

    Пример:
        >>> class DraftStore:
        ...     @_undoable
        ...     def modify(self, ...): ...
    """

    @functools.wraps(method)
    def wrapper(self: 'DraftStore', *args: Any, **kwargs: Any) -> Any:
        """
        Выполняет операцию как шаг истории.

        Args:
            self: Хранилище.
            *args: Аргументы операции.
            **kwargs: Именованные аргументы.

        Returns:
            Результат операции.

        Пример:
            >>> store.modify('photo', 3, {'a': 1})
        """
        with self._undo_step():
            return method(self, *args, **kwargs)

    return wrapper


@dataclass
class _Record:
    """
    Изменяемая внутренняя запись черновика (наружу — неизменяемый ``Draft``).

    Пример:
        >>> _Record('photo', 3).snapshot().key
        ('photo', 3)
    """

    entity: str
    id: Hashable
    is_new: bool = False
    deleted: bool = False
    data: Dict[str, Any] = field(default_factory=dict)
    original: Dict[str, Any] = field(default_factory=dict)
    order: int = 0

    @property
    def has_own_changes(self) -> bool:
        """
        Есть ли что сохранять.

        Returns:
            ``True``, если запись новая, удалена или изменены поля.

        Пример:
            >>> _Record('photo', 3).has_own_changes
            False
        """
        return self.is_new or self.deleted or bool(self.data)

    def copy(self) -> '_Record':
        """
        Независимая копия (для истории отмены).

        Returns:
            Копия записи.

        Пример:
            >>> _Record('photo', 3, data={'a': 1}).copy().data
            {'a': 1}
        """
        return _Record(self.entity, self.id, self.is_new, self.deleted, dict(self.data),
                       dict(self.original), self.order)

    def snapshot(self, parent_id: Optional[Hashable] = None) -> Draft:
        """
        Неизменяемая копия.

        Args:
            parent_id: Id родителя (хранится в индексе связей хранилища).

        Returns:
            ``Draft``.

        Пример:
            >>> _Record('photo', 3, data={'a': 1}).snapshot(12).parent_id
            12
        """
        return Draft(
            entity=self.entity, id=self.id, parent_id=parent_id, is_new=self.is_new,
            deleted=self.deleted, data=dict(self.data), original=dict(self.original),
            order=self.order,
        )


# Снимок для истории отмены: (черновики, связи узел -> id родителя)
_Snapshot = Tuple[Dict[NodeKey, _Record], Dict[NodeKey, Optional[Hashable]]]


class DraftStore:
    """
    Черновики записей дерева + связи «ребёнок → родитель» + события.

    Связи известны хранилищу из трёх источников:
        1. черновики (``create``/``modify``/``delete`` с ``parent_id`` или полем
           внешнего ключа в данных);
        2. ``remember_parent`` — интерфейс сообщает родителя записи БЕЗ черновика
           (например, у приёма 12 пациент 1), чтобы изменение фото подняло значок до
           пациента;
        3. ``parent_resolver`` — функция, которую хранилище само спрашивает о
           неизвестном родителе (например, запрос в БД); ответ кешируется.

    Пример:
        >>> store = DraftStore(schema, parent_resolver=lambda t, i: db_parent(t, i))
    """

    def __init__(
        self,
        schema: TreeSchema,
        parent_resolver: Optional[ParentResolver] = None,
        temp_id_factory: Optional[Callable[[], Hashable]] = None,
        history_limit: int = 100,
    ) -> None:
        """
        Создаёт пустое хранилище.

        Args:
            schema: Описание дерева типов.
            parent_resolver: Определитель родителя записи без черновика (необязательно).
            temp_id_factory: Генератор временных id новых записей; по умолчанию
                ``negative_ids()``.
            history_limit: Сколько шагов отмены (undo) помнить; 0 — история выключена.

        Пример:
            >>> DraftStore(TreeSchema([EntityType('patient')])).is_empty
            True
        """
        schema.validate()
        self.schema = schema
        self._resolver = parent_resolver
        self._next_temp_id = temp_id_factory or negative_ids()
        self._records: Dict[NodeKey, _Record] = {}
        # Связи: узел -> id родителя (None — родителя нет); только известные узлы
        self._parents: Dict[NodeKey, Optional[Hashable]] = {}
        self._children: Dict[NodeKey, Set[NodeKey]] = {}
        self._listeners: List[Listener] = []
        self._order = itertools.count(1)
        self._version = 0
        self._token = object()   # метка этого хранилища для планов (F2)
        self._batch_depth = 0
        self._pending: List[DraftEvent] = []
        # История отмены: снимки (черновики, связи) ДО каждого шага
        self.history_limit = max(0, history_limit)
        self._undo: List[_Snapshot] = []
        self._redo: List[_Snapshot] = []
        self._undo_depth = 0
        self._history_suspended = 0
        # R11 (финальный проход 2026-10-16): кеш значков. Таблица спрашивает статус строки
        # для КАЖДОЙ ячейки при каждой перерисовке, а он считается обходом потомков.
        # Сбрасывается при любом изменении черновиков (версия) или связей.
        self._links_version = 0
        # Q3 (финальный проход 2): изменения САМИХ черновиков (без 'linked') — по ним
        # считается шаг отмены; версия (_version) растёт и от связей (план устаревает).
        self._drafts_changes = 0
        self._status_cache: Dict[NodeKey, Optional[str]] = {}
        self._status_cache_key: Tuple[int, int] = (-1, -1)

    # ------------------------------------------------------------------
    # События
    # ------------------------------------------------------------------

    def subscribe(self, listener: Listener) -> None:
        """
        Подписывает на события (``DraftEvent``). Повторная подписка игнорируется.

        Ошибка в подписчике пишется в лог и не мешает остальным.

        Args:
            listener: Функция ``(event) -> None``.

        Returns:
            None

        Пример:
            >>> store.subscribe(lambda e: print(e.kind, e.node))
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """
        Отписывает от событий (нет подписки — ничего не делает).

        Args:
            listener: Функция, переданная в ``subscribe``.

        Returns:
            None

        Пример:
            >>> store.unsubscribe(handler)
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    @contextlib.contextmanager
    def batch(self) -> Iterator['DraftStore']:
        """
        Группа изменений: события копятся и рассылаются в конце (одной пачкой, по
        порядку); вся группа — ОДИН шаг отмены (undo). Вложенные ``batch`` допустимы.
        При исключении внутри события всё равно рассылаются — изменения, сделанные до
        ошибки, уже в хранилище (и отменяются одним ``undo``).

        Returns:
            Контекстный менеджер (отдаёт само хранилище).

        Пример:
            >>> with store.batch():
            ...     store.modify('photo', 3, {'a': 1})
            ...     store.modify('photo', 4, {'a': 2})
        """
        self._batch_depth += 1
        try:
            with self._undo_step():
                yield self
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                pending, self._pending = self._pending, []
                for event in pending:
                    self._dispatch(event)

    def _emit(self, kind: str, node: Optional[NodeKey],
              extra_affected: Iterable[NodeKey] = (), old_id: Optional[Hashable] = None) -> None:
        """
        Создаёт событие (узел + его предки + ``extra_affected``) и рассылает/копит его.

        Args:
            kind: Вид события.
            node: Узел.
            extra_affected: Дополнительно затронутые узлы (старые предки при переносе).
            old_id: Прежний id (для ``'remapped'``).

        Returns:
            None

        Пример:
            >>> store._emit('modified', ('photo', 3))
        """
        self._version += 1
        if kind != 'linked':
            self._drafts_changes += 1
        affected: List[NodeKey] = []
        if node is not None:
            affected.append(node)
            affected.extend(self.ancestors(node))
        for extra in extra_affected:
            if extra not in affected:
                affected.append(extra)
        event = DraftEvent(kind, node, tuple(affected), old_id)
        if self._batch_depth:
            self._pending.append(event)
        else:
            self._dispatch(event)

    def _dispatch(self, event: DraftEvent) -> None:
        """
        Рассылает событие подписчикам; ошибки подписчиков — в лог.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> store._dispatch(DraftEvent('cleared', None))
        """
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                _log.exception("Ошибка подписчика черновиков на событие %s", event.kind)

    @property
    def version(self) -> int:
        """
        Номер версии: растёт при каждом изменении (по нему план узнаёт, что устарел).

        Returns:
            Целое число.

        Пример:
            >>> v = store.version; store.modify('photo', 3, {'a': 1}); store.version > v
            True
        """
        return self._version

    @property
    def token(self) -> object:
        """
        Уникальная метка хранилища: план помнит, по какому хранилищу построен (F2).

        Returns:
            Объект-метка.

        Пример:
            >>> DraftStore(schema).token is DraftStore(schema).token
            False
        """
        return self._token

    # ------------------------------------------------------------------
    # Связи дерева
    # ------------------------------------------------------------------

    def _check_type(self, entity: str) -> None:
        """
        Проверяет, что тип описан в схеме.

        Args:
            entity: Имя типа.

        Returns:
            None

        Raises:
            SchemaError: Тип не описан.

        Пример:
            >>> store._check_type('photo')
        """
        self.schema.get(entity)

    def _set_link(self, node: NodeKey, parent_id: Optional[Hashable]) -> Optional[NodeKey]:
        """
        Запоминает родителя узла, обновляя индекс детей.

        Args:
            node: Узел.
            parent_id: Id родителя или ``None``.

        Returns:
            Прежний узел-родитель (если был и сменился), иначе ``None``.

        Пример:
            >>> store._set_link(('photo', 3), 12)
        """
        entity = node[0]
        parent_type = self.schema.parent_type(entity)
        if parent_type is None:
            self._parents[node] = None
            return None
        old_parent = self._parent_key(node) if node in self._parents else None
        if node in self._parents and self._parents[node] == parent_id:
            return None
        if old_parent is not None:
            siblings = self._children.get(old_parent)
            if siblings is not None:
                siblings.discard(node)
                if not siblings:
                    del self._children[old_parent]
        self._parents[node] = parent_id
        if parent_id is not None:
            self._children.setdefault((parent_type, parent_id), set()).add(node)
        self._links_version += 1
        return old_parent

    def _parent_node(self, node: NodeKey, parent_id: Optional[Hashable]) -> Optional[NodeKey]:
        """
        Узел-родитель по id родителя (тип — из схемы).

        Args:
            node: Узел-ребёнок.
            parent_id: Id родителя.

        Returns:
            Узел-родитель или ``None``.

        Пример:
            >>> store._parent_node(('photo', 7), 12)
            ('appointment', 12)
        """
        parent_type = self.schema.parent_type(node[0])
        if parent_type is None or parent_id is None:
            return None
        return (parent_type, parent_id)

    def _parent_key(self, node: NodeKey) -> Optional[NodeKey]:
        """
        Родитель по уже известной связи (без обращения к ``parent_resolver``).

        Args:
            node: Узел.

        Returns:
            Узел-родитель или ``None``.

        Пример:
            >>> store._parent_key(('photo', 3))
            ('appointment', 12)
        """
        parent_type = self.schema.parent_type(node[0])
        parent_id = self._parents.get(node)
        if parent_type is None or parent_id is None:
            return None
        return (parent_type, parent_id)

    def remember_parent(self, entity: str, entity_id: Hashable, parent_id: Optional[Hashable]) -> None:
        """
        Сообщает родителя записи (без черновика) — чтобы изменения потомков
        поднимались до неё и выше.

        Интерфейс вызывает при загрузке строк: «приём 12 принадлежит пациенту 1».
        Черновик не создаётся. Если у записи или её потомков есть черновики и связь
        новая/другая — событие ``'linked'`` (значки предков поменялись); иначе событий нет.

        Args:
            entity: Тип записи.
            entity_id: Id записи.
            parent_id: Id родителя или ``None``.

        Returns:
            None

        Пример:
            >>> store.remember_parent('appointment', 12, 1)
        """
        self._check_type(entity)
        # self._set_link((entity, entity_id), parent_id)
        # ↑ до R4 (финальный проход 2026-10-16): связь менялась молча — если у записи или
        #   её потомков есть черновики, значки новых предков не обновлялись (строки
        #   приёмов загрузились ПОСЛЕ правки фото — пациент без значка).
        node = (entity, entity_id)
        # L1 (2026-10-18): черновик сам меняет связь с родителем (запись перенесена) —
        # родителя решает черновик, а «сведения» снаружи (строка из БД со СТАРЫМ родителем)
        # её не затирают. Раньше затирали: при удалении старого родителя перенесённая
        # запись считалась его потомком и удалялась вместе с ним.
        fk = self.schema.parent_field(entity)
        record = self._records.get(node)
        if fk and record is not None and fk in record.data:
            return
        known = node in self._parents
        if known and self._parents[node] == parent_id:
            return
        old_ancestors = self.ancestors(node) if known else []
        self._set_link(node, parent_id)
        if node in self._records or self.has_descendant_changes(entity, entity_id):
            self._emit('linked', node, old_ancestors)

    def parent_of(self, entity: str, entity_id: Hashable) -> Optional[NodeKey]:
        """
        Родитель записи: из известных связей, иначе — у ``parent_resolver`` (с кешем).

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            Узел-родитель; ``None`` — корень или родитель неизвестен.

        Пример:
            >>> store.parent_of('photo', 3)
            ('appointment', 12)
        """
        node = (entity, entity_id)
        if self.schema.parent_type(entity) is None:
            return None
        if node not in self._parents and self._resolver is not None:
            try:
                resolved = self._resolver(entity, entity_id)
            except Exception:
                _log.exception("parent_resolver не определил родителя %s", node)
                return None
            self._set_link(node, resolved)
        return self._parent_key(node)

    def ancestors(self, node: NodeKey) -> List[NodeKey]:
        """
        Предки узла снизу вверх (родитель, дед …), насколько они известны.

        Защищено от циклов в данных (каждый узел — не больше одного раза).

        Args:
            node: Узел.

        Returns:
            Список предков.

        Пример:
            >>> store.ancestors(('photo', 3))
            [('appointment', 12), ('patient', 1)]
        """
        result: List[NodeKey] = []
        seen = {node}
        current = self.parent_of(*node)
        while current is not None and current not in seen:
            result.append(current)
            seen.add(current)
            current = self.parent_of(*current)
        return result

    def children(self, node: NodeKey) -> Set[NodeKey]:
        """
        Известные дети узла (с черновиками или сообщённые через ``remember_parent``).

        Args:
            node: Узел.

        Returns:
            Множество (копия).

        Пример:
            >>> store.children(('appointment', 12))
            {('photo', 3)}
        """
        return set(self._children.get(node, ()))

    def descendants(self, node: NodeKey) -> Set[NodeKey]:
        """
        Все известные потомки узла.

        Args:
            node: Узел.

        Returns:
            Множество (без самого узла).

        Пример:
            >>> store.descendants(('patient', 1))
            {('appointment', 12), ('photo', 3)}
        """
        result: Set[NodeKey] = set()
        stack = list(self._children.get(node, ()))
        while stack:
            child = stack.pop()
            if child in result or child == node:
                continue
            result.add(child)
            stack.extend(self._children.get(child, ()))
        return result

    def _ensure_ancestors(self, node: NodeKey) -> None:
        """
        Подтягивает цепочку предков (через ``parent_resolver``), чтобы индекс детей был
        полным: тогда «потомки пациента» включают изменённое фото.

        Args:
            node: Узел.

        Returns:
            None

        Пример:
            >>> store._ensure_ancestors(('photo', 3))
        """
        self.ancestors(node)

    # ------------------------------------------------------------------
    # Изменение черновиков
    # ------------------------------------------------------------------

    def _new_record(self, entity: str, entity_id: Hashable, is_new: bool) -> _Record:
        """
        Создаёт и регистрирует запись черновика.

        Args:
            entity: Тип.
            entity_id: Id.
            is_new: Новая запись.

        Returns:
            Запись.

        Пример:
            >>> store._new_record('photo', 3, False)
        """
        record = _Record(entity, entity_id, is_new=is_new, order=next(self._order))
        self._records[(entity, entity_id)] = record
        return record

    def _apply_parent(self, record: _Record, parent_id: Any) -> Optional[NodeKey]:
        """
        Запоминает родителя записи по сведениям вызывающего (``parent_id`` в ``modify`` /
        ``delete`` — не изменение, а «что известно о дереве»).

        Если черновик сам задаёт родителя (поле внешнего ключа есть в ``data``: перенос
        существующей записи или новая запись), сведения не применяются — родителя решает
        черновик (как ``remember_parent``, L1; DR2).

        Args:
            record: Запись.
            parent_id: Id родителя, ``None`` или ``MISSING`` (не менять).

        Returns:
            Прежний родитель, если сменился.

        Пример:
            >>> store._apply_parent(record, 12)
        """
        if parent_id is MISSING:
            return None
        # DR2 (2026-10-25): таблица старого родителя передаёт родителя из строки БД при
        # правке другого поля перенесённой записи — раньше это возвращало связь к старому
        # родителю (значки не у того приёма; удаление старого уносило перенесённую запись).
        fk = self.schema.parent_field(record.entity)
        if fk and fk in record.data:
            return None
        return self._set_link((record.entity, record.id), parent_id)

    @_undoable
    def create(
        self,
        entity: str,
        data: Optional[Mapping[str, Any]] = None,
        parent_id: Any = MISSING,
        temp_id: Optional[Hashable] = None,
    ) -> Hashable:
        """
        Новая запись (ещё нет в БД).

        Родитель — ``parent_id`` или поле внешнего ключа в ``data``; поле внешнего ключа
        в данных выставляется равным родителю (интерфейс видит согласованные данные).

        Args:
            entity: Тип.
            data: Поля записи.
            parent_id: Id родителя (может быть временным id нового родителя).
            temp_id: Свой временный id; по умолчанию — из ``temp_id_factory``.

        Returns:
            Временный id новой записи.

        Raises:
            SchemaError: Тип не описан.
            ValueError: Нет родителя у типа с обязательным родителем; id уже занят.

        Пример:
            >>> store.create('photo', {'path': 'a.jpg'}, parent_id=12)
            -1
        """
        entity_type = self.schema.get(entity)
        values = dict(data or {})
        fk = entity_type.parent_field
        if parent_id is MISSING:
            parent_id = values.get(fk) if fk else None
        if entity_type.parent is not None and parent_id is None and entity_type.parent_required:
            raise ValueError(f"новой записи '{entity}' нужен родитель ({entity_type.parent})")
        new_id = self._next_temp_id() if temp_id is None else temp_id
        node = (entity, new_id)
        if node in self._records:
            raise ValueError(f"черновик {node} уже есть")
        if fk:
            values[fk] = parent_id
        record = self._new_record(entity, new_id, is_new=True)
        record.data = values
        self._set_link(node, parent_id)
        self._ensure_ancestors(node)
        self._emit('created', node)
        return new_id

    @_undoable
    def modify(
        self,
        entity: str,
        entity_id: Hashable,
        changes: Mapping[str, Any],
        original: Optional[Mapping[str, Any]] = None,
        parent_id: Any = MISSING,
    ) -> None:
        """
        Изменение полей записи (новой или существующей); повторные изменения
        дополняют черновик (требование 3).

        Для существующей записи: если передан ``original`` (исходные значения из БД),
        поле, вернувшееся к исходному значению, убирается из черновика; черновик без
        изменений удаляется целиком. Изменение поля внешнего ключа переносит запись к
        другому родителю.

        Args:
            entity: Тип.
            entity_id: Id.
            changes: Новые значения полей.
            original: Исходные значения (запоминаются при первом изменении поля).
            parent_id: Известный родитель записи (не изменение, а сведения о дереве).

        Returns:
            None

        Пример:
            >>> store.modify('appointment', 12, {'cost': 500}, original={'cost': 400}, parent_id=1)
            >>> store.modify('appointment', 12, {'cost': 400})   # вернули — черновика нет
            >>> store.has_draft('appointment', 12)
            False
        """
        entity_type = self.schema.get(entity)
        node = (entity, entity_id)
        if not changes:
            # R6 (финальный проход 2026-10-16): пустое изменение раньше рассылало событие,
            #   делало план устаревшим и добавляло пустой шаг отмены. Теперь — только
            #   сведения о родителе.
            if parent_id is not MISSING:
                self.remember_parent(entity, entity_id, parent_id)
            return
        record = self._records.get(node)
        created = record is None
        if record is None:
            record = self._new_record(entity, entity_id, is_new=False)
        self._apply_parent(record, parent_id)
        fk = entity_type.parent_field
        old_parents: List[NodeKey] = []
        for name, value in changes.items():
            if record.is_new:
                record.data[name] = value
            else:
                if original is not None and name in original and name not in record.original:
                    record.original[name] = original[name]
                if name in record.original and record.original[name] == value:
                    record.data.pop(name, None)
                else:
                    record.data[name] = value
            if fk and name == fk:
                previous = self._set_link(node, value)
                if previous is not None:
                    old_parents.append(previous)
                    old_parents.extend(self.ancestors(previous))
        self._ensure_ancestors(node)
        if not record.has_own_changes:
            del self._records[node]
            if not created:
                self._emit('discarded', node, old_parents)
            return
        self._emit('reparented' if old_parents else 'modified', node, old_parents)

    @_undoable
    def delete(self, entity: str, entity_id: Hashable, parent_id: Any = MISSING) -> None:
        """
        Помечает запись на удаление (новую или существующую). Изменения записи и её
        потомков сохраняются — ``undelete`` их вернёт. Что делать с веткой при
        сохранении, решает политика удаления (``policies``).

        Args:
            entity: Тип.
            entity_id: Id.
            parent_id: Известный родитель записи.

        Returns:
            None

        Пример:
            >>> store.delete('appointment', 12, parent_id=1)
        """
        self._check_type(entity)
        node = (entity, entity_id)
        record = self._records.get(node) or self._new_record(entity, entity_id, is_new=False)
        self._apply_parent(record, parent_id)
        self._ensure_ancestors(node)
        if record.deleted:
            return
        record.deleted = True
        self._emit('deleted', node)

    @_undoable
    def undelete(self, entity: str, entity_id: Hashable) -> None:
        """
        Снимает пометку удаления; изменения записи возвращаются. Запись без
        изменений — черновик удаляется.

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            None

        Пример:
            >>> store.undelete('appointment', 12)
        """
        node = (entity, entity_id)
        record = self._records.get(node)
        if record is None or not record.deleted:
            return
        record.deleted = False
        if not record.has_own_changes:
            del self._records[node]
        self._emit('undeleted', node)

    @_undoable
    def discard(
        self,
        targets: Optional[Iterable[NodeKey]] = None,
        scope: SaveScope = SaveScope.SELF,
    ) -> Set[NodeKey]:
        """
        Отменяет черновики в объёме (цель × направления).

        Отмена НОВОЙ записи отменяет и черновики её потомков: их родитель так и не
        появится в БД.

        Args:
            targets: Узлы цели; ``None`` — все черновики.
            scope: Направления.

        Returns:
            Отменённые узлы.

        Пример:
            >>> store.discard([('appointment', 12)], SaveScope.BRANCH)
            {('appointment', 12), ('photo', -1)}
        """
        selected = select_nodes(self, targets, scope)
        # for node in list(selected):
        #     record = self._records.get(node)
        #     if record is not None and record.is_new:
        #         selected.update(n for n in self.descendants(node) if n in self._records)
        # ↑ до N2 (2026-10-16): существующая запись, перенесённая в отменяемую НОВУЮ,
        #   отменялась целиком (со всеми своими правками). Теперь у неё откатывается только
        #   перенос (поле внешнего ключа) — если исходный родитель известен.
        moved_back: List[NodeKey] = []
        for node in list(selected):
            record = self._records.get(node)
            if record is None or not record.is_new:
                continue
            for child in self.descendants(node):
                child_record = self._records.get(child)
                if child_record is None or child in selected:
                    continue
                if child_record.is_new:
                    selected.add(child)               # родитель так и не появится
                    continue
                parent = self._parent_key(child)
                parent_record = self._records.get(parent) if parent is not None else None
                if parent_record is None or not parent_record.is_new:
                    continue                          # глубже — уйдёт вместе с родителем
                if self._can_move_back(child):
                    moved_back.append(child)          # вернуть к исходному родителю
                else:
                    selected.add(child)               # исходный родитель неизвестен
        with self.batch():
            for child in moved_back:
                self._move_back(child)
            for node in sorted(selected, key=lambda n: self._records[n].order):
                # предки — ДО удаления: у новой записи _drop убирает и связь, и без этого
                # событие не сообщило бы родителям, что их значок изменился
                ancestors = self.ancestors(node)
                self._drop(node)
                self._emit('discarded', node, ancestors)
        return selected

    def _can_move_back(self, node: NodeKey) -> bool:
        """
        Можно ли вернуть существующую запись к исходному родителю: поле внешнего ключа
        изменено и его исходное значение известно (N2).

        Args:
            node: Узел.

        Returns:
            ``True``, если можно.

        Пример:
            >>> store._can_move_back(('photo', 7))
            True
        """
        record = self._records.get(node)
        fk = self.schema.parent_field(node[0])
        return (record is not None and not record.is_new and fk is not None
                and fk in record.data and fk in record.original)

    def _move_back(self, node: NodeKey) -> None:
        """
        Откатывает перенос существующей записи (поле внешнего ключа → исходное
        значение); черновик без других изменений удаляется (N2).

        Args:
            node: Узел.

        Returns:
            None

        Пример:
            >>> store._move_back(('photo', 7))
        """
        record = self._records[node]
        fk = self.schema.parent_field(node[0])
        old_parents = self.ancestors(node)
        record.data.pop(fk, None)
        self._set_link(node, record.original[fk])
        if not record.has_own_changes:
            del self._records[node]
            self._emit('discarded', node, old_parents)
        else:
            self._emit('reparented', node, old_parents)

    def _drop(self, node: NodeKey) -> None:
        """
        Удаляет черновик узла; у новой записи — и её связь (записи больше нет).

        Args:
            node: Узел.

        Returns:
            None

        Пример:
            >>> store._drop(('photo', -1))
        """
        record = self._records.pop(node, None)
        if record is not None and record.is_new:
            self._forget(node)

    def _forget(self, node: NodeKey) -> None:
        """
        Убирает узел из индекса связей.

        Args:
            node: Узел.

        Returns:
            None

        Пример:
            >>> store._forget(('photo', -1))
        """
        parent = self._parent_key(node)
        if parent is not None and parent in self._children:
            self._children[parent].discard(node)
            if not self._children[parent]:
                del self._children[parent]
        self._parents.pop(node, None)
        self._links_version += 1

    @_undoable
    def clear(self) -> None:
        """
        Удаляет все черновики и связи.

        Returns:
            None

        Пример:
            >>> store.clear(); store.is_empty
            True
        """
        self._records.clear()
        self._parents.clear()
        self._children.clear()
        self._links_version += 1
        self._emit('cleared', None)

    @_undoable
    def revert_field(self, entity: str, entity_id: Hashable, *fields: str) -> None:
        """
        Отменяет изменение отдельных полей записи (остальные правки остаются).

        Существующая запись: поле убирается из черновика; поле внешнего ключа — запись
        возвращается к исходному родителю (нужно известное исходное значение). Новая
        запись: поле убирается из данных (родителя новой записи так не отменить —
        отмените запись). Черновик без изменений удаляется.

        Args:
            entity: Тип.
            entity_id: Id.
            *fields: Имена полей.

        Returns:
            None

        Raises:
            ValueError: Отмена поля внешнего ключа без известного исходного значения
                или у новой записи.

        Пример:
            >>> store.revert_field('appointment', 12, 'cost')
        """
        node = (entity, entity_id)
        record = self._records.get(node)
        if record is None:
            return
        fk = self.schema.parent_field(entity)
        if fk in fields and fk in record.data:
            if record.is_new:
                raise ValueError("у новой записи родитель не отменяется — отмените саму запись")
            if fk not in record.original:
                raise ValueError(f"исходное значение '{fk}' неизвестно — перенос не отменить")
        old_parents: List[NodeKey] = []
        if not any(name in record.data for name in fields):
            return                      # R6: нечего отменять — ни события, ни шага истории
        for name in fields:
            if name not in record.data:
                continue
            record.data.pop(name)
            if name == fk:
                old_parents = self.ancestors(node)
                self._set_link(node, record.original[fk])
        if not record.has_own_changes:
            del self._records[node]
            self._emit('discarded', node, old_parents)
        else:
            self._emit('reparented' if old_parents else 'modified', node, old_parents)

    # ------------------------------------------------------------------
    # История отмены (undo / redo)
    # ------------------------------------------------------------------

    def _snapshot(self) -> '_Snapshot':
        """
        Снимок черновиков и связей (копии).

        Returns:
            ``(записи, связи)``.

        Пример:
            >>> records, parents = store._snapshot()
        """
        return ({k: r.copy() for k, r in self._records.items()}, dict(self._parents))

    @contextlib.contextmanager
    def _undo_step(self) -> Iterator[None]:
        """
        Шаг истории: снимок ДО внешней операции; если она что-то изменила (версия
        выросла) — снимок в стек отмены, стек повтора очищается.

        Returns:
            Контекстный менеджер.

        Пример:
            >>> with store._undo_step(): store._records.clear()
        """
        outer = self._undo_depth == 0 and not self._history_suspended and self.history_limit > 0
        snapshot = self._snapshot() if outer else None
        # version = self._version
        # ↑ до Q3: шаг считался по общей версии — 'linked' (загрузка строк) давал пустой
        #   шаг отмены. Теперь — только изменения самих черновиков.
        changes = self._drafts_changes
        self._undo_depth += 1
        try:
            yield
        finally:
            self._undo_depth -= 1
            if outer and self._drafts_changes != changes:
                self._undo.append(snapshot)
                del self._undo[:-self.history_limit]
                self._redo.clear()

    @property
    def can_undo(self) -> bool:
        """
        Есть что отменить.

        Returns:
            ``True``, если есть шаг.

        Пример:
            >>> store.can_undo
            False
        """
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        """
        Есть что повторить.

        Returns:
            ``True``, если есть шаг.

        Пример:
            >>> store.can_redo
            False
        """
        return bool(self._redo)

    def undo(self) -> bool:
        """
        Отменяет последний шаг (операцию или ``batch``).

        Returns:
            ``True``, если было что отменять.

        Пример:
            >>> store.modify('photo', 3, {'a': 1}); store.undo(); store.has_draft('photo', 3)
            False
        """
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        """
        Повторяет отменённый шаг.

        Returns:
            ``True``, если было что повторять.

        Пример:
            >>> store.undo(); store.redo()
            True
        """
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        return True

    def clear_history(self) -> None:
        """
        Забывает историю отмены (например, после сохранения — делается автоматически).

        Returns:
            None

        Пример:
            >>> store.clear_history(); store.can_undo
            False
        """
        self._undo.clear()
        self._redo.clear()

    def _restore(self, snapshot: '_Snapshot') -> None:
        """
        Восстанавливает снимок; события ``'restored'`` по изменившимся узлам (с прежними
        и новыми предками — значки обновятся).

        Связи, узнанные позже снимка (``remember_parent``, ``parent_resolver``),
        сохраняются; связи новых записей, которых в снимке нет, забываются.

        Args:
            snapshot: ``(записи, связи)``.

        Returns:
            None

        Пример:
            >>> store._restore(store._snapshot())
        """
        records, parents = snapshot
        changed = [n for n in set(self._records) | set(records)
                   if self._records.get(n) != records.get(n)]
        old_ancestors = {n: self.ancestors(n) for n in changed}
        merged = {n: p for n, p in self._parents.items()
                  if not (n in self._records and self._records[n].is_new and n not in records)}
        merged.update(parents)
        # R7 (финальный проход 2026-10-16): связи, указывающие на НОВЫЕ записи, которых
        #   после восстановления нет, отбрасываются — иначе существующая запись, перенесённая
        #   в отменённую новую, осталась бы привязанной к несуществующему родителю.
        gone_new = {n for n, r in self._records.items() if r.is_new and n not in records}
        merged = {n: p for n, p in merged.items()
                  if n not in gone_new and self._parent_node(n, p) not in gone_new}
        self._records = {k: r.copy() for k, r in records.items()}
        self._parents = {}
        self._children = {}
        self._links_version += 1
        for node, parent_id in merged.items():
            self._set_link(node, parent_id)
        self._history_suspended += 1
        try:
            with self.batch():
                for node in sorted(changed, key=str):
                    self._emit('restored', node, old_ancestors[node])
        finally:
            self._history_suspended -= 1

    # ------------------------------------------------------------------
    # Чтение
    # ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """
        Нет ни одного черновика.

        Returns:
            ``True``, если пусто.

        Пример:
            >>> DraftStore(schema).is_empty
            True
        """
        return not self._records

    def has_draft(self, entity: str, entity_id: Hashable) -> bool:
        """
        Есть ли черновик у записи.

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            ``True``, если есть.

        Пример:
            >>> store.has_draft('photo', 3)
            True
        """
        return (entity, entity_id) in self._records

    def get(self, entity: str, entity_id: Hashable) -> Optional[Draft]:
        """
        Черновик записи (копия).

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            ``Draft`` или ``None``.

        Пример:
            >>> store.get('photo', 3).data
            {'path': 'b.jpg'}
        """
        node = (entity, entity_id)
        record = self._records.get(node)
        return record.snapshot(self._parents.get(node)) if record else None

    def drafted_nodes(self) -> List[NodeKey]:
        """
        Узлы с черновиками в порядке их появления.

        Returns:
            Список ключей.

        Пример:
            >>> store.drafted_nodes()
            [('appointment', 12), ('photo', -1)]
        """
        return [key for key, _ in sorted(self._records.items(), key=lambda kv: kv[1].order)]

    def drafts(
        self,
        entity: Optional[str] = None,
        parent_id: Any = MISSING,
        new_only: bool = False,
    ) -> List[Draft]:
        """
        Черновики (копии) с фильтрами, в порядке появления.

        Args:
            entity: Только этого типа.
            parent_id: Только с этим родителем.
            new_only: Только новые записи (для добавления строк в таблицу).

        Returns:
            Список ``Draft``.

        Пример:
            >>> [d.id for d in store.drafts('photo', parent_id=12, new_only=True)]
            [-1]
        """
        result = []
        for node in self.drafted_nodes():
            record = self._records[node]
            if entity is not None and record.entity != entity:
                continue
            if parent_id is not MISSING and self._parents.get(node) != parent_id:
                continue
            if new_only and not record.is_new:
                continue
            result.append(record.snapshot(self._parents.get(node)))
        return result

    def effective(self, entity: str, entity_id: Hashable,
                  base: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """
        Данные записи с учётом черновика: ``base`` (из БД) + изменения.

        Args:
            entity: Тип.
            entity_id: Id.
            base: Исходные данные записи.

        Returns:
            Новый словарь.

        Пример:
            >>> store.effective('appointment', 12, {'cost': 400, 'date': 'x'})
            {'cost': 500, 'date': 'x'}
        """
        result = dict(base or {})
        record = self._records.get((entity, entity_id))
        if record is not None:
            result.update(record.data)
        return result

    def counts(self) -> Dict[str, Dict[str, int]]:
        """
        Сводка черновиков по типам: сколько новых, изменённых, помеченных на удаление
        (для диалогов и строки состояния).

        Returns:
            ``{тип: {'new': n, 'modified': m, 'deleted': d}}`` — только типы с черновиками.

        Пример:
            >>> store.counts()
            {'appointment': {'new': 1, 'modified': 2, 'deleted': 0}}
        """
        result: Dict[str, Dict[str, int]] = {}
        for record in self._records.values():
            bucket = result.setdefault(record.entity, {'new': 0, 'modified': 0, 'deleted': 0})
            if record.deleted:
                bucket['deleted'] += 1
            elif record.is_new:
                bucket['new'] += 1
            else:
                bucket['modified'] += 1
        return result

    def has_descendant_changes(self, entity: str, entity_id: Hashable) -> bool:
        """
        Есть ли черновики у потомков записи.

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            ``True``, если есть.

        Пример:
            >>> store.has_descendant_changes('patient', 1)
            True
        """
        return any(node in self._records for node in self.descendants((entity, entity_id)))

    def status(self, entity: str, entity_id: Hashable) -> Optional[str]:
        """
        Значок строки: ``'own'`` — изменена сама, ``'child'`` — изменены потомки,
        ``'both'`` — и то и другое, ``None`` — изменений нет.

        Вычисляется каждый раз по индексу (счётчиков нет — нечему расходиться).

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            Статус или ``None``.

        Пример:
            >>> store.status('patient', 1)
            'child'
        """
        key = (self._version, self._links_version)
        if key != self._status_cache_key:
            self._status_cache = {}
            self._status_cache_key = key
        node = (entity, entity_id)
        if node in self._status_cache:
            return self._status_cache[node]
        own = node in self._records
        child = self.has_descendant_changes(entity, entity_id)
        if own and child:
            status = 'both'
        elif own:
            status = 'own'
        elif child:
            status = 'child'
        else:
            status = None
        self._status_cache[node] = status
        return status

    def has_changes(
        self,
        targets: Optional[Iterable[NodeKey]] = None,
        scope: SaveScope = SaveScope.BRANCH,
    ) -> bool:
        """
        Есть ли черновики в объёме.

        Args:
            targets: Узлы цели; ``None`` — всё хранилище.
            scope: Направления.

        Returns:
            ``True``, если есть.

        Пример:
            >>> store.has_changes([('patient', 1)])
            True
        """
        return bool(select_nodes(self, targets, scope))

    # ------------------------------------------------------------------
    # После сохранения
    # ------------------------------------------------------------------

    def _remap(self, entity: str, old_id: Hashable, new_id: Hashable) -> None:
        """
        Временный id сохранённой записи → настоящий: связи детей и поле внешнего ключа
        в их черновиках переписываются (D10 старой системы).

        Args:
            entity: Тип.
            old_id: Временный id.
            new_id: Id из БД.

        Returns:
            None

        Пример:
            >>> store._remap('appointment', -5, 55)
        """
        old_node, new_node = (entity, old_id), (entity, new_id)
        parent_id = self._parents.pop(old_node, None)
        parent = (self.schema.parent_type(entity), parent_id) if parent_id is not None else None
        if parent is not None and parent in self._children:
            self._children[parent].discard(old_node)
            self._children[parent].add(new_node)
        self._parents[new_node] = parent_id
        children = self._children.pop(old_node, set())
        if children:
            self._children[new_node] = children
        for child in children:
            self._parents[child] = new_id
            record = self._records.get(child)
            fk = self.schema.parent_field(child[0])
            if record is not None and fk and record.data.get(fk) == old_id:
                record.data[fk] = new_id
        record = self._records.pop(old_node, None)
        if record is not None:
            record.id = new_id
            self._records[new_node] = record
        # ссылки (не владение) других черновиков на эту запись — тоже на настоящий id
        # (2026-10-18: раньше заменялась только связь детей с родителем)
        for referrer_type, ref in self.schema.referrers(entity):
            for (other_entity, _), other in self._records.items():
                if other_entity == referrer_type and other.data.get(ref.field) == old_id:
                    other.data[ref.field] = new_id
        self._emit('remapped', new_node, old_id=old_id)

    def apply_saved(self, consumed: Iterable[NodeKey], id_map: Mapping[NodeKey, Hashable],
                    removed: Iterable[NodeKey] = ()) -> None:
        """
        Отражает успешное сохранение: черновики ``consumed`` удаляются, временные id
        созданных записей заменяются настоящими, удалённые из БД узлы забываются.

        Вызывается исполнителем плана (``executor``) только после успешной транзакции;
        свой исполнитель (другое хранилище данных) вызывает так же. История отмены
        очищается: вернуть отменой то, что уже записано в БД, нельзя.

        (До 2026-10-16 метод был закрытым ``_commit`` — исполнитель лез во внутренности
        хранилища; имя ``_commit`` оставлено как синоним.)

        Args:
            consumed: Узлы, чьи черновики сохранены (или отброшены как часть удалённой
                ветки).
            id_map: Временный ключ → настоящий id (для созданных).
            removed: Узлы, удалённые из БД (и их известные потомки забываются).

        Returns:
            None

        Пример:
            >>> store.apply_saved({('photo', -1)}, {('photo', -1): 77})
        """
        self._history_suspended += 1
        try:
            self._apply_saved(consumed, id_map, removed)
        finally:
            self._history_suspended -= 1
        self.clear_history()

    # Синоним прежнего закрытого имени (до 2026-10-16)
    _commit = apply_saved

    def _apply_saved(self, consumed: Iterable[NodeKey], id_map: Mapping[NodeKey, Hashable],
                     removed: Iterable[NodeKey]) -> None:
        """
        Тело ``apply_saved`` (без истории).

        Args:
            consumed: Сохранённые/поглощённые узлы.
            id_map: Временный ключ → настоящий id.
            removed: Удалённые из БД узлы.

        Returns:
            None

        Пример:
            >>> store._apply_saved({('photo', -1)}, {('photo', -1): 77}, ())
        """
        with self.batch():
            # for node in consumed:
            #     self._records.pop(node, None)
            #     self._emit('saved', node)
            # ↑ до 2026-10-25 (DR3): поглощённая НОВАЯ запись (удалённая до сохранения —
            #   в БД так и не появилась) оставляла связь в индексе: родитель «помнил»
            #   несуществующего ребёнка (children/descendants), к нему же оставались
            #   привязаны записи, перенесённые в неё.
            ghosts: Set[NodeKey] = set()
            for node in consumed:
                record = self._records.pop(node, None)
                if record is not None and record.is_new and node not in id_map:
                    ghosts.add(node)
                self._emit('saved', node)       # предки — по связям ДО забывания
            stale = [n for n, p in self._parents.items()
                     if n in ghosts or self._parent_node(n, p) in ghosts]
            for node in stale:
                self._forget(node)
            for (entity, old_id), new_id in id_map.items():
                self._remap(entity, old_id, new_id)
            for node in removed:
                for gone in [node, *self.descendants(node)]:
                    self._records.pop(gone, None)
                    self._forget(gone)
