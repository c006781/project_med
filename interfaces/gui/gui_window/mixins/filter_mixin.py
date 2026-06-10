# interfaces/gui/gui_window/mixins/filter_mixin.py
"""
Миксин для серверной фильтрации и сортировки страниц списка.

**Основные возможности:**
    - Хранение фильтров по столбцам в `_column_filters`.
    - Хранение глобального текстового поиска в `_global_search_text`.
    - Перестроение единого дерева фильтров (`_rebuild_filters_tree`) и вызов `reload_with_filters`.
    - Отображение активных фильтров в панели `FilterBar` через `_refresh_filter_bar`.
    - Обработка сортировки через заголовки таблицы (`set_sorting`, `set_multi_sorting`).
    - **При активном fuzzy-фильтре сортировка полностью отключается** (игнорируются вызовы `set_sorting`/`set_multi_sorting`).

**Требования к классу-наследнику:**
    - Должен иметь атрибуты:
        * `source_model` (экземпляр `PaginatedTableModel` или аналогичный с методом
          `get_field_name_at_visible_column`)
        * `service` (сервис с методами `get_page_filtered` и `get_unique_values`)
        * `field_configs` (словарь конфигурации полей)
        * `reload_with_filters(filters_tree)` – метод для перезагрузки с фильтрами
        * `reload_with_order_by(order_by)` – метод для перезагрузки с сортировкой
    - Опционально:
        * `filter_bar` (экземпляр `FilterBar`) – для отображения активных фильтров

**Атрибуты (создаются лениво):**
    - `_column_filters` (Dict[int, Dict]): {видимый_индекс_столбца: {'logic': 'AND'/'OR', 'conditions': [...]}}
    - `_global_search_text` (str): Текст для глобального поиска (поиск по всем строковым DATA-столбцам).

**Методы:**
    - `setup_filtering(filter_bar, table_view)` – инициализация фильтрации.
    - `set_sorting(column, order)` – установка сортировки по одному столбцу (игнорируется при fuzzy).
    - `set_multi_sorting(specs)` – установка многоколоночной сортировки (игнорируется при fuzzy).
    - `set_global_search(text)` – установка глобального текстового фильтра.
    - `_rebuild_filters_tree()` – перестраивает дерево `_current_filters` из `_column_filters` и `_global_search_text`.
    - `_refresh_filter_bar()` – обновляет отображение чипов в FilterBar.

**Примечание:**
    Миксин **не использует** прокси модель (`QSortFilterProxyModel`). Все операции фильтрации и сортировки
    идут напрямую через сервис (с перезагрузкой страницы).
"""

from typing import (
    # Dict, 
    Any, Dict, List, Optional, Tuple, Union, get_args, get_origin,
)

from app.utils.logger.logger import AppLogger

from app.dependencies import get_note_service

