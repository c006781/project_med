# interfaces/gui/gui_window/widgets/photo_uploader_widget.py

import os
from typing import List, Tuple, Dict

from PySide6.QtCore import QEvent, Signal, Qt, QSize
from PySide6.QtGui import QPixmap, QFontMetrics, QPainter, QTextOption
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QDialog, QLabel, QScrollArea, QStyledItemDelegate,
    QStyleOptionViewItem, QTextEdit, QApplication
)

from app.dto import PhotoDTO
from app.utils.logger.logger import AppLogger


class PhotoDelegate(QStyledItemDelegate):
    """
    Делегат для отрисовки масштабированной иконки в ячейке таблицы.
    """

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent, photo_widget):
        super().__init__(parent)
        self.photo_widget = photo_widget

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        full_path = index.data(Qt.UserRole)
        if not full_path:
            super().paint(painter, option, index)
            return

        pixmap = self.photo_widget._get_pixmap(full_path)
        if pixmap.isNull():
            super().paint(painter, option, index)
            return

        rect = option.rect
        scaled_pixmap = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = rect.x() + (rect.width() - scaled_pixmap.width()) // 2
        y = rect.y() + (rect.height() - scaled_pixmap.height()) // 2
        painter.drawPixmap(x, y, scaled_pixmap)

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def sizeHint(self, option: QStyleOptionViewItem, index):
        return QSize(100, 100)


class TextEditDelegate(QStyledItemDelegate):
    """
    Делегат для редактирования текста в ячейке с помощью многострочного QTextEdit.
    Поддерживает перенос строк, автоматический перенос при наборе и ручной ввод Shift+Enter.
    """

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        super().__init__(parent)

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def createEditor(self, parent, option, index):
        """Создаёт QTextEdit вместо стандартного QLineEdit."""
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)  # только обычный текст
        editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)  # перенос по словам
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Устанавливаем высоту около 100 пикселей для удобства
        editor.setMinimumHeight(80)
        return editor

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def setEditorData(self, editor, index):
        """Загружает текущий текст в редактор."""
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setPlainText(str(value))

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def setModelData(self, editor, model, index):
        """Сохраняет текст из редактора в модель."""
        model.setData(index, editor.toPlainText(), Qt.EditRole)

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def updateEditorGeometry(self, editor, option, index):
        """Устанавливает геометрию редактора (растягивается на всю ячейку)."""
        editor.setGeometry(option.rect)

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def eventFilter(self, editor, event):
        """
        Обрабатывает нажатия клавиш в редакторе.
        Enter завершает редактирование, Shift+Enter вставляет перенос строки.
        """
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Enter or event.key() == Qt.Key_Return:
                if event.modifiers() == Qt.ShiftModifier:
                    # Shift+Enter: вставляем перенос строки (стандартное поведение QTextEdit)
                    return False  # пусть обрабатывает QTextEdit
                else:
                    # Enter без Shift: завершаем редактирование
                    self.commitData.emit(editor)
                    self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
                    return True
        return super().eventFilter(editor, event)


