# interfaces/gui/gui_window/widgets/paginated_table_model.py
"""
Модель таблицы с поддержкой ленивой подгрузки страниц (пагинации).

В отличие от DynamicTableModel, эта модель не требует полной замены данных
через update_data. Вместо этого она поддерживает добавление страниц (append_page)
и предоставляет методы для управления общим количеством записей и флагом
возможности подгрузки следующих страниц.

Поддерживает:
    - Отображение полей, заданных в columns.
    - Редактирование (если ячейка отмечена как editable).
    - Чекбоксы в отдельном столбце (опционально).
    - Установку цвета фона для строк.
    - Локальную сортировку только по уже загруженным данным.
    - Сигнал row_modified при изменении данных в строке.
    - Пагинацию: добавление страниц, общее количество, canFetchMore.
"""

import datetime
# from enum import Enum
from typing import (
    List, Dict, Any, Optional, Callable, 
    # Type, Union
)
# from collections.abc import Sequence
# from functools import partial


from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.base_table_model import BaseTableModel
from interfaces.gui.gui_window.widgets.table_column import ColumnType, TableColumn

from PySide6.QtCore import (
    QModelIndex,  QThread,
    # QObject, QTimer, 
    # QAbstractTableModel, QEvent, 
    Qt, Signal
)
from PySide6.QtGui import QColor



class LoadPageThread(QThread):
    """Поток для асинхронной загрузки страницы данных."""
    finished = Signal(list, int)   # (page_data, total_count)
    error = Signal(str)

    def __init__(self, service, offset, limit, filters, order_by):
        super().__init__()
        self.service = service
        self.offset = offset
        self.limit = limit
        self.filters = filters
        self.order_by = order_by

    def run(self):
        try:
            page, total = self.service.get_page_filtered(
                offset=self.offset,
                limit=self.limit,
                filters=self.filters,
                order_by=self.order_by,
            )
            self.finished.emit(page, total)
        except Exception as e:
            self.error.emit(str(e))



