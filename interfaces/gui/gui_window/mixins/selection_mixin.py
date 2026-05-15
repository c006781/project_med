# interfaces/gui/gui_window/mixins/selection_mixin.py
"""
Миксин для управления выделением строк (обычное выделение и чекбоксы).
"""

from typing import List, Set, Optional, Any


class SelectionMixin:
    """
    Предоставляет методы для работы с выделением строк.
    """

    @property
    def selected_dto(self):
        return self._selected_dto if hasattr(self, '_selected_dto') else None

    @selected_dto.setter
    def selected_dto(self, value):
        self._selected_dto = value

    def get_selected_entity_ids(self) -> Set[int]:
        """Возвращает множество ID выбранных сущностей (обычное выделение + чекбоксы)."""

        selected = self._get_selected_ids_from_view()
        checkbox = self._get_selected_checkbox_ids()
        return selected.union(checkbox)

    def is_selection_empty(self) -> bool:
        """Проверяет, есть ли выбранные строки."""
        return len(self.get_selected_entity_ids()) == 0

    def get_current_selected_dto(self) -> Optional[Any]:
        # """Возвращает DTO текущей выделенной строки (обычное выделение)."""
        """Возвращает DTO текущей выделенной строки (первый выделенный, если их несколько)."""
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
    
    def  _get_source_index_or_proxy_model (self, proxy_index):

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
        """Выделяет строку с указанным ID. Возвращает True при успехе."""
        row = self._find_row_by_id(entity_id)
        if row >= 0:
            self._set_current_row(row)
            return True
        return False

    def clear_selection(self):
        """Снимает всё выделение и чекбоксы."""
        self.table_view.clearSelection()
        self._clear_checkboxes()

    def _store_current_row(self) -> int:
        """Сохраняет индекс текущей строки (для декоратора preserve_selection)."""
        row = self.table_view.currentIndex().row()
        self._saved_row = row
        return row

    def _restore_current_row(self, row: int = None):
        """Восстанавливает сохранённую строку."""
        if row is None:
            row = getattr(self, '_saved_row', -1)
        if row >= 0 and row < self.source_model.rowCount():
            self._set_current_row(row)
        else:
            self._select_first_row()
        self._saved_row = -1

    def _select_first_row(self):
        if self.source_model.rowCount() > 0:
            self._set_current_row(0)

    def _set_current_row(self, row: int):
        proxy_index = self.source_model.index(row, 0)
        if proxy_index.isValid():
            self.table_view.setCurrentIndex(proxy_index)
            self.table_view.scrollTo(proxy_index)

    def _find_row_by_id(self, entity_id: int) -> int:
        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and getattr(dto, 'id', None) == entity_id:
                return row
        return -1

    def _get_selected_ids_from_view(self) -> Set[int]:
        """Возвращает множество ID, выделенных обычным выделением."""
        return {dto.id for dto in self._get_selected_dtos() if dto.id is not None}

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
        """Возвращает список DTO выделенных строк (обычное выделение)."""
        dtos = []
        for row in self._get_selected_rows_indices():
            dto = self.source_model.get_item_at_row(row)
            if dto:
                dtos.append(dto)

        return dtos

    def _get_selected_checkbox_ids(self) -> Set[int]:
        ids = set()
        # Если модель поддерживает получение состояния чекбокса
        if hasattr(self.source_model, 'get_checkbox_state'):
            for row in range(self.source_model.rowCount()):
                if self.source_model.get_checkbox_state(row):
                    dto = self.source_model.get_item_at_row(row)
                    if dto and dto.id is not None:
                        ids.add(dto.id)
        return ids

    def _clear_checkboxes(self):
        if hasattr(self.source_model, 'set_checkbox_state'):
            for row in range(self.source_model.rowCount()):
                self.source_model.set_checkbox_state(row, False)