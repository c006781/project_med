# interfaces/gui/gui_window/widgets/paginated_table_model.py
"""
Модель таблицы с поддержкой ленивой подгрузки страниц (пагинации) и динамическими столбцами.

В отличие от DynamicTableModel, эта модель не требует полной замены данных
через update_data. Вместо этого она поддерживает добавление страниц (append_page)
и предоставляет методы для управления общим количеством записей и флагом
возможности подгрузки следующих страниц.

**Цвета строк:**
    - Цвет фона строки привязан к ID сущности (атрибут `id` в DTO).
    - Для хранения цветов используется словарь `_row_colors: Dict[int, QColor]`, где ключ – ID.
    - При сортировке (локальной или серверной) цвета не сбрасываются, так как они следуют за сущностью.
    - Новые строки (временный ID < 0) также могут иметь цвет (зелёный).

**Локальная сортировка:**
    - Метод `set_sort_specs` применяет сортировку к уже загруженным данным.
    - **Важно:** При использовании `PaginatedListPage` локальная сортировка отключена
      при активном fuzzy-фильтре (пункты меню сортировки неактивны). В остальных случаях
      используется серверная сортировка.

**Методы для работы с цветами:**
    - `set_row_color(entity_id, color)` – устанавливает цвет для строки с указанным ID.
    - `clear_row_color(entity_id)` – удаляет цвет для ID.
    - `clear_row_colors()` – удаляет все цвета.

Важно:
    - Этот класс не предназначен для прямого использования в `QSortFilterProxyModel`.
    - Все операции фильтрации и сортировки должны выполняться на стороне сервера.
    - Локальная сортировка (`set_sort_specs`) сортирует только загруженные строки.

Особенности:
    - Использует класс `TableColumn` для описания столбцов (DATA и SYSTEM).
    - Поддерживает чекбоксы (системный столбец `__checkbox__`).
    - Цвет строк привязан к ID сущности (а не к индексу), что позволяет сохранять цвета после сортировки.
    - Ленивая загрузка: методы `can_fetch_more`, `append_page`, `set_total_count`.
    - Сигнал `row_modified` при изменении данных в строке.

Поддерживает:
    - Отображение полей, заданных в columns.
    - Редактирование (если ячейка отмечена как editable).
    - Чекбоксы в отдельном столбце (опционально).
    - Установку цвета фона для строк.
    - Локальную сортировку только по уже загруженным данным.
    - Сигнал row_modified при изменении данных в строке.
    - Пагинацию: добавление страниц, общее количество, canFetchMore.

Атрибуты:
    _data (List[Any]): Загруженные DTO.
    _columns (List[TableColumn]): Список всех столбцов (в порядке отображения).
    _total_count (int): Общее количество записей в БД (с учётом фильтров).
    _checkbox_states (Dict[int, bool]): Состояния чекбоксов (ключ – индекс строки).
    _row_colors (Dict[int, QColor]): Цвета строк (ключ – ID сущности, может быть отрицательным для новых).
    _sort_specs (List[Tuple[int, Qt.SortOrder]]): Спецификации локальной сортировки.

Note:
    При локальной сортировке (`set_sort_specs`) цвета строк остаются привязанными к исходным ID,
    но строки перемещаются. Это ожидаемое поведение, так как цвета должны следовать за сущностью.
"""

import datetime
# from enum import Enum
from typing import (
    List, Dict, Any, 
    Optional, Callable, 
    Tuple, Type, Union, 
    # Type, Union
)
# from collections.abc import Sequence
# from functools import partial


from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.base_table_model import BaseTableModel
from interfaces.gui.gui_window.widgets.delegate.type_delegate import ButtonDelegate
from interfaces.gui.gui_window.widgets.table_column import ColumnType, TableColumn, with_to_dict

from PySide6.QtCore import (
    QModelIndex,  QThread,
    # QObject, QTimer, 
    # QAbstractTableModel, QEvent, 
    Qt, Signal
)
from PySide6.QtGui import QColor



class LoadPageThread(QThread):
    """Поток для асинхронной загрузки страницы данных."""

    finished = Signal(list, int)   # (page_data, total_count)
    error = Signal(str)

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.PaginatedTableModel',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @AppLogger.get_instance(
        name='LoadPageThread',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, service, offset, limit, filters, order_by):
        super().__init__()
        self.service = service
        self.offset = offset
        self.limit = limit
        self.filters = filters
        self.order_by = order_by

    @AppLogger.get_instance(
        name='LoadPageThread',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self):
        self.logger.debug(f"LoadPageThread START: offset={self.offset}, limit={self.limit}")
        try:
            page, total = self.service.get_page_filtered(
                offset=self.offset,
                limit=self.limit,
                filters=self.filters,
                order_by=self.order_by,
            )

            self.logger.debug(f"LoadPageThread got {len(page)} items, total={total}")
            self.finished.emit(page, total)
        except Exception as e:
            self.logger.exception(f"LoadPageThread error: {e}")
            self.error.emit(str(e))



