# interfaces/gui/gui_window/main_window.py

"""
Главное окно приложения.

Собирает все миксины и предоставляет единую точку входа в GUI.
Содержит инициализацию UI, создание страниц, подключение сигналов,
а также методы загрузки данных для списков (load_patients, load_appointments и т.д.).
"""

import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox,
    QStackedWidget, QFrame
)
from PySide6.QtCore import Qt

from app.utils.logger.logger import AppLogger
from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service
)
from interfaces.gui.gui_window.widgets.log_viewer import LogViewer, LogViewerHandler

# Импорт миксинов
from interfaces.gui.gui_window.mixins.pages_creation_mixin import PagesCreationMixin
from interfaces.gui.gui_window.mixins.connections_mixin import ConnectionsMixin
from interfaces.gui.gui_window.mixins.delete_handlers_mixin import DeleteHandlersMixin
from interfaces.gui.gui_window.mixins.navigation_mixin import NavigationMixin
from interfaces.gui.gui_window.mixins.sync_mixin import SyncMixin


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
        enable_file_logging='system',
        use_name_in_filename='system'
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
            enable_file_logging='user',
            use_name_in_filename='user'
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

        # Подключение основных сигналов (кнопки, комбобокс, навигация)
        self._connect_signals()

        # Определяем, существует ли файл конфигурации
        from app.config.config_manager.manager import AppConfigManager
        config_manager = AppConfigManager.get_instance()
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
        enable_file_logging='system',
        use_name_in_filename='system'
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
        enable_file_logging='system',
        use_name_in_filename='system'
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
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_notes(self, extra_data):
        """Возвращает список всех заметок."""
        return get_note_service().get_all()

    @AppLogger.get_instance(
        name='MainWindow',
        enable_file_logging='system',
        use_name_in_filename='system'
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
        enable_file_logging='system',
        use_name_in_filename='system'
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
        enable_file_logging='system',
        use_name_in_filename='system'
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
        self.action_combo.addItem("Скачать БД")
        self.action_combo.addItem("Сохранить изменения")
        self.action_combo.addItem("Отправить БД на сервер")
        self.action_combo.setEditable(False)
        self.action_combo.setMaximumWidth(200)
        self.header_layout.addWidget(self.action_combo)

        # Кнопка настроек
        self.settings_btn = QPushButton("Настройки")
        self.settings_btn.setMaximumWidth(100)
        self.header_layout.addWidget(self.settings_btn)

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
        enable_file_logging='system',
        use_name_in_filename='system'
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
        enable_file_logging='system',
        use_name_in_filename='system'
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