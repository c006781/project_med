# interfaces/gui/gui_window/mixins/filter_mixin.py
"""
Миксин для фильтрации: заголовки таблицы, строка фильтров, глобальный поиск.
"""

from typing import Dict, List, Optional

from interfaces.gui.gui_window.utils.filter_converter import convert_ui_filters_to_sql


class FilterMixin:
    """
    Предоставляет методы для работы с фильтрацией.
    """

    def setup_filtering(self, filter_bar, table_view):
        """Подключает фильтр-бар и заголовок таблицы."""
        self.filter_bar = filter_bar
        self.table_view = table_view

        # Подключаем сигналы от заголовка
        header = self.table_view.horizontalHeader()
        if hasattr(header, 'filter_requested'):
            header.filter_requested.connect(self._on_column_filter_requested)
            header.filter_clear_requested.connect(self._clear_column_filter)

        if hasattr(header, 'set_get_unique_values_func'):
            header.set_get_unique_values_func(self._get_unique_values_for_column)

        # Подключаем сигналы от фильтр-бара
        if filter_bar:
            filter_bar.filter_removed.connect(self._on_filter_removed)
            filter_bar.all_filters_cleared.connect(self._clear_all_filters)
            if hasattr(filter_bar, 'filter_condition_removed'):
                filter_bar.filter_condition_removed.connect(self._on_filter_condition_removed)

    def _on_column_filter_requested(self, column: int, logic: str, conditions: list):
        """Обработчик сигнала от заголовка таблицы."""
        col_name = self._get_column_name_by_visible_index(column)
        if not col_name:
            return
        tree = convert_ui_filters_to_sql({column: {'logic': logic, 'conditions': conditions}}, {column: col_name})
        self._current_filters = tree
        self.reload_with_filters(self._current_filters)
        self._update_filter_bar()

    def _clear_column_filter(self, column: int):
        """Очищает фильтр для столбца."""
        # Упрощённо: сбрасываем все фильтры
        self._current_filters = None
        self.reload_with_filters(self._current_filters)
        self._update_filter_bar()

    def _clear_all_filters(self):
        self._current_filters = None
        self.reload_with_filters(self._current_filters)
        self._update_filter_bar()

    def set_global_search(self, text: str):
        """Глобальный поиск по всем текстовым полям."""
        if not text:
            self._current_filters = None
        else:
            text_filters = []
            for col_name, config in self.field_configs.items():
                if config.get('type') == str and not config.get('virtual', False):
                    text_filters.append({'column': col_name, 'operator': 'ilike', 'value': text})
            if text_filters:
                self._current_filters = {'or': text_filters}
            else:
                self._current_filters = None
        self.reload_with_filters(self._current_filters)
        self._update_filter_bar()

    def _on_filter_removed(self, column: int):
        self._clear_column_filter(column)

    def _on_filter_condition_removed(self, column: int, condition_index: int):
        # Пока просто очищаем весь фильтр столбца
        self._clear_column_filter(column)

    def _get_unique_values_for_column(self, visible_column: int) -> List[str]:
        col_name = self._get_column_name_by_visible_index(visible_column)
        if not col_name:
            return []
        return self.service.get_unique_values(col_name)

    def _get_column_name_by_visible_index(self, visible_index: int) -> Optional[str]:
        return self.source_model.get_field_name_at_visible_column(visible_index)

    def _update_filter_bar(self):
        if not hasattr(self, 'filter_bar'):
            return
        
        # TODO: преобразовать _current_filters в формат для отображения в FilterBar
        # Пока просто скрываем или показываем
        self.filter_bar.setVisible(self._current_filters is not None)