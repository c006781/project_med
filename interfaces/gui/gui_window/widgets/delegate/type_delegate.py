# interfaces/gui/gui_window/widgets/delegate/type_delegate.py

from dataclasses import dataclass
from datetime import (
    date, 
    time
)
from typing import Any, Dict, List, OrderedDict

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.utils.gui_helpers import install_standard_context_menu

from PySide6.QtWidgets import (
    QCompleter, QDateTimeEdit, QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QPushButton,
    QStyle, QStyledItemDelegate,  QLineEdit, 
    QCheckBox, QTextEdit, 
    QComboBox, 
    # QPushButton, QTimeEdit,  QDateEdit,
    QStyleOptionButton, QApplication,
    QVBoxLayout,
)

from PySide6.QtCore import (
    QDateTime, QRect, Qt, 
    # QPoint, 
    QDate, QTime,  QModelIndex, 
    QAbstractItemModel,  QEvent, 
    QSize,  Signal,
)

from PySide6.QtGui import (
    QPainter, 
    # QMouseEvent
)

from interfaces.gui.gui_window.widgets.custom_date_time_widgets import DateEditWidget, TimeEditWidget


@dataclass(frozen=True)  # frozen=True делает объект неизменяемым и хешируемым
class Point:
    x: int
    y: int

    def get_coords(self):
        return self.x, self.y


