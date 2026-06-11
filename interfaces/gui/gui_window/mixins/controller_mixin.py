# interfaces/gui/gui_window/mixins/controller_mixin.py
"""
Миксин, реализующий интерфейс IDynamicListController.
"""

from typing import Set

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.controllers.list_controller import IDynamicListController


class ControllerMixin(IDynamicListController):
    """
    Реализует методы IDynamicListController, делегируя другим миксинам.
    """ 

    @AppLogger.get_instance(
        name='ControllerMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_row(self) -> None:
        if not self.is_edit_mode():
            return
        self._add_inline_row()

    @AppLogger.get_instance(
        name='ControllerMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def delete_selected_rows(self) -> None:
        if not self.is_edit_mode():
            return
        self._delete_selected_rows()

    @AppLogger.get_instance(
        name='ControllerMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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