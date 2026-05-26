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
    QDialog, QDialogButtonBox, QListWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTextEdit, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap



class PhotoEditDialog(QDialog):
    """
    Диалог для просмотра и редактирования фотографии.
    """

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.PhotoEditDialog',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value



    def __init__(
        self, 
        parent=None, 
        current_path: Optional[str] = None,
        description: str = "", 
        allowed_extensions: List[str] = None,
        readonly: bool = False,
        parent_id: Optional[int] = None,
        storage_path: str = "",
        mode: str = 'single',
        temp_dir: Optional[str] = None,
    ):
        """
        Инициализирует диалог.

        Args:
            parent: Родительский виджет.
            current_path: Абсолютный путь к текущему файлу (может быть None).
            description: Текущее описание фото.
            allowed_extensions: Список разрешённых расширений (по умолчанию стандартные).
            readonly: Режим "только просмотр" (запрещает изменения).
            parent_id: ID родительской сущности (для копирования файла).
            storage_path: Базовый путь к хранилищу фотографий.
            mode: Режим работы – 'single' (одно фото) или 'multi' (несколько файлов).
        """
        super().__init__(parent)

        # self.logger = AppLogger.get_instance('gui.PhotoEditDialog')
        self._mode = mode

        self._temp_dir = temp_dir

        # self.setWindowTitle("Редактирование фото")
        self.setWindowTitle("Редактирование фото" if self._mode == 'single' else "Выбор нескольких фото")
        self.resize(600, 500)

        self._current_path = current_path
        self._description = description
        self._allowed_extensions = allowed_extensions or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        self._readonly = readonly
        self._parent_id = parent_id          # ID родителя (существующей сущности) или None
        self._storage_path = storage_path    # базовый путь к хранилищу
        self._new_path = None
        self._new_description = None

        self._selected_files = []   # для multi-режима

        self._setup_ui()
        if self._mode == 'single':
            self._load_photo()

    def _get_full_path(self, rel_path: str) -> Optional[str]:
        """Возвращает полный путь к файлу, сначала проверяя временную папку."""
        if not rel_path:
            return None
        if os.path.isabs(rel_path):
            return rel_path if os.path.exists(rel_path) else None
        # Относительный путь – ищем во временной папке, потом в основной
        if self._temp_dir:
            cand = os.path.join(self._temp_dir, rel_path)
            if os.path.exists(cand):
                return cand
        if self._storage_path:
            cand = os.path.join(self._storage_path, rel_path)
            if os.path.exists(cand):
                return cand
        return None
    
    # ------------------------------------------------------------------
    # Копирование файла в хранилище (для single-режима)
    # ------------------------------------------------------------------

    def _copy_file_to_storage(self, source_path: str) -> str:
        """
        Копирует файл в хранилище, генерирует относительный путь.
        Возвращает относительный путь (относительно storage_path).
        """


        if self._temp_dir:
            # Временная папка черновика
            os.makedirs(self._temp_dir, exist_ok=True)
            ext = os.path.splitext(source_path)[1]

            unique_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(self._temp_dir, unique_name)

            shutil.copy2(source_path, dest_path)

            # Возвращаем просто имя файла (относительно temp_dir)
            return unique_name
        else:
            # Прямое копирование в основное хранилище (для уже сохранённых строк)
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

    def _add_files_multi(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", "",
                                                f"Изображения (*{' *'.join(self._allowed_extensions)})")
        for f in files:
            self.list_widget.addItem(f)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.splitext(path)[1].lower() in self._allowed_extensions:
                self.list_widget.addItem(path)
        event.acceptProposedAction()

    def get_selected_files(self) -> List[str]:
        """Возвращает список выбранных файлов (для multi-режима)."""
        if self._mode == 'multi':
            return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        else:
            return [self._new_path] if self._new_path else []

    # ------------------------------------------------------------------
    # Построение UI в зависимости от режима
    # ------------------------------------------------------------------

    def _setup_ui(self):
        if self._mode == 'multi':
            self._setup_multi_ui()
        else:
            self._setup_single_ui()

    def _setup_single_ui(self):
        """Создаёт UI для режима одного фото."""
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
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _setup_multi_ui(self):
        """Создаёт UI для режима множественного выбора файлов."""
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить файлы")
        add_btn.clicked.connect(self._add_files_multi)
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.list_widget.clear)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


        add_btn.setEnabled(not self._readonly)
        clear_btn.setEnabled(not self._readonly)
        self.list_widget.setEnabled(not self._readonly)

        # Отключаем drag-and-drop в режиме только для чтения
        self.setAcceptDrops(not self._readonly)

        # self.setAcceptDrops(True)



    def _load_photo(self):
        """Загружает текущее фото (если есть) в preview."""
        full_path = self._get_full_path(self._current_path)
        if full_path:
            pixmap = QPixmap(full_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
                return
        self.preview_label.setText("Нет фото")

        # if self._current_path and os.path.exists(self._current_path):
        #     pixmap = QPixmap(self._current_path)
        #     if not pixmap.isNull():
        #         scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        #         self.preview_label.setPixmap(scaled)
        #         return
        # self.preview_label.setText("Нет фото")

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
            QMessageBox.warning(
                self, 
                "Ошибка",
                f"Недопустимый формат файла.\nРазрешены: {', '.join(self._allowed_extensions)}"
            )
            return

        # Загружаем preview
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return

        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self._new_path = self._copy_file_to_storage(file_path)

        # Обновляем текущий путь для корректной работы при повторном открытии диалога
        self._current_path = self._new_path
        self.delete_btn.setEnabled(True)

    def _delete_photo(self):
        """Удаляет текущее фото из хранилища (если путь относительный)."""

        self.logger.debug(f"_delete_photo: current_path={self._current_path}")
        if self._current_path and not os.path.isabs(self._current_path):
            # Сначала ищем во временной папке
            if self._temp_dir:
                full_path = os.path.join(self._temp_dir, self._current_path)
            else:
                full_path = os.path.join(self._storage_path, self._current_path)

            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    self.logger.debug(f"Удалён файл {full_path}")
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