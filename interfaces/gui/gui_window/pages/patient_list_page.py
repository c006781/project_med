# interfaces/gui/gui_window/pages/patient_list_page.py
"""
Страница списка пациентов с пагинацией, фильтрацией и черновиками.
Наследует PaginatedListPage.
"""

from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage

from app.dependencies import get_patient_service

from app.dto.dto_all import PatientDTO
from app.dto.field_configs import PATIENT_CONFIG

from app.utils.logger.logger import AppLogger


class PatientListPage(PaginatedListPage):
    """
    Страница списка пациентов.

    Использует PaginatedListPage со следующими параметрами:
        - entity_type = "patient"
        - show_controls включает все основные кнопки: режим редактирования,
          выпадающие списки, сохранение, поиск и дополнительную кнопку "Приёмы".
    """

    @AppLogger.get_instance(
        name='PatientListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, shared_registry=None):
        super().__init__(
            service=get_patient_service(),
            dto_class=PatientDTO,
            field_configs=PATIENT_CONFIG,
            page_title="Пациенты",
            add_action_text="Добавить пациента",
            action_button_text="Приёмы",
            parent=parent,
            exclude_columns=None,
            entity_type="patient",
            shared_registry=shared_registry,
            show_controls=[
                'edit_mode_btn',
                'action_combo',
                'inline_action_combo',
                'save_btn',
                'search',
                'action_btn'
            ]
        )

    #     self.selection_changed.connect(self._on_selection_changed)  # Подключаем сигнал на выыбранали строка в ТБ

    # def _on_selection_changed_for_button(self, dto):
    #     """Активирует/деактивирует кнопку «Приёмы» при выборе строки."""
    #     if hasattr(self, 'action_btn') and self.action_btn:
    #         # dto может быть None (выделение снято) или PatientDTO
    #         self.action_btn.setEnabled(dto is not None)
