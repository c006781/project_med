# interfaces/gui/gui_window/mixins/right_panel_mixin.py

"""
Миксин для управления правой панелью (заметка и фото).
"""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QTextEdit
from PySide6.QtCore import Qt

from app.config.config_manager.manager import get_config_env
from app.utils.logger.logger import AppLogger
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

import os


class RightPanelMixin:
    """
    Создаёт и управляет правой панелью: заметка и фотографии.
    Атрибуты (должны быть определены в классе-наследнике):
        detail_widget: QWidget
        detail_layout: QVBoxLayout
        note_text_edit: QTextEdit
        photo_widget: PhotoUploaderWidget
        _loading_right_panel: bool
        edit_mode: bool
        selected_dto: Any
        logger: AppLogger
    """

    def _setup_detail_panel(self):
        """Создаёт виджеты правой панели и подключает сигналы."""
        # Заметка
        self.note_text_edit = QTextEdit()
        self.note_text_edit.setReadOnly(True)  # изначально только просмотр
        self.note_text_edit.textChanged.connect(self._on_draft_changed)

        self.detail_layout.addWidget(QLabel("Заметка:"))
        self.detail_layout.addWidget(self.note_text_edit)

        # Фотографии
        self.photo_widget = PhotoUploaderWidget()
        config = get_config_env()
        storage_path = config.get(
            'PHOTOS_STORAGE_PATH',
            os.path.join('.', 'photos')
        )
        self.logger.debug(f'storage_path: {storage_path}')
        self.photo_widget.set_storage_path(storage_path)
        self.photo_widget.set_readonly(True)
        self.photo_widget.photosChanged.connect(self._on_draft_changed)

        self.detail_layout.addWidget(QLabel("Фотографии:"))
        self.detail_layout.addWidget(self.photo_widget)

        self._loading_right_panel = False

    def _on_note_text_changed(self):
        """
        Обработчик изменения текста заметки (может быть вызван напрямую,
        но мы уже используем _on_draft_changed, поэтому этот метод можно
        оставить как заглушку или вообще убрать.
        """
        pass

    def _on_photos_changed(self):
        """
        Обработчик изменения списка фото (используется _on_draft_changed).
        """
        pass