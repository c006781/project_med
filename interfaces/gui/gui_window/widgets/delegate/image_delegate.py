# interfaces/gui/gui_window/widgets/delegate/image_delegate.py
import os
from typing import (
    Dict, 
    # Optional,
)


from app.utils.logger.logger import AppLogger

from PySide6.QtCore import (
    # QMetaObject, Q_ARG, QRect, 
    QSize, Qt, QThread, Signal,
)
from PySide6.QtGui import (
    QPixmap, QPainter, 
    QColor,
)
from PySide6.QtWidgets import (
    QStyledItemDelegate, 
    QStyleOptionViewItem,
)


class AsyncImageLoader(QThread):
    """Загружает миниатюру в отдельном потоке."""
    finished = Signal(int, QPixmap)  # row, pixmap

    def __init__(self, row: int, full_path: str, target_size: QSize):
        super().__init__()
        self.row = row
        self.full_path = full_path
        self.target_size = target_size

    def run(self):
        pixmap = QPixmap(self.full_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        self.finished.emit(self.row, pixmap)


class ImageThumbnailDelegate(QStyledItemDelegate):
    """
    Делегат для отображения миниатюры изображения в ячейке таблицы.
    Путь к файлу берётся из модели через Qt.UserRole.
    """
    _cache: Dict[str, QPixmap] = {}          # общий кэш для всех экземпляров
    _pending: Dict[str, bool] = {}           # флаги, чтобы не дублировать загрузку

    def __init__(self, parent=None, storage_path: str = "", target_size: QSize = QSize(80, 80)):
        super().__init__(parent)
        self.logger = AppLogger.get_instance('gui.ImageThumbnailDelegate')
        self.storage_path = storage_path
        self.target_size = target_size

    def sizeHint(self, option: QStyleOptionViewItem, index):
        """
        Возвращает высоту строки:
            - если в ячейке есть фото → высота миниатюры + отступ
            - иначе → стандартная высота (через базовый метод)
        """
        file_path = index.data(Qt.UserRole) if index.isValid() else None
        if not file_path:
            # Нет пути – используем стандартное поведение
            return super().sizeHint(option, index)
        # Есть фото – фиксированная высота на основе target_size
        return QSize(self.target_size.width(), self.target_size.height() + 10)

    def set_storage_path(self, path: str):
        self.storage_path = path

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # Получаем путь к файлу (из UserRole, т.к. DisplayRole возвращает строку)
        file_path = index.data(Qt.UserRole) if index.isValid() else None
        if not file_path:
            self._draw_placeholder(painter, option, "Нет фото")
            return

        full_path = os.path.join(self.storage_path, file_path) if self.storage_path else file_path
        if not os.path.exists(full_path):
            self._draw_placeholder(painter, option, "Файл не найден")
            return

        # Проверяем кэш
        if full_path in self._cache:
            pixmap = self._cache[full_path]
            self._draw_pixmap(painter, option, pixmap)
            return

        # Если ещё не загружали – ставим заглушку и запускаем загрузку
        if full_path not in self._pending:
            self._pending[full_path] = True
            loader = AsyncImageLoader(index.row(), full_path, self.target_size)
            loader.finished.connect(self._on_thumbnail_loaded)
            loader.start()

        self._draw_placeholder(painter, option, "Загрузка...")

    def _draw_pixmap(self, painter: QPainter, option: QStyleOptionViewItem, pixmap: QPixmap):
        rect = option.rect
        scaled = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def _draw_placeholder(self, painter: QPainter, option: QStyleOptionViewItem, text: str):
        painter.fillRect(option.rect, QColor(240, 240, 240))
        painter.drawText(option.rect, Qt.AlignCenter, text)

    def _on_thumbnail_loaded(self, row: int, pixmap: QPixmap):
        # Сохраняем в кэш (ключ – полный путь, но мы его не знаем – можно передавать)
        # В упрощённом варианте – обновляем ячейку, заставив перерисовать
        # Для простоты будем обновлять весь виджет таблицы
        if self.parent() and hasattr(self.parent(), 'viewport'):
            self.parent().viewport().update()

    def sizeHint(self, option, index):
        return QSize(self.target_size.width(), self.target_size.height() + 10)