# interfaces/gui/gui_window/mixins/draft_tree_mixin.py
"""
Миксин для поддержки древовидных черновиков в странице списка.
"""

from typing import Optional, Callable, Dict, Any
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


    # def _ensure_draft_attrs(self) -> None:
    #     """Гарантирует наличие атрибутов черновика (ленивая инициализация)."""

    #     if not hasattr(self, '_children_components'):
    #         self._children_components = []

    #     if not hasattr(self, '_draft_modified'):
    #         self._draft_modified = False

    @property
    def _children_components(self):
        if not hasattr(self, '__children_components'):
            self.__children_components = False

        return self.__children_components

    @_draft_modified.setter
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