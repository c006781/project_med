# -*- coding: utf-8 -*-
"""
interfaces/gui/gui_window/main_window.py

Главное окно приложения.
Содержит верхнюю панель (шапку) с меню, прогресс-бар, кнопку назад,
область для хлебных крошек и центральный стек для страниц.
Управляет навигацией через PageManager.
Использует динамические страницы на основе DTO.
"""

import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox,
    QStackedWidget, QFrame, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QIcon

from interfaces.gui.gui_window.controllers.page_manager import PageManager
from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage
from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.settings_page import SettingsPage
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer, LogViewerHandler

from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service
)
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
from app.config.config_manager.manager import AppConfigManager
from app.network import DownloadThread, UploadThread
from app.utils.logger.logger import AppLogger


class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    """


    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Медицинское приложение")
        self.resize(1200, 800)

        # Логгер для этого класса
        self.logger = AppLogger.get_instance("gui.MainWindow")

        # Потоки для синхронизации
        self.download_thread = None
        self.upload_thread = None

        # Инициализация UI
        self._setup_ui()

        self._setup_log_viewer()  # логер

        # Инициализация менеджера страниц
        self._init_page_manager()

        # Подключение сигналов
        self._connect_signals()
        
        config_manager = AppConfigManager.get_instance()
        if not config_manager.config_exists:
            self.page_manager.switch_to('settings', extra_data={'first_start': True})
        else:
            self.page_manager.switch_to('patient_list')

        self.logger.info("Главное окно создано")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_log_viewer(self):
        handler = LogViewerHandler(self.log_viewer)
        AppLogger.add_global_handler(handler)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """Создаёт все элементы интерфейса."""
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Основной вертикальный layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Шапка (верхняя панель) ---
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_frame.setMaximumHeight(60)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 5, 10, 5)

        # Левая часть шапки: выпадающий список с действиями
        self.action_combo = QComboBox()
        self.action_combo.addItem("Скачать БД")
        self.action_combo.addItem("Сохранить изменения")
        self.action_combo.addItem("Отправить БД на сервер")
        self.action_combo.setEditable(False)
        self.action_combo.setMaximumWidth(200)
        header_layout.addWidget(self.action_combo)

        # Кнопка настроек
        self.settings_btn = QPushButton("Настройки")
        self.settings_btn.setMaximumWidth(100)
        header_layout.addWidget(self.settings_btn)

        # Растяжка
        header_layout.addStretch()

        # Хлебные крошки (второй уровень шапки)
        self.breadcrumbs_label = QLabel("Главная")
        self.breadcrumbs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.breadcrumbs_label)

        header_layout.addStretch()

        # Кнопка "Назад"
        self.back_btn = QPushButton("← Назад")
        self.back_btn.setMaximumWidth(80)
        self.back_btn.setEnabled(False)  # изначально недоступна
        header_layout.addWidget(self.back_btn)

        # Прогресс-бар (справа)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)  # скрыт по умолчанию
        header_layout.addWidget(self.progress_bar)

        main_layout.addWidget(header_frame)

        # --- Центральная область (стек страниц) ---
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # --- логирование -
        # Добавляем виджет логов в основной layout (после стека)
        self.log_viewer = LogViewer()
        main_layout.addWidget(self.log_viewer)

        # Кнопка для показа/скрытия логов (добавляем в шапку)
        self.show_log_btn = QPushButton("Показать логи")
        self.show_log_btn.setCheckable(True)
        self.show_log_btn.toggled.connect(self.log_viewer.setVisible)
        header_layout.addWidget(self.show_log_btn)  # например, после прогресс-бара

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._init_page_manager",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _init_page_manager(self):
        """
        Создаёт динамические страницы для каждой сущности.
        Определяет колонки, выпадающие списки, исключаемые поля.
        """
        # --- Пациенты ---
        patient_columns = [
            {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
            {'name': 'last_name', 'title': 'Фамилия', 'type': str, 'editable': True},
            {'name': 'first_name', 'title': 'Имя', 'type': str, 'editable': True},
            {'name': 'birth_date', 'title': 'Дата рождения', 'type': datetime.date, 'editable': True},
            {'name': 'phone', 'title': 'Телефон', 'type': str, 'editable': True},
            {'name': 'email', 'title': 'Email', 'type': str, 'editable': True},
        ]
        # self.patient_list_page = DynamicListPage(
        #     service=get_patient_service(),
        #     columns=patient_columns,
        #     page_title="Пациенты",
        #     add_action_text="Добавить пациента"
        # )
        self.patient_list_page = DynamicListPage(
            service=get_patient_service(),
            columns=patient_columns,
            page_title="Пациенты",
            add_action_text="Добавить пациента",
            action_button_text="Приёмы"          # дополнительная кнопка
        )
        self.patient_edit_page = DynamicEditPage(
            service=get_patient_service(),
            dto_class=PatientDTO,
            page_title="Редактирование пациента",
            exclude_fields=['id'],
            field_rename={
                'first_name': 'Имя',
                'last_name': 'Фамилия',
                'birth_date': 'Дата рождения',
                'phone': 'Телефон',
                'email': 'Email'
            }
        )
        self.patient_edit_page.list_page_id = 'patient_list'   # запоминаем ID списка пациентов


        # --- Приёмы ---
        appointment_columns = [
            {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
            {'name': 'patient_name', 'title': 'Пациент', 'type': str, 'editable': False},  # виртуальное поле
            {'name': 'date', 'title': 'Дата', 'type': datetime.date, 'editable': True},
            {'name': 'time', 'title': 'Время', 'type': datetime.time, 'editable': True},
            {'name': 'note_text', 'title': 'Заметка', 'type': str, 'editable': True},
        ]
        self.appointment_list_page = DynamicListPage(
            service=get_appointment_service(),
            columns=appointment_columns,
            page_title="Приёмы",
            add_action_text="Новый приём"
        )
        self.appointment_edit_page = DynamicEditPage(
            service=get_appointment_service(),
            dto_class=AppointmentDTO,
            page_title="Редактирование приёма",
            exclude_fields=['id', 'patient_name', 'note_id'],
            field_choices={},  # можно добавить, например, список пациентов
            field_rename={
                'patient_id': 'ID пациента',
                'date': 'Дата',
                'time': 'Время',
                'note_text': 'Заметка'
            }
        )
        
        self.appointment_edit_page.list_page_id = 'appointment_list'

        # --- Заметки ---
        note_columns = [
            {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
            {'name': 'text', 'title': 'Текст', 'type': str, 'editable': True},
        ]
        self.note_list_page = DynamicListPage(
            service=get_note_service(),
            columns=note_columns,
            page_title="Заметки",
            add_action_text="Создать заметку"
        )
        self.note_edit_page = DynamicEditPage(
            service=get_note_service(),
            dto_class=AppointmentNoteDTO,
            page_title="Редактирование заметки",
            exclude_fields=['id'],
            field_rename={'text': 'Текст заметки'}
        )
        self.note_edit_page.list_page_id = 'note_list'

        # --- Фото ---
        photo_columns = [
            {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
            {'name': 'appointment_id', 'title': 'ID приёма', 'type': int, 'editable': False},
            {'name': 'file_path', 'title': 'Файл', 'type': str, 'editable': False},
            {'name': 'description', 'title': 'Описание', 'type': str, 'editable': True},
        ]
        self.photo_list_page = DynamicListPage(
            service=get_photo_service(),
            columns=photo_columns,
            page_title="Фотографии",
            add_action_text="Добавить фото"
        )
        self.photo_edit_page = DynamicEditPage(
            service=get_photo_service(),
            dto_class=PhotoDTO,
            page_title="Редактирование фото",
            exclude_fields=['id'],
            field_rename={
                'appointment_id': 'ID приёма',
                'file_path': 'Путь к файлу',
                'description': 'Описание'
            }
        )
        self.photo_edit_page.list_page_id = 'photo_list'

        

        # --- Страница настроек (оставляем как есть) ---
        self.settings_page = SettingsPage()

        # Добавляем все страницы в стек
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

        for page in pages.values():
            self.stacked_widget.addWidget(page)

        self.page_manager = PageManager(self.stacked_widget, pages)

        # Проверяем наличие файла конфигурации
        # config_manager = AppConfigManager.get_instance()
        # if not config_manager.config_exists:
        #     # Первый запуск – открываем настройки с флагом
        #     self.page_manager.switch_to('settings', extra_data={'first_start': True})
        # else:
        #     # Обычный запуск – открываем список пациентов
        #     self.page_manager.switch_to('patient_list')  # начальная страница
        
        # self.page_manager.switch_to('patient_list')  # начальная страница

        # Передаём ссылку на главное окно каждой странице (если нужно)
        for page in pages.values():
            if hasattr(page, 'set_main_window'):
                page.set_main_window(self)

        # Подключаем сигналы от страниц
        self._connect_page_signals()

        # # Подключаем сигналы от менеджера страниц
        # self._connect_page_manager_signals()

        # # Подключаем сигналы от сервисов
        # self._connect_services_signals()

        # # Подключаем основные сигналы
        # self._connect_signals()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_patient_appointments_requested",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_patient_appointments_requested(self, patient_dto):
        """Переход к списку приёмов выбранного пациента."""
        self.page_manager.switch_to(
            'appointment_list',
            extra_data={'patient_id': patient_dto.id}
        )

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._connect_signals",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_signals(self):
        """Подключает основные сигналы (кнопки, комбобокс, навигация)."""
        # Кнопка назад
        self.back_btn.clicked.connect(self._on_back_clicked)

        # Кнопка настроек
        self.settings_btn.clicked.connect(self._on_settings_clicked)

        # Выбор действия в комбобоксе
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)

        # Сигналы от менеджера страниц
        self.page_manager.navigation_changed.connect(self._on_navigation_changed)
        self.page_manager.page_entered.connect(self._on_page_entered)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._connect_page_signals",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_page_signals(self):
        """Связывает сигналы страниц с методами навигации и удаления."""
        # Пациенты
        self.patient_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('patient_edit', extra_data=None)
        )
        self.patient_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to('patient_edit', extra_data={'id': dto.id})
        )
        self.patient_list_page.delete_requested.connect(self._on_patient_delete)
        
        self.patient_list_page.action_requested.connect(self._on_patient_appointments_requested)

        # Приёмы
        self.appointment_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'appointment_edit', 
                extra_data={
                    'patient_id': self.appointment_list_page.current_patient_id
                }
            )
        )
        self.appointment_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to('appointment_edit', extra_data={'id': dto.id})
        )
        self.appointment_list_page.delete_requested.connect(self._on_appointment_delete)

        # Заметки
        self.note_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('note_edit', extra_data=None)
        )
        self.note_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to('note_edit', extra_data={'id': dto.id})
        )
        self.note_list_page.delete_requested.connect(self._on_note_delete)

        # Фото
        self.photo_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to('photo_edit', extra_data=None)
        )
        self.photo_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to('photo_edit', extra_data={'id': dto.id})
        )
        self.photo_list_page.delete_requested.connect(self._on_photo_delete)

    # ----------------------------------------------------------------------
    # Обработчики удаления (вызываются из страниц)
    # ----------------------------------------------------------------------
    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_patient_delete",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_patient_delete(self, dto):
        """Удаление пациента с подтверждением."""
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить пациента {dto.last_name} {dto.first_name}? Все связанные приёмы и фото также будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                service = get_patient_service()
                service.delete_patient(dto.id)
                QMessageBox.information(self, "Успех", "Пациент удалён.")
                self.patient_list_page._load_data()  # обновить список
                self.logger.info(f"Удалён пациент ID={dto.id}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления пациента")
    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_appointment_delete",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_appointment_delete(self, dto):
        """Удаление приёма."""
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить приём ID {dto.id} от {dto.date}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                service = get_appointment_service()
                service.delete_appointment(dto.id)
                QMessageBox.information(self, "Успех", "Приём удалён.")
                self.appointment_list_page._load_data()
                self.logger.info(f"Удалён приём ID={dto.id}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления приёма")
    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_note_delete",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_note_delete(self, dto):
        """Удаление заметки."""
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить заметку ID {dto.id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                service = get_note_service()
                service.delete_note(dto.id)
                QMessageBox.information(self, "Успех", "Заметка удалена.")
                self.note_list_page._load_data()
                self.logger.info(f"Удалена заметка ID={dto.id}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления заметки")
    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_photo_delete",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_photo_delete(self, dto):
        """Удаление фотографии."""
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить фото ID {dto.id}? Файл будет удалён с диска.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                service = get_photo_service()
                service.delete_photo(dto.id)
                QMessageBox.information(self, "Успех", "Фото удалено.")
                self.photo_list_page._load_data()
                self.logger.info(f"Удалено фото ID={dto.id}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления фото")

    # ----------------------------------------------------------------------
    # Обработчики навигации и действий
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_back_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_back_clicked(self):
        """Обработчик кнопки 'Назад'."""
        self.page_manager.go_back()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_settings_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_settings_clicked(self):
        """Переход на страницу настроек."""
        self.page_manager.switch_to('settings')

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_action_selected",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(int)
    def _on_action_selected(self, index):
        """Обработка выбора действия в комбобоксе."""
        if index == 0:
            self._start_download()
        elif index == 1:
            self._save_changes()
        elif index == 2:
            self._start_upload()
        # Сбрасываем индекс на -1, чтобы можно было повторно выбрать то же действие
        self.action_combo.setCurrentIndex(-1)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._start_download",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _start_download(self):
        """Запуск скачивания БД с сервера."""
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        remote = config.get('database_remote_path')
        local = config.get('database_local_path')
        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return
        self.download_thread = DownloadThread(token, remote, local)
        self.download_thread.progress.connect(self._update_progress)
        self.download_thread.finished.connect(self._on_download_finished)
        self.download_thread.error.connect(self._on_download_error)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.download_thread.start()
        self.logger.info("Запущен поток скачивания")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._update_progress",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(int, int)
    def _update_progress(self, current, total):
        """Обновление прогресс-бара."""
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_download_finished",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(int)
    def _on_download_finished(self, code):
        """Завершение скачивания."""
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно скачана.")
        else:
            QMessageBox.critical(self, "Ошибка", f"Скачивание завершилось с кодом {code}")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_download_error",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(str)
    def _on_download_error(self, message):
        """Ошибка скачивания."""
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._save_changes",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _save_changes(self):
        """Сохранение изменений в локальной БД."""
        self.logger.info("Сохранение изменений")
        QMessageBox.information(self, "Информация", "Функция сохранения изменений пока не реализована.")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._start_upload",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _start_upload(self):
        """Загрузка БД на сервер."""
        config = AppConfigManager.get_instance()
        token = config.get('YANDEX_TOKEN')
        remote = config.get('database_remote_path')
        local = config.get('database_local_path')
        if not token:
            QMessageBox.warning(self, "Ошибка", "Не задан токен Яндекс.Диска.")
            return
        self.upload_thread = UploadThread(token, local, remote)
        self.upload_thread.progress.connect(self._update_progress)
        self.upload_thread.finished.connect(self._on_upload_finished)
        self.upload_thread.error.connect(self._on_upload_error)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.upload_thread.start()
        self.logger.info("Запущен поток загрузки")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_upload_finished",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(int)
    def _on_upload_finished(self, code):
        """Завершение загрузки."""
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно загружена.")
        else:
            QMessageBox.critical(self, "Ошибка", f"Загрузка завершилась с кодом {code}")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_upload_error",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(str)
    def _on_upload_error(self, message):
        """Ошибка загрузки."""
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_navigation_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(list, str)
    def _on_navigation_changed(self, history, current_page_id):
        """
        Слот, вызываемый при изменении навигации.
        Обновляет хлебные крошки и состояние кнопки назад.
        """
        # Формируем строку хлебных крошек (можно взять заголовки страниц)
        # Для простоты используем идентификаторы
        crumbs = " > ".join(history) if history else "Главная"
        self.breadcrumbs_label.setText(crumbs)

        # Кнопка назад доступна, если есть история
        self.back_btn.setEnabled(len(history) > 0)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow._on_page_entered",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(str, object)
    def _on_page_entered(self, page_id, extra_data):
        """Вызывается при входе на страницу. Передаёт extra_data в метод on_enter страницы."""
        page = self.page_manager._pages.get(page_id)
        if page and hasattr(page, 'on_enter'):
            page.on_enter(extra_data)

    # Методы для управления прогрессом (могут вызываться из других мест)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow.show_progress",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def show_progress(self, visible=True):
        """Показать/скрыть прогресс-бар."""
        self.progress_bar.setVisible(visible)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow.set_progress_range",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_progress_range(self, minimum, maximum):
        """Установить диапазон прогресса."""
        self.progress_bar.setRange(minimum, maximum)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="MainWindow.set_progress_value",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_progress_value(self, value):
        """Установить текущее значение прогресса."""
        self.progress_bar.setValue(value)