# Добавьте новый класс перед определением TextPopupDelegate
class TextEditDialog(QDialog):
    """Диалог для редактирования многострочного текста с автодополнением."""
        
    @AppLogger.get_instance(
        name='TextEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent, initial_text="", readonly=False, completion_list=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование текста")
        self.resize(600, 400)
        self.readonly = readonly
        self.completion_list = completion_list or []

        layout = QVBoxLayout(self)

        # Верхняя панель с кнопками (справа)
        top_layout = QHBoxLayout()
        btn_save = QPushButton("Сохранить")
        btn_cancel = QPushButton("Отмена")
        btn_save.setDefault(True)

        if readonly:
            btn_save.setEnabled(False)
        # btn_save.setEnabled(readonly)

        top_layout.addStretch()
        top_layout.addWidget(btn_save)
        top_layout.addWidget(btn_cancel)
        layout.addLayout(top_layout)

        # Многострочное поле
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(initial_text)

        if readonly:
            self.text_edit.setReadOnly(True)
        # self.text_edit.setReadOnly(not readonly )

        layout.addWidget(self.text_edit)

        # Список подсказок (автодополнение)
        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(100)
        self.list_widget.setVisible(False)

        # Добавляем стиль для подсветки строки при наведении мыши
        self.list_widget.setStyleSheet("""
    QListWidget::item:hover {
        background-color: #d0e0ff;
    }
"""
        )

        layout.addWidget(self.list_widget)

        # Подключаем сигналы
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    @AppLogger.get_instance(
        name='TextEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_text_changed(self):
        """Фильтрует список подсказок по текущему тексту."""
        if not self.completion_list:
            return
        
        text = self.text_edit.toPlainText().lower()
        if len(text) >= 1:
            filtered = [item for item in self.completion_list if text in item.lower()]
            self.list_widget.clear()
            self.list_widget.addItems(filtered[:10])  # не более 10
            self.list_widget.setVisible(bool(filtered))
        else:
            self.list_widget.setVisible(False)

    @AppLogger.get_instance(
        name='TextEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_item_clicked(self, item):
        """Вставляет выбранный текст в позицию курсора."""

        # cursor = self.text_edit.textCursor()
        # cursor.insertText(item.text())
        # self.text_edit.setTextCursor(cursor)

        self.text_edit.setPlainText(item.text())
        self.list_widget.setVisible(False)

    @AppLogger.get_instance(
        name='TextEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_text(self):

        return self.text_edit.toPlainText()

# class TextPopupDelegate(QStyledItemDelegate):
#     """
#     Делегат для ячеек с многострочным текстом.
#     При наведении мыши показывает маленькую кнопку,
#     по нажатию открывает диалог с QTextEdit для удобного редактирования с переносами строк.
#     В режиме только для чтения диалог открывается без возможности редактирования.
#     """
#     # sawe_paint : dict = {}

#     # _last_hovered_row = -1
#     # _last_hovered_col = -1

#     points_dict = OrderedDict()
#     # btn_opt = OrderedDict()
#     _button = None

#     @AppLogger.get_instance(
#         name='TextPopupDelegate',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def __init__(
#         self, 
#         parent=None, 
#         readonly=False, 
#         get_completion_list=None,
#     ):
#         super().__init__(parent)
#         self._readonly = readonly
#         self._get_completion_list = get_completion_list   # функция, возвращающая список строк
        
#         self._hovered_row = -1
#         self._hovered_col = -1

#         self._button_rect = None
#         # self._button = None

#         self._current_row = -1
#         self._current_col = -1

#          # Устанавливаем фильтр событий на таблицу, чтобы ловить Leave
#         if parent:
#             # parent.installEventFilter(self)

#             parent.setMouseTracking(True) 
#             parent.installEventFilter(self)
#             # Создаём кнопку один раз, скрытую
#             TextPopupDelegate._button = QPushButton("...", parent.viewport())
#             TextPopupDelegate._button.setFixedSize(20, 20)
#             TextPopupDelegate._button.setCursor(Qt.PointingHandCursor)
#             TextPopupDelegate._button.clicked.connect(self._on_button_clicked)
#             TextPopupDelegate._button.hide()

#     def _on_button_clicked(self):
#         if self._current_row >= 0 and self._current_col >= 0:
#             model = self.parent().model()
#             idx = model.index(self._current_row, self._current_col)
#             if idx.isValid():
#                 self._open_popup(model, idx)
    

#     def _update_button_position(self, index):
#         if not index.isValid() or not self.parent():
#             return
#         rect = self.parent().visualRect(index)  # уже в координатах viewport
#         btn_rect = QRect(
#             rect.right() - 22, 
#             rect.top() + (rect.height() - 20) // 2, 
#             20, 20
#         )
#         TextPopupDelegate._button.setGeometry(btn_rect)

#     def _show_button(self, index):
#         # if not self._readonly:
#         self._update_button_position(index)
#         TextPopupDelegate._button.show()
#         self._current_row = index.row()
#         self._current_col = index.column()

#     def _hide_button(self):
#         TextPopupDelegate._button.hide()
#         self._current_row = -1
#         self._current_col = -1
    

#     # @AppLogger.get_instance(
#     #     name='TextPopupDelegate',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     def paint(self, painter, option, index):
#         # Стандартная отрисовка содержимого ячейки
#         super().paint(painter, option, index)
#         # row, col = index.row(), index.column()
        
#         # key = Point(row, col)

#         # # Если мышь над этой ячейкой – рисуем кнопку
#         # print("paint 1 row, col", row, col)
#         # if self._hovered_row == row and self._hovered_col == col:
#         #     btn_rect = self._get_button_rect(option.rect)
#         #     print("paint 2 row, col", row, col)
#         #     if not btn_rect.isEmpty():
#         #         print("paint 3 row, col", row, col)
#         #         btn_opt = QStyleOptionButton()
#         #         btn_opt.rect = btn_rect
#         #         btn_opt.text = "..."
#         #         btn_opt.state = QStyle.State_Enabled
#         #         self._button_rect = btn_rect
#         #         QApplication.style().drawControl(QStyle.CE_PushButton, btn_opt, painter)
#         # #         TextPopupDelegate.points_dict[Point(row,col)] = (btn_opt, btn_rect)
#         # # # Добавляем текущую позицию в словарь (перемещаем в конец, если уже есть)
#         #         if key in TextPopupDelegate.points_dict:
#         #             TextPopupDelegate.points_dict.move_to_end(key)
#         #         else:
#         #             TextPopupDelegate.points_dict[key] = None
        
#         # # Если в словаре накопилось больше 1 позиции, значит где-то залипла кнопка
#         # # Удаляем самую старую и перерисовываем её ячейку
#         # while len(TextPopupDelegate.points_dict) > 1:
#         # # if len(TextPopupDelegate.points_dict) > 1:
#         #     oldest_key = next(iter(TextPopupDelegate.points_dict))
#         #     if oldest_key != key:  # не удаляем текущую
#         #         oldest_idx = index.model().index(oldest_key.x, oldest_key.y)
#         #         if oldest_idx.isValid():
#         #             old_rect = self.parent().visualRect(oldest_idx)
#         #             self.parent().viewport().update(old_rect)
#         #         TextPopupDelegate.points_dict.popitem(last=False)

                
#         # self._update_del_()
    
#     # @AppLogger.get_instance(
#     #     name='TextPopupDelegate',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     def _get_button_rect(self, cell_rect):
#         """Возвращает прямоугольник кнопки в правой части ячейки."""
#         btn_w = 20
#         btn_h = 20
#         x = cell_rect.right() - btn_w - 2
#         y = cell_rect.top() + (cell_rect.height() - btn_h) // 2
        
#         temp = QRect(x, y, btn_w, btn_h)
#         return temp
    
#     def _update_del_(
#         self, 
#     ):
#         while len(TextPopupDelegate.points_dict) > 1:
 
#             # Получаем первый (самый старый) ключ в OrderedDict
#             # first_key = next(iter(TextPopupDelegate.points_dict))
#             first_key, tt = TextPopupDelegate.points_dict.popitem(last=False)
#             btn_opt, btn_rect = tt
#             del btn_opt
#             del btn_rect
#             idx = self.parent().model().index(
#                 first_key.x, 
#                 first_key.y
#             )

#             old_rect = self.parent().visualRect(idx)
#             self.parent().viewport().update(old_rect)

#             # if idx.isValid():
#             #     self.parent().update(idx)
#             # Удаляем его
#             # del TextPopupDelegate.points_dict[first_key]    
#         else:
#             return True



#     # @AppLogger.get_instance(
#     #     name='TextPopupDelegate',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     def eventFilter(self, obj, event):
#         """Перехватываем событие Leave на таблице, чтобы сбросить hover."""
#         if obj == self.parent() and event.type() == QEvent.Leave:
#             self._hide_button()
#         return super().eventFilter(obj, event)

#         # if obj == self.parent() and event.type() == QEvent.Leave:

#         #     print("eventFilter 1", )
#         #     # self._update_del_()
#         #     if self._hovered_row != -1:
#         #         # Запоминаем координаты, чтобы перерисовать
#         #         old_row, old_col = self._hovered_row, self._hovered_col
#         #         self._hovered_row = -1
#         #         self._hovered_col = -1
#         #         # Перерисовываем ячейку, где был hover
#         #         idx = self.parent().model().index(old_row, old_col)

#         #         print( " eventFilter 2 old_row, old_col" ,old_row, old_col)
#         #         if idx.isValid():
#         #             print( " eventFilter 3 old_row, old_col" ,old_row, old_col)
#         #             # self.parent().update(idx)
#         #             old_rect = self.parent().visualRect(idx)
#         #             self.parent().viewport().update(old_rect)
#         #     return False  # не блокируем дальнейшую обработку события
#         # return super().eventFilter(obj, event)
    
#     def _update_del(self, model, row, col):
#         if row != -1:
#             old_idx = model.index(row, col)
#             print( " _update_del 1 row, col" ,row, col)
#             if old_idx.isValid():
#                 print( " _update_del  2 row, col" ,row, col)
#                 # Принудительно перерисовываем область старой ячейки
#                 old_rect = self.parent().visualRect(old_idx)
#                 self.parent().viewport().update(old_rect)

#                 # # TextPopupDelegate.sawe_paint[(self._hovered_row, self._hovered_col)] = 
#                 # self.parent().update(old_idx)
        
#     # @AppLogger.get_instance(
#     #     name='TextPopupDelegate',
#     #     # share_file_with = 'system',
#     #     enable_file_logging = 'system',
#     #     use_name_in_filename = False, # 'system'
#     # ).log_execution_time(
#     #     level=AppLogger._parse_log_level('DEBUG')
#     # )
#     def editorEvent(self, event, model, option, index):
#         """
#         Обрабатывает события мыши для ячейки с многострочным текстом.
#         При наведении мыши показывает маленькую кнопку,
#         по нажатию открывает диалог с QTextEdit для удобного редактирования с переносами строк.
#         """
       
#         # Обработка движения мыши – обновляем hover и перерисовываем старую/новую ячейки
#         if event.type() == QEvent.MouseMove:
#             if index.isValid():
#                 if (index.row(), index.column()) != (self._current_row, self._current_col):
#                     self._hide_button()
#                     self._show_button(index)
#             else:
#                 self._hide_button()
#             return False
        
#         if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
#             # Если клик по кнопке – она обработает сама (через clicked)
#             if TextPopupDelegate._button.isVisible() and TextPopupDelegate._button.geometry().contains(event.pos()):
#                 return True  # событие не передаём дальше в таблицу
#         return super().editorEvent(event, model, option, index)
    
#             # new_row, new_col = index.row(), index.column()
#             # # TextPopupDelegate.points_dict[Point(new_row,new_col)] = None
#             # # self._update_del_()
            
#             # print( " editorEvent 1 new_row, new_col" ,new_row, new_col)
#             # if (new_row, new_col) != (self._hovered_row, self._hovered_col):
#             #     old_row, old_col = self._hovered_row, self._hovered_col
#             #     self._hovered_row, self._hovered_col = new_row, new_col

#             #     print( " editorEvent  2 old_row, old_col" ,old_row, old_col)
#             #     # Полная перерисовка таблицы гарантированно убирает старую кнопку
#             #     # self.parent().viewport().update()

#             #     # # # Перерисовываем старую ячейку
#             #     # self._update_del(model, old_row, old_col)

#             #     # Перерисовываем новую ячейку (кнопка появится в paint)
#             #     new_rect = self.parent().visualRect(index)
#             #     self.parent().viewport().update(new_rect)

#             #     # # if (
#             #     # #     TextPopupDelegate._last_hovered_row is not None
#             #     # # ) and (
#             #     # #     TextPopupDelegate._last_hovered_col is not None
#             #     # # ):
#             #     # if (
#             #     #     TextPopupDelegate._last_hovered_row != index.row()
#             #     # ) and (
#             #     #     TextPopupDelegate._last_hovered_col != index.column()
#             #     # ):
#             #     #     self._update_del(
#             #     #         model, 
#             #     #         TextPopupDelegate._last_hovered_row, 
#             #     #         TextPopupDelegate._last_hovered_col                        
#             #     #     )
                
#             #     # else:
#             #     #     0==0      
#             #     # if old_row != -1:
#             #     #     old_idx = model.index(old_row, old_col)
#             #     #     if old_idx.isValid():
#             #     #         # Принудительно перерисовываем область старой ячейки
#             #     #         old_rect = self.parent().visualRect(old_idx)
#             #     #         self.parent().viewport().update(old_rect)

#             #             # # TextPopupDelegate.sawe_paint[(self._hovered_row, self._hovered_col)] = 
#             #             # self.parent().update(old_idx)
#             #     # if self.old_rect
#             #     # TextPopupDelegate.points_dict[Point(new_row,new_col)] = None
#             #     # TextPopupDelegate._last_hovered_row = new_row
#             #     # TextPopupDelegate._last_hovered_col = new_col
#             #     # self._update_del_()
#             #     # Перерисовываем новую ячейку
#             #     # new_rect = self.parent().visualRect(index)
#             #     # self.parent().viewport().update(new_rect)

#             #     # # Перерисовываем новую ячейку
#             #     # self.parent().update(index)
#             # return False

#         # Обработка двойного клика – только в режиме редактирования
#         if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
#             if not self._readonly:
#                 self._open_popup(model, index)
#                 return True
#             return False

#         # Клик по кнопке (левой кнопкой)
#         if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
#             if self._button_rect and self._button_rect.contains(event.pos()):
#                 self._open_popup(model, index)
#                 return True

#         return super().editorEvent(event, model, option, index)
    
#     @AppLogger.get_instance(
#         name='TextPopupDelegate',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def _open_popup(self, model, index):
#         """Открывает диалог просмотра/редактирования текста."""
        
#         value = model.data(index, Qt.EditRole)
#         text = str(value) if value is not None else ""

#         # Получаем список вариантов для автодополнения
#         completion_list = self._get_completion_list() if self._get_completion_list else []

#         dialog = TextEditDialog(self.parent(), text, self._readonly, completion_list)
#         if dialog.exec() == QDialog.Accepted:
#             new_text = dialog.get_text()
#             if new_text != text:
#                 model.setData(index, new_text, Qt.EditRole)

#         # dialog = QDialog(self.parent())
#         # dialog.setWindowTitle("Просмотр текста" if self._readonly else "Редактирование текста")

#         # layout = QVBoxLayout(dialog)
#         # text_edit = QTextEdit()
#         # text_edit.setPlainText(text)
#         # if self._readonly:
#         #     text_edit.setReadOnly(True)

#         # layout.addWidget(text_edit)

#         # btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
#         # btn_box.accepted.connect(dialog.accept)
#         # btn_box.rejected.connect(dialog.reject)
#         # layout.addWidget(btn_box)

#         # if dialog.exec() == QDialog.Accepted:
#         #     new_text = text_edit.toPlainText()
#         #     if new_text != text:
#         #         model.setData(index, new_text, Qt.EditRole)
    
#     @AppLogger.get_instance(
#         name='TextPopupDelegate',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def set_readonly(self, readonly):
#         """Устанавливает режим только для просмотра."""
#         self._readonly = readonly
#         if readonly:
#             self._hide_button()
    
#     @AppLogger.get_instance(
#         name='TextPopupDelegate',
#         # share_file_with = 'system',
#         enable_file_logging = 'system',
#         use_name_in_filename = False, # 'system'
#     ).log_execution_time(
#         level=AppLogger._parse_log_level('DEBUG')
#     )
#     def createEditor(self, parent, option, index):
#         # Не создаём редактор, вместо этого открываем попап (при двойном клике)
#         return None

# class TextPopupDelegate(QStyledItemDelegate):
#     """
#     Делегат для ячеек с многострочным текстом.
#     При наведении мыши показывает маленькую кнопку (один общий QPushButton на всю таблицу),
#     по нажатию открывает диалог с QTextEdit для удобного редактирования с переносами строк.
#     В режиме только для чтения диалог открывается без возможности редактирования.
#     """
#     _shared_button = None        # одна кнопка на все экземпляры
#     _current_delegate = None     # делегат, который сейчас показывает кнопку

#     @classmethod
#     def _get_shared_button(cls, parent):
#         """Создаёт общую кнопку, если её ещё нет."""
#         if cls._shared_button is None:
#             cls._shared_button = QPushButton("...", parent)
#             cls._shared_button.setFixedSize(20, 20)
#             cls._shared_button.setCursor(Qt.PointingHandCursor)
#             cls._shared_button.hide()
#         return cls._shared_button

#     def __init__(
#         self,
#         parent=None,
#         readonly=False,
#         get_completion_list=None,
#     ):
#         super().__init__(parent)
#         self._readonly = readonly
#         self._get_completion_list = get_completion_list
#         self._current_row = -1
#         self._current_col = -1

#         if parent:
#             parent.setMouseTracking(True)
#             parent.installEventFilter(self)

#     def _show_button(self, index):
#         """Показывает кнопку над указанной ячейкой."""
#         # if self._readonly or not index.isValid():
#         if  not index.isValid():
#             return

#         viewport = self.parent().viewport()
#         btn = self._get_shared_button(viewport)

#         # Обновляем родителя (на случай, если viewport изменился)
#         btn.setParent(viewport)

#         # Позиционируем кнопку
#         rect = self.parent().visualRect(index)
#         btn_rect = QRect(
#             rect.right() - 22,
#             rect.top() + (rect.height() - 20) // 2,
#             20, 20
#         )
#         btn.setGeometry(btn_rect)

#         # Переназначаем сигнал (отключаем старые, чтобы не было дублей)
#         try:
#             btn.clicked.disconnect()
#         except TypeError:
#             pass
#         btn.clicked.connect(self._on_button_clicked)

#         btn.show()
#         btn.raise_()

#         self._current_row = index.row()
#         self._current_col = index.column()
#         self.__class__._current_delegate = self

#     def _hide_button(self):
#         """Скрывает общую кнопку."""
#         if self.__class__._shared_button is not None:
#             self.__class__._shared_button.hide()
#         self._current_row = -1
#         self._current_col = -1
#         self.__class__._current_delegate = None

#     def _on_button_clicked(self):
#         """Обработчик клика по кнопке."""
#         if self._current_row >= 0 and self._current_col >= 0:
#             model = self.parent().model()
#             idx = model.index(self._current_row, self._current_col)
#             if idx.isValid():
#                 self._open_popup(model, idx)

#     def editorEvent(self, event, model, option, index):
#         """Обрабатывает события мыши для показа/скрытия кнопки."""
#         # Обработка движения мыши – обновляем hover и показываем кнопку
#         if event.type() == QEvent.MouseMove:
#             if index.isValid():
#                 if (index.row(), index.column()) != (self._current_row, self._current_col):
#                     # Скрываем кнопку (через класс, чтобы все делегаты видели)
#                     if self.__class__._shared_button:
#                         self.__class__._shared_button.hide()
#                     self.__class__._current_delegate = None
#                     self._current_row = -1
#                     self._current_col = -1
#                     # Показываем кнопку для новой ячейки
#                     self._show_button(index)
#             else:
#                 self._hide_button()
#             return False

#         # Обработка двойного клика – открываем диалог (только в режиме редактирования)
#         if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
#             if not self._readonly:
#                 self._open_popup(model, index)
#                 return True
#             return False

#         # Клик по кнопке уже обработан отдельно через сигнал
#         return super().editorEvent(event, model, option, index)

#     def eventFilter(self, obj, event):

#         # Обработка выхода мыши из таблицы
#         if obj == self.parent() and event.type() == QEvent.Leave:
#             self._hide_button()
#             return False

#         # Обработка движения мыши по таблице (для скрытия кнопки над чужими делегатами)
#         if obj == self.parent() and event.type() == QEvent.MouseMove:
#             # Если кнопка не видна, можно не проверять
#             if self.__class__._shared_button and self.__class__._shared_button.isVisible():
#                 pos = event.pos()
#                 index = self.parent().indexAt(pos)
#                 if index.isValid():
#                     delegate = self.parent().itemDelegateForColumn(index.column())
#                     if not isinstance(delegate, TextPopupDelegate):
#                         self._hide_button()
#                 else:
#                     self._hide_button()
#             return False

#         return super().eventFilter(obj, event)
#         # """При выходе мыши из таблицы скрываем кнопку."""
#         # if obj == self.parent() and event.type() == QEvent.Leave:
#         #     self._hide_button()
#         # return super().eventFilter(obj, event)

#     def paint(self, painter, option, index):
#         """Стандартная отрисовка без рисования кнопки (кнопка – реальный виджет)."""
#         super().paint(painter, option, index)

#     def set_readonly(self, readonly):
#         """Устанавливает режим только для просмотра."""
#         self._readonly = readonly
#         if readonly:
#             self._hide_button()

#     def _open_popup(self, model, index):
#         """Открывает диалог просмотра/редактирования текста."""
#         value = model.data(index, Qt.EditRole)
#         text = str(value) if value is not None else ""

#         # Получаем список вариантов для автодополнения
#         completion_list = self._get_completion_list() if self._get_completion_list else []

#         dialog = TextEditDialog(self.parent(), text, self._readonly, completion_list)
#         if dialog.exec() == QDialog.Accepted:
#             new_text = dialog.get_text()
#             if new_text != text:
#                 model.setData(index, new_text, Qt.EditRole)

#     def createEditor(self, parent, option, index):
#         # Не создаём редактор, вместо этого открываем попап (при двойном клике)
#         return None

class TextPopupDelegate(QStyledItemDelegate):
    """
    Делегат для ячеек с многострочным текстом.
    При наведении мыши показывает маленькую кнопку (один общий QPushButton на всю таблицу),
    по нажатию открывает диалог с QTextEdit для удобного редактирования с переносами строк.
    В режиме только для чтения диалог открывается без возможности редактирования.
    """
    _shared_button = None        # одна кнопка на все экземпляры
    _current_delegate = None     # делегат, который сейчас показывает кнопку
    _global_filter_installed = False  # флаг, что глобальный фильтр установлен

    @classmethod
    def _get_shared_button(cls, parent):
        """Создаёт общую кнопку, если её ещё нет."""
        if cls._shared_button is None:
            cls._shared_button = QPushButton("...", parent)
            cls._shared_button.setFixedSize(20, 20)
            cls._shared_button.setCursor(Qt.PointingHandCursor)
            cls._shared_button.hide()
        return cls._shared_button

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        parent=None,
        readonly=False,
        get_completion_list=None,
    ):
        super().__init__(parent)
        self._readonly = readonly
        self._get_completion_list = get_completion_list
        self._current_row = -1
        self._current_col = -1

        if parent:
            parent.setMouseTracking(True)
            parent.installEventFilter(self)
            self._install_global_hover_monitor(parent)

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _install_global_hover_monitor(self, table):
        """Устанавливает фильтр событий на viewport таблицы для отслеживания движения мыши."""
        if self.__class__._global_filter_installed:
            return
        viewport = table.viewport()
        viewport.installEventFilter(self)
        self.__class__._global_filter_installed = True

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _show_button(self, index):
        """Показывает кнопку над указанной ячейкой."""
        if not index.isValid():
            return

        viewport = self.parent().viewport()
        btn = self._get_shared_button(viewport)

        # Обновляем родителя (на случай, если viewport изменился)
        btn.setParent(viewport)

        # Позиционируем кнопку
        rect = self.parent().visualRect(index)
        btn_rect = QRect(
            rect.right() - 22,
            rect.top() + (rect.height() - 20) // 2,
            20, 20
        )
        btn.setGeometry(btn_rect)
        
        # Переназначаем сигнал (отключаем старые, чтобы не было дублей)
        try:
            btn.clicked.disconnect()
        except TypeError:
            pass

        btn.clicked.connect(self._on_button_clicked)

        btn.show()
        btn.raise_()

        self._current_row = index.row()
        self._current_col = index.column()
        self.__class__._current_delegate = self

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _hide_button(self):
        """Скрывает общую кнопку."""
        if self.__class__._shared_button is not None:
            self.__class__._shared_button.hide()
        self._current_row = -1
        self._current_col = -1
        self.__class__._current_delegate = None

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_button_clicked(self):
        """Обработчик клика по кнопке."""
        if self._current_row >= 0 and self._current_col >= 0:
            model = self.parent().model()
            idx = model.index(self._current_row, self._current_col)
            if idx.isValid():
                self._open_popup(model, idx)

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def editorEvent(self, event, model, option, index):
        """Обрабатывает события мыши для показа/скрытия кнопки."""
        # Обработка движения мыши – обновляем hover и показываем кнопку
        if event.type() == QEvent.MouseMove:
            if index.isValid():
                if (index.row(), index.column()) != (self._current_row, self._current_col):
                    # Скрываем кнопку (через класс, чтобы все делегаты видели)
                    if self.__class__._shared_button:
                        self.__class__._shared_button.hide()
                    self.__class__._current_delegate = None
                    self._current_row = -1
                    self._current_col = -1
                    # Показываем кнопку для новой ячейки
                    self._show_button(index)
            else:
                self._hide_button()
            return False

        # Обработка двойного клика – открываем диалог (только в режиме редактирования)
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            if not self._readonly:
                self._open_popup(model, index)
                return True
            return False

        return super().editorEvent(event, model, option, index)

    # @AppLogger.get_instance(
    #     name='TextPopupDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def eventFilter(self, obj, event):
        # Обработка выхода мыши из таблицы
        if obj == self.parent() and event.type() == QEvent.Leave:
            self._hide_button()
            return False

        # Обработка движения мыши по viewport (глобальный мониторинг)
        if obj == self.parent().viewport() and event.type() == QEvent.MouseMove:
            pos = event.pos()
            index = self.parent().indexAt(pos)
            if index.isValid():
                delegate = self.parent().itemDelegateForColumn(index.column())
                # Если делегат под курсором не TextPopupDelegate – скрываем кнопку
                if not isinstance(delegate, TextPopupDelegate):
                    self._hide_button()
            else:
                self._hide_button()
            return False

        return super().eventFilter(obj, event)

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def paint(self, painter, option, index):
        """Стандартная отрисовка без рисования кнопки (кнопка – реальный виджет)."""
        super().paint(painter, option, index)

    @AppLogger.get_instance(
        name='TextPopupDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_readonly(self, readonly):
        """Устанавливает режим только для просмотра."""
        self._readonly = readonly
        if readonly:
            self._hide_button()

    def _open_popup(self, model, index):
        """Открывает диалог просмотра/редактирования текста."""
        value = model.data(index, Qt.EditRole)
        text = str(value) if value is not None else ""

        # Получаем список вариантов для автодополнения
        completion_list = self._get_completion_list() if self._get_completion_list else []

        dialog = TextEditDialog(self.parent(), text, self._readonly, completion_list)
        if dialog.exec() == QDialog.Accepted:
            new_text = dialog.get_text()
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
        install_standard_context_menu(editor, menu_type='line')
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
        editor = QDateTimeEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("yyyy-MM-dd")
        editor.setSpecialValueText("")          # пустая строка для отображения, если дата не задана
        # editor.setDate(QDate.currentDate())     # начальная дата (не обязательна, но для визуала)
        editor.setDateTime(QDateTime())                 # невалидная дата → будет показан specialValueText
        install_standard_context_menu(editor, menu_type='date')
        # Устанавливаем фильтр событий для перехвата клавиши Delete
        editor.installEventFilter(self)

        return editor
    
    # @AppLogger.get_instance(
    #     name='DateDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def eventFilter(self, obj, event):
        """Перехватывает клавишу Delete для очистки даты."""
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            if isinstance(obj, QDateTimeEdit):
                obj.setDateTime(QDateTime())   # невалидная дата
                # obj.update()
                # Немедленно завершаем редактирование, чтобы сохранить None
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QStyledItemDelegate.NoHint)

                return True
        return super().eventFilter(obj, event)
    
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

        if value is None:
            editor.setDateTime(QDateTime())         
        elif isinstance(value, date):
            editor.setDate(QDate(value.year, value.month, value.day))
        else:
            editor.setDateTime(QDateTime())
        # elif isinstance(value, QDate):
            # editor.setDate(value)
        # else:
        #     editor.setDate(QDate.currentDate())

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
        else:
            # Если дата не задана (пустое поле), сохраняем None
            model.setData(index, None, Qt.EditRole)

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
        editor = QDateTimeEdit(parent)
        editor.setDisplayFormat("HH:mm")
        editor.setSpecialValueText("")          # пустая строка для отображения, если время не задано
        # editor.setTime(QTime.currentTime())     # начальное время
        editor.setDateTime(QDateTime())                 # невалидное время
        install_standard_context_menu(editor)
        # Устанавливаем фильтр событий для перехвата клавиши Delete
        editor.installEventFilter(self)
        
        return editor

    # @AppLogger.get_instance(
    #     name='TimeDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def eventFilter(self, obj, event):
        """Перехватывает клавишу Delete для очистки времени."""
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            if isinstance(obj, QDateTimeEdit):
                obj.setTime(QDateTime())   # невалидное время
                # obj.update()
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, QStyledItemDelegate.NoHint)

                return True
        return super().eventFilter(obj, event)
    
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

        if value is None:
            editor.setDateTime(QDateTime())          # невалидное время
        elif isinstance(value, time):
            editor.setTime(QTime(value.hour, value.minute))
        else:
            editor.setDateTime(QDateTime())
        # elif isinstance(value, QTime):
        #     editor.setTime(value)
        # else:
        #     editor.setTime(QTime.currentTime())

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
        else:
            model.setData(index, None, Qt.EditRole)

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


class DatePickerDelegate(QStyledItemDelegate):
    """Делегат для даты с текстовым полем и кнопкой календаря."""

    @AppLogger.get_instance(
        name='DatePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, config: Dict[str, Any] = None):
        super().__init__(parent)
        self.config = config  # сохраняем конфигурацию поля для передачи в DateEditWidget

    @AppLogger.get_instance(
        name='DatePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        widget = DateEditWidget(parent, config=self.config)
        # install_standard_context_menu(widget.line_edit)   # добавить
        widget.dateChanged.connect(lambda: self.commitData.emit(widget))
        return widget

    @AppLogger.get_instance(
        name='DatePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, date):
            editor.set_date(value)
        else:
            editor.set_date(None)

    @AppLogger.get_instance(
        name='DatePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        val = editor.get_date()
        model.setData(index, val, Qt.EditRole)

    @AppLogger.get_instance(
        name='DatePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class TimePickerDelegate(QStyledItemDelegate):
    """Делегат для времени с текстовым полем и кнопкой выбора."""
   
    @AppLogger.get_instance(
        name='TimePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, config: Dict[str, Any] = None):
        super().__init__(parent)
        self.config = config

    @AppLogger.get_instance(
        name='TimePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        widget = TimeEditWidget(parent, config=self.config)
        # install_standard_context_menu(widget.line_edit)   # добавить
        widget.timeChanged.connect(lambda: self.commitData.emit(widget))
        return widget

    @AppLogger.get_instance(
        name='TimePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if isinstance(value, time):
            editor.set_time(value)
        else:
            editor.set_time(None)

    @AppLogger.get_instance(
        name='TimePickerDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        val = editor.get_time()
        model.setData(index, val, Qt.EditRole)

    @AppLogger.get_instance(
        name='TimePickerDelegate',
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
        install_standard_context_menu(editor, menu_type='line')

        # Выравнивание текста по верхнему краю (и левому)
        editor.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        values = self._get_values()
        if values:
            completer = QCompleter(values)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)   # поиск по подстроке
            # Стилизация выпадающего списка автодополнения (подсветка при наведении)
            completer.popup().setStyleSheet("""
                QListView::item:hover {
                    background-color: #d0e0ff;
                }
            """)
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