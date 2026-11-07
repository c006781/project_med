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
from typing import Any, List, Mapping, Optional, Tuple
# import sys

from app.config import (
    APP_VERSION, 
    # GITHUB_REPO_SLUG
)

from app.utils.logger.logger import AppLogger

from app.updater import AppUpdater, current_system, pop_linux_update_failure

from app.config.config_manager.manager import (
    AppConfigManager,           # менеджер настроек
    DRAFT_MOVED_RULE_KEY,       # правило перенесённой записи
    UPDATE_CHECK_ON_START_KEY,  # проверка обновлений при запуске
    WORD_DOCUMENTS_PATH_KEY,    # папка документов Word
    draft_moved_rule_value,     # значение правила: неизвестное — умолчание
)

from app.utils.drafts import MovedRule

from app.utils.logger.bool_strings import to_bool

from app.exceptions.exceptions_all import YandexDiskError

from app.network.db_download import CheckedDownload

from app.network.thread_network import CheckedDownloadThread, UploadThread
# from app.network.thread_network import DownloadThread, UploadThread
# ↑ до 2026-11-07 (ТД-1): DownloadThread писал прямо в рабочий файл базы

from app.network.ya_dop import YaDiskResult, remote_db_file_path

from app.services.sync_service import (
    backup_db_before_transfer,  # резервная копия перед передачей
    discard_download,           # отказ от скачанного файла
    install_checked_download,   # замена рабочей базы скачанной
    remove_stale_downloads,     # временные файлы после аварийного выхода
)

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
from interfaces.gui.gui_window.controllers.action_manager import ActionManager

from interfaces.gui.gui_window.dialogs.instructions_dialog import InstructionsDialog

from interfaces.gui.gui_window.controllers.page_manager import PageManager

from interfaces.gui.gui_window.frames.appointment_photo_frame import AppointmentPhotoFrame

from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage
from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage
from interfaces.gui.gui_window.pages.patient_list_page import PatientListPage
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
    QStackedWidget, QFrame, QHBoxLayout, QTextEdit,
    QCheckBox,    # флажок в вопросе перед импортом из Word (ТД-8, 2026-10-25)
)
from PySide6.QtCore import Q_ARG, QThread, QUrl, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QDesktopServices

# Проверочные запуски: непустое истинное значение выключает проверку обновлений при старте,
# какой бы ни была настройка (окно не ходит в сеть и не задаёт вопрос об обновлении)
NO_UPDATE_CHECK_ENV : str = 'PROJECT_MED_NO_UPDATE_CHECK'

# Откат обновления на Linux возвращает только код; скрипт называет копию базы не в каждой причине
LINUX_ROLLBACK_DB_HINT : str = (
    "Откат возвращает только код программы: база, которую новая версия успела обновить, "
    "не возвращается. Копия базы до обновления лежит рядом с файлом базы (<база>.bak-…)."
)


