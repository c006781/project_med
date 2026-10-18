# app/utils/dataset_qt/table_model.py

"""
Модель таблицы Qt поверх набора данных (аналог ``TDBGrid`` RAD Studio).

Подключается к ``DataSource`` — набор можно сменить на лету, модель перестроится.

* Показ: текст поля (``DataSet.text``), правка — значение (``DataSet.value``); правка
  ячейки делает строку текущей и меняет значение (``set_value``; правка начинается сама,
  если у источника ``auto_edit``).
* Порции: таблица Qt сама зовёт ``canFetchMore``/``fetchMore`` при прокрутке к концу —
  набор догружает следующую порцию (``FetchMode.ON_DEMAND``).
* Подсветка строк по состоянию (``DataSet.row_status``): правится, новая, изменена,
  удалена (зачёркнуто) — цвета настраиваются (``status_colors``).
* Ошибки (проверка полей, запись) — сигнал ``error_occurred(текст)``.

**Число строк модель держит своё** (а не спрашивает набор): события набора приходят
ПОСЛЕ изменения, а Qt требует ``beginInsertRows`` ДО — модель между «begin» и «end»
отдаёт прежнее число, как требует Qt.

Зависит только от PySide6 и ядра ``dataset``.

Пример:
    >>> model = DataSetTableModel(DataSource(patients), columns=['last_name', 'first_name'])
    >>> view.setModel(model)
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QTableView

try:  # пакеты лежат рядом в одном родительском пакете (как в этом проекте)
    from ..dataset import DataEvent, DataSet, DataSource, EventKind, FieldDef, FieldKind
except ImportError:  # pragma: no cover — скопированы как отдельные пакеты верхнего уровня
    from dataset import DataEvent, DataSet, DataSource, EventKind, FieldDef, FieldKind

# Цвета строк по состоянию (DataSet.row_status); None — без подсветки
DEFAULT_STATUS_COLORS: Dict[str, str] = {
    'editing': '#fff4c2',
    'inserting': '#dff5df',
    'new': '#dff5df',
    'modified': '#fff4c2',
    'deleted': '#f7d9d9',
    'child': '#e6efff',          # изменены потомки строки (подчинённые записи)
}

_NUMERIC = (FieldKind.INTEGER, FieldKind.FLOAT)


class DataSetTableModel(QAbstractTableModel):
    """
    Таблица Qt над набором из ``DataSource``.

    Signals:
        error_occurred(str): Ошибка правки/записи/источника — текст для пользователя.
        current_row_changed(int): Сменилась текущая строка набора (для выделения в таблице).

    Пример:
        >>> model = DataSetTableModel(source)
        >>> model.columns
        ['id', 'last_name', 'first_name']
    """

    error_occurred = Signal(str)
    current_row_changed = Signal(int)

    def __init__(self, source: DataSource, columns: Optional[Sequence[str]] = None,
                 parent=None, status_colors: Optional[Mapping[str, Optional[str]]] = None) -> None:
        """
        Args:
            source: Источник набора.
            columns: Поля-колонки (по умолчанию — видимые поля набора).
            parent: Родитель Qt.
            status_colors: Цвета подсветки по состоянию строки (``None`` — без подсветки).

        Пример:
            >>> DataSetTableModel(DataSource(), columns=['a']).columnCount()
            1
        """
        super().__init__(parent)
        self.source = source
        self._given_columns = list(columns) if columns is not None else None
        self._columns: List[str] = list(columns or [])
        self._rows = 0
        colors = dict(DEFAULT_STATUS_COLORS)
        colors.update(status_colors or {})
        self._brushes = {k: QBrush(QColor(v)) for k, v in colors.items() if v}
        source.subscribe(self._on_event)
        self._reset()

    # ------------------------------------------------------------------ служебное

    @property
    def dataset(self) -> Optional[DataSet]:
        """
        Набор источника.

        Returns:
            Набор или ``None``.

        Пример:
            >>> model.dataset is source.dataset
            True
        """
        return self.source.dataset

    @property
    def columns(self) -> List[str]:
        """
        Поля-колонки.

        Returns:
            Список имён.

        Пример:
            >>> model.columns
            ['last_name']
        """
        return list(self._columns)

    def _dataset_rows(self) -> int:
        """
        Сколько строк сейчас у набора (0 — нет набора или закрыт).

        Returns:
            Число.

        Пример:
            >>> model._dataset_rows()
            3
        """
        ds = self.dataset
        return ds.row_count if ds is not None and ds.active else 0

    def _reset(self) -> None:
        """
        Перестраивает модель целиком (колонки, число строк).

        Returns:
            None

        Пример:
            >>> model._reset()
        """
        self.beginResetModel()
        ds = self.dataset
        if self._given_columns is None:
            self._columns = [f.name for f in ds.fields.visible()] if ds is not None else []
        self._rows = self._dataset_rows()
        self.endResetModel()

    def _row_changed(self, row: int) -> None:
        """
        Сообщает таблице, что строка изменилась (значения, подсветка).

        Args:
            row: Номер строки.

        Returns:
            None

        Пример:
            >>> model._row_changed(0)
        """
        if 0 <= row < self._rows and self._columns:
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(self._columns) - 1))

    def _on_event(self, event: DataEvent) -> None:
        """
        Событие набора → изменения модели.

        Args:
            event: Событие.

        Returns:
            None

        Пример:
            >>> model._on_event(DataEvent(EventKind.REFRESHED, ds))
        """
        kind = event.kind
        if event.dataset is not None and event.dataset is not self.dataset:
            return                                        # старый набор (сменили на лету)
        if kind in (EventKind.REFRESHED, EventKind.OPENED, EventKind.CLOSED):
            self._reset()
        elif kind is EventKind.ROWS_INSERTED and event.count:
            first = min(event.index, self._rows)
            self.beginInsertRows(QModelIndex(), first, first + event.count - 1)
            self._rows += event.count
            self.endInsertRows()
        elif kind is EventKind.ROWS_REMOVED and event.count:
            first = event.index
            last = min(first + event.count, self._rows) - 1
            if first <= last:
                self.beginRemoveRows(QModelIndex(), first, last)
                self._rows -= last - first + 1
                self.endRemoveRows()
        elif kind is EventKind.ROW_CHANGED and event.index is not None:
            self._row_changed(event.index)
        elif kind is EventKind.CURRENT_CHANGED:
            if isinstance(event.old, int):
                self._row_changed(event.old)
            if isinstance(event.new, int):
                self._row_changed(event.new)
                self.current_row_changed.emit(event.new)
        elif kind is EventKind.STATE_CHANGED:
            ds = self.dataset
            if ds is not None:
                self._row_changed(ds.current_index)
        elif kind is EventKind.ERROR and event.error is not None:
            self.error_occurred.emit(str(event.error))
        # набор и модель разошлись (событие пропущено) — перестроиться
        if self._rows != self._dataset_rows():
            self._reset()

    # ------------------------------------------------------------------ интерфейс Qt

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Число строк (своё, см. описание модуля).

        Args:
            parent: Родитель (у таблицы строк под родителем нет).

        Returns:
            Число строк.

        Пример:
            >>> model.rowCount()
            3
        """
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Число колонок.

        Args:
            parent: Родитель.

        Returns:
            Число колонок.

        Пример:
            >>> model.columnCount()
            2
        """
        return 0 if parent.isValid() else len(self._columns)

    def _field(self, column: int) -> Optional[FieldDef]:
        """
        Описание поля колонки (``None`` — поле не описано).

        Args:
            column: Номер колонки.

        Returns:
            ``FieldDef`` или ``None``.

        Пример:
            >>> model._field(0).label
            'Фамилия'
        """
        ds = self.dataset
        if ds is None or not 0 <= column < len(self._columns):
            return None
        return ds.fields.get(self._columns[column])

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """
        Данные ячейки.

        Args:
            index: Ячейка.
            role: Роль Qt.

        Returns:
            Текст / значение / цвет / шрифт / выравнивание или ``None``.

        Пример:
            >>> model.data(model.index(0, 0))
            'Петров'
        """
        ds = self.dataset
        if ds is None or not index.isValid() or index.row() >= min(self._rows, ds.row_count):
            return None
        row, name = index.row(), self._columns[index.column()]
        definition = self._field(index.column())
        is_check = definition is not None and definition.kind is FieldKind.BOOLEAN
        if role == Qt.CheckStateRole and is_check:
            return Qt.Checked if ds.value(name, row) else Qt.Unchecked
        if role == Qt.DisplayRole:
            return '' if is_check else ds.text(name, row)
        if role == Qt.EditRole:
            return ds.value(name, row)
        if role == Qt.BackgroundRole:
            return self._brushes.get(ds.row_status(row) or '')
        if role == Qt.FontRole and ds.row_status(row) == 'deleted':
            font = QFont()
            font.setStrikeOut(True)
            return font
        if role == Qt.TextAlignmentRole:
            definition = self._field(index.column())
            if definition is not None and definition.kind in _NUMERIC:
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        """
        Заголовки: подписи полей; строки — номера.

        Args:
            section: Номер колонки/строки.
            orientation: Горизонтальный/вертикальный.
            role: Роль.

        Returns:
            Текст или ``None``.

        Пример:
            >>> model.headerData(0, Qt.Horizontal)
            'Фамилия'
        """
        if role == Qt.ToolTipRole and orientation == Qt.Horizontal:
            ds = self.dataset
            if ds is not None and 0 <= section < len(self._columns):
                name = self._columns[section]
                if not ds.sortable(name):
                    return "Сортировка по этому столбцу — когда загружено всё (его считает программа)"
            return None
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            definition = self._field(section)
            if definition is not None:
                return definition.label
            return self._columns[section] if 0 <= section < len(self._columns) else None
        return section + 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Можно ли править ячейку: поле редактируемое, набор можно менять, ``auto_edit``.

        Args:
            index: Ячейка.

        Returns:
            Флаги Qt.

        Пример:
            >>> bool(model.flags(model.index(0, 0)) & Qt.ItemIsEditable)
            True
        """
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        ds, definition = self.dataset, self._field(index.column())
        if definition is not None and definition.local:
            # своё поле набора (отметка) — можно и в наборе «только для чтения»: в
            # хранилище не пишется
            if definition.kind is FieldKind.BOOLEAN:
                return base | Qt.ItemIsUserCheckable if definition.editable else base
            return base | Qt.ItemIsEditable if definition.editable else base
        editable = (ds is not None and ds.can_modify and self.source.auto_edit
                    and (definition is None or definition.editable))
        if definition is not None and definition.kind is FieldKind.BOOLEAN:
            return base | Qt.ItemIsUserCheckable if editable else base
        return base | Qt.ItemIsEditable if editable else base

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        """
        Правка ячейки: строка становится текущей, значение — в набор.

        Args:
            index: Ячейка.
            value: Значение.
            role: Роль (только ``EditRole``).

        Returns:
            ``True`` — значение принято; ``False`` — отказ (текст — ``error_occurred``).

        Пример:
            >>> model.setData(model.index(0, 0), 'Сидоров')
            True
        """
        ds = self.dataset
        if role not in (Qt.EditRole, Qt.CheckStateRole) or ds is None or not index.isValid():
            return False
        name = self._columns[index.column()]
        definition = self._field(index.column())
        if role == Qt.CheckStateRole:
            value = _checked(value)
        try:
            if definition is not None and definition.local:
                ds.set_local(name, value, index=index.row())   # отметка — без смены текущей
                return True
            if ds.current_index != index.row():
                ds.move_to(index.row())
            ds.set_value(name, value)
        except Exception as exc:          # проверка полей, запись, только чтение
            self.error_occurred.emit(str(exc))
            return False
        return True

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        """
        Сортировка щелчком по заголовку (``QTableView.setSortingEnabled(True)``).

        По столбцу, который считает программа, — только когда загружено всё; иначе
        отказ с объяснением (``error_occurred``), а не неверный порядок.

        Args:
            column: Колонка.
            order: Порядок.

        Returns:
            None

        Пример:
            >>> model.sort(0, Qt.DescendingOrder)
        """
        ds = self.dataset
        if ds is None or not 0 <= column < len(self._columns):
            return
        name = self._columns[column]
        if not ds.sortable(name):
            definition = self._field(column)
            label = definition.label if definition is not None else name
            self.error_occurred.emit(f"Сортировка по «{label}» — когда загружено всё "
                                     "(этот столбец считает программа)")
            return
        try:
            ds.set_order(('-' if order == Qt.DescendingOrder else '') + name)
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        """
        Есть ли ещё строки для догрузки (таблица спрашивает при прокрутке к концу).

        Args:
            parent: Родитель.

        Returns:
            ``True`` — есть.

        Пример:
            >>> model.canFetchMore()
            True
        """
        ds = self.dataset
        return not parent.isValid() and ds is not None and ds.has_more

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        """
        Догружает следующую порцию (строки добавятся по событию набора).

        Args:
            parent: Родитель.

        Returns:
            None

        Пример:
            >>> model.fetchMore()
        """
        ds = self.dataset
        if parent.isValid() or ds is None:
            return
        try:
            ds.fetch_more()
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    def disconnect_source(self) -> None:
        """
        Отписывается от источника (модель больше не нужна).

        Returns:
            None

        Пример:
            >>> model.disconnect_source()
        """
        self.source.unsubscribe(self._on_event)


