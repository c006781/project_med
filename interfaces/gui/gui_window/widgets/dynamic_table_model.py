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
from typing import List, Dict, Any, Optional, Callable, Union, get_args, get_origin
# from datetime import date, time
import datetime

from app.utils.logger.logger import AppLogger


class DynamicTableModel(QAbstractTableModel):
    """
    Модель для отображения любых DTO-объектов в таблице.
    """

    # Сигнал, испускаемый при изменении данных в строке (передаётся индекс строки)
    row_modified = Signal(int) # (row) # сигнал, испускаемый при изменении данных в строке

    # checkbox_toggled = Signal(int, bool)   # (row, checked) # сигнал, испускаемый при изменении состояния чекбокса

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

        # для работы с чекбоксами 
        self._checkbox_column_enabled = False # флаг, указывающий, что в таблице есть колонка с чекбоксами
        self._checkbox_states = {} # словарь {row: bool} для хранения состояний чекбоксов

        self._field_by_column = {}          # номер колонки -> имя поля
        self._update_column_mapping()
        
    @AppLogger.get_instance(
        name = 'DynamicTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_field_name(self, column: int) -> str:
        """Возвращает имя поля для данного индекса колонки или None."""
        return self._field_by_column.get(column)

    @AppLogger.get_instance(
        name = 'DynamicTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_column_mapping(self):
        """Создаёт маппинг: индекс колонки модели -> имя поля (или '__checkbox__' для чекбокс-столбца)."""

        self._field_by_column.clear()
        offset = 1 if self._checkbox_column_enabled else 0

        if self._checkbox_column_enabled:
            self._field_by_column[0] = '__checkbox__'

        for i, col_info in enumerate(self._columns):
            self._field_by_column[i + offset] = col_info['name']

    @AppLogger.get_instance(
        name = 'DynamicTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_real_type(self, field_type):
        """Извлекает реальный тип из Optional/Union."""
        # from typing import get_origin, get_args, Union

        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)
            for arg in args:
                if arg is not type(None):
                    return arg
                
        return field_type
    
    @AppLogger.get_instance(
        name = 'DynamicTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_model_column_index(self, field_name: str) -> int:
        """
        Возвращает реальный индекс колонки в модели (с учётом чекбокс-столбца)
        по имени поля. Если поле не найдено, возвращает -1.
        """
        # for idx, col in enumerate(self._columns):
        #     if col['name'] == field_name:
        #         # Если чекбокс-столбец активен, он находится в позиции 0,
        #         # значит реальные колонки начинаются с индекса 1.
        #         return idx + (1 if self._checkbox_column_enabled else 0)
        
        for col, name in self._field_by_column.items():
            if name == field_name:
                return col
        return -1     

    @AppLogger.get_instance(
        name = 'DynamicTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_column_visible(self, visible: bool):
        """Включает/выключает столбец чекбоксов."""
        if self._checkbox_column_enabled == visible:
            return
        
        self.beginResetModel()
        self._checkbox_column_enabled = visible

        if not visible:
            self._checkbox_states.clear()
        
        self._update_column_mapping() # обновляем маппинг индекса колонки -> имя поля

        self.endResetModel()
        
    @AppLogger.get_instance(
        name = 'DynamicTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_state(self, row: int, checked: bool):
        """Устанавливает состояние чекбокса для строки (source row)."""
        if not self._checkbox_column_enabled:
            return
        
        self._checkbox_states[row] = checked
        # Уведомляем об изменении только столбца 0
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [Qt.CheckStateRole])

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
        """Возвращает количество строк в таблице."""
        return len(self._data)

    # @AppLogger.get_instance(
    #     name = 'DynamicTableModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def columnCount(self, parent=QModelIndex()) -> int:
        """
        Возвращает количество столбцов в таблице.
        Если в таблице есть колонка с чекбоксами, то она учитывается.
        :return: количество столбцов
        :rtype: int
        """

        base = len(self._columns)
        return base + (1 if self._checkbox_column_enabled else 0)

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

        """
        Возвращает данные из модели для указанного индекса и роли.
        
        :param index: индекс ячейки
        :type index: QModelIndex
        :param role: роль данных (необязательно)
        :type role: int
        :return: данные из модели
        :rtype: Any
        
        Роли поддерживаются:
            - Qt.ItemDataRole.DisplayRole (по умолчанию)
            - Qt.ItemDataRole.EditRole
            - Qt.ItemDataRole.BackgroundRole
            - Qt.ItemDataRole.TextAlignmentRole
            - Qt.ItemDataRole.UserRole (для сортировки)
        """
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()

        field_name = self._get_field_name(col)
        if field_name is None:
            return None

        if field_name == '__checkbox__':
            if role == Qt.CheckStateRole:
                state = Qt.Checked if self._checkbox_states.get(row, False) else Qt.Unchecked
                # self.logger.debug(f"data: row={row}, CheckStateRole returning {state}")
                return state
            return None

        # # Сдвигаем реальные колонки, если чекбокс-столбец активен
        # actual_col = col - 1 if self._checkbox_column_enabled else col

        # # self.logger.debug(f'row: {row}, col: {col} result: {row >= len(self._data)}')

        # if actual_col < 0 or actual_col >= len(self._columns):
        #     return None

        # ----- Фоновый цвет строки -----
        if role == Qt.ItemDataRole.BackgroundRole:
            return self._row_colors.get(row)
        
        # item = self._data[row]
        # col_info = self._columns[actual_col]
        # field_name = col_info['name']
        # value = getattr(item, field_name, None)

        item = self._data[row]
        value = getattr(item, field_name, None)

        # ----- Отображение (DisplayRole) -----
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
        
        # ----- Редактирование (EditRole) -----
        if role == Qt.ItemDataRole.EditRole:
            # self.logger.debug(f'Qt.ItemDataRole.EditRole')
            # Для редактирования возвращаем сырое значение
            return value

        # ----- Выравнивание текста -----
        if role == Qt.ItemDataRole.TextAlignmentRole:
            # self.logger.debug(
            #     f"Qt.ItemDataRole.TextAlignmentRole result: {col_info.get('type') in (int, float)}"
            # )
            col_info = next((c for c in self._columns if c['name'] == field_name), None)
            # Числа выравниваем вправо, текст влево
            # if col_info.get('type') in (int, float):
            if col_info and col_info.get('type') in (int, float):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        # ----- Пользовательские данные (для сортировки) -----
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

        # self.logger.debug(
        #     f"setData: "
        #     f"role={role}, "
        #     f"value={value}, "
        #     f"not index.isValid ={not index.isValid}, "
        #     f"varole != Qt.ItemDataRole.EditRolelue={role != Qt.ItemDataRole.EditRole}"
        # )
        if not index.isValid():
            return False
        # if role != Qt.ItemDataRole.EditRole:
        #     return False
        
        row = index.row()
        col = index.column()
        
        field_name = self._get_field_name(col)

        # self.logger.debug(
        #     f"setData called: "
        #     f"row={row}, "
        #     f"col={col}, "
        #     f"role={role}, "
        #     f"value={value}"
        # )

        # ----- Чекбокс-столбец (только если включён) -----
        # if self._checkbox_column_enabled and col == 0 and role == Qt.ItemDataRole.CheckStateRole:
        if field_name == '__checkbox__' and role == Qt.CheckStateRole:

            checked = (value == Qt.Checked.value) # нынешняя метка
            old_state = self._checkbox_states.get(row, False)

            if old_state != checked:
                self._checkbox_states[row] = checked
                # Эмитим с обеими ролями, чтобы перерисовать
                self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.CheckStateRole])

            return True
        
        # Для остальных ролей (EditRole и др.) продолжаем
        if role != Qt.EditRole:
            return False

        # # Сдвигаем реальные колонки, если чекбокс-столбец активен
        # actual_col = col - 1 if self._checkbox_column_enabled else col
        # if actual_col < 0 or actual_col >= len(self._columns):
        #     return False

        if role != Qt.ItemDataRole.EditRole:
            return False
        
        # Найти информацию о колонке по имени поля
        col_info = next((c for c in self._columns if c['name'] == field_name), None)
        if not col_info or not col_info.get('editable', False):
            return False

        # col_info = self._columns[actual_col]
        # if not col_info.get('editable', False):
        #     return False

        field_name = col_info['name']
        item = self._data[row]

        # првкерка на изменение значения
        old_value = getattr(item, field_name, None)

        if old_value == value:
            return True   # ничего не меняем, сигнал не испускаем

        # Преобразование типа
        target_type = col_info.get('type')
        if target_type is not None and value is not None:
            real_type = self._get_real_type(target_type)
            try:
                if target_type is not None and value is not None:
                    real_type = self._get_real_type(target_type)

                    if real_type == int:
                        value = int(value)
                        
                    elif real_type == datetime.date and isinstance(value, str):
                        # ожидается строка в формате YYYY-MM-DD
                        # from datetime import date
                        value = datetime.date.fromisoformat(value)

                    elif real_type == datetime.time and isinstance(value, str):
                        # from datetime import time
                        value = datetime.time.fromisoformat(value)

                    # и т.д. – можно расширить
            except (ValueError, TypeError) as e:            
                self.logger.error(f"Ошибка преобразования типа для поля {field_name}: {e}")
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

        # Только горизонтальные заголовки
        if orientation != Qt.Orientation.Horizontal:
            return None

        # Если чекбокс-столбец активен и запрошен первый столбец (section == 0)
        field_name = self._get_field_name(section)
        if role == Qt.DisplayRole:
            if field_name == '__checkbox__':
                return ""   # пустой заголовок для чекбокс-столбца
        # if self._checkbox_column_enabled and section == 0:
        #     if role == Qt.ItemDataRole.DisplayRole:
        #         return ""  # Пустой заголовок, чтобы не было текста
        #     # Для специальных ролей можно вернуть идентификатор (например, для контекстного меню)
        #     # if role == Qt.UserRole:
        #     #     return "checkbox_header"
        #     return None

        # # Сдвигаем реальные колонки, если чекбокс-столбец активен
        # actual_section = section - 1 if self._checkbox_column_enabled else section
        # if actual_section < 0 or actual_section >= len(self._columns):
        #     return None

        # if role == Qt.ItemDataRole.DisplayRole:
        #     return self._columns[actual_section]['title']

        col_info = next((c for c in self._columns if c['name'] == field_name), None)
        if col_info:
            return col_info['title']

        # Для роли выравнивания (можно задать выравнивание по центру для чекбокс-столбца, но здесь не нужно)
        # if role == Qt.TextAlignmentRole and self._checkbox_column_enabled and section == 0:
        #     return Qt.AlignCenter

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

        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        row = index.row()
        col = index.column()

        # self.logger.debug(
        #     f"setData: "
        #     f"row = {row}, "
        #     f"col = {col}, "
        #     f"not index.isValid ={not index.isValid}, "
        #     f"row >= len(self._data) = {row >= len(self._data)}"
        # )

        if row >= len(self._data):
            return Qt.ItemFlag.NoItemFlags

        # ----- Чекбокс-столбец (только если включён) -----
        field_name = self._get_field_name(col)
        if field_name == '__checkbox__':
        # if self._checkbox_column_enabled and col == 0:
            # Чекбокс всегда можно включить/выключить, но только если редактирование разрешено глобально?
            # В нашем случае чекбоксы активны только в режиме редактирования,
            # но модель не знает о режиме – управление видимостью и доступностью через edit_mode
            # Поэтому просто даём флаги чекбокса и включения.
            return Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        # # Сдвигаем реальные колонки, если чекбокс-столбец активен
        # actual_col = col - 1 if self._checkbox_column_enabled else col
        # if actual_col < 0 or actual_col >= len(self._columns):
        #     return Qt.ItemFlag.NoItemFlags

        col_info = next((c for c in self._columns if c['name'] == field_name), None)
        if not col_info:
            return Qt.NoItemFlags

        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if col_info.get('editable', False):
            flags |= Qt.ItemIsEditable

        # # Проверяем, редактируема ли колонка
        # if self._columns[actual_col].get('editable', False):
        #     flags |= Qt.ItemFlag.ItemIsEditable

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