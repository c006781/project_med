# interfaces/gui/gui_window/widgets/time_delegate.py
from PySide6.QtWidgets import QStyledItemDelegate, QTimeEdit
from PySide6.QtCore import QTime, Qt
from datetime import time


class TimeDelegate(QStyledItemDelegate):
    """Делегат для редактирования времени."""

    def createEditor(self, parent, option, index):
        editor = QTimeEdit(parent)
        editor.setDisplayFormat("HH:mm")
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, time):
            editor.setTime(QTime(value.hour, value.minute))
        elif isinstance(value, QTime):
            editor.setTime(value)
        else:
            editor.setTime(QTime.currentTime())

    def setModelData(self, editor, model, index):
        qtime = editor.time()
        if qtime.isValid():
            model.setData(index, time(qtime.hour(), qtime.minute()), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)