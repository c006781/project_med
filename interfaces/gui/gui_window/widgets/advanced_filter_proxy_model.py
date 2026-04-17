# interfaces/gui/gui_window/widgets/advanced_filter_proxy_model.py

"""
Прокси-модель с поддержкой фильтрации по столбцам (текстовый поиск, выбор значений из списка) и общим текстовым фильтром.
"""

from typing import Optional, List, Dict, Any

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel

from PySide6.QtCore import QSortFilterProxyModel, Qt, QModelIndex
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

        self._column_filters: Dict[int, Dict[str, Any]] = {}   # column -> filter info
        self._global_text_filter: str = ""                     # общий текстовый фильтр




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
            filter_text: Optional[str] = None, 
            selected_values: Optional[List[str]] = None
        ) -> None:
        """
        Устанавливает фильтр для столбца.
        :param column: номер столбца
        :param filter_text: подстрока для поиска (необязательно)
        :param selected_values: список строк, которые должны проходить фильтр (если не пуст)
        """
        if filter_text is None and selected_values is None:
            # удаляем фильтр
            if column in self._column_filters:
                del self._column_filters[column]
        else:
            self._column_filters[column] = {}
            if filter_text is not None:
                self._column_filters[column]['text'] = filter_text.lower()
            if selected_values is not None:
                self._column_filters[column]['values'] = set(selected_values)
        self.invalidateFilter()

    def clear_column_filter(self, column: int) -> None:
        """
        Очищает фильтр для столбца.
        
        :param column: номер столбца
        """
        if column in self._column_filters:
            del self._column_filters[column]
            self.invalidateFilter()


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
        self._column_filters.clear()
        self._global_text_filter = ""
        self.invalidateFilter()


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
        for col, filter_info in self._column_filters.items():
            idx = source_model.index(source_row, col, source_parent)
            data = source_model.data(idx, Qt.DisplayRole)
            if data is None:
                data = ""
            data_str = str(data)

            # Текстовый фильтр (подстрока)
            if 'text' in filter_info:
                if filter_info['text'] not in data_str.lower():
                    return False

            # Фильтр по списку значений
            if 'values' in filter_info and filter_info['values']:
                if data_str not in filter_info['values']:
                    return False

        return True
    
    # @AppLogger.get_instance(
    #     name = 'AdvancedFilterProxyModel',
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