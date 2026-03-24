# interfaces/gui/gui_window/widgets/advanced_filter_proxy_model.py

from typing import Optional, List, Dict, Any

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: Dict[int, Dict[str, Any]] = {}   # column -> filter info
        self._global_text_filter: str = ""                     # общий текстовый фильтр

    # def _setup_table(self):
    #     """
    #     Устанавливает таблицу с настройками сортировки и фильтрации.

    #     Создает таблицу с возможностью сортировки и фильтрации.
    #     Таблица отображает данные из списка self.current_data, а также
    #     позволяет сортировать данные по любому из столбцов.

    #     Далее создается экземпляр класса AdvancedFilterProxyModel,
    #     который является проксирующим моделью данных. Он получает модель
    #     данных self.source_model и позволяет фильтровать данные по любому из столбцов.

    #     Наконец, для таблицы self.table_view устанавливаются моделью данных
    #     self.proxy_model и настройки заголовка столбцов.
    #     """
        
    #     self.table_view = FilterTableView()
    #     self.table_view.setSortingEnabled(True)
    #     self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    #     self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    #     self.table_view.doubleClicked.connect(self._on_row_double_clicked)

    #     self.source_model = DynamicTableModel(self.current_data, self.columns)
    #     self.proxy_model = AdvancedFilterProxyModel()  # <-- новая прокси-модель
    #     self.proxy_model.setSourceModel(self.source_model)
    #     self.table_view.setModel(self.proxy_model)

    #     # Настройка заголовка
    #     header = self.table_view.horizontalHeader()
    #     if hasattr(header, 'set_get_unique_values_func'):
    #         header.set_get_unique_values_func(self.get_unique_values_for_column)
    #         header.filter_requested.connect(self.on_filter_requested)
    #         header.filter_clear_requested.connect(self.on_filter_clear)

    #     # Настройка ширины колонок
    #     header.setStretchLastSection(True)
    #     header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    # def on_filter_requested(self, column: int, operator: str, value):
    #     """
    #     Обработка сигнала фильтрации от заголовка.

    #     Когда пользователь нажимает на кнопку "Фильтр" в заголовке таблицы,
    #     то генерируется сигнал filter_requested, который передает информацию о запросе
    #     фильтрации.

    #     :param column: номер столбца, для которого нужно установить фильтр
    #     :param operator: оператор фильтрации (eq, like, fuzzy, in)
    #     :param value: значение для сравнения (зависит от оператора)

    #     В зависимости от оператора, мы устанавливаем фильтр для столбца column.
    #     Если operator == 'in', то value – список выбранных строк, которые должны проходить фильтр.
    #     Если operator == 'contains', то value – подстрока, которая должна быть найдена в столбце column.
    #     Если operator == 'clear', то мы сбрасываем фильтр для столбца column.
    #     """
    #     if operator == 'in':
    #         # value – список выбранных строк
    #         self.proxy_model.set_column_filter(column, selected_values=value)
    #     elif operator == 'contains':
    #         self.proxy_model.set_column_filter(column, filter_text=value)
    #     elif operator == 'clear':
    #         self.proxy_model.clear_column_filter(column)

    # def on_filter_clear(self, column: int):
    #     """Сброс фильтра для колонки."""
    #     self.proxy_model.clear_column_filter(column)

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

    def clear_all_filters(self) -> None:
        """
        Очищает все фильтры (фильтры для столбцов и общий текстовый фильтр).
        """
        self._column_filters.clear()
        self._global_text_filter = ""
        self.invalidateFilter()

    def set_global_text_filter(self, text: str) -> None:
        """
        Устанавливает общий текстовый фильтр.

        :param text: текст для поиска (необязательно)
        """
        self._global_text_filter = text.lower()
        self.invalidateFilter()

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