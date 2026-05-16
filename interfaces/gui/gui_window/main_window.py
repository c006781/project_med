# interfaces/gui/gui_window/main_window.py

"""
Главное окно приложения.

Собирает все миксины и предоставляет единую точку входа в GUI.
Содержит инициализацию UI, создание страниц, подключение сигналов,
а также методы загрузки данных для списков (load_patients, load_appointments и т.д.).
"""

import os
import platform
import subprocess
import sys
import tempfile
from typing import List
# import sys

from app.config import APP_VERSION, GITHUB_REPO_SLUG


from app.utils.logger.logger import AppLogger
from app.updater import AppUpdater

from app.config.config_manager.manager import AppConfigManager

from app.network.thread_network import DownloadThread, UploadThread

from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service, get_sync_service
)

from app.dto.dto_all import (
    AppointmentDTO, AppointmentNoteDTO, 
    PatientDTO, PhotoDTO
)
from app.dto.field_configs import (
    APPOINTMENT_CONFIG, NOTE_CONFIG, 
    PATIENT_CONFIG, PHOTO_CONFIG
)

from interfaces.gui.gui_window.dialogs.instructions_dialog import InstructionsDialog

from interfaces.gui.gui_window.controllers.page_manager import PageManager
from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage
from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage
from interfaces.gui.gui_window.pages.settings_page import SettingsPage
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer, LogViewerHandler
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

# Импорт миксинов
# from interfaces.gui.gui_window.mixins.pages_creation_mixin import PagesCreationMixin
# from interfaces.gui.gui_window.mixins.connections_mixin import ConnectionsMixin
# from interfaces.gui.gui_window.mixins.delete_handlers_mixin import DeleteHandlersMixin
# from interfaces.gui.gui_window.mixins.navigation_mixin import NavigationMixin
# from interfaces.gui.gui_window.mixins.sync_mixin import SyncMixin

from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressDialog,
    QWidget, QVBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox,
    QStackedWidget, QFrame, QHBoxLayout, QTextEdit
)
from PySide6.QtCore import Q_ARG, QThread, QUrl, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QDesktopServices


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
                'patient_id', 
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
                    # 'patient_id': self.appointment_list_page.current_extra.get('patient_id')
                    'patient_id': self.appointment_list_page._context_params.get('patient_id')
                    # if self.appointment_list_page._context_params.get('patient_id') is not None else None
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
        elif index == 2:        # Парсинг данных с файла
            self._start_parsing()
        elif index == 3:        # Инструкции
            self._show_instructions_dialog()
        elif index == 5:        # Скачать БД
            self._start_download()
        elif index == 6:        # Загрузить БД
            self._start_upload()

        # Сбрасываем выбранный индекс, чтобы можно было повторно выбрать то же действие
        # self.action_combo.setCurrentIndex(-1)
        self.action_combo.blockSignals(True)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.blockSignals(False)
    
    def _correct_remote_path(
        self,
        remote: str,
        local: str,
    ):
        # --- ДОБАВЛЕННАЯ ПРОВЕРКА И КОРРЕКЦИЯ REMOTE-ПУТИ ---
        # Если remote не заканчивается на расширение файла БД, добавляем имя из local
        # Расширения .db, .sqlite, .sqlite3
        # import os
        db_extensions = ('.db', '.sqlite', '.sqlite3')
        if not remote.lower().endswith(db_extensions):
            # Извлекаем имя файла из local пути
            local_filename = os.path.basename(local)
            # Нормализуем remote (убираем возможный завершающий слэш)
            remote = remote.rstrip('/\\')
            remote = f"{remote}/{local_filename}"
            self.logger.info(f"Корректировка remote пути: добавлено имя файла -> {remote}")  

        return remote

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
        
        # --- ДОБАВЛЕННАЯ ПРОВЕРКА И КОРРЕКЦИЯ REMOTE-ПУТИ ---
        remote = self._correct_remote_path(remote, local)

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
        
        # Корректируем удалённый путь (добавляем имя файла, если указана только папка)
        remote = self._correct_remote_path(remote, local)

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
        self.logger.error(f"Download error: {message}")
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

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # Вспомогательные методы управления прогресс-баром (могут вызываться извне)
    def show_progress(self, visible=True):
        """Показать или скрыть прогресс-бар."""
        self.progress_bar.setVisible(visible)

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_progress_range(self, minimum, maximum):
        """Установить диапазон значений прогресс-бара."""
        self.progress_bar.setRange(minimum, maximum)

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_progress_value(self, value):
        """Установить текущее значение прогресса."""
        self.progress_bar.setValue(value)

