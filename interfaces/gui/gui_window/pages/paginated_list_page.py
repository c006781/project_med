# interfaces/gui/gui_window/pages/paginated_list_page.py
"""
Новая страница списка с пагинацией, заменяющая DynamicListPage.
"""

import datetime

from app.draft.draft_registry import DraftRegistry

from interfaces.gui.gui_window.mixins.draft_tree_mixin import DraftTreeMixin
from interfaces.gui.gui_window.mixins.pagination_mixin import PaginationMixin
from interfaces.gui.gui_window.mixins.selection_mixin import SelectionMixin
from interfaces.gui.gui_window.mixins.edit_mode_mixin import EditModeMixin
from interfaces.gui.gui_window.mixins.data_change_mixin import DataChangeMixin
from interfaces.gui.gui_window.mixins.filter_mixin import FilterMixin
from interfaces.gui.gui_window.mixins.ui_mixin import UIMixin
from interfaces.gui.gui_window.mixins.controller_mixin import ControllerMixin

from interfaces.gui.gui_window.pages.base_page import BasePage

from interfaces.gui.gui_window.widgets.paginated_table_model import PaginatedTableModel
from interfaces.gui.gui_window.widgets.table_column import ColumnType, TableColumn

from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
    CompleterStringDelegate,
    DatePickerDelegate,
    StringDelegate,
    TextPopupDelegate,
    TimePickerDelegate,
    BoolDelegate,
    ComboBoxDelegate,
)

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QColor

