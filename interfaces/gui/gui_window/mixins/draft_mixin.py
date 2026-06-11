# interfaces/gui/gui_window/mixins/draft_mixin.py

"""
Миксин для работы с черновиками фото.
"""


from typing import Optional

from app.utils.logger import AppLogger


class DraftMixin: 
    """
    Миксин для поддержки черновиков в страницах списка с правой панелью.

    Требует наличия в классе-наследнике:
        - self.selected_dto
        - self._draft_photos (словарь)
        - self.photo_widget (PhotoUploaderWidget)
        - self.logger
    """

    @AppLogger.get_instance(
        name='DraftMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _save_current_draft(self):
        """Сохраняет черновик текущего приёма (фото). Переопределяется в наследниках."""
        if not self.selected_dto:
            return
        
        self._draft_photos[self.selected_dto.id] = self.photo_widget.dump_state()

    @AppLogger.get_instance(
        name='DraftMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _load_draft_for_appointment(self, appointment_id: int, dto) -> None:
        """Загружает черновик или свежие фото для указанного приёма."""
        self.photo_widget.clear()
        if appointment_id in self._draft_photos:
            self.photo_widget.load_state(self._draft_photos[appointment_id])
        else:
            self.photo_widget.set_existing_photos(dto.photos or [])

    @AppLogger.get_instance(
        name='DraftMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _has_draft_changes_for_appointment(self, appointment_id: int) -> bool:
        """Проверяет наличие черновиков для приёма."""
        if appointment_id not in self._draft_photos:
            return False
        draft = self._draft_photos[appointment_id]
        
        return bool(draft.get('pending_photos') or draft.get('deleted_photo_ids') or draft.get('modified_photo_ids'))

    @AppLogger.get_instance(
        name='DraftMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _clear_drafts(self, appointment_id: Optional[int] = None) -> None:
        """Очищает черновики для одного приёма или всех."""
        if appointment_id is None:
            self._draft_photos.clear()
        else:
            self._draft_photos.pop(appointment_id, None)
