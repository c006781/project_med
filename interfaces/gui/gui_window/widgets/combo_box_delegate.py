# -*- coding: utf-8 -*-
"""
Делегат для отображения выпадающего списка в ячейке таблицы.
При клике на ячейку показывает QComboBox с заданными вариантами.
"""
from PySide6.QtWidgets import QStyledItemDelegate, QComboBox
from PySide6.QtCore import QModelIndex, QAbstractItemModel, QEvent, Qt
from PySide6.QtGui import QMouseEvent


class ComboBoxDelegate(QStyledItemDelegate):
    """
    Делегат, который при редактировании ячейки показывает QComboBox.
    Список значений для комбобокса передаётся через параметр choices.
    """

    def __init__(self, parent=None, choices=None):
        """
        :param parent: родительский виджет (обычно QTableView)
        :param choices: список строк для выбора
        """
        super().__init__(parent)
        self.choices = choices or []

    def createEditor(self, parent, option, index):
        """Создаёт виджет-редактор (QComboBox) для ячейки."""
        combo = QComboBox(parent)
        combo.addItems(self.choices)
        return combo

    def setEditorData(self, editor, index):
        """Устанавливает текущее значение модели в комбобокс."""
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        if value is not None:
            editor.setCurrentText(str(value))

    def setModelData(self, editor, model, index):
        """Сохраняет выбранное значение в модель."""
        value = editor.currentText()
        model.setData(index, value, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        """Обновляет геометрию редактора."""
        editor.setGeometry(option.rect)