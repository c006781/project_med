# interfaces/gui/gui_window/utils/gui_helpers.py

"""
Вспомогательные функции для GUI.
"""
import datetime
from typing import Dict, Any

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import (
    # QStyledItemDelegate, 
    QDateEdit, QTimeEdit, QWidget, QMenu, 
    QLineEdit, QTextEdit, 
    # QCompleter, 
    QApplication
)

from PySide6.QtCore import QDate, QTime, Qt, QPoint

# from PySide6.QtGui import QClipboard

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _install_for_date_edit(date_edit: QDateEdit):
    """Устанавливает русское контекстное меню для QDateEdit."""
    def show_context_menu(pos):
        menu = QMenu()

        # Вырезать: копирует и очищает
        cut_action = menu.addAction("Вырезать\tCtrl+X")
        cut_action.triggered.connect(_make_cut_date(date_edit))

        # Копировать
        copy_action = menu.addAction("Копировать\tCtrl+C")
        copy_action.triggered.connect(lambda: _copy_date_from_edit(date_edit))

        # Вставить
        paste_action = menu.addAction("Вставить\tCtrl+V")
        paste_action.triggered.connect(lambda: _paste_date_to_edit(date_edit))

        menu.addSeparator()

        # Удалить (очистить)
        delete_action = menu.addAction("Удалить\tDel")
        delete_action.triggered.connect(date_edit.clear)

        # Выделить всё
        select_all_action = menu.addAction("Выделить всё\tCtrl+A")
        select_all_action.triggered.connect(date_edit.selectAll)

        menu.exec(date_edit.mapToGlobal(pos))

    def _make_cut_date(editor):
        def cut():
            _copy_date_from_edit(editor)
            editor.clear()
        return cut

    date_edit.setContextMenuPolicy(Qt.CustomContextMenu)
    date_edit.customContextMenuRequested.connect(show_context_menu)

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _install_for_time_edit(time_edit: QTimeEdit):
    """Устанавливает русское контекстное меню для QTimeEdit с горячими клавишами."""
    def show_context_menu(pos):
        menu = QMenu()

        cut_action = menu.addAction("Вырезать\tCtrl+X")
        cut_action.triggered.connect(_make_cut_time(time_edit))

        copy_action = menu.addAction("Копировать\tCtrl+C")
        copy_action.triggered.connect(lambda: _copy_time_from_edit(time_edit))

        paste_action = menu.addAction("Вставить\tCtrl+V")
        paste_action.triggered.connect(lambda: _paste_time_to_edit(time_edit))

        menu.addSeparator()

        delete_action = menu.addAction("Удалить\tDel")
        delete_action.triggered.connect(time_edit.clear)

        select_all_action = menu.addAction("Выделить всё\tCtrl+A")
        select_all_action.triggered.connect(time_edit.selectAll)

        menu.exec(time_edit.mapToGlobal(pos))

    def _make_cut_time(editor):
        def cut():
            _copy_time_from_edit(editor)
            editor.clear()
        return cut

    time_edit.setContextMenuPolicy(Qt.CustomContextMenu)
    time_edit.customContextMenuRequested.connect(show_context_menu)

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _copy_date_from_edit(date_edit):
    qdate = date_edit.date()
    if qdate.isValid():
        QApplication.clipboard().setText(qdate.toString("yyyy-MM-dd"))

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _paste_date_to_edit(date_edit):
    text = QApplication.clipboard().text().strip()
    if not text:
        return
    try:
        d = datetime.date.fromisoformat(text)
        date_edit.setDate(QDate(d.year, d.month, d.day))
    except ValueError:
        pass

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _copy_time_from_edit(time_edit):
    qtime = time_edit.time()
    if qtime.isValid():
        QApplication.clipboard().setText(qtime.toString("HH:mm"))

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _paste_time_to_edit(time_edit):
    text = QApplication.clipboard().text().strip()
    if not text:
        return
    try:
        h, m = map(int, text.split(':'))
        time_edit.setTime(QTime(h, m))
    except:
        pass

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def apply_readonly_to_widgets(
    widgets: Dict[str, QWidget],
    field_configs: Dict[str, Dict[str, Any]]
) -> None:
    """
    Применяет readOnly или отключает виджеты, у которых в конфигурации
    установлен 'editable': False.
    """
    for field_name, widget in widgets.items():
        config = field_configs.get(field_name, {})
        if not config.get('editable', True):
            if hasattr(widget, 'setReadOnly'):
                widget.setReadOnly(True)
            elif hasattr(widget, 'setEnabled'):
                widget.setEnabled(False)



