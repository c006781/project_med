# interfaces/gui/gui_window/widgets/delegate/type_delegate.py

from datetime import (
    date, 
    time
)
from typing import Dict, List

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu

from PySide6.QtWidgets import (
    QCompleter, QDialog, QDialogButtonBox,
    QStyle, QStyledItemDelegate,  QLineEdit, 
    QCheckBox, QDateEdit, QTextEdit, 
    QTimeEdit, QComboBox, 
    # QPushButton, 
    QStyleOptionButton, QApplication,
    QVBoxLayout,
)

from PySide6.QtCore import (
    QRect, Qt, 
    # QPoint, 
    QDate, QTime,  QModelIndex, 
    QAbstractItemModel,  QEvent, 
    QSize,  Signal,
)

from PySide6.QtGui import (
    QPainter, 
    # QMouseEvent
)

class TextPopupDelegate(QStyledItemDelegate):
    """
    Делегат для ячеек с многострочным текстом.
    При наведении мыши показывает маленькую кнопку,
    по нажатию открывает диалог с QTextEdit для удобного редактирования с переносами строк.
    В режиме только для чтения диалог открывается без возможности редактирования.
    """
    # sawe_paint : dict = {}

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, readonly=False):
        super().__init__(parent)
        self._readonly = readonly
        self._hovered_row = -1
        self._hovered_col = -1
        # # для отслеживания изменения hover
        # self._prev_hovered_row = -1      
        # self._prev_hovered_col = -1

        self._button_rect = None

         # Устанавливаем фильтр событий на таблицу, чтобы ловить Leave
        if parent:
            parent.installEventFilter(self)
    
    # @AppLogger.get_instance(
    #     name='TextPopupDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def paint(self, painter, option, index):
        # Стандартная отрисовка содержимого ячейки
        super().paint(painter, option, index)

        # Если мышь над этой ячейкой – рисуем кнопку
        if self._hovered_row == index.row() and self._hovered_col == index.column():
            btn_rect = self._get_button_rect(option.rect)
            btn_opt = QStyleOptionButton()
            btn_opt.rect = btn_rect
            btn_opt.text = "..."
            btn_opt.state = QStyle.State_Enabled
            self._button_rect = btn_rect
            QApplication.style().drawControl(QStyle.CE_PushButton, btn_opt, painter)
    
    # @AppLogger.get_instance(
    #     name='TextPopupDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def _get_button_rect(self, cell_rect):
        """Возвращает прямоугольник кнопки в правой части ячейки."""
        btn_w = 20
        btn_h = 20
        x = cell_rect.right() - btn_w - 2
        y = cell_rect.top() + (cell_rect.height() - btn_h) // 2
        # temp = QRect(x, y, btn_w, btn_h)

        # k_now = (self._hovered_row, self._hovered_col)
        # for k, v in TextPopupDelegate.sawe_paint.items():
        #     if k != k_now:
        #         print(k, k_now)
        #         idx = self.parent().model().index(*k)
        #         if idx.isValid():
        #             self.parent().update(idx)
        #         # old_idx = model.index(*k)
        #         # if old_idx.isValid():

        #         #     # TextPopupDelegate.sawe_paint[(self._hovered_row, self._hovered_col)] = 
        #         #     self.parent().update(old_idx)



        # temp = None      
        # if k_now in TextPopupDelegate.sawe_paint.keys():
        #     temp = TextPopupDelegate.sawe_paint[k_now]
        
        # TextPopupDelegate.sawe_paint.clear()
            
        #     # return temp
        # if temp is None:
        #     temp = QRect(x, y, btn_w, btn_h)
        #     TextPopupDelegate.sawe_paint[k_now] = temp
        
        temp = QRect(x, y, btn_w, btn_h)
        return temp
    
    # @AppLogger.get_instance(
    #     name='TextPopupDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def eventFilter(self, obj, event):
        """Перехватываем событие Leave на таблице, чтобы сбросить hover."""
        if obj == self.parent() and event.type() == QEvent.Leave:
            if self._hovered_row != -1:
                # Запоминаем координаты, чтобы перерисовать
                old_row, old_col = self._hovered_row, self._hovered_col
                self._hovered_row = -1
                self._hovered_col = -1
                # Перерисовываем ячейку, где был hover
                idx = self.parent().model().index(old_row, old_col)
                if idx.isValid():
                    self.parent().update(idx)
            return False  # не блокируем дальнейшую обработку события
        return super().eventFilter(obj, event)
    
    # @AppLogger.get_instance(
    #     name='TextPopupDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def editorEvent(self, event, model, option, index):
        """
        Обрабатывает события мыши для ячейки с многострочным текстом.
        При наведении мыши показывает маленькую кнопку,
        по нажатию открывает диалог с QTextEdit для удобного редактирования с переносами строк.
        """
        # if event.type() == QEvent.MouseButtonPress:
        #     if self._hovered_row != -1:
        #         old_idx = model.index(self._hovered_row, self._hovered_col)
        #         self._hovered_row = -1
        #         self._hovered_col = -1
        #         if old_idx.isValid():
        #             self.parent().update(old_idx)
        # Обработка движения мыши – обновляем hover и перерисовываем старую/новую ячейки
        if event.type() == QEvent.MouseMove:
            
            new_row, new_col = index.row(), index.column()
            if (new_row, new_col) != (self._hovered_row, self._hovered_col):
                old_row, old_col = self._hovered_row, self._hovered_col
                self._hovered_row, self._hovered_col = new_row, new_col

                # Перерисовываем старую ячейку
                if old_row != -1:
                    old_idx = model.index(old_row, old_col)
                    if old_idx.isValid():

                        # TextPopupDelegate.sawe_paint[(self._hovered_row, self._hovered_col)] = 
                        self.parent().update(old_idx)
                # Перерисовываем новую ячейку
                self.parent().update(index)
            return False

        # Обработка двойного клика – только в режиме редактирования
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            if not self._readonly:
                self._open_popup(model, index)
                return True
            return False

        # Клик по кнопке (левой кнопкой)
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._button_rect and self._button_rect.contains(event.pos()):
                self._open_popup(model, index)
                return True

        return super().editorEvent(event, model, option, index)
    
    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _open_popup(self, model, index):
        """Открывает диалог просмотра/редактирования текста."""
        value = model.data(index, Qt.EditRole)
        text = str(value) if value is not None else ""

        dialog = QDialog(self.parent())
        dialog.setWindowTitle("Просмотр текста" if self._readonly else "Редактирование текста")

        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(text)
        if self._readonly:
            text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.Accepted:
            new_text = text_edit.toPlainText()
            if new_text != text:
                model.setData(index, new_text, Qt.EditRole)
    
    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_readonly(self, readonly):
        self._readonly = readonly
    
    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        # Не создаём редактор, вместо этого открываем попап (при двойном клике)
        return None