class UpdateMixin:
    """
    Миксин, добавляющий функциональность проверки и загрузки обновлений.
    """

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _init_updater(self):
        """Инициализирует модуль обновлений и подключает сигналы."""
        try:
            self.updater = AppUpdater(self)
            # Подключаем сигналы
            self.updater.update_available.connect(self._on_update_available)
            self.updater.no_update.connect(self._on_no_update)
            self.updater.check_error.connect(self._on_update_error)
            self.updater.download_progress.connect(self._on_download_progress)
            self.updater.download_finished.connect(self._on_download_finished)
            self.updater.download_error.connect(self._on_download_error)

            self.logger.info(f"Модуль обновлений инициализирован, версия: {APP_VERSION}")
        except Exception as e:
            self.logger.exception(f"Ошибка инициализации модуля обновлений: {e}")

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def check_for_updates(self):
        """Запускает ручную проверку обновлений (вызывается из SettingsPage)."""
        if hasattr(self, 'updater'):
            self.updater.check_for_updates()
        else:
            QMessageBox.warning(self, "Ошибка", "Система обновлений не инициализирована")

    # @AppLogger.get_instance(
    #     name='UpdateMixin',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # @Slot(str, str)
    # def _on_update_available(self, new_version: str, release_url: str):
    #     msg = QMessageBox(self)
    #     msg.setWindowTitle("Доступно обновление")
    #     msg.setText(f"Доступна новая версия {new_version}\nВаша версия: {APP_VERSION}")
    #     msg.setInformativeText("Что вы хотите сделать?")
    #     download_btn = msg.addButton("Скачать и установить", QMessageBox.ActionRole)
    #     open_btn = msg.addButton("Открыть страницу релиза", QMessageBox.ActionRole)
    #     cancel_btn = msg.addButton("Отмена", QMessageBox.RejectRole)
    #     msg.setDefaultButton(cancel_btn)
    #     msg.exec()

    #     clicked = msg.clickedButton()
    #     if clicked == download_btn:
    #         # Запускаем скачивание и установку
    #         if hasattr(self, 'updater') and hasattr(self.updater, '_pending_release_data'):
    #             self.updater.apply_update_from_release(self.updater._pending_release_data)
    #         else:
    #             QMessageBox.warning(self, "Ошибка", "Не удалось получить данные релиза")
    #     elif clicked == open_btn:
    #         QDesktopServices.openUrl(QUrl(release_url))

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @Slot(str, str)
    def _on_update_available(self, new_version: str, release_url: str):
        self._auto_check = False   # сбрасываем флаг автоматической проверки

        self.logger.debug(
            f"_on_update_available called: "
            f"new_version={new_version}, "
            f"url={release_url}"
        )

        msg = QMessageBox(self)
        msg.setWindowTitle("Доступно обновление")
        msg.setText(f"Доступна новая версия {new_version}\nВаша версия: {APP_VERSION}")
        msg.setInformativeText("Что вы хотите сделать?")
        download_btn = msg.addButton("Скачать и установить", QMessageBox.ActionRole)

        open_btn = msg.addButton("Открыть страницу релиза", QMessageBox.ActionRole)
        cancel_btn = msg.addButton("Отмена", QMessageBox.RejectRole)

        msg.setDefaultButton(cancel_btn)
        msg.exec()

        # print(
        #     "Pending release data:", 
        #     self.updater._pending_release_data 
        #     if hasattr(self.updater, '_pending_release_data') 
        #     else "None"
        # )

        clicked = msg.clickedButton()
        if clicked == download_btn:
            self.logger.debug("Download button clicked, trying to apply update from release data")
            if hasattr(self, 'updater') and hasattr(self.updater, '_pending_release_data'):
                data = self.updater._pending_release_data
                # self.logger.debug(f"Pending release data keys: {list(self.updater._pending_release_data.keys())}")
                self.logger.debug(
                    f"_pending_release_data exists, "
                    f"type={type(data)}, "
                    f"keys={data.keys() if data else None}"
                )
                self.updater.apply_update_from_release(data)
            else:
                self.logger.error("No pending release data or updater missing")
                QMessageBox.warning(self, "Ошибка", "Не удалось получить данные релиза")

        elif clicked == open_btn:
            QDesktopServices.openUrl(QUrl(release_url))

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_no_update(self):
        # При автоматической проверке не показываем сообщение
        if getattr(self, '_auto_check', False):
            self._auto_check = False
            return
        QMessageBox.information(self, "Проверка обновлений", "У вас установлена последняя версия.")

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_update_error(self, error_msg: str):
        QMessageBox.warning(self, "Ошибка", f"Не удалось проверить обновления:\n{error_msg}")

    # @AppLogger.get_instance(
    #     name='UpdateMixin',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    @Slot(int, int)
    def _on_download_progress(self, current: int, total: int):
        """Обновляет прогресс-бар в главном окне."""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_download_finished(self, file_path: str):
        self.progress_bar.setVisible(False)
        reply = QMessageBox.question(
            self, "Обновление загружено",
            f"Файл обновления сохранён:\n{file_path}\n\n"
            "Заменить текущую программу? (потребуется перезапуск)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._apply_update_file(file_path)

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_download_error(self, error_msg: str):
        self.logger.error(f"Download error: {error_msg}")
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "Ошибка загрузки", f"Не удалось скачать обновление:\n{error_msg}")

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_update_file(self, new_file_path: str):
        """
        Заменяет текущий исполняемый файл на новый.
        Работает только если программа запущена из EXE (собранной).
        В режиме разработки (из .py) просто показывает сообщение.
        """
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            QMessageBox.information(self, "Режим разработки", "В режиме разработки замена файла недоступна. Скопируйте файл вручную.")
            return

        # Проверяем, что файл не равен текущему
        if os.path.samefile(new_file_path, current_exe):
            QMessageBox.warning(self, "Ошибка", "Новый файл совпадает с текущим.")
            return

        system = platform.system()
        if system == "Windows":
            # Создаём bat-скрипт для замены
            bat_content = f"""@echo off
timeout /t 2 /nobreak > nul
copy /Y "{new_file_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
            bat_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.bat")
            with open(bat_path, "w") as f:
                f.write(bat_content)
            subprocess.Popen([bat_path], shell=True)
            QApplication.quit()
        elif system == "Linux":
            # Создаём shell-скрипт
            sh_content = f"""#!/bin/bash
