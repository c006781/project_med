# interfaces/gui/gui_window/mixins/selection_mixin.py
"""
Миксин для управления выделением строк в таблице.

Основные возможности:
    - Получение ID выбранных сущностей (обычное выделение + чекбоксы).
    - Получение DTO текущей (первой) выделенной строки.
    - Сохранение и восстановление текущей строки (для декораторов).
    - Поиск строки по ID сущности.
    - Сброс выделения и чекбоксов.

Требования к классу-наследнику:
    - Должен иметь атрибуты:
        * self.table_view (QTableView) – таблица, для которой управляется выделение.
        * self.source_model (BaseTableModel) – модель данных (должна поддерживать
          методы get_item_at_row, set_checkbox_state, get_checkbox_state).
        * self.proxy_model (QSortFilterProxyModel, опционально) – прокси-модель,
          используемая в таблице. Если есть, методы автоматически преобразуют индексы.
    - Желательно наличие метода _update_selection_state (вызывается при изменении выделения).

Атрибуты (свойства, создаваемые лениво):
    _saved_row (int): Сохранённый индекс строки (используется в _store_current_row).
    selected_dto (Optional[Any]): DTO текущей выделенной строки (кэшируется).

Примечание:
    Все методы, возвращающие индексы строк, работают с исходной моделью (source_model).
    При наличии прокси-модели индексы преобразуются автоматически.
"""

from typing import (
    List, Set, 
    Optional, Any,
)


