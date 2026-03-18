# -*- coding: utf-8 -*-
"""
Страница со списком пациентов.
Содержит таблицу с кнопками действий, возможность фильтрации и поиска.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QHeaderView, QMessageBox, QInputDialog, QLineEdit, QTableView
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, Slot, QSortFilterProxyModel
from PySide6.QtGui import QIcon

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.button_delegate import ButtonDelegate
from app.services import PatientService
from app.dto import PatientDTO
from app.exceptions import PatientNotFoundError, PatientValidationError
from app.dependencies import get_patient_service
from app.utils.logger.logger import AppLogger


class PatientTableModel(QAbstractTableModel):
    """
    Модель для отображения списка пациентов.
    """
    _headers = ["ID", "Фамилия", "Имя", "Дата рождения", "Телефон", "Email"]

    def __init__(self, patients=None, parent=None):
        super().__init__(parent)
        self._patients = patients or []
        self.logger = AppLogger.get_instance("gui.PatientTableModel")

    def rowCount(self, parent=QModelIndex()):
        return len(self._patients)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        patient = self._patients[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(patient.id)
            elif col == 1:
                return patient.last_name
            elif col == 2:
                return patient.first_name
            elif col == 3:
                return patient.birth_date.isoformat() if patient.birth_date else ""
            elif col == 4:
                return patient.phone or ""
            elif col == 5:
                return patient.email or ""
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        """Сортировка модели (вызывается прокси-моделью)."""
        self.beginResetModel()
        reverse = (order == Qt.SortOrder.DescendingOrder)
        if column == 0:
            self._patients.sort(key=lambda p: p.id, reverse=reverse)
        elif column == 1:
            self._patients.sort(key=lambda p: p.last_name, reverse=reverse)
        elif column == 2:
            self._patients.sort(key=lambda p: p.first_name, reverse=reverse)
        elif column == 3:
            self._patients.sort(key=lambda p: p.birth_date or "", reverse=reverse)
        elif column == 4:
            self._patients.sort(key=lambda p: p.phone or "", reverse=reverse)
        elif column == 5:
            self._patients.sort(key=lambda p: p.email or "", reverse=reverse)
        self.endResetModel()

    def update_patients(self, patients):
        """Обновляет список пациентов."""
        self.beginResetModel()
        self._patients = patients
        self.endResetModel()

    def get_patient_at_row(self, row):
        """Возвращает пациента по индексу строки."""
        if 0 <= row < len(self._patients):
            return self._patients[row]
        return None


class PatientFilterProxyModel(QSortFilterProxyModel):
    """
    Прокси-модель для фильтрации пациентов.
    Поддерживает текстовый фильтр по всем колонкам (или выбранным).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""
        self._filter_column = -1  # -1 означает все колонки

    def set_filter_text(self, text):
        """Устанавливает текст фильтра."""
        self._filter_text = text.lower()
        self.invalidateFilter()

    def set_filter_column(self, column):
        """Устанавливает колонку для фильтрации (-1 для всех)."""
        self._filter_column = column
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        """Определяет, проходит ли строка фильтр."""
        if not self._filter_text:
            return True
        source_model = self.sourceModel()
        if not source_model:
            return True

        # Получаем данные из всех колонок, если _filter_column == -1, иначе только из указанной
        columns = [self._filter_column] if self._filter_column != -1 else range(source_model.columnCount())
        for col in columns:
            index = source_model.index(source_row, col, source_parent)
            data = source_model.data(index, Qt.ItemDataRole.DisplayRole)
            if data and self._filter_text in str(data).lower():
                return True
        return False


class PatientListPage(BasePage):
    """
    Страница со списком пациентов.
    """

    button_clicked = Signal(int)  # сигнал о нажатии кнопки (индекс строки)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = AppLogger.get_instance("gui.PatientListPage")
        self.patient_service = get_patient_service()
        self._setup_ui()
        self._load_patients()

    def _setup_ui(self):
        """Создаёт элементы интерфейса."""
        main_layout = QVBoxLayout(self)

        # Верхняя панель с кнопками
        top_layout = QHBoxLayout()

        self.add_btn = QPushButton("Добавить пациента")
        self.add_btn.clicked.connect(self._on_add_patient)
        top_layout.addWidget(self.add_btn)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self._load_patients)
        top_layout.addWidget(self.refresh_btn)

        top_layout.addStretch()

        # Поле поиска
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.search_edit)

        main_layout.addLayout(top_layout)

        # Таблица
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)

        # Модель и прокси
        self.source_model = PatientTableModel()
        self.proxy_model = PatientFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.table_view.setModel(self.proxy_model)

        # Делегат для кнопок в первом столбце
        self.button_delegate = ButtonDelegate(self.table_view, "Действия")
        self.table_view.setItemDelegateForColumn(0, self.button_delegate)
        self.button_delegate.button_clicked.connect(self._on_action_button_clicked)

        # Настройка колонок
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)

        main_layout.addWidget(self.table_view)

    def _load_patients(self):
        """Загружает список пациентов из сервиса и обновляет модель."""
        try:
            patients = self.patient_service.get_all_patients()
            self.source_model.update_patients(patients)
            self.logger.debug(f"Загружено {len(patients)} пациентов")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить пациентов: {e}")
            self.logger.exception("Ошибка загрузки пациентов")

    @Slot()
    def _on_add_patient(self):
        """Переход на страницу редактирования нового пациента."""
        if self.page_manager:
            # Передаём ID=None, чтобы страница редактирования знала, что это создание
            self.page_manager.switch_to('patient_edit', extra_data={'patient_id': None})

    @Slot(int)
    def _on_action_button_clicked(self, row):
        """
        Обработка нажатия кнопки действия в строке.
        Переходим на страницу редактирования пациента.
        """
        proxy_index = self.proxy_model.index(row, 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        patient = self.source_model.get_patient_at_row(source_index.row())
        if patient:
            if self.page_manager:
                self.page_manager.switch_to('patient_edit', extra_data={'patient_id': patient.id})

    @Slot(str)
    def _on_search_text_changed(self, text):
        """Обновляет фильтр поиска."""
        self.proxy_model.set_filter_text(text)