class StringDelegate(QStyledItemDelegate):
    """Делегат для редактирования строковых ячеек с русским контекстным меню."""
    
    @AppLogger.get_instance(
        name='StringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, column_masks: Dict[int, str] = None):
        super().__init__(parent)
        self.column_masks = column_masks or {}

    @AppLogger.get_instance(
        name='StringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        install_standard_context_menu(editor)
        # Установить маску, если есть для этой колонки
        mask = self.column_masks.get(index.column())
        if mask:
            editor.setInputMask(mask)
        return editor

    @AppLogger.get_instance(
        name='StringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setText(str(value))

    @AppLogger.get_instance(
        name='StringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

    @AppLogger.get_instance(
        name='StringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class BoolDelegate(QStyledItemDelegate):
    """Делегат для редактирования булевых значений (чекбокс)."""

    @AppLogger.get_instance(
        name='BoolDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        editor = QCheckBox(parent)
        editor.setCheckable(True)
        return editor

    @AppLogger.get_instance(
        name='BoolDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        editor.setChecked(bool(value))

    @AppLogger.get_instance(
        name='BoolDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        model.setData(index, editor.isChecked(), Qt.EditRole)

    @AppLogger.get_instance(
        name='BoolDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        rect = option.rect
        size = editor.sizeHint()
        x = rect.x() + (rect.width() - size.width()) // 2
        y = rect.y() + (rect.height() - size.height()) // 2
        editor.setGeometry(x, y, size.width(), size.height())

class DateDelegate(QStyledItemDelegate):
    """Делегат для редактирования дат с календарём."""

    @AppLogger.get_instance(
        name='DateDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd")
        # install_standard_context_menu(editor)
        install_standard_context_menu(editor)
        return editor

    @AppLogger.get_instance(
        name='DateDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, date):
            editor.setDate(QDate(value.year, value.month, value.day))
        elif isinstance(value, QDate):
            editor.setDate(value)
        else:
            editor.setDate(QDate.currentDate())

    @AppLogger.get_instance(
        name='DateDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        qdate = editor.date()
        if qdate.isValid():
            model.setData(
                index, 
                date(qdate.year(), qdate.month(), qdate.day()), 
                Qt.EditRole
            )

    @AppLogger.get_instance(
        name='DateDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)       

class TimeDelegate(QStyledItemDelegate):
    """Делегат для редактирования времени."""

    @AppLogger.get_instance(
        name='TimeDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        editor = QTimeEdit(parent)
        editor.setDisplayFormat("HH:mm")
        install_standard_context_menu(editor)
        return editor

    @AppLogger.get_instance(
        name='TimeDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, time):
            editor.setTime(QTime(value.hour, value.minute))
        elif isinstance(value, QTime):
            editor.setTime(value)
        else:
            editor.setTime(QTime.currentTime())

    @AppLogger.get_instance(
        name='TimeDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        qtime = editor.time()
        if qtime.isValid():
            model.setData(index, time(qtime.hour(), qtime.minute()), Qt.EditRole)

    @AppLogger.get_instance(
        name='TimeDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='ComboBoxDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, choices=None):
        """
        :param parent: родительский виджет (обычно QTableView)
        :param choices: список строк для выбора
        """
        super().__init__(parent)
        self.choices = choices or []

    @AppLogger.get_instance(
        name='ComboBoxDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        """Создаёт виджет-редактор (QComboBox) для ячейки."""
        combo = QComboBox(parent)
        combo.addItems(self.choices)
        # install_standard_context_menu(combo)   #  (работает только для редактируемых комбобоксов)
        return combo

    @AppLogger.get_instance(
        name='ComboBoxDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        """Устанавливает текущее значение модели в комбобокс."""
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        if value is not None:
            editor.setCurrentText(str(value))

    @AppLogger.get_instance(
        name='ComboBoxDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        """Сохраняет выбранное значение в модель."""
        value = editor.currentText()
        model.setData(index, value, Qt.ItemDataRole.EditRole)

    @AppLogger.get_instance(
        name='ComboBoxDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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
    
    @AppLogger.get_instance(
        name='ButtonDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, button_text="..."):
        super().__init__(parent)
        self.button_text = button_text

    @AppLogger.get_instance(
        name='ButtonDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='ButtonDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='ButtonDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def sizeHint(self, option, index):
        """Возвращает размер, достаточный для кнопки."""
        return QSize(80, 25)  
    



class DateStringDelegate(StringDelegate):
    """Делегат для редактирования даты как строки с русским контекстным меню."""

    @AppLogger.get_instance(
        name='DateStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, date):
            editor.setText(value.isoformat())
        else:
            editor.setText(str(value) if value else "")

    @AppLogger.get_instance(
        name='DateStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='TimeStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, time):
            editor.setText(value.strftime("%H:%M"))
        else:
            editor.setText(str(value) if value else "")

    @AppLogger.get_instance(
        name='TimeStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='CompleterStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='CompleterStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_values(self) -> List[str]:
        """Возвращает список вариантов для автодополнения (с кэшированием)."""
        if self._column in self._cache:
            return self._cache[self._column]
        if not self._get_unique_values_func:
            return []
        values = self._get_unique_values_func(self._column)
        self._cache[self._column] = values
        return values

    @AppLogger.get_instance(
        name='CompleterStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

    @AppLogger.get_instance(
        name='CompleterStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setText(str(value))

    @AppLogger.get_instance(
        name='CompleterStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

    @AppLogger.get_instance(
        name='CompleterStringDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)