def _checked(value: Any) -> bool:
    """
    Значение галочки Qt → bool (Qt отдаёт и перечисление, и число).

    Args:
        value: ``Qt.Checked``/``Qt.Unchecked`` или 0/2.

    Returns:
        ``True`` — отмечено.

    Пример:
        >>> _checked(Qt.Checked), _checked(0)
        (True, False)
    """
    if isinstance(value, Qt.CheckState):
        return value == Qt.Checked
    try:
        return int(value) == Qt.Checked.value
    except (TypeError, ValueError):
        return bool(value)


def bind_table_view(view: QTableView, model: DataSetTableModel) -> None:
    """
    Связывает выделение таблицы Qt с текущей строкой набора — в обе стороны.

    Щелчок по строке делает её текущей (во время правки — сохранение, ``auto_post``;
    не прошла проверку — выделение возвращается, текст — ``error_occurred``).
    Смена текущей строки в наборе (навигатор, код) — выделение переходит на неё.

    Args:
        view: ``QTableView``.
        model: Модель.

    Returns:
        None

    Пример:
        >>> bind_table_view(view, model)
    """
    view.setModel(model)
    selection = view.selectionModel()
    guard = {'busy': False}

    def follow_dataset(row: int) -> None:
        """
        Текущая строка набора → выделение таблицы.

        Args:
            row: Номер строки (-1 — нет строки).

        Returns:
            None

        Пример:
            >>> follow_dataset(3)
        """
        if guard['busy']:
            return
        guard['busy'] = True
        try:
            if row < 0:
                selection.clearCurrentIndex()
            else:
                column = max(view.currentIndex().column(), 0)
                view.setCurrentIndex(model.index(row, column))
        finally:
            guard['busy'] = False

    def follow_view(current: QModelIndex, previous: QModelIndex) -> None:
        """
        Выделение таблицы → текущая строка набора (отказ — выделение возвращается).

        Args:
            current: Новая ячейка.
            previous: Прежняя ячейка.

        Returns:
            None

        Пример:
            >>> follow_view(model.index(2, 0), model.index(1, 0))
        """
        if guard['busy'] or not current.isValid():
            return
        ds = model.dataset
        if ds is None or ds.current_index == current.row():
            return
        try:
            ds.move_to(current.row())
        except Exception as exc:
            model.error_occurred.emit(str(exc))
            follow_dataset(ds.current_index)          # вернуть выделение на текущую строку

    model.current_row_changed.connect(follow_dataset)
    selection.currentRowChanged.connect(follow_view)
    ds = model.dataset
    if ds is not None and ds.active:
        follow_dataset(ds.current_index)


__all__ = ['DataSetTableModel', 'bind_table_view', 'DEFAULT_STATUS_COLORS']
