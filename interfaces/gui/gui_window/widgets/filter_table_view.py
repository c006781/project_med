# -*- coding: utf-8 -*-
"""
Кастомный QTableView с заголовком, поддерживающим фильтрацию и сортировку.
Заголовок (QHeaderView) переопределён для показа меню при клике.
"""
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu, QDialog
from PySide6.QtCore import Qt, Signal#, Slot
from PySide6.QtGui import QAction


class FilterHeaderView(QHeaderView):
    """
    Заголовок таблицы, который при клике правой кнопкой мыши показывает меню
    с опциями сортировки и фильтрации.
    """
    filter_requested = Signal(int, str, object)  # индекс колонки, оператор, значение
    filter_clear_requested = Signal(int)         # сброс фильтра для колонки

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

    def set_get_unique_values_func(self, func):
        """
        Устанавливает функцию, которая будет использоваться для получения списка уникальных значений
        для столбца. Функция должна возвращать список уникальных значений в виде строкового представления.
        """
        self._get_unique_values_func = func

    def _show_context_menu(self, pos):
        """Показывает контекстное меню для секции заголовка."""
        logical_index = self.logicalIndexAt(pos)

        if logical_index == -1:
            return

        menu = QMenu(self)

        # Сортировка
        sort_asc = QAction("Сортировать по возрастанию", self)
        sort_asc.triggered.connect(lambda: self.parent().sortByColumn(logical_index, Qt.SortOrder.AscendingOrder))
        menu.addAction(sort_asc)

        sort_desc = QAction("Сортировать по убыванию", self)
        sort_desc.triggered.connect(lambda: self.parent().sortByColumn(logical_index, Qt.SortOrder.DescendingOrder))
        menu.addAction(sort_desc)

        menu.addSeparator()

        # Сброс сортировки
        clear_sort = QAction("Сбросить сортировку", self)
        clear_sort.triggered.connect(lambda: self.parent().sortByColumn(-1, Qt.SortOrder.AscendingOrder))
        menu.addAction(clear_sort)

        menu.addSeparator()

        # # Фильтр по значению (простой диалог)
        # filter_action = QAction("Фильтр...", self)
        # filter_action.triggered.connect(lambda: self._request_filter(logical_index))
        # menu.addAction(filter_action)

        # Фильтрация по значениям
        # if self._get_unique_values_func:
        #     values_menu = menu.addMenu("Выбрать из значений...")
        #     # Не будем сразу заполнять, чтобы не загружать данные при создании меню
        #     values_menu.aboutToShow.connect(lambda: self._populate_values_menu(values_menu, logical_index))
        # else:
        #     # fallback: простой диалог
        #     filter_action = menu.addAction("Фильтр...")
        #     filter_action.triggered.connect(lambda: self._request_filter(logical_index))

        if self._get_unique_values_func:
            values_action = menu.addAction("Выбрать из значений...")
            values_action.triggered.connect(lambda: self._show_values_dialog(logical_index))
        else:
            filter_action = menu.addAction("Фильтр...")
            filter_action.triggered.connect(lambda: self._request_filter(logical_index))


        # Сброс фильтра для колонки
        clear_filter = QAction("Сбросить фильтр", self)
        clear_filter.triggered.connect(lambda: self.filter_clear_requested.emit(logical_index))
        menu.addAction(clear_filter)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _show_values_dialog(self, logical_index):
        """
        Открывает диалог выбора значений для фильтрации в таблице.

        :param logical_index: индекс столбца, для которого необходимо отобразить фильтр
        :type logical_index: int
        """
        if not self._get_unique_values_func:
            return
        values = self._get_unique_values_func(logical_index)
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QHBoxLayout, QPushButton
        dialog = QDialog(self)
        dialog.setWindowTitle("Выбор значений")
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        for val in values:
            item = QListWidgetItem(str(val))
            item.setData(Qt.UserRole, val)
            list_widget.addItem(item)
        layout.addWidget(list_widget)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Отмена")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        if dialog.exec() == QDialog.Accepted:
            selected = []
            for item in list_widget.selectedItems():
                selected.append(item.data(Qt.UserRole))
            self.filter_requested.emit(logical_index, 'in', selected)

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

    def _request_filter(self, logical_index):
        """Запрашивает ввод значения фильтра."""
        # Здесь можно открыть диалог, но для простоты используем input dialog
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getText(self, "Фильтр", f"Введите значение для фильтрации (столбец {logical_index}):")
        if ok and value:
            self.filter_requested.emit(logical_index, 'contains', value)

    # def _clear_filter(self, logical_index):
    #     """Сброс фильтра для колонки."""
    #     self.filter_requested.emit(logical_index, 'clear', None)


class FilterTableView(QTableView):
    """
    Таблица с поддержкой фильтрации через заголовок.
    Использует FilterHeaderView.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortingEnabled(True)
        header = FilterHeaderView(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(header)
        header.filter_requested.connect(self.on_filter_requested)

    def on_filter_requested(self, column, operator, value):
        """
        Обрабатывает сигнал фильтрации.
        Должен быть переопределён или связан с моделью.
        """
        # В базовом классе просто передаём сигнал дальше
        pass