from interfaces.gui.gui_window.widgets.table_column import ColumnType
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

    @property
    def _global_search_text(self) -> str:
        try:
            return self.__global_search_text
        except AttributeError as e:
            self.__global_search_text:str = ""
        return self.__global_search_text

    @_global_search_text.setter
    def _global_search_text(self, value: str):
        self.__global_search_text = value

    @property
    def _column_filters(self) -> Dict[int, Dict[str, Any]]:
        """Словарь фильтров для каждого столбца: {видимый_индекс: {'logic': 'AND'/'OR', 'conditions': [...]}}."""

        try:
            return self.__column_filters
        except AttributeError as e:
            self.__column_filters = {}
        return self.__column_filters

    @_column_filters.setter
    def _column_filters(self, value: Dict[int, Dict[str, Any]]):
        self.__column_filters = value

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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
            # # Локальная сортировка – передаём спецификацию с одним столбцом
            # self.source_model.set_sort_specs([(column, order)])
            # Локальная сортировка отключена – игнорируем
            # Можно также показать всплывающее сообщение (опционально)
            # QMessageBox.information(self, "Сортировка недоступна", "При активном нечётком поиске сортировка не поддерживается.")
            
            return

        # Серверная сортировка – формируем order_by как список
        direction = '-' if order == Qt.DescendingOrder else ''
        order_by = [f"{direction}{col_name}"]

        self._current_order_by = order_by
        self.reload_with_order_by(order_by)

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_multi_sorting(self, specs: List[Tuple[int, Qt.SortOrder]]) -> None:
        """
        Устанавливает многоколоночную сортировку.
        
        :param specs: список кортежей (видимый_индекс_столбца, порядок)
        """

        if not specs:
            return
        
        if self._has_fuzzy_filter():
            # # Локальная сортировка
            # self.source_model.set_sort_specs(specs)
            # Локальная сортировка отключена – игнорируем
            # Можно также показать всплывающее сообщение (опционально)
            # QMessageBox.information(self, "Сортировка недоступна", "При активном нечётком поиске сортировка не поддерживается.")
            
            return

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

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_sort_indicator_changed(self, logical_index: int, order: Qt.SortOrder) -> None:
        """
        Обработчик сигнала сортировки от заголовка таблицы.
        Вызывается при клике пользователя на заголовок столбца.
        """
        self.set_sorting(logical_index, order)

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

            # Новый сигнал для очистки глобального поиска
            if hasattr(filter_bar, 'clear_global_search'):
                filter_bar.clear_global_search.connect(self._clear_global_search)

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_global_in_block(self):
        """
        Очищает глобальный поиск (сбрасывает текст и перезагружает данные).

        Отключает сигналы поля поиска (self.search_edit), чтобы при программной
        очистке не вызвать лишнюю перезагрузку страницы.
        """
        
        self._global_search_text = ""

        # Также очищаем поле ввода, если оно есть
        if hasattr(self, 'search_edit') and self.search_edit:
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_global_search(self):
        """Очищает глобальный поиск (сбрасывает текст и перезагружает данные)."""

        self._clear_global_in_block()

        self._apply_filters_and_refresh()

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_column_filter_requested(self, column: int, logic: str, conditions: list):

        if not self._get_column_name_by_visible_index(column):
            return
        # Сохраняем фильтр для столбца
        if conditions:
            self._column_filters[column] = {'logic': logic, 'conditions': conditions}
        else:
            self._column_filters.pop(column, None)
            
        self._apply_filters_and_refresh()   

        # """
        # Обработчик сигнала фильтрации от заголовка таблицы.

        # Преобразует условия фильтра в дерево (через `convert_ui_filters_to_sql`)
        # и вызывает `reload_with_filters`.

        # Args:
        #     column: Номер столбца (видимый индекс).
        #     logic: 'AND' или 'OR' – логика объединения условий внутри столбца.
        #     conditions: Список словарей, каждый с ключами 'operator', 'value', 'value2'.

        # Note:
        #     Если передан fuzzy-оператор, он не преобразуется в SQL, но может быть
        #     обработан сервисом отдельно (см. `get_page_filtered`).
        # """
            
        # col_name = self._get_column_name_by_visible_index(column)
        # if not col_name:
        #     return
        
        # tree = convert_ui_filters_to_sql(
        #     {
        #         column: {
        #             'logic': logic, 
        #             'conditions': conditions, 
        #         }
        #     }, {
        #         column: col_name
        #     }
        # )
        # self._current_filters = tree
        # self.reload_with_filters(self._current_filters)

        # self._update_filter_bar()
    
    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )    
    def _get_real_type(self, field_type):
        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)
            non_none = [arg for arg in args if arg is not type(None)]

            if non_none:
                return non_none[0]
            
        return field_type

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _rebuild_filters_tree(self):
        """
        Собирает дерево фильтров из `self._column_filters` и `self._global_search_text`,
        затем вызывает `reload_with_filters`.

        **Порядок объединения:**
            - Узлы от разных столбцов объединяются через `AND`.
            - Узел глобального поиска (если есть) добавляется как отдельное `OR`-условие
                (поиск по всем строковым DATA-столбцам).
            - Если есть несколько узлов, они помещаются в корневой `{'and': [...]}`.

        **Какие поля включаются в глобальный поиск:**
            - Невиртуальные строковые поля (например, `last_name`, `phone`).
            - Виртуальные поля-заметки (поля, у которых в field_configs есть ключ `is_note`).
            - Системные столбцы и числовые/дата-поля исключаются.

        После обновления `self._current_filters` вызывает `reload_with_filters`,
        что приводит к загрузке первой страницы отфильтрованных данных.
        """
        
        # if not self._column_filters:
        #     self._current_filters = None
        #     self.reload_with_filters(None)
        #     return

        nodes = []
        # Фильтры по столбцам
        for col, filter_def in self._column_filters.items():
            col_name = self._get_column_name_by_visible_index(col)
            if col_name:
                tree = convert_ui_filters_to_sql(
                    {col: filter_def},
                    {col: col_name}
                )
                if tree:
                    nodes.append(tree)

        # Контекстные фильтры (например, patient_id, appointment_id)
        context = getattr(self, '_context_params', {})
        for key, value in context.items():
            # Игнорируем служебные ключи (начинаются с __)
            if key.startswith('__'):
                continue
            # Добавляем как условие "column = value"
            nodes.append({'column': key, 'operator': 'eq', 'value': value})

        # Глобальный поиск
        if self._global_search_text:
            text_filters = []
            # Проходим по всем DATA-столбцам строкового типа
            # if hasattr(self.source_model, '_columns'):
            #     for col in self.source_model._columns:
            if hasattr(self.source_model, 'get_columns'):
                for col in self.source_model.get_columns():
                    # if col.column_type == ColumnType.DATA and col.data_type == str:
                    real_type = self._get_real_type(col.data_type)
                    if real_type == str:
                        config = self.field_configs.get(col.field_name, {})
                        # Включаем невиртуальные поля ИЛИ виртуальные поля-заметки
                        if (
                            not config.get('virtual', False)
                        ) or (
                            config.get('is_note')
                        ):
                            text_filters.append({
                                'column': col.field_name,
                                'operator': 'ilike',
                                'value': self._global_search_text
                            })
                if text_filters:
                    nodes.append({'or': text_filters})

        # Формируем дерево
        if not nodes:
            temp = None

        elif len(nodes) == 1:
            temp = nodes[0]

        else:
            temp = {'and': nodes}
        
        self._current_filters = temp
        self.reload_with_filters(self._current_filters)

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_filters_and_refresh(self):
        # Перестраиваем дерево фильтров и обновляем панель
        self._rebuild_filters_tree()   # перестроить дерево и перезагрузить данные
        self._refresh_filter_bar()      # обновить отображение чипов

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _refresh_filter_bar(self):
        """
        Обновляет панель активных фильтров (`FilterBar`) на основе `self._column_filters`.

        Для каждого столбца с активным фильтром получает заголовок из модели таблицы
        и вызывает `self.filter_bar.update_filters(column_filters, column_titles)`.
        Если фильтров нет, панель скрывается.

        **Важно:** Глобальный поиск (`self._global_search_text`) не отображается в FilterBar
        (у него нет чипов), так как он представляет собой отдельное условие, не привязанное
        к конкретному столбцу.
        """
            
        if not hasattr(self, 'filter_bar'):
            return
        
        if not self._column_filters:
            self.filter_bar.setVisible(False)
            return
        
        # Получаем заголовки столбцов для отображения в чипах
        column_titles = {}
        for col in self._column_filters.keys():
            title = self.table_view.model().headerData(col, Qt.Horizontal, Qt.DisplayRole)
            column_titles[col] = title if title else f"Столбец {col}"

        # self.filter_bar.update_filters(self._column_filters, column_titles)
        # # self.filter_bar.setVisible(True) # убрал. есть в filter_bar.update_filters

        self.filter_bar.update_filters(
            self._column_filters,
            column_titles,
            global_search_text=self._global_search_text
        )

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_column_filter(self, column: int):
        """Очищает фильтр для указанного столбца."""

        if column in self._column_filters:
            del self._column_filters[column]

        self._apply_filters_and_refresh()

        # if not self._column_filters:
        #     return
            
        # self._column_filters.clear()
        # self._apply_filters_and_refresh()
        
        # if not self._current_filters:
        #     return

        # col_name = self._get_column_name_by_visible_index(column)
        # if not col_name:
        #     return
        
        # # Удаляем все узлы, относящиеся к этому столбцу (рекурсивно)
        # def remove_column(node):
        #     if isinstance(node, dict):
        #         if node.get('column') == col_name:
        #             return None  # удалить
                
        #         # Пройти по значениям
        #         for k, v in list(node.items()):
        #             new_v = remove_column(v)

        #             if new_v is None:
        #                 del node[k]
        #             else:
        #                 node[k] = new_v

        #         return node if node else None
            
        #     elif isinstance(node, list):
        #         new_list = [remove_column(item) for item in node if remove_column(item) is not None]

        #         return new_list if new_list else None
            
        #     return node
        
        # new_filters = remove_column(self._current_filters)

        # if new_filters is None or (isinstance(new_filters, list) and not new_filters):
        #     self._current_filters = None
        # else:
        #     self._current_filters = new_filters

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_all_filters(self):
        """Очищает все фильтры."""
        if self._column_filters:
            self._column_filters.clear()

        # self._global_search_text = ""
        self._clear_global_in_block()
        self._apply_filters_and_refresh()

        # if not self._current_filters:
        #     return
        
        # self._current_filters = None
        # self.reload_with_filters(self._current_filters)
        # self._update_filter_bar()

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_global_search(self, text: str):
        """
        Устанавливает глобальный текстовый фильтр (поиск по всем текстовым полям).

        Создаёт дерево фильтров с оператором 'ilike' для каждого строкового поля
        (не виртуального) и вызывает `reload_with_filters`.

        Args:
            text: Строка поиска. Если пустая – фильтр сбрасывается.
        """
        
        self._global_search_text = text
        self._apply_filters_and_refresh()

        # if hasattr(self, 'save_btn') and self.save_btn:


        # if not text:
        #     self._current_filters = None

        # else:
        #     text_filters = []
        #     # for col_name, config in self.field_configs.items():
        #     #     if config.get('type') == str and not config.get('virtual', False):
        #     #         text_filters.append(
        #     #             {
        #     #                 'column': col_name, 
        #     #                 'operator': 'ilike', 
        #     #                 'value': text
        #     #             }
        #     #         )
        #     for col in self.source_model.columns:
        #         # Проверяем: это DATA-столбец, тип str, не виртуальное поле
        #         if (
        #             col.column_type == ColumnType.DATA and 
        #             col.data_type == str and 
        #             not self.field_configs.get(col.field_name, {}).get('virtual', False)
        #         ):
        #             text_filters.append({
        #                 'column': col.field_name,
        #                 'operator': 'ilike',
        #                 'value': text
        #             })

        #     if text_filters:
        #         self._current_filters = {'or': text_filters}

        #     else:
        #         self._current_filters = None

        # self.reload_with_filters(self._current_filters)

        # # self._update_filter_bar()
        # self._refresh_filter_bar()

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_context_filters(self) -> List[Dict[str, Any]]:
        """
        Преобразует _context_params в список SQL-фильтров.
        Параметры, начинающиеся с '__' (служебные), игнорируются.
        """
        filters = []
        for key, value in self._context_params.items():
            if key.startswith('__'):
                continue
            # Предполагаем, что значение может быть любого типа, и оператор 'eq'
            filters.append({'column': key, 'operator': 'eq', 'value': value})
        return filters

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_filter_removed(self, column: int):
        self._clear_column_filter(column)

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_filter_condition_removed(self, column: int, condition_index: int) -> None:
        """Обработчик удаления конкретного условия из фильтра (при множественных условиях)."""

        # # Пока просто очищаем весь фильтр столбца
        # self._clear_column_filter(column)

        if column not in self._column_filters:
            return
        
        filter_def = self._column_filters[column]
        conditions = filter_def.get('conditions', [])

        if 0 <= condition_index < len(conditions):

            # Удаляем условие по индексу
            del conditions[condition_index]

            # Если условий не осталось – удаляем весь фильтр столбца
            if not conditions:
                del self._column_filters[column]

            else:
                # Обновляем словарь фильтра (логика не меняется)
                self._column_filters[column] = {
                    'logic': filter_def['logic'],
                    'conditions': conditions
                }

            # Перестраиваем дерево фильтров и обновляем панель
            self._apply_filters_and_refresh()

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='FilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    # def _update_filter_bar(self):
    #     if not hasattr(self, 'filter_bar'):
    #         return
        
    #     # TODO: преобразовать _current_filters в формат для отображения в FilterBar
    #     # Пока просто скрываем или показываем
    #     self.filter_bar.setVisible(self._current_filters is not None)