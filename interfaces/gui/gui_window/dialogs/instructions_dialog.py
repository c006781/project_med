# interfaces/gui/gui_window/dialogs/instructions_dialog.py

import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton

from app.utils.logger.logger import AppLogger

class InstructionsDialog(QDialog):
    """
    Диалог с древовидным списком инструкций из папки docs.
    """

    @AppLogger.get_instance(
        name='InstructionsDialog',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Инструкции")
        self.resize(500, 400)

        self.logger = AppLogger.get_instance(
            name='gui.InstructionsDialog',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        self._setup_ui()
        self._load_docs_tree()

    def _setup_ui(self) -> None:
        """Создаёт интерфейс: дерево + кнопка закрытия."""

        layout = QVBoxLayout(self)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Инструкции")
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _load_docs_tree(self) -> None:
        """Рекурсивно сканирует папку docs и строит дерево."""

        # Определяем путь к папке docs (относительно корня проекта)
        # base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'docs')
        base_dir = os.path.join('.', 'docs')

        base_dir = os.path.abspath(base_dir) # ПОЛУЧАЕМ АБСОЛЮТНЫЙ ПУТЬ К ФАЙЛУ НЕ ПО ПОЛОЖЕНИЮ ЗАПУСКА ПРОГРАММЫ

        if not os.path.exists(base_dir):
            self.logger.warning(f"Папка docs не найдена: {base_dir}")
            return

        self.tree.clear()
        self._add_directory_to_tree(self.tree.invisibleRootItem(), base_dir)

    def _add_directory_to_tree(self, parent_item: QTreeWidgetItem, dir_path: str) -> None:
        """
        Рекурсивно добавляет содержимое директории в дерево.
        Папки становятся ветками (некликабельными), файлы .pdf – листьями.
        """

        try:
            entries = sorted(os.listdir(dir_path))
        except OSError as e:
            self.logger.error(f"Ошибка чтения директории {dir_path}: {e}")
            return

        for entry in entries:
            full_path = os.path.join(dir_path, entry)
            if os.path.isdir(full_path):
                # Создаём элемент папки (некликабельный)
                folder_item = QTreeWidgetItem(parent_item)
                folder_item.setText(0, entry)
                folder_item.setFlags(folder_item.flags() & ~Qt.ItemIsSelectable)
                # Рекурсивно добавляем содержимое
                self._add_directory_to_tree(folder_item, full_path)
            elif entry.lower().endswith('.pdf'):
                # Добавляем файл .pdf как лист
                file_item = QTreeWidgetItem(parent_item)
                file_item.setText(0, entry)
                file_item.setData(0, Qt.UserRole, full_path)  # сохраняем полный путь

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Обработка двойного клика: открыть .pdf в браузере."""

        file_path = item.data(0, Qt.UserRole)
        if file_path and os.path.isfile(file_path):
            # url = QUrl(f"file:///{file_path}")
            url = QUrl.fromLocalFile(file_path)
            if not QDesktopServices.openUrl(url):
                self.logger.warning(f"Не удалось открыть файл: {file_path}")
        else:
            self.logger.debug(f"Двойной клик по папке или не-файлу: {item.text(0)}")