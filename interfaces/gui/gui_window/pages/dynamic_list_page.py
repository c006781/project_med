# interfaces/gui/gui_window/pages/dynamic_list_page.py
# -*- coding: utf-8 -*-


from typing import List

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.combo_box_delegate import ComboBoxDelegate
from interfaces.gui.gui_window.widgets.advanced_filter_proxy_model import AdvancedFilterProxyModel

from PySide6.QtWidgets import (
    # QWidget, 
    QVBoxLayout, 
    QHBoxLayout, 
    QPushButton, 
    QLineEdit,
    QHeaderView, 
    QMessageBox, 
    # QTableView, 
    QAbstractItemView,
)
from PySide6.QtCore import (
    # Qt, 
    Signal, 
    Slot, 
    # QSortFilterProxyModel
)



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
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self,
        service,  # сервис, используемый для редактирования записи
        loader_func,  # функция, которая возвращает список данных
        dto_class,  # класс DTO, используемый для создания записи
        field_configs,  # внешняя конфигурация
        page_title="Список",  # заголовок страницы
        add_action_text="Добавить",  # текст кнопки добавления
        action_button_text=None,  # текст дополнительной кнопки (если задана)
        edit_on_double_click=True,  # True, если редактирование должно быть доступно при двойном нажатии на строке
        parent=None,  # родительский виджет
    ):
        # """
        # Инициализирует страницу списка.
        # """

        """
        Инициализирует страницу списка.

        :param service: сервис, используемый для редактирования записи
        :param loader_func: функция, которая возвращает список данных
        :param dto_class: класс DTO, используемый для создания записи
        :param field_configs: внешняя конфигурация
        :param page_title: заголовок страницы
        :param add_action_text: текст кнопки добавления
        :param action_button_text: текст дополнительной кнопки (если задана)
        :param edit_on_double_click: True, если редактирование должно быть доступно при двойном нажатии на строке
        :param parent: родительский виджет
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name = f"gui.{self.__class__.__name__}",
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )


        self.service = service
        self.loader_func = loader_func
        # self.columns = columns
        self.dto_class = dto_class
        self.field_configs = field_configs
        self.page_title = page_title
        self.add_action_text = add_action_text
        self.action_button_text = action_button_text
        self.edit_on_double_click = edit_on_double_click

        self.main_layout = QVBoxLayout(self) # сохраним основной layout как атрибут
        self.columns = self._build_columns()   # строим список колонок


        self.current_data = []  # список данных, которые сейчас отображаются на странице
        self.selected_dto = None  # выбранный DTO (объект с атрибутами, соответствующими колонкам)
        self._selection_connected = False  # флаг, который указывает, является ли соединение между сигналами selectionChanged и слотом _on_selection_changed установленным

        self.current_extra = None  # запоминаем последние переданные параметры

        # настройка интерфейса страницы
        self._needs_refresh = False  # флаг, который указывает, нужно ли перезагружать данные при следующем входе на страницу
        self._setup_ui()
        
        self._load_data() # загрузка данных на страницу

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _build_columns(self):
        """
        Создаёт список колонок из field_configs и dto_class.

        Возвращает список словарей, где каждый словарь содержит информацию о колонке:
        - name: имя поля в DTO
        - title: заголовок поля (если не задан, то берется из имени поля)

        Field_configs - это список словарей, где каждый словарь содержит информацию о поле:
        - name: имя поля в DTO
        - title: заголовок поля (если не задан, то берется из имени поля)
        - choices: список значений, которые доступны для поля (если не задан)
        - editable: флаг, который указывает, является ли поле доступным для редактирования (если не задан)

        Dto_class - это класс DTO, который содержит информацию о полях и их значения.
        """
        
        cols = []
        # Сортировка по order (если order не задан, ставим в конец)
        # sorted_fields = sorted(self.field_configs.items(), key=lambda x: x[1].get('order', 999))
        # for field_name, config in sorted_fields:
        for field_name, config in self.field_configs.items():
            if config.get('hidden', False):  # по умолчанию False # нужно ли скрывать объект
                continue

            # Получаем тип поля из DTO (по умолчанию str, если поля нет)
            field_info = self.dto_class.model_fields.get(field_name)
            field_type = field_info.annotation if field_info else str

            # field_type = self.dto_class.model_fields[field_name].annotation
            cols.append({
                'name': field_name,
                'title': config.get('title', field_name.replace('_', ' ').title()),
                'type': field_type,
                'editable': config.get('editable', False),
                'choices': config.get('choices'),
            })
        # return cols
        # Сортировка по order
        return sorted(
            cols, 
            key=lambda c: self.field_configs.get(
                c['name'], {}
            ).get('order', 0)
        )

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_filter_requested(self, column: int, operator: str, value):
        """
        Обработка сигнала фильтрации от заголовка.

        :param column: номер столбца, для которого нужно установить фильтр
        :param operator: оператор фильтрации (eq, like, fuzzy, in)
        :param value: значение для сравнения (зависит от оператора)
        """
        if operator == 'in':
            self.proxy_model.set_column_filter(column, selected_values=value)
        elif operator == 'contains':
            self.proxy_model.set_column_filter(column, filter_text=value)
        elif operator == 'clear':
            self.proxy_model.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage.on_filter_clear",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_filter_clear(self, column: int):
        """
        Сброс фильтра для колонки.

        :param column: номер столбца
        """
        self.proxy_model.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage.get_unique_values_for_column",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_unique_values_for_column(self, column: int) -> List[str]:
        """
        Возвращает список уникальных значений для указанного столбца.

        :param column: индекс столбца, для которого необходимо получить список уникальных значений
        :type column: int
        :return: список уникальных значений в виде строкового представления
        :rtype: List[str]
        """
        if self.service is None:
            return []
        
        col_name = self.columns[column]['name']
        values = self.service.get_unique_values(col_name)
        
        # Преобразуем в строки (могут быть даты, числа)
        return [str(v) for v in values]

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage.set_needs_refresh",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def set_needs_refresh(self, value=True):
        """
        Устанавливает флаг _needs_refresh.

        :param value: True, если данные нужно перезагружать при следующем входе на страницу
        """
        self._needs_refresh = value
        
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_top_panel(self):
        """
        Создаёт верхнюю панель с кнопками и полем поиска.

        Верхняя панель содержит кнопки "Добавить", "Удалить", "Обновить"
        и поле поиска. Кнопка "Добавить" добавляет новый элемент в список,
        "Удалить" удаляет выбранный элемент из списка, а "Обновить" обновляет
        список элементов. Поле поиска позволяет искать элементы в списке
        по тексту, введенному в поле.
        """
        # Верхняя панель
        top_layout = QHBoxLayout()

        # Кнопка "Добавить"
        self.add_btn = QPushButton(self.add_action_text)
        self.add_btn.clicked.connect(self.add_requested.emit)
        top_layout.addWidget(self.add_btn)

        # Кнопка "Удалить"
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        top_layout.addWidget(self.delete_btn)

        # Кнопка "Действие" (если она была указана)
        if self.action_button_text:
            self.action_btn = QPushButton(self.action_button_text)
            self.action_btn.clicked.connect(self._on_action_clicked)
            self.action_btn.setEnabled(False)
            top_layout.addWidget(self.action_btn)

        # Кнопка "Обновить"
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.clicked.connect(self._load_data)
        top_layout.addWidget(self.refresh_btn)

        # Заполнение пустого пространства
        top_layout.addStretch()

        # Поле поиска
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.search_edit)

        self.main_layout.addLayout(top_layout)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_table(self):
        """
        Создает таблицу с настройками сортировки и фильтрации.

        Создает таблицу с возможностью сортировки и фильтрации.
        Таблица отображает данные из списка self.current_data, а также
        позволяет сортировать данные по любому из столбцов.

        Сначала создается экземпляр класса FilterTableView, который является
        таблицей с возможностью сортировки и фильтрации. Затем
        для таблицы устанавливаются настройки: сортировка по любому из столбцов,
        выбор строк в таблице, а также обработка двойного нажатия на строке.

        Далее создается экземпляр класса DynamicTableModel, который
        является моделью данных для таблицы. Модель данных содержит список
        self.current_data, который является текущим списком данных, отображаемых
        в таблице. Затем создается экземпляр класса QSortFilterProxyModel,
        который является проксирующим моделью данных. Он получает модель
        данных self.source_model и позволяет фильтровать данные по любому из столбцов.

        Наконец, для таблицы self.table_view устанавливаются моделью данных
        self.proxy_model и настройки заголовка столбцов.
        """

        # Добавляем основной макет

        # Таблица
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Модель таблицы
        self.source_model = DynamicTableModel(self.current_data, self.columns)

        # Прокси-модель
        self.proxy_model = AdvancedFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        
        self.table_view.setModel(self.proxy_model)



        # # Обработка события изменения выбора в таблице
        # self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        # self.proxy_model = AdvancedFilterProxyModel()
        # self.proxy_model.setSourceModel(self.source_model)
        # self.table_view.setModel(self.proxy_model)

        # Настройка заголовка таблицы
        header = self.table_view.horizontalHeader()
        if hasattr(header, 'set_get_unique_values_func'):
            header.set_get_unique_values_func(self.get_unique_values_for_column)
            header.filter_requested.connect(self.on_filter_requested)
            header.filter_clear_requested.connect(self.on_filter_clear)


        # # Прокси-модель
        # self.proxy_model = QSortFilterProxyModel()
        # self.proxy_model.setSourceModel(self.source_model)
        # self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # self.proxy_model.setFilterKeyColumn(-1)
        # self.table_view.setModel(self.proxy_model)

        # # Шапка заголовка
        # header = self.table_view.horizontalHeader()

        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # # Добавляем таблицу
        # self.main_layout.addWidget(self.table_view)



    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """
        Устанавливает интерфейс страницы.

        Создаёт форму верхней панели с кнопками "Добавить", "Удалить" и "Обновить".
        Создаёт дополнительную кнопку (если задана).
        Создаёт поле поиска.
        Создаёт таблицу с возможностью сортировки и выделения строк.
        """
        # Основной макет
        # self.main_layout = QVBoxLayout(self)

        self._setup_top_panel() # Верхняя панель
        self._setup_table() # Добавляем основной макет

        # Добавляем таблицу в основной layout
        self.main_layout.addWidget(self.table_view)

        self._setup_delegates() # Устанавливаем делегаты для колонок с выпадающими списками
      
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._setup_delegates",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )  
    def _setup_delegates(self):
        """
        Устанавливает делегаты для колонок, у которых есть choices.
        
        Делегат создается для каждой колонки, у которой есть choices.
        Делегат будет использоваться для отображения комбобокса в соответствующей колонке.
        """
        for col_idx, col_info in enumerate(self.columns):
            choices = col_info.get('choices')
            if choices:
                delegate = ComboBoxDelegate(self.table_view, choices)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage.showEvent",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def showEvent(self, event):
        """
        Обработка события отображения страницы.

        Подключает функцию super().showEvent(), а также подключает сигнал selectionChanged к слоту _on_selection_changed,
        если он не был подключен ранее. Это необходимо, чтобы слушатель _on_selection_changed срабатывал,
        когда пользователь выбирает строку в таблице.
        """
        super().showEvent(event)
        # Подключаем сигнал selectionChanged к слоту _on_selection_changed, если он не был подключен ранее
        if not self._selection_connected:
            selection_model = self.table_view.selectionModel()
            if selection_model is not None:
                # Подключаем сигнал selectionChanged к слоту _on_selection_changed
                selection_model.selectionChanged.connect(self._on_selection_changed)
                self._selection_connected = True

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._load_data",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_data(self):
        """
        Загружает данные из базы данных с помощью функции loader_func.

        Функция loader_func должна возвращать список данных, которые будут отображаться в таблице.

        Если функция loader_func не может загрузить данные (например, если база данных не доступна),
        то выводим сообщение об ошибке и записываем в журнал ошибка.

        :param self: экземпляр класса
        :type self: DynamicListPage
        """
        try:
            self.current_data = self.loader_func(self.current_extra)
            # self.current_data = self.service.get_all()
            self.source_model.update_data(self.current_data)

            self.table_view.clearSelection()

            self.logger.debug(f"Загружено {len(self.current_data)} записей")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception(f"Ошибка загрузки данных: {e}")

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._on_search_text_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_search_text_changed(self, text):
        """
        Обработка события изменения текста в поле поиска.

        Обновляет фильтр поиска в модели proxy_model.

        :param self: экземпляр класса
        :type self: DynamicListPage
        :param text: текст, который был введен в поле поиска
        :type text: str
        """
        # self.proxy_model.setFilterFixedString(text)
        self.proxy_model.set_global_text_filter(text)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._on_selection_changed",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_selection_changed(
        self, 
        selected, 
        deselected
    ):
        """
        Обработка события изменения выбора в таблице.

        Если была выбрана строка, то извлекается DTO, соответствующий выбранной строке,
        иначе, если не была выбрана ни одна строка, то извлекается None.

        Также изменяет доступность кнопки удаления и дополнительной кнопки (если задана).

        :param selected: список выбранных индексов
        :type selected: QItemSelection
        :param deselected: список индексов, которые были сняты с выбора
        :type deselected: QItemSelection
        """
        self.logger.debug(f"selected = {selected}, deselected = {deselected}")
        # Получаем список выбранных индексов
        indexes = selected.indexes()
        self.logger.debug(f"indexes = {indexes}")
        
        # Если был выбран хоть бы один индекс, то извлекается соответствующий DTO
        # иначе, если не была выбрана ни одна строка, то извлекается None
        if indexes:
            proxy_index = indexes[0]
            source_index = self.proxy_model.mapToSource(proxy_index)
            self.logger.debug(f" proxy_index = {proxy_index}, source_index = {source_index}")

            self.selected_dto = self.source_model.get_item_at_row(source_index.row())
            self.delete_btn.setEnabled(True)
            self.logger.debug(f"result = {hasattr(self, 'action_btn')}")
            if hasattr(self, 'action_btn'):
                self.action_btn.setEnabled(True)
        else:
            self.selected_dto = None
            self.delete_btn.setEnabled(False)
            self.logger.debug(f"result = {hasattr(self, 'action_btn')}")
            if hasattr(self, 'action_btn'):
                self.action_btn.setEnabled(False)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._on_row_double_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _on_row_double_clicked(self, index):
        """
        Обработка двойного нажатия на строку в таблице.

        Если была выбрана строка, то извлекается DTO, соответствующий выбранной строке,
        иначе, если не была выбрана ни одна строка, то не происходит ничего.

        :param index: индекс строки, по которой был произведен двойной клик
        :type index: QModelIndex
        """
        self.logger.debug(f'index: {index} result: {not self.edit_on_double_click or not index.isValid()}')
        if not self.edit_on_double_click or not index.isValid():
            return
        
        source_index = self.proxy_model.mapToSource(index)
        dto = self.source_model.get_item_at_row(source_index.row())

        self.logger.debug(f'source_index {source_index} dto: {dto} ')
        if dto:
            self.edit_requested.emit(dto)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._on_delete_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_delete_clicked(self):
        """
        Обработка нажатия кнопки "Удалить".

        Если была выбрана строка, то выводит предупреждение о необходимости подтверждения.
        Если пользователь подтвердил удаление, то извлекается соответствующий сигнал.

        Удаление выбранной записи происходит в соответствующем слоте
        """
        # Проверяем, выбрана ли строка
        if not self.selected_dto:
            return

        # Выводим предупреждение о необходимости подтверждения
        reply = QMessageBox.question(
            self, 
            "Подтверждение",
            "Удалить выбранную запись?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        # Если пользователь подтвердил удаление, то извлекается соответствующий сигнал
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(self.selected_dto)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="DynamicListPage._on_action_clicked",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _on_action_clicked(self):
        """
        Обработка нажатия дополнительной кнопки.

        Если была выбрана строка, то извлекается соответствующий сигнал.
        """
        if self.selected_dto:
            self.action_requested.emit(self.selected_dto)
    
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        """
        Определяем, нужно ли перезагружать данные при входе на страницу.
        
        Если self._needs_refresh == True, то перезагружаем данные.
        self._needs_refresh - это флаг, который указывает, нужно ли перезагружать данные при следующем входе на страницу.
        Он может быть установлен в True в других местах кода, если возникла необходимость перезагрузки данных.
        
        Если передан extra_data и он отличается от self.current_extra, то перезагружаем данные.
        self.current_extra - это словарь, который хранит дополнительные данные, необходимые для работы страницы.
        """
        reload_needed = self._needs_refresh
        if extra_data is not None and extra_data != self.current_extra:
            self.current_extra = extra_data
            reload_needed = True
        
        if reload_needed:
            self._load_data()
            self._needs_refresh = False
