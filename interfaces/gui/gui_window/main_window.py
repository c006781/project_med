# -*- coding: utf-8 -*-
"""
Главное окно приложения.
Содержит верхнюю панель (шапку) с меню, прогресс-бар, кнопку назад,
область для хлебных крошек и центральный стек для страниц.
Управляет навигацией через PageManager.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QComboBox,
    QStackedWidget, QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QIcon

from interfaces.gui.gui_window.controllers.page_manager import PageManager
from interfaces.gui.gui_window.pages.settings_page import SettingsPage
from interfaces.gui.gui_window.pages.patient_list_page import PatientListPage
from interfaces.gui.gui_window.pages.patient_edit_page import PatientEditPage
from interfaces.gui.gui_window.pages.appointment_list_page import AppointmentListPage
from interfaces.gui.gui_window.pages.appointment_detail_page import AppointmentDetailPage

# Импортируем логгер (опционально)
from app.utils.logger.logger import AppLogger

from app.network import DownloadThread, UploadThread
from app.config.config_manager.manager import AppConfigManager


class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Медицинское приложение")
        self.resize(1200, 800)

        # Логгер для этого класса
        self.logger = AppLogger.get_instance("gui.MainWindow")

        # Инициализация UI
        self._setup_ui()

        # Инициализация менеджера страниц
        self._init_page_manager()

        # Подключение сигналов
        self._connect_signals()

        self.logger.info("Главное окно создано")

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

    def _init_page_manager(self):
        """Создаёт страницы и менеджер навигации."""
        # Создаём экземпляры страниц
        self.settings_page = SettingsPage()
        self.patient_list_page = PatientListPage()
        self.patient_edit_page = PatientEditPage()
        self.appointment_list_page = AppointmentListPage()
        self.appointment_detail_page = AppointmentDetailPage()

        # Добавляем страницы в стек с уникальными идентификаторами
        self.stacked_widget.addWidget(self.settings_page)          # index 0
        self.stacked_widget.addWidget(self.patient_list_page)     # index 1
        self.stacked_widget.addWidget(self.patient_edit_page)     # index 2
        self.stacked_widget.addWidget(self.appointment_list_page) # index 3
        self.stacked_widget.addWidget(self.appointment_detail_page) # index 4

        # Создаём менеджер страниц
        self.page_manager = PageManager(
            stacked_widget=self.stacked_widget,
            pages={
                'settings': self.settings_page,
                'patient_list': self.patient_list_page,
                'patient_edit': self.patient_edit_page,
                'appointment_list': self.appointment_list_page,
                'appointment_detail': self.appointment_detail_page,
            }
        )

        # Устанавливаем начальную страницу
        self.page_manager.switch_to('patient_list')

        # Передаём ссылку на главное окно (непонятно сюда ли...)
        for page in [self.settings_page, self.patient_list_page, self.patient_edit_page,
                     self.appointment_list_page, self.appointment_detail_page]:
            page.set_main_window(self)

    def _connect_signals(self):
        """Подключает сигналы к слотам."""
        # Кнопка назад
        self.back_btn.clicked.connect(self._on_back_clicked)

        # Кнопка настроек
        self.settings_btn.clicked.connect(self._on_settings_clicked)

        # Выбор действия в комбобоксе
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)

        # Сигналы от менеджера страниц
        self.page_manager.navigation_changed.connect(self._on_navigation_changed)

        self.page_manager.page_entered.connect(self._on_page_entered)

    @Slot()
    def _on_back_clicked(self):
        """Обработчик кнопки 'Назад'."""
        self.page_manager.go_back()

    @Slot()
    def _on_settings_clicked(self):
        """Переход на страницу настроек."""
        self.page_manager.switch_to('settings')

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

    # def _start_download(self):
    #     """Запуск скачивания БД с сервера."""
    #     self.logger.info("Запуск скачивания БД")
    #     # TODO: запустить поток DownloadThread, показать прогресс
    #     self.progress_bar.setVisible(True)
    #     self.progress_bar.setRange(0, 0)  # бесконечный прогресс
    
    def _start_download(self):
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

    @Slot(int, int)
    def _update_progress(self, current, total):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    @Slot(int)
    def _on_download_finished(self, code):
        self.progress_bar.setVisible(False)
        if code == 0:
            QMessageBox.information(self, "Успех", "База данных успешно скачана.")
        else:
            QMessageBox.critical(self, "Ошибка", f"Скачивание завершилось с кодом {code}")

    @Slot(str)
    def _on_download_error(self, message):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Ошибка", message)

    def _save_changes(self):
        """Сохранение изменений в локальной БД."""
        self.logger.info("Сохранение изменений")
        # TODO: возможно, просто коммит текущих изменений, если используется транзакция

    def _start_upload(self):
        """Загрузка БД на сервер."""
        self.logger.info("Запуск загрузки БД")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

    @Slot(list, str)
    def _on_navigation_changed(self, history, current_page_id):
        """
        Слот, вызываемый при изменении навигации.
        Обновляет хлебные крошки и состояние кнопки назад.
        """
        # Формируем строку хлебных крошек
        crumbs = " > ".join(history) if history else "Главная"
        self.breadcrumbs_label.setText(crumbs)

        # Кнопка назад доступна, если в истории больше одного элемента
        self.back_btn.setEnabled(len(history) > 1)

    # Методы для управления прогрессом (будут вызываться из потоков)
    def show_progress(self, visible=True):
        """Показать/скрыть прогресс-бар."""
        self.progress_bar.setVisible(visible)

    def set_progress_range(self, minimum, maximum):
        """Установить диапазон прогресса."""
        self.progress_bar.setRange(minimum, maximum)

    def set_progress_value(self, value):
        """Установить текущее значение прогресса."""
        self.progress_bar.setValue(value)

    @Slot(str, object)
    def _on_page_entered(self, page_id, extra_data):
        """Вызывается при входе на страницу. Передаёт extra_data в метод on_enter страницы."""
        page = self.page_manager._pages.get(page_id)
        if page and hasattr(page, 'on_enter'):
            page.on_enter(extra_data)