class SelectionMixin:
    """
    Предоставляет методы для работы с выделением строк (обычное выделение и чекбоксы).
    """
    
    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------


    @property
    def _saved_row(self) -> int:
        """Возвращает сохранённый индекс строки (используется в _store_current_row)."""
        if not hasattr(self, '__saved_row'):
            self.__saved_row = -1 # сохранённый индекс строки?
        return self.__saved_row

    @_saved_row.setter
    def _saved_row(self, value: int):
        self.__saved_row = value

    @property
    def selected_dto(self):
        """Возвращает DTO текущей выделенной строки (кэшированное значение)."""
        if not hasattr(self, '_selected_dto'):
            self._selected_dto = None
        return self._selected_dto

    @selected_dto.setter
    def selected_dto(self, value):
        self._selected_dto = value

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------


    def get_selected_entity_ids(self) -> Set[int]:
        """"
        Возвращает множество ID сущностей, выбранных в таблице.

        Учитывает как обычное выделение (клик + Shift/Ctrl), так и чекбоксы,
        если они активны в режиме редактирования.

        Returns:
            set[int]: Множество ID выбранных записей.
        """

        selected = self._get_selected_ids_from_view()
        checkbox = self._get_selected_checkbox_ids()

        return selected.union(checkbox)

    def is_selection_empty(self) -> bool:
        """
        Проверяет, есть ли выбранные строки.

        Returns:
            bool: True, если ни одна строка не выбрана (ни обычным выделением, ни чекбоксами), иначе False.
        """

        return len(self.get_selected_entity_ids()) == 0

    def get_current_selected_dto(self) -> Optional[Any]:
        """
        Возвращает DTO текущей выделенной строки.

        Если выделено несколько строк, возвращается DTO первой из них (в порядке выделения).
        Если выделения нет, возвращается None.

        Returns:
            Optional[Any]: DTO выбранной строки или None.
        """

        dtos = self._get_selected_dtos()

        return dtos[0] if dtos else None

        # selection_model = self.table_view.selectionModel()
        # if not selection_model or not selection_model.hasSelection():
        #     return None
        
        # indexes = selection_model.selectedIndexes()
        # if not indexes:
        #     return None
        
        # proxy_index = indexes[0]
        # # # Если есть прокси-модель (у нас её нет в новой реализации), преобразуем
        # # source_index = proxy_index
        # # if hasattr(self, 'proxy_model') and self.proxy_model:
        # #     source_index = self.proxy_model.mapToSource(proxy_index)
        
        # source_index = self._get_source_index_or_proxy_model(proxy_index) # Если есть прокси-модель (у нас её нет в новой реализации), преобразуем

        # return self.source_model.get_item_at_row(source_index.row())
    
    # ------------------------------------------------------------------
    # Защищённые методы (вспомогательные)
    # ------------------------------------------------------------------

    def  _get_source_index_or_proxy_model (self, proxy_index):
        """
        Преобразует индекс из прокси-модели в индекс исходной модели.

        Если прокси-модель не используется (self.proxy_model отсутствует или равен None),
        возвращает переданный индекс без изменений.

        Args:
            proxy_index: Индекс в прокси-модели (QModelIndex).

        Returns:
            QModelIndex: Индекс в исходной модели.
        """

        # Если есть прокси-модель (у нас её нет в новой реализации), преобразуем
        source_index = proxy_index

        if (
            hasattr(self, 'proxy_model')
        # ) and (
        #     hasattr(self, 'proxy_model')
        ) and (
            self.proxy_model
        ):
            source_index = self.proxy_model.mapToSource(proxy_index)

        return source_index

    def select_by_id(self, entity_id: int) -> bool:
        """
        Выделяет строку с указанным ID сущности.

        Args:
            entity_id (int): ID записи для выделения.

        Returns:
            bool: True, если строка найдена и выделена, иначе False.
        """

        row = self._find_row_by_id(entity_id)
        if row >= 0:
            self._set_current_row(row)

            return True
        
        return False

    def clear_selection(self):
        """Снимает всё выделение (обычное выделение и чекбоксы)."""
        self.table_view.clearSelection()
        self._clear_checkboxes()

    # ------------------------------------------------------------------
    # Методы для сохранения/восстановления строки (используются декораторами)
    # ------------------------------------------------------------------

    def _store_current_row(self) -> int:
        """
        Запоминает текущую строку (индекс в прокси-модели) и возвращает его.

        Используется декоратором preserve_selection.

        Returns:
            int: Индекс текущей строки (или -1, если нет текущей).
        """

        row = self.table_view.currentIndex().row()
        self._saved_row = row

        return row

    def _restore_current_row(self, row: int = None):
        """
        Восстанавливает сохранённую строку.

        Если передан конкретный row, восстанавливает его.
        Иначе использует self._saved_row.
        Если сохранённой строки нет или она вне диапазона, выбирает первую строку.

        Args:
            row (int, optional): Индекс строки для восстановления. По умолчанию None.
        """

        if row is None:
            row = getattr(self, '_saved_row', -1)

        if row >= 0 and row < self.source_model.rowCount():
            self._set_current_row(row)
            
        else:
            self._select_first_row()

        self._saved_row = -1

    def _select_first_row(self):
        """Выбирает первую строку в таблице, если она существует."""
        
        if self.source_model.rowCount() > 0:
            self._set_current_row(0)

    def _set_current_row(self, row: int):
        """
        Устанавливает текущую строку в таблице (прокручивает к ней).

        Args:
            row (int): Индекс строки в исходной модели.
        """

        index = self.source_model.index(row, 0)
        if index.isValid():
            self.table_view.setCurrentIndex(index)
            self.table_view.scrollTo(index)

    def _find_row_by_id(self, entity_id: int) -> int:
        """
        Ищет строку в исходной модели по ID сущности.

        Args:
            entity_id (int): ID сущности.

        Returns:
            int: Индекс строки или -1, если не найдено.
        """

        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and getattr(dto, 'id', None) == entity_id:

                return row
            
        return -1
    
    # ------------------------------------------------------------------
    # Методы для получения выбранных строк/ID
    # ------------------------------------------------------------------


    def _get_selected_ids_from_view(self) -> Set[int]:
        """
        Возвращает множество ID, выделенных обычным выделением (клик + Shift/Ctrl).

        Returns:
            set[int]: ID выбранных сущностей.
        """

        return {
            dto.id 
            for dto in self._get_selected_dtos() 
            if dto.id is not None
        }

        # ids = set()
        # selection_model = self.table_view.selectionModel()
        # if selection_model:
        #     for proxy_index in selection_model.selectedRows(0):
        #         # source_index = proxy_index
        #         # if hasattr(self, 'proxy_model') and self.proxy_model:
        #         #     source_index = self.proxy_model.mapToSource(proxy_index)

        #         source_index = self._get_source_index_or_proxy_model(proxy_index) # Если есть прокси-модель (у нас её нет в новой реализации), преобразуем
                
        #         dto = self.source_model.get_item_at_row(source_index.row())
        #         if dto and dto.id is not None:
        #             ids.add(dto.id)
        # return ids

    def _get_selected_rows_indices(self) -> List[int]:
        """
        Возвращает список индексов строк (в исходной модели), выделенных в таблице.

        Учитывает только обычное выделение (не чекбоксы).

        Returns:
            List[int]: Список индексов строк.
        """

        selection_model = self.table_view.selectionModel()
        if not selection_model:
            return []
        
        rows = []
        for proxy_index in selection_model.selectedRows(0):
            source_index = self._get_source_index_or_proxy_model(proxy_index)
            if source_index.isValid():
                rows.append(source_index.row())
                
        return rows

    def _get_selected_dtos(self) -> List[Any]:
        """
        Возвращает список DTO, соответствующих выделенным строкам (обычное выделение).

        Returns:
            List[Any]: Список DTO (порядок соответствует порядку выделения).
        """

        dtos = []
        for row in self._get_selected_rows_indices():
            dto = self.source_model.get_item_at_row(row)
            if dto:
                dtos.append(dto)

        return dtos

    def _get_selected_checkbox_ids(self) -> Set[int]:
        """
        Возвращает множество ID сущностей, у которых установлены чекбоксы.

        Использует метод get_checkbox_state модели (если он реализован).

        Returns:
            set[int]: ID выбранных через чекбоксы сущностей.
        """

        ids = set()

        # Используем метод get_checkbox_state, который теперь гарантированно есть в BaseTableModel

        # Если модель поддерживает получение состояния чекбокса
        # if hasattr(self.source_model, 'get_checkbox_state'): # Используем метод get_checkbox_state, который теперь гарантированно есть в BaseTableModel
        for row in range(self.source_model.rowCount()):
            if self.source_model.get_checkbox_state(row):
                dto = self.source_model.get_item_at_row(row)
                if dto and dto.id is not None:
                    ids.add(dto.id)
                    
        return ids

    def _clear_checkboxes(self):
        """
        Снимает все чекбоксы в таблице (если модель поддерживает set_checkbox_state).
        """
        if hasattr(self.source_model, 'set_checkbox_state'):
            for row in range(self.source_model.rowCount()):
                self.source_model.set_checkbox_state(row, False)