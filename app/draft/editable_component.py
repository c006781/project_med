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

from PySide6.QtCore import QObject


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