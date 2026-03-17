# -*- coding: utf-8 -*-
"""
Кастомный QTableView с заголовком, поддерживающим фильтрацию и сортировку.
Заголовок (QHeaderView) переопределён для показа меню при клике.
"""
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction


class FilterHeaderView(QHeaderView):
    """
    Заголовок таблицы, который при клике правой кнопкой мыши показывает меню
    с опциями сортировки и фильтрации.
    """
    filter_requested = Signal(int, str, object)  # индекс колонки, оператор, значение

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

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

        # Фильтр по значению (простой диалог)
        filter_action = QAction("Фильтр...", self)
        filter_action.triggered.connect(lambda: self._request_filter(logical_index))
        menu.addAction(filter_action)

        # Сброс фильтра (будет реализован через модель)
        clear_filter = QAction("Сбросить фильтр", self)
        clear_filter.triggered.connect(lambda: self._clear_filter(logical_index))
        menu.addAction(clear_filter)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _request_filter(self, logical_index):
        """Запрашивает ввод значения фильтра."""
        # Здесь можно открыть диалог, но для простоты используем input dialog
        from PySide6.QtWidgets import QInputDialog
        value, ok = QInputDialog.getText(self, "Фильтр", f"Введите значение для фильтрации (столбец {logical_index}):")
        if ok and value:
            self.filter_requested.emit(logical_index, 'contains', value)

    def _clear_filter(self, logical_index):
        """Сброс фильтра для колонки."""
        self.filter_requested.emit(logical_index, 'clear', None)


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