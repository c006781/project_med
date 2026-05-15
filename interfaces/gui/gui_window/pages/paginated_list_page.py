# interfaces/gui/gui_window/pages/paginated_list_page.py
"""
Новая страница списка с пагинацией, заменяющая DynamicListPage.
"""

import datetime
from typing import Any, Dict, Optional, Set

from app.draft.draft_registry import DraftRegistry

from interfaces.gui.gui_window.mixins.draft_tree_mixin import DraftTreeMixin
from interfaces.gui.gui_window.mixins.pagination_mixin import PaginationMixin
from interfaces.gui.gui_window.mixins.selection_mixin import SelectionMixin
from interfaces.gui.gui_window.mixins.edit_mode_mixin import EditModeMixin
# from interfaces.gui.gui_window.mixins.data_change_mixin import DataChangeMixin
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
    # DataChangeMixin,
    FilterMixin,
    UIMixin,
    ControllerMixin,
    DraftTreeMixin,  
):
    """
    Универсальная страница списка с пагинацией, фильтрацией и редактированием.


   
    Примечание для наследников:
        При переопределении методов _save_new_rows, _save_modified_rows, _save_deleted_rows
        необходимо сохранять контракт возвращаемых значений (для _save_new_rows – словарь).
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
        # уточнения:
        #   loader_func – это пережиток старой архитектуры. В новой версии данные загружаются через сервис с пагинацией, поэтому loader_func не нужен и должен быть удалён. Вся логика загрузки данных теперь сосредоточена в PaginationMixin.

        super().__init__(parent)

        self.service = service
        self.dto_class = dto_class
        self.field_configs = field_configs
        self.page_title = page_title
        self.add_action_text = add_action_text
        self.action_button_text = action_button_text
        self.exclude_columns = exclude_columns or []

        self._entity_type = entity_type

        self._next_temp_id = -1

        # DataChangeMixin.__init__(self)
        self.edit_mode = False

        self._build_columns()
        self._create_model()
        self.setup_ui()
        self.setup_pagination(service, page_size=50, extra_rows=5)
        self.setup_filtering(self.filter_bar, self.table_view)

        # Инициализация реестра черновиков
        self._draft_registry = DraftRegistry(self) # Инициализация реестра черновиков (глобальный, передаётся из главного окна)
        self._draft_registry.draft_changed.connect(self._on_draft_registry_changed)
        self._draft_component_id = None # Установка ключа для текущего компонента (будет установлен позже, при выборе строки)

        # Создание реестра черновиков для фото и других дочерних виджетов
        self._setup_draft_system()

        # Подключаем сигнал изменения черновиков к перекраске строки
        self.draft_modified_changed.connect(self._on_draft_modified_changed)

        self.entity_status_changed.connect(self._on_entity_status_changed)
        
        # Подключаем сигнал выделения строки (если ещё не подключён)
        selection_model = self.table_view.selectionModel()
        if selection_model:
            selection_model.selectionChanged.connect(self._on_selection_changed_for_draft)

        self.reload_with_filters(None) # Загружаем первую страницу данных (через пагинацию)

    def _on_row_modified_from_model(self, row: int):
        """Обработчик прямого редактирования ячейки в таблице."""
        dto = self.source_model.get_item_at_row(row)
        if dto and dto.id is not None and dto.id >= 0:
            self.mark_own_change(dto.id)

    # def _load_data(self): # Удалить метод полностью – он больше не нужен # Если в наследниках он переопределялся, их нужно переписать, используя пагинацию
    #     # Очищаем все черновики, статусы, счётчики для текущего типа сущности
    #     for i in [
    #         f"{self._entity_type}:",
    #         f"__status__:{self._entity_type}:",
    #         f"__counter__:{self._entity_type}:",
    #         f"__deleted__:{self._entity_type}:",
    #         f"__new__:{self._entity_type}:",
    #     ]:
    #         self._draft_registry.discard_by_prefix(i)   
    #     # self._draft_registry.discard_by_prefix(f"{self._entity_type}:")
    #     # self._draft_registry.discard_by_prefix(f"__status__:{self._entity_type}:")
    #     # self._draft_registry.discard_by_prefix(f"__counter__:{self._entity_type}:")
    #     # self._draft_registry.discard_by_prefix(f"__deleted__:{self._entity_type}:")
    #     # self._draft_registry.discard_by_prefix(f"__new__:{self._entity_type}:")

    #     # Очищаем кэш статусов
    #     self._status_cache.clear()

    #     # Загружаем новые данные
    #     self.current_data = self.loader_func(self.current_extra)
    #     self.source_model.update_data(self.current_data)
    #     self._update_save_button_state()

    # ------------------------------------------------------------------
    # Переопределение абстрактных методов DraftTreeMixin
    # ------------------------------------------------------------------

    def _get_parent_id(self, child_id: int) -> Optional[int]:
        """
        Для текущей страницы (например, список приёмов) у приёма нет родителя.
        Для списка фото нужно было бы вернуть appointment_id, но здесь мы работаем
        с основным списком (например, пациенты или приёмы). Поэтому возвращаем None.
        Если страница будет использоваться как дочерняя, метод переопределяется.
        """
        return None

    def _get_children_ids(self, parent_id: int) -> Set[int]:
        """
        Возвращает множество ID дочерних сущностей. Для базовой страницы – пустое множество.
        В AppointmentListPage этот метод будет переопределён для возврата ID фото.
        """
        return set()

    # ------------------------------------------------------------------
    # Обработка сигналов реестра
    # ------------------------------------------------------------------

    def _on_entity_status_changed(self, entity_id: int, has_changes: bool):
        """
        При изменении статуса сущности обновляем UI (цвет строки, кнопку сохранения).
        """
        self._update_row_color_by_id( # Перекрашиваем строку, соответствующую этой сущности
            entity_id = entity_id ,          
        )  

        self._update_save_button_state() # Обновляем состояние кнопки сохранения

    def _on_draft_registry_changed(self, key: str, has_draft: bool):
        """
        При изменении реестра проверяем, не изменился ли статус какой‑либо сущности,
        и обновляем UI (цвет строки, кнопку сохранения).
        """

        parts = key.split(':')
        if len(parts) < 2:
            return
        
        # Определяем entity_id из ключа
        if parts[0] == '__status__':
            # Ключ статуса: __status__:entity_type:entity_id
            entity_type = parts[1]
            if entity_type != self._entity_type:
                return
            
            entity_id = int(parts[2])

            status = self._draft_registry.get_entity_status(entity_type, entity_id)
            self._set_cached_status(entity_id, status)
            self.entity_status_changed.emit(entity_id, status is not None) # Перекрашиваем строку, соответствующую этой сущности

            # # Перекрашиваем строку, соответствующую этой сущности
            # row = self._find_row_by_id(entity_id)
            # if row >= 0:
            #     self._update_row_color(row)

            # self._update_row_color_by_id( # Перекрашиваем строку, соответствующую этой сущности # убрал так как есть вызов в entity_status_changed
            #     entity_id = entity_id ,          
            # )  

        elif parts[0] == '__counter__':
            # Изменение счётчика – не требует UI, только пересчёт статуса родителя
            # (уже сделан через _update_child_change)
            pass

        else:
            # Другие ключи – игнорируем (черновики, удалённые, новые)
            pass

    # ------------------------------------------------------------------
    # Обработка изменения черновиков
    # ------------------------------------------------------------------

    def _on_draft_modified_changed(self, has_draft: bool):
        """Обработчик изменения черновиков в поддереве (сигнал от DraftTreeMixin)."""
        if not self.selected_dto:
            return
        
        # entity_id = self.selected_dto.id
        # # row = self._find_row_by_id(entity_id)
        # # if row >= 0:
        # #     # Просто перекрашиваем строку; статус уже обновлён через реестр
        # #     self._update_row_color(row)

        self._update_row_color_by_id( # Перекрашиваем строку
            entity_id = self.selected_dto.id           
        )  

        self._update_save_button_state() # Обновляем состояние кнопки сохранения
        
        # """
        # Слот, вызываемый при изменении состояния черновиков в поддереве (сигнал draft_modified_changed).
        # Перекрашивает текущую строку и при необходимости добавляет/удаляет ID из modified_ids.
        # """
        # if not self.selected_dto:
        #     return
        
        # entity_id = self.selected_dto.id
        # row = self._find_row_by_id(entity_id)
        # if row >= 0:
        #     self._update_row_color(row)
        #     if has_draft:
        #         # Если появились черновики – добавляем ID в modified_ids (если ещё не добавлен)
        #         if entity_id not in self.modified_ids:
        #             self._add_to_modified(entity_id)

        #     else:
        #         # Если черновиков больше нет – проверяем, не вернулись ли данные к оригиналу
        #         # и если нет других изменений, удаляем из modified_ids
        #         if not self._has_any_changes(entity_id):
        #             if entity_id in self.modified_ids:
        #                 self._remove_from_modified(entity_id)

    def _has_any_changes(self, entity_id: int) -> bool:
        """
        Проверяет, есть ли изменения (собственные или дочерние) у сущности.

        Args:
            entity_id: ID сущности.

        Returns:
            True, если статус сущности 'own', 'child' или 'both', иначе False.
        """

        status = self._draft_registry.get_entity_status(self._entity_type, entity_id)

        return status in ('own', 'child', 'both')
    
        # """
        # Проверяет, есть ли изменения в строке (основные поля или черновики потомков).
        # """
        # # Проверка основных полей
        # row = self._find_row_by_id(entity_id)
        # if row < 0:
        #     return False
        
        # dto = self.source_model.get_item_at_row(row)
        # original = self.original_data.get(row)
        # if original and dto.model_dump() != original.model_dump():
        #     return True
        
        # # Проверка черновиков потомков через свойство миксина
        # return self.has_descendant_drafts

    # ------------------------------------------------------------------
    # Переопределение методов сохранения (работа с реестром)
    # ------------------------------------------------------------------

    def _save_new_rows(self) -> Dict[int, Any]:
        """
        Сохраняет все новые строки, помеченные как __new__.

        Returns:
            Словарь {временный_id: созданный_DTO} для всех успешно сохранённых строк.
        """

        prefix = f"__new__:{self._entity_type}:"

        saved_map = {}

        for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
            temp_id = int(key.split(':')[-1])
            data = self._draft_registry.get(key)
            dto = data["dto"]
            created = self.service.create(dto)

            # Обновляем модель
            row = self._find_row_by_id(temp_id)
            if row >= 0:
                self.source_model.update_row(row, created)

                # Убираем пометку 'new' и сбрасываем собственные изменения
                self._draft_registry.discard(key)
                # self._update_own_change(created.id, False)
                self.clear_own_change(created.id)

                saved_map[temp_id] = created

            else:
                self.logger.warning(f"Не найдена строка для временного ID {temp_id}")

        if saved_map:
            self._update_save_button_state() # Обновляем состояние кнопки сохранения
        
        return saved_map

    def _save_modified_rows(self) -> None:
        """Сохраняет изменения существующих строк (только те, у которых есть статус 'own' или 'both')."""

        entity_ids = set()

        # Ищем все ключи статусов для данного типа
        for key in self._draft_registry.get_keys_by_prefix(f"__status__:{self._entity_type}:"):
            parts = key.split(':')
            if len(parts) >= 3:
                entity_id = int(parts[2])
                status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
                if status in ('own', 'both'):
                    entity_ids.add(entity_id)

        for entity_id in entity_ids:
            row = self._find_row_by_id(entity_id)
            if row < 0:
                continue

            dto = self.source_model.get_item_at_row(row)
            if dto is None:
                continue

            updated = self.service.update(dto)
            self.source_model.update_row(row, updated)

            # уточнение:
            # так как в дальнейшем может потребоваться делать общий буфер на все страници - чистим сейчас
            self.clear_entity_drafts(entity_id) # Удаляет черновики для данной сущности

            # Снимаем флаг собственных изменений (обновляем статус)
            self.clear_own_change(entity_id)  # снимаем флаг 'own'

        # """
        # Сохраняет изменения существующих строк, у которых есть черновики.
        # Использует ключи вида "entity_type:entity_id:*" (не служебные).
        # """
        # prefix = f"{self._entity_type}:"
        # # Собираем уникальные ID сущностей, у которых есть черновики
        # entity_ids = set()
        # for key in self._draft_registry.get_keys_by_prefix(prefix):
        #     # Пропускаем служебные ключи
        #     if key.startswith(('__', f"{self._entity_type}:")):
        #         parts = key.split(':')
        #         if len(parts) >= 2 and parts[0] == self._entity_type:
        #             try:
        #                 entity_id = int(parts[1])
        #                 entity_ids.add(entity_id)
        #             except ValueError:
        #                 pass
        # # Для каждого ID обновляем запись в БД
        # for entity_id in entity_ids:
        #     row = self._find_row_by_id(entity_id)
        #     if row < 0:
        #         continue
        #     dto = self.source_model.get_item_at_row(row)
        #     if dto is None:
        #         continue
        #     updated = self.service.update(dto)
        #     self.source_model.update_row(row, updated)
        #     # Снимаем флаг собственных изменений (черновики остаются? Нет, черновики нужно удалить)
        #     # Решаем: после сохранения все черновики для этой сущности должны быть удалены.
        #     self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)
        #     self._update_own_change(entity_id, False)

    
    # def _clear_draft_registry(self, entity_id: int) -> None:
    #     """
    #     Удаляет черновики для данной сущности.
    #     Примечание: дочерние черновики (например, фото) уже сохранены и удалены
    #     в _save_child_components, поэтому удаление по префиксу безопасно.
    #     """

    #     # # После сохранения сбрасываем статус и черновики
    #     # self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)


    #     # Удаляем все ключи, начинающиеся с "entity_type:entity_id:"
    #     # (включая возможные остаточные дочерние черновики – они уже применены)
    #     temp = f"{self._entity_type}:{entity_id}"
    #     self._draft_registry.discard_by_prefix(f"{temp}:") # Удаляем ТОЛЬКО прямые черновики этой сущности (но не дочерние)

    #     # Удаляем статус и счётчик
    #     self._draft_registry.delete_entity_status(self._entity_type, entity_id)
    #     self._draft_registry.discard(f"__counter__:{temp}")

    def _save_deleted_rows(self) -> None:
        """Удаляет строки, помеченные как __deleted__."""

        prefix = f"__deleted__:{self._entity_type}:"

        for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
            entity_id = int(key.split(':')[-1])
            self.service.delete(entity_id)

            # Удаляем сам ключ удаления
            self._draft_registry.discard(key)

            # Удаляем все черновики, статусы и счётчики для этой сущности
            self._draft_registry.discard_by_prefix(f"{self._entity_type}:{entity_id}:")
            self._draft_registry.delete_entity_status(self._entity_type, entity_id)
            self._draft_registry.discard(f"__counter__:{self._entity_type}:{entity_id}")

            # # Уведомляем родителей (если есть)
            # parent_id = self._get_parent_id(entity_id)
            # if parent_id is not None:
            #     self.mark_child_change(parent_id, -1)

            # Очищаем кэш статусов в миксине
            self._status_cache.pop(entity_id, None)

            self._update_parent_child_counter(entity_id, -1) # -1 к счётчику родителя # Уведомляем родителей (если есть) # Наследован из DraftTreeMixin

    @property
    def _saving_in_progress(self) -> bool:
        if not hasattr(self, '__saving_in_progress'):
            self.__saving_in_progress = False # флаг блокировки

        return self.__saving_in_progress

    @_saving_in_progress.setter
    def _saving_in_progress(self, value):
        self.__saving_in_progress = value  # флаг блокировки

    def _save_all_changes_impl(self) -> bool:
        """Основной метод сохранения (вызывается из EditModeMixin)."""
        if self._saving_in_progress: # флаг блокировки
            self.logger.warning("Сохранение уже выполняется, повторный вызов игнорирован")
            return False
        
        self._saving_in_progress = True 

        try:
            # Сохраняем новые строки
            new_map = self._save_new_rows()

            # 2. Если текущая выбранная строка была новой, обновляем selected_dto
            if self.selected_dto and self.selected_dto.id in new_map:
                self.selected_dto = new_map[self.selected_dto.id]

            # Сохраняем дочерние черновики (например, фото)
            self._save_child_components()
            
            # Сохраняем изменённые строки
            self._save_modified_rows()

            # Сохраняем удалённые строки
            self._save_deleted_rows()

            # Перезагружаем данные и выходим из режима редактирования
            self.reload_data()

            # Очищаем реестр от служебных ключей (черновики, статусы, счётчики, удалённые, новые)
            self._clear_entity_registry()

            # Выходим из режима редактирования (отключаем чекбоксы, блокируем редактирование)
            self._exit_edit_mode()

            self._update_save_button_state() # Обновляем состояние кнопки сохранения (на случай, если _exit_edit_mode не вызывает)

            return True
        
        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении: {e}")
            return False
        
        finally:
            self._saving_in_progress = False

    def reload_with_filters(self, filters_tree):
        """Перезагружает данные с новыми фильтрами и обновляет состояние кнопки сохранения."""
    
        super().reload_with_filters(filters_tree)   # вызывает _load_first_page() в миксине
        self._update_save_button_state() # Обновляем состояние кнопки сохранения

    def _save_child_components(self):
        """
        Сохраняет черновики всех дочерних компонентов (например, фото).
        Вызывается перед сохранением строк таблицы, чтобы дочерние сущности
        успели записаться в БД и получить ID родителя.

        Примечание: Если parent_id равен None (например, для новой строки, ещё не сохранённой),
        дочерние компоненты не смогут сохраниться – это нормально, так как им нужен реальный ID.
        """
        # Сохраняем дочерние черновики (например, фото)

        parent_id = self.selected_dto.id if self.selected_dto else None
        # Если parent_id is None, дочерние черновики не могут быть сохранены,
        # так как им не с чем связаться – пропускаем.
        if parent_id is None or parent_id < 0:
            self.logger.warning(
                f"_save_child_components: родительский ID {parent_id} невалиден, "
                "дочерние черновики не будут сохранены"
            )
            return
        
        for child in self._children_components:
            if hasattr(child, 'apply'):
                child.apply(
                    self._draft_registry,
                    parent_id=parent_id,
                    service=self._get_child_service()
                )

        # self._update_save_button_state() #  тут неадо, так как работаем только с дочерними, а не с нынешней    

    def _clear_entity_registry(self):
        """
        Очищает реестр от всех черновиков, статусов, счётчиков, удалённых и новых записей
        для текущего типа сущности.

        ВНИМАНИЕ: Этот метод удаляет черновики только для текущего типа сущности
        (self._entity_type). Если в будущем реестр станет глобальным (один на всё приложение),
        очистка будет ограничена префиксами данного типа, что безопасно.
        """

        # Очищаем реестр от служебных ключей (черновики, статусы, счётчики, удалённые, новые)

        # уточнение:
        # метод удаляет все черновики из реестра, включая те, которые могут быть нужны для других страниц (если реестр общий). Поскольку у вас реестр создаётся для каждой страницы отдельно, это не страшно. Но если в будущем вы решите сделать реестр глобальным, лучше удалить этот метод или переопределить его в наследниках. Пока можно оставить.
        # Если в будущем нудно делать реестр глобальным (один на всё приложение), тогда очистку нужно будет делать выборочно (по префиксу типа сущности). Но пока оставляйте как есть
        
        for prefix in [
            f"{self._entity_type}:",
            f"__status__:{self._entity_type}:",
            f"__counter__:{self._entity_type}:",
            f"__deleted__:{self._entity_type}:",
            f"__new__:{self._entity_type}:",
        ]:
            self._draft_registry.discard_by_prefix(prefix)
        
        # Очищаем кэш статусов, чтобы при следующей загрузке страницы не осталось старых данных
        self._status_cache.clear()

    # ------------------------------------------------------------------
    # Вспомогательные методы для цвета строки
    # ------------------------------------------------------------------

    def _get_row_color(self, dto: Any) -> QColor:
        """Определяет цвет строки на основе статуса сущности."""
        entity_id = dto.id
        
        if entity_id is None or entity_id < 0:
            # Новая строка – зелёный, если есть черновик __new__
            if self._draft_registry.has(f"__new__:{self._entity_type}:{entity_id}"):
                return QColor(200, 255, 200)
            
            return QColor(255, 255, 255)
        
        # Существующая строка
        if self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):
            return QColor(255, 200, 200)  # красный
        
        status = self._get_cached_status(entity_id)
        if status in ('own', 'child', 'both'):

            return QColor(255, 255, 180)  # жёлтый
        
        return QColor(255, 255, 255)      # белый

    def _update_row_color(self, row: int):
        dto = self.source_model.get_item_at_row(row)
        if dto is None:
            return
        color = self._get_row_color(dto) # этот метод уже использует реестр
        self.source_model.set_row_color(row, color)

    # ------------------------------------------------------------------
    # Методы для работы с выделением и кнопками
    # ------------------------------------------------------------------

    def _has_unsaved_changes(self) -> bool:
        """Проверяет наличие любых несохранённых изменений в реестре."""

        # Есть ли черновики для текущего типа?
        if self._draft_registry.has_prefix(f"{self._entity_type}:"):
            return True
        
        # Есть ли удалённые?
        if self._draft_registry.has_prefix(f"__deleted__:{self._entity_type}:"):
            return True
        
        # Есть ли новые?
        if self._draft_registry.has_prefix(f"__new__:{self._entity_type}:"):
            return True
        
        return False

        # # Есть ли черновики для текущего типа?
        # prefix = f"{self._entity_type}:"
        # if any(k.startswith(prefix) for k in self._draft_registry._storage):
        #     return True
        
        # # Есть ли удалённые?
        # if self._draft_registry.has_prefix(f"__deleted__:{self._entity_type}:"):
        #     return True
        
        # # Есть ли новые?
        # if self._draft_registry.has_prefix(f"__new__:{self._entity_type}:"):
        #     return True
        
        # return False

    def _update_save_button_state(self):
        """
        Обновляет состояние кнопки сохранения.
        """
        self.save_changes_btn.setEnabled(self._has_unsaved_changes())

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

    # def _save_all_changes_impl(self) -> bool:
    #     # 1. Сохраняем дочерние черновики (фото и т.д.)
    #     # for child in self._children_components:
    #     #     if hasattr(child, 'apply'):
    #     #         child.apply(
    #     #             self._draft_registry, 
    #     #             parent_id=self.get_current_selected_dto().id, 
    #     #             service=self._get_child_service()
    #     #         )
    #     # self._save_changes()
    #     self._save_child_drafts()
        
    #     # 2. Сохраняем строки таблицы (родительский метод)
    #     return super()._save_all_changes_impl()

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

    # def _on_row_modified(self, row: int):
    #     """Обработчик изменения строки – теперь также проверяем дочерние черновики."""
    #     super()._on_row_modified(row)
    #     # Если изменения есть в дочерних – помечаем строку как изменённую
    #     if self._draft_modified:
    #         self._add_to_modified(self.selected_dto.id)

    # def _update_row_color(self, row: int):
    #     """Обновляет цвет строки с учётом дочерних черновиков."""

    #     dto = self.source_model.get_item_at_row(row)
    #     if dto is None:
    #         return
        
    #     if dto.id is None or dto.id < 0:
    #         color = QColor(200, 255, 200) if row in self.new_rows else QColor(255, 255, 255)

    #     else:
    #         if dto.id in self.deleted_ids:
    #             color = QColor(255, 200, 200)

    #         elif dto.id in self.modified_ids or self._draft_modified:
    #             color = QColor(255, 255, 180)

    #         else:
    #             color = QColor(255, 255, 255)

    #     self.source_model.set_row_color(row, color)

    # # def _save_changes(self, if_question: bool = True) -> bool:
    # # def _save_changes(self, if_question: bool = True):
    # def _save_child_drafts(self, if_question: bool = True):
    #     """Сохраняет изменения: сначала дочерние поддеревья, затем основные поля."""
    #     # Сохраняем дочерние черновики
    #     for child in self._children_components:
    #         if hasattr(child, 'apply'):
    #             child.apply(
    #                 self._draft_registry, 
    #                 parent_id=self.selected_dto.id, 
    #                 service=self._get_child_service()
    #             )

    #     # # Затем основные поля
    #     # return super()._save_changes(if_question) # непонятно нужно ли...

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
        # self.source_model.row_modified.connect(self._on_row_modified)
        self.source_model.row_modified.connect(self._on_row_modified_from_model)

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

    # def _save_new_rows(self):
    #     for row in list(self.new_rows):
    #         dto = self.source_model.get_item_at_row(row)
    #         if dto:
    #             created = self.service.create(dto)
    #             self.source_model.update_row(row, created)
    #             self.original_data[row] = created
    #     self.new_rows.clear()

    # def _save_modified_rows(self):
    #     for entity_id in list(self.modified_ids):
    #         row = self._find_row_by_id(entity_id)
    #         if row < 0:
    #             continue
    #         dto = self.source_model.get_item_at_row(row)
    #         if dto:
    #             updated = self.service.update(dto)
    #             self.source_model.update_row(row, updated)
    #             self.original_data[row] = updated
    #     self.modified_ids.clear()

    # def _save_deleted_rows(self):
    #     for entity_id in list(self.deleted_ids):
    #         self.service.delete(entity_id)
    #     self.deleted_ids.clear()

    def _add_inline_row(self):

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

        if hasattr(self, '_context_params'):
            for key, value in self._context_params.items():
                if key in defaults:
                    defaults[key] = value

        dto = self.dto_class(**defaults)
        temp_id = self._next_temp_id
        self._next_temp_id -= 1
        dto.id = temp_id

        # Сохраняем в реестр как новую строку
        self._draft_registry.set(f"__new__:{self._entity_type}:{temp_id}", {"dto": dto})

        # Добавляем в модель
        row = self.source_model.add_row(dto)

        # Помечаем как имеющую собственные изменения (новая строка)
        self.mark_own_change(temp_id)

        # Уведомляем родителя о появлении нового потомка с изменениями
        self._update_parent_child_counter(temp_id, +1)

        self._update_row_color(row)

        self._update_save_button_state() # Обновляем состояние кнопки сохранения

        # # Создать пустой DTO и добавить
        # defaults = {}
        # for col in self.columns:
        #     if col.column_type != ColumnType.DATA:
        #         continue
        #     if col.data_type == str:
        #         defaults[col.field_name] = ""
        #     elif col.data_type == int:
        #         defaults[col.field_name] = 0
        #     elif col.data_type == datetime.date:
        #         defaults[col.field_name] = datetime.date.today()
        #     else:
        #         defaults[col.field_name] = None
        # # Применяем контекстные параметры
        # if hasattr(self, '_context_params'):
        #     for key, value in self._context_params.items():
        #         if key in defaults:
        #             defaults[key] = value
        # dto = self.dto_class(**defaults)
        # dto.id = self._next_temp_id if hasattr(self, '_next_temp_id') else -1
        # self._next_temp_id = (self._next_temp_id or -1) - 1
        # self._add_new_row(dto)

    # def _update_parent_child_counter(self, entity_id, delta:int): # перенесён в DraftTreeMixin
    #     # Если есть родитель, увеличиваем счётчик его потомков
    #     parent_id = self._get_parent_id(entity_id)
    #     if parent_id is not None:
    #         self.mark_child_change(parent_id, delta)

    def _delete_selected_rows(self):
        ids_to_delete = self.get_selected_entity_ids()

        for entity_id in ids_to_delete:
            temp = f"__deleted__:{self._entity_type}:{entity_id}"
            if not self._draft_registry.has( # проверка если строка уже была помечена на удаление
                temp
            ):
                
                # Помечаем как удалённую
                self._draft_registry.set(temp, {})

                # # Если есть родитель, увеличиваем счётчик его потомков
                # parent_id = self._get_parent_id(entity_id)
                # if parent_id is not None:
                #     self.mark_child_change(parent_id, 1)

                self._update_parent_child_counter(entity_id, 1) # +1 к счётчику родителя # Если есть родитель, увеличиваем счётчик его потомков  # Наследован из DraftTreeMixin        

                # # Перекрашиваем строку
                # row = self._find_row_by_id(entity_id)
                # if row >= 0:
                #     self._update_row_color(row)

                self._update_row_color_by_id(entity_id)  # Перекрашиваем строку

        self._clear_checkboxes() # Чистим чекбоксы

        self._update_save_button_state() # Обновляем состояние кнопки сохранения


        # ids_to_delete = self.get_selected_entity_ids()
        # for entity_id in ids_to_delete:
        #     self._mark_for_deletion(entity_id)

        # self._clear_checkboxes()

    def _update_row_color_by_id(self, entity_id):
        """
        Обновляет цвет строки для сущности по её ID.

        Args:
            entity_id: ID сущности, цвет которой нужно обновить.
        """

        # Перекрашиваем строку, соответствующую этой сущности
        row = self._find_row_by_id(entity_id)
        if row >= 0:
            # Просто перекрашиваем строку; статус уже обновлён через реестр
            self._update_row_color(row)

    def _cancel_selected_rows_changes(self):
        ids_to_cancel = self.get_selected_entity_ids()
        for entity_id in ids_to_cancel:
            row = self._find_row_by_id(entity_id)
            if row < 0:
                continue

            dto = self.source_model.get_item_at_row(row)
            if dto and dto.id is not None and dto.id < 0:
                # self._remove_new_row(row)

                # Новая строка – удаляем из реестра и из модели
                self._draft_registry.discard(f"__new__:{self._entity_type}:{entity_id}")
                self.source_model.remove_row(row)
                
                # Очищаем кэш статусов
                self._status_cache.pop(entity_id, None)

                # Уведомляем родителя, что исчез потомок с изменениями
                self._update_parent_child_counter(entity_id, -1)

            else:
                # fresh = self.service.get_by_id(entity_id)
                # self.source_model.update_row(row, fresh)
                # if entity_id in self.modified_ids:
                #     self.modified_ids.discard(entity_id)
                # if entity_id in self.deleted_ids:
                #     self.deleted_ids.discard(entity_id)
                # self._update_row_color(row)

                # Существующая – отменяем всё поддерево
                self.discard_entity_subtree(entity_id)  # метод из DraftTreeMixin

                # Перезагружаем DTO из БД
                fresh = self.service.get_by_id(entity_id)

                self.source_model.update_row(row, fresh)

                # Статус обновится автоматически через сигналы, цвет тоже
                self._update_row_color(row) # Перекрашиваем строку


        self._clear_checkboxes() # Чистим чекбоксы

        self._update_save_button_state() # Обновляем состояние кнопки сохранения