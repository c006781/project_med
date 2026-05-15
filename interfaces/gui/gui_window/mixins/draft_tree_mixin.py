# interfaces/gui/gui_window/mixins/draft_tree_mixin.py
"""
Миксин для поддержки древовидных черновиков в странице списка.
"""

from typing import Optional, Callable, Dict, Any, Set
from PySide6.QtCore import Signal

from app.draft.draft_registry import DraftRegistry
from app.draft.ihierarchical_editable import IHierarchicalEditableComponent
from app.utils.logger.logger import AppLogger


class DraftTreeMixin:
    """
    Предоставляет методы для управления деревом черновиков.

    Требует наличия атрибутов:
        - self._draft_registry (DraftRegistry)
        - self._draft_component_id (str) – ключ для текущего компонента
        - self._children_components (list) – список дочерних IEditableComponent
        - self.logger (AppLogger)

    Сигналы:
        draft_modified_changed(bool): Испускается при изменении состояния черновиков в поддереве.
        
    """

    draft_modified_changed = Signal(bool)

    entity_status_changed = Signal(int, bool)  # (entity_id, has_changes)


    # def _ensure_draft_attrs(self) -> None:
    #     """Гарантирует наличие атрибутов черновика (ленивая инициализация)."""

    #     if not hasattr(self, '_children_components'):
    #         self._children_components = []

    #     if not hasattr(self, '_draft_modified'):
    #         self._draft_modified = False

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def _status_cache(self) -> Dict[int, Optional[str]]:
        """Кэш статусов для сущностей (entity_id -> status)."""
        if not hasattr(self, '__status_cache'):
            self.__status_cache = {}
        return self.__status_cache

    @property
    def _parent_cache(self) -> Dict[int, int]:
        """Кэш parent_id для дочерних сущностей (child_id -> parent_id)."""
        if not hasattr(self, '__parent_cache'):
            self.__parent_cache = {}
        return self.__parent_cache

    @property
    def _children_cache(self) -> Dict[int, Set[int]]:
        """Кэш множеств дочерних ID для родителя (parent_id -> set[child_id])."""
        if not hasattr(self, '__children_cache'):
            self.__children_cache = {}
        return self.__children_cache

    @property
    def _children_components(self) -> list:
        if not hasattr(self, '__children_components'):
            self.__children_components = []

        return self.__children_components

    @_children_components.setter
    def _children_components(self, value):
        self.__children_components = value       

    
    @property
    def _draft_modified(self):
        if not hasattr(self, '__draft_modified'):
            self.__draft_modified = False

        return self.__draft_modified

    @_draft_modified.setter
    def _draft_modified(self, value):
        self.__draft_modified = value       

    @property
    def has_descendant_drafts(self) -> bool:
        """
        Возвращает True, если есть изменения в текущем компоненте или любом из его потомков.
        """
        # Убеждаемся, что атрибуты инициализированы
        if not hasattr(self, '_draft_modified'):
            self._draft_modified = False
        return self._draft_modified

    def setup_draft_tree(self, registry: DraftRegistry, component_id: str) -> None:
        """
        Инициализирует дерево черновиков.

        Args:
            registry: Реестр черновиков.
            component_id: Уникальный ключ для текущего компонента (например, "appointment:123:").
        """
        self._draft_registry = registry
        self._draft_component_id = component_id
        

        self._children_components = []     
        self._draft_modified = False   
    
        # # Ленивая инициализация атрибутов
        # if not hasattr(self, '_children_components'):
        #     self._children_components = []

        # if not hasattr(self, '_draft_modified'):
        #     self._draft_modified = False

        # Подписываемся на изменения в реестре для ключа текущего компонента
        registry.subscribe(component_id, self._on_registry_changed)

    def add_draft_child(self, child: IHierarchicalEditableComponent) -> None:
        """
        Добавляет дочерний компонент и подписывается на его сигнал changed.
        """

        # self._ensure_draft_attrs()    

        if child not in self._children_components:
            self._children_components.append(child)
            if hasattr(child, 'changed'):
                child.changed.connect(self._on_child_changed)

            # Также подписываемся на draft_modified_changed, если есть
            if hasattr(child, 'draft_modified_changed'):
                child.draft_modified_changed.connect(self._on_child_modified_changed)

            self._update_modified_state()

    def remove_draft_child(self, child: IHierarchicalEditableComponent) -> None:
        """Удаляет дочерний компонент."""

        # self._ensure_draft_attrs()

        if child in self._children_components:
            self._children_components.remove(child)

            if hasattr(child, 'changed'):
                child.changed.disconnect(self._on_child_changed)

            if hasattr(child, 'draft_modified_changed'):
                child.draft_modified_changed.disconnect(self._on_child_modified_changed)

            self._update_modified_state()

    def _on_registry_changed(self, key: str, has_draft: bool) -> None:
        """Обработчик изменения черновика в реестре для текущего компонента."""
        if key == self._draft_component_id:
            self._update_modified_state()

    def _on_child_changed(self) -> None:
        """Вызывается при изменении состояния дочернего компонента."""
        self._update_modified_state()

    def _on_child_modified_changed(self, modified: bool) -> None:
        """Вызывается при изменении флага modified у дочернего компонента."""
        self._update_modified_state()

    def _update_modified_state(self) -> None:
        """
        Пересчитывает, есть ли изменения в поддереве (собственные + дочерние).
        Испускает сигнал draft_modified_changed при изменении состояния.
        """

        # self._ensure_draft_attrs()

        has_own = self._draft_registry.has(self._draft_component_id)
        has_child = any(
            (hasattr(child, 'has_descendant_changes') and child.has_descendant_changes(self._draft_registry)) or
            (hasattr(child, 'has_changes') and child.has_changes(self._draft_registry))
            for child in self._children_components
        )
        modified = has_own or has_child
        if modified != self._draft_modified:
            self._draft_modified = modified
            self.draft_modified_changed.emit(modified)

    def apply_subtree(self, applier: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Применяет все черновики текущего поддерева (рекурсивно по префиксу).
        """

        # self._ensure_draft_attrs()
        
        prefix = self._draft_component_id
        self._draft_registry.apply_subtree(prefix, applier)

    def discard_subtree(self) -> None:
        """Отменяет все черновики текущего поддерева."""
        prefix = self._draft_component_id
        self._draft_registry.discard_subtree(prefix)

    def clear_child_drafts(self) -> None:
        """Очищает черновики всех дочерних компонентов (без применения)."""

        # self._ensure_draft_attrs()
        
        for child in self._children_components:
            if hasattr(child, 'discard'):
                child.discard(self._draft_registry)

    # ------------------------------------------------------------------
    # Абстрактные методы (должны быть переопределены в наследнике)
    # ------------------------------------------------------------------

    def _get_parent_id(self, child_id: int) -> Optional[int]:
        """
        Возвращает ID родительской сущности для дочерней.
        Переопределяется в классе страницы (например, для фото возвращает appointment_id).
        """
        return None

    def _get_children_ids(self, parent_id: int) -> Set[int]:
        """
        Возвращает множество ID дочерних сущностей для родителя.
        Переопределяется в классе страницы (например, для приёма – все photo_id).
        """
        return set()
    
    # ------------------------------------------------------------------
    # Обновление статуса сущности с распространением вверх
    # ------------------------------------------------------------------

    def _update_own_change(self, entity_id: int, has_own_change: bool) -> None:
        """
        Устанавливает/снимает флаг собственного изменения для сущности.
        Вызывает пересчёт статуса и распространение вверх.
        """
        old_status = self._get_cached_status(entity_id)
        new_status = self._compute_new_status(entity_id, has_own_change)
        if new_status == old_status:
            return

        self._set_cached_status(entity_id, new_status)
        self._draft_registry.set_entity_status(
            self._entity_type, entity_id, new_status
        )
        self.entity_status_changed.emit(entity_id, new_status is not None)
        self.draft_modified_changed.emit(bool(new_status))

        # Распространяем изменение вверх
        self._propagate_status_up(entity_id)

    def _update_child_change(self, parent_id: int, delta: int) -> None:
        """
        Вызывается при изменении количества потомков с не‑None статусом.
        delta = +1 (появился), -1 (исчез). Обновляет счётчик и пересчитывает статус родителя.
        """
        if delta == 0:
            return
        # Обновляем счётчик в реестре
        self._draft_registry.inc_child_counter(
            self._entity_type, parent_id, delta
        )
        # Пересчитываем статус родителя (с учётом его собственных изменений)
        self._recompute_parent_status(parent_id)

    def _recompute_parent_status(self, parent_id: int) -> None:
        """Пересчитывает статус родителя на основе его собственных изменений и счётчика детей."""
        own_status = self._draft_registry.get_entity_status(
            self._entity_type, parent_id
        )
        has_own = own_status in ('own', 'both')
        child_count = self._draft_registry.get_child_counter(
            self._entity_type, parent_id
        )
        new_status = self._status_from_flags(has_own, child_count > 0)

        old_status = self._get_cached_status(parent_id)
        if new_status == old_status:
            return

        self._set_cached_status(parent_id, new_status)
        self._draft_registry.set_entity_status(
            self._entity_type, parent_id, new_status
        )
        self.entity_status_changed.emit(parent_id, new_status is not None)

        # Распространяем дальше вверх
        self._propagate_status_up(parent_id)

    def _propagate_status_up(self, entity_id: int) -> None:
        """Рекурсивно обновляет статус всех предков (вверх по дереву)."""
        parent_id = self._get_parent_id(entity_id)
        if parent_id is None:
            return
        self._recompute_parent_status(parent_id)

    def _propagate_status_down(self, entity_id: int) -> None:
        """
        Рекурсивно сбрасывает статусы всех потомков (вниз по дереву).
        Используется при отмене изменений в поддереве.
        """
        for child_id in self._get_children_ids(entity_id):
            self._draft_registry.delete_entity_status(self._entity_type, child_id)
            self._set_cached_status(child_id, None)
            self.entity_status_changed.emit(child_id, False)
            self._propagate_status_down(child_id)

        # ------------------------------------------------------------------
    # Вспомогательные методы (не требуют переопределения)
    # ------------------------------------------------------------------

    def _get_cached_status(self, entity_id: int) -> Optional[str]:
        """Возвращает статус из кэша."""
        return self._status_cache.get(entity_id)

    def _set_cached_status(self, entity_id: int, status: Optional[str]) -> None:
        """Устанавливает статус в кэше."""
        if status is None:
            self._status_cache.pop(entity_id, None)
        else:
            self._status_cache[entity_id] = status

    def _compute_new_status(
        self, entity_id: int, has_own_change: bool
    ) -> Optional[str]:
        """Вычисляет новый статус на основе флага собственных изменений и счётчика детей."""
        child_count = self._draft_registry.get_child_counter(
            self._entity_type, entity_id
        )
        return self._status_from_flags(has_own_change, child_count > 0)

    @staticmethod
    def _status_from_flags(has_own: bool, has_child: bool) -> Optional[str]:
        """Преобразует флаги в статус."""
        if has_own and has_child:
            return 'both'
        if has_own:
            return 'own'
        if has_child:
            return 'child'
        return None
    
    # ------------------------------------------------------------------
    # Публичные методы для внешнего использования
    # ------------------------------------------------------------------

    def mark_own_change(self, entity_id: int) -> None:
        """Помечает сущность как имеющую собственные изменения."""
        self._update_own_change(entity_id, True)

    def clear_own_change(self, entity_id: int) -> None:
        """Снимает флаг собственных изменений (например, после сохранения)."""
        self._update_own_change(entity_id, False)

    def mark_child_change(self, parent_id: int, delta: int) -> None:
        """Уведомляет о появлении/исчезновении изменений у потомка родителя."""
        self._update_child_change(parent_id, delta)

    def discard_entity_subtree(self, entity_id: int) -> None:
        """
        Полностью отменяет все изменения для сущности и её потомков.
        Удаляет черновики, сбрасывает статусы, обновляет родителей.
        """
        # 1. Сбрасываем статусы потомков (вниз)
        self._propagate_status_down(entity_id)
        # 2. Удаляем все черновики и статус самой сущности
        self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)
        # 3. Сбрасываем кэш статуса сущности
        self._set_cached_status(entity_id, None)
        # 4. Обновляем родителя этой сущности (вверх)
        parent_id = self._get_parent_id(entity_id)
        if parent_id is not None:
            self._recompute_parent_status(parent_id)

    ################

    def clear_entity_drafts(self, entity_id: int) -> None:
        """
        Удаляет черновики для данной сущности, оставляя дочерние черновики нетронутыми.

        Используется после сохранения сущности, чтобы очистить её временные данные,
        но не удалять изменения, которые могут быть ещё не применены к дочерним компонентам.

        Примечание: дочерние черновики (например, фото) не удаляются этим методом,
        так как они уже должны быть сохранены или удалены отдельно.

        Args:
            entity_id: ID сущности, черновики которой нужно удалить.
        """
        # Определяем, были ли у сущности собственные изменения
        status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
        had_own = status in ('own', 'both')

        # Удаляем черновики и статус

        # # После сохранения сбрасываем статус и черновики
        # self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)

        # Удаляем все ключи, начинающиеся с "entity_type:entity_id:"
        # (включая возможные остаточные дочерние черновики – они уже применены)
        temp = f"{self._entity_type}:{entity_id}"
        self._draft_registry.discard_by_prefix(f"{temp}:") # Удаляем ТОЛЬКО прямые черновики этой сущности (но не дочерние)

        # Удаляем статус и счётчик
        self._draft_registry.delete_entity_status(self._entity_type, entity_id)
        self._draft_registry.discard(f"__counter__:{temp}")

        # Если были собственные изменения – уведомляем родителя (уменьшаем его счётчик)
        if had_own:
            self._update_parent_child_counter(entity_id, -1)

    def _update_parent_child_counter(self, entity_id: int, delta: int) -> None:
        """
        Уведомляет родителя (если он есть) об изменении количества потомков с не‑None статусом.
        Используется при удалении строки или при сохранении удалённой строки.

        Args:
            entity_id: ID сущности, у которой изменился статус (например, фото).
            delta: Изменение счётчика (+1 – появился изменённый потомок, -1 – исчез).
        """

        # Если есть родитель, увеличиваем счётчик его потомков
        parent_id = self._get_parent_id(entity_id)
        if parent_id is not None:
            self.mark_child_change(parent_id, delta)