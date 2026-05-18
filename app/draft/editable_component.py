# app/draft/editable_component.py
"""
Абстрактный интерфейс для компонентов, поддерживающих редактирование с черновиками.

**Цель интерфейса:**
    Позволить любым виджетам (например, `PhotoUploaderWidget`) участвовать в единой системе
    древовидных черновиков, управляемой `DraftRegistry` и `PaginatedListPage`. Компонент
    может быть как листом (не имеет детей), так и внутренним узлом (имеет собственные дочерние
    компоненты). Все компоненты, добавляемые в `PaginatedListPage` через `add_draft_child`,
    **должны реализовывать этот интерфейс**.

**Обязанности компонента:**
    - Предоставлять уникальный ключ (`get_draft_key`), по которому его черновики хранятся в реестре.
      Ключ должен иметь вид `{entity_type}:{parent_id}:{subsystem}` (например, `"appointment:123:photos"`).
    - Уметь сохранять своё состояние в реестр (`save_to_registry`) и восстанавливать из него
      (`load_from_registry`). Для сохранения обычно используется `dump_state()`.
    - Сообщать, есть ли у него активные черновики (`has_changes`).
    - Применять свои черновики к БД (`apply`) и удалять их из реестра после успешного применения.
    - Отменять свои черновики (`discard`) – удалять из реестра и сбрасывать UI.
    - **Ключевое нововведение:** поддерживать callback для уведомления родительской страницы
      об изменении количества активных черновиков (`set_draft_change_notifier`).
      Этот callback должен вызываться при каждом создании или удалении черновика в компоненте,
      передавая `(parent_id, delta)`, где `delta = +1` для создания, `-1` для удаления.
      Без этого счётчики детей в `PaginatedListPage` будут неточными.

**Требования к реализации в дочернем компоненте:**
    - Реализовать все абстрактные методы.
    - В методе `apply` использовать `registry.apply_and_clear(self.get_draft_key(), applier)`
      или вручную вызвать `registry.discard(self.get_draft_key())` после успешного сохранения.
      Если не удалить черновик, он останется в реестре и может быть повторно применён.
    - При изменении состояния (появление/исчезновение черновика) вызывать `_notify_parent(parent_id, delta)`,
      если родительский ID известен.
    - Рекомендуется наследовать `EditableComponentMixin` для получения готовой логики подписки на реестр,
      управления дочерними компонентами и метода `_notify_parent`.

**Автоматическая синхронизация с реестром (подписка):**
    - Компонент может подписаться на изменения своего ключа в реестре
        через вызов `subscribe_to_registry(registry)`. После подписки
        при любом добавлении/удалении черновика по этому ключу компонент
        получит сигнал и вызовет `load_from_registry(registry)`.
    - Это позволяет отказаться от ручных вызовов `_load_drafts_for_children()`
        со стороны родительской страницы.
    - При смене родительского ID (например, при переходе на другую строку таблицы)
        компонент должен переподписаться на новый ключ. Для этого используется
        метод `update_parent_id(parent_id)`, который должен быть переопределён
        в наследниках, если ключ зависит от `parent_id`.

**Пример реализации в дочернем компоненте (например, PhotoUploaderWidget):**
    def update_parent_id(self, parent_id: int):
        self._parent_id = parent_id
        if self._registry:
            self.unsubscribe_from_registry(self._registry)
            self.subscribe_to_registry(self._registry)     

**Пример реализации для виджета фото (схематично):**
    ```python
    class PhotoUploaderWidget(EditableComponentMixin):
        def get_draft_key(self):
            return f"appointment:{self._appointment_id}:photos"
        def dump_state(self):
            return {'pending_photos': [...], 'deleted_photo_ids': [...], ...}
        def save_to_registry(self, registry):
            registry.set(self.get_draft_key(), self.dump_state())
            self.changed.emit()
            if self._appointment_id:
                self._notify_parent(self._appointment_id, +1)   # уведомляем о создании черновика
        def apply(self, registry, parent_id=None, service=None):
            def applier(data):
                # сохраняем фото в БД через сервис
                service.update_photos_for_appointment(parent_id, data['pending_photos'], data['deleted_photo_ids'])
            registry.apply_and_clear(self.get_draft_key(), applier)
            # после применения черновик удалён, уведомляем родителя
            self._notify_parent(parent_id, -1)
        def discard(self, registry):
            registry.discard(self.get_draft_key())
            self.clear_ui()
            self.changed.emit()
            self._notify_parent(self._appointment_id, -1)


ВАЖНО: Любой компонент, реализующий IEditableComponent и добавляемый через add_child,
ОБЯЗАН реализовывать метод set_draft_change_notifier и вызывать переданный callback
при каждом изменении количества активных черновиков (создание/удаление).
Без этого счётчики родителей будут неточными.
"""

