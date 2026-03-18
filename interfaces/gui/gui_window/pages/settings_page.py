# -*- coding: utf-8 -*-
"""
Страница настроек приложения.
Позволяет редактировать параметры конфигурации и сохранять их в файл.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Slot, Qt

from interfaces.gui.gui_window.pages.base_page import BasePage
from app.config.config_manager.manager import AppConfigManager
from app.utils.logger.logger import AppLogger


class SettingsPage(BasePage):
    """
    Страница настроек.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = AppLogger.get_instance("gui.SettingsPage")
        self.config_manager = AppConfigManager.get_instance()
        self._setup_ui()
        self._load_settings()

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
        form_layout.addRow("Папка бекапов:", backup_layout)

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

    def _browse_file(self, line_edit, title, filter_str):
        """Открывает диалог выбора файла и вставляет путь в line_edit."""
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", filter_str)
        if file_path:
            line_edit.setText(file_path)

    def _browse_dir(self, line_edit, title):
        """Открывает диалог выбора папки."""
        dir_path = QFileDialog.getExistingDirectory(self, title)
        if dir_path:
            line_edit.setText(dir_path)

    def _load_settings(self):
        """Загружает текущие настройки из менеджера и заполняет поля."""
        self.db_path_edit.setText(self.config_manager.get('database_local_path', ''))
        self.photos_path_edit.setText(self.config_manager.get('PHOTOS_STORAGE_PATH', ''))
        self.token_edit.setText(self.config_manager.get('YANDEX_TOKEN', ''))
        self.remote_path_edit.setText(self.config_manager.get('database_remote_path', ''))
        self.backup_path_edit.setText(self.config_manager.get('BACKUP_PATH', ''))  # возможно, добавить в конфиг
        self.backup_count_spin.setValue(int(self.config_manager.get('BACKUP_COUNT', 5)))
        self.log_file_check.setChecked(self.config_manager.get('LOG_ENABLED', True))

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
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")
            self.logger.exception("Ошибка сохранения настроек")

    def on_enter(self):
        """При входе на страницу обновляем настройки (на случай внешних изменений)."""
        self.config_manager.load()  # перезагружаем из файла
        self._load_settings()
        self.logger.debug("Страница настроек открыта")