# app/draft/ihierarchical_editable.py
"""
Расширенный интерфейс для компонентов, имеющих дочерние черновики.
"""

from abc import abstractmethod
from typing import List

from app.draft.editable_component import IEditableComponent
from app.draft.draft_registry import DraftRegistry


class IHierarchicalEditableComponent(IEditableComponent):

    """
    Интерфейс для компонента, который может содержать дочерние компоненты с черновиками.
    """

    @abstractmethod
    def add_child(self, child: IEditableComponent) -> None:
        """Добавляет дочерний компонент."""
        pass

    @abstractmethod
    def remove_child(self, child: IEditableComponent) -> None:
        """Удаляет дочерний компонент."""
        pass

    @abstractmethod
    def get_children(self) -> List[IEditableComponent]:
        """Возвращает список дочерних компонентов."""
        pass

    @abstractmethod
    def has_descendant_changes(self, registry: DraftRegistry) -> bool:
        """
        Рекурсивно проверяет наличие изменений в этом компоненте или любом из его потомков.

        Args:
            registry: Реестр черновиков.

        Returns:
            True, если есть изменения хотя бы в одном компоненте поддерева.
        """
        pass