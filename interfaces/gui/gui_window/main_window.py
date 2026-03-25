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

from app.utils.logger.logger import AppLogger

from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service
)
from app.dto import PatientDTO, AppointmentDTO, AppointmentNoteDTO, PhotoDTO
from app.config.config_manager.manager import AppConfigManager
from app.network import DownloadThread, UploadThread
from app.dto.field_configs import PATIENT_CONFIG, APPOINTMENT_CONFIG, NOTE_CONFIG, PHOTO_CONFIG

from interfaces.gui.gui_window.controllers.page_manager import PageManager
from interfaces.gui.gui_window.pages.dynamic_list_page import DynamicListPage

from interfaces.gui.gui_window.pages.dynamic_edit_page import DynamicEditPage
from interfaces.gui.gui_window.pages.settings_page import SettingsPage
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer, LogViewerHandler
from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage, DynamicDetailListPage

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox,
    QStackedWidget, QFrame, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QIcon


class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    """

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def load_patients(self, extra_data):
        """
        Возвращает список всех пациентов из БД.

        :param extra_data: дополнительные данные, которые могут потребоваться
            для загрузки пациентов (например, фильтры)
        :return: список пациентов в формате PatientDTO
        :rtype: List[PatientDTO]
        """
        return get_patient_service().get_all_patients()

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def load_appointments(self, extra_data):
        """
        Возвращает список всех приёмов из БД.

        :param extra_data: словарь с дополнительными данными, которые могут потребоваться
            для загрузки приёмов (например, фильтры)
        :return: список приёмов в формате AppointmentDTO
        :rtype: List[AppointmentDTO]
        """
        patient_id = extra_data.get('patient_id') if extra_data else None
        service = get_appointment_service()
        if patient_id:
            return service.get_appointments_by_patient(patient_id)
        else:
            return service.get_all()
        
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def load_notes(self, extra_data):
        """
        Возвращает список всех заметок из БД. (без фильтрации)

        :param extra_data: дополнительные данные, которые могут потребоваться
            для загрузки заметок (например, фильтры)
        :return: список заметок в формате AppointmentNoteDTO
        :rtype: List[AppointmentNoteDTO]
        """
        return get_note_service().get_all()  

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def load_photos(self,extra_data):
        """
        Возвращает список всех фотографий из БД. (без фильтрации)

        :param extra_data: дополнительные данные, которые могут потребоваться
            для загрузки фотографий (например, фильтры)
        :return: список фотографий в формате PhotoDTO
        :rtype: List[PhotoDTO]
        """
        return get_photo_service().get_all()




    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        """
        Инициализирует главное окно приложения.

        :param parent: родительский виджет
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.setWindowTitle("Медицинское приложение")
        self.resize(1200, 800)

        # Логгер для этого класса
        self.logger = AppLogger.get_instance(
            name = 'gui.MainWindow',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

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
            self.page_manager.switch_to(
                'settings', 
                add_to_history=False, # Не добавляем в историю, так как страница пациентов не была активна
                extra_data={'first_start': True}
            )
        else:
            self.page_manager.switch_to('patient_list')

        self.logger.info("Главное окно создано")

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._setup_log_viewer",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_log_viewer(self):
        """
        Создает логгер для отображения логов приложения.
        Добавляет глобальный обработчик логов, который будет отображать
        логи в логгере.
        """
        handler = LogViewerHandler(self.log_viewer)
        AppLogger.add_global_handler(handler)

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_header_frame",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_header_frame(self):
        # --- Шапка (верхняя панель) ---
        """
        Создает верхнюю панель (шапку) для главного окна.
        
        :return: Верхняя панель (шапка)
        :rtype: QFrame
        """
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_frame.setMaximumHeight(60)

        return header_frame  
      
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_action_combo",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_action_combo(self):  
        # Левая часть шапки: выпадающий список с действиями
        """
        Создает выпадающий список с действиями (Скачать БД, Сохранить изменения, Отправить БД на сервер)
        и возвращает его.
        """
        action_combo = QComboBox()
        action_combo.addItem("Скачать БД")
        action_combo.addItem("Сохранить изменения")
        action_combo.addItem("Отправить БД на сервер")
        action_combo.setEditable(False)
        action_combo.setMaximumWidth(200)

        return action_combo 

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_settings_btn",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_settings_btn(self):  
        # Кнопка настроек
        """
        Создает кнопку для настроек приложения.

        Возвращает QPushButton с текстом "Настройки" и максимальной шириной 100 пикселей.
        """
        settings_btn = QPushButton("Настройки")
        settings_btn.setMaximumWidth(100)
        return settings_btn
    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_breadcrumbs_label",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_breadcrumbs_label(self):  
        # Хлебные крошки (второй уровень шапки)
        """
        Создает хлебные крошки (второй уровень шапки).

        Возвращает QLabel с текстом "Главная" и выравниваем текст по центру.
        """
        breadcrumbs_label = QLabel("Главная")
        breadcrumbs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return breadcrumbs_label
    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_back_btn",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_back_btn(self):  
        # Кнопка "Назад"
        """
        Создаёт кнопку "Назад" для навигации.
        
        Возвращает QPushButton с текстом "← Назад", максимальной шириной 80 пикселей и изначально недоступной.
        """
        back_btn = QPushButton("← Назад")
        back_btn.setMaximumWidth(80)
        back_btn.setEnabled(False)  # изначально недоступна
        return back_btn
    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_progress_bar",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_progress_bar(self):  
         # Прогресс-бар (справа)
        """
        Создаёт прогресс-бар для отображения прогресса загрузки/загрузки.

        :return: созданный прогресс-бар
        :rtype: QProgressBar
        """
        progress_bar = QProgressBar()
        progress_bar.setMaximumWidth(200)
        progress_bar.setVisible(False)  # скрыт по умолчанию

        return progress_bar

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_main_layout",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_main_layout(self, central_widget):  
        # Основной вертикальный layout
        """
        Создаёт основной вертикальный layout для главного окна.

        :param central_widget: централь widget, к которому будет добавлен layout
        :type central_widget: QWidget
        :return: созданный layout
        :rtype: QVBoxLayout
        """
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        return  main_layout
    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._set_show_log_btn",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_show_log_btn(self, setVisible):  
         # Кнопка для показа/скрытия логов (добавляем в шапку)
        """
        Создаёт кнопку для показа/скрытия логов.

        Функция setVisible будет вызвана при изменении состояния кнопки (например, если кнопка была включена,
        то функция setVisible будет вызвана с параметром True, а если кнопка была выключена, то функция setVisible
        будет вызвана с параметром False.

        :param setVisible: функция, которая будет вызвана при изменении состояния кнопки
        :type setVisible: Callable[[bool], None]
        :return: созданная кнопка
        :rtype: QPushButton
        """
        show_log_btn = QPushButton("Показать логи")
        show_log_btn.setCheckable(True)  # делаем кнопку переключаемой
        show_log_btn.toggled.connect(setVisible)  # при изменении состояния кнопки вызываем функцию setVisible
        return show_log_btn
    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._setup_header",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_header(self, main_layout):
        """
        Создает заголовок для основного окна.

        Заголовок содержит комбо-бокс для выбора действия, кнопку настроек,
        метку хлебных крошеков, кнопку "Назад" и прогресс-бар.

        :param main_layout: основной вертикальный layout
        :type main_layout: QVBoxLayout
        """
        header_frame = self._set_header_frame()
        self.header_layout = QHBoxLayout(header_frame)
        self.header_layout.setContentsMargins(10, 5, 10, 5)

        # Комбо-бокс для выбора действия
        self.action_combo = self._set_action_combo()
        self.header_layout.addWidget(self.action_combo)

        # Кнопка настроек
        self.settings_btn = self._set_settings_btn()
        self.header_layout.addWidget(self.settings_btn)

        # Отступ до начала хлебных крошеков
        self.header_layout.addStretch()

        # Метка хлебных крошеков
        self.breadcrumbs_label = self._set_breadcrumbs_label()
        self.header_layout.addWidget(self.breadcrumbs_label)

        # Отступ до начала кнопки "Назад"
        self.header_layout.addStretch()

        # Кнопка "Назад"
        self.back_btn = self._set_back_btn()
        self.header_layout.addWidget(self.back_btn)

        # Прогресс-бар
        self.progress_bar = self._set_progress_bar()
        self.header_layout.addWidget(self.progress_bar)

        # Кнопка для показа/скрытия логов будет добавлена позже, после создания log_viewer
        # self.show_log_btn = self._set_show_log_btn(self.log_viewer.setVisible)
        # self.header_layout.addWidget(self.show_log_btn)

        main_layout.addWidget(header_frame)

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._setup_log_viewer_widget",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_log_viewer_widget(self, main_layout):
        """
        Создаёт виджет для отображения логов.
        Это виджет будет отображать логи, которые генерируются при выполнении программы.
        Виджет добавляется в основную вертикальный layout, чтобы логи отображались в правой части основного окна.
        :param main_layout: основной вертикальный layout
        :type main_layout: QVBoxLayout
        """
        self.log_viewer = LogViewer()
        # Создаём виджет для отображения логов
        # Это виджет будет отображать логи, которые генерируются при выполнении программы
        main_layout.addWidget(self.log_viewer)
        # Виджет добавляется в основную вертикальный layout, чтобы логи отображались в правой части основного окна

        # Теперь, когда log_viewer создан, можно добавить кнопку в шапку
        self.show_log_btn = self._set_show_log_btn(self.log_viewer.setVisible)
        self.header_layout.addWidget(self.show_log_btn)


    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """
        Инициализирует основной интерфейс окна.

        Создает центральный виджет, добавляет заголовок, центральную область (стек страниц) и лог-вьюер.
        Добавляет созданные виджеты в основной вертикальный layout.
        """

        # Создаем центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Создаем основной вертикальный layout
        main_layout = self._set_main_layout(central_widget)

        # Создаем заголовок (Шапка)
        self._setup_header(main_layout)

        # Создаем центральную область (стек страниц)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # Создаем лог-вьюер (виджет добавляется в layout, после этого добавляется кнопка в шапку)
        self._setup_log_viewer_widget(main_layout)

        # Обработчик логов (подключается после создания виджета)
        self._setup_log_viewer()

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_patient(self):
        """
        Создаёт страницу списка пациентов и страницу редактирования пациента.
        Создаём список столбцов для пациентов:
        - ID - целое число,不可яемое
        - Фамилия - строка,不可яемое
        - Имя - строка,不可яемое
        - Дата рождения - дата, изменяемое
        - Телефон - строка, изменяемое
        - Email - строка, изменяемое
        Создаём страницу со списком пациентов, страницу редактирования пациента и кнопкой добавления нового пациента.
        """
        # patient_columns = [
        #     {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
        #     {'name': 'last_name', 'title': 'Фамилия', 'type': str, 'editable': True},
        #     {'name': 'first_name', 'title': 'Имя', 'type': str, 'editable': True},
        #     {'name': 'birth_date', 'title': 'Дата рождения', 'type': datetime.date, 'editable': True},
        #     {'name': 'phone', 'title': 'Телефон', 'type': str, 'editable': True},
        #     {'name': 'email', 'title': 'Email', 'type': str, 'editable': True},
        # ]
        # Создаём страницу со списком пациентов
        # self.patient_list_page = DynamicListPage(
        #     service=get_patient_service(),
        #     columns=patient_columns,
        #     page_title="Пациенты",
        #     add_action_text="Добавить пациента"
        # )
        self.patient_list_page = DynamicListPage(
            service=get_patient_service(),
            loader_func=self.load_patients,
            # columns=patient_columns,
            dto_class=PatientDTO,
            field_configs=PATIENT_CONFIG,
            page_title="Пациенты",
            add_action_text="Добавить пациента",
            action_button_text="Приёмы"          # дополнительная кнопка
        )
        # Создаём страницу редактирования пациента
        self.patient_edit_page = DynamicEditPage(
            service=get_patient_service(),
            dto_class=PatientDTO,
            page_title="Редактирование пациента",
            exclude_fields=['id'],
            # field_rename={
            #     'first_name': 'Имя',
            #     'last_name': 'Фамилия',
            #     'birth_date': 'Дата рождения',
            #     'phone': 'Телефон',
            #     'email': 'Email'
            # }
            field_configs=PATIENT_CONFIG
        )
        # Указываем ID списка пациентов, чтобы страница редактирования пациента знала, какой список отображать
        self.patient_edit_page.list_page_id = 'patient_list'



    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_appointment(self):
        """
        Инициализирует страницы для работы с приёмами.
        Создаёт страницы со списком приёмов, страницу редактирования приёма и кнопкой добавления нового приёма.

        :return: None
        :rtype: None
        """
        
        # Создаём список столбцов для приёмов
        # ID - целое число,不可яемое
        # Пациент - строка,不可яемое
        # Дата - дата, изменяемое
        # Время - время, изменяемое
        # Заметка - строка, изменяемое

        # appointment_columns = [
        #     {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
        #     {'name': 'patient_name', 'title': 'Пациент', 'type': str, 'editable': False},  # виртуальное поле
        #     {'name': 'date', 'title': 'Дата', 'type': datetime.date, 'editable': True},
        #     {'name': 'time', 'title': 'Время', 'type': datetime.time, 'editable': True},
        #     {'name': 'note_text', 'title': 'Заметка', 'type': str, 'editable': True},
        # ]
        # appointment_columns = [
        #     {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
        #     {'name': 'patient_name', 'title': 'Пациент', 'type': str, 'editable': False},
        #     {'name': 'date', 'title': 'Дата', 'type': datetime.date, 'editable': True},
        #     {'name': 'time', 'title': 'Время', 'type': datetime.time, 'editable': True},
        #     # {'name': 'status', 'title': 'Статус', 'type': str, 'editable': True,
        #     # 'choices': ['Запланирован', 'Проведён', 'Отменён']},  # выпадающий список
        #     {'name': 'note_text', 'title': 'Заметка', 'type': str, 'editable': True},
        # ]
        
        # Создаём страницу со списком приёмов
        # страница будет загружаться функцией load_appointments
        # со страницей редактирования приёма
        # self.appointment_list_page = DynamicListPage(
        #     # service=get_appointment_service(),
        #     loader_func=self.load_appointments,
        #     columns=appointment_columns,
        #     page_title="Приёмы",
        #     add_action_text="Новый приём"
        # )
        self.appointment_list_page = AppointmentListPage(
            service=get_appointment_service(),
            loader_func=self.load_appointments,
            # columns=appointment_columns,
            dto_class=AppointmentDTO,
            field_configs=APPOINTMENT_CONFIG,
            page_title="Приёмы",
            add_action_text="Новый приём"
        )
        
        # Создаём страницу редактирования приёма
        # страница будет загружаться функцией get_appointment_service
        # со страницей списка приёмов
        self.appointment_edit_page = DynamicEditPage(
            service=get_appointment_service(),
            dto_class=AppointmentDTO,
            page_title="Редактирование приёма",
            exclude_fields=[
                'id', 
                # 'patient_id', # не убираем, так как нужен внос с обьект
                # 'patient_name', 
                # 'note_id',  # не убираем, так как нужен внос с обьект
            ],
            # field_choices={},  # можно добавить, например, список пациентов
            # field_rename={
            #     'patient_id': 'ID пациента',
            #     'date': 'Дата',
            #     'time': 'Время',
            #     'note_text': 'Заметка'
            # }
            field_configs=APPOINTMENT_CONFIG
        )
        
        # Указываем ID списка приёмов, чтобы страница редактирования приёма
        # знала, какой список отображать
        self.appointment_edit_page.list_page_id = 'appointment_list'


    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_note(self):
        # --- Заметки ---
        """
        Создаёт страницу списка заметок и страницу редактирования заметки.

        :return: tuple (DynamicListPage, DynamicEditPage)
        """
        # Создаём список столбцов для заметок
        # ID - целое число,不可яемое
        # Текст - строка, изменяемое
        # note_columns = [
        #     {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
        #     {'name': 'text', 'title': 'Текст', 'type': str, 'editable': True},
        # ]

        # Создаём страницу со списком заметок
        # страница будет загружаться функцией load_notes
        # со страницей редактирования заметки
        self.note_list_page = DynamicListPage(
            service=get_note_service(),
            loader_func=self.load_notes,
            # loader_func=lambda extra: get_note_service().get_all(),
            # columns=note_columns,
            dto_class=AppointmentNoteDTO,
            field_configs=NOTE_CONFIG,
            page_title="Заметки",
            add_action_text="Создать заметку"
        )

        # Создаём страницу редактирования заметки
        # страница будет загружаться функцией get_note_service
        # со страницей списка заметок
        self.note_edit_page = DynamicEditPage(
            service=get_note_service(),
            dto_class=AppointmentNoteDTO,
            page_title="Редактирование заметки",
            exclude_fields=['id'],
            # field_rename={'text': 'Текст заметки'},
            field_configs=NOTE_CONFIG

        )
        # Указываем ID списка заметок, чтобы страница редактирования заметки
        # знала, какой список отображать
        self.note_edit_page.list_page_id = 'note_list'



    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_photo(self):
        """
        Создаёт страницу списка фотографий и страницу редактирования фотографии.
        :return: tuple (DynamicListPage, DynamicEditPage)
        """
        # Создаём список столбцов для фотографий
        # ID - целое число,不可яемое
        # ID приёма - целое число,不可яемое
        # путь к файлу - строка,不可яемое
        # описание - строка, изменяемое
        # photo_columns = [
        #     {'name': 'id', 'title': 'ID', 'type': int, 'editable': False},
        #     {'name': 'appointment_id', 'title': 'ID приёма', 'type': int, 'editable': False},
        #     {'name': 'file_path', 'title': 'Файл', 'type': str, 'editable': False},
        #     {'name': 'description', 'title': 'Описание', 'type': str, 'editable': True},
        # ]

        # Создаём страницу со списком фотографий
        # страница будет загружаться функцией load_photos
        # со страницей редактирования фотографии
        self.photo_list_page = DynamicListPage(
            service=get_photo_service(),
            loader_func=self.load_photos,
            # columns=photo_columns,
            dto_class=PhotoDTO,
            field_configs=PHOTO_CONFIG,
            page_title="Фотографии",
            add_action_text="Добавить фото"
        )

        # Создаём страницу редактирования фотографии
        # страница будет загружаться функцией get_photo_service
        # со страницей списка фотографий
        self.photo_edit_page = DynamicEditPage(
            service=get_photo_service(),
            dto_class=PhotoDTO,
            page_title="Редактирование фото",
            exclude_fields=['id'],
            # field_rename={
            #     'appointment_id': 'ID приёма',
            #     'file_path': 'Путь к файлу',
            #     'description': 'Описание'
            # }
            field_configs=PHOTO_CONFIG
        )
        # Указываем ID списка фотографий, чтобы страница редактирования фотографии
        # знала, какой список отображать
        self.photo_edit_page.list_page_id = 'photo_list'

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._init_page_manager",
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
        self._set_patient()

        # --- Приёмы ---
        self._set_appointment()
        
        # --- Заметки ---
        self._set_note()

        # --- Фото ---
        self._set_photo()

        # --- Страница настроек (оставляем как есть) ---
        self.settings_page = SettingsPage(
            page_title="Настройки",
        )

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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_patient_appointments_requested",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_patient_appointments_requested(self, patient_dto):
        """Переход к списку приёмов выбранного пациента."""
        self.page_manager.switch_to(
            'appointment_list',
            extra_data={
                'patient_id': patient_dto.id
            }            
        )
        

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._connect_signals",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_signals(self):
        """
        Подключает основные сигналы (кнопки, комбобокс, навигация).

        Сигналы, которые подлючаются:
        - кнопка "Назад" (back_btn)
        - кнопка "Настройки" (settings_btn)
        - выбор действия в комбобоксе (action_combo)
        - сигналы от менеджера страниц (navigation_changed, page_entered)
        """
        # Кнопка назад
        # Подключает сигнал "назад" при нажатии кнопки
        self.back_btn.clicked.connect(self._on_back_clicked)

        # Кнопка настроек
        # Подключает сигнал "настройки" при нажатии кнопки
        self.settings_btn.clicked.connect(self._on_settings_clicked)

        # Выбор действия в комбобоксе
        # Подключает сигнал "выбор действия" при изменении значения в комбобоксе
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)

        # Сигналы от менеджера страниц
        # Подключает сигналы "изменение навигации" и "вход на страницу" от менеджера страниц
        self.page_manager.navigation_changed.connect(self._on_navigation_changed)
        self.page_manager.page_entered.connect(self._on_page_entered)




    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._connect_patient",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_patient(self):
        # Пациенты
        """
        Подключает сигналы от страницы пациентов.

        Сигналы, которые подлючаются:
        - добавление нового пациента (add_requested)
        - редактирование существующего пациента (edit_requested)
        - удаление существующего пациента (delete_requested)
        - переход к списку приёмов выбранного пациента (action_requested)
        """
        self.patient_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'patient_edit', 
                extra_data=None
            )
        )
        self.patient_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'patient_edit', 
                extra_data={
                    'id': dto.id
                }
            )
        )
        self.patient_list_page.delete_requested.connect(
            self._on_patient_delete
        )
        
        self.patient_list_page.action_requested.connect(
            self._on_patient_appointments_requested
        )

    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._connect_appointment",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_appointment(self):
        # Приёмы
        """
        Подключает сигналы от страницы приёмов.

        Сигналы, которые подлючаются:
        - добавление нового приёма (add_requested)
        - редактирование существующего приёма (edit_requested)
        - удаление существующего приёма (delete_requested)
        """
        self.appointment_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'appointment_edit', 
                extra_data={
                    # 'patient_id': self.appointment_list_page.current_patient_id
                    'patient_id': self.appointment_list_page.current_extra.get('patient_id')
                    if self.appointment_list_page.current_extra else None
                }
            )
        )
        self.appointment_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'appointment_edit', 
                extra_data={
                    'id': dto.id
                }
            )
        )
        self.appointment_list_page.delete_requested.connect(
            self._on_appointment_delete
        )

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._connect_note",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_note(self):
        # Заметки
        """
        Подключает сигналы от страницы заметок.

        Сигналы, которые подлючаются:
        - добавление новой заметки (add_requested)
        - редактирование существующей заметки (edit_requested)
        - удаление существующей заметки (delete_requested)
        """
        self.note_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'note_edit', 
                extra_data=None,
            )
        )
        self.note_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'note_edit', 
                extra_data={
                    'id': dto.id,
                }
            )
        )
        self.note_list_page.delete_requested.connect(
            self._on_note_delete
        )

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._connect_photo",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_photo(self):
        # Фото
        """
        Подключает сигналы от страницы фотографий.

        Сигналы, которые подлючаются:
        - добавление новой фотографии (add_requested)
        - редактирование существующей фотографии (edit_requested)
        - удаление существующей фотографии (delete_requested)
        """
        self.photo_list_page.add_requested.connect(
            lambda: self.page_manager.switch_to(
                'photo_edit', 
                extra_data=None
            )
        )
        self.photo_list_page.edit_requested.connect(
            lambda dto: self.page_manager.switch_to(
                'photo_edit', extra_data={
                    'id': dto.id
                }
            )
        )
        self.photo_list_page.delete_requested.connect(
            self._on_photo_delete
        )

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._connect_page_signals",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _connect_page_signals(self):
        """Связывает сигналы страниц с методами навигации и удаления."""
        # # Пациенты
        self._connect_patient()

        # Приёмы
        self._connect_appointment()

        # Заметки
        self._connect_note()

        # Фото
        self._connect_photo()

    # ----------------------------------------------------------------------
    # Обработчики удаления (вызываются из страниц)
    # ----------------------------------------------------------------------
    
    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_patient_delete",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_appointment_delete",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_note_delete",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_photo_delete",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_back_clicked",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_settings_clicked",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_action_selected",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._start_download",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._update_progress",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_download_finished",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_download_error",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._save_changes",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._start_upload",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_upload_finished",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_upload_error",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(str)
    def _on_upload_error(self, message):
        # """Ошибка загрузки."""
        """
        Обработчик ошибки при загрузке.
        Вызывается при ошибке загрузки.
        :param message: сообщение об ошибке
        :type message: str
        """
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_navigation_changed",
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
        :param history: список кортежей (id, title) страниц, которые были посещены
        :param current_page_id: идентификатор текущей страницы
        """


        # Формируем строку из заголовков
        titles = [title for _, title in history]
        # Добавляем заголовок текущей страницы
        if current_page_id:
            current_title = self.page_manager._get_page_title(current_page_id)  # или взять из _current_page_title
            titles.append(current_title)

        # Формируем строку хлебных крошек
        crumbs = " > ".join(titles) if titles else "Главная"
        
        # Установка текста в метке хлебных крошек
        self.breadcrumbs_label.setText(crumbs)

        # Включение или отключение кнопки назад
        self.back_btn.setEnabled(len(history) > 0)

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow._on_page_entered",
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
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.show_progress",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def show_progress(self, visible=True):
        """Показать/скрыть прогресс-бар."""
        self.progress_bar.setVisible(visible)

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.set_progress_range",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_progress_range(self, minimum, maximum):
        """Установить диапазон прогресса."""
        self.progress_bar.setRange(minimum, maximum)

    @AppLogger.get_instance(
        name = 'MainWindow',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="MainWindow.set_progress_value",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_progress_value(self, value):
        """Установить текущее значение прогресса."""
        self.progress_bar.setValue(value)