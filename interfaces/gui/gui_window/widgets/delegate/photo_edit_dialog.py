# interfaces/gui/gui_window/widgets/photo_edit_dialog.py
"""
Диалог для просмотра/редактирования одного фото.
Поддерживает:
    - отображение текущего изображения
    - выбор нового файла (с валидацией расширений)
    - удаление фото
    - редактирование описания (опционально)
"""

import os
import shutil
from typing import List, Optional, Tuple
import uuid

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTextEdit, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap



class PhotoEditDialog(QDialog):
    """
    Диалог для просмотра и редактирования фотографии.
    """

    def __init__(
        self, 
        parent=None, 
        current_path: Optional[str] = None,
        description: str = "", 
        allowed_extensions: List[str] = None,
        readonly: bool = False,
        parent_id: Optional[int] = None,
        storage_path: str = "",
    ):
        """
        Инициализирует диалог.

        Args:
            parent: Родительский виджет.
            current_path: Абсолютный путь к текущему файлу (может быть None).
            description: Текущее описание фото.
            allowed_extensions: Список разрешённых расширений (по умолчанию стандартные).
            readonly: Режим "только просмотр" (запрещает изменения).
        """
        super().__init__(parent)
        self.logger = AppLogger.get_instance('gui.PhotoEditDialog')
        self.setWindowTitle("Редактирование фото")
        self.resize(600, 500)

        self._current_path = current_path
        self._description = description
        self._allowed_extensions = allowed_extensions or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        self._readonly = readonly
        self._parent_id = parent_id          # ID родителя (существующей сущности) или None
        self._storage_path = storage_path    # базовый путь к хранилищу
        self._new_path = None
        self._new_description = None

        self._setup_ui()
        self._load_photo()

    def _copy_file_to_storage(self, source_path: str) -> str:
        """
        Копирует файл в хранилище, генерирует относительный путь.
        Возвращает относительный путь (относительно storage_path).
        """
        if not self._storage_path or self._parent_id is None or self._parent_id <= 0:
            # Для новых строк или без родителя не копируем – вернём абсолютный путь
            return source_path

        # Создаём подпапку для родителя
        parent_folder = os.path.join(self._storage_path, f"app_{self._parent_id}")
        os.makedirs(parent_folder, exist_ok=True)

        # Генерируем уникальное имя файла
        # import uuid
        ext = os.path.splitext(source_path)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(parent_folder, unique_name)

        # Копируем файл
        # import shutil
        shutil.copy2(source_path, dest_path)

        # Возвращаем относительный путь
        rel_path = os.path.relpath(dest_path, self._storage_path)
        return rel_path

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Область для превью
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(300)
        self.preview_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        layout.addWidget(self.preview_label)

        # Кнопки выбора файла и удаления
        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("Выбрать файл")
        self.select_btn.clicked.connect(self._select_file)
        self.select_btn.setEnabled(not self._readonly)
        btn_layout.addWidget(self.select_btn)

        self.delete_btn = QPushButton("Удалить фото")
        self.delete_btn.clicked.connect(self._delete_photo)
        self.delete_btn.setEnabled(not self._readonly and self._current_path is not None)
        btn_layout.addWidget(self.delete_btn)
        layout.addLayout(btn_layout)

        # Поле для описания
        self.desc_label = QLabel("Описание:")
        layout.addWidget(self.desc_label)
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlainText(self._description)
        self.desc_edit.setReadOnly(self._readonly)
        self.desc_edit.setMaximumHeight(100)
        layout.addWidget(self.desc_edit)

        # Кнопки OK/Cancel
        # from PySide6.QtWidgets import QDialogButtonBox
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_photo(self):
        """Загружает текущее фото (если есть) в preview."""
        if self._current_path and os.path.exists(self._current_path):
            pixmap = QPixmap(self._current_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
                return
        self.preview_label.setText("Нет фото")

    def _select_file(self):
        """Открывает диалог выбора файла, проверяет расширение."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            f"Изображения (*{' *'.join(self._allowed_extensions)})"
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self._allowed_extensions:
            QMessageBox.warning(self, "Ошибка",
                                f"Недопустимый формат файла.\nРазрешены: {', '.join(self._allowed_extensions)}")
            return

        # Загружаем preview
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return

        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self._new_path = self._copy_file_to_storage(file_path)
        self.delete_btn.setEnabled(True)

    def _delete_photo(self):
        """Удаляет текущее фото из хранилища (если путь относительный)."""

        if self._current_path and not os.path.isabs(self._current_path):
            full_path = os.path.join(self._storage_path, self._current_path)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except OSError as e:
                    self.logger.warning(f"Не удалось удалить файл {full_path}: {e}")
        self._current_path = None
        self._new_path = None
        self.preview_label.setText("Нет фото")
        self.delete_btn.setEnabled(False)
    
    def get_result(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Возвращает результат редактирования.

        Returns:
            Tuple[Optional[str], Optional[str]]: (новый_путь_к_файлу, новое_описание)
            Если фото было удалено, возвращает (None, None).
            Если изменений не было, возвращает (None, None).
        """

        new_desc = self.desc_edit.toPlainText()
        if self._new_path is not None:
            return self._new_path, new_desc
        if self._current_path is None:
            return None, None
        if new_desc != self._description:
            return self._current_path, new_desc
        return None, None

    def accept(self):
        """Переопределяем accept, чтобы перед закрытием сохранить результат."""
        self._new_description = self.desc_edit.toPlainText()
        super().accept()