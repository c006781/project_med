# app/draft/editable_component.py
"""
Абстрактный интерфейс для компонентов, поддерживающих редактирование с черновиками.

Компонент должен:
- Иметь возможность сохранять своё состояние в DraftRegistry.
- Загружать состояние из реестра.
- Сообщать, есть ли изменения.
- Применять изменения к БД (через сервисы).
- Отменять изменения (удалять черновик).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from app.utils.logger.logger import AppLogger

from app.draft.draft_registry import DraftRegistry

from PySide6.QtCore import QObject, Signal


class IEditableComponent(ABC):
    """
    Интерфейс для компонента, который может иметь черновики.
    """

    # @AppLogger.get_instance(
    #     name='IEditableComponent',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @abstractmethod
    def get_draft_key(self) -> str:
        """
        Возвращает уникальный ключ для доступа к черновику в реестре.
        Ключ должен быть стабильным для данного экземпляра компонента.

        :return: Строка вида "entity_type:entity_id:subsystem"
        """
        
        pass

    # @AppLogger.get_instance(
    #     name='IEditableComponent',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @abstractmethod
    def load_from_registry(self, registry: DraftRegistry) -> None:
        """
        Загружает данные из реестра в UI компонента.
        Если черновика нет, загружает исходные данные (из БД или пустые).

        :param registry: Экземпляр DraftRegistry.
        """
        pass

    # @AppLogger.get_instance(
    #     name='IEditableComponent',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @abstractmethod
    def save_to_registry(self, registry: DraftRegistry) -> None:
        """
        Сохраняет текущее состояние UI компонента в реестр.

        :param registry: Экземпляр DraftRegistry.
        """
        pass

    # @AppLogger.get_instance(
    #     name='IEditableComponent',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @abstractmethod
    def has_changes(self, registry: DraftRegistry) -> bool:
        """
        Проверяет, есть ли у компонента несохранённые изменения.

        :param registry: Экземпляр DraftRegistry.
        :return: True, если изменения есть.
        """
        pass

    # @AppLogger.get_instance(
    #     name='IEditableComponent',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @abstractmethod
    def apply(self, registry: DraftRegistry, parent_id: Optional[int] = None, service=None) -> None:
        """
        Применяет изменения компонента к БД с помощью переданного сервиса.
        Должен вызывать registry.apply_and_clear(self.get_draft_key(), applier).

        :param registry: Экземпляр DraftRegistry.
        :param parent_id: ID родительской сущности (например, ID приёма для фото).
        :param service: Сервис, необходимый для сохранения.
        """
        pass

    # @AppLogger.get_instance(
    #     name='IEditableComponent',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    @abstractmethod
    def discard(self, registry: DraftRegistry) -> None:
        """
        Отменяет изменения компонента: удаляет черновик из реестра и сбрасывает UI.
        """
        pass


class EditableComponentMixin(QObject, IEditableComponent):
    """
    Базовый миксин для виджетов, реализующих IEditableComponent.
    Предоставляет общую логику подписки на изменения реестра и обновления UI.
    """ 

    changed = Signal()   # сигнал, испускаемый при изменении состояния черновика

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, parent=None):

        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='draft.EditableComponentMixin',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        self._registry_subscribed = False
        self._registry = None

        self._children: List[IEditableComponent] = []
        self._has_child_changes = False

    # ----------------------------------------------------------------------
    # Управление дочерними компонентами
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def add_child(self, child: IEditableComponent) -> None:
        """Добавляет дочерний компонент и подписывается на его сигнал changed."""

        if child not in self._children:
            self._children.append(child)
            # Если у ребёнка есть сигнал changed, подключаемся
            if hasattr(child, 'changed'):
                child.changed.connect(self._on_child_changed)
            self._update_child_changes()

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def remove_child(self, child: IEditableComponent) -> None:
        """Удаляет дочерний компонент."""

        if child in self._children:
            self._children.remove(child)
            if hasattr(child, 'changed'):
                child.changed.disconnect(self._on_child_changed)
            self._update_child_changes()

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_children(self) -> List[IEditableComponent]:

        return self._children.copy()

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _on_child_changed(self) -> None:
        """Вызывается при изменении состояния дочернего компонента."""

        self._update_child_changes()
        self.changed.emit()

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _update_child_changes(self) -> None:
        """Пересчитывает флаг _has_child_changes на основе текущих детей."""

        # Для эффективности можно проверять has_changes у детей через реестр
        # Но проще полагаться на сигналы. При добавлении/удалении – пересчёт.
        # Здесь не требуется сложная логика, так как каждый ребёнок сам испускает сигнал.
        # Поэтому просто устанавливаем флаг в True, если есть хотя бы один ребёнок
        # (сигнал already indicates change). Но для точности можно проверить.
        self._has_child_changes = any(child.has_changes(self._registry) for child in self._children)

    # ----------------------------------------------------------------------
    # Методы IHierarchicalEditableComponent
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def has_descendant_changes(self, registry: DraftRegistry) -> bool:
        """Рекурсивно проверяет наличие изменений в поддереве."""

        if self.has_changes(registry):
            return True
        
        for child in self._children:
            if hasattr(child, 'has_descendant_changes'):
                if child.has_descendant_changes(registry):
                    return True
                
            elif child.has_changes(registry):
                return True
            
        return False

    # ----------------------------------------------------------------------
    # Существующие методы (с добавлением сигнала при изменении)
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def save_to_registry(self, registry: DraftRegistry) -> None:
        """Сохраняет состояние в реестр и испускает сигнал changed."""

        # super().save_to_registry(registry)
        self.changed.emit()

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard(self, registry: DraftRegistry) -> None:
        """Отменяет изменения и испускает сигнал changed."""

        # super().discard(registry)
        self.changed.emit()   

    def _get_child_service(self, child_name: str = None):
        # заглушка.
        # В AppointmentListPage переопределить для возврата self._photo_service

        return None    

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _subscribe_to_registry(self, registry: DraftRegistry, prefix: Optional[str] = None) -> None:
        """
        Подписывается на изменения реестра (по ключу или префиксу).
        При получении сигнала вызывает self.on_registry_changed.

        :param registry: Экземпляр DraftRegistry.
        :param prefix: Если передан, подписывается на префикс, иначе на точный ключ.
        """

        if self._registry_subscribed and self._registry is registry:
            return

        self._registry = registry
        key = self.get_draft_key()

        if prefix is not None:
            registry.subscribe_prefix(prefix, self._on_registry_change)
        else:
            registry.subscribe(key, self._on_registry_change)

        self._registry_subscribed = True

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _unsubscribe_from_registry(self, registry: DraftRegistry, prefix: Optional[str] = None) -> None:
        """
        Отписывается от реестра.
        """
        if not self._registry_subscribed:
            return
        
        key = self.get_draft_key()

        if prefix is not None:
            registry.unsubscribe_prefix(prefix, self._on_registry_change)
        else:
            registry.unsubscribe(key, self._on_registry_change)

        self._registry_subscribed = False

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _on_registry_change(self, key: str, has_draft: bool) -> None:
        """
        Обработчик изменения черновика в реестре.
        Вызывает переопределяемый метод on_registry_changed.

        :param key: Ключ изменённого черновика.
        :param has_draft: True – добавлен, False – удалён.
        """

        if key == self.get_draft_key() or key.startswith(self.get_draft_key() + ':'):
            self.on_registry_changed(key, has_draft)

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def on_registry_changed(self, key: str, has_draft: bool) -> None:
        """
        Вызывается при изменении черновика, связанного с этим компонентом.
        Может быть переопределён в наследниках для синхронизации UI.

        :param key: Ключ изменённого черновика.
        :param has_draft: True – черновик добавлен, False – удалён.
        """

        self.logger.debug(f"Registry changed: {key}, has_draft={has_draft}")
        # По умолчанию просто перезагружаем состояние
        if has_draft:
            self.load_from_registry(self._registry)
        else:
            # Черновик удалён – загружаем исходные данные
            self.load_from_registry(self._registry)