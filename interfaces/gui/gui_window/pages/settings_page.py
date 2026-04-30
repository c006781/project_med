# interfaces/gui/gui_window/pages/settings_page.py

from app.utils.logger.logger import AppLogger
from interfaces.gui.gui_window.pages.base_page import BasePage
from app.config.config_manager.manager import AppConfigManager

from PySide6.QtWidgets import (
    # QWidget, 
    QComboBox, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Slot, Qt

class SettingsPage(BasePage):
    """
    Страница настроек.
    """

    # @AppLogger.get_instance(
    #     name = 'SettingsPage',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    @staticmethod
    def _to_bool(value) -> bool:
        """Преобразует значение в bool, поддерживая строки 'true'/'false', '1'/'0', 'yes'/'no'."""
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        
        return bool(value)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
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
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        self.page_title = page_title
        
        self.config_manager = AppConfigManager.get_instance()
        self.first_start = False          # флаг первого запуска

        self._setup_ui()
        self._load_settings()

    # ----------------------------------------------------------------------
    # Построение интерфейса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """Создаёт все виджеты страницы настроек."""
        main_layout = QVBoxLayout(self)

        # ----- Группа основных настроек (БД, фото, токен) -----
        basic_group = QGroupBox("Основные настройки")
        form_layout = QFormLayout(basic_group)

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

        # Удалённый путь БД на диске
        self.remote_path_edit = QLineEdit()
        form_layout.addRow("Удалённый путь БД:", self.remote_path_edit)

        # Папка для бекапов
        self.backup_path_edit = QLineEdit()
        self.backup_path_btn = QPushButton("Обзор...")
        self.backup_path_btn.setMaximumWidth(80)
        backup_layout = QHBoxLayout()
        backup_layout.addWidget(self.backup_path_edit)
        backup_layout.addWidget(self.backup_path_btn)
        form_layout.addRow("Папка для локальных бекапов БД:", backup_layout)

        # Количество бекапов
        self.backup_count_spin = QSpinBox()
        self.backup_count_spin.setRange(1, 100)
        form_layout.addRow("Количество бекапов:", self.backup_count_spin)

        main_layout.addWidget(basic_group)

        # ----- Группа настроек логирования -----
        log_group = QGroupBox("Настройки логирования")
        log_layout = QFormLayout(log_group)

        # Папка для хранения логов
        self.log_dir_edit = QLineEdit()
        self.log_dir_btn = QPushButton("Обзор...")
        log_dir_layout = QHBoxLayout()
        log_dir_layout.addWidget(self.log_dir_edit)
        log_dir_layout.addWidget(self.log_dir_btn)
        log_layout.addRow("Папка для логов:", log_dir_layout)

        # Добавлять временную метку в имя файла
        self.log_timestamp_check = QCheckBox("Добавлять дату/время в имя файла лога")
        log_layout.addRow(self.log_timestamp_check)

        # ----- Системный логгер -----
        system_frame = QFrame()
        system_frame.setFrameShape(QFrame.Shape.Box)
        system_frame.setMaximumHeight(180)
        system_vbox = QVBoxLayout(system_frame)
        system_vbox.addWidget(QLabel("<b>Системный логгер</b>"))

        self.system_enabled_check = QCheckBox("Включить системный логгер")
        self.system_console_check = QCheckBox("Вывод в консоль")
        self.system_file_check = QCheckBox("Запись в файл")
        self.system_level_combo = QComboBox()
        self.system_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

        system_vbox.addWidget(self.system_enabled_check)
        system_vbox.addWidget(self.system_console_check)
        system_vbox.addWidget(self.system_file_check)
        system_vbox.addWidget(QLabel("Уровень:"))
        system_vbox.addWidget(self.system_level_combo)
        log_layout.addRow(system_frame)

        # ----- Пользовательский логгер -----
        user_frame = QFrame()
        user_frame.setFrameShape(QFrame.Shape.Box)
        user_frame.setMaximumHeight(180)
        user_vbox = QVBoxLayout(user_frame)
        user_vbox.addWidget(QLabel("<b>Пользовательский логгер</b>"))

        self.user_enabled_check = QCheckBox("Включить пользовательский логгер")
        self.user_console_check = QCheckBox("Вывод в консоль")
        self.user_file_check = QCheckBox("Запись в файл")
        self.user_level_combo = QComboBox()
        self.user_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

        user_vbox.addWidget(self.user_enabled_check)
        user_vbox.addWidget(self.user_console_check)
        user_vbox.addWidget(self.user_file_check)
        user_vbox.addWidget(QLabel("Уровень:"))
        user_vbox.addWidget(self.user_level_combo)
        log_layout.addRow(user_frame)

        # Параметры ротации файлов
        self.log_max_bytes_spin = QSpinBox()
        self.log_max_bytes_spin.setRange(1024, 100 * 1024 * 1024)   # 1 KB – 100 MB
        self.log_max_bytes_spin.setSuffix(" байт")
        self.log_max_bytes_spin.setToolTip("Максимальный размер одного файла лога")

        self.log_backup_count_spin = QSpinBox()
        self.log_backup_count_spin.setRange(1, 50)
        self.log_backup_count_spin.setToolTip("Количество сохраняемых архивных копий")

        log_layout.addRow("Макс. размер файла (байт):", self.log_max_bytes_spin)
        log_layout.addRow("Количество бэкапов:", self.log_backup_count_spin)

        main_layout.addWidget(log_group)

        # ----- Кнопка сохранения -----
        self.save_btn = QPushButton("Сохранить настройки")
        self.save_btn.setMaximumWidth(200)
        main_layout.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # ----- Подключение сигналов -----
        self.db_path_btn.clicked.connect(lambda: self._browse_file(self.db_path_edit, "Выберите файл БД", "*.db"))
        self.photos_path_btn.clicked.connect(lambda: self._browse_dir(self.photos_path_edit, "Выберите папку для фото"))
        self.backup_path_btn.clicked.connect(lambda: self._browse_dir(self.backup_path_edit, "Выберите папку для бекапов"))
        self.log_dir_btn.clicked.connect(lambda: self._browse_dir(self.log_dir_edit, "Выберите папку для логов"))
        self.save_btn.clicked.connect(self._save_settings)

    # ----------------------------------------------------------------------
    # Вспомогательные методы для выбора путей
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
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
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
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

    # ----------------------------------------------------------------------
    # Загрузка настроек из конфига в поля формы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_settings(self):
        # Основные
        self.db_path_edit.setText(self.config_manager.get('database_local_path', ''))
        self.photos_path_edit.setText(self.config_manager.get('PHOTOS_STORAGE_PATH', ''))
        self.token_edit.setText(self.config_manager.get('YANDEX_TOKEN', ''))
        self.remote_path_edit.setText(self.config_manager.get('database_remote_path', ''))
        self.backup_path_edit.setText(self.config_manager.get('BACKUP_PATH', ''))
        self.backup_count_spin.setValue(int(self.config_manager.get('BACKUP_COUNT', 5)))

        # Настройки логирования
        self.log_dir_edit.setText(self.config_manager.get('LOG_DIR', ''))
        self.log_timestamp_check.setChecked(self._to_bool(self.config_manager.get('use_timestamp', False)))

        # Системный логгер
        self.system_enabled_check.setChecked(self._to_bool(self.config_manager.get('system_enabled', True)))
        self.system_console_check.setChecked(self._to_bool(self.config_manager.get('system_console_enabled', True)))
        self.system_file_check.setChecked(self._to_bool(self.config_manager.get('system_file_enabled', True)))
        self.system_level_combo.setCurrentText(self.config_manager.get('system_LEVEL', 'DEBUG'))

        # Пользовательский логгер
        self.user_enabled_check.setChecked(self._to_bool(self.config_manager.get('user_enabled', True)))
        self.user_console_check.setChecked(self._to_bool(self.config_manager.get('user_console_enabled', True)))
        self.user_file_check.setChecked(self._to_bool(self.config_manager.get('user_file_enabled', True)))
        self.user_level_combo.setCurrentText(self.config_manager.get('user_LEVEL', 'DEBUG'))

        # Ротация
        self.log_max_bytes_spin.setValue(int(self.config_manager.get('LOG_MAX_BYTES', 10 * 1024 * 1024)))
        self.log_backup_count_spin.setValue(int(self.config_manager.get('LOG_BACKUP_COUNT', 5)))

    # ----------------------------------------------------------------------
    # Сохранение настроек и перезагрузка логгеров
    # ----------------------------------------------------------------------


    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _save_settings(self):
        # Сохраняем основные настройки
        self.config_manager.set('database_local_path', self.db_path_edit.text())
        self.config_manager.set('PHOTOS_STORAGE_PATH', self.photos_path_edit.text())
        self.config_manager.set('YANDEX_TOKEN', self.token_edit.text())
        self.config_manager.set('database_remote_path', self.remote_path_edit.text())
        self.config_manager.set('BACKUP_PATH', self.backup_path_edit.text())
        self.config_manager.set('BACKUP_COUNT', self.backup_count_spin.value())

        # Сохраняем настройки логирования
        self.config_manager.set('LOG_DIR', self.log_dir_edit.text())
        self.config_manager.set('use_timestamp', self.log_timestamp_check.isChecked())

        self.config_manager.set('system_enabled', self.system_enabled_check.isChecked())
        self.config_manager.set('system_console_enabled', self.system_console_check.isChecked())
        self.config_manager.set('system_file_enabled', self.system_file_check.isChecked())
        self.config_manager.set('system_LEVEL', self.system_level_combo.currentText())

        self.config_manager.set('user_enabled', self.user_enabled_check.isChecked())
        self.config_manager.set('user_console_enabled', self.user_console_check.isChecked())
        self.config_manager.set('user_file_enabled', self.user_file_check.isChecked())
        self.config_manager.set('user_LEVEL', self.user_level_combo.currentText())

        self.config_manager.set('LOG_MAX_BYTES', self.log_max_bytes_spin.value())
        self.config_manager.set('LOG_BACKUP_COUNT', self.log_backup_count_spin.value())

        try:
            self.config_manager.save()

            # ----------------------------------------------------------
            # Ключевой момент: перезагружаем все логгеры из нового конфига
            # ----------------------------------------------------------
            # from app.utils.logger.logger import AppLogger
            AppLogger.reload_all_from_app_config()

            QMessageBox.information(self, "Успех", "Настройки сохранены.")
            self.logger.info("Настройки сохранены, логгеры перезагружены")

            if self.main_window and hasattr(self.main_window, 'on_settings_changed'):
                self.main_window.on_settings_changed()

            # Если это был первый запуск (настройки открыты при старте) – переходим на список пациентов
            if self.first_start:
                self.main_window.page_manager.switch_to(
                    'patient_list',
                    add_to_history=False,
                )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")
            self.logger.exception(f"Ошибка сохранения настроек: {e}")

    # ----------------------------------------------------------------------
    # Метод, вызываемый при показе страницы
    # ----------------------------------------------------------------------


    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
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