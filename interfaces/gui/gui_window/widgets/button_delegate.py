# -*- coding: utf-8 -*-
"""
Делегат для отображения кнопки в ячейке таблицы.
При клике на кнопку испускается сигнал с индексом строки.
"""
from PySide6.QtWidgets import QStyledItemDelegate, QPushButton, QStyleOptionButton, QApplication
from PySide6.QtCore import Qt, QModelIndex, QAbstractItemModel, QEvent, QSize
from PySide6.QtGui import QPainter, QMouseEvent


class ButtonDelegate(QStyledItemDelegate):
    """
    Делегат, рисующий кнопку в ячейке.
    При клике испускает сигнал button_clicked с индексом строки.
    """
    def __init__(self, parent=None, button_text="..."):
        super().__init__(parent)
        self.button_text = button_text

    def paint(self, painter: QPainter, option, index: QModelIndex):
        """Отрисовывает кнопку."""
        # Сохраняем состояние painter
        painter.save()

        # Создаём опцию кнопки
        btn_option = QStyleOptionButton()
        btn_option.rect = option.rect
        btn_option.text = self.button_text
        btn_option.state = QStyle.StateFlag.State_Enabled

        # Отрисовываем кнопку
        QApplication.style().drawControl(QApplication.style().CE_PushButton, btn_option, painter)

        painter.restore()

    def editorEvent(self, event: QEvent, model: QAbstractItemModel, option, index: QModelIndex) -> bool:
        """Обрабатывает события мыши для кнопки."""
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = event
            if mouse_event.button() == Qt.MouseButton.LeftButton:
                # Эмитируем сигнал (можно через модель, но проще через главное окно)
                self.parent().button_clicked.emit(index.row())
                return True
        return False

    def sizeHint(self, option, index):
        """Возвращает размер, достаточный для кнопки."""
        return QSize(80, 25)