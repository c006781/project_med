# interfaces/gui/gui_window/widgets/bool_delegate.py

from PySide6.QtWidgets import QStyledItemDelegate, QCheckBox
from PySide6.QtCore import Qt


class BoolDelegate(QStyledItemDelegate):
    """Делегат для редактирования булевых значений (чекбокс)."""

    def createEditor(self, parent, option, index):
        editor = QCheckBox(parent)
        editor.setCheckable(True)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        editor.setChecked(bool(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.isChecked(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect
        size = editor.sizeHint()
        x = rect.x() + (rect.width() - size.width()) // 2
        y = rect.y() + (rect.height() - size.height()) // 2
        editor.setGeometry(x, y, size.width(), size.height())