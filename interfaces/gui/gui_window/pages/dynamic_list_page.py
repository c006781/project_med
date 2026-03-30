# interfaces/gui/gui_window/pages/dynamic_list_page.py

from typing import (
    List,
    Optional, 
    Callable, 
    Any, 
    Set, 
    Dict,
    Union,
    get_args,
    get_origin
)
import datetime 

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
    Qt, 
    Signal, 
    Slot, 
    QModelIndex
)
from PySide6.QtGui import QColor



class DynamicListPage(BasePage):
    """
    Универсальная страница списка с поддержкой inline-редактирования.
    Добавлена возможность отложенного сохранения изменений через кнопку «Сохранить изменения».
    Поддерживает два режима:
        - обычный режим: двойной клик по строке вызывает action_requested (переход на другой фрейм),
          редактирование выполняется через формы.
        - режим редактирования: включается кнопкой-переключателем, появляются inline-кнопки
          «Добавить строку», «Удалить строку», «Сохранить изменения», двойной клик начинает редактирование ячейки.
    """


    add_requested = Signal() # сигнал для добавления (можно не использовать, если добавляем строку напрямую)
    edit_requested = Signal(object) # сигнал для открытия формы редактирования
    delete_requested = Signal(object) # сигнал для удаления (с подтверждением)
    action_requested = Signal(object)  # дополнительное действие

    # detail_requested = Signal(object) # сигнал для перехода к детальной странице (двойной клик
        
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
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
        # edit_on_double_click=True,  # True, если редактирование должно быть доступно при двойном нажатии на строке
        parent=None,  # родительский виджет
        exclude_columns=None,
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
        # self.edit_on_double_click = edit_on_double_click

        self.exclude_columns = exclude_columns or []



        # Словарь для отслеживания изменённых строк:
        # modified_rows: set of row indices, которые были изменены пользователем (но ещё не сохранены)
        self.modified_rows: Set[int] = set()
        # deleted_rows: set of row indices, помеченные на удаление (соответствующие DTO будут удалены при сохранении)
        self.deleted_rows: Set[int] = set()
        # new_rows: set of row indices, которые были добавлены через inline-добавление (пока не реализовано)
        self.new_rows: Set[int] = set()
        # Сопоставление индекса строки с исходным DTO для восстановления при отмене (опционально)
        self.original_data: Dict[int, Any] = {}

        self.edit_mode: bool = False # Режим редактирования (по умолчанию выключен)

        self.main_layout = QVBoxLayout(self) # сохраним основной layout как атрибут
        self.columns = self._build_columns()   # строим список колонок

        self.current_data = []  # список данных, которые сейчас отображаются на странице  # список DTO
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
        level = AppLogger._parse_log_level('DEBUG')
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

            if field_name in self.exclude_columns:
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
            ).get(
                'order',
                len(self.field_configs)
                # 0
            )
        )

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_filter_requested(
        self, 
        column: int, 
        operator: str, 
        value
    ):
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
        level = AppLogger._parse_log_level('DEBUG')
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
        level = AppLogger._parse_log_level('DEBUG')
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
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_needs_refresh(self, value=True):
        """
        Устанавливает флаг _needs_refresh.

        :param value: True, если данные нужно перезагружать при следующем входе на страницу
        """
        self._needs_refresh = value
    
    # ----------------------- Построение интерфейса -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_top_panel(self):
        """
        Создаёт верхнюю панель с кнопками и полем поиска.

        Верхняя панель содержит кнопки "Добавить", "Удалить", "Обновить" и поле поиска.
        и поле поиска. Кнопка "Добавить" добавляет новый элемент в список,
        Кнопки:
        "Добавить" добавляет новый элемент в список,
        "Удалить" удаляет выбранный элемент из списка,
        "Обновить" обновляет  список элементов. Поле поиска позволяет искать элементы в списке по тексту, введенному в поле.
        """

        # Верхняя панель
        top_layout = QHBoxLayout()

        # Кнопка переключения режима редактирования (переключатель)
        self.edit_mode_btn = QPushButton("Режим редактирования")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.toggled.connect(self._on_edit_mode_toggled)
        top_layout.addWidget(self.edit_mode_btn)

        # Кнопка "Добавить" (открыть форму)
        self.add_btn = QPushButton(self.add_action_text)
        self.add_btn.clicked.connect(self.add_requested.emit)
        top_layout.addWidget(self.add_btn)

        # Кнопка "Редактировать" (открыть форму)
        self.edit_btn = QPushButton("Редактировать")
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.edit_btn.setEnabled(False)
        top_layout.addWidget(self.edit_btn)

        # Кнопка "Удалить"
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        top_layout.addWidget(self.delete_btn)


        # Inline-кнопки (показываются только в режиме редактирования)
        self.inline_add_btn = QPushButton("Добавить строку")
        self.inline_add_btn.clicked.connect(self._add_inline_row)
        self.inline_add_btn.setVisible(False)
        top_layout.addWidget(self.inline_add_btn)

        self.inline_delete_btn = QPushButton("Удалить строку")
        self.inline_delete_btn.clicked.connect(self._mark_selected_for_deletion)
        self.inline_delete_btn.setVisible(False)
        top_layout.addWidget(self.inline_delete_btn)

        # Кнопка сохранения изменений (inline)
        self.save_changes_btn = QPushButton("Сохранить изменения")
        self.save_changes_btn.clicked.connect(self._save_changes)
        self.save_changes_btn.setEnabled(False)
        top_layout.addWidget(self.save_changes_btn)

        # Кнопка "Действие" (если она была указана) (например, "Приёмы")
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
        level = AppLogger._parse_log_level('DEBUG')
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

        # Изначально двойной клик не редактирует ячейки (режим не редактирования)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Модель таблицы
        self.source_model = DynamicTableModel(self.current_data, self.columns)
        # Подключаем сигнал изменения строки для отслеживания изменений
        self.source_model.row_modified.connect(self._on_row_modified)

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
        level = AppLogger._parse_log_level('DEBUG')
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
        level = AppLogger._parse_log_level('DEBUG')
    )  
    def _setup_delegates(self):
        """
        Устанавливает делегаты для колонок, у которых есть choices.
        
        Делегат создается для каждой колонки, у которой есть choices.
        Делегат будет использоваться для отображения комбобокса в соответствующей колонке.
        """
        for col_idx, col_info in enumerate(self.columns):
            choices = col_info.get('choices')

            self.logger.debug(f'if choices : {not (choices is None)}')    
            if choices:
                delegate = ComboBoxDelegate(self.table_view, choices)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)

    # ----------------------- Управление режимом редактирования -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )  
    @Slot(bool)
    def _on_edit_mode_toggled(self, checked: bool):
        """
        Обработчик переключения режима редактирования.
        При включении режима:
            - показываем inline-кнопки
            - скрываем кнопки форм (добавить, редактировать, удалить)
            - разрешаем редактирование ячеек по двойному клику
            - двойной клик больше не вызывает переход на другой фрейм
        При выключении режима:
            - если есть несохранённые изменения, спрашиваем, сохранить ли их
            - после ответа скрываем inline-кнопки и показываем кнопки форм
            - отключаем редактирование ячеек
            - двойной клик снова вызывает переход на другой фрейм
        """
                
        if not checked and (self.modified_rows or self.deleted_rows or self.new_rows):
            # Есть несохранённые изменения – спрашиваем
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_changes()
                # После сохранения выходим из режима
                self.edit_mode = False
            elif reply == QMessageBox.StandardButton.No:
                # Откатываем изменения: перезагружаем данные
                self._load_data()
                # Сбрасываем флаги
                self.modified_rows.clear()
                self.deleted_rows.clear()
                self.new_rows.clear()
                self._update_save_button_state()
                self.edit_mode = False
            else:
                # Cancel – остаёмся в режиме редактирования
                return


        else:
            self.edit_mode = checked

        # Управление видимостью кнопок
        
        if self.edit_mode:
            # Показываем inline-кнопки
            self.inline_add_btn.setVisible(True)
            self.inline_delete_btn.setVisible(True)
            self.save_changes_btn.setVisible(True)
            # Скрываем кнопки форм
            self.add_btn.setVisible(False)
            self.edit_btn.setVisible(False)
            self.delete_btn.setVisible(False)
            # Скрываем кнопку обновления и дополнительную кнопку действия
            self.refresh_btn.setVisible(False)
            if hasattr(self, 'action_btn') and self.action_btn:
                self.action_btn.setVisible(False)
            # Включаем редактирование ячеек
            self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked)
            # Отключаем переход по двойному клику
            self.table_view.doubleClicked.disconnect(self._on_row_double_clicked)
        else:
            # Скрываем inline-кнопки
            self.inline_add_btn.setVisible(False)
            self.inline_delete_btn.setVisible(False)
            self.save_changes_btn.setVisible(False)
            # Показываем кнопки форм
            self.add_btn.setVisible(True)
            self.edit_btn.setVisible(True)
            self.delete_btn.setVisible(True)
            # Показываем кнопку обновления и дополнительную кнопку действия
            self.refresh_btn.setVisible(True)
            if hasattr(self, 'action_btn') and self.action_btn:
                self.action_btn.setVisible(True)
            # Отключаем редактирование ячеек
            self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
            # Включаем переход по двойному клику
            self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Сбрасываем выделение, чтобы избежать путаницы
        self.table_view.clearSelection()
        self.selected_dto = None
        self.delete_btn.setEnabled(False)
        self.edit_btn.setEnabled(False)

        if hasattr(self, 'action_btn'):
            self.action_btn.setEnabled(False)

        self.logger.debug(f"Режим редактирования: {'включён' if self.edit_mode else 'выключен'}")

    # ----------------------- Обработка изменений строк -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_row_modified(self, row: int):
        """
        Слот, вызываемый при изменении данных в строке модели.
        Помечает строку как изменённую и обновляет цвет.
        """

        self.logger.debug(f"Строка {row} изменена")

        # Пропускаем, если строка уже помечена на удаление
        if row in self.deleted_rows:
            return
            
        self.modified_rows.add(row)
        self._update_row_color(row)
        self._update_save_button_state()

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_color(self, row: int):
        """
        Устанавливает цвет фона для строки в зависимости от статуса:
        - новая: светло-зелёный
        - изменённая: светло-жёлтый
        - удалённая: светло-красный
        - обычная: белый
        """
        self.logger.debug(f"Обновление цвета строки {row}")
        # source_row = self.proxy_model.mapToSource(self.proxy_model.index(row, 0)).row()
        # Получаем индекс в исходной модели
        proxy_index = self.proxy_model.index(row, 0)
        self.logger.debug(f"if not proxy_index.isValid() {not proxy_index.isValid()}")
        if not proxy_index.isValid():
            return
        
        source_row = self.proxy_model.mapToSource(proxy_index).row()
        self.logger.debug(f"if source_row == -1 {source_row == -1}")
        if source_row == -1:
            return

        if row in self.deleted_rows:
            color = QColor(255, 200, 200)   # красный
        elif row in self.new_rows:
            color = QColor(200, 255, 200)   # зелёный
        elif row in self.modified_rows:
            color = QColor(255, 255, 180)   # жёлтый
        else:
            color = QColor(255, 255, 255)   # белый

        
        self.logger.debug(f"Обновление цвета строки {row} - {color.name()}")

        # # Применяем цвет ко всем ячейкам строки
        # for col in range(self.table_view.model().columnCount()):
        #     idx = self.table_view.model().index(row, col)
        #     self.logger.debug(f"Обновление цвета ячейки {row},{idx.column()} - {color.name()}")
        #     self.table_view.model().setData(idx, color, Qt.ItemDataRole.BackgroundRole)
        self.source_model.set_row_color(source_row, color)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_save_button_state(self):
        """Включает/отключает кнопку сохранения в зависимости от наличия изменений."""
        has_changes = bool(self.modified_rows or self.deleted_rows or self.new_rows)
        self.save_changes_btn.setEnabled(has_changes)

    # ----------------------- Inline-операции -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _add_inline_row(self):
        """
        Добавляет новую строку в таблицу для inline-создания.
        Создаёт DTO с начальными значениями для полей, отображаемых в таблице,
        а также подставляет значения из current_extra, если они есть.
        """
        defaults = {}
        # Перебираем колонки, которые отображаются в таблице
        for col_info in self.columns:
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})
            # Пропускаем виртуальные и скрытые поля
            if config.get('virtual', False) or config.get('hidden', False):
                continue

            field_info = self.dto_class.model_fields.get(field_name)
            if field_info is None:
                continue

            # Определяем реальный тип поля (с учётом Optional)
            field_type = field_info.annotation
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                field_type = next((arg for arg in args if arg is not type(None)), None)

            # Устанавливаем значение по умолчанию в зависимости от типа
            if field_type is None:
                defaults[field_name] = None
            elif field_type == str:
                defaults[field_name] = ""
            elif field_type == int:
                defaults[field_name] = 0
            elif field_type == datetime.date:
                defaults[field_name] = datetime.date.today()
            elif field_type == datetime.time:
                defaults[field_name] = datetime.time(0, 0)
            elif field_type == bool:
                defaults[field_name] = False
            else:
                defaults[field_name] = None

        # Дополнительно подставляем значения из current_extra, если они есть и соответствуют полям DTO
        if self.current_extra:
            for key, value in self.current_extra.items():
                if key in self.dto_class.model_fields and key not in defaults:
                    defaults[key] = value

        try:
            new_dto = self.dto_class(**defaults)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать новую строку: {e}")
            self.logger.exception(f"Ошибка создания пустого DTO: {e}")
            return

        row = self.source_model.add_row(new_dto)
        self.new_rows.add(row)
        self._update_row_color(row)
        self._update_save_button_state()

        proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))
        if proxy_index.isValid():
            self.table_view.scrollTo(proxy_index)

        self.logger.info(f"Добавлена новая строка (индекс {row})")

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _mark_selected_for_deletion(self):
        """
        Помечает выбранную строку на удаление (inline-удаление).
        Строка становится красной, будет удалена при сохранении.
        """
        if not self.selected_dto:
            return

        proxy_index = self.table_view.currentIndex()
        if not proxy_index.isValid():
            return
        
        row = proxy_index.row()

        if row in self.deleted_rows:
            return

        # Добавляем в множество удалённых
        self.deleted_rows.add(row)
        # Если строка была изменена или новая, убираем из соответствующих множеств
        self.modified_rows.discard(row)
        self.new_rows.discard(row)
        self._update_row_color(row)
        self._update_save_button_state()

        # Очищаем выделение
        self.table_view.clearSelection()
        self.selected_dto = None
        self.delete_btn.setEnabled(False)
        if hasattr(self, 'action_btn'):
            self.action_btn.setEnabled(False)

        self.logger.info(f"Строка {row} помечена на удаление")


    # ----------------------- Сохранение изменений -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _save_changes(self):
        """
        Сохраняет все накопленные изменения (новые, изменённые, удалённые) в БД.
        """
        if not (self.modified_rows or self.deleted_rows or self.new_rows):
            return

        # Запрашиваем подтверждение
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Сохранить все изменения? Будут обновлены, добавлены и удалены записи в БД.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Блокируем таблицу на время сохранения
        self.table_view.setEnabled(False)
        self.save_changes_btn.setEnabled(False)

        try:
            # 1. Удаление помеченных строк
            # Собираем ID для удаления, удаляем из модели и из БД
            for row in sorted(self.deleted_rows, reverse=True):
                dto = self.source_model.get_item_at_row(row)

                if dto and hasattr(dto, 'id') and dto.id is not None:
                    # Удаляем через сервис
                    self.service.delete(dto.id)
                    self.logger.info(f"Удалена запись ID={dto.id}")
                    
                # Удаляем строку из модели
                self.source_model.remove_row(row),
            
            self.deleted_rows.clear()

            # 2. Обновление изменённых строк
            for row in self.modified_rows:
                dto = self.source_model.get_item_at_row(row)

                if dto and hasattr(dto, 'id') and dto.id is not None:
                    # Обновляем существующую запись
                    updated = self.service.update(dto)
                    # Заменяем DTO в модели на обновлённый (на случай, если сервис вернул новый объект)
                    self.source_model.update_row(row, updated)
                    self.logger.info(f"Обновлена запись ID={updated.id}"),
                
            self.modified_rows.clear()

            # 3. Обработка новых строк
            for row in self.new_rows:
                dto = self.source_model.get_item_at_row(row)
                # Это новая запись (добавленная через inline, если реализуем)
                if dto:
                    created = self.service.create(dto)
                    self.source_model.update_row(row, created)
                    self.logger.info(f"Создана новая запись ID={created.id}")

            self.new_rows.clear()

            # 4. Перезагружаем данные, чтобы синхронизировать с БД (на случай изменений, сделанных сервисом)
            self._load_data()

            QMessageBox.information(self, "Успех", "Изменения сохранены.")
        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении изменений: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изменения: {e}")
        finally:
            self.table_view.setEnabled(True)
            self._update_save_button_state()

    # ----------------------- Действия с выделенной строкой (формы) -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
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
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_edit_clicked(self):
        """Открывает форму редактирования для выбранной строки."""
        if self.selected_dto:
            self.edit_requested.emit(self.selected_dto)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    # def _on_delete_clicked(self):
    #     """
    #     Обработка нажатия кнопки "Удалить".

    #     Если была выбрана строка, то выводит предупреждение о необходимости подтверждения.
    #     Если пользователь подтвердил удаление, то извлекается соответствующий сигнал.

    #     Удаление выбранной записи происходит в соответствующем слоте
    #     """

    #     # Проверяем, выбрана ли строка
    #     if not self.selected_dto:
    #         return

    #     # Выводим предупреждение о необходимости подтверждения
    #     reply = QMessageBox.question(
    #         self, 
    #         "Подтверждение",
    #         "Удалить выбранную запись? Она будет помечена на удаление и удалена после сохранения.",
    #         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    #     )

    #     # Если пользователь подтвердил удаление, то извлекается соответствующий сигнал
    #     if reply == QMessageBox.StandardButton.Yes:
    #         self.delete_requested.emit(self.selected_dto)

    #     # Находим индекс строки в прокси-модели
    #     proxy_index = self.table_view.currentIndex()
    #     if not proxy_index.isValid():
    #         return
        
    #     row = proxy_index.row()
    #     # Если строка уже удалена, ничего не делаем
    #     if row in self.deleted_rows:
    #         return

    #     # Добавляем в множество удалённых
    #     self.deleted_rows.add(row)
    #     # Если строка была изменена или новая, убираем из соответствующих множеств
    #     self.modified_rows.discard(row)
    #     self.new_rows.discard(row)
    #     # Обновляем цвет строки
    #     self._update_row_color(row)
    #     self._update_save_button_state()
    #     # Очищаем выделение
    #     self.table_view.clearSelection()
    #     self.selected_dto = None
    #     self.delete_btn.setEnabled(False)
        
    #     if hasattr(self, 'action_btn'):
    #         self.action_btn.setEnabled(False)

    #     self.logger.info(f"Строка {row} помечена на удаление")
    def _on_delete_clicked(self):
        """
        Удаление через форму (с подтверждением). Используется, когда режим редактирования выключен.
        """

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
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )      
    @Slot()
    def _on_action_clicked(self):
        """Дополнительное действие (например, переход к списку приёмов)."""

        if self.selected_dto:
            self.action_requested.emit(self.selected_dto)

    # ----------------------- Загрузка данных и обработка выделения -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
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

            self.source_model.clear_row_colors()

            # Сбрасываем все отслеживаемые изменения
            self.modified_rows.clear()
            self.deleted_rows.clear()
            self.new_rows.clear()
            self.original_data.clear()
            self._update_save_button_state()

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
        level = AppLogger._parse_log_level('DEBUG')
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
        # self.logger.debug(f"selected = {selected}, deselected = {deselected}")
        # Получаем список выбранных индексов
        indexes = selected.indexes()
        self.logger.debug(f"indexes = {indexes}")

        def _btn(selected_dto):
            """
            Устанавливает доступность кнопок "Удалить", "Редактировать" и "Действие" в зависимости от наличия выбранной строки.

            Если была выбрана строка, то кнопки становятся доступными, иначе - недоступными.

            :param selected_dto: выбранный DTO или None, если не была выбрана строка
            :type selected_dto: DTO or None
            """

            self.selected_dto = selected_dto

            thec = not(selected_dto is None)
            self.delete_btn.setEnabled(thec)
            self.edit_btn.setEnabled(thec)
            self.logger.debug(f"hasattr(self, 'action_btn') : {hasattr(self, 'action_btn')}")
            if hasattr(self, 'action_btn'):
                self.action_btn.setEnabled(thec)

        
        # Если был выбран хоть бы один индекс, то извлекается соответствующий DTO
        # иначе, если не была выбрана ни одна строка, то извлекается None
        if indexes:
            proxy_index = indexes[0]
            source_index = self.proxy_model.mapToSource(proxy_index)
            # self.logger.debug(f" proxy_index = {proxy_index}, source_index = {source_index}")

            _btn(
                selected_dto = self.source_model.get_item_at_row(source_index.row())
            )
        else:
            _btn(
                selected_dto = None
            )        

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_row_double_clicked(self, index):
        # """
        # Обработка двойного нажатия на строку в таблице.

        # Если была выбрана строка, то извлекается DTO, соответствующий выбранной строке,
        # иначе, если не была выбрана ни одна строка, то не происходит ничего.

        # :param index: индекс строки, по которой был произведен двойной клик
        # :type index: QModelIndex
        # """

        # self.logger.debug(
        #     f'index: {index} result: {not self.edit_on_double_click or not index.isValid()}'
        # )
        # # if not self.edit_on_double_click or not index.isValid():
        # if  not index.isValid():
        #     return
        
        # source_index = self.proxy_model.mapToSource(index)
        # dto = self.source_model.get_item_at_row(source_index.row())

        # self.logger.debug(f'source_index {source_index} dto: {type(dto)}')
        # if dto:
        #     # self.edit_requested.emit(dto)
        #     self.detail_requested.emit(dto)
        """
        Обработка двойного клика в обычном режиме (не редактирование).
        Вызывает action_requested для перехода на следующий фрейм.
        """
        if not self.edit_mode and index.isValid():
            source_index = self.proxy_model.mapToSource(index)
            dto = self.source_model.get_item_at_row(source_index.row())
            if dto:
                self.action_requested.emit(dto)
                
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
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
        level = AppLogger._parse_log_level('DEBUG')
    )
    def showEvent(self, event):
        """
        Обработка события отображения страницы.

        Подключает функцию super().showEvent(), а также подключает сигнал selectionChanged к слоту _on_selection_changed,
        если он не был подключен ранее. Это необходимо, чтобы слушатель _on_selection_changed срабатывал,
        когда пользователь выбирает строку в таблице.
        """
        super().showEvent(event)

        # Подключаем сигнал selectionChanged к слоту _on_selection_changed

        self.logger.debug(f'not self._selection_connected : {not self._selection_connected}')

        if not self._selection_connected:
            selection_model = self.table_view.selectionModel()
            
            self.logger.debug(f'if selection_model is not None : {selection_model is not None}')
            if selection_model is not None:
                # Подключаем сигнал selectionChanged к слоту _on_selection_changed
                selection_model.selectionChanged.connect(self._on_selection_changed)
                self._selection_connected = True

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
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
        
        self.logger.debug(
            f'if extra_data is not None and extra_data != self.current_extra : {extra_data is not None and extra_data != self.current_extra}'
        )
        if extra_data is not None and extra_data != self.current_extra:
            self.current_extra = extra_data
            reload_needed = True

        self.logger.debug(
            f'if reload_needed : {not (reload_needed is None)}'
        )
        if reload_needed:
            self._load_data()
            self._needs_refresh = False

    # ----------------------- Вспомогательные методы для inline-добавления (опционально) -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def add_new_row(self, dto: Any = None):
        """
        Добавляет новую пустую строку в таблицу (для inline-создания).
        Если dto не передан, создаётся пустой DTO через конструктор.
        """
        if dto is None:
            # Создаём пустой DTO (все поля None, кроме обязательных)
            dto = self.dto_class()

        row = self.source_model.add_row(dto)
        self.new_rows.add(row)
        self._update_row_color(row)
        self._update_save_button_state()

        # Прокручиваем к новой строке
        proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))

        self.logger.debug(
            f'if proxy_index.isValid() : {proxy_index.isValid()}'
        )
        if proxy_index.isValid():
            self.table_view.scrollTo(proxy_index)