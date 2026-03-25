# interfaces/gui/gui_window/pages/settings_page.py
# -*- coding: utf-8 -*-

from app.utils.logger.logger import AppLogger
from interfaces.gui.gui_window.pages.base_page import BasePage
from app.config.config_manager.manager import AppConfigManager

from PySide6.QtWidgets import (
    # QWidget, 
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Slot, Qt



class SettingsPage(BasePage):
    """
    Страница настроек.
    """

    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self, 
        parent=None, 
        page_title="Настройки"
    ):
        """
        Инициализирует страницу настроек.
        
        :param parent: родительский виджет
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name = 'gui.SettingsPage',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

        self.page_title = page_title
        
        self.config_manager = AppConfigManager.get_instance()
        self.first_start = False          # флаг первого запуска

        self._setup_ui()
        self._load_settings()





    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """Создаёт элементы интерфейса."""
        main_layout = QVBoxLayout(self)

        # Группа основных настроек
        group_box = QGroupBox("Основные настройки")
        form_layout = QFormLayout(group_box)

        # Путь к локальной БД
        self.db_path_edit = QLineEdit()
        self.db_path_btn = QPushButton("Обзор...")
        self.db_path_btn.setMaximumWidth(80)
        db_path_layout = QHBoxLayout()
        db_path_layout.addWidget(self.db_path_edit)
        db_path_layout.addWidget(self.db_path_btn)
        form_layout.addRow("Путь к БД:", db_path_layout)

        # Папка для хранения фото
        self.photos_path_edit = QLineEdit()
        self.photos_path_btn = QPushButton("Обзор...")
        self.photos_path_btn.setMaximumWidth(80)
        photos_layout = QHBoxLayout()
        photos_layout.addWidget(self.photos_path_edit)
        photos_layout.addWidget(self.photos_path_btn)
        form_layout.addRow("Папка для фото:", photos_layout)

        # Токен Яндекс.Диска
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("Токен Яндекс.Диска:", self.token_edit)

        # Путь к удалённому файлу БД на диске
        self.remote_path_edit = QLineEdit()
        form_layout.addRow("Удалённый путь БД:", self.remote_path_edit)

        # Папка для бекапов
        self.backup_path_edit = QLineEdit()

        self.backup_path_btn = QPushButton("Обзор...")
        self.backup_path_btn.setMaximumWidth(80)

        backup_layout = QHBoxLayout()
        backup_layout.addWidget(self.backup_path_edit)
        backup_layout.addWidget(self.backup_path_btn)
        
        # form_layout.addRow("Папка бекапов:", backup_layout)
        # Вместо "Папка бекапов" напишем "Папка для локальных бекапов БД"
        form_layout.addRow("Папка для локальных бекапов БД:", backup_layout)
        self.backup_path_edit.setToolTip("Здесь будут сохраняться резервные копии файла базы данных")

        # Количество бекапов
        self.backup_count_spin = QSpinBox()
        self.backup_count_spin.setRange(1, 100)
        form_layout.addRow("Количество бекапов:", self.backup_count_spin)

        # Включение/отключение логирования в файл (пример переключателя)
        self.log_file_check = QCheckBox("Вести лог в файл")
        form_layout.addRow("Логирование:", self.log_file_check)

        main_layout.addWidget(group_box)

        # Кнопка сохранения
        self.save_btn = QPushButton("Сохранить настройки")
        self.save_btn.setMaximumWidth(200)
        main_layout.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Подключаем кнопки
        self.db_path_btn.clicked.connect(lambda: self._browse_file(self.db_path_edit, "Выберите файл БД", "*.db"))
        self.photos_path_btn.clicked.connect(lambda: self._browse_dir(self.photos_path_edit, "Выберите папку для фото"))
        self.backup_path_btn.clicked.connect(lambda: self._browse_dir(self.backup_path_edit, "Выберите папку для бекапов"))
        self.save_btn.clicked.connect(self._save_settings)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage._browse_file",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _browse_file(self, line_edit, title, filter_str):
        """
        Открывает нажатие на кнопку "Обзреть" для поля ввода и открывает диалоговое окно выбора файла.
        
        :param line_edit: Поле ввода для ввода пути к файлу.
        :type line_edit: QLineEdit
        :param title: Заголовок диалогового окна.
        :type title: str
        :param filter_str: Строка фильтрации для файлов.
        :type filter_str: str
        """
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", filter_str)
        if file_path:
            line_edit.setText(file_path)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage._browse_dir",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _browse_dir(self, line_edit, title):
        """
        Открывает нажатие на кнопку "Обзреть" для поля ввода и открывает диалоговое окно выбора папки.
        
        :param line_edit: Поле ввода для ввода пути к папке.
        :type line_edit: QLineEdit
        :param title: Заголовок диалогового окна.
        :type title: str
        """
        dir_path = QFileDialog.getExistingDirectory(self, title)
        if dir_path:
            line_edit.setText(dir_path)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage._load_settings",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_settings(self):
        # """Загружает текущие настройки из менеджера и заполняет поля."""
        """
        Загружает текущие настройки из менеджера и заполняет поля.

        Заполняет поля:
        - database_local_path
        - PHOTOS_STORAGE_PATH
        - YANDEX_TOKEN
        - database_remote_path
        - BACKUP_PATH
        - BACKUP_COUNT
        - LOG_ENABLED
        """
        self.db_path_edit.setText(
            self.config_manager.get('database_local_path', '')
        )

        self.photos_path_edit.setText(
            self.config_manager.get('PHOTOS_STORAGE_PATH', '')
        )

        self.token_edit.setText(
            self.config_manager.get('YANDEX_TOKEN', '')
        )

        self.remote_path_edit.setText(
            self.config_manager.get('database_remote_path', '')
        )

        self.backup_path_edit.setText(
            self.config_manager.get('BACKUP_PATH', '')
        )

        self.backup_count_spin.setValue(
            int(self.config_manager.get('BACKUP_COUNT', 5))
        )

        self.log_file_check.setChecked(
            self.config_manager.get('LOG_ENABLED', True)
        )


    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage._save_settings",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _save_settings(self):
        """Сохраняет настройки из полей в менеджер и в файл."""
        self.config_manager.set('database_local_path', self.db_path_edit.text())
        self.config_manager.set('PHOTOS_STORAGE_PATH', self.photos_path_edit.text())
        self.config_manager.set('YANDEX_TOKEN', self.token_edit.text())
        self.config_manager.set('database_remote_path', self.remote_path_edit.text())
        self.config_manager.set('BACKUP_PATH', self.backup_path_edit.text())
        self.config_manager.set('BACKUP_COUNT', self.backup_count_spin.value())
        self.config_manager.set('LOG_ENABLED', self.log_file_check.isChecked())

        try:
            self.config_manager.save()
            QMessageBox.information(self, "Успех", "Настройки сохранены.")
            self.logger.info("Настройки сохранены пользователем")
            
            # Если это был первый запуск, переходим на главную страницу
            if self.first_start:
                self.main_window.page_manager.switch_to(
                    'patient_list',
                    add_to_history=False, # Не добавляем в историю, так как страница пациентов не была активна
                )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")
            self.logger.exception("Ошибка сохранения настроек")

    @AppLogger.get_instance(
        name = 'SettingsPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="SettingsPage.on_enter",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу настроек.
        extra_data может содержать 'first_start' (True/False).
        """

        # """При входе на страницу обновляем настройки и запоминаем флаг первого запуска."""

        self.config_manager.load()
        self._load_settings()
        self.first_start = extra_data.get('first_start', False) if extra_data else False
        self.logger.debug(f"Страница настроек открыта, first_start={self.first_start}")