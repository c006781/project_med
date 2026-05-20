# interfaces/gui/gui_window/mixins/filter_mixin.py
"""
Миксин для серверной фильтрации и сортировки страниц списка.

Предоставляет методы для:
    - Преобразования фильтров из UI в дерево условий и вызова `reload_with_filters()`.
    - Обработки сортировки через заголовки таблицы (`reload_with_order_by()`).
    - Получения уникальных значений для столбцов (через `service.get_unique_values`).
    - Управления панелью активных фильтров (`FilterBar`).

Требует наличия в классе-наследнике:
    - `self._current_filters` (дерево фильтров).
    - `self._current_order_by` (список полей для сортировки).
    - `self.reload_with_filters(filters_tree)` (метод перезагрузки данных).
    - `self.reload_with_order_by(order_by)` (метод перезагрузки с сортировкой).
    - `self.service` (сервис с методами `get_unique_values`).
    - `self.source_model` (модель таблицы).
    - `self._get_column_name_by_visible_index(visible_index)` – возвращает имя поля.

Примечание: данный миксин не использует прокси-модель и полностью совместим с `PaginatedListPage`.
"""

from typing import (
    # Dict, 
    List, Optional, Tuple,
)

from app.dependencies import get_note_service
from interfaces.gui.gui_window.utils.filter_converter import convert_ui_filters_to_sql

from PySide6.QtCore import (
    Qt,
)

