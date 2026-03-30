# interfaces/gui/gui_window/widgets/date_delegate.py


from PySide6.QtWidgets import QStyledItemDelegate, QDateEdit
from PySide6.QtCore import QDate, Qt
from datetime import date


class DateDelegate(QStyledItemDelegate):
    """Делегат для редактирования дат с календарём."""

    def createEditor(self, parent, option, index):
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd")
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, date):
            editor.setDate(QDate(value.year, value.month, value.day))
        elif isinstance(value, QDate):
            editor.setDate(value)
        else:
            editor.setDate(QDate.currentDate())

    def setModelData(self, editor, model, index):
        qdate = editor.date()
        if qdate.isValid():
            model.setData(index, date(qdate.year(), qdate.month(), qdate.day()), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)