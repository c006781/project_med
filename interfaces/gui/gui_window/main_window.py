# interfaces/gui/gui_window/main_window.py

"""
Главное окно приложения.

Собирает все миксины и предоставляет единую точку входа в GUI.
Содержит инициализацию UI, создание страниц, подключение сигналов,
а также методы загрузки данных для списков (load_patients, load_appointments и т.д.).
"""

import os
import sys

from app.utils.logger.logger import AppLogger

from app.config.config_manager.manager import AppConfigManager
from app.network.thread_network import DownloadThread, UploadThread
from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service, get_sync_service
)

from app.dto.dto_all import AppointmentDTO, AppointmentNoteDTO, PatientDTO, PhotoDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG

from interfaces.gui.gui_window.controllers.page_manager import PageManager
from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage
from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage
from interfaces.gui.gui_window.pages.settings_page import SettingsPage
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer, LogViewerHandler

# Импорт миксинов
# from interfaces.gui.gui_window.mixins.pages_creation_mixin import PagesCreationMixin
# from interfaces.gui.gui_window.mixins.connections_mixin import ConnectionsMixin
# from interfaces.gui.gui_window.mixins.delete_handlers_mixin import DeleteHandlersMixin
# from interfaces.gui.gui_window.mixins.navigation_mixin import NavigationMixin
# from interfaces.gui.gui_window.mixins.sync_mixin import SyncMixin

from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox,
    QStackedWidget, QFrame
)
from PySide6.QtCore import Qt, Slot

from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget


class PagesCreationMixin:
    """
    Миксин, предоставляющий методы для создания всех страниц GUI.
    """

    @AppLogger.get_instance(
        name='PagesCreationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
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
        
class ConnectionsMixin:
    """
    Миксин, содержащий методы для связывания сигналов страниц с действиями.
    """

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_signals(self):
        """
        Подключает основные сигналы главного окна:
            - кнопка "Назад"
            - кнопка "Настройки"
            - выбор действия в комбобоксе
            - сигналы менеджера страниц (навигация, вход на страницу)
        """
        # Кнопка возврата на предыдущую страницу
        self.back_btn.clicked.connect(self._on_back_clicked)

        # # Кнопка открытия страницы настроек
        # self.settings_btn.clicked.connect(self._on_settings_clicked)

        # Выбор действия из выпадающего списка (скачать, сохранить, отправить)
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)

        # Сигналы от менеджера страниц
        self.page_manager.navigation_changed.connect(self._on_navigation_changed)
        self.page_manager.page_entered.connect(self._on_page_entered)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_page_signals(self):
        """
        Связывает сигналы всех страниц (списков и редактирования) с методами-обработчиками.
        """
        self._connect_patient()
        self._connect_appointment()
        self._connect_note()
        self._connect_photo()

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_patient(self):
        """
        Подключает сигналы страницы списка пациентов:
            - add_requested → переход на страницу создания пациента
            - edit_requested → переход на страницу редактирования с переданным DTO
            - delete_requested → вызов обработчика удаления
            - action_requested → переход к списку приёмов выбранного пациента
        """
        # Добавление нового пациента
        self.patient_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('patient_edit', extra_data=None)
        )
        # Редактирование существующего пациента
        self.patient_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'patient_edit',
                extra_data={'id': dto.id}
            )
        )
        # Удаление пациента
        self.patient_list_page.delete_requested.connect(self._on_patient_delete)
        # Дополнительное действие: показать приёмы пациента
        self.patient_list_page.action_requested.connect(self._on_patient_appointments_requested)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_appointment(self):
        """
        Подключает сигналы страницы списка приёмов:
            - add_requested → переход на страницу создания приёма (с patient_id, если есть)
            - edit_requested → переход на страницу редактирования
            - delete_requested → вызов обработчика удаления
        """
        # Добавление нового приёма (если в extra_data есть patient_id, он будет передан)
        self.appointment_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'appointment_edit',
                extra_data={
                    'patient_id': self.appointment_list_page.current_extra.get('patient_id')
                    if self.appointment_list_page.current_extra else None
                }
            )
        )
        # Редактирование приёма
        self.appointment_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'appointment_edit',
                extra_data={'id': dto.id}
            )
        )
        # Удаление приёма
        self.appointment_list_page.delete_requested.connect(self._on_appointment_delete)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_note(self):
        """
        Подключает сигналы страницы списка заметок:
            - add_requested → переход на страницу создания заметки
            - edit_requested → переход на страницу редактирования
            - delete_requested → вызов обработчика удаления
        """
        self.note_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('note_edit', extra_data=None)
        )
        self.note_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'note_edit',
                extra_data={'id': dto.id}
            )
        )
        self.note_list_page.delete_requested.connect(self._on_note_delete)

    @AppLogger.get_instance(
        name='ConnectionsMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _connect_photo(self):
        """
        Подключает сигналы страницы списка фотографий:
            - add_requested → переход на страницу создания фото
            - edit_requested → переход на страницу редактирования
            - delete_requested → вызов обработчика удаления
        """
        self.photo_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('photo_edit', extra_data=None)
        )
        self.photo_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'photo_edit',
                extra_data={'id': dto.id}
            )
        )
        self.photo_list_page.delete_requested.connect(self._on_photo_delete)