class FilterMixin:
    """
    Миксин для серверной фильтрации и сортировки в страницах списка.

    **Предназначение:**
        Обеспечивает фильтрацию данных через перезагрузку страницы с новыми параметрами
        (`reload_with_filters`), а не через прокси-модель. Сортировка также выполняется
        на сервере через `reload_with_order_by`.

    **Требования к классу-наследнику:**
        - Должен иметь атрибуты:
            * `source_model` (экземпляр `PaginatedTableModel` или аналогичный с методом
              `get_field_name_at_visible_column`)
            * `service` (сервис с методами `get_page_filtered` и `get_unique_values`)
            * `field_configs` (словарь конфигурации полей)
            * `_current_filters` (дерево фильтров, может быть None)
            * `_current_order_by` (список полей для сортировки, может быть None)
            * `reload_with_filters(filters_tree)` – метод для перезагрузки с фильтрами
            * `reload_with_order_by(order_by)` – метод для перезагрузки с сортировкой
        - Опционально:
            * `filter_bar` (экземпляр `FilterBar`) – для отображения активных фильтров

    **Примечание:**
        Этот миксин **не требует** `proxy_model`. Все операции идут напрямую через
        `source_model` и сервис. Совместим с `PaginatedListPage`.

    Args:
        filter_bar: Экземпляр FilterBar (создаётся в UIMixin).
        table_view: Экземпляр FilterTableView (создаётся в UIMixin).

    Raises:
        AttributeError: Если у table_view.horizontalHeader() нет сигналов
            `filter_requested` или `filter_clear_requested` (используется FilterHeaderView).

    Note:
        Этот метод должен вызываться после создания всех UI-компонентов,
        обычно в `__init__` страницы после `setup_ui()`.

    Example:
        >>> class MyListPage(PaginatedListPage, FilterMixin):
        ...     pass
        ...
        >>> page = MyListPage(...)
        >>> page.setup_filtering(page.filter_bar, page.table_view)
        >>> # Теперь фильтрация и сортировка через заголовки работают
    """

    def set_sorting(self, column: int, order: Qt.SortOrder) -> None:
        """
        Устанавливает сортировку по указанному столбцу.
       
            - Если есть fuzzy-фильтр: локальная сортировка уже загруженных данных.
            - Иначе: серверная сортировка (перезагрузка страницы с order_by).

        Args:
            column: Индекс видимого столбца (0-based).
            order: Порядок сортировки (AscendingOrder или DescendingOrder).
        """
        
        col_name = self._get_column_name_by_visible_index(column)
        if not col_name:
            return

        if self._has_fuzzy_filter():
            # Локальная сортировка – передаём спецификацию с одним столбцом
            self.source_model.set_sort_specs([(column, order)])

        else:
            # Серверная сортировка – формируем order_by как список
            direction = '-' if order == Qt.DescendingOrder else ''
            order_by = [f"{direction}{col_name}"]

            self._current_order_by = order_by
            self.reload_with_order_by(order_by)

    def set_multi_sorting(self, specs: List[Tuple[int, Qt.SortOrder]]) -> None:
        """
        Устанавливает многоколоночную сортировку.
        
        :param specs: список кортежей (видимый_индекс_столбца, порядок)
        """
        if not specs:
            return
        if self._has_fuzzy_filter():
            # Локальная сортировка
            self.source_model.set_sort_specs(specs)

        else:
            # Серверная сортировка: преобразуем в список строк
            order_by = []
            for col_idx, order in specs:
                col_name = self._get_column_name_by_visible_index(col_idx)
                if col_name:
                    direction = '-' if order == Qt.DescendingOrder else ''
                    order_by.append(f"{direction}{col_name}")

            if order_by:
                self._current_order_by = order_by
                self.reload_with_order_by(order_by)

    def _on_sort_indicator_changed(self, logical_index: int, order: Qt.SortOrder) -> None:
        """
        Обработчик сигнала сортировки от заголовка таблицы.
        Вызывается при клике пользователя на заголовок столбца.
        """
        self.set_sorting(logical_index, order)

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

        # sortIndicatorChanged испускается при клике на заголовок столбца
        header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

        # Подключаем сигналы от фильтр-бара
        if filter_bar:
            filter_bar.filter_removed.connect(self._on_filter_removed)
            filter_bar.all_filters_cleared.connect(self._clear_all_filters)
            if hasattr(filter_bar, 'filter_condition_removed'):
                filter_bar.filter_condition_removed.connect(self._on_filter_condition_removed)

    def _has_fuzzy_filter(self) -> bool:
        """
        Проверяет, есть ли в текущем дереве фильтров оператор 'fuzzy'.
        Рекурсивный обход.

        Returns:
            True, если хотя бы один узел содержит operator='fuzzy', иначе False.
        """

        if not self._current_filters:
            return False

        def check(node):
            if isinstance(node, dict):
                if node.get('operator') == 'fuzzy':
                    return True
                
                for value in node.values():
                    if check(value):
                        return True
                    
            elif isinstance(node, list):
                for item in node:
                    if check(item):
                        return True
                    
            return False

        return check(self._current_filters)

    def _on_column_filter_requested(self, column: int, logic: str, conditions: list):
        """
        Обработчик сигнала фильтрации от заголовка таблицы.

        Преобразует условия фильтра в дерево (через `convert_ui_filters_to_sql`)
        и вызывает `reload_with_filters`.

        Args:
            column: Номер столбца (видимый индекс).
            logic: 'AND' или 'OR' – логика объединения условий внутри столбца.
            conditions: Список словарей, каждый с ключами 'operator', 'value', 'value2'.

        Note:
            Если передан fuzzy-оператор, он не преобразуется в SQL, но может быть
            обработан сервисом отдельно (см. `get_page_filtered`).
        """
            
        col_name = self._get_column_name_by_visible_index(column)
        if not col_name:
            return
        
        tree = convert_ui_filters_to_sql(
            {
                column: {
                    'logic': logic, 
                    'conditions': conditions, 
                }
            }, {
                column: col_name
            }
        )
        self._current_filters = tree
        self.reload_with_filters(self._current_filters)

        self._update_filter_bar()


    def _clear_column_filter(self, column: int):
        """Очищает фильтр для указанного столбца."""

        if not self._current_filters:
            return
        
        col_name = self._get_column_name_by_visible_index(column)
        if not col_name:
            return
        
        # Удаляем все узлы, относящиеся к этому столбцу (рекурсивно)
        def remove_column(node):
            if isinstance(node, dict):
                if node.get('column') == col_name:
                    return None  # удалить
                
                # Пройти по значениям
                for k, v in list(node.items()):
                    new_v = remove_column(v)

                    if new_v is None:
                        del node[k]
                    else:
                        node[k] = new_v

                return node if node else None
            
            elif isinstance(node, list):
                new_list = [remove_column(item) for item in node if remove_column(item) is not None]

                return new_list if new_list else None
            
            return node
        
        new_filters = remove_column(self._current_filters)

        if new_filters is None or (isinstance(new_filters, list) and not new_filters):
            self._current_filters = None
        else:
            self._current_filters = new_filters


    def _clear_all_filters(self):
        """Очищает все фильтры."""

        if not self._current_filters:
            return
        
        self._current_filters = None
        self.reload_with_filters(self._current_filters)
        self._update_filter_bar()

    def set_global_search(self, text: str):
        """
        Устанавливает глобальный текстовый фильтр (поиск по всем текстовым полям).

        Создаёт дерево фильтров с оператором 'ilike' для каждого строкового поля
        (не виртуального) и вызывает `reload_with_filters`.

        Args:
            text: Строка поиска. Если пустая – фильтр сбрасывается.
        """
            
        if not text:
            self._current_filters = None

        else:
            text_filters = []
            for col_name, config in self.field_configs.items():
                if config.get('type') == str and not config.get('virtual', False):
                    text_filters.append(
                        {
                            'column': col_name, 
                            'operator': 'ilike', 
                            'value': text
                        }
                    )

            if text_filters:
                self._current_filters = {'or': text_filters}

            else:
                self._current_filters = None

        self.reload_with_filters(self._current_filters)

        self._update_filter_bar()

    def _on_filter_removed(self, column: int):
        self._clear_column_filter(column)

    def _on_filter_condition_removed(self, column: int, condition_index: int) -> None:
        """Обработчик удаления конкретного условия из фильтра (при множественных условиях)."""

        # Пока просто очищаем весь фильтр столбца
        self._clear_column_filter(column)

    def _get_unique_values_for_column(self, visible_column: int) -> List[str]:
        col_name = self._get_column_name_by_visible_index(visible_column)
        if not col_name:
            return []
        
        # Проверяем, является ли поле виртуальной заметкой
        config = self.field_configs.get(col_name, {})
        if config.get('virtual', False) and config.get('is_note'):
            note_service = get_note_service()
            if note_service and hasattr(note_service, 'get_unique_note_texts'):
                return note_service.get_unique_note_texts()
            
            return []
        
        # Обычное поле – запрос к БД через сервис
        return self.service.get_unique_values(col_name)

    def _get_column_name_by_visible_index(self, visible_index: int) -> Optional[str]:
        """Возвращает имя поля DTO для видимого столбца."""

        if hasattr(self.source_model, 'get_field_name_at_visible_column'):
            return self.source_model.get_field_name_at_visible_column(visible_index)
        # Fallback для старых моделей
        if hasattr(self.source_model, 'get_model_column_index'):
            for field_name in self.field_configs.keys():
                idx = self.source_model.get_model_column_index(field_name)
                if idx == visible_index:
                    return field_name
        return None

    def _update_filter_bar(self):
        if not hasattr(self, 'filter_bar'):
            return
        
        # TODO: преобразовать _current_filters в формат для отображения в FilterBar
        # Пока просто скрываем или показываем
        self.filter_bar.setVisible(self._current_filters is not None)