class PaginatedTableModel(BaseTableModel):
    """
    Модель таблицы с поддержкой ленивой подгрузки страниц и динамическими столбцами.

    Использует класс TableColumn для описания столбцов, что позволяет гибко управлять
    видимостью, порядком и системными столбцами (чекбокс, кнопки).

    Атрибуты:
        _data (List[Any]): Загруженные DTO.
        _columns (List[TableColumn]): Список всех столбцов (в порядке отображения).
        _total_count (int): Общее количество записей в БД (с учётом фильтров).
        _checkbox_states (Dict[int, bool]): Состояния чекбоксов (для системного столбца __checkbox__).
        _row_colors (Dict[int, QColor]): Цвета строк.

    Примечание:
        При локальной сортировке цвета строк остаются привязанными к исходным индексам _data,
        что может привести к несоответствию цветов после сортировки. Рекомендуется очищать
        цвета строк перед сортировкой или использовать серверную сортировку.
    """

    row_modified = Signal(int)

    def __init__(
        self,
        columns: List[TableColumn],
        parent=None,
        get_unique_values_func: Optional[Callable[[int], List[str]]] = None,
    ):
        """
        Инициализирует модель.

        Args:
            columns: Список объектов TableColumn (уже включая системные, если нужно).
            parent: Родительский QObject.
            get_unique_values_func: Функция для получения уникальных значений
                для автодополнения (принимает индекс видимого столбца).
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='gui.PaginatedTableModel',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        # ---- Данные ----
        self._data: List[Any] = []                     # загруженные DTO
        self._total_count: int = 0                     # общее количество (устанавливается извне)

        # ---- Столбцы ----
        self._columns: List[TableColumn] = columns     # порядок соответствует отображению
        self._checkbox_column_system_name = '__checkbox__'

        # ---- Чекбоксы ----
        self._checkbox_states: Dict[int, bool] = {}    # строка -> состояние

        # ---- Цвета строк ----
        self._row_colors: Dict[int, QColor] = {}       # строка -> цвет

        # ---- Внешние зависимости ----
        self._get_unique_values_func = get_unique_values_func

        # Проверка: если есть чекбокс-столбец, он должен быть системным и с правильным system_name
        self._ensure_checkbox_column()

        self.logger.debug(f"PaginatedTableModel инициализирована с {len(self._columns)} столбцами")

    def get_checkbox_state(self, row: int) -> bool:
        return self._checkbox_states.get(row, False)

    # ----------------------------------------------------------------------
    # Инициализация и проверка столбцов
    # ----------------------------------------------------------------------

    def _ensure_checkbox_column(self) -> None:
        """Убеждается, что в списке столбцов есть чекбокс-столбец (создаёт, если нет)."""
        for col in self._columns:
            if col.system_name == self._checkbox_column_system_name:
                return
        # Добавляем в начало
        checkbox_col = TableColumn.create_checkbox_column(order=0)
        self._columns.insert(0, checkbox_col)
        # Обновляем order у всех
        for idx, col in enumerate(self._columns):
            col.order = idx

    # ----------------------------------------------------------------------
    # Работа со столбцами (публичные методы)
    # ----------------------------------------------------------------------

    def column_count(self) -> int:
        """Возвращает общее количество столбцов (включая скрытые)."""
        return len(self._columns)

    def visible_column_count(self) -> int:
        """Возвращает количество видимых столбцов."""
        return sum(1 for col in self._columns if col.visible)

    def get_column_index(self, system_name: str) -> int:
        """
        Возвращает индекс столбца по системному имени (в модели, с учётом скрытых).
        Если столбец не найден, возвращает -1.
        """
        for idx, col in enumerate(self._columns):
            if col.system_name == system_name:
                return idx
        return -1

    def get_visible_column_index(self, system_name: str) -> int:
        """
        Возвращает индекс видимого столбца по системному имени.
        Учитываются только видимые столбцы, порядок их следования.
        """
        visible_idx = 0
        for col in self._columns:
            if col.visible:
                if col.system_name == system_name:
                    return visible_idx
                visible_idx += 1
        return -1

    def get_column_by_system_name(self, system_name: str) -> Optional[TableColumn]:
        """Возвращает объект столбца по системному имени."""
        for col in self._columns:
            if col.system_name == system_name:
                return col
        return None

    def set_column_visible(self, system_name: str, visible: bool) -> None:
        """
        Изменяет видимость столбца.
        Меняет флаг в TableColumn и испускает сигнал layoutChanged,
        который заставляет таблицу перерисовать заголовки, но НЕ сбрасывает данные.
        """
        col = self.get_column_by_system_name(system_name)
        if col is None or col.visible == visible:
            return
        col.visible = visible
        # layoutChanged перерисовывает заголовки и обновляет количество столбцов,
        # но данные остаются на месте (в отличие от beginResetModel).
        self.layoutChanged.emit()

    def get_field_name_at_visible_column(self, visible_index: int) -> Optional[str]:
        """
        По индексу видимого столбца возвращает имя поля (для DATA-столбцов)
        или None для системных.
        """
        visible_idx = 0
        for col in self._columns:
            if col.visible:
                if visible_idx == visible_index:
                    return col.field_name if col.column_type == ColumnType.DATA else None
                visible_idx += 1
        return None

    # ----------------------------------------------------------------------
    # Реализация абстрактных методов BaseTableModel
    # ----------------------------------------------------------------------

    def get_item_at_row(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    def get_all_data(self) -> List[Any]:
        return self._data[:]

    def update_row(self, row: int, new_dto: Any) -> None:
        if row < 0 or row >= len(self._data):
            self.logger.warning(f"update_row: неверный индекс {row}")
            return
        self._data[row] = new_dto
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])

    def add_row(self, dto: Any) -> int:
        row = len(self._data)
        self.beginInsertRows(QModelIndex(), row, row)
        self._data.append(dto)
        self._checkbox_states[row] = False
        self.endInsertRows()
        self.row_modified.emit(row)
        return row

    def remove_row(self, row: int) -> Optional[Any]:
        if row < 0 or row >= len(self._data):
            return None
        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._data.pop(row)
        # Сдвигаем чекбоксы
        new_states = {}
        for r, state in self._checkbox_states.items():
            if r > row:
                new_states[r - 1] = state
            elif r < row:
                new_states[r] = state
        self._checkbox_states = new_states
        # Сдвигаем цвета (если есть)
        if row in self._row_colors:
            del self._row_colors[row]
        for r in list(self._row_colors.keys()):
            if r > row:
                self._row_colors[r - 1] = self._row_colors[r]
                del self._row_colors[r]
        self.endRemoveRows()
        return removed

    def clear(self) -> None:
        self.beginResetModel()
        self._data.clear()
        self._checkbox_states.clear()
        self._row_colors.clear()
        self._total_count = 0
        self.endResetModel()

    def set_checkbox_column_visible(self, visible: bool) -> None:
        """Устанавливает флаг видимости чекбокс-столбца в модели."""
        col = self.get_column_by_system_name(self._checkbox_column_system_name)
        if col is None or col.visible == visible:
            return
        col.visible = visible
        self.layoutChanged.emit()   # перестроит всю модель (но данные останутся)

    def set_checkbox_state(self, row: int, checked: bool) -> None:
        if not self.get_column_by_system_name(self._checkbox_column_system_name).visible:
            return
        if row < 0 or row >= len(self._data):
            return
        self._checkbox_states[row] = checked
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [Qt.CheckStateRole])

    def set_row_color(self, row: int, color: QColor) -> None:
        if 0 <= row < len(self._data):
            self._row_colors[row] = color
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    def clear_row_colors(self) -> None:
        self._row_colors.clear()
        if self.rowCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    # ----------------------------------------------------------------------
    # Пагинация
    # ----------------------------------------------------------------------

    def can_fetch_more(self) -> bool:
        return self._total_count > 0 and len(self._data) < self._total_count

    def append_page(self, data: List[Any]) -> None:
        if not data:
            return
        start = len(self._data)
        self.beginInsertRows(QModelIndex(), start, start + len(data) - 1)
        self._data.extend(data)
        for idx in range(start, len(self._data)):
            if idx not in self._checkbox_states:
                self._checkbox_states[idx] = False
        self.endInsertRows()

    def set_total_count(self, total: int) -> None:
        self._total_count = total

    def total_count(self) -> int:
        """Возвращает текущее общее количество записей."""
        return self._total_count

    # ----------------------------------------------------------------------
    # Методы QAbstractTableModel
    # ----------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self.visible_column_count()

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        visible_col = index.column()
        if row >= len(self._data):
            return None

        # Находим столбец по видимому индексу
        visible_idx = 0
        target_col = None
        for col in self._columns:
            if col.visible:
                if visible_idx == visible_col:
                    target_col = col
                    break
                visible_idx += 1
        if target_col is None:
            return None

        # Чекбокс-столбец (системный)
        if target_col.system_name == self._checkbox_column_system_name:
            if role == Qt.CheckStateRole:
                return Qt.Checked if self._checkbox_states.get(row, False) else Qt.Unchecked
            return None

        # Цвет строки
        if role == Qt.BackgroundRole:
            return self._row_colors.get(row)

        # Получаем значение из DTO
        if target_col.column_type == ColumnType.DATA and target_col.field_name:
            value = getattr(self._data[row], target_col.field_name, None)
        else:
            value = None  # для других системных столбцов (кнопок и т.д.) данные не хранятся

        if role == Qt.DisplayRole:
            if value is None:
                return ""
            if isinstance(value, datetime.date):
                return value.isoformat()
            if isinstance(value, datetime.time):
                return value.strftime("%H:%M")
            return str(value)

        if role == Qt.EditRole:
            return value

        if role == Qt.TextAlignmentRole:
            if target_col.data_type in (int, float):
                return Qt.AlignRight | Qt.AlignVCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.UserRole:
            return value

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        visible_col = index.column()
        if row >= len(self._data):
            return False

        # Находим столбец по видимому индексу
        visible_idx = 0
        target_col = None
        for col in self._columns:
            if col.visible:
                if visible_idx == visible_col:
                    target_col = col
                    break
                visible_idx += 1
        if target_col is None:
            return False

        # Чекбокс
        if target_col.system_name == self._checkbox_column_system_name:
            if role == Qt.CheckStateRole:
                checked = (value == Qt.Checked.value)
                old = self._checkbox_states.get(row, False)
                if old != checked:
                    self._checkbox_states[row] = checked
                    self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.CheckStateRole])
                return True
            return False

        if role != Qt.EditRole:
            return False

        if target_col.column_type != ColumnType.DATA or not target_col.editable:
            return False

        # Обновляем значение в DTO
        item = self._data[row]
        old_value = getattr(item, target_col.field_name, None)
        if old_value == value:
            return True

        # Преобразование типа (если нужно)
        if target_col.data_type and value is not None:
            try:
                if target_col.data_type == int:
                    value = int(value)
                elif target_col.data_type == datetime.date and isinstance(value, str):
                    value = datetime.date.fromisoformat(value)
                elif target_col.data_type == datetime.time and isinstance(value, str):
                    value = datetime.time.fromisoformat(value)
                # можно добавить другие
            except (ValueError, TypeError):
                return False

        setattr(item, target_col.field_name, value)
        self.dataChanged.emit(index, index, [role])
        self.row_modified.emit(row)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        row = index.row()
        if row >= len(self._data):
            return Qt.NoItemFlags

        visible_col = index.column()
        visible_idx = 0
        target_col = None
        for col in self._columns:
            if col.visible:
                if visible_idx == visible_col:
                    target_col = col
                    break
                visible_idx += 1
        if target_col is None:
            return Qt.NoItemFlags

        if target_col.system_name == self._checkbox_column_system_name:
            return Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if target_col.column_type == ColumnType.DATA and target_col.editable:
            flags |= Qt.ItemIsEditable
        return flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation != Qt.Horizontal:
            return None
        if role != Qt.DisplayRole:
            return None

        visible_idx = 0
        for col in self._columns:
            if col.visible:
                if visible_idx == section:
                    return col.title
                visible_idx += 1
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        """
        Сортирует только загруженные данные (локально).
        ВНИМАНИЕ: цвета строк будут привязаны к прежним индексам и могут не соответствовать
        данным после сортировки. Рекомендуется очищать цвета перед сортировкой или
        использовать серверную сортировку.
        """
        # Очищаем цвета, так как они привязаны к старым индексам
        self.clear_row_colors()

        # Находим столбец по видимому индексу
        visible_idx = 0
        target_col = None
        for col in self._columns:
            if col.visible:
                if visible_idx == column:
                    target_col = col
                    break
                visible_idx += 1
        if target_col is None or target_col.column_type != ColumnType.DATA:
            return

        field_name = target_col.field_name
        reverse = (order == Qt.DescendingOrder)
        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=lambda obj: (getattr(obj, field_name, None) is not None, getattr(obj, field_name, None)), reverse=reverse)
        self.layoutChanged.emit()
