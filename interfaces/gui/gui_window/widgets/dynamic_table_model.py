# interfaces/gui/gui_window/widgets/dynamic_table_model.py

"""
Универсальная модель таблицы, строящаяся на основе списка DTO и описания колонок.
Каждая колонка задаётся словарём:
    {
        'name': str,          # имя поля в DTO
        'title': str,         # заголовок для отображения
        'type': type,         # тип данных (int, str, date, time и т.д.)
        'editable': bool,     # можно ли редактировать ячейку
        'choices': list или callable  # опционально: список значений для выпадающего списка
    }
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from typing import List, Dict, Any, Optional, Callable
# from datetime import date, time
import datetime

from app.utils.logger.logger import AppLogger


class DynamicTableModel(QAbstractTableModel):
    """
    Модель для отображения любых DTO-объектов в таблице.
    """

    # Сигнал, испускаемый при изменении данных в строке (передаётся индекс строки)
    row_modified = Signal(int)

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def __init__(
        self,
        data: List[Any], 
        columns: List[Dict], 
        parent=None,
        get_unique_values_func=None,
    ):
        """
        :param data: список DTO (объекты с атрибутами, соответствующими колонкам)
        :param columns: описание колонок в таблице
        :param get_unique_values_func: вызываемый объект с сигнатурой func(column_index) -> List[str]
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name = 'gui.DynamicTableModel',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
            
        )

        self._data = data
        self._columns = columns
        self._editable_columns = {col['name']: col.get('editable', False) for col in columns}

        self._row_colors = {}  # словарь {row: QColor}

        self._get_unique_values_func = get_unique_values_func 


    def get_unique_values_for_column(self, col: int) -> List[str]:
        """
        Возвращает список уникальных строк для указанного столбца.
        Если функция не задана или возникает ошибка, возвращает пустой список.
        """
        if not self._get_unique_values_func:
            return []
        try:
            return self._get_unique_values_func(col)
        except Exception as e:
            self.logger.exception(f"Ошибка получения уникальных значений для столбца {col}: {e}")
            return []


    def clear_row_color(self, row: int):
        """
        Очищает цвет строки в таблице.
        Если строка имела цвет, то он будет удален.
        :param row: индекс строки в таблице
        :type row: int
        """
        if row in self._row_colors:
            del self._row_colors[row]
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.BackgroundRole])

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._columns)

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def data(
        self, 
        index: QModelIndex, 
        role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        # self.logger.debug(f'index: {index}, role: {role}')

        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()

        # self.logger.debug(f'row: {row}, col: {col} result: {row >= len(self._data)}')

        if row >= len(self._data):
            return None
        
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._row_colors.get(row)
        
        item = self._data[row]
        col_info = self._columns[col]
        field_name = col_info['name']
        value = getattr(item, field_name, None)

        # self.logger.debug(
        #     # f'item: {item}, col_info: {col_info}, field_name: {field_name}, value: {value}, role: {role}'
        #     f'field_name: {field_name}, value: {value}, role: {role}'
        # )
 
        # self.logger.debug(
        #     # f'item: {item}, col_info: {col_info}, field_name: {field_name}, value: {value}, role: {role}'
        #     # f'field_name: {field_name}, value: {value}, role: {role}'
        #     f'field_name: {field_name}, value: {value}, role: {role}'
        # )
        if role == Qt.ItemDataRole.DisplayRole:
            # self.logger.debug(f'Qt.ItemDataRole.DisplayRole result: {value is None}')
            
            if value is None:
                return ""
            
            # Для дат и времени возвращаем строку в стандартном формате
            if isinstance(value, datetime.date):
                # self.logger.debug(f'Qt.ItemDataRole.DisplayRole - datetime.date')
                return value.isoformat()
            
            if isinstance(value, datetime.time):
                # self.logger.debug(f'Qt.ItemDataRole.DisplayRole - datetime.time')
                return value.strftime("%H:%M")

            temp = str(value)
            # self.logger.debug(f'return str(value): {temp}')

            return temp

        if role == Qt.ItemDataRole.EditRole:
            # self.logger.debug(f'Qt.ItemDataRole.EditRole')
            # Для редактирования возвращаем сырое значение
            return value

        if role == Qt.ItemDataRole.TextAlignmentRole:
            # self.logger.debug(
            #     f"Qt.ItemDataRole.TextAlignmentRole result: {col_info.get('type') in (int, float)}"
            # )
            # Числа выравниваем вправо, текст влево
            if col_info.get('type') in (int, float):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        # Для сортировки используем DisplayRole (уже строка) или можно вернуть значение
        if role == Qt.ItemDataRole.UserRole:
            # self.logger.debug(f'Qt.ItemDataRole.UserRole')
            return value  # для сортировки

            
        # self.logger.debug(f'role {role} not found')
        return None

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def setData(
        self, 
        index: QModelIndex, 
        value: Any, 
        role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        """
        Обновляет значение в ячейке (если колонка редактируемая).
        Сигнал dataChanged испускается автоматически.
        """
        
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        
        row = index.row()
        col = index.column()

        if row >= len(self._data):
            return False

        col_info = self._columns[col]
        if not col_info.get('editable', False):
            return False

        field_name = col_info['name']
        item = self._data[row]

        # првкерка на изменение значения
        old_value = getattr(item, field_name, None)
        if old_value == value:
            return True   # ничего не меняем, сигнал не испускаем

        # Преобразование типа (если нужно)
        try:
            target_type = col_info.get('type')
            if target_type is not None and value is not None:
                if target_type == int:
                    try:
                        value = int(value)
                    except ValueError as e:
                        self.logger.error(f"Ошибка преобразования в int {e}")
                        return False
                    
                elif target_type == datetime.date and isinstance(value, str):
                    # ожидается строка в формате YYYY-MM-DD
                    # from datetime import date
                    value = datetime.date.fromisoformat(value)

                elif target_type == datetime.time and isinstance(value, str):
                    # from datetime import time
                    value = datetime.time.fromisoformat(value)

                # и т.д. – можно расширить
        except (ValueError, TypeError) as e:            
            self.logger.error(f"Ошибка преобразования типа {e}")
            return False  # не удалось преобразовать

        setattr(item, field_name, value)
        self.dataChanged.emit(index, index, [role])
        self.row_modified.emit(row)

        self.logger.debug(f"Изменено поле {field_name} в строке {row}, новое значение: {value}")
        return True

    def set_row_color(self, row: int, color: QColor):
        """Устанавливает цвет фона для строки."""
        if 0 <= row < len(self._data):
            self._row_colors[row] = color
            top_left = self.index(row, 0)
            bottom_right = self.index(row, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.BackgroundRole])

    def clear_row_colors(self):
        """Очищает все установленные цвета строк."""
        self._row_colors.clear()
        if self.rowCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.BackgroundRole])

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def headerData(
        self, 
        section: int, 
        orientation: Qt.Orientation, 
        role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """
        Возвращает заголовок для секции таблицы.

        :param section: номер секции
        :type section: int
        :param orientation: ориентация заголовка (Qt.Orientation.Horizontal или Qt.Orientation.Vertical)
        :type orientation: Qt.Orientation
        :param role: роль данных (необязательный, по умолчанию - Qt.ItemDataRole.DisplayRole)
        :type role: int
        :return: заголовок для секции, если ориентация - Qt.Orientation.Horizontal и роль - Qt.ItemDataRole.DisplayRole, иначе - None
        :rtype: Any
        """

        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._columns[section]['title']
        
        return None

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Возвращает флаги для ячейки (например, ItemIsEditable, если ячейка является редактируемой).
        
        :param index: индекс ячейки
        :type index: QModelIndex
        :return: флаги для ячейки
        :rtype: Qt.ItemFlags
        """
        flags = super().flags(index)
        if index.isValid():
            col = index.column()
            if self._columns[col].get('editable', False):
                flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def sort(
        self, 
        column: int, 
        order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ):
        """
        Сортирует данные по указанной колонке.
        Вызывается прокси-моделью или напрямую, если сортировка включена.
        """
        self.layoutAboutToBeChanged.emit()
        col_info = self._columns[column]
        field_name = col_info['name']
        reverse = (order == Qt.SortOrder.DescendingOrder)

        # Функция для получения значения сортировки
        def key_func(obj):
            val = getattr(obj, field_name, None)
            # Обработка None – помещаем в конец или начало
            return (val is not None, val)

        self._data.sort(key=key_func, reverse=reverse)
        self.layoutChanged.emit()

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def update_data(self, new_data: List[Any]):
        """
        Полностью обновляет данные модели.
        
        :param new_data: новый список данных
        :type new_data: List[Any]
        """

        self.beginResetModel()
        self._data = new_data
        self.clear_row_colors()
        self.endResetModel()

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def get_item_at_row(self, row: int) -> Optional[Any]:
        """
        Возвращает DTO, соответствующий указанной строке модели. (по индексу строки)
        
        :param row: номер строки
        :type row: int
        :return: DTO, если строка существует, None иначе
        :rtype: Optional[Any]
        """

        if 0 <= row < len(self._data):
            return self._data[row]
        
        return None
    
    def add_row(self, dto: Any) -> int:
        """
        Добавляет новую строку в конец модели.
        Возвращает индекс добавленной строки.
        """

        row = len(self._data)
        self.beginInsertRows(QModelIndex(), row, row)
        self._data.append(dto)
        self.endInsertRows()
        # Новая строка считается изменённой (для подсветки)
        self.row_modified.emit(row)
        return row

    def remove_row(self, row: int) -> Optional[Any]:
        """
        Удаляет строку из модели и возвращает удалённый DTO.
        Используется для временного удаления (без вызова сервиса).
        """

        if row < 0 or row >= len(self._data):
            return None
        
        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._data.pop(row)
        self.endRemoveRows()
        return removed

    def update_row(self, row: int, new_dto: Any):
        """
        Заменяет DTO в указанной строке на новый.
        Используется после сохранения изменений.
        """

        if row < 0 or row >= len(self._data):
            return
        
        self._data[row] = new_dto
        # Уведомляем об изменении всей строки
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])