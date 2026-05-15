# interfaces/gui/gui_window/mixins/ui_mixin.py
"""
Миксин для построения пользовательского интерфейса страницы списка.
"""

from interfaces.gui.gui_window.widgets.filter_column import FilterBar
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, 
    QPushButton, QLineEdit, 
    QComboBox,
)
from PySide6.QtCore import Qt, Signal



class UIMixin:
    """
    Предоставляет методы построения интерфейса.
    """

    def setup_ui(self):
        """Создаёт основной интерфейс страницы."""
        self.main_layout = QVBoxLayout(self)

        self._create_top_panel()
        self._create_table()
        self.main_layout.addWidget(self.table_view)
        self._create_filter_bar()
        # Вставляем фильтр-бар перед таблицей
        idx = self.main_layout.indexOf(self.table_view)
        if idx >= 0:
            self.main_layout.insertWidget(idx, self.filter_bar)

        self._setup_delegates()

    def _create_top_panel(self):
        top_layout = QHBoxLayout()

        # Кнопка переключения режима редактирования
        self.edit_mode_btn = QPushButton("Режим редактирования")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.toggled.connect(self.toggle_edit_mode)
        top_layout.addWidget(self.edit_mode_btn)

        # Выпадающий список действий (обычный режим)
        self.action_combo = QComboBox()
        self.action_combo.addItems(["▼ Действия с записями", "Добавить", "Редактировать", "Удалить", "Обновить"])
        self.action_combo.model().item(0).setEnabled(False)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)
        top_layout.addWidget(self.action_combo)

        # Выпадающий список inline-действий (режим редактирования)
        self.inline_action_combo = QComboBox()
        self.inline_action_combo.addItems(["▼ Действия со строками", "Добавить строку", "Удалить строку", "Отменить изменения"])
        self.inline_action_combo.model().item(0).setEnabled(False)
        self.inline_action_combo.setCurrentIndex(0)
        self.inline_action_combo.currentIndexChanged.connect(self._on_inline_action_selected)
        self.inline_action_combo.setVisible(False)
        top_layout.addWidget(self.inline_action_combo)

        # Кнопка сохранения
        self.save_changes_btn = QPushButton("Сохранить изменения")
        self.save_changes_btn.setEnabled(False)
        self.save_changes_btn.setVisible(False)
        self.save_changes_btn.clicked.connect(self.save_all_changes)
        top_layout.addWidget(self.save_changes_btn)

        # Кнопка дополнительного действия
        if getattr(self, 'action_button_text', None):
            self.action_btn = QPushButton(self.action_button_text)
            self.action_btn.clicked.connect(self._on_action_clicked)
            self.action_btn.setEnabled(False)
            top_layout.addWidget(self.action_btn)

        top_layout.addStretch()

        # Поле поиска
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self.set_global_search)
        top_layout.addWidget(self.search_edit)

        self.main_layout.addLayout(top_layout)

    def _create_table(self):
        # from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(self.table_view.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(self.table_view.SelectionMode.SingleSelection)
        self.table_view.setEditTriggers(self.table_view.NoEditTriggers)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

    def _create_filter_bar(self):
        # from interfaces.gui.gui_window.widgets.filter_column import FilterBar
        self.filter_bar = FilterBar(self)
        self.filter_bar.setVisible(False)

    def _setup_delegates(self):
        # Будет реализовано позже, аналогично DynamicListPage._setup_delegates
        pass

    def _on_action_selected(self, index):
        if index == 1:   # Добавить
            self.add_requested.emit()
        elif index == 2: # Редактировать
            dto = self.get_current_selected_dto()
            if dto:
                self.edit_requested.emit(dto)
        elif index == 3: # Удалить
            dto = self.get_current_selected_dto()
            if dto:
                self.delete_requested.emit(dto)
        elif index == 4: # Обновить
            self.reload_data()
        self.action_combo.setCurrentIndex(0)

    def _on_inline_action_selected(self, index):
        if index == 1:   # Добавить строку
            self.add_row()
        elif index == 2: # Удалить строку
            self.delete_selected_rows()
        elif index == 3: # Отменить изменения
            self.cancel_selected_rows_changes()
        self.inline_action_combo.setCurrentIndex(0)

    def _on_action_clicked(self):
        dto = self.get_current_selected_dto()
        if dto:
            self.action_requested.emit(dto)

    def _on_row_double_clicked(self, index):
        if not self.edit_mode:
            dto = self.get_current_selected_dto()
            if dto:
                self.action_requested.emit(dto)

    def _update_ui_for_edit_mode(self, edit_mode: bool):
        self.action_combo.setVisible(not edit_mode)
        self.inline_action_combo.setVisible(edit_mode)
        self.save_changes_btn.setVisible(edit_mode)
        self.table_view.setEditTriggers(self.table_view.DoubleClicked if edit_mode else self.table_view.NoEditTriggers)
        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.setEnabled(not edit_mode)