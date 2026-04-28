# interfaces/gui/gui_window/widgets/filter_table_view.py

"""
Кастомный QTableView с заголовком, поддерживающим фильтрацию и сортировку.
Заголовок (QHeaderView) переопределён для показа меню при клике.
"""

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.filter_column import FilterColumnDialog

from PySide6.QtWidgets import (
    QTableView, QHeaderView, QMenu, 
    QDialog, QListWidget, QListWidgetItem, 
    QVBoxLayout, QHBoxLayout, QPushButton,
    QInputDialog
)

from PySide6.QtCore import Qt, Signal#, Slot
from PySide6.QtGui import QAction


class FilterHeaderView(QHeaderView):
    """
    Заголовок таблицы, который при клике правой кнопкой мыши показывает меню
    с опциями сортировки и фильтрации.
    """

    # filter_requested = Signal(int, str, object)  # индекс колонки, оператор, значение
    filter_requested = Signal(int, str, object)  # column, logic, conditions
    filter_clear_requested = Signal(int)         # сброс фильтра для колонки
    
    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, orientation, parent=None):
        """
        Инициализирует заголовок таблицы.

        :param orientation: ориентация заголовка (Qt.Orientation.Horizontal или Qt.Orientation.Vertical)
        :type orientation: Qt.Orientation
        :param parent: родительский объект (необязательный)
        :type parent: QObject
        """

        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._get_unique_values_func = None   # функция для получения уникальных значений 

        self._checkbox_column_visible = False   # по умолчанию скрыт

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_column_visible(self, visible: bool):
        """Устанавливает, виден ли столбец чекбоксов."""
        self._checkbox_column_visible = visible

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_header_menu(self, toggle_callback):
        """Устанавливает callback для управления всеми чекбоксами."""
        self._checkbox_toggle_callback = toggle_callback



 
    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _create_checkbox_menu_item( 
        self, 
        name:str, 
        thec:bool
    ):   
        """
        Создает пункт меню для чекбокса со значением thec.

        :param name: имя пункта меню
        :type name: str
        :param thec: значение чекбокса
        :type thec: bool
        :return: пункт меню
        :rtype: QAction
        """
        select_ = QAction(name, self)
        select_.triggered.connect(
            lambda: self._checkbox_toggle_callback(thec)
        )

        return select_
    
    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_get_unique_values_func(self, func):
        """
        Устанавливает функцию, которая будет использоваться для получения списка уникальных значений
        для столбца. Функция должна возвращать список уникальных значений в виде строкового представления.
        """
        self._get_unique_values_func = func

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_context_menu(self, pos):
        """Показывает контекстное меню для секции заголовка."""

        logical_index = self.logicalIndexAt(pos)

        if logical_index == -1:
            return

        # ----- Если это столбец чекбоксов (индекс 0) и callback задан -----
        if (
            logical_index == 0
        ) and (
            hasattr(self, '_checkbox_toggle_callback') # callback задан
        ) and (
            self._checkbox_column_visible # столбец виден
        ):
            menu = QMenu(self)

            for name, thec in [ # True - выбрать, False - снять
                ("Выбрать все", True), 
                ("Снять все", False),
            ]:
                menu.addAction(
                    self._create_checkbox_menu_item ( 
                        name, 
                        thec 
                    )    
                )

            menu.exec(
                self.viewport().mapToGlobal(pos)
            )

            return

        # ----- Обычное меню для остальных столбцов -----
        menu = QMenu(self)

        # Сортировка
        sort_asc = QAction("Сортировать по возрастанию", self)
        sort_asc.triggered.connect(lambda: self.parent().sortByColumn(logical_index, Qt.AscendingOrder))
        menu.addAction(sort_asc)

        sort_desc = QAction("Сортировать по убыванию", self)
        sort_desc.triggered.connect(lambda: self.parent().sortByColumn(logical_index, Qt.DescendingOrder))
        menu.addAction(sort_desc)

        menu.addSeparator()

        # Сброс сортировки
        clear_sort = QAction("Сбросить сортировку", self)
        clear_sort.triggered.connect(lambda: self.parent().sortByColumn(-1, Qt.AscendingOrder))
        menu.addAction(clear_sort)

        menu.addSeparator()

        # Пункт настройки фильтра
        filter_action = QAction("Настроить фильтр...", self)
        filter_action.triggered.connect(lambda: self._request_advanced_filter(logical_index))
        menu.addAction(filter_action)

        # Сброс фильтра для колонки
        clear_filter = QAction("Сбросить фильтр", self)
        clear_filter.triggered.connect(lambda: self.filter_clear_requested.emit(logical_index))
        menu.addAction(clear_filter)

        menu.exec(self.viewport().mapToGlobal(pos))

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _request_advanced_filter(self, logical_index: int):
        """Открывает диалог расширенной фильтрации для столбца с поддержкой множественных условий."""
        
        # Получаем уникальные значения для столбца (для оператора 'in')
        if self._get_unique_values_func:
            values = self._get_unique_values_func(logical_index)
        else:
            values = []

        # Получаем заголовок столбца для отображения в диалоге
        column_title = self.model().headerData(logical_index, Qt.Horizontal, Qt.DisplayRole)
        if not column_title:
            column_title = f"Столбец {logical_index}"

        # Получаем текущий фильтр для этого столбца (если есть)
        model = self.parent().model()
        current_logic = None
        current_conditions = []

        if (
            hasattr(self.parent(), 'model')
            and hasattr(model, '_column_filters')
            and logical_index in model._column_filters
        ):
            current_filter = model._column_filters[logical_index]
            current_logic = current_filter.get('logic')
            current_conditions = current_filter.get('conditions', [])

        # Определяем тип данных столбца
        column_type = str
        if hasattr(self.model(), 'column_type'):
            column_type = self.model().column_type(logical_index)
        elif self.model().rowCount() > 0:
            idx = self.model().index(0, logical_index)
            data = self.model().data(idx, Qt.EditRole)
            if data is not None:
                column_type = type(data)

        # Создаём диалог фильтрации (новый, с поддержкой множественных условий)
        # from .filter_column import FilterColumnDialog
        dialog = FilterColumnDialog(
            column_title=column_title,
            column_type=column_type,
            current_logic=current_logic,
            current_conditions=current_conditions,
            unique_values=values,
            parent=self
        )

        if dialog.exec() == QDialog.Accepted:
            logic, conditions = dialog.get_filter()
            # Испускаем сигнал с логикой и списком условий
            self.filter_requested.emit(logical_index, logic, conditions)

    # @AppLogger.get_instance( 
    #     name = 'FilterHeaderView',
    #     enable_file_logging = 'system',
    #    use_name_in_filename =  False, #  True, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _show_values_dialog(self, logical_index):
    #     """
    #     Открывает диалог выбора значений для фильтрации в таблице.

    #     :param logical_index: индекс столбца, для которого необходимо отобразить фильтр
    #     :type logical_index: int
    #     """
    #     if not self._get_unique_values_func:
    #         return
        
    #     values = self._get_unique_values_func(logical_index)

    #     dialog = QDialog(self)
    #     dialog.setWindowTitle("Выбор значений")

    #     layout = QVBoxLayout(dialog)

    #     list_widget = QListWidget()
    #     list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

    #     for val in values:
    #         item = QListWidgetItem(str(val))
    #         item.setData(Qt.UserRole, val)
    #         list_widget.addItem(item)
            
    #     layout.addWidget(list_widget)

    #     btn_layout = QHBoxLayout()

    #     ok_btn = QPushButton("OK")
    #     ok_btn.clicked.connect(dialog.accept)
    #     btn_layout.addWidget(ok_btn)

    #     cancel_btn = QPushButton("Отмена")
    #     cancel_btn.clicked.connect(dialog.reject)
    #     btn_layout.addWidget(cancel_btn)
       
        
    #     layout.addLayout(btn_layout)

    #     if dialog.exec() == QDialog.Accepted:
    #         selected = []
    #         for item in list_widget.selectedItems():
    #             selected.append(item.data(Qt.UserRole))
                
    #         self.filter_requested.emit(logical_index, 'in', selected, None)

    # def _populate_values_menu(self, values_menu, logical_index):
    #     """Заполняет подменю уникальными значениями с чекбоксами."""
    #     values_menu.clear()
    #     if not self._get_unique_values_func:
    #         return
    #     values = self._get_unique_values_func(logical_index)
    #     # Создаём QAction для каждого значения
    #     for val in values:
    #         action = QAction(str(val), values_menu)
    #         action.setCheckable(True)
    #         # Сохраняем значение как data
    #         action.setData(val)
    #         values_menu.addAction(action)
    #     # Добавляем кнопки OK/Cancel или применяем при закрытии
    #     # Проще: при выборе элемента применяем фильтр сразу, но это неудобно для множественного выбора.
    #     # Лучше добавить кнопку "Применить" и собирать выбранные значения.
    #     # Для простоты пока сделаем, что выбор элемента сразу отправляет фильтр с этим одним значением.
    #     # Позже можно заменить на диалог.
    #     # Но для полноты реализуем диалог.
    #     # Вместо подменю лучше открыть диалог.
    #     # Переделаем: вместо подменю будем открывать диалог.
    #     # Пока просто вызовем диалог.

    # def _request_filter_values(self, logical_index):
    #     """Открывает диалог выбора значений."""
    #     if not self._get_unique_values_func:
    #         return
    #     values = self._get_unique_values_func(logical_index)
    #     dialog = FilterValuesDialog(self, values)
    #     if dialog.exec() == QDialog.Accepted:
    #         selected = dialog.get_selected_values()
    #         self.filter_requested.emit(logical_index, 'in', selected)

    # @AppLogger.get_instance( 
    #     name = 'FilterHeaderView',
    #     enable_file_logging = 'system',
    #    use_name_in_filename =  False, #  True, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _request_filter(self, logical_index):
    #     """Запрашивает ввод значения фильтра."""
    #     # Здесь можно открыть диалог, но для простоты используем input dialog
    #     value, ok = QInputDialog.getText(self, "Фильтр", f"Введите значение для фильтрации (столбец {logical_index}):")
    #     if ok and value:
    #         self.filter_requested.emit(logical_index, 'contains', value)

    # def _clear_filter(self, logical_index):
    #     """Сброс фильтра для колонки."""
    #     self.filter_requested.emit(logical_index, 'clear', None)


class FilterTableView(QTableView):
    """
    Таблица с поддержкой фильтрации через заголовок.
    Использует FilterHeaderView.
    """

    @AppLogger.get_instance( 
        name = 'FilterTableView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSortingEnabled(True)

        header = FilterHeaderView(Qt.Orientation.Horizontal, self)

        self.setHorizontalHeader(header)

        header.filter_requested.connect(self.on_filter_requested)

        # self.horizontalHeader().setVisible(True)

    # @AppLogger.get_instance( 
    #     name = 'FilterTableView',
    #     enable_file_logging = 'system',
    #    use_name_in_filename =  False, #  True, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def showEvent(self, event):
    #     """При каждом отображении таблицы принудительно показываем заголовок."""
    #     super().showEvent(event)
    #     self.horizontalHeader().setVisible(True)

    @AppLogger.get_instance( 
        name = 'FilterTableView',
        enable_file_logging = 'system',
       use_name_in_filename =  False, #  True, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_filter_requested(self, column, operator, value, value2=None):
        """
        Обрабатывает сигнал фильтрации.
        Должен быть переопределён или связан с моделью.
        """
        # В базовом классе просто передаём сигнал дальше
        pass