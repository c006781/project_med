# interfaces/gui/gui_window/pages/paginated_photo_list_page.py
"""
Страница списка фотографий на базе PaginatedListPage.
Используется в новом фрейме с двумя таблицами (приёмы + фото).
"""

from typing import Optional

from app.utils.logger.logger import AppLogger

from app.dependencies import get_photo_service

from app.dto.dto_all import PhotoDTO
from app.dto.field_configs import PHOTO_CONFIG

from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage


class PaginatedPhotoListPage(PaginatedListPage):
    """
    Страница списка фотографий (одно фото на строку) с пагинацией,
    фильтрацией и черновиками. Предназначена для использования в связке
    с PaginatedAppointmentListPage.
    """

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        parent=None, 
        shared_registry=None, 
        show_controls=None,
        exclude_columns=None,
    ):
        if show_controls is None:
            show_controls = [
                'edit_mode_btn',
                'action_combo',
                'inline_action_combo',
                'save_btn',
                'search'
            ]


        if exclude_columns is None:
            exclude_columns = []

        exclude_columns = exclude_columns + ['appointment_id']

        super().__init__(
            service=get_photo_service(),
            dto_class=PhotoDTO,
            field_configs=PHOTO_CONFIG,
            page_title="Фотографии",
            add_action_text="Добавить фото",
            action_button_text=None,
            parent=parent,
            exclude_columns=exclude_columns,   # скрываем столбец ID приёма
            entity_type="photo",
            shared_registry=shared_registry,
            show_controls=show_controls
        )

        # # Отключаем обработку двойного клика на уровне страницы,
        # # потому что фото редактируется через делегат ImageThumbnailDelegate
        # self.action_requested.disconnect()

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_parent_id_for_new_row(self, dto) -> int: # в будущем перенести в PaginatedListPage и сделать диначическим
        
        """
        Возвращает ID родительской сущности для новой строки фото.

        Для фото родителем является приём (appointment). ID приёма должен быть передан
        в self._context_params под ключом 'appointment_id' (устанавливается родительским фреймом).

        Returns:
            ID приёма или None, если контекст не задан.
        """
        return self._context_params.get('appointment_id', None)

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_parent_id(self, child_id: int) -> Optional[int]:
        """
        Возвращает ID приёма (appointment_id) для фото.
        Используется для уведомления родителя об изменениях.
        """
        # Находим строку по ID фото в модели
        row = self._find_row_by_id(child_id)
        if row < 0:
            return None
        
        dto = self.source_model.get_item_at_row(row)
        if dto:
            return getattr(dto, 'appointment_id', None)
        
        return None
    
    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_parent_entity_type(self, child_id: int) -> str:
        """
        Родитель фото – приём, тип 'appointment'.
        """
        return 'appointment'

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_child_ids(self, parent_id: int) -> list:
        """
        У фото нет дочерних сущностей.
        """
        return []

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_photo_to_new_row(self, file_path: str) -> bool:
        """Создаёт новую строку с фото (использует _add_photo_from_file)."""
        photo_field = self._get_photo_field_name_impl()
        
        if not photo_field:
            return False
        
        self._add_photo_from_file(file_path, photo_field)

        return True