class PaginatedTableModel(BaseTableModel):
    """
    Модель таблицы с поддержкой ленивой подгрузки страниц и динамическими столбцами.

    Использует класс TableColumn для описания столбцов, что позволяет гибко управлять
    видимостью, порядком и системными столбцами (чекбокс, кнопки).

    Атрибуты:
        _data (List[Any]): Загруженные DTO.
        _columns (List[TableColumn]): Список всех столбцов (в порядке отображения).
        _total_count (int): Общее количество записей в БД (с учётом фильтров).
        _checkbox_states (Dict[int, bool]): Состояния чекбоксов (для системного столбца __checkbox__).
        _row_colors (Dict[int, QColor]): Цвета строк.

    Примечание:
        При локальной сортировке цвета строк остаются привязанными к исходным индексам _data,
        что может привести к несоответствию цветов после сортировки. Рекомендуется очищать
        цвета строк перед сортировкой или использовать серверную сортировку.
    """

    row_modified = Signal(int)

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.PaginatedTableModel',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
            return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @property
    def _data(self) -> List[Any]:
        # self.logger.debug(
        #     f"not hasattr(self, '__data') = {not hasattr(self, '__data')} "
        # )
        try:
            return self.__data
        except AttributeError as e:

            # if not hasattr(self, '__data'):
            self.logger.debug(
                f"new self.__data "
            )
            self.__data: List[Any] = [] # загруженные DTO
        return self.__data

    @_data.setter
    def _data(self, value: List[Any]):
        # self.logger.debug(
        #     f"update self.__data "
        #     f"self.__data is None = {getattr(self,'__data',None)} "
        #     f"len(getattr(self,'__data', [])) = {len(getattr(self,'__data', []))} "
        #     f"len(value) = {len(value)} "
        # )
        self.__data = value

    @property
    def _total_count(self) -> int:
        # self.logger.debug(
        #     f"not hasattr(self, '__total_count') = {not hasattr(self, '__total_count')} "
        # )
        try:
            return self.__total_count
        except AttributeError as e:
            self.logger.debug(
                f"new self.__total_count "
            )
            self.__total_count: int = 0  # общее количество (устанавливается извне)
        return self.__total_count

    @_total_count.setter
    def _total_count(self, value: int):
        # self.logger.debug(
        #     f"update self.__total_count "
        #     f"self.__total_count = {getattr(self,'__total_count',None)} "
        #     f"value = {value} "
        # )
        self.__total_count = value

    @property
    def _checkbox_states(self) -> Dict[int, bool]:
        try:
            return self.__checkbox_states
        except AttributeError as e:
            self.logger.debug(
                f"new self.__checkbox_states "
            )
            self.__checkbox_states: Dict[int, bool] = {}    # строка -> состояние
        return self.__checkbox_states

    @_checkbox_states.setter
    def _checkbox_states(self, value: Dict[int, bool]):
        self.__checkbox_states = value

    @property
    def _row_colors(self) -> Dict[int, QColor]:
        try:
            return self.__row_colors
        except AttributeError as e:
            self.logger.debug(
                f"new self.__row_colors "
            )
            self.__row_colors: Dict[int, QColor] = {}       # строка -> цвет
        return self.__row_colors

    @_row_colors.setter
    def _row_colors(self, value: Dict[int, QColor]):
        self.__row_colors = value

    @property
    def _sort_specs(self) -> List:
        try:
            return self.__sort_specs
        except AttributeError as e:
            self.logger.debug(
                f"new self.__sort_specs "
            )
            self.__sort_specs: List = []  # список (column_index, order)
        return self.__sort_specs

    @_sort_specs.setter
    def _sort_specs(self, value: List):
        self.__sort_specs = value

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        columns: List[TableColumn],
        parent=None,
        get_unique_values_func: Optional[Callable[[int], List[str]]] = None,
    ):
        """
        Инициализирует модель.

        Args:
            columns: Список объектов TableColumn (уже включая системные, если нужно).
            parent: Родительский QObject.
            get_unique_values_func: Функция для получения уникальных значений для автодополнения (принимает индекс видимого столбца).
        """

        super().__init__(parent)

        # self.logger = AppLogger.get_instance(
        #     name='gui.PaginatedTableModel',
        #     enable_file_logging='user',
        #     use_name_in_filename=False,
        # )

        # ---- Сортировка ----
        

        # ---- Данные ----
        # self._data: List[Any] = []                     # загруженные DTO
        # self._total_count: int = 0                     # общее количество (устанавливается извне)

        # ---- Столбцы ----
        self._columns: List[TableColumn] = columns     # порядок соответствует отображению
        self._checkbox_column_system_name = '__checkbox__'

        # ---- Чекбоксы ----
        # self._checkbox_states: Dict[int, bool] = {}    # строка -> состояние

        # ---- Цвета строк ----
        # self._row_colors: Dict[int, QColor] = {}       # строка -> цвет

        # ---- Внешние зависимости ----
        self._get_unique_values_func = get_unique_values_func

        # Проверка: если есть чекбокс-столбец, он должен быть системным и с правильным system_name
        self._ensure_checkbox_column()

        self.logger.debug(f"PaginatedTableModel инициализирована с {len(self._columns)} столбцами")

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def update_row_by_id(self, entity_id: int, new_dto: Any) -> Optional[int]:
        """
        Находит строку по ID сущности (включая временные отрицательные ID) и заменяет DTO.
        Возвращает True, если строка найдена и обновлена.
        """
        for row, dto in enumerate(self._data):
            if getattr(dto, 'id', None) == entity_id:
                self.update_row(row, new_dto)
                
                return row
            
        return None

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_by_id(self, entity_id: int, new_dto: Any, update_selected: bool = True) -> bool:
        """
        Обновляет строку в таблице по ID сущности (работает с временными ID).
        Если строка была выбрана, обновляет self.selected_dto.
        """

        if not self.source_model.update_row_by_id(entity_id, new_dto):
            return False
        
        # Обновляем original_data
        self.original_data[new_dto.id] = new_dto
        if entity_id != new_dto.id:
            self.original_data.pop(entity_id, None)

        if update_selected and self.selected_dto and self.selected_dto.id == entity_id:
            self.selected_dto = new_dto

        return True




        # if self.source_model.update_row_by_id(entity_id, new_dto):
        #     # Обновляем original_data – он хранится по индексу, но после update_row_by_id индекс мог измениться?
        #     # original_data привязан к индексу, но это отдельная проблема. Лучше перейти на хранение original_data по ID.
        #     # Для простоты пока найдём строку заново и обновим original_data.
        #     row = self._find_row_by_id(entity_id)
        #     if row >= 0:
        #         self.original_data[row] = new_dto
        #     if update_selected and self.selected_dto and self.selected_dto.id == entity_id:
        #         self.selected_dto = new_dto
        #     return True
        # return False

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _reorder_columns_by_index(self) -> None:
        """Обновляет атрибут order у всех столбцов в соответствии с их текущим индексом в _columns."""
        for idx, col in enumerate(self._columns):
            col.order = idx

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def insert_column(self, column: TableColumn) -> bool:
        """
        Вставляет столбец на позицию, указанную в column.order.
        Если столбец с таким system_name уже существует, возвращает False.
        При вставке все столбцы с индексом >= column.order сдвигаются вправо,
        затем вызывается _reorder_columns_by_index().

        Args:
            column: Объект TableColumn для вставки.

        Returns:
            True, если вставка успешна, иначе False (например, столбец с таким system_name уже существует).
        """
        
        if any(c.system_name == column.system_name for c in self._columns):
            return False
        
        order = column.order

        if order is None:
            order = len(self._columns)

        if  order > len(self._columns): 
            order = len(self._columns)

        if order < 0:
            order = 0

        self.beginInsertColumns(QModelIndex(), order, order)
        self._columns.insert(order, column)
        self._reorder_columns_by_index()
        self.endInsertColumns()

        return True

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def remove_column(self, system_name: str) -> bool:
        """Удаляет столбец с указанным system_name, сдвигает правые столбцы влево."""
        for idx, col in enumerate(self._columns):
            if col.system_name == system_name:
                self.beginRemoveColumns(QModelIndex(), idx, idx)
                del self._columns[idx]
                self._reorder_columns_by_index()
                self.endRemoveColumns()
                return True
        return False

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def move_column(self, system_name: str, new_order: int) -> bool:
        """
        Перемещает столбец на новую позицию new_order.
        new_order – желаемый индекс в списке _columns (0-based).
        """
        # Найти текущий индекс
        current_idx = None
        col_to_move = None
        for idx, col in enumerate(self._columns):
            if col.system_name == system_name:
                current_idx = idx
                col_to_move = col
                break

        if current_idx is None:
            return False
        
        if new_order < 0:
            new_order = 0

        if new_order >= len(self._columns):  
            new_order = len(self._columns) -1 
        
        if current_idx == new_order:
            return True

        self.layoutAboutToBeChanged.emit()
        self._columns.pop(current_idx)
        self._columns.insert(new_order, col_to_move)
        self._reorder_columns_by_index()
        self.layoutChanged.emit()

        return True

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear_own_change(self, entity_id: int) -> None:
        self.logger.debug(
            f"clear_own_change: entity_id={entity_id}, "
            f"текущий статус={self._get_cached_status(entity_id)}"
        )
        self._update_own_change(entity_id, False)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def mark_own_change(self, entity_id: int) -> None:
        self.logger.debug(
            f"mark_own_change: entity_id={entity_id}, "
            f"текущий статус={self._get_cached_status(entity_id)}"
        )
        self._update_own_change(entity_id, True)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_columns(self) -> List[TableColumn]:
        """
        Возвращает список всех столбцов модели (включая скрытые).

        Returns:
            List[TableColumn]: Копия списка _columns.
        """
        return self._columns[:]  # возвращаем копию, чтобы защитить внутренний список

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_system_column(
        self,
        system_name: str,
        title: str,
        order: Optional[int] = None, 
        delegate_class: Optional[Type] = None,
        delegate_args: Optional[Dict] = None,
        visible: bool = True,
        width: Optional[Union[int, Dict[str, Any]]] = None,
        stretch: bool = False,   # новый параметр
    ) -> bool:
        """
        Добавляет системный столбец (не связанный с полем DTO) в модель.
        Позиция вставки определяется параметром order (если None — столбец добавляется в конец).
        Использует метод insert_column, который самостоятельно поддерживает порядок.

        Args:
            system_name: Уникальное системное имя (например, '__checkbox__').
            title: Заголовок столбца.
            order: Желаемый индекс в списке столбцов (0-based). Если None, столбец добавляется в конец.
            delegate_class: Класс делегата для отображения/редактирования.
            delegate_args: Аргументы для делегата.
            visible: Видим ли столбец изначально.
            width: Предпочтительная ширина (если None, то по умолчанию).

        Returns:
            True, если столбец успешно добавлен, False если столбец с таким system_name уже существует.
        """
        # Проверяем уникальность системного имени
        if any(c.system_name == system_name for c in self._columns):
            return False

        # Определяем позицию вставки
        if order is None:
            order = len(self._columns)   # добавляем в конец

        # Ограничиваем допустимые значения
        if order < 0:
            order = 0

        if order > len(self._columns):
            order = len(self._columns)

        width_config = width
        width_config = with_to_dict(width_config)

        if stretch:
            width_config['stretch'] = True
        
        # Создаём объект столбца (системный, не DATA)
        col = TableColumn(
            system_name=system_name,
            title=title,
            column_type=ColumnType.SYSTEM,
            field_name=None,               # системные столбцы не связаны с DTO
            visible=visible,
            order=order,                   # сохраняем желаемую позицию
            delegate_class=delegate_class,
            delegate_args=delegate_args or {},
            # width=width,
            width = width_config if width_config else None,
            editable=False,                # системные столбцы обычно не редактируются
        )

        # Вставляем через общий метод, который сам пересчитает order у всех столбцов
        return self.insert_column(col)
        # # Проверяем, нет ли уже столбца с таким system_name
        # if self.get_column_by_system_name(system_name):
        #     return False

        # col = TableColumn(
        #     system_name=system_name,
        #     title=title,
        #     column_type=ColumnType.SYSTEM,
        #     field_name=None,
        #     visible=visible,
        #     order=position if position is not None else len(self._columns),
        #     delegate_class=delegate_class,
        #     delegate_args=delegate_args or {},
        #     width=width,
        # )
        # # Вставка с обновлением индексов

        # self.logger.debug(
        #     f"position is None  = {position is None} "
        # )
        # if position is None:
        #     position = len(self._columns)

        # self.beginInsertColumns(QModelIndex(), position, position)
        # self._columns.insert(position, col)

        # # Обновляем order у всех столбцов после позиции
        # for i in range(position + 1, len(self._columns)):
        #     self.logger.debug(
        #         f"i  = {i} "
        #     )
        #     self._columns[i].order = i

        # self.endInsertColumns()

        # # # Обновляем маппинг (нужно перестроить _field_by_column)
        # # self._update_column_mapping()  # Обновление маппинга не требуется – поиск столбцов выполняется через _column_appears_for_index

        # return True

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_checkbox_column(
        self, 
        order: int = 0, 
        visible: bool = False,
        width: Optional[Union[int, Dict[str, Any]]] = 30,
        delegate_class = None,
        stretch: bool = False, # для старой версии
    ) -> bool:
        """Добавляет столбец чекбоксов."""

       
        width_config = width
        width_config = with_to_dict(width)

        if width:
            width_config['stretch'] = True 

        return self.add_system_column(
            system_name='__checkbox__',
            title='',
            order=order,
            delegate_class=delegate_class,
            visible=visible,
            # width=width,
            width=width_config,
            stretch=stretch,
        )

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_button_column(
        self,
        system_name: str,
        title: str = "",
        button_text: str = "...",
        order: Optional[int] = None,
        visible: bool = True,
        width: Optional[Union[int, Dict[str, Any]]] = 80,
        stretch: bool = False, # для старой версии
    ) -> bool:
        """Добавляет столбец с кнопкой."""
        # from interfaces.gui.gui_window.widgets.delegate.type_delegate import ButtonDelegate

        width_config = width
        width_config = with_to_dict(width_config)

        if stretch:
            width_config['stretch'] = True

        return self.add_system_column(
            system_name=system_name,
            title=title,
            order=order,
            delegate_class=ButtonDelegate,
            delegate_args={'button_text': button_text},
            visible=visible,
            # width=width,
            width=width_config,
            # stretch=stretch,
        )

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_sort_specs(self, specs: List[Tuple[int, Qt.SortOrder]]) -> None:
        """
        Устанавливает спецификации сортировки (столбец, направление) и применяет сортировку.
        
        Args:
            specs: Список кортежей (видимый_индекс_столбца, порядок).
                Порядок в списке определяет приоритет (первый – первичная сортировка).

        Note:
            Этот метод выполняет сортировку **уже загруженных** данных.
            Для серверной сортировки используйте `reload_with_order_by` в `PaginationMixin`.

        Warning:
            Сортировка сбрасывает цвета строк, если они были привязаны к индексам.
            В текущей реализации цвета привязаны к ID сущности, поэтому они сохраняются.
        """

        self._sort_specs = specs.copy()
        self._apply_sort()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_multi_sorting(self, specs):
        parent = self.parent()

        while parent and not hasattr(parent, 'set_multi_sorting'):
            parent = parent.parent()

        self.logger.debug(
            f"parent is None  = {parent is None} "
        )
        if parent and hasattr(parent, 'set_multi_sorting'):
            parent.set_multi_sorting(specs)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _apply_sort(self) -> None:
        """
        Применяет текущие спецификации сортировки к загруженным данным.

        **Важно:** При локальной сортировке (которая теперь отключена при fuzzy-фильтре)
        цвета строк **не сбрасываются**, так как они привязаны к ID сущности.
        Метод `clear_row_colors()` больше не вызывается.
        """
        self.logger.debug(
            f"not self._sort_specs  = {not self._sort_specs} "
        )
        if not self._sort_specs:
            return
        

        # # Очищаем цвета, так как они привязаны к старым индексам
        # self.clear_row_colors() # При локальной сортировке (которая теперь отключена при fuzzy) это не страшно. Но если вы когда-нибудь включите локальную сортировку для других случаев, цвета будут сбрасываться. 
        # Не очищаем цвета – они привязаны к ID сущности и сохранятся после сортировки

        # Строим ключевые функции для каждой спецификации
        def sort_key(obj):
            key_values = []
            for col_idx, order in self._sort_specs:
                self.logger.debug(
                    f"col_idx  = {col_idx} "
                    f"order is None  = {order is None} "
                )


                # # Находим столбец по видимому индексу
                # visible_idx = 0
                # target_col = None
                # for col in self._columns:
                #     if col.visible:
                #         if visible_idx == col_idx:
                #             target_col = col
                #             break
                #         visible_idx += 1

                # Находим столбец по видимому индексу
                target_col = self._column_appears_for_index(col_idx)


                self.logger.debug(
                    f"target_col is None  = {target_col is None} "
                    f"target_col.column_type != ColumnType.DATA  = {target_col.column_type != ColumnType.DATA} "
                )
                if target_col is None or target_col.column_type != ColumnType.DATA:
                    # Если столбец не DATA, пропускаем (сортировка по нему невозможна)
                    key_values.append((None,))
                    continue

                field_name = target_col.field_name
                value = getattr(obj, field_name, None)

                # Для корректного сравнения None помещаем в конец или начало
                # (для возрастания – None идут последними, для убывания – первыми)
                self.logger.debug(
                    f"order == Qt.AscendingOrder  = {order == Qt.AscendingOrder} "
                )
                if order == Qt.AscendingOrder:
                    key_values.append((value is not None, value))
                else:
                    key_values.append((value is None, value))

            return tuple(key_values)
        
        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=sort_key, reverse=False)  # reverse не нужен, так как знак учтён в ключе
        self.layoutChanged.emit()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_checkbox_state(self, row: int) -> bool:
        """
        Возвращает состояние чекбокса для строки (с учётом видимости столбца).

        Если столбец чекбоксов не виден, всегда возвращает False, так как пользователь
        не может изменить состояние, и модель не должна учитывать эти строки при выделении.

        Args:
            row: Индекс строки в модели.

        Returns:
            True, если чекбокс установлен и столбец видим, иначе False.
        """
        tt = not self.get_column_by_system_name(self._checkbox_column_system_name).visible  # проверить нужность
        self.logger.debug(
            f"not self.get_column_by_system_name(self._checkbox_column_system_name).visible  = {tt} "
        )
        if tt: # проверить нужность
            return False
        
        return self._checkbox_states.get(row, False)

    # ----------------------------------------------------------------------
    # Инициализация и проверка столбцов
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _ensure_checkbox_column(self) -> None:
        """
        Убеждается, что в списке столбцов есть чекбокс-столбец.
        Если он уже есть, но не на первой позиции (order=0), перемещает его в начало.
        После любых изменений порядка уведомляет родительскую страницу о необходимости
        переустановить делегаты (через _reapply_delegates).
        """

        idx_checkbox_column = None

        # Проверяем, есть ли уже столбец чекбокса
        for idx, col in enumerate(self._columns):
            self.logger.debug(
                f"col  = {col} "
                f"col.system_name == self._checkbox_column_system_name  = {col.system_name == self._checkbox_column_system_name} "
            )
            if col.system_name == self._checkbox_column_system_name:
                idx_checkbox_column = idx
                break        
        
        self.logger.debug(
            f"idx_checkbox_column is None  = {idx_checkbox_column is None} "
        )
        if_update = False
        if idx_checkbox_column is None:
            # Если нет – добавляем чекбокс-столбец с order=0 (первая позиция)
            self.add_checkbox_column(order=0, visible=False)
            if_update = True
        else:
            # Если уже есть – убедимся, что он первый
            if idx != 0:
                self.move_column(self._checkbox_column_system_name, 0)
                if_update = True
            
        self.logger.debug(
            f"if_update  = {if_update} "
        )
        if if_update:
            #  Уведомляем родительскую страницу о необходимости обновить делегаты
            if self.parent() and hasattr(self.parent(), '_reapply_delegates'):
                self.parent()._reapply_delegates()
            else:
                self.logger.warning(
                    f"self.parent() and hasattr(self.parent(), '_reapply_delegates')  = False"
                )




        # # Создаём чекбокс-столбец с временным order (не важен)
        # # Добавляем в начало
        # checkbox_col = TableColumn.create_checkbox_column(
        #     order=0   # order=0 означает позицию 0
        # )

        # self.insert_column(checkbox_col)   # позиция берётся из column.order

    # ----------------------------------------------------------------------
    # Работа со столбцами (публичные методы)
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_column_at_visible_index(self, visible_index: int) -> Optional[TableColumn]:
        """
        Возвращает объект TableColumn по индексу видимого столбца.
        
        Args:
            visible_index: Индекс столбца, отображаемого в таблице (0-based).
            
        Returns:
            Объект TableColumn или None, если столбец с таким индексом не существует.
        """

        # visible_idx = 0
        # # Находим объект TableColumn по видимому индексу
        # for col in self._columns:
        #     if col.visible:
        #         if visible_idx == visible_index:
        #             return col
                
        #         visible_idx += 1
        # return None

        # Находим столбец по видимому индексу
        target_col = self._column_appears_for_index(visible_index)

        return target_col

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def column_count(self) -> int:
        """Возвращает общее количество столбцов (включая скрытые)."""

        return len(self._columns)

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def visible_column_count(self) -> int:
        """Возвращает количество видимых столбцов."""

        return sum(1 for col in self._columns if col.visible)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_column_index(self, system_name: str) -> int:
        """
        Возвращает индекс столбца по системному имени (в модели, с учётом скрытых).

        Args:
            system_name: Уникальное системное имя столбца (например, '__checkbox__').

        Returns:
            Индекс столбца в списке _columns (0-based) или -1, если столбец не найден.
        """

        for idx, col in enumerate(self._columns):
            self.logger.debug(
                f"idx  = {idx} "
                f"col.system_name == system_name  = {col.system_name == system_name} "
            )
            if col.system_name == system_name:
                return idx
            
        return -1

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_visible_column_index(self, system_name: str) -> int:
        """
        Возвращает индекс видимого столбца по системному имени.

        Учитываются только видимые столбцы, порядок их следования.
        Если столбец скрыт или не существует, возвращается -1.

        Args:
            system_name: Уникальное системное имя столбца.

        Returns:
            Индекс видимого столбца (0-based) или -1.
        """

        # visible_idx = 0

        # for col in self._columns:
        #     if col.visible:
        #         if col.system_name == system_name:
        #             return visible_idx
                
        #         visible_idx += 1

        # Находим номер видимого столбеца по системному имени
        target_col = self._column_appears_for_index(system_name, if_return_visible_idx=True)

        self.logger.debug(
            f"target_col is None  = {target_col is None} "
        )
        return -1 if target_col is None else target_col

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_column_by_system_name(self, system_name: str) -> Optional[TableColumn]:
        """
        Возвращает объект столбца по системному имени.

        Args:
            system_name: Уникальное системное имя столбца.

        Returns:
            Объект TableColumn или None, если столбец не найден.
        """

        # for col in self._columns:
        #     if col.system_name == system_name:
        #         return col
            
        # return None
    
        # Находим столбец по системному имени
        target_col = self._column_appears_for_index(system_name, is_visible=False)

        return target_col

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_column_visible(self, system_name: str, visible: bool) -> None:
        """
        Изменяет видимость столбца.

        Меняет флаг visible в соответствующем TableColumn и испускает сигнал layoutChanged, который заставляет таблицу перерисовать заголовки, но НЕ сбрасывает данные.

        Args:
            system_name: Уникальное системное имя столбца.
            visible: True – показать столбец, False – скрыть.

        Returns:
            None
        """

        col = self.get_column_by_system_name(system_name)
        self.logger.debug(
            f"col is None  = {col is None} "
            f"col is None or col.visible == visible  = {col is None or col.visible == visible} "
        )
        if col is None or col.visible == visible:
            return
        
        col.visible = visible
        # layoutChanged перерисовывает заголовки и обновляет количество столбцов,
        # но данные остаются на месте (в отличие от beginResetModel).
        self.layoutChanged.emit()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_field_name_at_visible_column(self, visible_index: int) -> Optional[str]:
        """
        По индексу видимого столбца возвращает имя поля DTO (для DATA-столбцов) или None.

        Args:
            visible_index: Индекс видимого столбца (0-based).

        Returns:
            Имя поля (например, 'last_name') или None для системных столбцов (чекбокс, кнопка).
        """

        # visible_idx = 0
        # for col in self._columns:
        #     if col.visible:
        #         if visible_idx == visible_index:

        #             return col.field_name if col.column_type == ColumnType.DATA else None
                
        #         visible_idx += 1

        # return None

        # Находим видимый столбец по системному имени
        target_col = self._column_appears_for_index(visible_index)
        self.logger.debug(
            f"target_col is None  = {target_col is None} "
        )
        if target_col is None:
            return None

        self.logger.debug(
            f"target_col.column_type == ColumnType.DATA  = {target_col.column_type == ColumnType.DATA} "
        )
        target_col = target_col.field_name if target_col.column_type == ColumnType.DATA else None

        return target_col

    # ----------------------------------------------------------------------
    # Реализация абстрактных методов BaseTableModel
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_item_at_row(self, row: int) -> Optional[Any]:
        """
        Возвращает DTO для указанной строки.

        Args:
            row: Индекс строки (0-based).

        Returns:
            DTO или None, если строка не существует.
        """
        _len_data = len(self._data)
        self.logger.debug(
            f"row  = {row} "
            f"len(self._data)  = {_len_data} "
        )
        if 0 <= row < _len_data:
            return self._data[row]
        
        return None

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_all_data(self) -> List[Any]:
        """
        Возвращает копию списка всех загруженных DTO.

        Returns:
            Список DTO (копия, не ссылка на внутренний список).
        """
        
        return self._data[:]

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def update_row(self, row: int, new_dto: Any) -> None:
        """
        Заменяет DTO в указанной строке на новый.

        После замены испускается сигнал dataChanged для всей строки.

        Args:
            row: Индекс строки.
            new_dto: Новый DTO.

        Returns:
            None
        """
        _len_data = len(self._data)
        self.logger.debug(
            f"row  = {row} "
            f"len(self._data)  = {_len_data} "
        )
        if row < 0 or row >= _len_data:
            self.logger.warning(f"update_row: неверный индекс {row}")
            return
        
        self._data[row] = new_dto
        # top_left = self.index(row, 0)
        # bottom_right = self.index(row, self.columnCount() - 1)
        # self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.EditRole])
        self._redrawing_lines(row, [Qt.DisplayRole, Qt.EditRole])

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_row(self, dto: Any) -> int:
        """
        Добавляет новую строку в конец модели.

        Args:
            dto: DTO новой записи.

        Returns:
            Индекс добавленной строки.
        """

        row = len(self._data)
        self.beginInsertRows(QModelIndex(), row, row)
        self._data.append(dto)
        self._checkbox_states[row] = False
        self.endInsertRows()
        self.row_modified.emit(row)

        # Если есть активные спецификации сортировки, применяем их

        self.logger.debug(
            f"self._sort_specs is None  = {self._sort_specs is None} "
        )
        if self._sort_specs:
            self._apply_sort()
            # После сортировки исходный индекс row может измениться, но цвет строки будет восстановлен через layoutChanged
            # Возвращаем новый индекс? Сложно, но вызывающий код обычно не полагается на него,
            # кроме как для установки цвета строки, который перекрасится через _on_model_layout_changed.
            # Поэтому возвращаем исходный row – он всё равно будет неактуален, но это не критично.

        return row
    
    def insert_row_at(self, row: int, dto: Any) -> None:
        """
        Вставляет новую строку в указанную позицию модели.

        **Назначение:**
            Позволяет вставить DTO в произвольное место (не только в конец), сдвигая
            все последующие строки вниз. Корректно обновляет состояния чекбоксов.

        **Алгоритм:**
            1. Проверяет допустимость индекса `row`. Если `row` выходит за границы
            [0, rowCount], вставляет в конец.
            2. Вызывает `beginInsertRows` с позицией `row`.
            3. Вставляет DTO во внутренний список `_data`.
            4. Сдвигает состояния чекбоксов для всех строк, начиная с `row`, на +1.
            5. Вызывает `endInsertRows`.

        **Важно:**
            - Метод НЕ испускает сигнал `row_modified`, так как новая строка ещё
            не имеет черновиков (изменения будут помечены отдельно через реестр).
            - После вставки необходимо вручную зарегистрировать строку в реестре
            черновиков и вызвать `mark_own_change` (это делает вызывающий код).

        **Параметры:**
            row (int): Индекс, по которому вставляется строка (0‑based).
                    Допустимые значения от 0 до `rowCount()` включительно.
            dto (Any): DTO новой записи (обычно с временным отрицательным ID).

        **Возвращает:**
            None

        **Пример:**
            >>> model.insert_row_at(0, new_dto)  # вставить в начало
            >>> model.insert_row_at(model.rowCount(), new_dto)  # вставить в конец
        """
        # Проверка границ
        if row < 0 or row > len(self._data):
            row = len(self._data)

        self.beginInsertRows(QModelIndex(), row, row)

        self._data.insert(row, dto)

        # вертикальный Сдвигаем чекбоксы
        new_states = {}
        for r, state in self._checkbox_states.items(): 
            if r >= row:
                new_states[r + 1] = state
            else:
                new_states[r] = state

        self._checkbox_states = new_states

        self.endInsertRows()
        # Сигнал row_modified для новой строки не испускаем, она будет помечена через реестр
    
    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def remove_row(self, row: int) -> Optional[Any]:
        """
        Удаляет строку из модели.

        Args:
            row: Индекс удаляемой строки.

        Returns:
            Удалённый DTO или None, если строка не существовала.
        """
        _len_data = len(self._data)
        self.logger.debug(
            f"row  = {row} "
            f"len(self._data)  = {_len_data} "
        )
        if row < 0 or row >= _len_data:
            return None

        # Получаем DTO и ID до удаления
        dto = self._data[row]
        entity_id = getattr(dto, 'id', None)

        self.beginRemoveRows(QModelIndex(), row, row)
        removed = self._data.pop(row)

        # Сдвигаем чекбоксы (они привязаны к индексам строк)
        new_states = {}
        for r, state in self._checkbox_states.items():

            self.logger.debug(
                f"row  = {row} "
                f"r = {r} "
            )
            if r > row:
                new_states[r - 1] = state
            elif r < row:
                new_states[r] = state

        self._checkbox_states = new_states


        # Удаляем цвет для этого ID (если он был)
        self.logger.debug(
            f"entity_id is not None  = {entity_id is not None} "
        )
        if entity_id is not None:
            self.clear_row_color(entity_id)

        # Если цвета хранятся по индексам (старый способ), сдвигаем их (но лучше не надо)
        # Для обратной совместимости оставим сдвиг, но он уже не нужен, так как цвета по ID   
        # # Сдвигаем цвета (если есть)
        # if row in self._row_colors:
        #     del self._row_colors[row]

        # for r in list(self._row_colors.keys()):
        #     if r > row:
        #         self._row_colors[r - 1] = self._row_colors[r]
        #         del self._row_colors[r]

        self.endRemoveRows()

        return removed

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear(self) -> None:
        """
        Полностью очищает модель: удаляет все данные, сбрасывает чекбоксы и цвета.

        Returns:
            None
        """

        self.beginResetModel()
        self._data.clear()
        self._checkbox_states.clear()
        self._row_colors.clear()

        self._total_count = 0
        self._sort_specs = []
        self.endResetModel()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_column_visible(self, visible: bool) -> None:
        """
        Устанавливает флаг видимости чекбокс-столбца в модели.

        Args:
            visible: True – показать столбец, False – скрыть.

        Returns:
            None
        """
        
        col = self.get_column_by_system_name(self._checkbox_column_system_name)
        self.logger.debug(
            f"col is None  = {col is None} "
        )
        if col is None or col.visible == visible:
            return
        
        col.visible = visible
        self.layoutChanged.emit()   # перестроит всю модель (но данные останутся)

        # Уведомляем родительскую страницу о необходимости обновить ширину столбцов
        if self.parent() and hasattr(self.parent(), '_apply_column_widths'): # на всякий случай
            self.parent()._apply_column_widths()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_state(self, row: int, checked: bool) -> None:
        """
        Устанавливает состояние чекбокса для строки (только если столбец видим).

        Args:
            row: Индекс строки.
            checked: True – установить чекбокс, False – снять.

        Returns:
            None
        """
        tt = not self.get_column_by_system_name(self._checkbox_column_system_name).visible
        self.logger.debug(
            f"not self.get_column_by_system_name(self._checkbox_column_system_name).visible  = {tt} "
        )
        if tt:
            return

        _len_data = len(self._data)
        self.logger.debug(
            f"row = {row} "
            f"len(self._data) = {_len_data} "
        )
        if row < 0 or row >= _len_data:
            return
        
        self._checkbox_states[row] = checked

        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [Qt.CheckStateRole])

    # def set_row_color(self, row: int, color: QColor) -> None:
    #     """
    #     Устанавливает цвет фона для строки.

    #     Args:
    #         row: Индекс строки.
    #         color: Цвет фона.

    #     Returns:
    #         None
    #     """

    #     if 0 <= row < len(self._data):
    #         self._row_colors[row] = color
    #         top_left = self.index(row, 0)
    #         bottom_right = self.index(row, self.columnCount() - 1)
    #         self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_row_color(self, entity_id: int, color: QColor) -> None:
        """
        Устанавливает цвет фона для строки по ID сущности.

        Args:
            entity_id: ID сущности (из DTO). Может быть отрицательным для новых строк.
            color: Цвет фона.

        Note:
            Цвет сохраняется в словаре `_row_colors` по ключу `entity_id`.
            При отрисовке строки цвет извлекается по ID текущего DTO.
            Этот способ позволяет сохранять цвета после сортировки (в отличие от привязки к индексу).
        """

        # self.logger.debug(
        #     f"entity_id is None = {entity_id is None} "
        #     f"color is None = {color is None} "
        # )
        if (entity_id is None) or (color is None):
            return

        self._row_colors[entity_id] = color

        # Обновляем все строки, где DTO имеет этот ID (обычно одна строка)
        for row, dto in enumerate(self._data):

            # self.logger.debug(
            #     f"row = {row} "
            #     f"getattr(dto, 'id', None) = {getattr(dto, 'id', None)} "
            # )
            if getattr(dto, 'id', None) == entity_id:
                self._redrawing_lines(row)
                break
    
    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear_row_color(self, entity_id: int) -> None:
        """
        Удаляет цвет для указанной сущности и обновляет строку.

        Args:
            entity_id: ID сущности, цвет которой нужно удалить.
        """

        self.logger.debug(
            f"entity_id = {entity_id} "
            f"entity_id not in self._row_colors = {entity_id not in self._row_colors} "
        )
        if entity_id not in self._row_colors:
            return

        del self._row_colors[entity_id]

        # Находим строку с этим ID и перерисовываем
        for row, dto in enumerate(self._data):
            self.logger.debug(
                f"row = {row} "
                f"getattr(dto, 'id', None) = {getattr(dto, 'id', None)} "
            )
            if getattr(dto, 'id', None) == entity_id:
                # top_left = self.index(row, 0)
                # bottom_right = self.index(row, self.columnCount() - 1)
                # self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])
                self._redrawing_lines(row)
                break

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear_row_colors(self) -> None:
        """
        Сбрасывает все установленные цвета строк.

        Очищает словарь _row_colors и испускает сигнал dataChanged для всех строк,
        чтобы представление перерисовало их с новым фоном (без цвета).
        """
        self.logger.debug(
            f"not self._row_colors = {not self._row_colors} "
        )
        if not self._row_colors:
            return

        self._row_colors.clear()

        rowCount = self.rowCount()
        self.logger.debug(
            f"self.rowCount() = {rowCount} "
        )
        if rowCount > 0:
            # top_left = self.index(0, 0)
            # bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            # self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])
            self._redrawing_lines()

        # """Сбрасывает все установленные цвета строк."""

        # self._row_colors.clear()

        # # Перерисовываем все строки, чтобы убрать цвета
        # if self.rowCount() > 0:
        #     self._redrawing_lines()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _redrawing_lines(
        self,
        row: Optional[int] = None,
        roles: Optional[List[Qt.ItemDataRole]] = None
    ) -> None:
        """
        Перерисовывает строку по индексу.

        Args:
            row: Индекс строки.
            roles: Список ролей, которые нужно перерисовать.
                None = [Qt.BackgroundRole]

        Returns:
            None
        """

        self.logger.debug(
            f"roles is None = {roles is None} "
        )
        if roles is None:
            roles = [Qt.BackgroundRole]

        self.logger.debug(
            f"row is not None = {row is not None} "
        )
        top_left = self.index(
            row if row is not None else 0
            , 0
        )
        bottom_right = self.index(
            row if row is not None else (self.rowCount() - 1),
            self.columnCount() - 1
        )
        self.dataChanged.emit(top_left, bottom_right, roles)

    # ----------------------------------------------------------------------
    # Пагинация
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def can_fetch_more(self) -> bool:
        """
        Определяет, можно ли загрузить ещё страницы (есть ли незагруженные записи).

        Returns:
            True, если общее количество записей больше количества уже загруженных, иначе False.
        """

        return self._total_count > 0 and len(self._data) < self._total_count

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def append_page(self, data: List[Any]) -> None:
        """
        Добавляет очередную страницу данных в конец модели.

        Args:
            data: Список DTO новой страницы.

        Returns:
            None
        """

        # self.logger.debug(
        #     f"not data = {not data} "
        # )
        if not data:
            return
        
        start = len(self._data)
        self.logger.debug(
            f"len(data) = {len(data)} "
            f"len(self._data) = {start} "
        )
        self.beginInsertRows(QModelIndex(), start, start + len(data) - 1)
        self._data.extend(data)

        _len_data = len(self._data)
        self.logger.debug(
            f"start = {start} "
            f"len(self._data) = {_len_data} "
        )
        for idx in range(start, _len_data):
            # self.logger.debug(
            #     f"idx = {idx} "
            #     f"idx not in self._checkbox_states = {idx not in self._checkbox_states} "
            # )
            if idx not in self._checkbox_states:
                self._checkbox_states[idx] = False

        self.endInsertRows()

        self.logger.debug(
            f"append_page: rows added, new rowCount = {len(self._data)} "
        )
        # Принудительное уведомление представления (добавлено)
        # Если есть активные спецификации сортировки, применяем их
        self.logger.debug(
            f"self._sort_specs is None = {self._sort_specs is None} "
        )
        if self._sort_specs:
            self._apply_sort()

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_total_count(self, total: int) -> None:
        """
        Устанавливает общее количество записей в БД (с учётом фильтров).

        Args:
            total: Общее количество записей.

        Returns:
            None
        """

        self._total_count = total

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def total_count(self) -> int:
        """
        Возвращает текущее общее количество записей в БД (с учётом фильтров).

        Returns:
            Общее количество записей (устанавливается через set_total_count).
            Если значение не было установлено, возвращает 0.
        """

        return self._total_count

    # ----------------------------------------------------------------------
    # Методы QAbstractTableModel
    # ----------------------------------------------------------------------

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Возвращает количество строк в модели.

        Args:
            parent: Родительский индекс (не используется для плоских таблиц).

        Returns:
            Количество загруженных строк.
        """
        cnt = len(self._data)
        # self.logger.debug(
        #     f"len(self._data) = {cnt}"
        # )
        return cnt

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Возвращает количество видимых столбцов.

        Args:
            parent: Родительский индекс (не используется).

        Returns:
            Количество видимых столбцов (системные и DATA).
        """

        return self.visible_column_count()

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def _column_appears_for_index(
        self, 
        value_col: Union[int, str, ColumnType], 
        is_visible: bool = True,
        if_return_visible_idx: bool = False
    ) -> Optional[Union[int, TableColumn]]:
        """
        Возвращает первый столбец, у которого совпадает:
            - порядковый индекс (visible_idx) если value_col int
            - system_name если value_col str
            - column_type если value_col ColumnType
        При этом учитывается только видимость (если is_visible=True, то только visible=True).

        Args:
            value_col: Искомое значение (индекс, имя или тип).
            is_visible: Если True, учитываются только видимые столбцы;
                        если False, учитываются все столбцы.

        Returns:
            Найденный столбец или None.
        """

        if not isinstance(value_col, (int, str, ColumnType)):
            raise TypeError(f"value_col должен быть int, str или ColumnType, получен {type(value_col)}")

        # Находим столбец по видимому индексу
        visible_idx = 0

        thec_value = None

        # Находим объект TableColumn по видимому индексу

        # self.logger.debug(
        #     f"len(self._columns) = {len(self._columns)} "
        # )
        for col in self._columns:
            thec_visible = getattr(col, 'visible', False)
            if thec_visible or (not is_visible):
                if isinstance(value_col, int):
                    thec_value = visible_idx   
                elif isinstance(value_col, str): 
                    thec_value = col.system_name  
                elif isinstance(value_col, ColumnType): 
                    thec_value = col.column_type  
                
                if thec_value == value_col:
                    return col if not if_return_visible_idx else visible_idx
                    
                visible_idx += 1

        return None

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def _get_line_color_DTO(
        self, 
        role: int, 
        row: int, 
        target_col
    ) -> Any:
        """
        Возвращает данные для ячейки таблицы в зависимости от роли, используя DTO из строки.

        Метод предназначен для использования внутри `data()` и учитывает:
            - Цвет фона строки (привязан к ID сущности, а не к индексу).
            - Отображаемое значение (DisplayRole) с форматированием дат и времени.
            - Редактируемое значение (EditRole) – исходный объект.
            - Выравнивание текста (TextAlignmentRole) – числа вправо, остальное влево.
            - Пользовательские данные для сортировки (UserRole).

        Args:
            role (int): Роль данных из Qt (например, Qt.DisplayRole, Qt.BackgroundRole и т.д.).
            row (int): Индекс строки в модели (source model).
            target_col (TableColumn): Объект столбца, для которого запрашиваются данные.
                Содержит информацию о типе столбца, имени поля, типе данных и т.д.

        Returns:
            Any: Значение в зависимости от роли:
                - Qt.BackgroundRole → QColor цвет фона строки (или None, если цвет не задан).
                - Qt.DisplayRole → отформатированная строка (даты в ISO, время в HH:MM, иначе str).
                - Qt.EditRole → исходное значение из DTO (может быть None).
                - Qt.TextAlignmentRole → Qt.AlignmentFlag (правый для чисел, иначе левый).
                - Qt.UserRole → исходное значение (для сортировки).
                - В остальных случаях → None.

        Примечания:
            - Цвет строки определяется по ID сущности из DTO (атрибут `id`).
              Если ID отсутствует или цвет не задан, возвращается None.
            - Для системных столбцов (например, чекбокс) этот метод не вызывается –
              они обрабатываются отдельно в `data()`.

        Пример:
            >>> # Внутри data():
            >>> if role == Qt.BackgroundRole:
            ...     return self._get_line_color_DTO(role, row, target_col)
            >>> # получим цвет фона строки
        """
        # # Цвет строки
        # if role == Qt.BackgroundRole:
        #     return self._row_colors.get(row)

        # Цвет строки (по ID сущности)

        # self.logger.debug(
        #     f"role == Qt.BackgroundRole = {role == Qt.BackgroundRole} "
        # )
        if role == Qt.BackgroundRole:
            dto = self._data[row]
            entity_id = getattr(dto, 'id', None)
            # self.logger.debug(
            #     f"entity_id is not None = {entity_id is not None} "
            # )
            if entity_id is not None:
                return self._row_colors.get(entity_id)
            return None

        # Получаем значение из DTO
        # self.logger.debug(
        #     f"target_col.column_type == ColumnType.DATA = {target_col.column_type == ColumnType.DATA} "
        #     f"target_col.field_name is None = {target_col.field_name is None} "
        # )
        if target_col.column_type == ColumnType.DATA and target_col.field_name:
            value = getattr(self._data[row], target_col.field_name, None)
        else:
            value = None  # для других системных столбцов (кнопок и т.д.) данные не хранятся

        # self.logger.debug(
        #     f"role == Qt.DisplayRole = {role == Qt.DisplayRole} "
        # )
        if role == Qt.DisplayRole:
            if value is None:
                # return ""
                # Для столбцов с типом datetime.date возвращаем маску
                if target_col and target_col.data_type == datetime.date:
                    return "    -  -  "
                return ""
            
            if isinstance(value, datetime.date):
                return value.isoformat()
            
            if isinstance(value, datetime.time):
                return value.strftime("%H:%M")
            
            return str(value)

        # self.logger.debug(
        #     f"role == Qt.EditRole = {role == Qt.EditRole} "
        # )
        if role == Qt.EditRole:
            return value

        # self.logger.debug(
        #     f"role == Qt.TextAlignmentRole = {role == Qt.TextAlignmentRole} "
        # )
        if role == Qt.TextAlignmentRole:
            if target_col.data_type in (int, float):
                return Qt.AlignRight | Qt.AlignVCenter
            
            return Qt.AlignLeft | Qt.AlignVCenter

        # self.logger.debug(
        #     f"role == Qt.UserRole = {role == Qt.UserRole} "
        # )
        if role == Qt.UserRole:
            return value

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """
        Возвращает данные для ячейки в зависимости от роли.

        Поддерживаемые роли:
            - Qt.DisplayRole: текстовое представление (форматирует даты и время в ISO-строки).
            - Qt.EditRole: исходное значение DTO.
            - Qt.BackgroundRole: цвет фона строки.
            - Qt.TextAlignmentRole: выравнивание (числа – вправо, остальное – влево).
            - Qt.UserRole: исходное значение для сортировки.
            - Qt.CheckStateRole: возвращает состояние чекбокса (если столбец видим).
        
        Args:
            index: Индекс ячейки.
            role: Роль данных.

        Returns:
            Значение в зависимости от роли или None.
        """

        isValid = not index.isValid()
        # self.logger.debug(
        #     f"not index.isValid() = {isValid} "
        # )
        if isValid:
            return None

        row = index.row()
        visible_col = index.column()
        _len_data = len(self._data)
        # self.logger.debug(
        #     f"row = {row} "
        #     f"len(self._data) = {_len_data} "
        # )
        if row >= _len_data:
            return None

        # Находим столбец по видимому индексу
        target_col = self._column_appears_for_index(visible_col)

        # self.logger.debug(
        #     f"target_col is None = {target_col is None} "
        # )
        if target_col is None:
            return None

        # Чекбокс-столбец (системный)
        # self.logger.debug(
        #     f"target_col.system_name == self._checkbox_column_system_name = {target_col.system_name == self._checkbox_column_system_name} "
        # )
        if target_col.system_name == self._checkbox_column_system_name:

            # self.logger.debug(
            #     f"role == Qt.CheckStateRole = {role == Qt.CheckStateRole} "
            # )
            if role == Qt.CheckStateRole:
                return Qt.Checked if self._checkbox_states.get(row, False) else Qt.Unchecked
            
            if role == Qt.BackgroundRole:
                dto = self._data[row]
                entity_id = getattr(dto, 'id', None)
                if entity_id is not None:
                    return self._row_colors.get(entity_id)
                return None
            
            return None

        # Цвет строки из DTO
        return self._get_line_color_DTO(role, row, target_col)

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = Qt.EditRole
    ) -> bool:
        """
        Устанавливает новое значение в ячейку (для редактирования).

        Args:
            index: Индекс ячейки.
            value: Новое значение.
            role: Роль (должен быть Qt.EditRole или Qt.CheckStateRole).

        Returns:
            True, если значение было установлено, иначе False.
        """

        isValid = not index.isValid()
        self.logger.debug(
            f"not index.isValid() = {isValid} "
        )
        if isValid:
            return False

        row = index.row()
        visible_col = index.column()
        _len_data = len(self._data)
        self.logger.debug(
            f"row = {row} "
            f"len(self._data) = {_len_data} "
        )
        if row >= _len_data:
            return False

        # # Находим столбец по видимому индексу
        # visible_idx = 0
        # target_col = None
        # for col in self._columns:
        #     if col.visible:
        #         if visible_idx == visible_col:
        #             target_col = col
        #             break

        #         visible_idx += 1

        # Находим столбец по видимому индексу
        target_col = self._column_appears_for_index(visible_col)

        self.logger.debug(
            f"target_col is None = {target_col is None} "
        )
        if target_col is None:
            return False

        # Чекбокс
        self.logger.debug(
            f"target_col.system_name == self._checkbox_column_system_name = {target_col.system_name == self._checkbox_column_system_name} "
        )
        if target_col.system_name == self._checkbox_column_system_name:
            self.logger.debug(
                f"role == Qt.CheckStateRole = {role == Qt.CheckStateRole} "
            )
            if role == Qt.CheckStateRole:
                checked = (value == Qt.Checked.value)
                old = self._checkbox_states.get(row, False)
                self.logger.debug(
                    f"old = {old} "
                    f"checked = {checked} "
                )
                if old != checked:
                    self._checkbox_states[row] = checked
                    self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.CheckStateRole])

                return True
            
            return False

        self.logger.debug(
            f"role != Qt.EditRole = {role != Qt.EditRole} "
        )
        if role != Qt.EditRole:
            return False

        self.logger.debug(
            f"target_col.column_type != ColumnType.DATA = {target_col.column_type != ColumnType.DATA} "
            f"not target_col.editable = {not target_col.editable} "
        )
        if target_col.column_type != ColumnType.DATA or not target_col.editable:
            return False

        # Обновляем значение в DTO
        item = self._data[row]
        old_value = getattr(item, target_col.field_name, None)
        self.logger.debug(
            f"old_value == value = {old_value == value} "
        )
        if old_value == value:
            return True

        # Преобразование типа (если нужно)
        self.logger.debug(
            f"target_col.data_type is None = {target_col.data_type is None} "
            f"value is not None = {value is not None} "
        )
        if target_col.data_type and value is not None:
            try:
                if target_col.data_type == int:
                    value = int(value)
                elif target_col.data_type == datetime.date and isinstance(value, str):
                    value = datetime.date.fromisoformat(value)
                elif target_col.data_type == datetime.time and isinstance(value, str):
                    value = datetime.time.fromisoformat(value)
                # можно добавить другие

            except (ValueError, TypeError):
                return False

        setattr(item, target_col.field_name, value)
        self.dataChanged.emit(index, index, [role])
        self.logger.debug(f"setData: row={row}, col={target_col.field_name}, new value={value}")
        self.row_modified.emit(row)

        return True

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Возвращает флаги для ячейки (редактируемость, выбираемость, чекбоксы).

        Для чекбокс-столбца: флаги пользовательского чекбокса.
        Для DATA-столбца: редактируем, если `editable == True`.

        Args:
            index: Индекс ячейки.

        Returns:
            Комбинация флагов Qt.ItemFlag.
        """
        isValid = not index.isValid()
        # self.logger.debug(
        #     f"not index.isValid() = {isValid} "
        # )
        if isValid:
            return Qt.NoItemFlags

        row = index.row()
        _len_data = len(self._data)
        # self.logger.debug(
        #     f"row = {row} "
        #     f"len(self._data) = {_len_data} "
        # )
        if row >= _len_data:
            return Qt.NoItemFlags

        visible_col = index.column()

        # visible_idx = 0
        # target_col = None
        # for col in self._columns:
        #     if col.visible:
        #         if visible_idx == visible_col:
        #             target_col = col
        #             break

        #         visible_idx += 1
        
        # Находим столбец по видимому индексу
        target_col = self._column_appears_for_index(visible_col)

        # self.logger.debug(
        #     f"target_col is None = {target_col is None} "
        # )
        if target_col is None:
            return Qt.NoItemFlags

        # self.logger.debug(
        #     f"target_col.system_name == self._checkbox_column_system_name = {target_col.system_name == self._checkbox_column_system_name} "
        # )
        if target_col.system_name == self._checkbox_column_system_name:
            return Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        # self.logger.debug(
        #     f"target_col.column_type == ColumnType.DATA = {target_col.column_type == ColumnType.DATA} "
        #     f"target_col.editable = {target_col.editable} "
        # )
        if target_col.column_type == ColumnType.DATA and target_col.editable:
            flags |= Qt.ItemIsEditable

        return flags

    # @AppLogger.get_instance(
    #     name='PaginatedTableModel',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def headerData(
        self, 
        section: int, 
        orientation: Qt.Orientation, 
        role: int = Qt.DisplayRole
    ) -> Any:
        """
        Возвращает данные для заголовка таблицы (горизонтального или вертикального).

        Для горизонтальных заголовков возвращает название столбца (из `TableColumn.title`).
        Для вертикальных заголовков возвращает номер строки (начиная с 1).

        Args:
            section (int): Индекс секции (столбца для горизонтального, строки для вертикального).
            orientation (Qt.Orientation): Qt.Horizontal или Qt.Vertical.
            role (int): Роль данных (по умолчанию Qt.DisplayRole).

        Returns:
            Any: Для горизонтальных заголовков – строка с названием столбца или None;
                для вертикальных заголовков – целое число (номер строки) или None;
                для других ролей (например, TextAlignmentRole) – соответствующее значение.
        """

        # if orientation != Qt.Horizontal:
        #     return None


        # if role != Qt.DisplayRole:
        #     return None

        # Горизонтальные заголовки (как было)
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                target_col = self._column_appears_for_index(section)
                return None if target_col is None else target_col.title
            return None
        
        # Вертикальные заголовки – номера строк
        if orientation == Qt.Vertical:
            if role == Qt.DisplayRole:
                # section – индекс строки в модели (0-based)
                return section + 1          # 1, 2, 3, ...
            if role == Qt.TextAlignmentRole:
                return Qt.AlignRight | Qt.AlignVCenter   # выравнивание номера
        return None

        # Находим столбец по видимому индексу
        target_col = self._column_appears_for_index(section)

        return None if target_col is None else target_col.title

    @AppLogger.get_instance(
        name='PaginatedTableModel',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        """Сортировка по одному столбцу (сохраняется обратная совместимость)."""
        self.set_sort_specs([(column, order)])

        # """
        # Сортирует только загруженные данные (локально).

        # ВНИМАНИЕ: цвета строк будут привязаны к прежним индексам и могут не соответствовать данным после сортировки. Рекомендуется очищать цвета перед сортировкой или использовать серверную сортировку.

        # Args:
        #     column: Индекс видимого столбца.
        #     order: Порядок сортировки (AscendingOrder или DescendingOrder).

        # Returns:
        #     None
        # """

        # # нужно обязательно сделать: метод sort реализован с очисткой цветов. Это приводит к тому, что при сортировке все цвета сбрасываются. Возможно, вы хотели сохранить цвета для отсортированных строк (например, зелёный для новых строк должен перемещаться вместе с ними)

        # # Очищаем цвета, так как они привязаны к старым индексам
        # self.clear_row_colors()

        # # Находим столбец по видимому индексу
        # visible_idx = 0
        # target_col = None
        # for col in self._columns:
        #     if col.visible:
        #         if visible_idx == column:
        #             target_col = col
        #             break

        #         visible_idx += 1

        # if target_col is None or target_col.column_type != ColumnType.DATA:
        #     return

        # field_name = target_col.field_name
        # reverse = (order == Qt.DescendingOrder)
        # self.layoutAboutToBeChanged.emit()
        # self._data.sort(key=lambda obj: (getattr(obj, field_name, None) is not None, getattr(obj, field_name, None)), reverse=reverse)
        # self.layoutChanged.emit()