class PaginatedListPage(
    BasePage,
    PaginationMixin,
    SelectionMixin,
    EditModeMixin,
    DataChangeMixin,
    FilterMixin,
    UIMixin,
    ControllerMixin,
    DraftTreeMixin,  
):
    """
    Универсальная страница списка с пагинацией, фильтрацией и редактированием.
    """

    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    action_requested = Signal(object)

    def __init__(
        self,
        service,
        dto_class,
        field_configs,
        page_title="Список",
        add_action_text="Добавить",
        action_button_text=None,
        parent=None,
        exclude_columns=None,
        entity_type: str = "",

    ):
        super().__init__(parent)

        self.service = service
        self.dto_class = dto_class
        self.field_configs = field_configs
        self.page_title = page_title
        self.add_action_text = add_action_text
        self.action_button_text = action_button_text
        self.exclude_columns = exclude_columns or []

        self._entity_type = entity_type

        DataChangeMixin.__init__(self)
        self.edit_mode = False

        self._build_columns()
        self._create_model()
        self.setup_ui()
        self.setup_pagination(service, page_size=50, extra_rows=5)
        self.setup_filtering(self.filter_bar, self.table_view)
        self.reload_with_filters(None)

        # Инициализация реестра черновиков (глобальный, передаётся из главного окна)
        self._draft_registry = DraftRegistry(self)

        # Установка ключа для текущего компонента (будет установлен позже, при выборе строки)
        self._draft_component_id = None

        # Создание реестра черновиков для фото и других дочерних виджетов
        self._setup_draft_system()

        # Подключаем сигнал изменения черновиков к перекраске строки
        self.draft_modified_changed.connect(self._on_draft_modified_changed)
        
        # Подключаем сигнал выделения строки (если ещё не подключён)
        selection_model = self.table_view.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed_for_draft)

    # ------------------------------------------------------------------
    # Обработка изменения черновиков
    # ------------------------------------------------------------------

    def _on_draft_modified_changed(self, has_draft: bool):
        """
        Слот, вызываемый при изменении состояния черновиков в поддереве (сигнал draft_modified_changed).
        Перекрашивает текущую строку и при необходимости добавляет/удаляет ID из modified_ids.
        """
        if not self.selected_dto:
            return
        
        entity_id = self.selected_dto.id
        row = self._find_row_by_id(entity_id)
        if row >= 0:
            self._update_row_color(row)
            if has_draft:
                # Если появились черновики – добавляем ID в modified_ids (если ещё не добавлен)
                if entity_id not in self.modified_ids:
                    self._add_to_modified(entity_id)

            else:
                # Если черновиков больше нет – проверяем, не вернулись ли данные к оригиналу
                # и если нет других изменений, удаляем из modified_ids
                if not self._has_any_changes(entity_id):
                    if entity_id in self.modified_ids:
                        self._remove_from_modified(entity_id)

    def _has_any_changes(self, entity_id: int) -> bool:
        """
        Проверяет, есть ли изменения в строке (основные поля или черновики потомков).
        """
        # Проверка основных полей
        row = self._find_row_by_id(entity_id)
        if row < 0:
            return False
        
        dto = self.source_model.get_item_at_row(row)
        original = self.original_data.get(row)
        if original and dto.model_dump() != original.model_dump():
            return True
        
        # Проверка черновиков потомков через свойство миксина
        return self.has_descendant_drafts

    # ------------------------------------------------------------------
    # Обработка изменения выделения строки
    # ------------------------------------------------------------------

    def _on_selection_changed_for_draft(self, selected, deselected):
        """
        Обработчик изменения выделения в таблице.
        Обновляет self.selected_dto и перекрашивает новую строку.
        """
        new_dto = self.get_current_selected_dto()
        if new_dto == self.selected_dto:
            return
        
        self.selected_dto = new_dto
        if new_dto:
            row = self._find_row_by_id(new_dto.id)
            if row >= 0:
                self._update_row_color(row)

    def _clear_drafts(self):
        """Очищает черновики (заглушка, переопределяется в наследниках)."""
        if hasattr(self, '_draft_registry'):
            self._draft_registry.clear()

    def _get_child_service(self, child_name: str = None):
        """Возвращает сервис для дочернего компонента (переопределяется в наследниках)."""
        return None

    def _setup_draft_system(self):
        """Создаёт дочерние компоненты, реализующие IEditableComponent."""
        # Пример: фото-виджет (будет создан в AppointmentListPage)
        pass

    def on_enter(self, extra_data=None):
        """При входе на страницу обновляет ключ черновика для текущей строки."""
        super().on_enter(extra_data)
        if self.selected_dto:
            self._update_draft_key_for_selected()

    def _save_all_changes_impl(self) -> bool:
        # 1. Сохраняем дочерние черновики (фото и т.д.)
        # for child in self._children_components:
        #     if hasattr(child, 'apply'):
        #         child.apply(
        #             self._draft_registry, 
        #             parent_id=self.get_current_selected_dto().id, 
        #             service=self._get_child_service()
        #         )
        # self._save_changes()
        self._save_child_drafts()
        
        # 2. Сохраняем строки таблицы (родительский метод)
        return super()._save_all_changes_impl()

    def _update_draft_key_for_selected(self):
        """Обновляет ключ черновика текущего компонента на основе ID выбранной строки."""
        if not self.selected_dto:
            return
        
        new_key = f"{self._entity_type}:{self.selected_dto.id}:"


        if new_key != self._draft_component_id:
            if self._draft_component_id:
                self._draft_registry.unsubscribe(self._draft_component_id, self._on_registry_changed)
            self._draft_component_id = new_key
            self.setup_draft_tree(self._draft_registry, new_key)
            # Перезагружаем данные из реестра в дочерние виджеты
            self._load_drafts_for_children()

    def _load_drafts_for_children(self):
        """Загружает черновики в дочерние компоненты."""
        for child in self._children_components:
            if hasattr(child, 'load_from_registry'):
                child.load_from_registry(self._draft_registry)

    def _on_row_modified(self, row: int):
        """Обработчик изменения строки – теперь также проверяем дочерние черновики."""
        super()._on_row_modified(row)
        # Если изменения есть в дочерних – помечаем строку как изменённую
        if self._draft_modified:
            self._add_to_modified(self.selected_dto.id)

    def _update_row_color(self, row: int):
        """Обновляет цвет строки с учётом дочерних черновиков."""
        
        dto = self.source_model.get_item_at_row(row)
        if dto is None:
            return
        
        if dto.id is None or dto.id < 0:
            color = QColor(200, 255, 200) if row in self.new_rows else QColor(255, 255, 255)

        else:
            if dto.id in self.deleted_ids:
                color = QColor(255, 200, 200)

            elif dto.id in self.modified_ids or self._draft_modified:
                color = QColor(255, 255, 180)

            else:
                color = QColor(255, 255, 255)

        self.source_model.set_row_color(row, color)

    # def _save_changes(self, if_question: bool = True) -> bool:
    # def _save_changes(self, if_question: bool = True):
    def _save_child_drafts(self, if_question: bool = True):
        """Сохраняет изменения: сначала дочерние поддеревья, затем основные поля."""
        # Сохраняем дочерние черновики
        for child in self._children_components:
            if hasattr(child, 'apply'):
                child.apply(
                    self._draft_registry, 
                    parent_id=self.selected_dto.id, 
                    service=self._get_child_service()
                )

        # # Затем основные поля
        # return super()._save_changes(if_question) # непонятно нужно ли...

    def _build_columns(self):
        # from interfaces.gui.gui_window.widgets.table_column import TableColumn
        self.columns = []
        for field_name, config in self.field_configs.items():
            if field_name in self.exclude_columns:
                continue
            if config.get('hidden', False):
                continue
            col = TableColumn(
                system_name=field_name,
                title=config.get('title', field_name.replace('_', ' ').title()),
                data_type=self.dto_class.model_fields[field_name].annotation,
                editable=config.get('editable', False),
                order=config.get('order', 0),
                choices=config.get('choices'),
                autocomplete=config.get('autocomplete', False),
                input_mask=config.get('input_mask'),
            )
            self.columns.append(col)
        self.columns.sort(key=lambda c: c.order)

    def _create_model(self):
        # from interfaces.gui.gui_window.widgets.paginated_table_model import PaginatedTableModel
        self.source_model = PaginatedTableModel(self.columns, parent=self)
        self.table_view.setModel(self.source_model)
        self.source_model.row_modified.connect(self._on_row_modified)

    def _setup_delegates(self) -> None:
        """
        Устанавливает делегаты для столбцов на основе field_configs и типа данных.
        Адаптировано для PaginatedTableModel.
        """
        # from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
        #     CompleterStringDelegate,
        #     DatePickerDelegate,
        #     StringDelegate,
        #     TextPopupDelegate,
        #     TimePickerDelegate,
        #     BoolDelegate,
        #     ComboBoxDelegate,
        # )
        # from interfaces.gui.gui_window.widgets.table_column import ColumnType
        # import datetime

        type_delegate_map = {
            datetime.date: DatePickerDelegate,
            datetime.time: TimePickerDelegate,
            bool: BoolDelegate,
            str: StringDelegate,
        }

        # Проходим по всем видимым столбцам
        for visible_idx in range(self.source_model.columnCount()):
            # Находим объект TableColumn по видимому индексу
            col = None
            v_idx = 0
            for c in self.source_model._columns:
                if c.visible:
                    if v_idx == visible_idx:
                        col = c
                        break
                    v_idx += 1
            if col is None or col.column_type != ColumnType.DATA:
                continue

            field_name = col.field_name
            config = self.field_configs.get(field_name, {})
            model_col = visible_idx  # в PaginatedTableModel видимый индекс = индекс в представлении

            # 1) Выпадающий список (choices)
            choices = config.get('choices')
            if choices:
                delegate = ComboBoxDelegate(self.table_view, choices)
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue

            # 2) Многострочный текст (textarea)
            widget_type = config.get('widget_type')
            if widget_type == 'textarea':
                delegate = TextPopupDelegate(
                    self.table_view,
                    readonly=not self.edit_mode,
                    get_completion_list=lambda col=visible_idx: self._get_unique_values_for_column(col)
                )
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue

            # 3) Автодополнение для строк
            if col.data_type == str and config.get('autocomplete', False):
                delegate = CompleterStringDelegate(
                    self.table_view,
                    get_unique_values_func=self._get_unique_values_for_column,
                    column=visible_idx
                )
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue

            # 4) Стандартные делегаты по типу
            delegate_class = type_delegate_map.get(col.data_type)
            if delegate_class:
                if delegate_class in (DatePickerDelegate, TimePickerDelegate):
                    delegate = delegate_class(self.table_view, config=config)
                else:
                    delegate = delegate_class(self.table_view)
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue

            # 5) Обычные строки с маской ввода
            if col.data_type == str:
                mask = config.get('input_mask')
                column_masks = {model_col: mask} if mask else None
                delegate = StringDelegate(self.table_view, column_masks=column_masks)
                self.table_view.setItemDelegateForColumn(model_col, delegate)

    def reload_data(self) -> None:
        self.reload_with_filters(self._current_filters)

    def _save_new_rows(self):
        for row in list(self.new_rows):
            dto = self.source_model.get_item_at_row(row)
            if dto:
                created = self.service.create(dto)
                self.source_model.update_row(row, created)
                self.original_data[row] = created
        self.new_rows.clear()

    def _save_modified_rows(self):
        for entity_id in list(self.modified_ids):
            row = self._find_row_by_id(entity_id)
            if row < 0:
                continue
            dto = self.source_model.get_item_at_row(row)
            if dto:
                updated = self.service.update(dto)
                self.source_model.update_row(row, updated)
                self.original_data[row] = updated
        self.modified_ids.clear()

    def _save_deleted_rows(self):
        for entity_id in list(self.deleted_ids):
            self.service.delete(entity_id)
        self.deleted_ids.clear()

    def _add_inline_row(self):
        # Создать пустой DTO и добавить
        defaults = {}
        for col in self.columns:
            if col.column_type != ColumnType.DATA:
                continue
            if col.data_type == str:
                defaults[col.field_name] = ""
            elif col.data_type == int:
                defaults[col.field_name] = 0
            elif col.data_type == datetime.date:
                defaults[col.field_name] = datetime.date.today()
            else:
                defaults[col.field_name] = None
        # Применяем контекстные параметры
        if hasattr(self, '_context_params'):
            for key, value in self._context_params.items():
                if key in defaults:
                    defaults[key] = value
        dto = self.dto_class(**defaults)
        dto.id = self._next_temp_id if hasattr(self, '_next_temp_id') else -1
        self._next_temp_id = (self._next_temp_id or -1) - 1
        self._add_new_row(dto)

    def _delete_selected_rows(self):
        ids_to_delete = self.get_selected_entity_ids()
        for entity_id in ids_to_delete:
            self._mark_for_deletion(entity_id)
        self._clear_checkboxes()

    def _cancel_selected_rows_changes(self):
        ids_to_cancel = self.get_selected_entity_ids()
        for entity_id in ids_to_cancel:
            row = self._find_row_by_id(entity_id)
            if row < 0:
                continue
            dto = self.source_model.get_item_at_row(row)
            if dto and dto.id is not None and dto.id < 0:
                self._remove_new_row(row)
            else:
                fresh = self.service.get_by_id(entity_id)
                self.source_model.update_row(row, fresh)
                if entity_id in self.modified_ids:
                    self.modified_ids.discard(entity_id)
                if entity_id in self.deleted_ids:
                    self.deleted_ids.discard(entity_id)
                self._update_row_color(row)
        self._clear_checkboxes()