# interfaces/gui/gui_window/widgets/photo_uploader_widget.py

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QInputDialog, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap, QIcon
import os

class PhotoUploaderWidget(QWidget):
    photosChanged = Signal()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        """
        Инициализирует виджет для загрузки фотографий.
        :param parent: родительский виджет
        :type parent: QWidget
        """
        super().__init__(parent)
        self.pending_photos = []  # список (file_path, description)
        self.existing_photos = []  # список (photo_id, file_path, description)
        self.deleted_photo_ids = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(Qt.QSize(100, 100))
        self.list_widget.setViewMode(QListWidget.IconMode)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Добавить фото")
        self.add_btn.clicked.connect(self.add_photo)
        btn_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Удалить выбранное")
        self.remove_btn.clicked.connect(self.remove_photo)
        btn_layout.addWidget(self.remove_btn)

        layout.addLayout(btn_layout)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def add_photo(self):
        """
        Добавляет фото в временный список.
        Открывает диалог для выбора файла и ввода описания.
        Добавляет фото в список pending_photos и отображает его в виджете.
        Вызывает сигнал photosChanged.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return
        description, ok = QInputDialog.getText(self, "Описание", "Введите описание фото:")
        if not ok:
            description = ""
        # Добавляем во временный список
        self.pending_photos.append((file_path, description))
        self._add_item_to_list(file_path, description, is_existing=False)
        self.photosChanged.emit()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def remove_photo(self):
        """
        Удаляет фото из временного списка или из списка существующих.
        Вызывает сигнал photosChanged.
        """
        current = self.list_widget.currentItem()
        if not current:
            return
        row = self.list_widget.row(current)
        # Определяем, из какого списка удаляем
        if row < len(self.existing_photos):
            # Удаляем существующее фото
            photo_id = self.existing_photos[row][0]
            self.deleted_photo_ids.append(photo_id)
            del self.existing_photos[row]
        else:
            # Удаляем из pending
            pending_index = row - len(self.existing_photos)
            del self.pending_photos[pending_index]
        self.list_widget.takeItem(row)
        self.photosChanged.emit()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _add_item_to_list(self, file_path, description, is_existing):
        """
        Добавляет фото в список фотографий.

        :param file_path: путь к файлу с фотографией
        :param description: описание фотографии
        :param is_existing: флаг, указывающий на то, является ли фото существующим
        """
        pixmap = QPixmap(file_path)
        icon = QIcon(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        item = QListWidgetItem(icon, description or "")
        self.list_widget.addItem(item)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_existing_photos(self, photos):
        """
        Устанавливает существующие фотографии.

        :param photos: список существующих фотографий
        :type photos: List[PhotoDTO]
        """
        self.existing_photos = photos
        self._refresh_list()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _refresh_list(self):
        """
        Обновляет список фотографий.

        Сначала существующие фото, а потом новые.
        """
        self.list_widget.clear()
        # Сначала существующие фото
        for photo_id, file_path, desc in self.existing_photos:
            self._add_item_to_list(file_path, desc, is_existing=True)
        # Потом новые
        for file_path, desc in self.pending_photos:
            self._add_item_to_list(file_path, desc, is_existing=False)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_pending_photos(self):
        return self.pending_photos

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_deleted_photo_ids(self):
        """
        Возвращает список id удаленных фотографий.

        :return: список id удаленных фотографий
        :rtype: List[int]
        """
        return self.deleted_photo_ids