class PhotoUploaderWidget(QWidget):
    """
    Виджет для управления фотографиями приёма.
    Отображает фото в таблице: столбец 0 – масштабированная иконка,
    столбец 1 – редактируемое описание с поддержкой переноса строк и многострочного редактирования.
    """
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
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='gui.PhotoUploaderWidget',
            enable_file_logging='user',
            use_name_in_filename='user',
        )
        self.logger.debug("Инициализация PhotoUploaderWidget")

        # Данные
        self.pending_photos: List[Tuple[str, str]] = []   # (путь, описание)
        self.existing_photos: List[PhotoDTO] = []         # существующие фото
        self.deleted_photo_ids: List[int] = []            # ID на удаление
        self._storage_path: str = None                    # базовый путь к хранилищу
        self._image_cache: Dict[str, QPixmap] = {}        # кэш изображений

        self._setup_ui()
        self._adjust_column_widths()

    # ----------------------------------------------------------------------
    # Построение интерфейса
    # ----------------------------------------------------------------------

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
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Таблица
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Фото", "Описание"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        # Настройка столбцов
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setWordWrap(True)  # для отображения многострочного текста

        # Делегаты
        photo_delegate = PhotoDelegate(self.table, self)
        self.table.setItemDelegateForColumn(0, photo_delegate)

        text_delegate = TextEditDelegate(self.table)
        self.table.setItemDelegateForColumn(1, text_delegate)

        # Сигналы
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        main_layout.addWidget(self.table)

        # Кнопки
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Добавить фото")
        self.add_btn.clicked.connect(self.add_photo)
        btn_layout.addWidget(self.add_btn)

        self.view_btn = QPushButton("Просмотр")
        self.view_btn.clicked.connect(self._view_photo)
        self.view_btn.setEnabled(False)
        btn_layout.addWidget(self.view_btn)

        self.remove_btn = QPushButton("Удалить выбранное")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)

        main_layout.addLayout(btn_layout)

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
    def _adjust_column_widths(self):
        width = self.table.viewport().width()
        if width > 0:
            col0_width = int(width * 0.33)
            self.table.setColumnWidth(0, col0_width)
            self.logger.debug(f"Ширина столбца 0: {col0_width}")

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
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_column_widths()
        self._adjust_row_heights()

    # ----------------------------------------------------------------------
    # Обработчики событий таблицы
    # ----------------------------------------------------------------------

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
    def _on_selection_changed(self):
        self.view_btn.setEnabled(len(self.table.selectedItems()) > 0)

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
    def _on_table_double_clicked(self, item: QTableWidgetItem):
        if item.column() == 0:
            self._view_photo()
        # столбец 1 редактируется автоматически через делегат

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
    def _on_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        column = item.column()
        if column != 1:
            return

        new_text = item.text()
        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            if photo.description != new_text:
                photo.description = new_text
                self.photosChanged.emit()
                self.logger.debug(f"Обновлено описание фото ID={photo.id}")
        else:
            pending_index = row - len(self.existing_photos)
            if pending_index < len(self.pending_photos):
                file_path, old_desc = self.pending_photos[pending_index]
                if old_desc != new_text:
                    self.pending_photos[pending_index] = (file_path, new_text)
                    self.photosChanged.emit()
                    self.logger.debug("Обновлено описание нового фото")

    # ----------------------------------------------------------------------
    # Действия с фотографиями
    # ----------------------------------------------------------------------

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
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return

        self.pending_photos.append((file_path, ""))
        self._refresh_table()
        self.photosChanged.emit()
        self.logger.info(f"Добавлено фото: {file_path}")

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
    def _remove_selected(self):
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            return

        for row in sorted(selected_rows, reverse=True):
            self._remove_row(row)

        self._refresh_table()
        self.photosChanged.emit()
        self.logger.info(f"Удалено {len(selected_rows)} фото")

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
    def _remove_row(self, row: int):
        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            self.deleted_photo_ids.append(photo.id)
            del self.existing_photos[row]
            self.logger.debug(f"Помечено на удаление фото ID={photo.id}")
        else:
            pending_index = row - len(self.existing_photos)
            del self.pending_photos[pending_index]
            self.logger.debug("Удалено новое фото")

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
    def _view_photo(self):
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            return
        row = next(iter(selected_rows))

        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            full_path = os.path.join(self._storage_path, photo.file_path) if self._storage_path else photo.file_path
        else:
            pending_index = row - len(self.existing_photos)
            file_path, _ = self.pending_photos[pending_index]
            full_path = file_path

        if not os.path.exists(full_path):
            self.logger.warning(f"Файл не найден: {full_path}")
            return

        pixmap = self._get_pixmap(full_path)
        if pixmap.isNull():
            self.logger.warning(f"Не удалось загрузить: {full_path}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Просмотр фото")
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        label = QLabel()
        label.setPixmap(pixmap)
        scroll.setWidget(label)
        layout.addWidget(scroll)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.resize(800, 600)
        dialog.exec()

    # ----------------------------------------------------------------------
    # Работа с таблицей
    # ----------------------------------------------------------------------

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
    def _refresh_table(self):
        total_rows = len(self.existing_photos) + len(self.pending_photos)
        self.table.setRowCount(total_rows)
        self.table.setUpdatesEnabled(False)

        for i, photo in enumerate(self.existing_photos):
            self._set_table_row(i, photo.file_path, photo.description or "", is_existing=True)
        for i, (file_path, desc) in enumerate(self.pending_photos):
            row = len(self.existing_photos) + i
            self._set_table_row(row, file_path, desc, is_existing=False)

        self._adjust_row_heights()
        self.table.setUpdatesEnabled(True)
        self.logger.debug(f"Таблица обновлена: {total_rows} строк")

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
    def _set_table_row(self, row: int, file_path: str, description: str, is_existing: bool):
        full_path = file_path
        if is_existing and self._storage_path:
            full_path = os.path.join(self._storage_path, file_path)

        item_icon = QTableWidgetItem()
        item_icon.setData(Qt.UserRole, full_path)
        item_icon.setFlags(item_icon.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, item_icon)

        item_text = QTableWidgetItem(description)
        item_text.setFlags(item_text.flags() | Qt.ItemIsEditable)
        item_text.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.table.setItem(row, 1, item_text)

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
    def _adjust_row_heights(self):
        col0_width = self.table.columnWidth(0)
        if col0_width <= 0:
            return

        font = self.table.font()
        metrics = QFontMetrics(font)

        for row in range(self.table.rowCount()):
            item_icon = self.table.item(row, 0)
            full_path = item_icon.data(Qt.UserRole) if item_icon else None
            if not full_path:
                continue

            pixmap = self._get_pixmap(full_path)
            if pixmap.isNull():
                icon_height = 100
            else:
                ratio = pixmap.width() / pixmap.height() if pixmap.height() > 0 else 1.0
                scaled_width = min(col0_width, pixmap.width())
                icon_height = int(scaled_width / ratio) if ratio > 0 else 100
                icon_height = max(icon_height, 1)

            item_text = self.table.item(row, 1)
            text = item_text.text() if item_text else ""

            text_height = 0
            if text:
                text_width = self.table.columnWidth(1) - 10
                if text_width > 0:
                    rect = metrics.boundingRect(0, 0, text_width, 0, Qt.TextWordWrap, text)
                    text_height = rect.height()

            row_height = max(icon_height, text_height) + 10
            self.table.setRowHeight(row, row_height)

    # ----------------------------------------------------------------------
    # Кэширование
    # ----------------------------------------------------------------------

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
    def _get_pixmap(self, full_path: str) -> QPixmap:
        if full_path in self._image_cache:
            return self._image_cache[full_path]
        pixmap = QPixmap(full_path)
        if not pixmap.isNull():
            self._image_cache[full_path] = pixmap
        return pixmap

    # ----------------------------------------------------------------------
    # Публичные методы
    # ----------------------------------------------------------------------

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
    def set_storage_path(self, path: str):
        self._storage_path = path
        self.logger.debug(f"Путь к хранилищу: {path}")

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
    def set_existing_photos(self, photos: List[PhotoDTO]):
        self.existing_photos = photos
        self._refresh_table()
        self.logger.debug(f"Установлено {len(photos)} существующих фото")

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
    def get_pending_photos(self) -> List[Tuple[str, str]]:
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
    def get_deleted_photo_ids(self) -> List[int]:
        return self.deleted_photo_ids

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
    def clear(self):
        self.pending_photos.clear()
        self.existing_photos.clear()
        self.deleted_photo_ids.clear()
        self._image_cache.clear()
        self.table.setRowCount(0)
        self.logger.debug("Виджет очищен")