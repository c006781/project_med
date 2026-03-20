# interfaces/gui/gui_window/pages/appointment_list_page.py
# -*- coding: utf-8 -*-
"""
Страница со списком приёмов.
Левая часть - таблица приёмов, правая - детали выбранного приёма (с фото).
При клике на строку в таблице справа показывается информация.
"""

from app.utils.logger.logger import AppLogger

from app.services import AppointmentService, PhotoService
from app.dto import AppointmentDTO
from app.exceptions import AppointmentNotFoundError
from app.dependencies import get_appointment_service, get_photo_service

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableView, QPushButton, QHeaderView, QMessageBox,
    QLineEdit, QLabel, QTextEdit, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, Slot, QSortFilterProxyModel, QSize
from PySide6.QtGui import QPixmap, QIcon

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView


class AppointmentTableModel(QAbstractTableModel):
    """
    Модель для отображения списка приёмов.
    """
    _headers = ["ID", "Дата", "Время", "Заметка"]

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, appointments=None, parent=None):
        """
        Инициализирует модель для отображения списка приёмов.

        :param appointments: Список приёмов (опциональный)
        :type appointments: list of AppointmentDTO
        :param parent: Родительский объект (необязательный)
        :type parent: QObject
        """
        super().__init__(parent)
        self._appointments = appointments or []

    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.rowCount",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def rowCount(self, parent=QModelIndex()):
        """
        Возвращает количество строк в модели.

        :param parent: Родительский индекс (необязательный)
        :type parent: QModelIndex
        :return: Количество строк в модели
        :rtype: int
        """
        return len(self._appointments)

    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.columnCount",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def columnCount(self, parent=QModelIndex()):
        
        """
        Возвращает количество колонок в модели.

        :param parent: Родительский индекс (необязательный)
        :type parent: QModelIndex
        :return: Количество колонок в модели
        :rtype: int
        """
        return len(self._headers)
    
    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.data",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """
        Возвращает значение ячейки по указанному индексу и роли.

        :param index: Индекс ячейки
        :type index: QModelIndex
        :param role: Роль значения (DisplayRole по умолчанию)
        :type role: int
        :return: Значение ячейки или None
        :rtype: Any
        """
        if not index.isValid():
            return None
        app = self._appointments[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(app.id)
            elif col == 1:
                return app.date.isoformat() if app.date else ""
            elif col == 2:
                return app.time.strftime("%H:%M") if app.time else ""
            elif col == 3:
                return app.note_text[:50] + "..." if app.note_text else ""
        return None

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.headerData",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """
        Возвращает заголовок ячейки по указанному индексу и роли.

        :param section: Номер ячейки
        :type section: int
        :param orientation: Ориентация ячейки (Horizontal или Vertical)
        :type orientation: Qt.Orientation
        :param role: Роль значения (DisplayRole по умолчанию)
        :type role: int
        :return: Заголовок ячейки или None
        :rtype: str
        """
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        return None

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.sort",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        """
        Сортировка модели (вызывается прокси-моделью).

        :param column: Номер ячейки для сортировки
        :type column: int
        :param order: Порядок сортировки (по умолчанию - AscendingOrder)
        :type order: Qt.SortOrder
        """
        self.beginResetModel()
        reverse = (order == Qt.SortOrder.DescendingOrder)
        if column == 0:
            self._appointments.sort(key=lambda a: a.id, reverse=reverse)
        elif column == 1:
            self._appointments.sort(key=lambda a: a.date or "", reverse=reverse)
        elif column == 2:
            self._appointments.sort(key=lambda a: a.time or "", reverse=reverse)
        elif column == 3:
            self._appointments.sort(key=lambda a: a.note_text or "", reverse=reverse)
        self.endResetModel()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.update_appointments",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def update_appointments(self, appointments):
        """
        Обновляет список приёмов.

        :param appointments: Новый список приёмов
        :type appointments: List[AppointmentDTO]
        """
        self.beginResetModel()
        self._appointments = appointments
        self.endResetModel()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentTableModel.get_appointment_at_row",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_appointment_at_row(self, row):
        """
        Возвращает приём по индексу строки.

        :param row: Индекс строки
        :type row: int
        :return: DTO приёма или None, если индекс вне диапазона
        :rtype: Optional[AppointmentDTO]
        """
        if 0 <= row < len(self._appointments):
            return self._appointments[row]
        return None


class AppointmentFilterProxyModel(QSortFilterProxyModel):
    """Прокси для фильтрации приёмов по тексту."""


    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentFilterProxyModel.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        """
        Инициализирует фильтр для приёмов по тексту.

        Этот класс наследуется от QSortFilterProxyModel и
        переопределяет метод setFilterText для фильтрации
        приёмов по тексту.

        :param parent: Родительский объект (необязательный)
        :type parent: QObject
        """
        super().__init__(parent)
        self._filter_text = ""

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentFilterProxyModel.set_filter_text",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_filter_text(self, text):
        """
        Устанавливает текст фильтра для приёмов.

        Создаёт кэш-версию текста и вызывает обновление прокси-модели.

        :param text: Текст фильтра (необязательный)
        :type text: str
        """
        self._filter_text = text.lower()  # Создаём кэш-версию текста
        self.invalidateFilter()  # Вызываем обновление прокси-модели

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentFilterProxyModel.filterAcceptsRow",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def filterAcceptsRow(self, source_row, source_parent):
        """
        Определяет, проходит ли строка фильтр.

        Метод берет строку и родительский объект из модели-источника и
        проверяет, является ли текст фильтра пустым. Если да, то возвращает True,
        потому что пустой текст фильтра соответствует любая строка.

        Затем он получает модель-источник и производится проверка наличия текста фильтра
        в данных модели. Если текст фильтра найден, то возвращает True.
        В противном случае возвращает False.

        :param source_row: Номер строки в модели-источнике (необязательный)
        :type source_row: int
        :param source_parent: Родительский объект из модели-источника (необязательный)
        :type source_parent: QObject
        :return: True, если строка проходит фильтр, False в противном случае
        :rtype: bool
        """
        if not self._filter_text:
            return True
        source_model = self.sourceModel()
        if not source_model:
            return True
        for col in range(source_model.columnCount()):
            index = source_model.index(source_row, col, source_parent)
            data = source_model.data(index, Qt.ItemDataRole.DisplayRole)
            if data and self._filter_text in str(data).lower():
                return True
        return False


class AppointmentListPage(BasePage):
    """
    Страница со списком приёмов.
    Принимает в extra_data ключ 'patient_id' для фильтрации.
    """

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = AppLogger.get_instance("gui.AppointmentListPage")
        self.appointment_service = get_appointment_service()
        self.photo_service = get_photo_service()  # для загрузки фото

        self.current_patient_id = None
        self.current_appointment_id = None

        self._setup_ui()
        self._load_appointments()  # загрузит все, если нет patient_id

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """Создаёт двухпанельный интерфейс."""
        main_layout = QVBoxLayout(self)

        # Верхняя панель с кнопками
        top_layout = QHBoxLayout()

        self.add_btn = QPushButton("Новый приём")
        self.add_btn.clicked.connect(self._on_add_appointment)
        top_layout.addWidget(self.add_btn)

        self.delete_btn = QPushButton("Удалить приём")
        self.delete_btn.clicked.connect(self._on_delete_appointment)
        self.delete_btn.setEnabled(False)
        top_layout.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self._load_appointments)
        top_layout.addWidget(self.refresh_btn)

        top_layout.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.search_edit)

        main_layout.addLayout(top_layout)

        # Разделитель: слева таблица, справа детали
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая часть: таблица приёмов
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)

        self.source_model = AppointmentTableModel()
        self.proxy_model = AppointmentFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.table_view.setModel(self.proxy_model)

        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.selectionModel().selectionChanged.connect(self._on_appointment_selected)

        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        left_layout.addWidget(self.table_view)
        splitter.addWidget(left_widget)

        # Правая часть: детали приёма
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.info_label = QLabel("Выберите приём")
        right_layout.addWidget(self.info_label)

        self.note_text = QTextEdit()
        self.note_text.setReadOnly(True)
        self.note_text.setMaximumHeight(150)
        right_layout.addWidget(QLabel("Заметка:"))
        right_layout.addWidget(self.note_text)

        self.photo_list = QListWidget()
        self.photo_list.setIconSize(QSize(100, 100))
        self.photo_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.photo_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.photo_list.itemDoubleClicked.connect(self._on_photo_double_clicked)
        right_layout.addWidget(QLabel("Фотографии:"))
        right_layout.addWidget(self.photo_list)

        splitter.addWidget(right_widget)
        splitter.setSizes([400, 600])

        main_layout.addWidget(splitter)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage.on_enter",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        """При входе загружаем приёмы для указанного пациента (если patient_id передан)."""
        self.current_patient_id = extra_data.get('patient_id') if extra_data else None
        self._load_appointments()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._load_appointments",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_appointments(self):
        """Загружает приёмы, применяя фильтр по patient_id, если он задан."""
        try:
            if self.current_patient_id:
                apps = self.appointment_service.get_appointments_by_patient(self.current_patient_id)
            else:
                apps = self.appointment_service.get_all()
            self.source_model.update_appointments(apps)
            self.logger.debug(f"Загружено {len(apps)} приёмов")
            # Сбрасываем выделение
            self.table_view.clearSelection()
            self._clear_details()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить приёмы: {e}")
            self.logger.exception("Ошибка загрузки приёмов")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._on_add_appointment",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_add_appointment(self):
        """Переход на страницу создания нового приёма (с patient_id, если он известен)."""
        extra = {}
        if self.current_patient_id:
            extra['patient_id'] = self.current_patient_id
        if self.page_manager:
            self.page_manager.switch_to('appointment_edit', extra_data=extra)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._on_delete_appointment",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_delete_appointment(self):
        """Удаление выбранного приёма."""
        if not self.current_appointment_id:
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить этот приём? Все связанные фото также будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.appointment_service.delete_appointment(self.current_appointment_id)
                QMessageBox.information(self, "Успех", "Приём удалён.")
                self.logger.info(f"Удалён приём ID={self.current_appointment_id}")
                self._load_appointments()
                self._clear_details()
                self.delete_btn.setEnabled(False)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления приёма")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._on_search_text_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(str)
    def _on_search_text_changed(self, text):
        """Обновляет фильтр в таблице."""
        self.proxy_model.set_filter_text(text)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._on_appointment_selected",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_appointment_selected(self, selected, deselected):
        """Обработка выбора строки в таблице."""
        indexes = selected.indexes()
        if indexes:
            proxy_index = indexes[0]  # берём первый индекс (любой колонки)
            source_index = self.proxy_model.mapToSource(proxy_index)
            appointment = self.source_model.get_appointment_at_row(source_index.row())
            if appointment:
                self.current_appointment_id = appointment.id
                self._show_appointment_details(appointment)
                self.delete_btn.setEnabled(True)
            else:
                self._clear_details()
                self.delete_btn.setEnabled(False)
        else:
            self._clear_details()
            self.delete_btn.setEnabled(False)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._show_appointment_details",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _show_appointment_details(self, appointment: AppointmentDTO):
        """Отображает детали приёма и загружает фото."""
        self.info_label.setText(f"Приём ID {appointment.id} от {appointment.date} {appointment.time or ''}")
        self.note_text.setText(appointment.note_text or "")
        # Загружаем фото
        self.photo_list.clear()
        try:
            photos = self.photo_service.get_photos_for_appointment(appointment.id)
            for photo in photos:
                # Здесь нужно получить полный путь к файлу
                # Временно используем заглушку
                pixmap = QPixmap()  # должна загружаться из photo.file_path
                if not pixmap.isNull():
                    icon = QIcon(pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    icon = QIcon()
                item = QListWidgetItem(icon, photo.description or "")
                item.setData(Qt.ItemDataRole.UserRole, photo.id)
                self.photo_list.addItem(item)
        except Exception as e:
            self.logger.exception("Ошибка загрузки фото")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._clear_details",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _clear_details(self):
        """Очищает панель деталей."""
        self.info_label.setText("Выберите приём")
        self.note_text.clear()
        self.photo_list.clear()
        self.current_appointment_id = None

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentListPage._on_photo_double_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(QListWidgetItem)
    def _on_photo_double_clicked(self, item):
        """При двойном клике на фото можно открыть его в большом окне (заглушка)."""
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        QMessageBox.information(self, "Фото", f"Открыть фото ID {photo_id} (не реализовано)")
        # TODO: открыть полноразмерное фото