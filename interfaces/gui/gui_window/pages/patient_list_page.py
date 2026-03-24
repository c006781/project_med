# -*- coding: utf-8 -*-
"""
Страница со списком пациентов.
Содержит таблицу с кнопками действий, возможность фильтрации и поиска.
"""

from app.utils.logger.logger import AppLogger

from app.services import PatientService
from app.dto import PatientDTO
from app.exceptions import PatientNotFoundError, PatientValidationError
from app.dependencies import get_patient_service
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QHeaderView, QMessageBox, QInputDialog, QLineEdit, QTableView
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, Slot, QSortFilterProxyModel
from PySide6.QtGui import QIcon

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.button_delegate import ButtonDelegate


class PatientTableModel(QAbstractTableModel):
    """
    Модель для отображения списка пациентов.
    """
    _headers = ["ID", "Фамилия", "Имя", "Дата рождения", "Телефон", "Email"]

    @AppLogger.get_instance(
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, patients=None, parent=None):
        
        """
        Инициализирует модель для отображения списка пациентов.
        
        :param patients: (list) Список пациентов для отображения.
        :param parent: (QWidget) Родительский виджет.
        """
        super().__init__(parent)
        self._patients = patients or []
        self.logger = AppLogger.get_instance(
            name = 'gui.PatientFilterProxyModel',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

    @AppLogger.get_instance(
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.rowCount",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def rowCount(self, parent=QModelIndex()):
        return len(self._patients)

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.columnCount",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def columnCount(self, parent=QModelIndex()):
        """
        Возвращает количество колонок в модели.
        
        :param parent: Индекс родительского элемента (необязательный)
        :type parent: QModelIndex
        :return: Количество колонок в модели
        :rtype: int
        """
        return len(self._headers)

    @AppLogger.get_instance(
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.data",
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

    @AppLogger.get_instance(
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.headerData",
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
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.sort",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        # """Сортировка модели (вызывается прокси-моделью)."""
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

    @AppLogger.get_instance(
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.update_patients",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def update_patients(self, patients):
        # """Обновляет список пациентов."""
        """
        Обновляет список пациентов.

        :param patients: Новый список пациентов
        :type patients: list[Patient]
        """
        self.beginResetModel()
        self._patients = patients
        self.endResetModel()

    @AppLogger.get_instance(
        name = 'PatientTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientTableModel.get_patient_at_row",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_patient_at_row(self, row):
        # """Возвращает пациента по индексу строки."""
        """
        Возвращает пациента по индексу строки.
        
        :param row: индекс строки
        :type row: int
        :return: Пациент, если индекс строки валиден, иначе None
        :rtype: Optional[PatientDTO]
        """
        if 0 <= row < len(self._patients):
            return self._patients[row]
        return None


class PatientFilterProxyModel(QSortFilterProxyModel):
    """
    Прокси-модель для фильтрации пациентов.
    Поддерживает текстовый фильтр по всем колонкам (или выбранным).
    """

    
    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientFilterProxyModel.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        """
        Инициализирует прокси-модель для фильтрации пациентов.

        :param parent: родительский виджет
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self._filter_text = ""
        self._filter_column = -1  # -1 означает все колонки

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientFilterProxyModel.set_filter_text",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_filter_text(self, text):
        # """Устанавливает текст фильтра."""
        """
        Устанавливает текст фильтра.

        Метод берет текст фильтра и вызывает обновление прокси-модели.
        Текст фильтра сохраняется в нижнем регистре, чтобы обеспечить
        регистронезависимый поиск.

        :param text: Текст фильтра (необязательный)
        :type text: str
        """
        self._filter_text = text.lower()
        self.invalidateFilter()

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientFilterProxyModel.set_filter_column",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_filter_column(self, column):
        # """Устанавливает колонку для фильтрации (-1 для всех)."""
        """
        Устанавливает колонку для фильтрации (-1 для всех).
        
        :param column: номер колонки (-1 для всех)
        :type column: int
        """
        self._filter_column = column
        self.invalidateFilter()

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientFilterProxyModel.filterAcceptsRow",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def filterAcceptsRow(self, source_row, source_parent):
        # """Определяет, проходит ли строка фильтр."""
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
        :type source_parent: QModelIndex
        :return: True, если строка проходит фильтр, False в противном случае
        :rtype: bool
        """
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

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        """
        Инициализирует страницу со списком пациентов.

        :param parent: родительский виджет
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.logger = AppLogger.get_instance(
            ame = "gui.PatientListPage",
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )
        self.patient_service = get_patient_service()
        self._setup_ui()
        self._load_patients()

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_add_btn(self):
        """
        Создает кнопку "Добавить пациента" и возвращает ее.
        Кнопка добавляет нового пациента в список.
        """
        add_btn = QPushButton("Добавить пациента")
        add_btn.clicked.connect(self._on_add_patient)
        return add_btn
    
    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_refresh_btn(self):
        """
        Создает кнопку "Обновить" и возвращает ее.
        Кнопка обновляет список пациентов, полученный из сервиса.
        """
        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self._load_patients)
        return refresh_btn

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_search_edit(self):
        # Поле поиска
        """
        Создает поле для поиска пациентов.
        
        Возвращает созданное поле для поиска.
        """
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Поиск...")
        search_edit.textChanged.connect(self._on_search_text_changed)
        return search_edit  

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _set_table_view(self):
        # Таблица
        """
        Создает таблицу со списком пациентов.
        
        Создает таблицу со списокм пациентов, кнопками действия и возможностью
        сортировки и фильтрации.
        """
        table_view = FilterTableView()
        table_view.setSortingEnabled(True)

        # Модель и прокси
        self.source_model = PatientTableModel()
        self.proxy_model = PatientFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        table_view.setModel(self.proxy_model)

        # Делегат для кнопок в первом столбце
        self.button_delegate = ButtonDelegate(self.table_view, "Действия")
        table_view.setItemDelegateForColumn(0, self.button_delegate)
        self.button_delegate.button_clicked.connect(self._on_action_button_clicked)

        # Настройка колонок
        table_view.horizontalHeader().setStretchLastSection(True)
        table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)

        return table_view  
        

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )    
    def _set_top_layout(self):
        # Верхняя панель с кнопками
        """
        Создает верхнюю панель с кнопками и полем поиска.

        Создает верхнюю панель, содержащую кнопки "Добавить", "Обновить"
        и поле поиска. Кнопка "Добавить" добавляет нового пациента в список,
        "Обновить" обновляет список пациентов, полученный из сервиса,
        а поле поиска позволяет искать пациентов по тексту, введенному в поле.
        """
        top_layout = QHBoxLayout()

        self.add_btn = self._set_add_btn()
        top_layout.addWidget(self.add_btn)

        self.refresh_btn = self._set_refresh_btn()
        top_layout.addWidget(self.refresh_btn)

        top_layout.addStretch()

        # Поле поиска
        self.search_edit = self._set_search_edit()
        top_layout.addWidget(self.search_edit)

        return top_layout   

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """
        Создает элементы интерфейса: кнопки "Добавить" и "Обновить",
        поле поиска и таблицу со списком пациентов.
        """
        main_layout = QVBoxLayout(self)

        # Верхняя панель с кнопками
        top_layout = self._set_top_layout()

        main_layout.addLayout(top_layout)

        # Таблица
        self.table_view = self._set_table_view()
        
        main_layout.addWidget(self.table_view)

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage._load_patients",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_patients(self):
        """
        Загружает список пациентов из сервиса и обновляет модель.

        Метод загружает список пациентов из сервиса, используя сервис PatientService,
        и обновляет модель, используя метод update_patients класса PatientTableModel.
        Если загрузка прошла успешно, то в логгере выводится информационное сообщение
        с количеством загруженных пациентов. Если загрузка прошла неудачно, то в логгере
        выводится ошибочное сообщение с информацией о возникшей ошибке.
        """
        try:
            patients = self.patient_service.get_all_patients()
            self.source_model.update_patients(patients)
            self.logger.debug(f"Загружено {len(patients)} пациентов")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить пациентов: {e}")
            self.logger.exception("Ошибка загрузки пациентов")

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage._on_add_patient",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_add_patient(self):
        """Переход на страницу редактирования нового пациента."""
        if self.page_manager:
            # Передаём ID=None, чтобы страница редактирования знала, что это создание
            self.page_manager.switch_to('patient_edit', extra_data={'patient_id': None})

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage._on_action_button_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(int)
    def _on_action_button_clicked(self, row):
        """
        Обработка нажатия кнопки действия в строке.
        Переходим на страницу редактирования пациента.

        :param row: номер строки, в которой была нажата кнопка
        :type row: int
        """
        proxy_index = self.proxy_model.index(row, 0)
        source_index = self.proxy_model.mapToSource(proxy_index)
        patient = self.source_model.get_patient_at_row(source_index.row())
        if patient:
            if self.page_manager:
                self.page_manager.switch_to('patient_edit', extra_data={'patient_id': patient.id})

    @AppLogger.get_instance(
        name = 'PatientFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="PatientListPage._on_search_text_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot(str)
    def _on_search_text_changed(self, text):
        """Обновляет фильтр поиска."""
        self.proxy_model.set_filter_text(text)