class DeleteHandlersMixin:
    """
    Миксин, содержащий слоты для удаления сущностей с подтверждением.
    """

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_patient_delete(self, dto):
        """
        Удаление пациента после подтверждения пользователя.
        Удаляются также все связанные приёмы и фотографии (каскадно).
        """
        # Запрашиваем подтверждение
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить пациента {dto.last_name} {dto.first_name}? "
            "Все связанные приёмы и фото также будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_patient_service()
            service.delete_patient(dto.id)
            QMessageBox.information(self, "Успех", "Пациент удалён.")
            self.patient_list_page._load_data()      # обновляем список
            self.logger.info(f"Удалён пациент ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления пациента: {e}")

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_appointment_delete(self, dto):
        """
        Удаление приёма после подтверждения.
        """
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить приём ID {dto.id} от {dto.date}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_appointment_service()
            service.delete_appointment(dto.id)
            QMessageBox.information(self, "Успех", "Приём удалён.")
            self.appointment_list_page._load_data()   # обновляем список
            self.logger.info(f"Удалён приём ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления приёма: {e}")

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_note_delete(self, dto):
        """
        Удаление заметки после подтверждения.
        """
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить заметку ID {dto.id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_note_service()
            service.delete_note(dto.id)
            QMessageBox.information(self, "Успех", "Заметка удалена.")
            self.note_list_page._load_data()         # обновляем список
            self.logger.info(f"Удалена заметка ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления заметки: {e}")

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_photo_delete(self, dto):
        """
        Удаление фотографии (запись в БД и физический файл) после подтверждения.
        """
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить фото ID {dto.id}? Файл будет удалён с диска.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_photo_service()
            service.delete_photo(dto.id)
            QMessageBox.information(self, "Успех", "Фото удалено.")
            self.photo_list_page._load_data()        # обновляем список
            self.logger.info(f"Удалено фото ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления фото: {e}")

class NavigationMixin:
    """
    Миксин, отвечающий за обработку навигационных действий:
        - кнопка "Назад"
        - кнопка "Настройки"
        - переход к списку приёмов пациента
        - обновление хлебных крошек и состояния кнопки "Назад"
    """

    @AppLogger.get_instance(
        name='NavigationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_back_clicked(self):
        """
        Возврат на предыдущую страницу с проверкой несохранённых изменений,
        если текущая страница – список в режиме редактирования.
        """

        current_page = self.page_manager._pages.get(self.page_manager.current_page_id)

        self.logger.debug(
            f"if isinstance(current_page, DynamicListPage) and current_page.edit_mode: {isinstance(current_page, DynamicListPage) and current_page.edit_mode}"
        )
        # Если это страница настроек и она не разрешает выход
        if current_page is self.settings_page:
            if hasattr(current_page, 'can_leave') and not current_page.can_leave():
                return
            
        # T1 = isinstance(current_page, DynamicListPage)
        # T2 = current_page.edit_mode
        # 0==0

        # Если страница умеет отменять изменения – используем её метод
        if hasattr(current_page, 'cancel_changes_and_leave'):
            if not current_page.cancel_changes_and_leave():
                return  # пользователь нажал Cancel
        else:

            if isinstance(current_page, DynamicListPage) and current_page.edit_mode:
                # Проверяем наличие несохранённых изменений
                if current_page.modified_rows or current_page.deleted_rows or current_page.new_rows:
                    reply = QMessageBox.question(
                        self, "Несохранённые изменения",
                        "Есть несохранённые изменения. Сохранить перед возвратом?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        current_page._save_changes()
                        # current_page._exit_edit_mode()
                    elif reply == QMessageBox.StandardButton.No:
                        # Откатываем изменения
                        current_page._load_data() # обновляем список
                        current_page._clear_selection() # сбрасываем выделение в таблице (если оно есть)
                        current_page._clear_drafts() # Очистка черновиков (если они есть)
                        # current_page.modified_rows.clear()
                        # current_page.deleted_rows.clear()
                        # current_page.new_rows.clear()

                        current_page._update_save_button_state()  # обновляем состояние кнопки
                        # current_page._exit_edit_mode()
                        # Если страница умеет сбрасывать свою правую панель из БД — вызываем
                        if hasattr(current_page, 'reset_current_appointment_from_db'):
                            current_page.reset_current_appointment_from_db()
                    else:
                        # Cancel – не переходим назад
                        return
                else:
                    pass
                    # current_page._exit_edit_mode()
        
        self.page_manager.go_back()

    @AppLogger.get_instance(
        name='NavigationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_settings_clicked(self):
        """Переход на страницу настроек."""
        self.page_manager.switch_to('settings')

    @AppLogger.get_instance(
        name='NavigationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_patient_appointments_requested(self, patient_dto):
        """
        Переход к списку приёмов выбранного пациента.
        Передаётся patient_id в extra_data для фильтрации списка.
        """
        self.page_manager.switch_to(
            'appointment_list',
            extra_data={'patient_id': patient_dto.id}
        )

    @AppLogger.get_instance(
        name='NavigationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(list, str)
    def _on_navigation_changed(self, history, current_page_id):
        """
        Обновляет хлебные крошки и состояние кнопки "Назад" при изменении навигации.
        """
        # Собираем заголовки страниц из истории
        titles = [title for _, title in history]
        # Добавляем заголовок текущей страницы
        if current_page_id:
            current_title = self.page_manager._get_page_title(current_page_id)
            titles.append(current_title)

        # Формируем строку с разделителем " > "
        crumbs = " > ".join(titles) if titles else "Главная"
        self.breadcrumbs_label.setText(crumbs)

        # Кнопка "Назад" активна, только если есть история
        self.back_btn.setEnabled(len(history) > 0)

    @AppLogger.get_instance(
        name='NavigationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str, object)
    def _on_page_entered(self, page_id, extra_data):
        """
        Вызывается при входе на страницу. Передаёт extra_data в метод on_enter страницы.
        """
        page = self.page_manager._pages.get(page_id)
        if page and hasattr(page, 'on_enter'):
            try:
                page.on_enter(extra_data)
            except Exception as e:
                self.logger.exception(f"Ошибка в on_enter страницы {page_id}: {e}")
                raise e

class SyncMixin:
    """
    Миксин, реализующий асинхронную загрузку и выгрузку БД с Яндекс.Диска.
    Использует отдельные потоки (QThread) для неблокирующей работы.
    """

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_action_selected(self, index):
        """
        Обработчик выбора действия в комбобоксе.
            index 0 → скачать БД
            index 1 → сохранить изменения (пока заглушка)
            index 2 → отправить БД на сервер
        """
        if index == 1:          # Настройки
            self._on_settings_clicked()
        elif index == 3:        # Скачать БД (если использовался insertSeparator, то индекс 2, иначе 3)
            self._start_download()
        elif index == 4:        # Загрузить БД (индекс 3 или 4)
            self._start_upload()

        # Сбрасываем выбранный индекс, чтобы можно было повторно выбрать то же действие
        # self.action_combo.setCurrentIndex(-1)
        self.action_combo.blockSignals(True)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.blockSignals(False)

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _start_download(self):
        """
        Запускает поток скачивания файла БД с Яндекс.Диска.
        Перед запуском проверяет наличие токена.
        """
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        remote = config.get('database_remote_path')
        local = config.get('database_local_path')

        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return

        # Создаём и настраиваем поток загрузки
        self.download_thread = DownloadThread(token, remote, local)
        self.download_thread.progress.connect(self._update_progress)
        self.download_thread.finished.connect(self._on_download_finished)
        self.download_thread.error.connect(self._on_download_error)

        # Показываем прогресс-бар (бесконечный режим до получения размера)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.download_thread.start()
        self.logger.info("Запущен поток скачивания БД")

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _start_upload(self):
        """
        Запускает поток загрузки локального файла БД на Яндекс.Диск.
        """
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        remote = config.get('database_remote_path')
        local = config.get('database_local_path')

        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return

        self.upload_thread = UploadThread(token, local, remote, overwrite=True)
        self.upload_thread.progress.connect(self._update_progress)
        self.upload_thread.finished.connect(self._on_upload_finished)
        self.upload_thread.error.connect(self._on_upload_error)

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.upload_thread.start()
        self.logger.info("Запущен поток загрузки БД")

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int, int)
    def _update_progress(self, current, total):
        """
        Обновляет прогресс-бар в соответствии с текущим и общим размером.
        Если total == 0, переводим бар в режим "безлимитного" прогресса.
        """
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)   # бесконечная анимация

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_download_finished(self, code):
        """
        Обработчик завершения скачивания.
        Скрывает прогресс-бар и выводит сообщение об успехе или ошибке.
        """
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно скачана.")
            # # Перезагружаем данные на всех страницах-списках
            # self._reload_all_list_pages()
            # Перезагружаем все данные через существующий механизм
            self.on_settings_changed(changed_blocks={'database'})
        else:
            QMessageBox.critical(self, "Ошибка", f"Скачивание завершилось с кодом {code}")

    # @AppLogger.get_instance(
    #     name='MainWindow',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _reload_all_list_pages(self):
    #     """
    #     Перезагружает данные на всех страницах-списках (пациенты, приёмы, заметки, фото).
    #     Также, если текущая страница – это страница редактирования (DynamicEditPage),
    #     перезагружает её с сохранением ID редактируемой записи.
    #     """
    #     self.logger.info("Перезагрузка всех страниц после синхронизации БД")

    #     # Список страниц-списков
    #     list_pages = [
    #         self.patient_list_page,
    #         self.appointment_list_page,
    #         self.note_list_page,
    #         self.photo_list_page,
    #     ]

    #     # Перезагружаем каждую страницу списка, если она существует и имеет метод _load_data
    #     for page in list_pages:
    #         if page and hasattr(page, '_load_data'):
    #             # Временно блокируем сигналы выделения, чтобы не вызывать лишние обновления
    #             if hasattr(page, 'table_view') and page.table_view.selectionModel():
    #                 page.table_view.selectionModel().blockSignals(True)
    #             try:
    #                 page._load_data()
    #             finally:
    #                 if hasattr(page, 'table_view') and page.table_view.selectionModel():
    #                     page.table_view.selectionModel().blockSignals(False)

    #     # Если текущая страница – редактирование (DynamicEditPage) или другая детальная страница,
    #     # перезагружаем её, сохраняя контекст (id записи)
    #     current_page = self.page_manager._pages.get(self.page_manager.current_page_id)
    #     if current_page and current_page not in list_pages:
    #         if hasattr(current_page, 'on_enter'):
    #             # Получаем те же extra_data, которые были переданы при входе на страницу
    #             extra = self.page_manager.get_current_extra_data()
    #             # Если extra_data не сохранялись, но у страницы есть атрибут current_id – используем его
    #             if extra is None and hasattr(current_page, 'current_id') and current_page.current_id:
    #                 extra = {'id': current_page.current_id}
    #             # Вызываем on_enter для перезагрузки данных
    #             current_page.on_enter(extra)
    #             self.logger.info(f"Перезагружена страница {current_page.page_title}")

    #     self.logger.info("Перезагрузка страниц завершена")

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_download_error(self, message):
        """
        Обработчик ошибки в потоке скачивания.
        """
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_upload_finished(self, code):
        """
        Обработчик завершения загрузки на диск.
        """
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно загружена.")
        else:
            QMessageBox.critical(self, "Ошибка", f"Загрузка завершилась с кодом {code}")

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_upload_error(self, message):
        """
        Обработчик ошибки в потоке загрузки.
        """
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _save_changes(self):
        """
        Заглушка для сохранения изменений в локальной БД.
        В текущей версии не реализовано.
        """
        self.logger.info("Сохранение изменений (заглушка)")
        QMessageBox.information(self, "Информация", "Функция сохранения изменений пока не реализована.")

    # Вспомогательные методы управления прогресс-баром (могут вызываться извне)
    def show_progress(self, visible=True):
        """Показать или скрыть прогресс-бар."""
        self.progress_bar.setVisible(visible)

    def set_progress_range(self, minimum, maximum):
        """Установить диапазон значений прогресс-бара."""
        self.progress_bar.setRange(minimum, maximum)

    def set_progress_value(self, value):
        """Установить текущее значение прогресса."""
        self.progress_bar.setValue(value)
        

class MainWindow(
    QMainWindow,
    PagesCreationMixin,
    ConnectionsMixin,
    DeleteHandlersMixin,
    NavigationMixin,
    SyncMixin
):
    """
    Главное окно приложения.
    Наследует QMainWindow и все миксины, предоставляющие готовую функциональность.
    """

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        """
        Инициализирует главное окно:
            - устанавливает заголовок и размер
            - создаёт логгер
            - подготавливает UI (шапка, стек страниц, лог-вьюер)
            - инициализирует менеджер страниц
            - подключает сигналы
            - проверяет наличие конфигурации и открывает соответствующую страницу
        """
        super().__init__(parent)

        # Настройки окна
        self.setWindowTitle("Медицинское приложение")
        self.resize(1200, 800)

        # Логгер для данного класса (используется во всех миксинах через self.logger)
        self.logger = AppLogger.get_instance(
            name='gui.MainWindow',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user'
        )

        # Атрибуты для потоков синхронизации (будут использоваться в SyncMixin)
        self.download_thread = None
        self.upload_thread = None

        # Построение интерфейса
        self._setup_ui()

        # Подключение обработчика логов к виджету LogViewer
        self._setup_log_viewer()

        # Создание страниц и менеджера страниц
        self._init_page_manager()

        self.sync_service = get_sync_service()

        # Подключение основных сигналов (кнопки, комбобокс, навигация)
        self._connect_signals()

        # Определяем, существует ли файл конфигурации
        # from app.config.config_manager.manager import AppConfigManager
        config_manager = AppConfigManager.get_instance()
        
        # Применяем сохранённые настройки ко всем логгерам (если файл существует)
        if config_manager.config_exists:
            # from app.utils.logger.logger import AppLogger
            AppLogger.reload_all_from_app_config()

        if not config_manager.config_exists:
            # Первый запуск – открываем настройки с флагом first_start
            self.page_manager.switch_to(
                'settings',
                add_to_history=False,
                extra_data={'first_start': True}
            )
        else:
            # Обычный запуск – показываем список пациентов
            self.page_manager.switch_to('patient_list')

        self.logger.info("Главное окно создано")

    # ----------------------------------------------------------------------
    # Методы загрузки данных для страниц списков
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_patients(self, extra_data):
        """
        Возвращает список всех пациентов из БД.
        Используется как loader_func для DynamicListPage.
        """
        return get_patient_service().get_all_patients()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_appointments(self, extra_data):
        """
        Возвращает список приёмов.
        Если в extra_data передан patient_id – только приёмы этого пациента,
        иначе – все приёмы.
        """
        patient_id = extra_data.get('patient_id') if extra_data else None
        service = get_appointment_service()
        if patient_id:
            return service.get_appointments_by_patient(patient_id)
        else:
            return service.get_all()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_notes(self, extra_data):
        """Возвращает список всех заметок."""
        return get_note_service().get_all()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_photos(self, extra_data):
        """Возвращает список всех фотографий."""
        return get_photo_service().get_all()

    # ----------------------------------------------------------------------
    # Приватные методы построения UI
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Создаёт центральный виджет, основной вертикальный layout,
        шапку (header), стек страниц и виджет просмотра логов.
        """
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Верхняя панель с действиями, навигацией и прогрессом
        self._setup_header(main_layout)

        # Стек для переключения страниц
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Виджет для отображения логов (изначально скрыт)
        self._setup_log_viewer_widget(main_layout)

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_header(self, main_layout):
        """
        Создаёт верхнюю панель (шапку) с комбобоксом действий,
        кнопкой настроек, хлебными крошками, кнопкой "Назад" и прогресс-баром.
        """
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_frame.setMaximumHeight(60)

        self.header_layout = QHBoxLayout(header_frame)
        self.header_layout.setContentsMargins(10, 5, 10, 5)

        # Выпадающий список действий
        self.action_combo = QComboBox()
        self.action_combo.addItem("Файл")          # индекс 0 – заглушка
        self.action_combo.addItem("Настройки")     # индекс 1
        self.action_combo.insertSeparator(2)       # разделитель 
        self.action_combo.addItem("Скачать БД с сервера")   # индекс 3
        self.action_combo.addItem("Загрузить БД на сервер") # индекс 4
        self.action_combo.setEditable(False)
        self.action_combo.setMaximumWidth(200)

        # Делаем пункт "Файл" невыбираемым
        self.action_combo.model().item(0).setEnabled(False)
        # Пункт-разделитель (индекс 2) тоже делаем невыбираемым, можно пустую строку
        # self.action_combo.model().item(2).setEnabled(False)
        self.action_combo.setCurrentIndex(0)  # по умолчанию выбран заглушечный пункт

        self.header_layout.addWidget(self.action_combo)

        # Кнопка настроек
        # self.settings_btn = QPushButton("Настройки")
        # self.settings_btn.setMaximumWidth(100)
        # self.header_layout.addWidget(self.settings_btn)

        self.header_layout.addStretch()

        # Хлебные крошки (отображают путь навигации)
        self.breadcrumbs_label = QLabel("Главная")
        self.breadcrumbs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_layout.addWidget(self.breadcrumbs_label)

        self.header_layout.addStretch()

        # Кнопка "Назад"
        self.back_btn = QPushButton("← Назад")
        self.back_btn.setMaximumWidth(80)
        self.back_btn.setEnabled(False)
        self.header_layout.addWidget(self.back_btn)

        # Прогресс-бар (по умолчанию скрыт)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.header_layout.addWidget(self.progress_bar)

        main_layout.addWidget(header_frame)

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_log_viewer_widget(self, main_layout):
        """
        Создаёт виджет LogViewer и добавляет его в основной layout.
        Кнопка показа/скрытия логов добавляется в шапку после создания виджета.
        """
        self.log_viewer = LogViewer()
        main_layout.addWidget(self.log_viewer)

        # Кнопка для отображения/скрытия панели логов (добавляем в существующую шапку)
        self.show_log_btn = QPushButton("Показать логи")
        self.show_log_btn.setCheckable(True)
        self.show_log_btn.toggled.connect(self.log_viewer.setVisible)
        self.header_layout.addWidget(self.show_log_btn)

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_log_viewer(self):
        """
        Добавляет глобальный обработчик логов, который перенаправляет все записи
        в виджет LogViewer.
        """
        handler = LogViewerHandler(self.log_viewer)
        AppLogger.add_global_handler(handler)

    @AppLogger.get_instance(
        name='MainWindow',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def on_settings_changed(
        self,
        changed_blocks: set = None,
    ):
        """
        Слот, вызываемый при изменении настроек (после сохранения в SettingsPage).
        (Перезагружает сервисы, обновляет пути и перезагружает текущую страницу.)

        Применяет изменения в UI в зависимости от того, какие блоки настроек изменились.
        Это позволяет избежать полной перезагрузки всего интерфейса.

        Параметры:
            changed_blocks (set, optional): Множество строк – названия блоков,
                которые изменились (например, {'photos', 'database'}).
                Если None, считается, что изменилось всё (для обратной совместимости).

        Логика:
            - Если блок 'photos' изменился (или changed_blocks is None), обновляет
              путь к хранилищу фото во всех виджетах PhotoUploaderWidget.
            - Если блок 'database' или 'photos' изменился, перезагружает данные
              на всех страницах-списках (пациенты, приёмы, заметки, фото).
            - Если блок 'database' изменился и текущая страница – редактирование,
              перезагружает её данные через вызов on_enter с сохранёнными extra_data.

        Returns:
            None
        """

        self.logger.info("Применение новых настроек...")

        #  Обновляем пути к фото во всех PhotoUploaderWidget
        config = AppConfigManager.get_instance()
        storage_path = config.get('PHOTOS_STORAGE_PATH', os.path.join('.', 'photos'))

        # # Обновляем путь через PhotoService (классовый атрибут)
        # photo_service = get_photo_service()
        #
        # # Устанавливаем путь через свойство – оно обновит классовый атрибут
        # photo_service._storage_path = storage_path


        # Обновляем путь к фото во всех виджетах PhotoUploaderWidget (только если изменился блок photos)
        if changed_blocks is None or 'photos' in changed_blocks:
            for widget in self._find_all_photo_widgets():
                widget.set_storage_path(storage_path)

        # Перезагружаем данные на страницах-списках (только если изменилась БД или фото)
        if changed_blocks is None or 'database' in changed_blocks or 'photos' in changed_blocks:

            list_pages = [
                self.patient_list_page,
                self.appointment_list_page,
                self.note_list_page,
                self.photo_list_page,
            ]
            for page in list_pages:
                if page and hasattr(page, '_load_data'):
                    page._load_data()
        
        # Если изменилась БД и текущая страница – редактирование, перезагружаем её данные
        #    перезагружаем её данные, если она поддерживает on_enter с extra_data
        if changed_blocks is None or 'database' in changed_blocks:
            current_page = self.page_manager._pages.get(self.page_manager.current_page_id)
            if current_page and current_page not in list_pages:
                # Для страниц редактирования: если открыта какая-то запись, перезагрузим её
                if hasattr(current_page, 'on_enter'):
                    # Передаём те же extra_data, что были при входе, чтобы не сбросить id
                    extra = self.page_manager.get_current_extra_data()
                    current_page.on_enter(extra)
        
        self.logger.info("Применение настроек завершено")

    @AppLogger.get_instance(
        name='MainWindow',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _find_all_photo_widgets(self):
        """Рекурсивно собирает все виджеты PhotoUploaderWidget в окне."""
        result = []
        for child in self.findChildren(PhotoUploaderWidget):
            result.append(child)
        return result