from abc import ABC, abstractmethod
from typing import (
    # Dict, Any,
    Optional, List, Callable
)

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

    @abstractmethod
    def set_draft_change_notifier(self, notifier: Callable[[int, int], None]) -> None:
        """
        Устанавливает callback для уведомления родительской страницы об изменении количества черновиков.

        **Обязательность:**
            Любой компонент, реализующий `IEditableComponent` и добавляемый в `PaginatedListPage`
            через `add_draft_child`, **обязан** вызывать этот callback при каждом изменении
            количества активных черновиков (создание или удаление).

        **Параметры callback:**
            - parent_id (int): ID родительской сущности (например, ID приёма для фото).
            - delta (int): +1 при появлении нового черновика, -1 при его исчезновении.

        **Пример вызова внутри компонента:**
            ```python
            def _add_new_photo(self):
                # ... логика добавления фото ...
                if self._draft_change_notifier:
                    self._draft_change_notifier(self._parent_id, +1)
        """

        pass


class EditableComponentMixin(QObject, IEditableComponent):
    """
    Базовый миксин для виджетов, реализующих IEditableComponent.

    Предоставляет:
        - Ленивую инициализацию атрибутов (чтобы не требовать вызова `__init__` в наследниках).
        - Методы `add_child`, `remove_child`, `get_children` для построения дерева компонентов.
        - Механизм подписки на изменения реестра (`_subscribe_to_registry`, `_unsubscribe_from_registry`).
        - Метод `_notify_parent(parent_id, delta)` для вызова сохранённого callback.
        - Сигнал `changed`, который должен испускаться при любом изменении состояния черновика.

    **Требования к наследникам:**
        - Реализовать абстрактные методы (`get_draft_key`, `load_from_registry`, `has_changes`,
          `apply`, `discard`, `set_draft_change_notifier`).
        - В методах, изменяющих количество черновиков (добавление/удаление), вызывать
          `self._notify_parent(parent_id, delta)` после изменения.
        - Испускать сигнал `self.changed.emit()` после любых изменений.

    **Как использовать в наследнике:**
        1. Унаследовать этот класс.
        2. Реализовать абстрактные методы (`get_draft_key`, `load_from_registry`, `has_changes`,
           `apply`, `discard`, а также `set_draft_change_notifier`, если требуется уведомлять родителя).
        3. В методах, изменяющих количество черновиков (например, при добавлении/удалении фото),
           вызывать `self._notify_parent(parent_id, delta)` после изменения.
        4. Испускать сигнал `self.changed.emit()` после любых изменений.
        5. Опционально переопределить `save_to_registry` и `discard` для собственной логики,
           но не забывать вызывать `super().save_to_registry(registry)` или хотя бы `self.changed.emit()`.

    **Важно:** Если наследник не вызывает `_notify_parent`, родительская страница не узнает
        об изменении количества черновиков, и счётчики детей могут стать неточными.

        **Автоматическая синхронизация с реестром (подписка):**
        - Компонент может подписаться на изменения своего ключа в реестре
          через вызов `subscribe_to_registry(registry)`. После подписки
          при любом добавлении/удалении черновика по этому ключу компонент
          получит сигнал и вызовет `load_from_registry(registry)`.
        - Это позволяет отказаться от ручных вызовов `_load_drafts_for_children()`
          со стороны родительской страницы.
        - При смене родительского ID (например, при переходе на другую строку таблицы)
          компонент должен переподписаться на новый ключ. Для этого используется
          метод `update_parent_id(parent_id)`, который должен быть переопределён
          в наследниках, если ключ зависит от `parent_id`.

    **Пример использования в дочернем компоненте (например, PhotoUploaderWidget):**
        def update_parent_id(self, parent_id: int):
            self._parent_id = parent_id
            if self._registry:
                self.unsubscribe_from_registry(self._registry)
                self.subscribe_to_registry(self._registry)
    """

    changed = Signal()   # сигнал, испускаемый при изменении состояния черновика

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        if not hasattr(self, '_logger'):
            self._logger = AppLogger.get_instance(
                name='gui.EditableComponentMixin',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        return self._logger
    
    @logger.setter
    def logger(self, value):
        self._logger = value

    @property
    def _registry_subscribed(self) -> bool:
        if not hasattr(self, '__registry_subscribed'):
            self.__registry_subscribed = False
        return self.__registry_subscribed

    @_registry_subscribed.setter
    def _registry_subscribed(self, value):
        self.__registry_subscribed = value

    @property
    def _registry(self) -> Optional[DraftRegistry]:
        if not hasattr(self, '__registry'):
            self.__registry = None
        return self.__registry

    @_registry.setter
    def _registry(self, value):
        self.__registry = value

    @property
    def _children(self) -> List[IEditableComponent]:
        if not hasattr(self, '__children'):
            self.__children = []
        return self.__children

    @_children.setter
    def _children(self, value):
        self.__children = value

    @property
    def _has_child_changes(self) -> bool:
        if not hasattr(self, '__has_child_changes'):
            self.__has_child_changes = False
        return self.__has_child_changes

    @_has_child_changes.setter
    def _has_child_changes(self, value):
        self.__has_child_changes = value

    @property
    def _draft_change_notifier(self):
        if not hasattr(self, '__draft_change_notifier'):
            self.__draft_change_notifier = None
        return self.__draft_change_notifier

    @_draft_change_notifier.setter
    def _draft_change_notifier(self, value):
        self.__draft_change_notifier = value

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, parent=None):

        super().__init__(parent)

        # self._registry_subscribed = False
        # self._registry = None
        #
        # self._children: List[IEditableComponent] = []
        # self._has_child_changes = False

    def get_draft_key(self) -> str:
        raise NotImplementedError("Must be implemented in subclass")

    def load_from_registry(self, registry: DraftRegistry) -> None:
        raise NotImplementedError

    def has_changes(self, registry: DraftRegistry) -> bool:
        raise NotImplementedError

    def apply(self, registry: DraftRegistry, parent_id: Optional[int] = None, service=None) -> None:
        raise NotImplementedError

    def set_draft_change_notifier(
        self,
        notifier: Callable[[int, int], None]
    ) -> None:
        """
        Устанавливает callback для уведомления родительской страницы об изменении количества черновиков.

        **Обязательность:**
            Любой компонент, реализующий `IEditableComponent` и добавляемый в `PaginatedListPage`
            через `add_draft_child`, **обязан** вызывать этот callback при каждом изменении
            количества активных черновиков (создание или удаление).

        **Параметры callback:**
            - parent_id (int): ID родительской сущности (например, ID приёма для фото).
            - delta (int): +1 при появлении нового черновика, -1 при его исчезновении.

        **Типичная реализация в наследнике:**
            def set_draft_change_notifier(self, notifier):
                self._draft_change_notifier = notifier

            def _add_new_item(self):
                # ... добавляем черновик ...
                if self._draft_change_notifier:
                    self._draft_change_notifier(self._parent_id, +1)

            def _remove_item(self):
                # ... удаляем черновик ...
                if self._draft_change_notifier:
                    self._draft_change_notifier(self._parent_id, -1)

        **Пример вызова внутри компонента:**
            ```python
            def _add_new_photo(self):
                # ... логика добавления фото ...
                if self._draft_change_notifier:
                    self._draft_change_notifier(self._parent_id, +1)

        Args:
            notifier: Callback, принимающий (parent_id, delta).
        """

        self._draft_change_notifier = notifier

    def _notify_parent(self, parent_id: int, delta: int) -> None:
        """Вызывает сохранённый callback, если он есть."""
        if hasattr(self, '_draft_change_notifier') and self._draft_change_notifier:
            self._draft_change_notifier(parent_id, delta)

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
        """
        Пересчитывает флаг `_has_child_changes` на основе текущих детей.

        **Алгоритм:**
            - Проходит по всем дочерним компонентам.
            - Для каждого вызывает `child.has_changes(self._registry)`.
            - Если хотя бы один ребёнок возвращает True, `_has_child_changes` = True.

        **Важно:** Этот метод вызывается при добавлении/удалении дочернего компонента,
            а также при получении сигнала `changed` от любого из детей.

        **Требование к дочерним компонентам:**
            Они **должны** реализовывать метод `has_changes(registry)`. Если ребёнок
            его не реализует, возникнет ошибка (это оправдано, так как компонент без
            этого метода не может правильно сообщить о наличии изменений).

        **Альтернативный подход:**
            Можно полагаться только на сигналы `changed` и не проверять `has_changes` явно,
            но это может привести к неточностям, если сигнал был пропущен. Поэтому проверка
            через `has_changes` является более надёжной.

        **Безопасность:**
            Метод не вызывает ошибок, если `self._registry` ещё не инициализирован
            (например, до вызова `_subscribe_to_registry`). В этом случае пересчёт пропускается.
        """

        if self._registry is None:
            return

        # Проверяем каждого ребёнка через его метод has_changes
        # Если ребёнок не реализует has_changes – будет ошибка (см. требования выше)
        self._has_child_changes = any(
            child.has_changes(self._registry) for child in self._children
        )

    # ----------------------------------------------------------------------
    # Методы IHierarchicalEditableComponent
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def has_descendant_changes(self, registry: DraftRegistry) -> bool:
        """
        Рекурсивно проверяет наличие изменений в этом компоненте или любом из его потомков.

        Для проверки собственных изменений используется прямой вызов registry.has(self.get_draft_key()),
        а не абстрактный метод has_changes. Это позволяет миксину работать без реализации has_changes
        в наследниках (хотя наследники могут переопределить has_changes для своей логики).

        Args:
            registry: Реестр черновиков.

        Returns:
            True, если есть изменения хотя бы в одном компоненте поддерева.
        """

        # Проверяем наличие черновика непосредственно у этого компонента
        # if self.has_changes(registry):
        if registry.has(self.get_draft_key()):
            return True

        # Рекурсивно проверяем всех детей
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
        """
        Сохраняет текущее состояние компонента в реестр черновиков.

        **Важно:** Этот метод должен быть переопределён в конкретном компоненте,
        если он имеет собственную структуру данных для черновика. Базовая реализация
        предполагает наличие метода `dump_state()`, возвращающего словарь с состоянием,
        и сохраняет его в реестр по ключу `self.get_draft_key()`.

        После сохранения испускается сигнал `changed`, чтобы родительские компоненты
        могли обновить свои статусы.

        Args:
            registry (DraftRegistry): Реестр черновиков, в который сохраняется состояние.

        Пример переопределения в дочернем классе:
            def save_to_registry(self, registry):
                key = self.get_draft_key()
                state = self.dump_state()   # возвращает dict
                registry.set(key, state)
                self.changed.emit()
        """

        if hasattr(self, 'dump_state'):
            registry.set(self.get_draft_key(), self.dump_state())

        # super().save_to_registry(registry)
        self.changed.emit()

    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard(self, registry: DraftRegistry) -> None:
        """
        Отменяет изменения компонента: удаляет черновик из реестра и сбрасывает UI.

        Базовая реализация:
            1. Удаляет запись из реестра по ключу `self.get_draft_key()`.
            2. Испускает сигнал `changed`, чтобы уведомить родительские компоненты.

        **Важно:** Наследники, имеющие сложную внутреннюю структуру, могут переопределить
        этот метод, добавив дополнительную логику (например, очистку виджетов).

        Args:
            registry (DraftRegistry): Реестр черновиков, из которого удаляется состояние.

        Пример переопределения в дочернем классе:
            def discard(self, registry):
                key = self.get_draft_key()
                registry.discard(key)
                self.clear_ui()          # дополнительная очистка
                self.changed.emit()
        """

        registry.discard(self.get_draft_key())

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

    def subscribe_to_registry(self, registry: DraftRegistry) -> None:
        """
        Подписывает компонент на изменения в реестре по его ключу.
        После подписки компонент будет автоматически получать сигнал
        при добавлении/удалении черновика и вызывать `load_from_registry(registry)`.
        """
            
        self._subscribe_to_registry(registry, prefix=None)

    def unsubscribe_from_registry(self, registry: DraftRegistry) -> None:
        """
        Отписывает компонент от реестра.
        """

        self._unsubscribe_from_registry(registry, prefix=None)

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


    @AppLogger.get_instance(
        name='EditableComponentMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def update_parent_id(self, parent_id: int) -> None:
        """
        Обновляет идентификатор родителя и переподписывается на реестр,
        если ключ черновика зависит от parent_id.
        Должен быть переопределён в наследниках, у которых ключ динамический.
        Базовая реализация ничего не делает.
        """

        pass