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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        super().__init__(parent)

         # логгер
        self.logger = AppLogger.get_instance(
            name = f"gui.AdvancedFilterProxyModel",
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        self._column_filters: Dict[int, Dict[str, Any]] = {}  # column -> {active, operator, value, value2}  # номер столбца

        self._global_text_filter = ""                   # общий текстовый фильтр


    @AppLogger.get_instance(
        name='AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def remove_condition(self, column: int, condition_index: int) -> None:
        """
        Удаляет одно условие из фильтра для указанного столбца.

        :param column: номер столбца
        :param condition_index: индекс условия в списке conditions (0-based)
        """
        if column not in self._column_filters:
            self.logger.warning(f"Попытка удалить условие из столбца {column}, для которого нет фильтра")
            return

        filter_def = self._column_filters[column]
        conditions = filter_def.get('conditions', [])
        if condition_index < 0 or condition_index >= len(conditions):
            self.logger.warning(f"Индекс условия {condition_index} вне диапазона (0-{len(conditions)-1}) для столбца {column}")
            return

        # Удаляем условие
        del conditions[condition_index]

        # Если условий не осталось – удаляем весь фильтр для столбца
        if not conditions:
            self.clear_column_filter(column)
        else:
            # Иначе перезаписываем фильтр (логика не меняется)
            self._column_filters[column] = {
                'logic': filter_def['logic'],
                'conditions': conditions
            }
            self.invalidateFilter()
            self.filtersChanged.emit()

        self.logger.debug(f"Удалено условие {condition_index} из столбца {column}, осталось {len(conditions)} условий")

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_column_filter(
        self,
        column: int,
        logic: str,                           # 'AND' или 'OR'
        conditions: List[Dict[str, Any]]      # список условий
    ):
        """
        Устанавливает сложный фильтр для столбца.

        :param column: номер столбца
        :param logic: 'AND' (все условия должны выполняться) или 'OR' (хотя бы одно)
        :param conditions: список словарей, каждый с ключами:
            - 'operator' (str): eq, ne, gt, ge, lt, le, like, ilike, in, between, is_null, is_not_null
            - 'value' (Any): значение для сравнения
            - 'value2' (Any, optional): второе значение для between
        """
        if not conditions:
            self.clear_column_filter(column)
            return

        self._column_filters[column] = {
            'logic': logic,
            'conditions': conditions
        }
        self.invalidateFilter()
        self.filtersChanged.emit()

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def clear_column_filter(self, column: int) -> None:
        """
        Очищает фильтр для столбца.
        
        :param column: номер столбца
        """
        if column in self._column_filters:
            del self._column_filters[column]
            self.invalidateFilter()
            self.filtersChanged.emit()
    
    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )        
    def get_active_filters(self) -> Dict[int, Dict]:
        """Возвращает копию для отображения в FilterBar (может быть преобразована в плоский список чипов)."""
        return self._column_filters.copy()
    
    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_column_filter_simple(self, column: int, filter_text: str = None, selected_values: list = None):
        if filter_text:
            self.set_column_filter(column, 'AND', [{'operator': 'ilike', 'value': filter_text}])
        elif selected_values:
            self.set_column_filter(column, 'AND', [{'operator': 'in', 'value': selected_values}])
        else:
            self.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def clear_all_filters(self) -> None:
        """
        Очищает все фильтры (фильтры для столбцов и общий текстовый фильтр).
        """
        if self._column_filters:
            self._column_filters.clear()
            self._global_text_filter = ""
            self.invalidateFilter()
            self.filtersChanged.emit()

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
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

        # Глобальный текстовый фильтр
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
        for col, filter_def in self._column_filters.items():
            idx = source_model.index(source_row, col, source_parent)
            data = source_model.data(idx, Qt.DisplayRole)
            logic = filter_def['logic']
            conditions = filter_def['conditions']
            results = []
            for cond in conditions:
                op = cond['operator']
                val = cond.get('value')
                val2 = cond.get('value2')
                results.append(self._evaluate_filter(data, op, val, val2))
            if logic == 'AND':
                for res in results:
                    if not res:
                        return False
            else:  # OR
                for res in results:
                    if res:
                        break
                else:
                    return False
        return True

    @AppLogger.get_instance(
        name = 'AdvancedFilterProxyModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _evaluate_filter(self, data: Any, operator: str, value: Any, value2: Any = None) -> bool:
        """Применяет оператор к значению ячейки."""

        if data is None:
            data = ""

        # Для строковых операторов приводим к строке
        if operator == 'like':
            if value is None:
                return False
            # регистрозависимый поиск
            return str(value) in str(data) if value is not None else False

        if operator == 'ilike':
            if value is None:
                return False
            # регистронезависимый поиск
            return str(value).lower() in str(data).lower() if value is not None else False

        if operator == 'fuzzy':
            if value is None:
                return False
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

    # @AppLogger.get_instance(
    #     name = 'AdvancedFilterProxyModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
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
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def flags(self, index):
        source_index = self.mapToSource(index)
        if source_index.isValid():
            return self.sourceModel().flags(source_index)
        
        return super().flags(index)