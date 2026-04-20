# interfaces/gui/gui_window/widgets/advanced_filter_proxy_model.py

"""
Прокси-модель с поддержкой фильтрации по столбцам (текстовый поиск, выбор значений из списка) и общим текстовым фильтром.
"""

from typing import Optional, List, Dict, Any

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel

from PySide6.QtCore import (
    QSortFilterProxyModel, Qt, QModelIndex, Signal
)
from PySide6.QtWidgets import (
    # QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QHeaderView, 
    # QMessageBox, QTableView, 
    QAbstractItemView,
)

class AdvancedFilterProxyModel(QSortFilterProxyModel):
    """
    Прокси-модель с поддержкой фильтрации по столбцам (текстовый поиск,
    выбор значений из списка) и общим текстовым фильтром.
    """

    filtersChanged = Signal() # сигнал об изменении фильтров

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        super().__init__(parent)

         # логгер
        self.logger = AppLogger.get_instance(
            name = f"gui.AdvancedFilterProxyModel",
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

        # self._column_filters: Dict[int, Dict[str, Any]] = {}    # column -> filter info # номер столбца
        # self._global_text_filter: str = ""                      # общий текстовый фильтр

        self._filters: Dict[int, Dict[str, Any]] = {}   # column -> {active, operator, value, value2}  # номер столбца
        self._global_text_filter = ""                   # общий текстовый фильтр




    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_column_filter(
        self, 
        column: int, 
        operator: str, 
        value: Any = None, 
        value2: Any = None
    ):
        """Устанавливает расширенный фильтр для столбца."""
        if operator is None or operator == 'clear':
            self.clear_column_filter(column)
            return
        self._filters[column] = {
            'active': True,
            'operator': operator,
            'value': value,
            'value2': value2
        }
        self.invalidateFilter()
        self.filtersChanged.emit()

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def clear_column_filter(self, column: int) -> None:
        """
        Очищает фильтр для столбца.
        
        :param column: номер столбца
        """
        if column in self._filters:
            del self._filters[column]
            self.invalidateFilter()
            self.filtersChanged.emit()
    
    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )        
    def get_active_filters(self) -> Dict[int, Dict]:
        """Возвращает копию активных фильтров для отображения в FilterBar."""
        return self._filters.copy()
    
    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_column_filter_simple(self, column: int, filter_text: str = None, selected_values: list = None):
        if filter_text:
            self.set_column_filter(column, 'ilike', filter_text)
        elif selected_values:
            self.set_column_filter(column, 'in', selected_values)
        else:
            self.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def clear_all_filters(self) -> None:
        """
        Очищает все фильтры (фильтры для столбцов и общий текстовый фильтр).
        """
        self._filters.clear()
        self._global_text_filter = ""
        self.invalidateFilter()
        self.filtersChanged.emit()

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_global_text_filter(self, text: str) -> None:
        """
        Устанавливает общий текстовый фильтр.

        :param text: текст для поиска (необязательно)
        """
        self._global_text_filter = text.lower()
        self.invalidateFilter()

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """
        Определяет, проходит ли строка фильтр.

        Метод проверяет, является ли текст фильтра пустым. Если да, то возвращает True,
        потому что пустой текст фильтра соответствует любая строка.

        Затем он получает модель-источник и производится проверка наличия текста фильтра
        в данных модели. Если текст фильтра найден, то возвращает True.
        В противном случае возвращает False.

        :param source_row: Номер строки в модели-источнике (необязательный)
        :type source_row: int
        :param source_parent: Родительский объект из модели-источника (необязательный)
        :type source_parent: QModelIndex
        :return: True, если строка проходит фильтр, False в противном случае
        :rtype: bool
        """

        source_model = self.sourceModel()
        if not source_model:
            return True

        # Глобальный текстовый фильтр (ищет во всех столбцах)
        if self._global_text_filter:
            found = False
            for col in range(source_model.columnCount()):
                idx = source_model.index(source_row, col, source_parent)
                data = source_model.data(idx, Qt.DisplayRole)

                if data is not None and self._global_text_filter in str(data).lower():
                    found = True
                    break

            if not found:
                return False

        # Фильтры по столбцам
        for col, f in self._filters.items():
            idx = source_model.index(source_row, col, source_parent)
            data = source_model.data(idx, Qt.DisplayRole)
            if not self._evaluate_filter(data, f['operator'], f.get('value'), f.get('value2')):
                return False

        return True

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _evaluate_filter(self, data: Any, operator: str, value: Any, value2: Any = None) -> bool:
        """Применяет оператор к значению ячейки."""

        if data is None:
            data = ""

        # Для строковых операторов приводим к строке
        if operator == 'like':
            # регистрозависимый поиск
            return str(value) in str(data) if value is not None else False

        if operator == 'ilike':
            # регистронезависимый поиск
            return str(value).lower() in str(data).lower() if value is not None else False

        if operator == 'fuzzy':
            # нечёткий поиск (регистронезависимый, можно доработать)
            return str(value).lower() in str(data).lower() if value is not None else False
            
        # Числовые операторы
        if operator == 'eq':
            return data == value
        if operator == 'ne':
            return data != value
        if operator == 'gt':
            return data > value
        if operator == 'ge':
            return data >= value
        if operator == 'lt':
            return data < value
        if operator == 'le':
            return data <= value
        if operator == 'between':
            return value <= data <= value2
        if operator == 'in':
            return data in value if isinstance(value, list) else False
        if operator == 'is_null':
            return data is None or data == ""
        if operator == 'is_not_null':
            return data is not None and data != ""
        return True  # неизвестный оператор – пропускаем

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def data(
        self, 
        index: QModelIndex, 
        role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """
        Возвращает данные из модели-источника или из родительской модели,
        если роль не равен Qt.ItemDataRole.BackgroundRole.
        (Пробрасывает цвет фона от исходной модели)

        :param index: индекс ячейки
        :type index: QModelIndex
        :param role: роль данных (необязательно)
        :type role: int
        :return: данные из модели-источника или из родительской модели
        :rtype: Any
        """
        if role == Qt.ItemDataRole.BackgroundRole:
            # Пробрасываем цвет фона от исходной модели
            source_index = self.mapToSource(index)

            if source_index.isValid():
                return self.sourceModel().data(source_index, role)
            
        return super().data(index, role)
    
    @AppLogger.get_instance( 
        name = 'AdvancedFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def setData(self, index, value, role=Qt.EditRole):
        
        if role == Qt.CheckStateRole:
            source_index = self.mapToSource(index)
            if source_index.isValid():
                result = self.sourceModel().setData(source_index, value, role)
                if result:
                    # Уведомляем представление, что данные изменились
                    self.dataChanged.emit(index, index, [role])
                    # Принудительно обновляем виджет (если dataChanged недостаточно)
                    if self.parent() and hasattr(self.parent(), 'viewport'):
                        self.parent().viewport().update()
                return result
            
        return super().setData(index, value, role)

    # @AppLogger.get_instance(
    #     name = 'AdvancedFilterProxyModel',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def flags(self, index):
        source_index = self.mapToSource(index)
        if source_index.isValid():
            return self.sourceModel().flags(source_index)
        
        return super().flags(index)