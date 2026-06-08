# interfaces/gui/gui_window/pages/paginated_appointment_list_page.py
"""
Страница списка приёмов на базе PaginatedListPage.
Используется в новом фрейме с двумя таблицами (приёмы + фото).
"""

from typing import Optional

from app.utils.logger.logger import AppLogger

from app.dependencies import get_appointment_service, get_photo_service

from app.dto.dto_all import AppointmentDTO
from app.dto.field_configs import APPOINTMENT_CONFIG

from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage


class PaginatedAppointmentListPage(PaginatedListPage):
    """
    Страница списка приёмов с пагинацией, фильтрацией и черновиками.
    Предназначена для использования в связке с PaginatedPhotoListPage.
    """

    @property
    def _photo_service(self):
        """Ленивая инициализация сервиса для работы с фото (избегает циклических импортов)."""
        if not hasattr(self, '__photo_service'):
            # from app.dependencies import get_photo_service
            self.__photo_service = get_photo_service()
        return self.__photo_service

    @AppLogger.get_instance(
        name='PaginatedAppointmentListPage',
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

        # Добавляем поля, которые не должны отображаться в таблице
        exclude_columns = list(
            set(
                exclude_columns + [
                    'appointment_id', 
                    'patient_id', 
                    'photos'
                ]
            )
        )

        super().__init__(
            service=get_appointment_service(),
            dto_class=AppointmentDTO,
            field_configs=APPOINTMENT_CONFIG,
            page_title="Приёмы",
            add_action_text="Добавить приём",
            action_button_text=None,      # дополнительная кнопка не нужна
            parent=parent,
            exclude_columns=exclude_columns,
            entity_type="appointment",
            shared_registry=shared_registry,
            show_controls=show_controls
        )
        # # Сервис для фото (понадобится для каскадного удаления)
        # self._photo_service = get_photo_service()

    @AppLogger.get_instance(
        name='PaginatedAppointmentListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_parent_id_for_new_row(self, dto) -> int:
        """
        Приёмы являются корневыми сущностями (не имеют родителя).
        """
        return None

    @AppLogger.get_instance(
        name='PaginatedAppointmentListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_child_ids(self, parent_id: int) -> list:
        """
        Возвращает список ID фото, принадлежащих приёму.
        Используется для каскадного удаления при удалении приёма.
        """
        photos = self._photo_service.get_photos_for_appointment(parent_id)
        return [p.id for p in photos]
    
    # def _get_child_service(self, child_name: str = None) -> Optional['BaseService']:
    #     """
    #     Возвращает сервис для дочерних сущностей (фото).
    #     Переопределяет метод базового класса.

    #     Args:
    #         child_name: Имя дочерней сущности (не используется, так как у приёма только фото).

    #     Returns:
    #         PhotoService или None.
    #     """
    #     return self._photo_service
    
    def _get_child_relation_name(self, child_id: int) -> Optional[str]:
        """
        Для приёма дочерние сущности – фотографии, отношение 'photos'.
        """
        return 'photos'