# нужна ли проверка обновлений при запуске окна
def startup_update_check_enabled(
    config  : Any,                                  # настройки (метод get)
    environ : Optional[Mapping[str, str]] = None,   # окружение; None — окружение процесса
) -> bool:
    """
    Решает, проверять ли обновления при запуске окна.

    Переменная окружения ``PROJECT_MED_NO_UPDATE_CHECK`` главнее настройки: так проверочный
    запуск не зависит от файла настроек. Строки читаются общим правилом ``to_bool``; строка
    настройки, которую правило не знает, считается выключенной: лучше без сети, чем с ней.

    Args:
        config  : (Any) Настройки: объект с методом ``get(ключ, умолчание)``.
        environ : (Mapping/None) Окружение; None — ``os.environ``.

    Returns:
        (bool) True — проверять.

    Example:
        >>> startup_update_check_enabled(
        ...     {'UPDATE_CHECK_ON_START': True},                        # настройка включена
        ...     environ =   {'PROJECT_MED_NO_UPDATE_CHECK': '1'},           # проверочный запуск
        ... )
        False
    """
    env = os.environ if environ is None else environ
    if to_bool(env.get(NO_UPDATE_CHECK_ENV, '')):  # проверочный запуск
        return False
    return to_bool(
        config.get(
            UPDATE_CHECK_ON_START_KEY,  # настройка
            True,                       # нет ключа — как раньше, проверять
        ),
    )


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
        # self.patient_list_page = DynamicListPage(
        #     service=get_patient_service(),
        #     loader_func=self.load_patients,          # функция загрузки данных
        #     dto_class=PatientDTO,
        #     field_configs=PATIENT_CONFIG,
        #     page_title="Пациенты",
        #     add_action_text="Добавить пациента",
        #     action_button_text="Приёмы",              # дополнительная кнопка для просмотра приёмов пациента
        #     # save_directly=True,   
        # )

        # self.patient_list_page = PatientListPage(
        #     parent=self,
        #     shared_registry=None   # можно оставить None, будет создан локальный реестр
        # )
        # ↑ до 2026-10-16: своя таблица со своим реестром черновиков — изменения разных
        #   экранов нельзя было сохранить вместе (D1, app/draft/IMPLEMENTATION.md). Теперь —
        #   новый экран на общем хранилище окна; старый класс не тронут и остаётся запасным,
        #   если хранилище не создалось.
        if getattr(self, 'drafts', None) is not None:
            from interfaces.gui.gui_window.pages.draft_pages import PatientsDraftPage
            self.patient_list_page = PatientsDraftPage(
                self.drafts.store, save_handler=self._save_from_draft_page, parent=self,
            )
        else:
            self.patient_list_page = PatientListPage(parent=self, shared_registry=None)

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

        # Создаём новую страницу "Приёмы и фото"
        # self.appointment_photo_page = AppointmentPhotoFrame(
        #     parent=self,
        #     shared_registry=None   # или self._shared_draft_registry, если используется глобальный
        # )
        # ↑ до 2026-10-16: свой реестр, приёмы и фото сохранялись двумя транзакциями (D1, D2).
        #   Теперь — новый фрейм на общем хранилище окна; старый — запасной.
        if getattr(self, 'drafts', None) is not None:
            from interfaces.gui.gui_window.pages.draft_pages import AppointmentsPhotosDraftFrame
            self.appointment_photo_page = AppointmentsPhotosDraftFrame(
                self.drafts.store, save_handler=self._save_from_draft_page, parent=self,
            )
        else:
            self.appointment_photo_page = AppointmentPhotoFrame(parent=self, shared_registry=None)

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

            'appointment_photo': self.appointment_photo_page,
        }

        # Пилотный экран на наборах данных (2026-10-18, в духе RAD Studio): пациенты →
        # приёмы → фото. Стоит РЯДОМ со старыми экранами и их не меняет; не создался —
        # программа работает без него (см. app/utils/dataset/IMPLEMENTATION.md).
        try:
            from interfaces.gui.gui_window.pages.dataset_pilot_page import DataSetPilotPage
            self.dataset_pilot_page = DataSetPilotPage(
                drafts=getattr(self, 'drafts', None), save_handler=self.save_drafts, parent=self,
            )
            pages['dataset_pilot'] = self.dataset_pilot_page
        except Exception as e:
            self.dataset_pilot_page = None
            self.logger.exception(f"Пилотный экран наборов данных не создан: {e}")

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

    @Slot()
    def _on_dataset_pilot_clicked(self):
        """
        Переход на пилотный экран наборов данных (не создался — кнопка ничего не делает,
        причина — в журнале).

        Returns:
            None

        Пример:
            >>> window._on_dataset_pilot_clicked()
        """
        if getattr(self, 'dataset_pilot_page', None) is not None:
            self.page_manager.switch_to('dataset_pilot')

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
            # 'appointment_list',
            'appointment_photo',
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
    
    # def _correct_remote_path(
    #     self,
    #     remote: str,
    #     local: str,
    # ):
    #     # --- ДОБАВЛЕННАЯ ПРОВЕРКА И КОРРЕКЦИЯ REMOTE-ПУТИ ---
    #     # Если remote не заканчивается на расширение файла БД, добавляем имя из local
    #     # Расширения .db, .sqlite, .sqlite3
    #     # import os
    #     db_extensions = ('.db', '.sqlite', '.sqlite3')
    #     if not remote.lower().endswith(db_extensions):
    #         # Извлекаем имя файла из local пути
    #         local_filename = os.path.basename(local)
    #         # Нормализуем remote (убираем возможный завершающий слэш)
    #         remote = remote.rstrip('/\\')
    #         remote = f"{remote}/{local_filename}"
    #         self.logger.info(f"Корректировка remote пути: добавлено имя файла -> {remote}")
    #
    #     return remote
    # ↑ до 2026-11-07 (Ф2.1.2): то же правило есть в app.network.remote_db_file_path; там же
    #   пустой путь из настроек не роняет программу.

    @AppLogger.get_instance(
        name='SyncMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # def _start_download(self):
    #     """
    #     Запускает поток скачивания файла БД с Яндекс.Диска.
    #     Перед запуском проверяет наличие токена.
    #     """
    #     config = AppConfigManager.get_instance()
    #     token = config.get('YANDEX_TOKEN')
    #     remote = config.get('database_remote_path')
    #     local = config.get('database_local_path')
    #
    #     if not token:
    #         QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
    #         return
    #
    #     # Папка из настроек дополняется именем файла базы
    #     remote = remote_db_file_path(remote, local)
    #
    #     # Создаём и настраиваем поток загрузки
    #     self.download_thread = DownloadThread(token, remote, local)
    #     self.download_thread.progress.connect(self._update_progress)
    #     self.download_thread.finished.connect(self._on_db_download_finished)
    #     self.download_thread.error.connect(self._on_db_download_error)
    #
    #     # Показываем прогресс-бар (бесконечный режим до получения размера)
    #     self.progress_bar.setVisible(True)
    #     self.progress_bar.setRange(0, 0)
    #
    #     self.download_thread.start()
    #     self.logger.info("Запущен поток скачивания БД")
    #
    # @AppLogger.get_instance(
    #     name='SyncMixin',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _start_upload(self):
    #     """
    #     Запускает поток загрузки локального файла БД на Яндекс.Диск.
    #     """
    #     config = AppConfigManager.get_instance()
    #     token = config.get('YANDEX_TOKEN')
    #     remote = config.get('database_remote_path')
    #     local = config.get('database_local_path')
    #
    #     if not token:
    #         QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
    #         return
    #
    #     # Папка из настроек дополняется именем файла базы
    #     remote = remote_db_file_path(remote, local)
    #
    #     self.upload_thread = UploadThread(token, local, remote, overwrite=True)
    #     self.upload_thread.progress.connect(self._update_progress)
    #     self.upload_thread.finished.connect(self._on_upload_finished)
    #     self.upload_thread.error.connect(self._on_upload_error)
    #
    #     self.progress_bar.setVisible(True)
    #     self.progress_bar.setRange(0, 0)
    #
    #     self.upload_thread.start()
    #     self.logger.info("Запущен поток загрузки БД")
    # ↑ до 2026-11-07 (ТД-1): скачивание шло поверх рабочей базы, обрыв её портил; копии перед
    #   передачей не было, правки в окне и второй запуск во время передачи не запрещались.
    def _start_download(self) -> None:
        """
        Начинает безопасное скачивание базы: копия рабочей → поток скачивания и проверки.

        Рабочая база до конца проверки не меняется. Окно на время передачи не даёт править
        (:meth:`_set_transfer_running`). Замена — :meth:`_on_db_downloaded`.

        Example:
            >>> window._start_download()    # doctest: +SKIP
        """
        settings = self._prepare_transfer("Загрузка с Диска")
        if settings is None:
            return
        token, remote, local = settings
        self.download_thread = CheckedDownloadThread(
            token       =   token,      # токен
            remote_path =   remote,     # база на Диске
            local_path  =   local,      # рабочая база
            parent      =   self,       # окно
        )
        self.download_thread.progress.connect(self._update_progress)
        self.download_thread.downloaded.connect(self._on_db_downloaded)
        self.download_thread.finished.connect(self._on_db_download_finished)
        self.download_thread.failed.connect(self._log_transfer_failure)
        self.download_thread.error.connect(self._on_db_download_error)
        self._set_transfer_running(True)
        self.download_thread.start()
        self.logger.info("Запущен поток скачивания БД")

    def _start_upload(self) -> None:
        """
        Начинает выгрузку рабочей базы на Диск: копия рабочей → поток выгрузки.

        Example:
            >>> window._start_upload()      # doctest: +SKIP
        """
        settings = self._prepare_transfer("Выгрузка")
        if settings is None:
            return
        token, remote, local = settings
        self.upload_thread = UploadThread(
            token       =   token,      # токен
            local_path  =   local,      # рабочая база
            remote_path =   remote,     # база на Диске
            overwrite   =   True,       # файл на Диске заменяется
            parent      =   self,       # окно
        )
        self.upload_thread.progress.connect(self._update_progress)
        self.upload_thread.finished.connect(self._on_upload_finished)
        self.upload_thread.error.connect(self._on_upload_error)
        self._set_transfer_running(True)
        self.upload_thread.start()
        self.logger.info("Запущен поток загрузки БД")

    # проверки и резервная копия перед передачей
    def _prepare_transfer(
        self,
        action : str,   # название действия для сообщений
    ) -> Optional[Tuple[str, str, str]]:
        """
        Проверяет, можно ли начать обмен с Диском, и делает резервную копию рабочей базы.

        Передача не начинается, если идёт другая работа, не задан токен или не удалась копия.

        Args:
            action : (str) Название действия: «Загрузка с Диска», «Выгрузка».

        Returns:
            (Tuple[str, str, str]/None) Токен, путь к базе на Диске, рабочая база; None — начинать
                нельзя (сообщение уже показано).

        Example:
            >>> window._prepare_transfer('Выгрузка')    # doctest: +SKIP
            ('y0_…', 'Папка/clinic.db', './clinic.db')
        """
        running = self._running_task()
        if running:
            QMessageBox.warning(self, action, f"Сейчас идёт {running}. Дождитесь окончания.")
            return None
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        local = config.get('database_local_path')
        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return None
        try:
            self._db_backup_path = backup_db_before_transfer(local)
        except YandexDiskError as exc:
            self._log_transfer_failure(exc)
            QMessageBox.critical(
                self,                                                           # родитель
                "Резервная копия не сделана",                                   # заголовок
                f"{action} не начата: рабочая база не менялась.\n{exc}",        # текст
            )
            return None
        return token, remote_db_file_path(config.get('database_remote_path'), local), local

    # что сейчас нельзя прерывать
    def _running_task(self) -> Optional[str]:
        """
        Называет идущую работу, из-за которой нельзя выйти или начать новую передачу.

        Returns:
            (str/None) Название работы для сообщения; None — ничего не идёт.

        Example:
            >>> window._running_task() is None
            True
        """
        if getattr(self, '_transfer_running', False):
            return "обмен базой с Яндекс.Диском"
        parsing = getattr(self, 'parsing_thread', None)
        if parsing is not None and parsing.isRunning():
            return "импорт из Word"
        return None

    # начало и конец передачи: полоса и запрет правок
    def _set_transfer_running(
        self,
        running : bool,     # идёт ли передача
    ) -> None:
        """
        Отмечает начало или конец передачи: показывает полосу и запрещает работу с данными.

        Пока файл базы передаётся, правка записала бы в него изменения: выгрузка взяла бы
        несогласованный файл, а скачивание затёрло бы правку. Поэтому экраны и список действий
        на это время выключены.

        Args:
            running : (bool) Идёт ли передача.

        Example:
            >>> window._set_transfer_running(False)     # doctest: +SKIP
        """
        self._transfer_running = running
        self.stacked_widget.setEnabled(not running)
        self.action_combo.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:  # бегущая полоса до получения размера
            self.progress_bar.setRange(0, 0)

    # подробности сбоя передачи — в журнал
    def _log_transfer_failure(
        self,
        exc : BaseException,    # исключение передачи
    ) -> None:
        """
        Пишет подробности сбоя передачи в журнал; пользователю показывается короткий текст.

        Args:
            exc : (BaseException) Исключение; ``YandexDiskError`` — с ``log_text()``.

        Example:
            >>> window._log_transfer_failure(RuntimeError('сбой'))  # doctest: +SKIP
        """
        log_text = getattr(exc, 'log_text', None)
        self.logger.error(log_text() if callable(log_text) else f"Сбой передачи базы: {exc}")

    # итог скачивания: вопросы и замена рабочей базы
    @Slot(object)
    def _on_db_downloaded(
        self,
        result : CheckedDownload,   # проверенный временный файл и сведения
    ) -> None:
        """
        Решает судьбу скачанной и проверенной базы и заменяет ею рабочую.

        Порядок:
            1. содержимое совпало — замена не нужна;
            2. локальная база новее — вопрос, по умолчанию отказ;
            3. несохранённое пропадёт вместе с прежней базой — вопрос (:meth:`_confirm_db_replace`);
            4. замена и открытие (``install_checked_download``), обновление экранов.
        Отказ на любом шаге удаляет временный файл, рабочая база не меняется.

        Args:
            result : (CheckedDownload) Итог скачивания.

        Example:
            >>> window._on_db_downloaded(result)    # doctest: +SKIP
        """
        self._set_transfer_running(False)
        notes = list(result.warnings)
        if not result.needs_replace:
            discard_download(result)
            self._show_download_outcome("База на Яндекс.Диске совпадает с рабочей, замена не нужна.", notes)
            return
        if result.local_newer:
            reply = QMessageBox.question(
                self,                                                           # родитель
                "Локальная база новее",                                         # заголовок
                f"{notes.pop(0)}.\n\nЗаменить рабочую базу скачанной?",         # текст
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, # кнопки
                QMessageBox.StandardButton.No,                                  # по умолчанию отказ
            )
            if reply != QMessageBox.StandardButton.Yes:
                discard_download(result)
                self.logger.info("Скачанная база не установлена: локальная новее, отказ пользователя")
                return
        if not self._confirm_db_replace():
            discard_download(result)
            self.logger.info("Скачанная база не установлена: отказ из-за несохранённых изменений")
            return
        try:
            install_checked_download(result)
        except Exception as exc:
            self._log_transfer_failure(exc)
            self._reload_after_db_change()
            QMessageBox.critical(self, "База не заменена", f"{exc}\n\n{self._backup_note()}")
            return
        self.logger.info(f"Рабочая база заменена скачанной; копия прежней: {self._db_backup_path}")
        self._reload_after_db_change()
        self._show_download_outcome(f"База данных заменена скачанной.\n{self._backup_note()}", notes)

    # экраны после замены файла базы
    def _reload_after_db_change(self) -> None:
        """
        Обновляет экраны после замены файла базы; сбой экрана не мешает сообщить пользователю итог.

        Example:
            >>> window._reload_after_db_change()    # doctest: +SKIP
        """
        try:
            self.on_settings_changed(changed_blocks={'database'})
        except Exception as exc:
            self.logger.exception(f"Экраны не обновлены после замены базы: {exc}")

    # несохранённое перед заменой базы
    def _confirm_db_replace(self) -> bool:
        """
        Спрашивает о несохранённом перед заменой рабочей базы; согласие очищает черновики.

        Сохранять здесь бессмысленно: изменения записались бы в базу, которая сейчас будет заменена.
        Черновики ссылаются на записи прежней базы, поэтому при согласии они удаляются. Незавершённая
        правка экрана наборов данных, не прошедшая проверку, отменяет замену.

        Returns:
            (bool) True — можно заменять.

        Example:
            >>> window._confirm_db_replace()     # нет изменений — без вопросов
            True
        """
        pilot = getattr(self, 'dataset_pilot_page', None)
        if pilot is not None:
            problem = pilot.finish_pending_edits()
            if problem:
                QMessageBox.warning(
                    self,                                                                       # родитель
                    "Незавершённая правка",                                                     # заголовок
                    f"На экране «Наборы данных» правка не прошла проверку:\n{problem}\n\n"
                    "База не заменена. Исправьте или отмените правку и скачайте базу снова.",   # текст
                )
                return False
        drafts = getattr(self, 'drafts', None)
        if drafts is not None and not drafts.store.is_empty:
            reply = QMessageBox.question(
                self,                                                           # родитель
                "Несохранённые изменения",                                      # заголовок
                "Есть несохранённые изменения. После замены базы они будут потеряны: "
                "они относятся к прежней базе.\n\nЗаменить базу?",              # текст
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, # кнопки
                QMessageBox.StandardButton.No,                                  # по умолчанию отказ
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        if not self._confirm_old_pages_loss("Заменить базу"):
            return False
        if drafts is not None:
            drafts.store.clear()
        return True

    # строка о резервной копии для сообщений
    def _backup_note(self) -> str:
        """
        Возвращает строку о резервной копии рабочей базы для сообщений.

        Returns:
            (str) Где копия, или что рабочей базы не было.

        Example:
            >>> window._backup_note()   # doctest: +SKIP
            'Резервная копия прежней базы: ./backups/clinic - 2026-11-07_12-00-00.db'
        """
        path = getattr(self, '_db_backup_path', None)
        return f"Резервная копия прежней базы: {path}" if path else "Прежней рабочей базы не было."

    # сообщение об итоге скачивания
    def _show_download_outcome(
        self,
        text  : str,        # итог
        notes : List[str],  # предупреждения
    ) -> None:
        """
        Показывает итог скачивания и предупреждения проверки.

        Args:
            text  : (str) Итог.
            notes : (List[str]) Предупреждения (Диск не сообщил MD5 и т. п.).

        Example:
            >>> window._show_download_outcome('База заменена', [])      # doctest: +SKIP
        """
        lines = [text, *notes]
        QMessageBox.information(self, "Скачивание базы", "\n\n".join(lines))

    # временные файлы прошлого аварийного выхода
    def _remove_stale_db_downloads(self) -> None:
        """
        Убирает при старте недокачанные временные файлы базы.

        Example:
            >>> window._remove_stale_db_downloads()     # doctest: +SKIP
        """
        local = AppConfigManager.get_instance().get('database_local_path')
        removed = remove_stale_downloads(local) if local else []
        if removed:
            self.logger.info(f"Удалены временные файлы прерванного скачивания: {removed}")

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
    def _on_db_download_finished(
        self,
        code : int,     # код потока: 0 — успех
    ) -> None:
        """
        Завершение потока скачивания; итог при успехе уже разобран в :meth:`_on_db_downloaded`.

        Args:
            code : (int) Код потока.

        Example:
            >>> window._on_db_download_finished(0)  # doctest: +SKIP
        """
        self.progress_bar.setVisible(False)
        if code == 0:
            # QMessageBox.information(self, "Успех", "База данных успешно скачана.")
            # # # Перезагружаем данные на всех страницах-списках
            # # self._reload_all_list_pages()
            # # Перезагружаем все данные через существующий механизм
            # self.on_settings_changed(changed_blocks={'database'})
            # ↑ до 2026-11-07 (ТД-1): файл только скачан; вопросы, замена и сообщения — в
            #   _on_db_downloaded (его сигнал приходит первым)
            return
        else:
            self._set_transfer_running(False)
            # QMessageBox.critical(self, "Ошибка", f"Скачивание завершилось с кодом {code}")
            # ↑ до 2026-11-07 (Ф2.1.3): пользователю показывался код («-3»), а не его смысл
            QMessageBox.critical(self, "Ошибка", YaDiskResult.describe(code))

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
    def _on_db_download_error(
        self,
        message : str,  # причина
    ) -> None:
        """
        Показывает ошибку скачивания: рабочая база не менялась, временный файл уже удалён.

        Args:
            message : (str) Причина.

        Example:
            >>> window._on_db_download_error('Нет связи')   # doctest: +SKIP
        """
        self.logger.error(f"Download error: {message}")
        self._set_transfer_running(False)
        # QMessageBox.critical(self, "Ошибка", message)
        # ↑ до 2026-11-07 (ТД-1): пользователь не знал, что с рабочей базой
        QMessageBox.critical(self, "База не скачана", f"{message}\n\nРабочая база не менялась.")

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
        self._set_transfer_running(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно загружена.")
        else:
            # QMessageBox.critical(self, "Ошибка", f"Загрузка завершилась с кодом {code}")
            # ↑ до 2026-11-07 (Ф2.1.3): пользователю показывался код, а не его смысл
            QMessageBox.critical(self, "Ошибка", YaDiskResult.describe(code))

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
        self._set_transfer_running(False)
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
            # self.updater.download_progress.connect(self._on_download_progress)
            # self.updater.download_finished.connect(self._on_download_finished)
            # self.updater.download_error.connect(self._on_download_error)
            # ↑ до 2026-11-07 (MW2): SyncMixin стоит раньше в наследовании, и одноимённые обработчики
            #   брались у него: ошибка обновления шла как ошибка базы, файл — как код скачивания.
            self.updater.download_progress.connect(self._on_update_download_progress)
            self.updater.download_finished.connect(self._on_update_download_finished)
            self.updater.download_error.connect(self._on_update_download_error)
            self.updater.download_warning.connect(self._on_update_download_warning)

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
            # if hasattr(self, 'updater') and hasattr(self.updater, '_pending_release_data'):
            #     data = self.updater._pending_release_data
            # ↑ до 2026-11-07 (Ф2.1.4): чтение закрытого атрибута; у модуля есть свойство
            data = self.updater.pending_release_data if hasattr(self, 'updater') else None
            if data:
                # self.logger.debug(f"Pending release data keys: {list(self.updater._pending_release_data.keys())}")
                self.logger.debug(
                    f"_pending_release_data exists, "
                    f"type={type(data)}, "
                    f"keys={data.keys() if data else None}"
                )
                self._install_update(data)
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
    def _on_update_error(
        self,
        error_msg : str,    # текст ошибки проверки
    ) -> None:
        """
        Показывает ошибку ручной проверки обновлений; ошибку проверки при старте — только в журнал.

        Проверка при старте идёт без спроса, и окно с ошибкой при каждом запуске без сети только
        мешало бы.

        Args:
            error_msg : (str) Текст ошибки.

        Example:
            >>> window._on_update_error('Нет соединения')   # doctest: +SKIP
        """
        if getattr(self, '_auto_check', False):  # проверка при старте — тихая
            self._auto_check = False
            self.logger.info(f"Автоматическая проверка обновлений не удалась: {error_msg}")
            return
        QMessageBox.warning(self, "Ошибка", f"Не удалось проверить обновления:\n{error_msg}")

    # @AppLogger.get_instance(
    #     name='UpdateMixin',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    @Slot(int, int)
    def _on_update_download_progress(
        self,
        current : int,  # скачано байт
        total   : int,  # всего байт; 0 — неизвестно
    ) -> None:
        """
        Показывает прогресс скачивания обновления: в окне и в окне ожидания установки.

        Args:
            current : (int) Скачано байт.
            total   : (int) Всего байт; 0 — размер неизвестен, бегущая полоса.

        Example:
            >>> window._on_update_download_progress(10, 100)    # doctest: +SKIP
        """
        maximum = total if total > 0 else 0
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(current if total > 0 else 0)
        self.progress_bar.setVisible(True)
        dialog = getattr(self, 'update_progress_dialog', None)
        if dialog is not None:
            dialog.setRange(0, maximum)
            dialog.setValue(current if total > 0 else 0)

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_update_download_finished(
        self,
        file_path : str,    # скачанный файл обновления
    ) -> None:
        """
        Файл обновления только скачан (``AppUpdater.download_update``): спрашивает о замене.

        Обычная установка идёт другим путём (:meth:`_install_update`) и сюда не приходит.

        Args:
            file_path : (str) Скачанный файл.

        Example:
            >>> window._on_update_download_finished('/tmp/update.exe')  # doctest: +SKIP
        """
        self.progress_bar.setVisible(False)
        reply = QMessageBox.question(
            self, "Обновление загружено",
            f"Файл обновления сохранён:\n{file_path}\n\n"
            "Заменить текущую программу? (потребуется перезапуск)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes and self._resolve_unsaved_before_exit():
            self._apply_update_file(file_path)

    @AppLogger.get_instance(
        name='UpdateMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(str)
    def _on_update_download_error(
        self,
        error_msg : str,    # причина
    ) -> None:
        """
        Показывает, почему обновление не установлено; программа продолжает работу.

        Сюда приходит не только обрыв скачивания, но и отказ до него (нет прав на папку установки,
        не тот вид установки, нет файла для этой ОС) и несовпавшая контрольная сумма, поэтому
        заголовок не говорит о скачивании.

        Args:
            error_msg : (str) Причина.

        Example:
            >>> window._on_update_download_error('Нет прав на запись')  # doctest: +SKIP
        """
        self.logger.error(f"Update error: {error_msg}")
        self.progress_bar.setVisible(False)
        self._close_update_progress()
        # QMessageBox.warning(self, "Ошибка загрузки", f"Не удалось скачать обновление:\n{error_msg}")
        # ↑ до 2026-11-07 (MW3): заголовок неточен, это может быть отказ проверки или нет прав
        QMessageBox.warning(self, "Обновление не установлено", error_msg)

    @Slot(str)
    def _on_update_download_warning(
        self,
        text : str,     # предупреждение
    ) -> None:
        """
        Показывает предупреждение установки (релиз без контрольной суммы); установка продолжается.

        Args:
            text : (str) Предупреждение.

        Example:
            >>> window._on_update_download_warning('Нет хеша')  # doctest: +SKIP
        """
        self.logger.warning(f"Update warning: {text}")
        QMessageBox.warning(self, "Предупреждение об обновлении", text)

    # установка обновления: сначала несохранённое, потом запрет правок до выхода
    def _install_update(
        self,
        release_data : dict,    # данные релиза GitHub
    ) -> None:
        """
        Запускает установку обновления, не теряя несохранённого.

        Модуль обновлений в конце установки сам завершает программу (``sys.exit``), минуя
        ``closeEvent``. Поэтому вопрос о несохранённом задаётся до начала, а на время скачивания
        окно закрыто модальным окном ожидания: правка, сделанная после вопроса, пропала бы молча.
        При ошибке окно ожидания закрывается и работа продолжается.

        Args:
            release_data : (dict) Данные релиза.

        Example:
            >>> window._install_update(window.updater.pending_release_data)     # doctest: +SKIP
        """
        if not self._resolve_unsaved_before_exit():
            self.logger.info("Обновление отменено: есть несохранённые изменения")
            return
        self.update_progress_dialog = UpdateProgressDialog(self)
        self.update_progress_dialog.show()
        self.updater.apply_update_from_release(release_data)

    # закрыть окно ожидания установки
    def _close_update_progress(self) -> None:
        """
        Закрывает окно ожидания установки, если оно открыто.

        Example:
            >>> window._close_update_progress()     # doctest: +SKIP
        """
        dialog = getattr(self, 'update_progress_dialog', None)
        if dialog is not None:
            dialog.finish()
            self.update_progress_dialog = None

    # причина неудачного обновления Linux: показать один раз
    def _show_linux_update_failure(self) -> None:
        """
        Показывает при старте, почему обновление Linux откатилось; только на Linux, один раз.

        Скрипт обновления оставляет причину в файле, ``pop_linux_update_failure`` читает и удаляет
        его. Без сообщения пользователь просто увидел бы прежнюю версию. Подсказка о копии базы
        добавляется, если причина её не содержит: откат базу не возвращает.

        Example:
            >>> window._show_linux_update_failure()     # doctest: +SKIP
        """
        if current_system() != 'linux':
            return
        reason = pop_linux_update_failure()
        if reason is None:
            return
        self.logger.warning(f"Обновление откатилось: {reason}")
        text = reason if '.bak-' in reason else f"{reason}\n\n{LINUX_ROLLBACK_DB_HINT}"
        QMessageBox.warning(self, "Обновление не установлено", text)

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
#         elif system == "Linux":
#             # Создаём shell-скрипт
#             sh_content = f"""#!/bin/bash
# sleep 2
# cp "{new_file_path}" "{current_exe}"
# chmod +x "{current_exe}"
# "{current_exe}" &
# rm "$0"
# """
#             sh_path = os.path.join(tempfile.gettempdir(), "update_medicalapp.sh")
#             with open(sh_path, "w") as f:
#                 f.write(sh_content)
#             os.chmod(sh_path, 0o755)
#             subprocess.Popen([sh_path])
#             QApplication.quit()
        # ↑ до 2026-11-07 (MW4): ветка не работала. Linux-версия ставится архивом и запускается из
        #   исходников (sys.frozen ложно, выход выше), файл на замену окну никто не передаёт:
        #   обновление Linux — UpdateApplier и update.sh (app/UPDATER.md §1.3).
        else:
            QMessageBox.warning(self, "ОС не поддерживается", "Замена файла окном есть только на Windows; на Linux обновление ставит сама программа.")

class UpdateProgressDialog(QProgressDialog):
    """
    Модальное окно ожидания установки обновления; пользователь не может его закрыть.

    Пока оно открыто, правки в окне программы невозможны. Модуль обновлений не умеет отменять
    скачивание и сам завершает программу; при ошибке окно закрывает :meth:`finish`.

    Example:
        >>> UpdateProgressDialog(window).show()     # doctest: +SKIP
    """

    def __init__(
        self,
        parent : Optional[QWidget] = None,  # окно программы
    ) -> None:
        """
        Создаёт окно ожидания без кнопки отмены, с бегущей полосой до известного размера.

        Args:
            parent : (QWidget/None) Окно программы.

        Example:
            >>> UpdateProgressDialog().minimum()    # doctest: +SKIP
            0
        """
        super().__init__(
            "Обновление скачивается. После установки программа перезапустится.",    # текст
            "",                                                                     # кнопки нет
            0,                                                                      # начало шкалы
            0,                                                                      # 0..0 — бегущая
            parent,                                                                 # окно
        )
        self.setWindowTitle("Обновление программы")
        self.setCancelButton(None)
        self.setWindowModality(Qt.ApplicationModal)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setMinimumDuration(0)
        self._closing = False

    def finish(self) -> None:
        """
        Закрывает окно (установка не состоялась).

        Example:
            >>> dialog.finish()     # doctest: +SKIP
        """
        self._closing = True
        self.close()
        self.deleteLater()

    def reject(self) -> None:
        """
        Клавиша Esc: окно не закрывается, отменить установку нельзя.

        Example:
            >>> dialog.reject()     # doctest: +SKIP
        """

    def closeEvent(
        self,
        event : Any,    # событие закрытия Qt
    ) -> None:
        """
        Закрытие окна пользователем не срабатывает, срабатывает только :meth:`finish`.

        Args:
            event : (QCloseEvent) Событие закрытия.

        Example:
            >>> dialog.close()      # doctest: +SKIP
            False
        """
        if self._closing:
            event.accept()
        else:
            event.ignore()


# ========== Диалог прогресса ==========
class ParsingProgressDialog(QDialog):

    finished_closed = Signal()   # итоги показаны, окно закрыто

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
        self.summary_text.setMaximumHeight(200)
        self.summary_text.setVisible(False)
        layout.addWidget(self.summary_text)

        # Кнопка
        # self.close_btn = QPushButton("Отмена")
        # ↑ до 2026-11-07 (MW6): отменить импорт нельзя, поток продолжает писать в базу
        self.close_btn = QPushButton("Скрыть")
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
            item.setData(Qt.UserRole, name)  # имя файла: статус меняет только подпись рядом
            self._set_status(item, "⏳ Ожидание")
            self.list_widget.addItem(item)
            self._items[name] = item

    @Slot(str, str, str)
    def update_file_status(
        self,
        file_name : str,        # имя файла в списке
        status    : str,        # 'processing' / 'success' / 'failed'
        error_msg : str = "",   # текст ошибки; у 'success' — предупреждения (W2) или пусто
    ) -> None:
        """
        Показывает статус файла в списке диалога импорта.

        Args:
            file_name (str): Имя файла (как в ``set_file_list``).
            status (str): Статус от ``batch_parse``: 'processing', 'success', 'failed'.
            error_msg (str): Текст ошибки; у 'success' — предупреждения через «; »
                (например, телефон не распознан и не записан — ``parsers/IMPLEMENTATION.md``).

        Returns:
            None

        Пример:
            >>> dialog.update_file_status('а.docx', 'success', 'Телефон не распознан: «12-34-56» …')
        """
        item = self._items.get(file_name)
        if not item:
            return
        if status == "processing":
            self._set_status(item, "🔄 Обработка...")
            self.list_widget.scrollToItem(item)
        elif status == "success":
            # W2 (2026-10-25): предупреждения успешного файла — рядом со статусом
            if error_msg:
                self._set_status(item, f"✅ Готово ⚠️ {error_msg[:60]}")
            else:
                self._set_status(item, "✅ Готово")
            # self._set_status(item, "✅ Готово")
            # ↑ до 2026-10-25 (W2, parsers): предупреждения импорта не показывались
        elif status == "failed":
            self._set_status(item, f"❌ Ошибка: {error_msg[:60]}")
        else:
            self._set_status(item, "⏳ Ожидание")
        self.list_widget.repaint()

    # итоги импорта в окне прогресса
    def set_finished_results(
        self,
        summary : str,  # итоги: счётчики, ошибки, предупреждения, журнал
    ) -> None:
        """
        Показывает итоги рядом со списком файлов; кнопка закрывает окно и сообщает об этом.

        Args:
            summary : (str) Текст итогов (``parsers.word_importer.format_results``).

        Example:
            >>> dialog.set_finished_results('Обработано файлов: 1')     # doctest: +SKIP
        """
        self._finished = True
        # self.summary_text.clear()
        # self.summary_text.append(f"<b>Обработано файлов:</b> {total}")
        # self.summary_text.append(f"<b>Успешно:</b> {success}")
        # self.summary_text.append(f"<b>Ошибок:</b> {failed}")
        # self.summary_text.append(f"<b>Лог сохранён:</b> {log_path}")
        # ↑ до 2026-11-07 (MW5): без ошибок по файлам и предупреждений, которые есть в итогах парсера
        self.summary_text.setPlainText(summary)
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
            # self.accept()
            # ↑ до 2026-11-07 (MW5): Esc закрывал окно без сигнала, страницы не обновлялись
            self._on_close_finished()

    def closeEvent(self, event):
        if self._finished:
            self.finished_closed.emit()
        event.accept()

    def _set_status(self, item: QListWidgetItem, text: str):
        # item.setText(f"{item.text()}   {text}")
        # ↑ до 2026-11-07 (MW7): статусы копились в строке («⏳ Ожидание   🔄 Обработка...   ✅ Готово»)
        item.setText(f"{item.data(Qt.UserRole)}   {text}")

# ========== Поток парсинга ==========
class ParsingThread(QThread):
    finished = Signal(dict)
    error = Signal(str)
    file_list_ready = Signal(list)        # список имён файлов
    status_update = Signal(str, str, str)  # file_name, status, error_msg

    def __init__(
        self,
        folder_path   : str,            # папка с .docx
        find_existing : bool = False,   # искать пациента по ФИО + дате (ТД-8, выбор пользователя)
    ) -> None:
        """
        Поток импорта из Word.

        Args:
            folder_path (str): Папка с документами.
            find_existing (bool): Искать существующего пациента по ФИО + дате рождения
                (``parsers.word_importer.parse_one_file``, ТД-8).

        Returns:
            None

        Пример:
            >>> ParsingThread('C:/Документы', find_existing=True).start()
        """
        super().__init__()
        self.folder_path = folder_path
        self.find_existing = find_existing
        # def __init__(self, folder_path, update_existing=False):
        #     ...
        #     self.update_existing = update_existing
        # ↑ до 2026-10-25 (ТД-8, parsers): флаг «обновлять пациента» не работал и не задавался

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
                find_existing_patient=self.find_existing,     # ТД-8: выбор пользователя
                # update_existing_patient=self.update_existing,
                # ↑ до 2026-10-25 (ТД-8, parsers): параметр заменён find_existing_patient
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

    def _init_drafts(self) -> None:
        """
        Создаёт черновики приложения (``self.drafts``) и мост сигналов Qt
        (``self.drafts_bridge``).

        Ошибка создания не роняет окно: черновики будут недоступны (``None``), в лог —
        трассировка.

        Returns:
            None

        Пример:
            >>> window._init_drafts(); window.drafts.store.is_empty
            True
        """
        from app.draft.integration import create_app_drafts
        from interfaces.gui.gui_window.drafts_qt import DraftsQtBridge
        try:
            # self.drafts = create_app_drafts()
            # ↑ до 2026-11-07 (MW8): настройка DRAFT_MOVED_RULE не доходила до хранилища
            self.drafts = create_app_drafts(self._moved_rule_from_settings())
            self.drafts_bridge = DraftsQtBridge(self.drafts.store, parent=self)
        except Exception as e:
            self.logger.exception(f"Не удалось создать черновики: {e}")
            self.drafts = None
            self.drafts_bridge = None

    # правило перенесённой записи из настроек
    def _moved_rule_from_settings(self) -> MovedRule:
        """
        Читает правило «запись перенесли в новую, новую удалили» из настроек (В-21).

        Returns:
            (MovedRule) Правило; неизвестное значение в файле настроек — умолчание.

        Example:
            >>> window._moved_rule_from_settings()      # doctest: +SKIP
            <MovedRule.DELETE: 'delete'>
        """
        return MovedRule(
            draft_moved_rule_value(
                AppConfigManager.get_instance().get(DRAFT_MOVED_RULE_KEY),
            ),
        )

    def _save_from_draft_page(self, page) -> bool:
        """
        «Сохранить» на экране с новыми черновиками: вопрос «всё / текущее», затем
        ``save_drafts``. Цель «текущее» — выделенные строки, а если ничего не выделено —
        вся выборка страницы.

        Args:
            page: Страница (``DraftTablePage``), где нажали «Сохранить».

        Returns:
            ``True`` — сохранено.

        Пример:
            >>> window._save_from_draft_page(frame.appointments)
            True
        """
        from interfaces.gui.gui_window.pages.draft_pages import save_from_page
        return save_from_page(self, page, frame_nodes=page.page_nodes)

    def save_drafts(self, targets=None, scope=None) -> bool:
        """
        Сохраняет черновики с вопросами пользователю (новые родители, удаляемые ветки).

        Args:
            targets: Узлы цели (``None`` — всё).
            scope: Направления (``SaveScope``; по умолчанию ``BRANCH``).

        Returns:
            ``True`` — сохранено (или нечего сохранять); ``False`` — отказ или ошибка
            (сообщение пользователю уже показано).

        Пример:
            >>> window.save_drafts()
            True
        """
        from interfaces.gui.gui_window.drafts_qt import make_confirmations
        if self.drafts is None:
            return True
        ask_new, ask_delete = make_confirmations(self, self.drafts.schema)
        try:
            result = self.drafts.save(targets, scope, ask_new, ask_delete)
        except Exception as e:
            self.logger.exception(f"Ошибка сохранения черновиков: {e}")
            QMessageBox.critical(self, "Ошибка сохранения",
                                 f"Изменения не сохранены (в базе ничего не поменялось):\n{e}")
            return False
        return result is not None

    def closeEvent(self, event) -> None:
        """
        Закрытие окна: при несохранённых черновиках — вопрос «сохранить / не сохранять /
        отмена» (требование 8: черновики только в памяти).

        Args:
            event: Событие закрытия Qt.

        Returns:
            None

        Пример:
            >>> window.close()      # с изменениями — диалог
        """
        if not self._resolve_unsaved_before_exit():
            event.ignore()
            return
        # Поток уже сообщил об итоге, но мог ещё не выйти из run: уничтоженный на ходу он роняет процесс
        for thread in (self.download_thread, self.upload_thread):
            if thread is not None:
                thread.wait(2000)
        if getattr(self, 'drafts_bridge', None) is not None:
            self.drafts_bridge.detach()
        super().closeEvent(event)

    # несохранённое перед выходом: закрытие окна и установка обновления
    def _resolve_unsaved_before_exit(self) -> bool:
        """
        Решает с пользователем судьбу несохранённого перед выходом из программы.

        Порядок:
            0. идёт обмен с Диском или импорт — выйти нельзя, сообщение;
            1. незавершённая правка экрана наборов данных переводится в черновики;
            2. черновики: вопрос «сохранить / не сохранять / отмена» (требование 8);
            3. старые экраны со своими правками: вопрос, потерять ли их.

        Черновики при «не сохранять» здесь не очищаются: если выход не состоится (ошибка
        обновления), пользователь продолжит с ними.

        Returns:
            (bool) True — можно выходить; False — выход отменён (пользователем или ошибкой
                сохранения; сообщение уже показано).

        Example:
            >>> window._resolve_unsaved_before_exit()   # нет изменений — без вопросов
            True
        """
        from interfaces.gui.gui_window.drafts_qt import ask_on_close
        running = self._running_task()
        if running:  # поток нельзя прервать, а уничтоженный на ходу он роняет процесс
            QMessageBox.warning(self, "Идёт работа", f"Сейчас идёт {running}. Дождитесь окончания.")
            return False
        # F7 (2026-10-18): незавершённая правка на экране наборов данных — ещё не в черновиках
        # (и не в БД); без этого вопрос «сохранить?» её не видел, и она пропадала молча
        pilot = getattr(self, 'dataset_pilot_page', None)
        if pilot is not None:
            problem = pilot.finish_pending_edits()
            if problem:
                QMessageBox.warning(self, "Незавершённая правка",
                                    "На экране «Наборы данных» правка не прошла проверку:\n"
                                    f"{problem}\n\nИсправьте или отмените её.")
                return False
        drafts = getattr(self, 'drafts', None)
        if drafts is not None and not drafts.store.is_empty:
            choice = ask_on_close(self)
            if choice == 'cancel' or (choice == 'save' and not self.save_drafts()):
                return False
        return self._confirm_old_pages_loss("Выйти")

    # названия старых экранов, где есть свои несохранённые правки
    def _old_pages_with_changes(self) -> List[str]:
        """
        Возвращает названия экранов со своими несохранёнными правками, вне общих черновиков.

        Экран проверяется, если у него есть ``_has_unsaved_changes``. Сбой проверки считается
        наличием правок: лучше лишний вопрос, чем молчаливая потеря.

        Returns:
            (List[str]) Названия экранов; пусто — правок нет.

        Example:
            >>> window._old_pages_with_changes()
            []
        """
        manager = getattr(self, 'page_manager', None)
        titles : List[str] = []
        if manager is None:
            return titles
        for page_id, page in manager._pages.items():
            check = getattr(page, '_has_unsaved_changes', None)
            if check is None:
                continue
            try:
                changed = check()
            except Exception as e:
                self.logger.exception(f"Не удалось проверить правки экрана {page_id}: {e}")
                changed = True
            if changed:
                titles.append(manager._get_page_title(page_id))
        return titles

    # вопрос: потерять правки старых экранов или отказаться от действия
    def _confirm_old_pages_loss(
        self,
        action : str,   # название действия на кнопке вопроса, например 'Выйти'
    ) -> bool:
        """
        Спрашивает, продолжать ли действие, если на старых экранах есть несохранённые правки.

        Эти экраны хранят правки сами и сохраняют своей кнопкой. По умолчанию выбран отказ.

        Args:
            action : (str) Название действия для текста вопроса.

        Returns:
            (bool) True — правок нет или пользователь согласен их потерять.

        Example:
            >>> window._confirm_old_pages_loss('Выйти')     # нет правок — без вопроса
            True
        """
        titles = self._old_pages_with_changes()
        if not titles:
            return True
        reply = QMessageBox.question(
            self,                                                           # родитель
            "Несохранённые изменения",                                      # заголовок
            "Не сохранены изменения на экранах: {pages}.\n"
            "Они будут потеряны. {action} без сохранения?".format(
                pages   =   ', '.join(titles),  # экраны
                action  =   action,             # что собираемся сделать
            ),                                                              # текст
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, # кнопки
            QMessageBox.StandardButton.No,                                  # по умолчанию отказ
        )
        return reply == QMessageBox.StandardButton.Yes


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
        self.setMinimumSize(400, 300)
        self.resize(800, 600)  # желаемый начальный размер
        # Опционально: можно сбросить минимальный размер, чтобы окно можно было сжимать ещё сильнее,
        # но лучше оставить как есть, чтобы не ломать интерфейс
        # self.setMinimumSize(400, 300)  # уже установлен

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

        # Окно ожидания установки обновления (создаётся на время установки)
        self.update_progress_dialog = None

        # Идёт ли обмен с Диском и где копия рабочей базы последней передачи
        self._transfer_running = False
        self._db_backup_path = None

        # Недокачанные файлы базы от прошлого аварийного выхода
        self._remove_stale_db_downloads()

        # Построение интерфейса
        self._setup_ui()

        # Создаём менеджер действий
        self.action_manager = ActionManager(self)  

        # Подключение обработчика логов к виджету LogViewer
        self._setup_log_viewer()

        # Черновики (несохранённые изменения): ОДНО хранилище на всё окно — изменения со
        # всех экранов сохраняются вместе (D1, app/draft/IMPLEMENTATION.md). Создаётся ДО
        # страниц, чтобы они могли его получить. Пока страницы работают со старым
        # реестром (перевод — этап 5), хранилище пустое.
        self._init_drafts()

        # Создание страниц и менеджера страниц
        self._init_page_manager()

        self.sync_service = get_sync_service()

        # Подключение основных сигналов (кнопки, комбобокс, навигация)
        self._connect_signals()

        # Инициализация системы обновлений (собственный модуль)
        self._init_updater()

        # Откат обновления Linux: сообщение после показа окна
        QTimer.singleShot(0, self._show_linux_update_failure)

        # Не вызываем check_for_updates сразу, а планируем через 1 секунду
        QTimer.singleShot(1500, self._delayed_check_updates)

        # Определяем, существует ли файл конфигурации
        # from app.config.config_manager.manager import AppConfigManager
        config_manager = AppConfigManager.get_instance()
        
        # Применяем сохранённые настройки ко всем логгерам (если файл существует)
        if config_manager.config_exists:
            # from app.utils.logger.logger import AppLogger
            # AppLogger.reload_all_from_app_config()  # до развязки: логгер сам перечитывал конфиг
            # Логгер конфиг не читает — передаём актуальный (IMPLEMENTATION.md §7.1).
            # Основная настройка уже сделана setup_logging() в точке входа; здесь —
            # повторно, на случай запуска окна в обход main_gui_window.py.
            AppLogger.configure(config_manager.get_all())

        # CM1 (2026-10-14): config.msgpack был повреждён — менеджер переименовал его и
        # создал новый со значениями по умолчанию. Сообщаем, где битый файл, и открываем
        # настройки как при первом запуске (окно — после показа главного окна).
        if config_manager.broken_config_message:
            # QTimer.singleShot(0, lambda: QMessageBox.warning(
            #     self, "Конфигурация восстановлена", config_manager.broken_config_message))
            # ↑ до CM15 (проверка конфига 3, 2026-10-15): тот же заголовок и для файла,
            #   который не удалось ПРОЧИТАТЬ (заблокирован, нет прав) — он не
            #   восстанавливался и не тронут (broken_config_backup = None).
            title = ("Конфигурация восстановлена" if config_manager.broken_config_backup
                     else "Конфигурация не загружена")
            # M10a (проверка конфига 3): текст берём СЕЙЧАС. Окно показывается позже, а
            # экран настроек при входе (ниже) вызывает load(), который сбрасывает
            # broken_config_message (CM10) — окно выходило пустым.
            message = config_manager.broken_config_message
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, title, message))
            self.page_manager.switch_to(
                'settings',
                add_to_history=False,
                extra_data={'first_start': True}
            )
        elif not config_manager.config_exists:
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
    def _delayed_check_updates(self) -> None:
        """
        Запускает проверку обновлений через 1,5 с после старта окна, если она не выключена.

        Выключают настройка ``UPDATE_CHECK_ON_START`` и переменная ``PROJECT_MED_NO_UPDATE_CHECK``
        (:func:`startup_update_check_enabled`). Сам запрос идёт в потоке ``UpdateChecker``, окно не
        ждёт сеть. Проверка тихая: «обновлений нет» и ошибка не показываются, только найденное
        обновление.

        Example:
            >>> window._delayed_check_updates()     # doctest: +SKIP
        """
        if not startup_update_check_enabled(AppConfigManager.get_instance()):
            self.logger.info("Проверка обновлений при запуске выключена")
            return
        if getattr(self, 'updater', None) is None:  # модуль обновлений не создался — причина в журнале
            return
        # Автоматическая проверка обновлений при старте (без показа сообщения "нет обновлений")
        self._auto_check = True
        self.updater.check_for_updates()
        # # Проверяем доступность GitHub перед автоматической проверкой
        # from app.updater import is_github_reachable
        # if is_github_reachable():
        #     self.updater.check_for_updates()
        #
        # else:
        #     self.logger.info("GitHub недоступен, автоматическая проверка обновлений пропущена")
        # ↑ до 2026-11-07 (MW1): запрос к GitHub в потоке окна останавливал его на время ожидания
        #   (до 3 с); нет связи теперь видно из самой проверки, ошибка идёт только в журнал.

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
        running = self._running_task()
        if running:  # второй поток импорта или импорт во время замены базы
            QMessageBox.warning(self, "Импорт из Word", f"Сейчас идёт {running}. Дождитесь окончания.")
            return

        # Диалог выбора папки
        # Выбор открывается в папке документов из настроек (пусто — папка по умолчанию Qt)
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку с файлами .docx",
            str(AppConfigManager.get_instance().get(WORD_DOCUMENTS_PATH_KEY, '') or ''),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if not folder:
            return

        # ТД-8: пользователь сам решает, искать ли существующих пациентов (ФИО + год)
        find_existing = self._ask_find_existing(folder)
        if find_existing is None:
            return

        # Создаём и показываем диалог прогресса
        self.progress_dialog = ParsingProgressDialog(self)
        self.progress_dialog.show()

        # Создаём и запускаем поток
        self.parsing_thread = ParsingThread(
            folder,
            find_existing = find_existing,  # выбор пользователя (ТД-8)
        )
        # self.parsing_thread = ParsingThread(folder, update_existing=False)
        # ↑ до 2026-10-25 (ТД-8, parsers): поиск пациента не предлагался
        self.parsing_thread.file_list_ready.connect(self.progress_dialog.set_file_list)
        self.parsing_thread.status_update.connect(self.progress_dialog.update_file_status)
        self.parsing_thread.finished.connect(self._on_parsing_finished)
        self.parsing_thread.error.connect(self._on_parsing_error)

        self.parsing_thread.start()

    def _ask_find_existing(
        self,
        folder : str,   # выбранная папка (показывается в вопросе)
    ) -> Optional[bool]:
        """
        Перед импортом из Word: подтверждение и флажок «искать существующих пациентов»
        (ТД-8, решение владельца 2026-10-25 — выбор пользователя, по умолчанию выключен).

        Args:
            folder (str): Папка с документами.

        Returns:
            Optional[bool]: None — пользователь отменил импорт; True / False — флажок.

        Пример:
            >>> window._ask_find_existing('C:/Документы')     # «Импорт», флажок снят
            False
        """
        box = QMessageBox(self)
        box.setWindowTitle("Импорт из Word")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Импортировать документы из папки:\n{folder}")
        box.setInformativeText(
            "Без флажка каждый документ — новый пациент.\n"
            "С флажком пациент ищется по ФИО и дате рождения: приёмы добавятся к найденному, "
            "повторные приёмы пропускаются. Дубли можно объединить в программе."
        )
        # ссылка на флажок — своя: box.checkBox() в PySide6 может вернуть голый QObject
        find_box = QCheckBox("Искать существующих пациентов (ФИО + дата рождения)")
        box.setCheckBox(find_box)
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.button(QMessageBox.Ok).setText("Импорт")
        box.button(QMessageBox.Cancel).setText("Отмена")
        box.setDefaultButton(QMessageBox.Ok)

        if box.exec() != QMessageBox.Ok:
            return None
        return find_box.isChecked()

    @AppLogger.get_instance(
        name='MainWindow',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_parsing_finished(
        self,
        results : dict,   # результаты batch_parse (+ log_path)
    ) -> None:
        """
        Показывает итоги импорта из Word: счётчики, ошибки, предупреждения (W2: нераспознанный
        телефон не записан), путь к журналу (``parsers.word_importer.format_results``).

        Окно прогресса открыто — итоги в нём, рядом со статусами файлов, страницы обновляются
        при его закрытии. Пользователь его скрыл — отдельным сообщением, страницы сразу.

        Args:
            results (dict): Результаты ``batch_parse`` с ключом ``log_path``.

        Returns:
            None

        Пример:
            >>> window._on_parsing_finished({'total': 1, 'success': 1, 'failed': 0, 'warnings': []})
        """
        # if hasattr(self, 'progress_dialog'):
        #     self.progress_dialog.accept()
        #     self.progress_dialog = None
        #
        # total = results.get('total', 0)
        # success = results.get('success', 0)
        # failed = results.get('failed', 0)
        # log_path = results.get('log_path', 'не указан')
        #
        # if hasattr(self, 'progress_dialog') and self.progress_dialog:
        #     self.progress_dialog.set_finished_results(total, success, failed, log_path)
        #     if not hasattr(self, '_parsing_closed_connected'):
        #         self.progress_dialog.finished_closed.connect(self._on_parsing_dialog_closed)
        #         self._parsing_closed_connected = True
        # else:
        # ↑ до 2026-11-07 (MW5): окно закрывалось до показа итогов, ветка с итогами в окне не работала

        # W2 (2026-10-25): итоги с ошибками и предупреждениями — общим текстом парсера
        # (парсер уже загружен потоком импорта, если дошли до итогов)
        from parsers.word_importer import format_results
        dialog = getattr(self, 'progress_dialog', None)
        if dialog is not None and dialog.isVisible():
            dialog.set_finished_results(format_results(results))
            dialog.finished_closed.connect(self._on_parsing_dialog_closed)
        else:
            self.progress_dialog = None
            QMessageBox.information(
                self,                       # родитель
                "Парсинг завершён",         # заголовок
                format_results(results),    # счётчики, ошибки, предупреждения, журнал
            )
            # QMessageBox.information(
            #     self, "Парсинг завершён",
            #     f"Обработано файлов: {total}\nУспешно: {success}\nОшибок: {failed}\nЛог сохранён: {log_path}"
            # )
            # ↑ до 2026-10-25 (W2, parsers): без ошибок по файлам и предупреждений
            self._refresh_after_parsing()

    def _on_parsing_dialog_closed(self):
        """Вызывается, когда пользователь закрыл диалог прогресса после завершения парсинга."""
        self._refresh_after_parsing()
        self.progress_dialog = None

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
    def _on_parsing_error(
        self,
        error_msg : str,    # причина сбоя импорта
    ) -> None:
        """
        Показывает сбой импорта из Word: в окне прогресса, если оно открыто, иначе сообщением.

        Часть файлов могла быть обработана, поэтому страницы обновляются при закрытии окна.

        Args:
            error_msg : (str) Причина.

        Example:
            >>> window._on_parsing_error('Нет доступа к папке')     # doctest: +SKIP
        """
        # if hasattr(self, 'progress_dialog') and self.progress_dialog:
        #     self.progress_dialog.summary_text.setVisible(True)
        #     self.progress_dialog.summary_text.clear()
        #     self.progress_dialog.summary_text.append(f"<b>Ошибка выполнения парсинга:</b>\n{error_msg}")
        #     self.progress_dialog.close_btn.setText("Закрыть")
        #     try:
        #         self.progress_dialog.close_btn.clicked.disconnect()
        #     except TypeError:
        #         pass
        #     self.progress_dialog.close_btn.clicked.connect(self._on_parsing_dialog_closed)
        #     self.progress_dialog._finished = True
        # else:
        #     QMessageBox.critical(self, "Ошибка", f"При выполнении парсинга произошла ошибка:\n{error_msg}")
        # ↑ до 2026-11-07 (MW5): кнопка «Закрыть» не закрывала модальное окно, программа стояла
        dialog = getattr(self, 'progress_dialog', None)
        if dialog is not None and dialog.isVisible():
            dialog.set_finished_results(f"Ошибка выполнения парсинга:\n{error_msg}")
            dialog.finished_closed.connect(self._on_parsing_dialog_closed)
        else:
            self.progress_dialog = None
            QMessageBox.critical(self, "Ошибка", f"При выполнении парсинга произошла ошибка:\n{error_msg}")
            self._refresh_after_parsing()

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

        # Пилотный экран наборов данных (2026-10-18) — отдельной кнопкой, чтобы не сдвигать
        # номера пунктов списка действий (_on_action_selected выбирает по номеру)
        self.dataset_pilot_btn = QPushButton("Наборы данных (пилот)")
        self.dataset_pilot_btn.setToolTip("Пациенты → приёмы → фото на наборах данных")
        self.dataset_pilot_btn.clicked.connect(self._on_dataset_pilot_clicked)
        self.header_layout.addWidget(self.dataset_pilot_btn)

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

        # # ДЕБАГ КНОПКА. ВЫВОД РАЗМЕРОВ ОБЬЕКТОВ В КОНСОЛЬ!
        # self.dump_sizes_btn = QPushButton("Dump sizes")
        # self.dump_sizes_btn.clicked.connect(self._dump_layout_sizes)
        # self.header_layout.addWidget(self.dump_sizes_btn)

        # #  кнопка для дампа ячеек таблицы фото
        # self.dump_photo_cells_btn = QPushButton("Dump photo cells")
        # self.dump_photo_cells_btn.clicked.connect(self._dump_photo_cell_sizes)
        # self.header_layout.addWidget(self.dump_photo_cells_btn)

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

        # Правило перенесённой записи: построенный план устаревает сам
        if changed_blocks is None or 'drafts' in changed_blocks:
            if getattr(self, 'drafts', None) is not None:
                self.drafts.store.moved_rule = self._moved_rule_from_settings()

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

            # Экран наборов данных не входит в списки выше: держал бы строки прежней базы
            pilot = getattr(self, 'dataset_pilot_page', None)
            if pilot is not None and pilot._opened:
                pilot.open_data()
        
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


# ----------- методы для отладки расположения виджетов
    def _dump_layout_sizes(self):
        """Выводит в консоль дерево размеров всех виджетов окна."""
        print("\n=== DUMP LAYOUT SIZES ===")
        self._dump_widget_info(self, indent=0)
        print("=== END DUMP ===\n")

    def _dump_widget_info(self, widget, indent=0):
        """Рекурсивно выводит информацию о виджете и его дочерних элементах."""
        prefix = "  " * indent
        try:
            min_hint = widget.minimumSizeHint()
            min_size = widget.minimumSize()
            size = widget.size()
            print(f"{prefix}{widget.__class__.__name__}: size={size.width()}x{size.height()}, "
                  f"minSize={min_size.width()}x{min_size.height()}, "
                  f"minSizeHint={min_hint.width()}x{min_hint.height()}, "
                  f"visible={widget.isVisible()}")
        except Exception as e:
            print(f"{prefix}{widget.__class__.__name__}: error getting size info - {e}")

        for child in widget.findChildren(QWidget):
            # Проверяем, что родитель именно этот виджет, а не вложенный глубже
            if child.parent() == widget:
                self._dump_widget_info(child, indent + 1)

    def _dump_photo_cell_sizes(self):
        """Выводит в консоль размеры ячеек таблицы фото (для отладки)."""
        current_page = self.page_manager._pages.get(self.page_manager.current_page_id)
        if not current_page:
            print("Текущая страница не найдена")
            return

        # Проверяем, является ли текущая страница AppointmentPhotoFrame
        if hasattr(current_page, 'photo_page') and hasattr(current_page.photo_page, 'table_view'):
            table = current_page.photo_page.table_view
            model = table.model()
            if not model:
                print("Нет модели у таблицы фото")
                return

            # Находим индекс столбца с фото (первый DATA-столбец с ImageThumbnailDelegate)
            photo_col = -1
            for col in range(model.columnCount()):
                delegate = table.itemDelegateForColumn(col)
                if delegate and delegate.__class__.__name__ == 'ImageThumbnailDelegate':
                    photo_col = col
                    break

            if photo_col == -1:
                print("Столбец с фото не найден")
                return

            source_model = current_page.photo_page.source_model
            if source_model is None:
                print("Нет source_model")
                return

            # Импортируем ImageThumbnailDelegate для доступа к кэшу (локальный импорт)
            from interfaces.gui.gui_window.widgets.delegate.image_delegate import ImageThumbnailDelegate

            print("\n=== DUMP PHOTO CELL SIZES ===")
            for row in range(source_model.rowCount()):
                # Получаем DTO и ID сущности
                dto = source_model.get_item_at_row(row)
                entity_id = getattr(dto, 'id', None) if dto else None

                # Получаем индекс в таблице (через прокси-модель, если есть)
                proxy_model = table.model()
                if proxy_model and hasattr(proxy_model, 'mapFromSource'):
                    source_idx = source_model.index(row, photo_col)
                    proxy_idx = proxy_model.mapFromSource(source_idx)
                else:
                    proxy_idx = source_model.index(row, photo_col)

                if not proxy_idx.isValid():
                    continue

                rect = table.visualRect(proxy_idx)
                row_height = table.rowHeight(proxy_idx.row())  # используем индекс после прокси

                # Путь к файлу (из source_model через UserRole)
                file_path = source_model.data(source_model.index(row, photo_col), Qt.UserRole)
                full_path = file_path
                if file_path and not os.path.isabs(file_path):
                    storage_path = current_page.photo_page._get_photo_storage_path()
                    full_path = os.path.join(storage_path, file_path)

                # Размер миниатюры из кэша (глобальный кэш делегата)
                cache_info = ""
                if full_path in ImageThumbnailDelegate._cache:
                    pixmap = ImageThumbnailDelegate._cache[full_path]
                    cache_info = f", cached_size={pixmap.width()}x{pixmap.height()}"

                print(f"Row {row} (id={entity_id}): rect={rect.width()}x{rect.height()} at ({rect.x()},{rect.y()}), "
                    f"rowHeight={row_height}{cache_info}, path={file_path}")

            print("=== END DUMP ===\n")
        else:
            print("Текущая страница не содержит таблицу фото или не является AppointmentPhotoFrame")