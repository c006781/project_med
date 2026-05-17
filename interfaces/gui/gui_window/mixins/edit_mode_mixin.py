# interfaces/gui/gui_window/mixins/edit_mode_mixin.py

"""
Миксин для включения/выключения режима редактирования.
"""

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QMessageBox
# from PySide6.QtGui import QColor


class EditModeMixin:
    """
    Предоставляет методы для переключения режима редактирования,
    сохранения и отмены изменений.
    """


    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        """Кэш статусов для сущностей (entity_id -> status)."""
        if not hasattr(self, '_logger'):
            self._logger = AppLogger.get_instance(
                name='gui.EditModeMixin',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        return self._logger


    @property
    def _saving_in_progress(self) -> bool:
        if not hasattr(self, '__saving_in_progress'):
            self.__saving_in_progress = False # флаг для защиты от реентерабельности
        return self.__saving_in_progress

    @_saving_in_progress.setter
    def _saving_in_progress(self, value):
        self.__saving_in_progress = value



    def toggle_edit_mode(self, enable: bool):
        """Включает или выключает режим редактирования."""
        if enable == self.edit_mode:
            return
        
        if not enable and self._has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Yes:
                if not self._save_all_changes_impl():
                    return
                
            elif reply == QMessageBox.StandardButton.No:
                self._discard_all_changes()

            else:
                return
            
        self._set_edit_mode(enable)

    def is_edit_mode(self) -> bool:
        return getattr(self, 'edit_mode', False)

    def save_all_changes(self) -> bool:
        """Публичный метод – обёртка, предотвращающая повторный вход."""
        if self._saving_in_progress:
            self.logger.warning("save_all_changes уже выполняется, повторный вызов игнорирован")
            return False
        
        self._saving_in_progress = True
        try:
            return self._save_all_changes_impl()
        
        finally:
            self._saving_in_progress = False

    def _save_all_changes_impl(self) -> bool:
        """Сохраняет все изменения в БД. Возвращает True при успехе."""

        if not self._has_unsaved_changes():
            return True
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Сохранить все изменения?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return False
    
        try:
            self._save_new_rows()
            self._save_modified_rows()
            self._save_deleted_rows()
            self.reload_data()
            self._exit_edit_mode()
            QMessageBox.information(self, "Успех", "Изменения сохранены.")

            return True
        
        except Exception as e:
            self.logger.exception(f"Ошибка сохранения: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")

            return False

    def cancel_all_changes(self):
        """Отменяет все изменения и перезагружает данные."""
        self._discard_all_changes()
        self.reload_data()
        self._exit_edit_mode()

    def _has_unsaved_changes(self) -> bool:
        """
        Возвращает True, если есть несохранённые изменения:
        - новые строки (new_rows)
        - удалённые строки (deleted_ids)
        - изменённые строки (modified_ids)
        """
        
        return bool(self.modified_ids or self.deleted_ids or self.new_rows)

    def _discard_all_changes(self):
        self.modified_ids.clear()
        self.deleted_ids.clear()
        self.new_rows.clear()
        self._clear_drafts()
        self.source_model.clear_row_colors()

    def _set_edit_mode(self, enable: bool):
        self.edit_mode = enable
        self.source_model.set_checkbox_column_visible(enable)
        self._update_ui_for_edit_mode(enable)

    def _exit_edit_mode(self):
        if self.edit_mode:
            # self.toggle_edit_mode(False)

            # Выходим без диалога, так как изменения уже сохранены (или отменены)
            self._set_edit_mode(False)

    def _save_new_rows(self):
        raise NotImplementedError

    def _save_modified_rows(self):
        raise NotImplementedError

    def _save_deleted_rows(self):
        raise NotImplementedError

    def reload_data(self):
        """Перезагружает данные – должен быть реализован в наследнике."""

        raise NotImplementedError

    def _clear_drafts(self):
        """Очищает черновики – переопределяется в AppointmentListPage."""
        pass