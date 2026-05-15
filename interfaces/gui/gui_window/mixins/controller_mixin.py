# interfaces/gui/gui_window/mixins/controller_mixin.py
"""
Миксин, реализующий интерфейс IDynamicListController.
"""

from typing import Set

from interfaces.gui.gui_window.controllers.list_controller import IDynamicListController


class ControllerMixin(IDynamicListController):
    """
    Реализует методы IDynamicListController, делегируя другим миксинам.
    """ 

    def add_row(self) -> None:
        if not self.is_edit_mode():
            return
        self._add_inline_row()

    def delete_selected_rows(self) -> None:
        if not self.is_edit_mode():
            return
        self._delete_selected_rows()

    def cancel_selected_rows_changes(self) -> None:
        if not self.is_edit_mode():
            return
        
        self._cancel_selected_rows_changes()

    # def save_all_changes(self) -> bool:  # бесконечная рекурсия 
    #     # return self.save_all_changes() # из EditModeMixin
    #     return super().save_all_changes()  # вызов из EditModeMixin

    # def refresh_data(self) -> None:
    #     self.reload_data()

    # def get_selected_entity_ids(self) -> Set[int]:# рекурсия
    #     # return self.get_selected_entity_ids()   # из SelectionMixin
    #     return super().get_selected_entity_ids()  # вызов из SelectionMixin

    # def is_selection_empty(self) -> bool: # рекурсия 
    #     # return self.is_selection_empty()# из SelectionMixin
    #     return super().is_selection_empty()