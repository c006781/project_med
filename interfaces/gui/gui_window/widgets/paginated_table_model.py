# interfaces/gui/gui_window/widgets/paginated_table_model.py

"""
Модель таблицы с поддержкой ленивой подгрузки страниц (пагинации).

В отличие от DynamicTableModel, эта модель не требует полной замены данных
через update_data. Вместо этого она поддерживает добавление страниц (append_page)
и предоставляет методы для управления общим количеством записей и флагом
возможности подгрузки следующих страниц.

Поддерживает:
    - Чекбоксы (опциональный первый столбец)
    - Установку цвета фона для строк
    - Сортировку только по уже загруженным данным (локальная сортировка)
    - Сигнал row_modified при изменении данных
"""

import datetime
from typing import List, Dict, Any, Optional, Callable, Union
from collections.abc import Sequence
from functools import partial

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from app.utils.logger.logger import AppLogger


class PaginatedTableModel(QAbstractTableModel):
    """
    Модель таблицы с пагинацией, работающая со списком DTO.

    Атрибуты:
        _data (List[Any]): Загруженные строки (все, что были добавлены через append_page).
        _total_count (int): Общее количество строк в БД (с учётом фильтров).
        _columns (List[Dict]): Описание колонок.
        _checkbox_column_enabled (bool): Флаг включения столбца чекбоксов.
        _checkbox_states (Dict[int, bool]): Состояния чекбоксов для строк _data.
        _row_colors (Dict[int, QColor]): Цвета строк.
        _field_by_column (Dict[int, str]): Маппинг индекса колонки -> имя поля.
        row_modified (Signal): Сигнал, испускаемый при изменении данных в строке (передаёт индекс строки в _data).
    """

    row_modified = Signal(int)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        columns: List[Dict],
        parent=None,
        get_unique_values_func: Optional[Callable[[int], List[str]]] = None,
        column_masks: Optional[Dict[int, str]] = None,
    ):
        """
        Инициализирует модель таблицы.

        Args:
            columns: Список словарей с ключами:
                - 'name' (str): имя поля в DTO
                - 'title' (str): заголовок для отображения
                - 'type' (type): тип данных
                - 'editable' (bool): можно ли редактировать
            parent: Родительский объект.
            get_unique_values_func: Функция для получения уникальных значений столбца
                (используется делегатами, сама модель не вызывает).
            column_masks: Словарь {индекс колонки: маска ввода} (передаётся делегатам).
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='gui.PaginatedTableModel',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        self._data: List[Any] = []
        self._total_count = 0
        self._columns = columns
        self._editable_columns = {col['name']: col.get('editable', False) for col in columns}
        self._checkbox_column_enabled = False
        self._checkbox_states: Dict[int, bool] = {}
        self._row_colors: Dict[int, QColor] = {}
        self._get_unique_values_func = get_unique_values_func
        self._column_masks = column_masks or {}

        self._field_by_column: Dict[int, str] = {}
        self._update_column_mapping()

    # ----------------------------------------------------------------------
    # Управление пагинацией и общим количеством
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_total_count(self, total: int) -> None:
        """Устанавливает общее количество записей в БД (необязательно для точного canFetchMore)."""
        self._total_count = total
        if self._total_count > 0 and len(self._data) > self._total_count:
            # Случай, когда загружено больше, чем total – обрезаем
            self.logger.warning(f"Загружено больше данных ({len(self._data)}) чем total ({total})")

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def total_count(self) -> int:
        """Возвращает общее количество записей (если установлено) или -1."""
        return self._total_count

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def can_fetch_more(self) -> bool:
        """Может ли модель загрузить ещё данные."""
        return self._total_count > 0 and len(self._data) < self._total_count

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def append_page(self, data: List[Any]) -> None:
        """
        Добавляет очередную страницу данных в конец модели.
        Вызывается из контроллера после загрузки.

        Args:
            data: Список DTO новой страницы.
        """
        if not data:
            return
        start = len(self._data)
        self.beginInsertRows(QModelIndex(), start, start + len(data) - 1)
        self._data.extend(data)
        self.endInsertRows()
        # При добавлении новых строк чекбоксы по умолчанию False
        for idx in range(start, len(self._data)):
            self._checkbox_states[idx] = self._checkbox_states.get(idx, False)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear(self) -> None:
        """Полностью очищает модель (сбрасываются данные, чекбоксы, цвета)."""
        self.beginResetModel()
        self._data.clear()
        self._checkbox_states.clear()
        self._row_colors.clear()
        self._total_count = 0
        self.endResetModel()

    # ----------------------------------------------------------------------
    # Управление чекбокс-столбцом
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_column_visible(self, visible: bool) -> None:
        """Включает или отключает столбец чекбоксов (первый столбец)."""
        if self._checkbox_column_enabled == visible:
            return
        self.beginResetModel()
        self._checkbox_column_enabled = visible
        if not visible:
            self._checkbox_states.clear()
        self._update_column_mapping()
        self.endResetModel()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_state(self, row: int, checked: bool) -> None:
        """Устанавливает состояние чекбокса для строки (индекс в _data)."""
        if not self._checkbox_column_enabled or row < 0 or row >= len(self._data):
            return
        self._checkbox_states[row] = checked
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [Qt.CheckStateRole])

    # ----------------------------------------------------------------------
    # Управление цветом строк
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_row_color(self, row: int, color: QColor) -> None:
        """Устанавливает цвет фона для строки."""
        if 0 <= row < len(self._data):
            self._row_colors[row] = color
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear_row_colors(self) -> None:
        """Очищает все установленные цвета строк."""
        self._row_colors.clear()
        if self.rowCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    # ----------------------------------------------------------------------
    # Доступ к данным
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_item_at_row(self, row: int) -> Optional[Any]:
        """Возвращает DTO для указанной строки или None."""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_all_data(self) -> List[Any]:
        """Возвращает копию списка всех загруженных DTO."""
        return self._data[:]

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def update_row(self, row: int, new_dto: Any) -> None:
        """Заменяет DTO в указанной строке на новый."""
        if row < 0 or row >= len(self._data):
            return
        self._data[row] = new_dto
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def remove_row(self, row: int) -> Optional[Any]:
        """Удаляет строку и возвращает удалённый DTO."""
        if row < 0 or row >= len(self._data):
            return None
        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._data.pop(row)
        # Сдвигаем состояния чекбоксов для строк > row
        new_states = {}
        for r, state in self._checkbox_states.items():
            if r > row:
                new_states[r - 1] = state
            elif r < row:
                new_states[r] = state
            # r == row удаляем
        self._checkbox_states = new_states
        self.endRemoveRows()
        return removed

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_row(self, dto: Any, at_end: bool = True) -> int:
        """
        Добавляет новую строку в конец (или в начало) модели.

        Args:
            dto: DTO новой записи.
            at_end: Если True – добавляет в конец, иначе в начало.

        Returns:
            Индекс добавленной строки.
        """
        if at_end:
            row = len(self._data)
            self.beginInsertRows(QModelIndex(), row, row)
            self._data.append(dto)
            self._checkbox_states[row] = False
            self.endInsertRows()
        else:
            row = 0
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._data.insert(0, dto)
            # Сдвигаем состояния чекбоксов
            new_states = {}
            for r, state in self._checkbox_states.items():
                new_states[r + 1] = state
            new_states[0] = False
            self._checkbox_states = new_states
            self.endInsertRows()
        self.row_modified.emit(row)
        return row

    # ----------------------------------------------------------------------
    # Вспомогательные методы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_column_mapping(self) -> None:
        """Создаёт маппинг: индекс колонки модели -> имя поля (или '__checkbox__')."""
        self._field_by_column.clear()
        offset = 1 if self._checkbox_column_enabled else 0
        if self._checkbox_column_enabled:
            self._field_by_column[0] = '__checkbox__'
        for i, col_info in enumerate(self._columns):
            self._field_by_column[i + offset] = col_info['name']

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_field_name(self, column: int) -> Optional[str]:
        """Возвращает имя поля для индекса колонки."""
        return self._field_by_column.get(column)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_real_type(self, field_type) -> type:
        """Извлекает реальный тип из Optional/Union."""
        from typing import get_origin, get_args, Union
        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)
            for arg in args:
                if arg is not type(None):
                    return arg
        return field_type

    # ----------------------------------------------------------------------
    # Методы QAbstractTableModel
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._data)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._columns) + (1 if self._checkbox_column_enabled else 0)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row, col = index.row(), index.column()
        field_name = self._get_field_name(col)
        if field_name is None:
            return None

        if field_name == '__checkbox__':
            if role == Qt.CheckStateRole:
                return Qt.Checked if self._checkbox_states.get(row, False) else Qt.Unchecked
            return None

        # Фоновый цвет строки
        if role == Qt.BackgroundRole:
            return self._row_colors.get(row)

        # Получаем значение из DTO
        item = self._data[row]
        value = getattr(item, field_name, None)

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
            col_info = next((c for c in self._columns if c['name'] == field_name), None)
            if col_info and col_info.get('type') in (int, float):
                return Qt.AlignRight | Qt.AlignVCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.UserRole:
            return value   # для сортировки

        return None

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False

        row, col = index.row(), index.column()
        field_name = self._get_field_name(col)

        # Чекбокс
        if field_name == '__checkbox__':
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

        col_info = next((c for c in self._columns if c['name'] == field_name), None)
        if not col_info or not col_info.get('editable', False):
            return False

        item = self._data[row]
        old_value = getattr(item, field_name, None)
        if old_value == value:
            return True

        # Преобразование типа
        target_type = col_info.get('type')
        if target_type and value is not None:
            real_type = self._get_real_type(target_type)
            try:
                if real_type == int:
                    value = int(value)
                elif real_type == datetime.date and isinstance(value, str):
                    value = datetime.date.fromisoformat(value)
                elif real_type == datetime.time and isinstance(value, str):
                    value = datetime.time.fromisoformat(value)
                # можно добавить другие типы
            except (ValueError, TypeError) as e:
                self.logger.error(f"Ошибка преобразования для поля {field_name}: {e}")
                return False

        setattr(item, field_name, value)
        self.dataChanged.emit(index, index, [role])
        self.row_modified.emit(row)
        return True

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        row, col = index.row(), index.column()
        if row >= len(self._data):
            return Qt.NoItemFlags
        field_name = self._get_field_name(col)
        if field_name == '__checkbox__':
            return Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        col_info = next((c for c in self._columns if c['name'] == field_name), None)
        if not col_info:
            return Qt.NoItemFlags
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if col_info.get('editable', False):
            flags |= Qt.ItemIsEditable
        return flags

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation != Qt.Horizontal:
            return None
        field_name = self._get_field_name(section)
        if role == Qt.DisplayRole:
            if field_name == '__checkbox__':
                return ""
            col_info = next((c for c in self._columns if c['name'] == field_name), None)
            if col_info:
                return col_info['title']
        return None

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        """Сортирует только загруженные данные (локально)."""
        col_info = self._columns[column]
        field_name = col_info['name']
        reverse = (order == Qt.DescendingOrder)
        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=lambda obj: (getattr(obj, field_name, None) is not None, getattr(obj, field_name, None)), reverse=reverse)
        self.layoutChanged.emit()