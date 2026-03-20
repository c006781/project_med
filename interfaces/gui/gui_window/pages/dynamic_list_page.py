# interfaces/gui/gui_window/pages/dynamic_list_page.py
# -*- coding: utf-8 -*-

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QHeaderView, QMessageBox, QTableView, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, Slot, QSortFilterProxyModel
from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from app.utils.logger.logger import AppLogger


class DynamicListPage(BasePage):
    """
    Универсальная страница списка.
    Добавлена опциональная кнопка дополнительных действий (action_button_text),
    которая испускает сигнал action_requested при нажатии.
    """
    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    action_requested = Signal(object)  # новый сигнал для дополнительного действия
        
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self,
        service,
        columns,
        page_title="Список",
        add_action_text="Добавить",
        action_button_text=None,       # текст дополнительной кнопки (например, "Приёмы")
        edit_on_double_click=True,
        parent=None
    ):
        super().__init__(parent)
        self.service = service
        self.columns = columns
        self.page_title = page_title
        self.add_action_text = add_action_text
        self.action_button_text = action_button_text
        self.edit_on_double_click = edit_on_double_click
        self.logger = AppLogger.get_instance(f"gui.{self.__class__.__name__}")

        self.current_data = []
        self.selected_dto = None
        self._selection_connected = False

        self._needs_refresh = False
        
        self._setup_ui()
        self._load_data()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage.set_needs_refresh",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_needs_refresh(self, value=True):
        self._needs_refresh = value

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Верхняя панель
        top_layout = QHBoxLayout()

        self.add_btn = QPushButton(self.add_action_text)
        self.add_btn.clicked.connect(self.add_requested.emit)
        top_layout.addWidget(self.add_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        top_layout.addWidget(self.delete_btn)

        # Дополнительная кнопка (если задана)
        if self.action_button_text:
            self.action_btn = QPushButton(self.action_button_text)
            self.action_btn.clicked.connect(self._on_action_clicked)
            self.action_btn.setEnabled(False)
            top_layout.addWidget(self.action_btn)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self._load_data)
        top_layout.addWidget(self.refresh_btn)

        top_layout.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.search_edit)

        main_layout.addLayout(top_layout)

        # Таблица
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        self.source_model = DynamicTableModel(self.current_data, self.columns)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.table_view.setModel(self.proxy_model)

        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        main_layout.addWidget(self.table_view)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage.showEvent",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def showEvent(self, event):
        super().showEvent(event)
        if not self._selection_connected:
            selection_model = self.table_view.selectionModel()
            if selection_model is not None:
                selection_model.selectionChanged.connect(self._on_selection_changed)
                self._selection_connected = True

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._load_data",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_data(self):
        try:
            self.current_data = self.service.get_all()
            self.source_model.update_data(self.current_data)
            self.logger.debug(f"Загружено {len(self.current_data)} записей")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception("Ошибка загрузки данных")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._on_search_text_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_search_text_changed(self, text):
        self.proxy_model.setFilterFixedString(text)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._on_selection_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        if indexes:
            proxy_index = indexes[0]
            source_index = self.proxy_model.mapToSource(proxy_index)
            self.selected_dto = self.source_model.get_item_at_row(source_index.row())
            self.delete_btn.setEnabled(True)
            if hasattr(self, 'action_btn'):
                self.action_btn.setEnabled(True)
        else:
            self.selected_dto = None
            self.delete_btn.setEnabled(False)
            if hasattr(self, 'action_btn'):
                self.action_btn.setEnabled(False)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._on_row_double_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_row_double_clicked(self, index):
        if not self.edit_on_double_click or not index.isValid():
            return
        source_index = self.proxy_model.mapToSource(index)
        dto = self.source_model.get_item_at_row(source_index.row())
        if dto:
            self.edit_requested.emit(dto)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._on_delete_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_delete_clicked(self):
        if not self.selected_dto:
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить выбранную запись?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.selected_dto)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage._on_action_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_action_clicked(self):
        """Обработка нажатия дополнительной кнопки."""
        if self.selected_dto:
            self.action_requested.emit(self.selected_dto)
    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicListPage.on_enter",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        if self._needs_refresh:
            self._load_data()
            self._needs_refresh = False