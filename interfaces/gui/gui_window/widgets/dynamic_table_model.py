# -*- coding: utf-8 -*-
"""
interfaces/gui/gui_window/widgets/dynamic_table_model.py

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
    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def __init__(self, data: List[Any], columns: List[Dict], parent=None):
        """
        :param data: список DTO (объекты с атрибутами, соответствующими колонкам)
        :param columns: описание колонок (см. выше)
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
        return True

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
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
        """Полностью обновляет данные модели."""
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def get_item_at_row(self, row: int) -> Optional[Any]:
        """Возвращает DTO по индексу строки."""
        if 0 <= row < len(self._data):
            return self._data[row]
        return None