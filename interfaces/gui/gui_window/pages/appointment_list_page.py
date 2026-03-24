# interfaces/gui/gui_window/pages/appointment_list_page.py
# -*- coding: utf-8 -*-
"""
Страница со списком приёмов.
Левая часть - таблица приёмов, правая - детали выбранного приёма (с фото).
При клике на строку в таблице справа показывается информация.
"""

from app.utils.logger.logger import AppLogger

# from app.services import AppointmentService, PhotoService
# from app.dto import AppointmentDTO
# from app.exceptions import AppointmentNotFoundError
from app.dependencies import (
    # get_appointment_service, 
    get_photo_service
)

# from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.pages.dynamic_detail_list_page import DynamicDetailListPage
# from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView

from PySide6.QtWidgets import (
    # QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    # QTableView, QPushButton, QHeaderView, QMessageBox,
    # QLineEdit, 
    QLabel, QTextEdit, QListWidget, QListWidgetItem
)
from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, 
    # Signal, Slot, 
    QSortFilterProxyModel, QSize
)
from PySide6.QtGui import QPixmap, QIcon



class AppointmentTableModel(QAbstractTableModel):
    """
    Модель для отображения списка приёмов.
    """
    _headers = ["ID", "Дата", "Время", "Заметка"]

    @AppLogger.get_instance(
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.__init__",
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

        self.logger = AppLogger.get_instance(
            name = 'gui.AppointmentListPage',
            enable_file_logging = 'AppointmentTableModel',
            use_name_in_filename = 'AppointmentTableModel',
        )

    
    @AppLogger.get_instance(
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.rowCount",
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
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.columnCount",
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
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.data",
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
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.headerData",
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
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.sort",
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
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.update_appointments",
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
        name = 'AppointmentTableModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentTableModel.get_appointment_at_row",
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
        name = 'AppointmentFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentFilterProxyModel.__init__",
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

        self.logger = AppLogger.get_instance(
            name = 'gui.AppointmentListPage',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

    @AppLogger.get_instance(
        name = 'AppointmentFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentFilterProxyModel.set_filter_text",
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
        name = 'AppointmentFilterProxyModel',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentFilterProxyModel.filterAcceptsRow",
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


# class AppointmentListPage(BasePage):
class AppointmentListPage(DynamicDetailListPage):
    """
    Страница со списком приёмов с правой панелью (заметка и фото).
    """

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, service, loader_func, dto_class, field_configs, *args, **kwargs):
        """
        Инициализирует страницу со списком приёмов с правой панелью (заметка и фото).
        """
        
        super().__init__(service, loader_func, dto_class, field_configs, *args, **kwargs)
        
        self.logger = AppLogger.get_instance(
            name = 'gui.AppointmentListPage',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

        self.photo_service = get_photo_service()

        self.current_appointment_id = None
        self._setup_detail_panel()

        


    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentListPage._setup_detail_panel",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_detail_panel(self):
        """
        Создает виджету правой панели.

        Создает виджету с заметкой и фотографиями приема.
        """
        # Создаем виджету с заметкой

        self.note_text_edit = QTextEdit()
        # Установка режима "только для чтения"
        self.note_text_edit.setReadOnly(True)

        # Добавляем виджету с заметкой в верхнюю часть detail_layout
        self.detail_layout.addWidget(QLabel("Заметка:"))
        self.detail_layout.addWidget(self.note_text_edit)

        # Создаем виджету со списком фотографий
        self.photo_list = QListWidget()

        # Установка размера иконок фотографий
        self.photo_list.setIconSize(QSize(100, 100))

        # Добавляем виджету со списком фотографий в верхнюю часть detail_layout
        self.detail_layout.addWidget(QLabel("Фотографии:"))
        self.detail_layout.addWidget(self.photo_list)


    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentListPage.update_details",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def update_details(self, dto):
        """
        Обновляет правую панель данными выбранного приёма.
        Вызывается автоматически при выборе строки в таблице.

        :param dto: данные приёма
        :type dto: AppointmentDTO
        """
        if not dto:
            return
        self.current_appointment_id = dto.id
        self.note_text_edit.setText(dto.note_text or "")
        self._load_photos(dto.id)


    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentListPage._load_photos",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_photos(self, appointment_id):
        """
        Загружает фото для приёма и отображает их в списке.

        :param appointment_id: ID приёма
        :raises Exception: если произошла ошибка загрузки
        """
        self.photo_list.clear()
        try:
            photos = self.photo_service.get_photos_for_appointment(appointment_id)
            for photo in photos:
                # TODO: загружать реальный QPixmap из файла
                pixmap = QPixmap()  # заглушка
                if not pixmap.isNull():
                    icon = QIcon(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    icon = QIcon()
                item = QListWidgetItem(icon, photo.description or "")
                item.setData(Qt.UserRole, photo.id)
                self.photo_list.addItem(item)
        except Exception as e:
            self.logger.exception("Ошибка загрузки фото")