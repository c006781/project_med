# interfaces/gui/gui_window/mixins/data_change_mixin.py
"""
Миксин для отслеживания изменённых/удалённых/новых строк.
"""

from typing import Set, Dict, Any
from PySide6.QtGui import QColor


class DataChangeMixin:
    """
    Предоставляет атрибуты для отслеживания изменений и методы для их обработки.
    """

    def __init__(self):
        self.modified_ids: Set[int] = set()
        self.deleted_ids: Set[int] = set()
        self.new_rows: Set[int] = set()
        self.original_data: Dict[int, Any] = {}

    def _on_row_modified(self, row: int):
        """Обработчик сигнала row_modified от модели."""
        
        dto = self.source_model.get_item_at_row(row)
        if dto is None:
            return
        if dto.id is None or dto.id < 0:
            # Новая строка (временный ID)
            if row not in self.new_rows:
                self.new_rows.add(row)
                self.source_model.set_row_color(row, QColor(200, 255, 200))
                self._update_save_button_state()
            return
        original = self.original_data.get(row)
        if original and dto.model_dump() == original.model_dump():
            self._remove_from_modified(dto.id)
        else:
            self._add_to_modified(dto.id)
        self._update_row_color(row)

    def _add_to_modified(self, entity_id: int):
        if entity_id not in self.modified_ids:
            self.modified_ids.add(entity_id)
            self._update_save_button_state()

    def _remove_from_modified(self, entity_id: int):
        if entity_id in self.modified_ids:
            self.modified_ids.discard(entity_id)
            self._update_save_button_state()

    def _mark_for_deletion(self, entity_id: int):
        if entity_id not in self.deleted_ids:
            self.deleted_ids.add(entity_id)
            if entity_id in self.modified_ids:
                self.modified_ids.discard(entity_id)
            row = self._find_row_by_id(entity_id)
            if row >= 0:
                self.source_model.set_row_color(row, QColor(255, 200, 200))
            self._update_save_button_state()

    def _unmark_for_deletion(self, entity_id: int):
        if entity_id in self.deleted_ids:
            self.deleted_ids.discard(entity_id)
            row = self._find_row_by_id(entity_id)
            if row >= 0:
                self._update_row_color(row)
            self._update_save_button_state()

    def _add_new_row(self, dto: Any) -> int:
        row = self.source_model.add_row(dto)
        self.new_rows.add(row)
        self.source_model.set_row_color(row, QColor(200, 255, 200))
        self._update_save_button_state()
        return row

    def _remove_new_row(self, row: int):
        if row in self.new_rows:
            self.source_model.remove_row(row)
            self.new_rows.discard(row)
            self._update_save_button_state()

    def _update_row_color(self, row: int):
        dto = self.source_model.get_item_at_row(row)
        if dto is None:
            return
        if dto.id is None or dto.id < 0:
            color = QColor(200, 255, 200) if row in self.new_rows else QColor(255, 255, 255)
        else:
            if dto.id in self.deleted_ids:
                color = QColor(255, 200, 200)
            elif dto.id in self.modified_ids:
                color = QColor(255, 255, 180)
            else:
                color = QColor(255, 255, 255)
        self.source_model.set_row_color(row, color)

    def _update_save_button_state(self):
        has_changes = bool(self.modified_ids or self.deleted_ids or self.new_rows)
        if hasattr(self, 'save_changes_btn'):
            self.save_changes_btn.setEnabled(has_changes)