sleep 2
cp "{new_file_path}" "{current_exe}"
chmod +x "{current_exe}"
"{current_exe}" &
rm "$0"
"""
            sh_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.sh")
            with open(sh_path, "w") as f:
                f.write(sh_content)
            os.chmod(sh_path, 0o755)
            subprocess.Popen([sh_path])
            QApplication.quit()
        else:
            QMessageBox.warning(self, "ОС не поддерживается", "Автоматическая замена файла доступна только для Windows и Linux.")  

# ========== Диалог прогресса ==========
class ParsingProgressDialog(QDialog):

    finished_closed = Signal()   # новый сигнал

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Импорт данных из Word")
        self.setMinimumWidth(600)
        self.setModal(True)
        layout = QVBoxLayout(self)

        # Список файлов
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        # Область для итоговой информации (создаётся, но скрыта до завершения)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(120)
        self.summary_text.setVisible(False)
        layout.addWidget(self.summary_text)

        # Кнопка
        self.close_btn = QPushButton("Отмена")
        self.close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.close_btn)

        self._finished = False
        self._items = {}

    @Slot(list)
    def set_file_list(self, file_names: list):
        self.list_widget.clear()
        self._items.clear()
        for name in file_names:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, "pending")
            self._set_status(item, "⏳ Ожидание")
            self.list_widget.addItem(item)
            self._items[name] = item

    @Slot(str, str, str)
    def update_file_status(self, file_name: str, status: str, error_msg: str = ""):
        item = self._items.get(file_name)
        if not item:
            return
        if status == "processing":
            self._set_status(item, "🔄 Обработка...")
            self.list_widget.scrollToItem(item)
        elif status == "success":
            self._set_status(item, "✅ Готово")
        elif status == "failed":
            self._set_status(item, f"❌ Ошибка: {error_msg[:60]}")
        else:
            self._set_status(item, "⏳ Ожидание")
        self.list_widget.repaint()

    def set_finished_results(self, total: int, success: int, failed: int, log_path: str):
        """Вызывается после завершения парсинга – показывает итоговую информацию."""
        self._finished = True
        self.summary_text.clear()
        self.summary_text.append(f"<b>Обработано файлов:</b> {total}")
        self.summary_text.append(f"<b>Успешно:</b> {success}")
        self.summary_text.append(f"<b>Ошибок:</b> {failed}")
        self.summary_text.append(f"<b>Лог сохранён:</b> {log_path}")
        self.summary_text.setVisible(True)

        self.close_btn.setText("Закрыть")
        try:
            self.close_btn.clicked.disconnect()
        except TypeError:
            pass
        self.close_btn.clicked.connect(self._on_close_finished)

    def _on_close_clicked(self):
        if not self._finished:
            self.reject()

    def _on_close_finished(self):
        self.finished_closed.emit()
        self.accept()

    def reject(self):
        if not self._finished:
            super().reject()
        else:
            self.accept()

    def closeEvent(self, event):
        if self._finished:
            self.finished_closed.emit()
        event.accept()

    def _set_status(self, item: QListWidgetItem, text: str):
        item.setText(f"{item.text()}   {text}")

# ========== Поток парсинга ==========
class ParsingThread(QThread):
    finished = Signal(dict)
    error = Signal(str)
    file_list_ready = Signal(list)        # список имён файлов
    status_update = Signal(str, str, str)  # file_name, status, error_msg

    def __init__(self, folder_path, update_existing=False):
        super().__init__()
        self.folder_path = folder_path
        self.update_existing = update_existing

    def run(self):
        try:
            from parsers.word_importer import batch_parse

            # Колбэк: получили список всех файлов, которые будут обработаны
            def on_start(file_names):
                self.file_list_ready.emit(file_names)

            # Колбэк: обновление статуса файла
            def on_update(file_name, status, error_msg):
                self.status_update.emit(file_name, status, error_msg)

            # Вызываем batch_parse с specific_files=None – она сама определит,
            # какие .docx файлы есть в папке, и отфильтрует уже обработанные по логу.
            results, log_dir = batch_parse(
                folder_path=self.folder_path,
                specific_files=None,
                update_existing_patient=self.update_existing,
                progress_callback_start=on_start,
                progress_callback_update=on_update,
            )
            # Добавляем путь к логу в результаты
            results['log_path'] = os.path.join(log_dir, "parser.log") if log_dir else None
            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))
            
            
class MainWindow(
    QMainWindow,
    PagesCreationMixin,
    ConnectionsMixin,
    DeleteHandlersMixin,
    NavigationMixin,
    SyncMixin,
    UpdateMixin, 
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
            - инициализирует систему обновлений (updater4pyi)
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

        # Инициализация системы обновлений (собственный модуль)
        self._init_updater()

        # Не вызываем check_for_updates сразу, а планируем через 1 секунду
        QTimer.singleShot(1500, self._delayed_check_updates)

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

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _delayed_check_updates(self):
        """Отложенный запуск проверки обновлений."""
        # Автоматическая проверка обновлений при старте (без показа сообщения "нет обновлений")
        self._auto_check = True
        # self.updater.check_for_updates()

        # Проверяем доступность GitHub перед автоматической проверкой
        from app.updater import is_github_reachable
        if is_github_reachable():
            self.updater.check_for_updates()

        else:
            self.logger.info("GitHub недоступен, автоматическая проверка обновлений пропущена")

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _show_instructions_dialog(self):
        """Открывает диалог с инструкциями."""
        dialog = InstructionsDialog(self)
        dialog.exec()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def check_for_updates(self):
        """Запускает ручную проверку обновлений (вызывается из SettingsPage)."""

        self._auto_check = False   # ручная проверка – сообщение "нет обновлений" нужно показывать
        
        if hasattr(self, 'updater'):
            self.updater.check_for_updates()
        else:
            QMessageBox.warning(self, "Ошибка", "Система обновлений не инициализирована")

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _start_parsing(self):
        # Диалог выбора папки
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку с файлами .docx", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not folder:
            return

        # Создаём и показываем диалог прогресса
        self.progress_dialog = ParsingProgressDialog(self)
        self.progress_dialog.show()

        # Создаём и запускаем поток
        self.parsing_thread = ParsingThread(folder, update_existing=False)
        self.parsing_thread.file_list_ready.connect(self.progress_dialog.set_file_list)
        self.parsing_thread.status_update.connect(self.progress_dialog.update_file_status)
        self.parsing_thread.finished.connect(self._on_parsing_finished)
        self.parsing_thread.error.connect(self._on_parsing_error)

        self.parsing_thread.start()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_parsing_finished(self, results):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.accept()
            self.progress_dialog = None

        total = results.get('total', 0)
        success = results.get('success', 0)
        failed = results.get('failed', 0)
        log_path = results.get('log_path', 'не указан')

        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.set_finished_results(total, success, failed, log_path)
            if not hasattr(self, '_parsing_closed_connected'):
                self.progress_dialog.finished_closed.connect(self._on_parsing_dialog_closed)
                self._parsing_closed_connected = True
        else:
            QMessageBox.information(
                self, "Парсинг завершён",
                f"Обработано файлов: {total}\nУспешно: {success}\nОшибок: {failed}\nЛог сохранён: {log_path}"
            )
            self._refresh_after_parsing()

    def _on_parsing_dialog_closed(self):
        """Вызывается, когда пользователь закрыл диалог прогресса после завершения парсинга."""
        self._refresh_after_parsing()
        self.progress_dialog = None
        self._parsing_closed_connected = False

    def _refresh_after_parsing(self):
        """Обновляет страницы, которые могут содержать новые данные."""
        if hasattr(self, 'patient_list_page'):
            self.patient_list_page.refresh_data()
        if hasattr(self, 'appointment_list_page'):
            self.appointment_list_page.refresh_data()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_parsing_error(self, error_msg):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.summary_text.setVisible(True)
            self.progress_dialog.summary_text.clear()
            self.progress_dialog.summary_text.append(f"<b>Ошибка выполнения парсинга:</b>\n{error_msg}")
            self.progress_dialog.close_btn.setText("Закрыть")
            try:
                self.progress_dialog.close_btn.clicked.disconnect()
            except TypeError:
                pass
            self.progress_dialog.close_btn.clicked.connect(self._on_parsing_dialog_closed)
            self.progress_dialog._finished = True
        else:
            QMessageBox.critical(self, "Ошибка", f"При выполнении парсинга произошла ошибка:\n{error_msg}")

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
        self.action_combo.addItem("Парсинг данных с файла")  # индекс 2 - парсер
        self.action_combo.addItem("Инструкции")    # индекс 3   
        self.action_combo.insertSeparator(4)       # index 4 разделитель 
        self.action_combo.addItem("Скачать БД с сервера")   # индекс 5
        self.action_combo.addItem("Загрузить БД на сервер") # индекс 6
        # ответственная ф-я: def _on_action_selected

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