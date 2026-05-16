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

    def _update_id_own_in_real_id(
        self,
        temp_id,
        id,
    ):
        # Переносим статус 'own' (если был) с временного ID на реальный
        old_status = self._get_cached_status(temp_id)
        if old_status:
            self._set_cached_status(id, old_status)

            self._draft_registry.set_entity_status(self._entity_type, id, old_status)

            # Удаляем старый статус временного ID из реестра
            self._draft_registry.delete_entity_status(self._entity_type, temp_id)
            self._status_cache.pop(temp_id, None)
            # ВАЖНО: НЕ вызываем mark_child_change для родителя сейчас,
            # потому что родительский счётчик будет обновлён при сохранении
            # самих дочерних черновиков (они вызовут mark_child_change сами).

    def _transferring_child_drafts(
        self,
        temp_id,
        id,
    ):
        """
        Переносит все дочерние черновики с префикса, содержащего временный ID,
        на префикс с реальным ID. Без этого фото, добавленные до сохранения
        родителя, были бы потеряны.
        """

        # Переносим ВСЕ дочерние черновики (фото, заметки и т.д.)
        #    с префикса "entity_type:temp_id:" на "entity_type:created.id:"

        old_prefix = f"{self._entity_type}:{temp_id}:"
        new_prefix = f"{self._entity_type}:{id}:"
        for child_key in list(self._draft_registry.get_keys_by_prefix(old_prefix)):
            child_data = self._draft_registry.get(child_key)
            if child_data is not None:
                new_child_key = child_key.replace(old_prefix, new_prefix, 1)
                self._draft_registry.set(new_child_key, child_data)
                self._draft_registry.discard(child_key)
                self.logger.debug(f"Перенесён дочерний черновик {child_key} -> {new_child_key}")

    def _save_new_rows(self) -> Dict[int, Any]:
        """
        Сохраняет все новые строки, помеченные как __new__, в БД.

        **Важное примечание о логике переноса черновиков:**
        --------------------------------------------------------------------
        Пользователь может создать новую строку (например, приём) с временным ID,
        а затем, до сохранения этой строки, добавить к ней дочерние черновики
        (например, фото). В этом случае дочерние черновики хранятся в реестре
        под ключами, содержащими временный ID родителя (например, "appointment:-1:photos").

        При сохранении родителя в БД он получает реальный ID (например, 123).
        Без специальной обработки дочерние черновики остались бы привязанными
        к временному ID и не были бы найдены при последующем вызове _save_child_components.

        Поэтому данный метод выполняет:
            1. Сохранение родительской строки в БД, получение реального ID.
            2. Перенос всех дочерних черновиков (по префиксу "entity_type:temp_id:")
               на новый префикс с реальным ID.
            3. Перенос статуса 'own' с временного ID на реальный.
            4. Очистку временных ключей и кэша.

        После этого _save_child_components сможет найти дочерние черновики
        по правильному префиксу и применить их.
        --------------------------------------------------------------------

        Returns:
            Dict[int, Any]: Словарь {временный_id: созданный_DTO} для всех успешно сохранённых строк.
        """
        # Не удаляйте блок переноса дочерних черновиков! Без него фото, добавленные до сохранения родителя, будут потеряны.
        # Не вызывайте mark_child_change после переноса статуса – это нарушит счётчики (родитель получит +1 дважды: один раз от дочернего черновика, второй – здесь).
        # Не переносите статус до переноса дочерних черновиков – порядок не важен, но предпочтительнее сначала перенести черновики, чтобы они уже были на новом ключе, когда статус родителя изменится (хотя родительский статус изменится только после clear_own_change).



        prefix = f"__new__:{self._entity_type}:"
        saved_map = {}

        for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
            # 1. Извлекаем временный ID и DTO
            temp_id = int(key.split(':')[-1])
            data = self._draft_registry.get(key)
            dto = data["dto"]

            # 2. Сохраняем в БД, получаем реальный объект с ID
            created = self.service.create(dto)

            # 3. Находим строку в модели по временному ID
            row = self._find_row_by_id(temp_id)
            if row >= 0:
                # 4. Обновляем модель (заменяем временный DTO на созданный)
                self.source_model.update_row(row, created)

                # 5. Переносим ВСЕ дочерние черновики (фото, заметки и т.д.)
                #    с префикса "entity_type:temp_id:" на "entity_type:created.id:"
                self._transferring_child_drafts(temp_id, created.id)

                # 6. Переносим статус 'own' (если был) с временного ID на реальный
                self._update_id_own_in_real_id(temp_id, created.id)

                # ВАЖНО: НЕ вызываем mark_child_change для родителя сейчас,
                # потому что родительский счётчик будет обновлён при сохранении
                # самих дочерних черновиков (они вызовут mark_child_change сами).
                # Это обеспечивает симметричность: родитель узнаёт о потомке
                # только после того, как потомок реально сохранён и дочерние
                # черновики перенесены.

                # 7. Удаляем ключ __new__ (чтобы не сохранить повторно)
                self._draft_registry.discard(key)

                # 8. Снимаем флаг собственных изменений (строка сохранена, статус станет None)
                self.clear_own_change(created.id)

                # 9. Запоминаем соответствие для возможного обновления selected_dto
                saved_map[temp_id] = created

            else:
                self.logger.warning(f"Не найдена строка для временного ID {temp_id}")

        # После сохранения всех новых строк обновляем состояние кнопки сохранения
        if saved_map:
            self._update_save_button_state()

        return saved_map

        # """
        # Сохраняет все новые строки, помеченные как __new__.
        #
        # Returns:
        #     Словарь {временный_id: созданный_DTO} для всех успешно сохранённых строк.
        # """
        #
        # prefix = f"__new__:{self._entity_type}:"
        #
        # saved_map = {}
        #
        # for key in list(self._draft_registry.get_keys_by_prefix(prefix)):
        #     temp_id = int(key.split(':')[-1])
        #     data = self._draft_registry.get(key)
        #     dto = data["dto"]
        #     created = self.service.create(dto)
        #
        #     # Обновляем модель
        #     row = self._find_row_by_id(temp_id)
        #     if row >= 0:
        #         self.source_model.update_row(row, created)
        #
        #         # # Убираем пометку 'new' и сбрасываем собственные изменения
        #         # self._draft_registry.discard(key)
        #
        #         old_status = self._get_cached_status(temp_id) # Получаем старый статус (по временному ID)
        #
        #         if old_status:
        #             # Переносим статус на реальный ID
        #             self._set_cached_status(created.id, old_status)
        #             self._draft_registry.set_entity_status(self._entity_type, created.id, old_status)
        #             self._status_cache.pop(temp_id, None)
        #
        #             # # Уведомляем родителя, что появился потомок с изменениями
        #             # parent_id = self._get_parent_id(created.id)
        #             # if parent_id is not None:
        #             #     self.mark_child_change(parent_id, +1)
        #             # self._update_own_change(created.id, False)
        #
        #         # Удаляем ключ __new__ (чтобы не сохранить повторно)
        #         self._draft_registry.discard(key)
        #
        #         # Снимаем флаг собственных изменений (строка сохранена)
        #         self.clear_own_change(created.id)
        #
        #         saved_map[temp_id] = created
        #
        #     else:
        #         self.logger.warning(f"Не найдена строка для временного ID {temp_id}")
        #
        # if saved_map:
        #     self._update_save_button_state() # Обновляем состояние кнопки сохранения
        #
        # return saved_map

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
            # Сохраняем новые строки, получаем словарь {temp_id: created_dto}
            new_map = self._save_new_rows()

            # Если текущая выбранная строка была новой – обновляем selected_dto
            if self.selected_dto and self.selected_dto.id in new_map:
                self.selected_dto = new_map[self.selected_dto.id]

            # # Сохраняем дочерние черновики (например, фото)
            # self._save_child_components()

            # Сохраняем дочерние черновики для всех новых строк (они уже имеют реальный ID)
            for temp_id, created in new_map.items():
                self._save_child_components_for_parent(created.id)

            # Сохраняем дочерние черновики для текущей выбранной строки, если она существует и не новая
            if self.selected_dto and self.selected_dto.id >= 0:
                self._save_child_components_for_parent(self.selected_dto.id)
            
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

    def _save_child_components_for_parent(self, parent_id: int) -> None:
        """
        Применяет черновики всех дочерних компонентов (например, фото) для указанного родителя.

        Args:
            parent_id: ID родительской сущности (должен быть >= 0, то есть существовать в БД).
        """
        if parent_id is None or parent_id < 0:
            return

        for child in self._children_components:
            if hasattr(child, 'apply'):
                child.apply(
                    self._draft_registry,
                    parent_id=parent_id,
                    service=self._get_child_service()
                )
    # def _save_child_components(self):
    #     """
    #     Сохраняет черновики всех дочерних компонентов (например, фото).
    #     Вызывается перед сохранением строк таблицы, чтобы дочерние сущности
    #     успели записаться в БД и получить ID родителя.
    #
    #     Примечание: Если parent_id равен None (например, для новой строки, ещё не сохранённой),
    #     дочерние компоненты не смогут сохраниться – это нормально, так как им нужен реальный ID.
    #     """
    #     # Сохраняем дочерние черновики (например, фото)
    #
    #     parent_id = self.selected_dto.id if self.selected_dto else None
    #     # Если parent_id is None, дочерние черновики не могут быть сохранены,
    #     # так как им не с чем связаться – пропускаем.
    #     if parent_id is None or parent_id < 0:
    #         self.logger.warning(
    #             f"_save_child_components: родительский ID {parent_id} невалиден, "
    #             "дочерние черновики не будут сохранены"
    #         )
    #         return
    #
    #     for child in self._children_components:
    #         if hasattr(child, 'apply'):
    #             child.apply(
    #                 self._draft_registry,
    #                 parent_id=parent_id,
    #                 service=self._get_child_service()
    #             )
    #
    #     # self._update_save_button_state() #  тут неадо, так как работаем только с дочерними, а не с нынешней

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
        """
        Добавляет новую пустую строку в конец таблицы (режим редактирования).

        Важно: родитель НЕ уведомляется о появлении новой строки (нет вызова
        mark_child_change), потому что у новой строки ещё нет реального ID.
        Уведомление произойдёт только после сохранения строки в БД, когда
        дочерние черновики будут перенесены на реальный ID и применены.
        """

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
        self.mark_own_change(temp_id) # устанавливает статус 'own' для временного ID (без уведомления родителя)

        # # Уведомляем родителя о появлении нового потомка с изменениями
        # self._update_parent_child_counter(temp_id, +1)

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
    def _cancel_new_row(self, entity_id: int):
        """
        Отменяет создание новой строки с временным ID.
        Удаляет все её черновики (включая дочерние), ключ __new__ и саму строку из модели.
        """

        # Удаляем все черновики, привязанные к этому временному ID
        prefix = f"{self._entity_type}:{entity_id}:"
        self._draft_registry.discard_by_prefix(prefix)

        # Удаляем ключ __new__
        self._draft_registry.discard(f"__new__:{self._entity_type}:{entity_id}")

        # Удаляем статус сущности из реестра (ключ __status__)
        self._draft_registry.delete_entity_status(self._entity_type, entity_id)

        # Удаляем строку из модели
        row = self._find_row_by_id(entity_id)
        if row >= 0:
            self.source_model.remove_row(row)

        # Очищаем кэш статусов
        self._status_cache.pop(entity_id, None)

    def _delete_selected_rows(self):
        """
        Помечает выбранные строки на удаление или снимает пометку, если строка уже была помечена.

        Для существующих строк (entity_id >= 0):
            - Если строка ещё не помечена – создаётся ключ "__deleted__:entity_type:entity_id",
              увеличивается счётчик родителя на +1, строка перекрашивается в красный цвет.
            - Если строка уже помечена – пометка снимается (ключ удаляется, счётчик родителя
              уменьшается на -1, цвет восстанавливается).

        Для новых строк (entity_id < 0):
            - Они просто отменяются (удаляются из реестра и модели) через _cancel_new_row,
              потому что они ещё не сохранены и не имеют смысла «удаления».

        После обработки всех выбранных строк чекбоксы сбрасываются,
        и обновляется состояние кнопки сохранения.
        """

        ids_to_delete = self.get_selected_entity_ids()

        for entity_id in ids_to_delete:
            if entity_id < 0:
                # Новая строка – просто удаляем её (как при отмене)
                self._cancel_new_row(entity_id)

            else:
                # Существующая строка – помечаем на удаление
                temp = f"__deleted__:{self._entity_type}:{entity_id}"
                if self._draft_registry.has( # проверка если строка уже была помечена на удаление
                    temp
                ):
                    # Строка уже помечена на удаление – снимаем пометку
                    self._unmark_deleted_row(entity_id)

                else:
                    # Помечаем как удалённую
                    self._draft_registry.set(temp, {})

                    # Уведомляем родителя о том, что появился потомок, помеченный на удаление
                    # (это увеличит счётчик детей родителя)
                    self._update_parent_child_counter(entity_id, 1) # +1 к счётчику родителя # Если есть родитель, увеличиваем счётчик его потомков  # Наследован из DraftTreeMixin

                    self._update_row_color_by_id(entity_id)  # Перекрашиваем строку

        self._clear_checkboxes() # Чистим чекбоксы

        self._update_save_button_state() # Обновляем состояние кнопки сохранения

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

    def _unmark_deleted_row(self, entity_id: int) -> None:
        """
        Снимает пометку на удаление с существующей строки.

        Алгоритм:
            1. Проверяет, существует ли ключ __deleted__ для данной сущности.
            2. Если да – удаляет его.
            3. Уменьшает счётчик родителя на -1 (уведомляет родителя, что удалённый потомок «восстановлен»).
            4. Перекрашивает строку в актуальный цвет (без пометки на удаление).

        Args:
            entity_id: ID сущности, с которой нужно снять пометку на удаление.
        """
        deleted_key = f"__deleted__:{self._entity_type}:{entity_id}"
        if not self._draft_registry.has(deleted_key):
            # Пометки не было – ничего не делаем
            return

        # Удаляем ключ удаления
        self._draft_registry.discard(deleted_key)

        # Уменьшаем счётчик родителя (родитель теряет одного удалённого потомка)
        # Используем -1, так как ранее при пометке мы увеличивали счётчик на +1
        self._update_parent_child_counter(entity_id, -1)

        # Перекрашиваем строку (цвет будет определён по текущему статусу, без удаления)
        self._update_row_color_by_id(entity_id)

    def _cancel_selected_rows_changes(self):
        """
        Отменяет изменения для выбранных строк.

        При отмене НОВОЙ строки (временный ID) необходимо удалить ВСЕ её черновики,
        включая дочерние (например, фото), чтобы не оставлять мусор в реестре.
        Для существующей строки вызывается discard_entity_subtree, который очищает
        всё поддерево и перезагружает данные из БД.
        """

        ids_to_cancel = self.get_selected_entity_ids()
        for entity_id in ids_to_cancel:
            row = self._find_row_by_id(entity_id)
            if row < 0:
                continue

            dto = self.source_model.get_item_at_row(row)
            if dto and dto.id is not None and dto.id < 0:
                self._cancel_new_row(entity_id)

                # Родитель НЕ уведомляется, потому что он никогда не получал уведомления
                # о существовании этой новой строки (см. _add_inline_row).

            else:
                # Если строка была помечена на удаление – снимаем пометку
                if self._draft_registry.has(f"__deleted__:{self._entity_type}:{entity_id}"):
                    self._unmark_deleted_row(entity_id)
                    
                # Существующая – отменяем всё поддерево
                self.discard_entity_subtree(entity_id)  # метод из DraftTreeMixin

                # Перезагружаем DTO из БД
                fresh = self.service.get_by_id(entity_id)

                self.source_model.update_row(row, fresh)

                # Статус обновится автоматически через сигналы, цвет тоже
                self._update_row_color(row) # Перекрашиваем строку

        self._clear_checkboxes() # Чистим чекбоксы

        self._update_save_button_state() # Обновляем состояние кнопки сохранения