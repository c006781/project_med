# interfaces/gui/gui_window/pages/settings_page.py

import os

from app.config import APP_VERSION, GITHUB_REPO_SLUG
from app.dependencies import create_database
from app.utils.logger.logger import AppLogger

from app.network.ya_dop import check_and_create_path

from app.config.config_applier import ConfigApplier
from app.config.config_manager.manager import AppConfigManager

from interfaces.gui.gui_window.pages.base_page import BasePage

from PySide6.QtWidgets import (
    # QWidget, 
    QComboBox, QFrame, QLabel, QTabWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QWidget
)
from PySide6.QtCore import QThread, Signal, Slot, Qt

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
        """Создаёт все виджеты страницы настроек с вкладками."""
        main_layout = QVBoxLayout(self)

        # Создаём вкладки
        self.tab_widget = QTabWidget()
        self.settings_tab = QWidget()
        self.about_tab = QWidget()
        self.tab_widget.addTab(self.settings_tab, "Основные")
        self.tab_widget.addTab(self.about_tab, "О программе")
        main_layout.addWidget(self.tab_widget)

        # ----- Вкладка "Основные настройки" -----
        settings_layout = QVBoxLayout(self.settings_tab)

        # Группа основных настроек (БД, фото, токен)
        basic_group = QGroupBox("Основные настройки")
        form_layout = QFormLayout(basic_group)

        # Путь к локальной БД
        self.db_path_edit = QLineEdit()
        self.db_path_btn = QPushButton("Обзор...")
        self.db_path_btn.setMaximumWidth(80)
        self.create_db_btn = QPushButton("Создать тестовую БД")
        self.create_db_btn.setMaximumWidth(150)
        self.create_db_btn.setVisible(False)

        db_path_layout = QHBoxLayout()
        db_path_layout.addWidget(self.db_path_edit)
        db_path_layout.addWidget(self.db_path_btn)
        db_path_layout.addWidget(self.create_db_btn)
        form_layout.addRow("Путь к БД:", db_path_layout)

        # Папка для хранения фото
        self.photos_path_edit = QLineEdit()
        self.photos_path_btn = QPushButton("Обзор...")
        self.photos_path_btn.setMaximumWidth(80)
        photos_layout = QHBoxLayout()
        photos_layout.addWidget(self.photos_path_edit)
        photos_layout.addWidget(self.photos_path_btn)
        form_layout.addRow("Папка для фото:", photos_layout)

        # Токен Яндекс.Диска с кнопкой проверки
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token_layout = QHBoxLayout()
        token_layout.addWidget(self.token_edit)
        self.check_token_btn = QPushButton("Проверить")
        self.check_token_btn.setMaximumWidth(80)
        self.check_token_btn.clicked.connect(self._check_token)
        token_layout.addWidget(self.check_token_btn)
        form_layout.addRow("Токен Яндекс.Диска:", token_layout)

        # Удалённый путь БД с кнопкой проверки/создания
        self.remote_path_edit = QLineEdit()
        remote_layout = QHBoxLayout()
        remote_layout.addWidget(self.remote_path_edit)
        self.check_path_btn = QPushButton("Проверить/Создать")
        self.check_path_btn.setMaximumWidth(120)
        self.check_path_btn.clicked.connect(self._check_remote_path)
        remote_layout.addWidget(self.check_path_btn)
        form_layout.addRow("Удалённый путь БД:", remote_layout)

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

        settings_layout.addWidget(basic_group)

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
        self.log_max_bytes_spin.setRange(1024, 100 * 1024 * 1024)
        self.log_max_bytes_spin.setSuffix(" байт")
        self.log_max_bytes_spin.setToolTip("Максимальный размер одного файла лога")

        self.log_backup_count_spin = QSpinBox()
        self.log_backup_count_spin.setRange(1, 50)
        self.log_backup_count_spin.setToolTip("Количество сохраняемых архивных копий")

        log_layout.addRow("Макс. размер файла (байт):", self.log_max_bytes_spin)
        log_layout.addRow("Количество бэкапов:", self.log_backup_count_spin)

        settings_layout.addWidget(log_group)

        # Кнопка сохранения (помещаем под всеми настройками)
        self.save_btn = QPushButton("Сохранить настройки")
        self.save_btn.setMaximumWidth(200)
        settings_layout.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # ----- Сигналы для виджетов основной вкладки -----
        self.db_path_btn.clicked.connect(lambda: self._browse_file(self.db_path_edit, "Выберите файл БД", "*.db"))
        self.photos_path_btn.clicked.connect(lambda: self._browse_dir(self.photos_path_edit, "Выберите папку для фото"))
        self.backup_path_btn.clicked.connect(lambda: self._browse_dir(self.backup_path_edit, "Выберите папку для бекапов"))
        self.log_dir_btn.clicked.connect(lambda: self._browse_dir(self.log_dir_edit, "Выберите папку для логов"))
        self.save_btn.clicked.connect(self._save_settings)

        self.db_path_edit.textChanged.connect(self._update_create_db_button_visibility)
        self.create_db_btn.clicked.connect(self._on_create_test_db_clicked)

        # ----- Вкладка "О программе" -----
        self._setup_about_tab()

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_about_tab(self):
        layout = QVBoxLayout(self.about_tab)
        
        # Логотип (опционально)
        # logo = QLabel()
        # logo.setPixmap(QPixmap(":/icons/app_icon.png").scaled(64,64))
        # layout.addWidget(logo, alignment=Qt.AlignCenter)
        
        # Название и версия
        title = QLabel("<h2>Медицинское приложение</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        version_label = QLabel(f"Версия: <b>{APP_VERSION}</b>")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
        
        # Кнопка проверки обновлений
        self.check_update_btn = QPushButton("Проверить обновления")
        self.check_update_btn.clicked.connect(self._on_check_updates_clicked)
        layout.addWidget(self.check_update_btn, alignment=Qt.AlignCenter)
        
        # Ссылка на GitHub
        repo_url = f"https://github.com/{GITHUB_REPO_SLUG}"
        link_label = QLabel(f'<a href="{repo_url}">Страница проекта на GitHub</a>')
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(link_label)
        
        layout.addStretch()

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _on_check_updates_clicked(self):
        """Запускает ручную проверку обновлений через главное окно."""
        if self.main_window and hasattr(self.main_window, 'check_for_updates'):
            self.main_window.check_for_updates()
        else:
            QMessageBox.warning(self, "Ошибка", "Система обновлений недоступна")

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def can_leave(self) -> bool:
        """Проверяет, можно ли покинуть страницу (существует ли БД)."""
        db_path = self.db_path_edit.text().strip()
        if not db_path or not os.path.isfile(db_path):
            QMessageBox.warning(self, "Ошибка", "Сначала укажите существующий файл БД или создайте его.")
            return False
        
        return True

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _update_create_db_button_visibility(self, text: str = None):
        """Показывает кнопку 'Создать тестовую БД', если путь пуст или указывает на несуществующий файл."""
        path = self.db_path_edit.text().strip()
        if not path:
            self.create_db_btn.setVisible(True)
            return
        
        exists = os.path.exists(path)
        self.create_db_btn.setVisible(not exists)
        self.adjustSize()  # или self.updateGeometry()

    # Обработчик кнопки создания БД
    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _on_create_test_db_clicked(self):
        """Обработчик кнопки 'Создать тестовую БД'."""
        db_path = self.db_path_edit.text().strip()
        if not db_path:
            default_path = os.path.join('.', 'clinic.db')
            db_path = default_path
            self.db_path_edit.setText(default_path)
        
        reply = QMessageBox.question(
            self,
            "Создание базы данных",
            "Заполнить тестовыми данными?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        fill_test = (reply == QMessageBox.StandardButton.Yes)
        try:
            create_database(db_path, fill_test_data=fill_test)
            QMessageBox.information(self, "Успех", f"База данных создана: {db_path}")
            self._update_create_db_button_visibility()

        except Exception as e:
            self.logger.exception(f"Ошибка создания БД: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать БД: {e}")

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

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _check_token(self):
        """Проверяет токен Яндекс.Диска асинхронно."""
        token = self.token_edit.text().strip()
        
        if not token:
            QMessageBox.warning(self, "Ошибка", "Токен не задан.")
            return

        class TokenCheckThread(QThread):
            result = Signal(bool, str)
            def __init__(self, token):
                super().__init__()
                self.token = token
            def run(self):
                from app.network.ya_dop import check_token
                ok = check_token(self.token)
                msg = "Токен действителен" if ok else "Токен недействителен или нет соединения"
                self.result.emit(ok, msg)

        self.token_thread = TokenCheckThread(token)
        self.token_thread.result.connect(self._on_token_checked)
        self.token_thread.start()
        self.check_token_btn.setEnabled(False)
        self.check_token_btn.setText("Проверка...")

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _on_token_checked(self, ok: bool, message: str):
        self.check_token_btn.setEnabled(True)
        self.check_token_btn.setText("Проверить")

        if ok:
            QMessageBox.information(self, "Результат", message)
        else:
            QMessageBox.warning(self, "Результат", message)

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _check_remote_path(self):
        """Проверяет существование удалённого пути на Яндекс.Диске, предлагает создать."""
        token = self.token_edit.text().strip()
        path = self.remote_path_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "Ошибка", "Токен не задан.")
            return
        
        if not path:
            QMessageBox.warning(self, "Ошибка", "Удалённый путь не задан.")
            return

        class PathCheckThread(QThread):
            result = Signal(bool, str)

            def __init__(self, token, path):
                super().__init__()
                self.token = token
                self.path = path

            def run(self):
                # from app.network.ya_dop import check_and_create_path
                ok, msg = check_and_create_path(self.token, self.path, create_if_missing=True)
                self.result.emit(ok, msg)

        self.path_thread = PathCheckThread(token, path)
        self.path_thread.result.connect(self._on_path_checked)
        self.path_thread.start()
        self.check_path_btn.setEnabled(False)
        self.check_path_btn.setText("Проверка...")

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _on_path_checked(self, ok: bool, message: str):
        self.check_path_btn.setEnabled(True)
        self.check_path_btn.setText("Проверить/Создать")
        if ok:
            QMessageBox.information(self, "Результат", message)
        else:
            QMessageBox.warning(self, "Результат", message)

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
    def _sawe_new_config(
        self
    ):
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
        """
        Сохраняет настройки из формы в конфигурационный файл и применяет их.

        Последовательность действий:
            1. Копирует старую конфигурацию (`old_config`).
            2. Сохраняет все поля формы в `AppConfigManager`.
            3. Вызывает `self.config_manager.save()`.
            4. Получает новую конфигурацию и вычисляет список изменившихся блоков
               с помощью `ConfigApplier.get_changed_blocks()`.
            5. Для каждого изменённого блока вызывает соответствующий метод `ConfigApplier`.
            6. Уведомляет главное окно (`main_window.on_settings_changed`) с указанием
               изменённых блоков.
            7. Если это первый запуск (`self.first_start`), переключает страницу на
               список пациентов.

        Исключения:
            Любое исключение при сохранении перехватывается, выводится сообщение
            через QMessageBox.critical, и ошибка логируется.

        Returns:
            None
        """

        db_path = self.db_path_edit.text().strip()
        if not db_path:
            QMessageBox.warning(self, "Ошибка", "Путь к БД не может быть пустым.")
            return
        if not os.path.isfile(db_path):
            reply = QMessageBox.question(
                self, "База данных не найдена",
                f"Файл БД '{db_path}' не существует.\nСоздать новую БД?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                fill = QMessageBox.question(
                    self, "Тестовые данные",
                    "Заполнить тестовыми данными?"
                ) == QMessageBox.StandardButton.Yes
                try:
                    create_database(db_path, fill_test_data=fill)
                    QMessageBox.information(self, "Успех", "БД создана.")
                    # Путь уже установлен, продолжаем сохранение
                except Exception as e:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось создать БД: {e}")
                    return
            else:
                return  # не сохранять

        # Сохраняем старую конфигурацию для сравнения
        old_config = self.config_manager.get_all().copy()

        self._sawe_new_config()

        try:
            self.config_manager.save()

            # Получаем новую конфигурацию и определяем изменившиеся блоки
            new_config = self.config_manager.get_all()
            # from app.config.config_applier import ConfigApplier
            changed_blocks = ConfigApplier.get_changed_blocks(old_config, new_config)

            # Применяем только изменённые блоки
            applier = ConfigApplier()
            if 'database' in changed_blocks:
                applier.apply_database(new_config)

            if 'photos' in changed_blocks:
                applier.apply_photos_storage(new_config)

            if 'sync' in changed_blocks:
                applier.apply_sync(new_config)

            if any(block.startswith('logging') for block in changed_blocks):
                applier.apply_logging(new_config)

            if 'backup' in changed_blocks:
                applier.apply_backup(new_config)


            # # ----------------------------------------------------------
            # # Ключевой момент: перезагружаем все логгеры из нового конфига
            # # ----------------------------------------------------------
            # # from app.utils.logger.logger import AppLogger
            # AppLogger.reload_all_from_app_config()


            # Уведомляем главное окно о применённых изменениях (передаём список изменённых блоков)
            if self.main_window and hasattr(self.main_window, 'on_settings_changed'):
                self.main_window.on_settings_changed(
                    changed_blocks
                )

            QMessageBox.information(self, "Успех", "Настройки сохранены.")
            self.logger.info("Настройки сохранены, логгеры перезагружены")

            self._update_create_db_button_visibility()

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