# app/utils/drafts_qt/model.py

"""
Модель таблицы Qt поверх хранилища черновиков (``drafts.DraftStore``).

Строки — словари исходных данных (из БД) одной страницы + новые записи-черновики
текущего родителя. Показ — с учётом черновиков (``store.effective``), правка ячейки —
черновик (``store.modify`` с исходным значением: вернули как было — черновик исчезает),
цвет строки — по статусу (своё / у потомков / оба / удалена).

Модель сама подписана на хранилище: изменения из ЛЮБОГО места (другая таблица, другой
экран) сразу видны — значки предков обновляются, новые строки появляются, отменённые
исчезают. После сохранения в БД модель просит перечитать страницу (``reload_requested``).

Зависит только от PySide6 и пакета ``drafts`` (переносимость).

Пример:
    >>> columns = [Column('last_name', 'Фамилия'), Column('first_name', 'Имя')]
    >>> model = DraftTableModel(store, 'patient', columns)
    >>> model.set_rows([{'id': 1, 'last_name': 'Петров', 'first_name': 'Иван'}])
    >>> model.setData(model.index(0, 1), 'Пётр')
    True
    >>> store.status('patient', 1)
    'own'
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, List, Mapping, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont

try:  # пакеты лежат рядом в одном родительском пакете (как в этом проекте)
    from ..drafts import MISSING, DraftEvent, DraftStore, NodeKey, SaveScope
except ImportError:  # pragma: no cover — скопированы как отдельные пакеты верхнего уровня
    from drafts import MISSING, DraftEvent, DraftStore, NodeKey, SaveScope


@dataclass(frozen=True)
class Column:
    """
    Описание колонки.

    Attributes:
        field: Поле записи.
        title: Заголовок.
        editable: Можно править в таблице.
        to_text: Значение → текст для показа (по умолчанию ``str``, ``None`` → ``''``).
        from_edit: Значение из редактора → значение поля (по умолчанию как есть).
        width: Ширина колонки в пикселях (подсказка странице).

    Пример:
        >>> Column('cost', 'Стоимость', from_edit=int, to_text=lambda v: f'{v} ₽')
    """

    field: str
    title: str
    editable: bool = True
    to_text: Optional[Callable[[Any], str]] = None
    from_edit: Optional[Callable[[Any], Any]] = None
    width: Optional[int] = None

    def text(self, value: Any) -> str:
        """
        Текст ячейки.

        Args:
            value: Значение поля.

        Returns:
            Строка.

        Пример:
            >>> Column('a', 'A').text(None)
            ''
        """
        if self.to_text is not None:
            return self.to_text(value)
        return '' if value is None else str(value)


# Цвета строк по статусу: ключи 'own', 'child', 'both', 'deleted', 'new'
DEFAULT_COLORS: Dict[str, str] = {
    'own': '#fff4c2',      # изменена сама — жёлтый
    'child': '#e3f0ff',    # изменены потомки — голубой
    'both': '#ffe0b3',     # и то и другое — оранжевый
    'new': '#dff5e1',      # новая запись — зелёный
    'deleted': '#eeeeee',  # помечена на удаление — серый (+ зачёркнуто)
}

# Роль: ключ узла строки (entity, id)
NodeRole = Qt.UserRole + 1
# Роль: статус строки ('own'/'child'/'both'/None)
StatusRole = Qt.UserRole + 2


class DraftTableModel(QAbstractTableModel):
    """
    Таблица записей одного типа с черновиками.

    Сигналы:
        reload_requested: Данные в БД изменились (сохранение) — странице перечитать
            текущую страницу.
        row_id_changed(old_id, new_id): Новая запись сохранена — id строки сменился
            (страница может восстановить выделение).

    Пример:
        >>> model = DraftTableModel(store, 'photo', [Column('file_path', 'Файл')])
        >>> model.set_rows(rows_from_db, parent_id=12)
    """

    reload_requested = Signal()
    row_id_changed = Signal(object, object)

    def __init__(
        self,
        store: DraftStore,
        entity: str,
        columns: Sequence[Column],
        id_field: str = 'id',
        colors: Optional[Mapping[str, str]] = None,
        parent: Optional[Any] = None,
    ) -> None:
        """
        Args:
            store: Хранилище черновиков (общее для приложения).
            entity: Тип записей таблицы (из схемы хранилища).
            columns: Колонки.
            id_field: Поле id в строках.
            colors: Цвета строк по статусу (см. ``DEFAULT_COLORS``).
            parent: Родительский QObject.

        Пример:
            >>> DraftTableModel(store, 'patient', [Column('last_name', 'Фамилия')])
        """
        super().__init__(parent)
        store.schema.get(entity)
        self.store = store
        self.entity = entity
        self.columns: List[Column] = list(columns)
        self.id_field = id_field
        self.colors = {**DEFAULT_COLORS, **(colors or {})}
        self._fk = store.schema.parent_field(entity)
        self._rows: List[Dict[str, Any]] = []      # исходные данные; у новых — данные черновика
        self._new_ids: set = set()                  # id строк — новых записей (не из БД)
        self._parent_id: Any = MISSING              # родитель (контекст) таблицы
        self._reload_pending = False                # перечитывание уже запланировано
        store.subscribe(self._on_store_event)

    # ------------------------------------------------------------------
    # Данные страницы
    # ------------------------------------------------------------------

    def detach(self) -> None:
        """
        Отписывается от хранилища (перед удалением модели).

        Returns:
            None

        Пример:
            >>> model.detach()
        """
        self.store.unsubscribe(self._on_store_event)

    @property
    def parent_id(self) -> Any:
        """
        Родитель (контекст) таблицы: строки этой таблицы — его дети; новые строки
        создаются под ним. ``MISSING`` — без контекста (корневая таблица или «все»).

        Returns:
            Id родителя или ``MISSING``.

        Пример:
            >>> model.parent_id
            12
        """
        return self._parent_id

    def set_rows(self, rows: Sequence[Mapping[str, Any]], parent_id: Any = MISSING) -> None:
        """
        Задаёт строки страницы (из БД) и контекст родителя; добавляет новые записи-
        черновики этого родителя (для корневой таблицы — все новые записи типа).

        Родители загруженных строк сообщаются хранилищу (``remember_parent``) — значки
        предков поднимаются без запросов в БД.

        Args:
            rows: Строки (словари с полем id).
            parent_id: Родитель (контекст); ``MISSING`` — без контекста.

        Returns:
            None

        Пример:
            >>> model.set_rows([{'id': 7, 'appointment_id': 12}], parent_id=12)
        """
        self.beginResetModel()
        self._parent_id = parent_id
        self._rows = [dict(row) for row in rows]
        self._new_ids = set()
        known = {row.get(self.id_field) for row in self._rows}
        for row in self._rows:
            if self._fk and row.get(self._fk) is not None:
                self.store.remember_parent(self.entity, row[self.id_field], row[self._fk])
        for draft in self.store.drafts(self.entity, parent_id=parent_id, new_only=True):
            if draft.id not in known:
                self._rows.append({**draft.data, self.id_field: draft.id})
                self._new_ids.add(draft.id)
        self.endResetModel()

    def clear(self) -> None:
        """
        Пустая таблица (например, родитель не выбран).

        Returns:
            None

        Пример:
            >>> model.clear(); model.rowCount()
            0
        """
        self.beginResetModel()
        self._rows = []
        self._new_ids = set()
        self._parent_id = MISSING
        self.endResetModel()

    def row_id(self, row: int) -> Hashable:
        """
        Id записи строки.

        Args:
            row: Номер строки.

        Returns:
            Id.

        Пример:
            >>> model.row_id(0)
            7
        """
        return self._rows[row][self.id_field]

    def row_of(self, entity_id: Hashable) -> int:
        """
        Номер строки записи.

        Args:
            entity_id: Id.

        Returns:
            Номер строки или -1.

        Пример:
            >>> model.row_of(7)
            0
        """
        for i, row in enumerate(self._rows):
            if row.get(self.id_field) == entity_id:
                return i
        return -1

    def node(self, row: int) -> NodeKey:
        """
        Ключ узла строки.

        Args:
            row: Номер строки.

        Returns:
            ``(entity, id)``.

        Пример:
            >>> model.node(0)
            ('photo', 7)
        """
        return (self.entity, self.row_id(row))

    def record(self, row: int) -> Dict[str, Any]:
        """
        Данные строки с учётом черновика.

        Args:
            row: Номер строки.

        Returns:
            Новый словарь.

        Пример:
            >>> model.record(0)['file_path']
            'a.jpg'
        """
        base = self._rows[row]
        return self.store.effective(self.entity, base[self.id_field], base)

    def row_status(self, row: int) -> Optional[str]:
        """
        Статус строки для оформления: ``'deleted'``, ``'new'``, ``'own'``, ``'child'``,
        ``'both'`` или ``None``.

        Args:
            row: Номер строки.

        Returns:
            Статус.

        Пример:
            >>> model.row_status(0)
            'own'
        """
        draft = self.store.get(*self.node(row))
        if draft is not None and draft.deleted:
            return 'deleted'
        if draft is not None and draft.is_new:
            return 'new'
        return self.store.status(*self.node(row))

    # ------------------------------------------------------------------
    # QAbstractTableModel
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Число строк.

        Args:
            parent: Не используется (таблица плоская).

        Returns:
            Число строк.

        Пример:
            >>> model.rowCount()
            3
        """
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Число колонок.

        Args:
            parent: Не используется.

        Returns:
            Число колонок.

        Пример:
            >>> model.columnCount()
            2
        """
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        """
        Заголовки колонок.

        Args:
            section: Номер колонки/строки.
            orientation: Горизонтальный/вертикальный.
            role: Роль.

        Returns:
            Заголовок или ``None``.

        Пример:
            >>> model.headerData(0, Qt.Horizontal)
            'Фамилия'
        """
        if role == Qt.DisplayRole and orientation == Qt.Horizontal and 0 <= section < len(self.columns):
            return self.columns[section].title
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """
        Значение ячейки с учётом черновика + оформление по статусу.

        Args:
            index: Ячейка.
            role: Роль.

        Returns:
            Значение для роли.

        Пример:
            >>> model.data(model.index(0, 0))
            'Петров'
        """
        if not index.isValid():
            return None
        row, column = index.row(), self.columns[index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            value = self.record(row).get(column.field)
            return column.text(value) if role == Qt.DisplayRole else value
        if role == NodeRole:
            return self.node(row)
        status = self.row_status(row)
        if role == StatusRole:
            return status
        if role == Qt.BackgroundRole and status in self.colors:
            return QBrush(QColor(self.colors[status]))
        if role == Qt.FontRole and status == 'deleted':
            font = QFont()
            font.setStrikeOut(True)
            return font
        if role == Qt.ToolTipRole and status:
            return {
                'own': 'Есть несохранённые изменения',
                'child': 'Есть несохранённые изменения во вложенных записях',
                'both': 'Есть несохранённые изменения (и во вложенных записях)',
                'new': 'Новая запись (не сохранена)',
                'deleted': 'Помечена на удаление',
            }.get(status)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Флаги ячейки: правка запрещена у нередактируемых колонок и удалённых строк.

        Args:
            index: Ячейка.

        Returns:
            Флаги.

        Пример:
            >>> bool(model.flags(model.index(0, 0)) & Qt.ItemIsEditable)
            True
        """
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.columns[index.column()].editable and self.row_status(index.row()) != 'deleted':
            flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        """
        Правка ячейки → черновик. Исходное значение (из БД) передаётся хранилищу:
        вернули как было — поле убирается из черновика.

        Args:
            index: Ячейка.
            value: Значение из редактора.
            role: Только ``EditRole``.

        Returns:
            ``True``, если принято.

        Пример:
            >>> model.setData(model.index(0, 1), 'Пётр')
            True
        """
        if role != Qt.EditRole or not index.isValid() or not (self.flags(index) & Qt.ItemIsEditable):
            return False
        column = self.columns[index.column()]
        if column.from_edit is not None:
            try:
                value = column.from_edit(value)
            except (TypeError, ValueError):
                return False
        base = self._rows[index.row()]
        if self.record(index.row()).get(column.field) == value:
            return True
        parent_id = base.get(self._fk, MISSING) if self._fk else MISSING
        self.store.modify(self.entity, base[self.id_field], {column.field: value},
                          original={column.field: base.get(column.field)}, parent_id=parent_id)
        return True

    # ------------------------------------------------------------------
    # Операции
    # ------------------------------------------------------------------

    def add_row(self, data: Optional[Mapping[str, Any]] = None) -> Hashable:
        """
        Новая запись под текущим родителем (строка появится через событие хранилища).

        Args:
            data: Начальные поля.

        Returns:
            Временный id.

        Raises:
            ValueError: У типа обязателен родитель, а контекст не задан.

        Пример:
            >>> model.add_row({'file_path': 'a.jpg'})
            -3
        """
        parent_id = None if self._parent_id is MISSING else self._parent_id
        return self.store.create(self.entity, data or {}, parent_id=parent_id)

    def delete_rows(self, rows: Sequence[int]) -> None:
        """
        Помечает строки на удаление (одной пачкой событий).

        Args:
            rows: Номера строк.

        Returns:
            None

        Пример:
            >>> model.delete_rows([0, 2])
        """
        ids = [self.row_id(r) for r in rows]
        with self.store.batch():
            for entity_id in ids:
                base = self._rows[self.row_of(entity_id)]
                parent_id = base.get(self._fk, MISSING) if self._fk else MISSING
                self.store.delete(self.entity, entity_id, parent_id=parent_id)

    def undelete_rows(self, rows: Sequence[int]) -> None:
        """
        Снимает пометку удаления.

        Args:
            rows: Номера строк.

        Returns:
            None

        Пример:
            >>> model.undelete_rows([0])
        """
        ids = [self.row_id(r) for r in rows]
        with self.store.batch():
            for entity_id in ids:
                self.store.undelete(self.entity, entity_id)

    def discard_rows(self, rows: Sequence[int], scope: SaveScope = SaveScope.SELF) -> None:
        """
        Отменяет изменения строк (с потомками/предками — по ``scope``).

        Args:
            rows: Номера строк.
            scope: Направления.

        Returns:
            None

        Пример:
            >>> model.discard_rows([0], SaveScope.BRANCH)
        """
        self.store.discard([self.node(r) for r in rows], scope)

    # ------------------------------------------------------------------
    # События хранилища
    # ------------------------------------------------------------------

    def _belongs_here(self, entity_id: Hashable) -> bool:
        """
        Новая запись относится к этой таблице (тот же тип и родитель-контекст).

        Args:
            entity_id: Id записи этого типа.

        Returns:
            ``True``, если её строку нужно показать здесь.

        Пример:
            >>> model._belongs_here(-1)
            True
        """
        draft = self.store.get(self.entity, entity_id)
        if draft is None:
            return False
        return self._parent_id is MISSING or draft.parent_id == self._parent_id

    def _schedule_reload(self) -> None:
        """
        Одна просьба перечитать страницу на всю пачку событий: сохранение 50 записей —
        одно перечитывание, а не 50 (сигнал — после возврата в цикл событий Qt).

        Returns:
            None

        Пример:
            >>> model._schedule_reload()
        """
        if self._reload_pending:
            return
        self._reload_pending = True
        QTimer.singleShot(0, self._emit_reload)

    def _emit_reload(self) -> None:
        """
        Испускает ``reload_requested`` (запланировано ``_schedule_reload``).

        Returns:
            None

        Пример:
            >>> model._emit_reload()
        """
        self._reload_pending = False
        self.reload_requested.emit()

    def is_new_row(self, row: int) -> bool:
        """
        Строка — новая запись (не из БД).

        Args:
            row: Номер строки.

        Returns:
            ``True`` для новой.

        Пример:
            >>> model.is_new_row(model.row_of(-1))
            True
        """
        return self.row_id(row) in self._new_ids

    def _refresh_row(self, row: int) -> None:
        """
        Перерисовать строку целиком.

        Args:
            row: Номер строки.

        Returns:
            None

        Пример:
            >>> model._refresh_row(0)
        """
        self.dataChanged.emit(self.index(row, 0), self.index(row, max(0, len(self.columns) - 1)))

    def _on_store_event(self, event: DraftEvent) -> None:
        """
        Реакция на изменения хранилища (из любой части приложения).

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> model._on_store_event(DraftEvent('modified', ('patient', 1), (('patient', 1),)))
        """
        if event.kind == 'cleared':
            self._schedule_reload()
            return
        node = event.node
        if node is not None and node[0] == self.entity:
            row = self.row_of(node[1])
            if event.kind == 'created' and row < 0 and self._belongs_here(node[1]):
                draft = self.store.get(*node)
                self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
                self._rows.append({**draft.data, self.id_field: draft.id})
                self._new_ids.add(draft.id)
                self.endInsertRows()
            elif event.kind == 'discarded' and row >= 0 and node[1] in self._new_ids \
                    and not self.store.has_draft(*node):
                # отменённая НОВАЯ запись — строки больше нет (у существующей — остаётся)
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._rows[row]
                self._new_ids.discard(node[1])
                self.endRemoveRows()
            elif event.kind == 'remapped':
                old_row = self.row_of(event.old_id)
                if old_row >= 0:
                    self._rows[old_row][self.id_field] = node[1]
                    self._new_ids.discard(event.old_id)
                    self.row_id_changed.emit(event.old_id, node[1])
            elif event.kind == 'modified' and row >= 0:
                draft = self.store.get(*node)
                if draft is not None and draft.is_new:
                    self._rows[row] = {**draft.data, self.id_field: draft.id}
        if event.kind in ('saved', 'remapped'):
            self._schedule_reload()
        for entity, entity_id in event.affected:
            if entity == self.entity:
                row = self.row_of(entity_id)
                if row >= 0:
                    self._refresh_row(row)