# """
# Утилиты для добавления стандартного контекстного меню (копировать, вставить, вырезать, выделить всё)
# в различные виджеты.
# """

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def install_standard_context_menu(widget: QWidget):
    """
    Устанавливает стандартное контекстное меню для виджета, если он поддерживает
    операции копирования/вставки/вырезания/выделения.
    Для QLineEdit и QTextEdit уже есть стандартное меню, но оно может быть отключено.
    Для кастомных виджетов (например, CompleterEdit) нужно добавить вручную.
    """
    # if hasattr(widget, 'setContextMenuPolicy'):
    #     # Включаем политику по умолчанию, если она была отключена
    #     if widget.contextMenuPolicy() == Qt.ContextMenuPolicy.NoContextMenu:
    #         widget.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
    #     # Для QLineEdit и QTextEdit ничего больше не делаем – Qt сам предоставит меню
    #     if isinstance(widget, (QLineEdit, QTextEdit)):
    #         return

    # # Для CompleterEdit обработаем его внутренний line_edit
    # if hasattr(widget, 'line_edit') and isinstance(widget.line_edit, QLineEdit):
    #     install_standard_context_menu(widget.line_edit)

    # # Для других виджетов можно добавить кастомное меню, если нужно
    # # Например, для QTableWidget – обрабатывается отдельно в таблице

    """
    Устанавливает контекстное меню с русскими командами для QLineEdit и QTextEdit.
    """
    if isinstance(widget, QLineEdit):
        _install_for_line_edit(widget)
    elif isinstance(widget, QTextEdit):
        _install_for_text_edit(widget)
    elif isinstance(widget, QDateEdit):
        _install_for_date_edit(widget)
    elif isinstance(widget, QTimeEdit):
        _install_for_time_edit(widget)
    # Для других виджетов (например, CompleterEdit) – обрабатываем их внутренние поля
    elif hasattr(widget, 'line_edit') and isinstance(widget.line_edit, QLineEdit):
        install_standard_context_menu(widget.line_edit)

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _install_for_line_edit(line_edit: QLineEdit):
    """Устанавливает кастомное контекстное меню для QLineEdit."""
    def show_context_menu(pos: QPoint):
        menu = QMenu()
        
        # Копировать
        copy_action = menu.addAction("Копировать")
        copy_action.setEnabled(line_edit.hasSelectedText())
        copy_action.triggered.connect(line_edit.copy)
        
        # Вырезать
        cut_action = menu.addAction("Вырезать")
        cut_action.setEnabled(line_edit.hasSelectedText() and not line_edit.isReadOnly())
        cut_action.triggered.connect(line_edit.cut)
        
        # Вставить
        paste_action = menu.addAction("Вставить")
        has_text = bool(QApplication.clipboard().text())
        paste_action.setEnabled(not line_edit.isReadOnly() and has_text)
        paste_action.triggered.connect(line_edit.paste)
        
        menu.addSeparator()
        
        # Выделить всё
        select_all_action = menu.addAction("Выделить всё")
        select_all_action.triggered.connect(line_edit.selectAll)
        
        menu.exec(line_edit.mapToGlobal(pos))
    
    line_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    line_edit.customContextMenuRequested.connect(show_context_menu)

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _install_for_text_edit(text_edit: QTextEdit):
    """Устанавливает кастомное контекстное меню для QTextEdit."""
    def show_context_menu(pos: QPoint):
        menu = QMenu()
        
        copy_action = menu.addAction("Копировать")
        copy_action.setEnabled(text_edit.textCursor().hasSelection())
        copy_action.triggered.connect(text_edit.copy)
        
        cut_action = menu.addAction("Вырезать")
        cut_action.setEnabled(text_edit.textCursor().hasSelection() and not text_edit.isReadOnly())
        cut_action.triggered.connect(text_edit.cut)
        
        paste_action = menu.addAction("Вставить")
        has_text = bool(QApplication.clipboard().text())
        paste_action.setEnabled(not text_edit.isReadOnly() and has_text)
        paste_action.triggered.connect(text_edit.paste)
        
        menu.addSeparator()
        
        select_all_action = menu.addAction("Выделить всё")
        select_all_action.triggered.connect(text_edit.selectAll)
        
        menu.exec(text_edit.mapToGlobal(pos))
    
    text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    text_edit.customContextMenuRequested.connect(show_context_menu)

@AppLogger.get_instance(
    name='gui_helpers.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def add_copy_paste_to_table(table_widget):
    """
    Добавляет контекстное меню для таблицы (QTableView или QTableWidget)
    с русским пунктом «Копировать». Копирует выделенные ячейки в буфер обмена
    в формате табуляция/перевод строки.
    """
    def copy_selection():
        selection_model = table_widget.selectionModel()
        if not selection_model.hasSelection():
            return
        
        indexes = selection_model.selectedIndexes()
        if not indexes:
            return
        
        # Группируем по строкам и столбцам
        rows = sorted(set(idx.row() for idx in indexes))
        cols = sorted(set(idx.column() for idx in indexes))
        
        # Создаём матрицу данных
        data_matrix = []
        for row in rows:
            row_data = []
            for col in cols:
                # Ищем индекс для данной строки и столбца
                idx = None
                for i in indexes:
                    if i.row() == row and i.column() == col:
                        idx = i
                        break
                if idx:
                    model = table_widget.model()
                    if model:
                        value = model.data(idx, Qt.ItemDataRole.DisplayRole)
                        row_data.append(str(value) if value is not None else "")
                    else:
                        # Для QTableWidget
                        item = table_widget.item(row, col)
                        row_data.append(item.text() if item else "")
                else:
                    row_data.append("")
            data_matrix.append(row_data)
        
        # Формируем текст
        lines = ["\t".join(row_data) for row_data in data_matrix]
        text = "\n".join(lines)
        
        QApplication.clipboard().setText(text)
    
    @AppLogger.get_instance(
        name='gui_helpers.py',
        enable_file_logging = 'system',
        use_name_in_filename = False, 
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def show_context_menu(pos: QPoint):
        menu = QMenu()
        copy_action = menu.addAction("Копировать")
        copy_action.triggered.connect(copy_selection)
        menu.exec(table_widget.viewport().mapToGlobal(pos))

    table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table_widget.customContextMenuRequested.connect(show_context_menu)