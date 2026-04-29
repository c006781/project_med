# interfaces/gui/gui_window/widgets/delegate/type_delegate.py


from datetime import (
    date, 
    time
)
from typing import List

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu

from PySide6.QtWidgets import (
    QCompleter,
    QStyle,
    QStyledItemDelegate, 
    QLineEdit, QCheckBox, 
    QDateEdit, QTimeEdit, 
    QComboBox, 
    QPushButton, 
    QStyleOptionButton, 
    QApplication
)

from PySide6.QtCore import (
    Qt, 
    QPoint, 
    QDate, 
    QTime, 
    QModelIndex, 
    QAbstractItemModel, 
    QEvent, 
    QSize, 
    Signal
)

from PySide6.QtGui import (
    QPainter, 
    QMouseEvent
)



class StringDelegate(QStyledItemDelegate):
    """Делегат для редактирования строковых ячеек с русским контекстным меню."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        install_standard_context_menu(editor)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setText(str(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

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

class DateDelegate(QStyledItemDelegate):
    """Делегат для редактирования дат с календарём."""

    def createEditor(self, parent, option, index):
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd")
        # install_standard_context_menu(editor)
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
            model.setData(
                index, 
                date(qdate.year(), qdate.month(), qdate.day()), 
                Qt.EditRole
            )

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)       

class TimeDelegate(QStyledItemDelegate):
    """Делегат для редактирования времени."""

    def createEditor(self, parent, option, index):
        editor = QTimeEdit(parent)
        editor.setDisplayFormat("HH:mm")
        # install_standard_context_menu(editor)
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

# """
# Делегат для отображения выпадающего списка в ячейке таблицы.
# При клике на ячейку показывает QComboBox с заданными вариантами.
# """

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
        # install_standard_context_menu(combo)   #  (работает только для редактируемых комбобоксов)
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


# """
# Делегат для отображения кнопки в ячейке таблицы.
# При клике на кнопку испускается сигнал с индексом строки.
# """

class ButtonDelegate(QStyledItemDelegate):
    """
    Делегат, рисующий кнопку в ячейке.
    При клике испускает сигнал button_clicked с индексом строки.
    """
    button_clicked = Signal(int)
    
    def __init__(self, parent=None, button_text="..."):
        super().__init__(parent)
        self.button_text = button_text

    def paint(
        self, 
        painter: QPainter, 
        option, 
        index: QModelIndex
    ):
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

    def editorEvent(
        self, 
        event: QEvent, 
        model: QAbstractItemModel, 
        option, 
        index: QModelIndex
    ) -> bool:
        """Обрабатывает события мыши для кнопки."""
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = event
            if mouse_event.button() == Qt.MouseButton.LeftButton:
                # Эмитируем сигнал (можно через модель, но проще через главное окно)
                # self.parent().button_clicked.emit(index.row())
                self.button_clicked.emit(index.row())
                return True
        return False

    def sizeHint(self, option, index):
        """Возвращает размер, достаточный для кнопки."""
        return QSize(80, 25)  
    



class DateStringDelegate(StringDelegate):
    """Делегат для редактирования даты как строки с русским контекстным меню."""
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, date):
            editor.setText(value.isoformat())
        else:
            editor.setText(str(value) if value else "")

    def setModelData(self, editor, model, index):
        """
        Сохраняет текст в модели в формате datetime.date.
        Если текст пустой, то сохраняет None.
        Если текст не может быть преобразован в datetime.date, то оставляет старое значение.
        """
        text = editor.text().strip()
        if not text:
            model.setData(index, None, Qt.EditRole)
        else:
            try:
                d = date.fromisoformat(text)
                model.setData(index, d, Qt.EditRole)
            except ValueError:
                pass  # неверный формат – оставляем старое значение

class TimeStringDelegate(StringDelegate):
    """Делегат для редактирования времени как строки с русским контекстным меню."""
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, time):
            editor.setText(value.strftime("%H:%M"))
        else:
            editor.setText(str(value) if value else "")

    def setModelData(self, editor, model, index):
        text = editor.text().strip()
        if not text:
            model.setData(index, None, Qt.EditRole)
        else:
            try:
                t = time.fromisoformat(text)
                model.setData(index, t, Qt.EditRole)
            except ValueError:
                pass





# """
# Делегат для текстовых ячеек с автодополнением (QCompleter).
# """



class CompleterStringDelegate(QStyledItemDelegate):
    """
    Делегат для редактирования строковых ячеек с автодополнением.
    Список вариантов берётся из модели через коллбэк get_unique_values.
    """

    def __init__(self, parent=None, get_unique_values_func=None, column=None):
        """
        :param parent: родительский виджет (обычно QTableView)
        :param get_unique_values_func: функция, возвращающая список строк для автодополнения
        :param column: номер столбца (передаётся в get_unique_values_func)
        """
        super().__init__(parent)
        self.logger = AppLogger.get_instance(
            name='gui.CompleterStringDelegate',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user'
        )
        self._get_unique_values_func = get_unique_values_func
        self._column = column
        self._cache = {}  # кэш вариантов для столбца (на случай, если функция тяжёлая)

    def _get_values(self) -> List[str]:
        """Возвращает список вариантов для автодополнения (с кэшированием)."""
        if self._column in self._cache:
            return self._cache[self._column]
        if not self._get_unique_values_func:
            return []
        values = self._get_unique_values_func(self._column)
        self._cache[self._column] = values
        return values

    def createEditor(self, parent, option, index):
        """Создаёт QLineEdit с QCompleter."""
        editor = QLineEdit(parent)
        install_standard_context_menu(editor)

        # Выравнивание текста по верхнему краю (и левому)
        editor.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        values = self._get_values()
        if values:
            completer = QCompleter(values)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)   # поиск по подстроке
            editor.setCompleter(completer)

        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setText(str(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)