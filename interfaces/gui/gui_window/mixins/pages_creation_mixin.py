# interfaces/gui/gui_window/mixins/pages_creation_mixin.py

"""
Миксин для создания динамических страниц приложения.
Содержит методы инициализации страниц пациентов, приёмов, заметок и фотографий.
"""

from app.utils.logger.logger import AppLogger

from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service
)
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
from app.dto.field_configs import PATIENT_CONFIG, APPOINTMENT_CONFIG, NOTE_CONFIG, PHOTO_CONFIG

from interfaces.gui.gui_window.controllers.page_manager import PageManager

from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage
from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.settings_page import SettingsPage
from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage


class PagesCreationMixin:
    """
    Миксин, предоставляющий методы для создания всех страниц GUI.
    """

    @AppLogger.get_instance(
        name='PagesCreationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_patient(self):
        """
        Создаёт страницу списка пациентов и страницу редактирования пациента.
        Устанавливает атрибуты:
            - self.patient_list_page (DynamicListPage)
            - self.patient_edit_page (DynamicEditPage)
        """
        # Страница со списком пациентов
        self.patient_list_page = DynamicListPage(
            service=get_patient_service(),
            loader_func=self.load_patients,          # функция загрузки данных
            dto_class=PatientDTO,
            field_configs=PATIENT_CONFIG,
            page_title="Пациенты",
            add_action_text="Добавить пациента",
            action_button_text="Приёмы",              # дополнительная кнопка для просмотра приёмов пациента
            # save_directly=True,   
        )

        # Страница редактирования пациента
        self.patient_edit_page = DynamicEditPage(
            service=get_patient_service(),
            dto_class=PatientDTO,
            page_title="Редактирование пациента",
            exclude_fields=['id'],
            field_configs=PATIENT_CONFIG,
            save_directly=True,   
        )
        # Указываем ID страницы списка, чтобы после сохранения/удаления обновлять список
        self.patient_edit_page.list_page_id = 'patient_list'

    @AppLogger.get_instance(
        name='PagesCreationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_appointment(self):
        """
        Создаёт страницу списка приёмов и страницу редактирования приёма.
        Устанавливает атрибуты:
            - self.appointment_list_page (AppointmentListPage)
            - self.appointment_edit_page (DynamicEditPage)
        """
        self.appointment_list_page = AppointmentListPage(
            service=get_appointment_service(),
            loader_func=self.load_appointments,
            dto_class=AppointmentDTO,
            field_configs=APPOINTMENT_CONFIG,
            page_title="Приёмы",
            add_action_text="Новый приём",
            exclude_columns=[
                'photos',
                'patient_name',
                # 'photos',
            ] ,  # колонка с фото не отображается в таблице
            # save_directly=True,  
        )

        self.appointment_edit_page = DynamicEditPage(
            service=get_appointment_service(),
            dto_class=AppointmentDTO,
            page_title="Редактирование приёма",
            exclude_fields=['id', 'has_photos'],  # 'has_photos' – виртуальное поле
            related_services={'patient': get_patient_service()},  # для подгрузки данных пациента
            field_configs=APPOINTMENT_CONFIG,
            save_directly=True,   
        )
        self.appointment_edit_page.list_page_id = 'appointment_list'

    @AppLogger.get_instance(
        name='PagesCreationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_note(self):
        """
        Создаёт страницу списка заметок и страницу редактирования заметки.
        Устанавливает атрибуты:
            - self.note_list_page (DynamicListPage)
            - self.note_edit_page (DynamicEditPage)
        """
        self.note_list_page = DynamicListPage(
            service=get_note_service(),
            loader_func=self.load_notes,
            dto_class=AppointmentNoteDTO,
            field_configs=NOTE_CONFIG,
            page_title="Заметки",
            add_action_text="Создать заметку",
            # save_directly=True,  
        )

        self.note_edit_page = DynamicEditPage(
            service=get_note_service(),
            dto_class=AppointmentNoteDTO,
            page_title="Редактирование заметки",
            exclude_fields=['id'],
            field_configs=NOTE_CONFIG,
            save_directly=True,  
        )
        self.note_edit_page.list_page_id = 'note_list'

    @AppLogger.get_instance(
        name='PagesCreationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_photo(self):
        """
        Создаёт страницу списка фотографий и страницу редактирования фото.
        Устанавливает атрибуты:
            - self.photo_list_page (DynamicListPage)
            - self.photo_edit_page (DynamicEditPage)
        """
        self.photo_list_page = DynamicListPage(
            service=get_photo_service(),
            loader_func=self.load_photos,
            dto_class=PhotoDTO,
            field_configs=PHOTO_CONFIG,
            page_title="Фотографии",
            add_action_text="Добавить фото",
            # save_directly=True,  
        )

        self.photo_edit_page = DynamicEditPage(
            service=get_photo_service(),
            dto_class=PhotoDTO,
            page_title="Редактирование фото",
            exclude_fields=['id'],
            field_configs=PHOTO_CONFIG,
            save_directly=True,  
        )
        self.photo_edit_page.list_page_id = 'photo_list'

    @AppLogger.get_instance(
        name='PagesCreationMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _init_page_manager(self):
        """
        Инициализирует менеджер страниц.
        Сначала создаёт все страницы (пациенты, приёмы, заметки, фото),
        затем собирает их в словарь, добавляет в QStackedWidget,
        создаёт PageManager и подключает сигналы страниц.
        """
        # Создаём все страницы (важно: порядок не имеет значения, но все должны быть созданы)
        self._set_patient()
        self._set_appointment()
        self._set_note()
        self._set_photo()

        # Страница настроек (создаётся отдельно, так как она не использует динамические шаблоны)
        self.settings_page = SettingsPage(page_title="Настройки")

        # Словарь всех страниц с их идентификаторами
        pages = {
            'patient_list': self.patient_list_page,
            'patient_edit': self.patient_edit_page,
            'appointment_list': self.appointment_list_page,
            'appointment_edit': self.appointment_edit_page,
            'note_list': self.note_list_page,
            'note_edit': self.note_edit_page,
            'photo_list': self.photo_list_page,
            'photo_edit': self.photo_edit_page,
            'settings': self.settings_page,
        }

        # Добавляем каждую страницу в стековый виджет
        for page in pages.values():
            self.stacked_widget.addWidget(page)

        # Создаём менеджер страниц (управляет историей и переключениями)
        self.page_manager = PageManager(self.stacked_widget, pages)

        # Передаём ссылку на главное окно каждой странице (для доступа к page_manager и др.)
        for page in pages.values():
            if hasattr(page, 'set_main_window'):
                page.set_main_window(self)

        # Подключаем сигналы, генерируемые страницами (добавление, редактирование, удаление)
        self._connect_page_signals()