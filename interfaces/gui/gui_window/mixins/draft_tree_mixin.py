# interfaces/gui/gui_window/mixins/draft_tree_mixin.py
"""
Миксин для поддержки древовидных черновиков в странице списка.

**Основные задачи:**
    1. Хранение и актуализация статусов сущностей (`None/own/child/both`).
    2. Синхронизация счётчиков потомков (для быстрого пересчёта статуса родителя).
    3. Распространение изменений статуса вверх по дереву (при появлении/исчезновении черновика)
       и вниз по дереву (при отмене изменений).
    4. Предоставление публичных методов для пометки собственных изменений (`mark_own_change`),
       уведомления об изменениях потомков (`mark_child_change`) и отмены целого поддерева
       (`discard_entity_subtree`).

**Как это работает:**
    - Каждая сущность (строка таблицы) имеет статус, хранящийся в реестре по ключу
      `__status__:{entity_type}:{entity_id}`. Статус вычисляется на основе флага собственных изменений
      и количества потомков с не‑None статусом (счётчик).
    - При изменении статуса любой сущности вызывается _propagate_status_up, которая
      рекурсивно обновляет статусы всех предков.
    - При отмене изменений (discard_entity_subtree) сначала сбрасываются статусы потомков,
      затем статус самой сущности, и обновляется родитель.

**Связь с PaginatedListPage:**
    - Данный миксин используется исключительно внутри PaginatedListPage (и его наследников).
    - Атрибут self._entity_type должен быть определён в классе, использующем миксин.
    - Атрибут self._draft_registry (DraftRegistry) создаётся в PaginatedListPage.
    - Методы _get_parent_id и _get_children_ids переопределяются в наследниках для конкретной доменной логики.


**Требования к наследникам:**
    - Должен быть определён атрибут `self._entity_type` (строка, идентифицирующая тип сущности).
    - Должен быть определён атрибут `self._draft_registry` (экземпляр `DraftRegistry`).
    - Должен быть переопределён метод `_get_parent_id(child_id)`, возвращающий ID родителя
      для дочерней сущности (или `None`).
    - Для каскадного удаления одного типа может потребоваться переопределить `_get_children_ids(parent_id)`.

**Сигналы:**
    - `draft_modified_changed(bool)`: испускается при изменении флага `_draft_modified`
      (наличие изменений в поддереве, начиная с текущего компонента). Используется для перекраски строки.
    - `entity_status_changed(int, bool)`: испускается при изменении статуса конкретной сущности
      (передаётся entity_id и флаг наличия изменений). Используется для обновления цвета строки и кнопки.

**Пример использования в странице:**
    ```python
    class MyListPage(PaginatedListPage, DraftTreeMixin):
        def __init__(self, ...):
            super().__init__(...)
            self._draft_registry = DraftRegistry(self)
            self._draft_registry.draft_changed.connect(self._on_draft_registry_changed)
            self.entity_status_changed.connect(self._on_entity_status_changed)
            # ...
"""

from typing import Optional, Callable, Dict, Any, Set
from PySide6.QtCore import Signal

from app.utils.logger.logger import AppLogger

from app.draft.draft_registry import DraftRegistry
from app.draft.ihierarchical_editable import IHierarchicalEditableComponent


class DraftTreeMixin:
    """
    Предоставляет методы для управления деревом черновиков.

    Требует наличия атрибутов:
        - self._draft_registry (DraftRegistry)
        - self._draft_component_id (str) – ключ для текущего компонента
        - self._children_components (list) – список дочерних IEditableComponent
        - self.logger (AppLogger)
        Атрибуты _children_components и _draft_modified будут созданы автоматически пустыми / отключенными

    Сигналы:
        draft_modified_changed(bool): Испускается при изменении состояния черновиков в поддереве.
        
    """

    #  self._entity_type - из основного класса

    draft_modified_changed = Signal(bool)

    entity_status_changed = Signal(int, bool)  # (entity_id, has_changes)

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        """Кэш статусов для сущностей (entity_id -> status)."""
        if not hasattr(self, '_logger'):
            self._logger = AppLogger.get_instance(
                name='gui.DraftTreeMixin',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @property
    def _status_cache(self) -> Dict[int, Optional[str]]:
        """Кэш статусов для сущностей (entity_id -> status)."""
        if not hasattr(self, '__status_cache'):
            self.__status_cache = {}
        return self.__status_cache

    @_status_cache.setter
    def _status_cache(self, value):
        self.__status_cache = value

    @property
    def _parent_cache(self) -> Dict[int, int]:
        """Кэш parent_id для дочерних сущностей (child_id -> parent_id)."""
        if not hasattr(self, '__parent_cache'):
            self.__parent_cache = {}
        return self.__parent_cache

    @_parent_cache.setter
    def _parent_cache(self, value):
        self.__parent_cache = value

    @property
    def _children_cache(self) -> Dict[int, Set[int]]:
        """Кэш множеств дочерних ID для родителя (parent_id -> set[child_id])."""
        if not hasattr(self, '__children_cache'):
            self.__children_cache = {}
        return self.__children_cache

    @_children_cache.setter
    def _children_cache(self, value):
        self.__children_cache = value

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

    # def __init__(self):
    #     # self._logger = None
    #     pass

    def setup_draft_tree(self, registry: DraftRegistry, component_id: str) -> None:
        """
        Инициализирует дерево черновиков для нового ключа компонента.

        При смене выбранной строки вызывается повторно, поэтому необходимо:
            - Отписаться от предыдущего ключа (если был),
            - Сбросить внутренний флаг `_draft_modified`,
            - Подписаться на новый ключ,
            - Немедленно пересчитать состояние черновиков для нового ключа.

        Args:
            registry: Реестр черновиков (обычно один на страницу).
            component_id: Уникальный ключ для текущего компонента, например "appointment:123:".
        """

        # Отписываемся от предыдущего ключа, если он был установлен.
        #    Это предотвращает накопление подписок и утечки памяти.
        if hasattr(self, '_draft_component_id') and self._draft_component_id is not None:
            # Используем тот же реестр, который хранится в self._draft_registry
            # (он не меняется между вызовами setup_draft_tree)
            self._draft_registry.unsubscribe(self._draft_component_id, self._on_registry_changed)

        # Сохраняем новый реестр и ключ.
        #    Реестр обычно один и тот же, но на всякий случай обновляем.
        self._draft_registry = registry
        self._draft_component_id = component_id

        # Сбрасываем флаг `_draft_modified` в False.
        #    Это необходимо, чтобы при следующем вызове `_update_modified_state()`
        #    мы не ошибочно сохранили старое значение от предыдущего ключа.
        self._draft_modified = False

        # self._children_components = []
        # self._draft_modified = False
    
        # # Ленивая инициализация атрибутов
        # if not hasattr(self, '_children_components'):
        #     self._children_components = []

        # if not hasattr(self, '_draft_modified'):
        #     self._draft_modified = False

        # Подписываемся на изменения в реестре для ключа текущего компонента
        #    При любом добавлении/удалении черновика по этому ключу будет вызван
        #    self._on_registry_changed, который запустит пересчёт состояния.
        registry.subscribe(component_id, self._on_registry_changed)

        # Немедленно пересчитываем состояние черновиков для нового ключа.
        #    Это гарантирует, что `_draft_modified` примет правильное значение
        #    (если черновики уже существовали в реестре до подписки).
        self._update_modified_state()


    # def _discard_all_changes(self): # удалил, так как в PaginatedListPage своя реализация
    #     """
    #     Полностью отменяет все несохранённые изменения для текущего типа сущности.
    #     Очищает реестр, сбрасывает кэш, перезагружает данные.
    #     """
    #     # переопределение метода _discard_all_changes из EditModeMixin
    #
    #     # 1. Очищаем реестр от всех черновиков, статусов, счётчиков для текущего типа
    #     self._clear_entity_registry()
    #
    #     # 2. Перезагружаем данные из БД (первая страница)
    #     self.reload_data()
    #
    #     # 3. Сбрасываем цвета строк в таблице
    #     self.source_model.clear_row_colors()
    #
    #     # 4. Очищаем черновики дочерних компонентов (если есть)
    #     for child in self._children_components:
    #         if hasattr(child, 'discard'):
    #             child.discard(self._draft_registry)
    #
    #     # 5. Обновляем состояние кнопки сохранения
    #     self._update_save_button_state()
    #
    #     self.logger.debug(f"Глобальная отмена изменений для типа {self._entity_type}")


    # def add_draft_child(self, child: IHierarchicalEditableComponent) -> None:
    #     """
    #     Добавляет дочерний компонент и подписывается на его сигнал changed.
    #     """
    #
    #     if child not in self._children_components:
    #         self._children_components.append(child)
    #         if hasattr(child, 'changed'):
    #             child.changed.connect(self._on_child_changed)
    #
    #         # Также подписываемся на draft_modified_changed, если есть
    #         if hasattr(child, 'draft_modified_changed'):
    #             child.draft_modified_changed.connect(self._on_child_modified_changed)
    #
    #         self._update_modified_state()

    def add_draft_child(self, child: IHierarchicalEditableComponent) -> None:
        """
        Добавляет дочерний компонент и передаёт ему callback для уведомления родителя.

        **Требование к дочернему компоненту:**
            Он **обязан** реализовывать метод `set_draft_change_notifier` и вызывать переданный
            callback при каждом изменении количества активных черновиков (создание/удаление).
            Пример вызова: `notifier(parent_id, +1)` при появлении черновика,
            `notifier(parent_id, -1)` при его исчезновении (отмена или применение).

            Без этого счётчики родителей будут неточными, и статусы могут вычисляться неверно.

        Args:
            child: Компонент, реализующий IHierarchicalEditableComponent.
        """

        if child not in self._children_components:
            self._children_components.append(child)
            if hasattr(child, 'changed'):
                child.changed.connect(self._on_child_changed)

            if hasattr(child, 'draft_modified_changed'):
                child.draft_modified_changed.connect(self._on_child_modified_changed)

            # Передаём компоненту callback для уведомления родителя
            if hasattr(child, 'set_draft_change_notifier'):
                # Создаём замыкание, которое будет вызывать mark_child_change страницы
                def notifier(parent_id: int, delta: int):
                    self.mark_child_change(parent_id, delta)

                child.set_draft_change_notifier(notifier)

            else:
                self.logger.warning(
                    f"Дочерний компонент {child.__class__.__name__} не поддерживает set_draft_change_notifier. "
                    "Счётчики детей могут быть неточными."
                )

            self._update_modified_state()

    def remove_draft_child(self, child: IHierarchicalEditableComponent) -> None:
        """Удаляет дочерний компонент."""

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
        
        prefix = self._draft_component_id
        self._draft_registry.apply_subtree(prefix, applier)

    def discard_subtree(self) -> None:
        """Отменяет все черновики текущего поддерева."""
        prefix = self._draft_component_id
        self._draft_registry.discard_subtree(prefix)

    def clear_child_drafts(self) -> None:
        """Очищает черновики всех дочерних компонентов (без применения)."""

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
        Устанавливает или снимает флаг собственного изменения для сущности,
        пересчитывает её статус и распространяет изменение вверх по дереву.

        **Что делает метод:**
            1. Получает текущий статус сущности из кэша.
            2. Вычисляет новый статус на основе `has_own_change` и текущего
               количества активных потомков (счётчик из реестра).
            3. Если статус не изменился – ничего не делает.
            4. Если статус изменился:
               - Обновляет кэш и реестр (ключ `__status__`).
               - Испускает сигнал `entity_status_changed` (для перекраски строки).
               - Испускает сигнал `draft_modified_changed` (для изменения состояния поддерева).
               - Запускает распространение изменения вверх по дереву
                 (вызов `_propagate_status_up`), который пересчитывает статусы
                 всех предков.

        **ВАЖНО:**
            - Этот метод **НЕ изменяет счётчики потомков** (`__counter__`).
              Счётчики обновляются отдельно через `mark_child_change` при
              создании/удалении дочерних черновиков.
            - Если вы вызываете этот метод для снятия флага `'own'` после
              сохранения строки, не добавляйте сюда вызов `mark_child_change`,
              иначе счётчик родителя будет уменьшен дважды (один раз здесь,
              один раз в вызывающем коде, который уже уменьшил счётчик).
            - Корректное уменьшение счётчика родителя должно выполняться
              в том месте, где строка перестаёт быть изменённой (например,
              в `_save_new_rows` или `_save_modified_rows`).

        Args:
            entity_id: ID сущности (может быть временным, отрицательным).
            has_own_change: True – установить флаг собственного изменения,
                            False – снять флаг.

        Returns:
            None
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

        **Алгоритм:**
            1. Если delta == 0 – ничего не делаем.
            2. Обновляем счётчик потомков родителя в реестре (inc_child_counter).
            3. Если новое значение счётчика стало отрицательным – логируем предупреждение.

        Args:
            parent_id: ID родительской сущности.
            delta: Изменение количества активных потомков (+1 или -1).
        """

        if delta == 0:
            return

        # Обновляем счётчик в реестре
        new_count = self._draft_registry.inc_child_counter(
            self._entity_type, parent_id, delta
        )

        # Проверка на отрицательное значение – выполняем принудительную коррекцию
        if new_count < 0:
            self.logger.warning(
                f"Счётчик потомков для родителя {parent_id} стал отрицательным ({new_count}). "
                f"Дельта = {delta}. Возможен дисбаланс вызовов mark_child_change."
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
        """
        Рекурсивно обновляет статусы всех предков (вверх по дереву).

        Вызывается после изменения статуса любой сущности. Для каждого родителя:
            - пересчитывается его статус через `_recompute_parent_status`,
            - если статус изменился, распространяется дальше вверх.

        **Важно:** Родительская связь определяется методом `_get_parent_id`, который должен быть
            переопределён в наследнике (например, для фото возвращает ID приёма).
        """

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
        """
        Помечает сущность как имеющую собственные изменения (статус `'own'` или `'both'`).

        Вызывает `_update_own_change`, которая:
            - Вычисляет новый статус на основе флага `has_own_change=True` и текущего счётчика детей.
            - Если статус изменился, обновляет реестр, кэш и испускает сигнал `entity_status_changed`.
            - Запускает распространение изменения вверх по дереву (`_propagate_status_up`).

        Используется:
            - При прямом редактировании ячейки в таблице (через `_on_row_modified_from_model`).
            - При добавлении новой строки (временный ID помечается как `'own'`).
            - При пометке строки на удаление (тоже считается собственным изменением).
        """

        self._update_own_change(entity_id, True)

    def clear_own_change(self, entity_id: int) -> None:
        """
        Снимает флаг собственных изменений (например, после сохранения).

        **Важно:** Этот метод НЕ изменяет счётчик родителей. Если требуется
        уменьшить счётчик родителя (например, потому что изменённый потомок
        стал неизменённым), это должно быть сделано вызывающим кодом
        (например, в _save_new_rows) через mark_child_change. Не добавляйте
        сюда вызов mark_child_change, иначе счётчик будет уменьшен дважды.
        """
        self._update_own_change(entity_id, False)

    def mark_child_change(self, parent_id: int, delta: int) -> None:
        """
        Уведомляет о появлении/исчезновении активного черновика у потомка родителя.

        **Важно:** Этот метод НЕ проверяет parent_id на положительность, потому что
        дочерние черновики могут быть созданы для временного родителя (новая строка с ID < 0).
        При сохранении такой строки черновики переносятся на реальный ID (_transferring_child_drafts),
        а счётчики временного родителя остаются в реестре (они будут удалены при очистке ключей _clean_entity_registry_by_id).
        Это допустимо, так как счётчики с отрицательными ID никогда не используются в логике.

        **Для вызывающего кода:** Если нужно обновить счётчик родителя только для существующих
        сущностей (ID > 0), используйте _update_parent_child_counter, который сам проверяет parent_id.

        Args:
            parent_id: ID родительской сущности (может быть отрицательным для временных строк).
            delta: +1 (появился), -1 (исчез).
        """

        self._update_child_change(parent_id, delta)

    def discard_entity_subtree(self, entity_id: int) -> None:
        """
        Полностью отменяет все изменения для сущности и её потомков.

        **Алгоритм:**
            1. Сохраняет старый статус сущности (до отмены).
            2. Рекурсивно сбрасывает статусы всех потомков (вниз по дереву).
            3. Удаляет все черновики и статус самой сущности из реестра.
            4. Сбрасывает кэш статуса сущности.
            5. Если у сущности был ненулевой статус, уменьшает счётчик её родителя на 1
               (компенсируя увеличение, которое произошло при пометке на удаление или при появлении изменений).
            6. Пересчитывает статус родителя (если есть) – это запустит распространение вверх.

        **Когда используется:**
            - При отмене изменений для существующей строки (пользователь нажал «Отменить» для строки).
            - В `_cancel_selected_rows_changes` для существующих строк (не новых).

        **Важно:**
            - Этот метод удаляет **все** черновики (и свои, и дочерние).
            - Уменьшение счётчика родителя происходит только если у сущности был ненулевой статус.
              Это корректно, потому что при пометке на удаление или при появлении собственных изменений
              счётчик родителя был увеличен ровно один раз.

        Args:
            entity_id: ID сущности, изменения которой отменяются.
        """

        old_status = self._draft_registry.get_entity_status(self._entity_type, entity_id)

        # 1. Сбрасываем статусы потомков (вниз)
        self._propagate_status_down(entity_id)

        # 2. Удаляем все черновики и статус самой сущности
        self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)

        # 3. Сбрасываем кэш статуса сущности
        self._set_cached_status(entity_id, None)

        # Если у entity_id был ненулевой статус, уменьшаем счётчик его родителя
        if old_status is not None:
            self._update_parent_child_counter(entity_id, -1)

        # 4. Обновляем родителя этой сущности (вверх)
        parent_id = self._get_parent_id(entity_id)
        if parent_id is not None:
            self._recompute_parent_status(parent_id)

    ################

    def clear_entity_drafts(self, entity_id: int) -> None:
        """
        Удаляет **только собственные черновики** для данной сущности, оставляя дочерние черновики нетронутыми.

        **Когда используется:**
            - После успешного сохранения сущности (например, после вызова `service.update`),
              чтобы очистить её временные данные, но не трогать дочерние черновики
              (которые уже должны быть сохранены отдельно или ещё не сохранены).

        **Алгоритм:**
            1. Сохраняет старый статус сущности (до очистки).
            2. Удаляет все прямые черновики сущности по префиксу `{entity_type}:{entity_id}:`.
            3. Удаляет счётчик детей сущности (если был) – он пересчитается при следующем обращении.
            4. Пересчитывает новый статус сущности:
               - Собственных изменений больше нет → `has_own = False`.
               - Количество детей с не‑None статусом берётся из реестра (после удаления счётчик обнулён,
                 но дочерние черновики физически остаются – их статусы будут пересчитаны отдельно).
            5. Обновляет кэш и реестр (если статус изменился).
            6. Если старый статус был не `None`, а новый стал `None` (сущность перестала быть изменённой
               полностью), уменьшает счётчик родителя на 1 (уведомляет родителя, что этот потомок больше
               не является изменённым).
            7. Если статус изменился (любое изменение), распространяет это изменение вверх по дереву
               через `_propagate_status_up`, чтобы родители пересчитали свои статусы.

        **Важные отличия от `discard_entity_subtree`:**
            - `discard_entity_subtree` удаляет **все** черновики (и свои, и дочерние) – используется для полной отмены изменений строки.
            - `clear_entity_drafts` удаляет **только свои** черновики, оставляя детей нетронутыми – используется после сохранения, когда дети уже сохранены или должны остаться для дальнейшего редактирования.

        **Args:**
            entity_id: ID сущности, черновики которой нужно удалить (может быть временным отрицательным ID).

        **Returns:**
            None

        **Пример использования (в `_save_modified_rows`):**
            ```python
            updated = self.service.update(dto)
            self.source_model.update_row(row, updated)
            self.clear_entity_drafts(entity_id)   # очищаем черновики после сохранения
            self.clear_own_change(entity_id)      # снимаем флаг 'own' (необязательно, но для ясности)
        """

        # Определяем, были ли у сущности собственные изменения
        # status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
        # had_own = status in ('own', 'both')

        old_status = self._draft_registry.get_entity_status(self._entity_type, entity_id)
        had_non_none = old_status is not None

        # Удаляем черновики и статус

        # # После сохранения сбрасываем статус и черновики
        # self._draft_registry.discard_entity_subtree(self._entity_type, entity_id)

        # Удаляем прямые черновики этой сущности (но не дочерние)
        temp = f"{self._entity_type}:{entity_id}"
        # Удаляем все ключи, начинающиеся с "entity_type:entity_id:"
        # (включая возможные остаточные дочерние черновики – они уже применены)
        self._draft_registry.discard_by_prefix(f"{temp}:") # Удаляем ТОЛЬКО прямые черновики этой сущности (но не дочерние)

        # # Удаляем счётчик детей (если есть) – он пересчитается при следующем обращении
        # self._draft_registry.discard(f"__counter__:{temp}") # НЕ удаляем счётчик детей – он остаётся актуальным

        # Текущее количество активных потомков (счётчик не изменился)
        child_count = self._draft_registry.get_child_counter(self._entity_type, entity_id)
        new_status = self._status_from_flags(False, child_count > 0)

        self._set_cached_status(entity_id, new_status)
        if new_status is None:
            # Удаляем статус и счётчик
            self._draft_registry.delete_entity_status(self._entity_type, entity_id)
        else:
            self._draft_registry.set_entity_status(self._entity_type, entity_id, new_status)

        # Если статус изменился с не‑None на None, уменьшаем счётчик родителя
        if had_non_none and new_status is None:
            self._update_parent_child_counter(entity_id, -1)

        # # Если были собственные изменения – уведомляем родителя (уменьшаем его счётчик)
        # if had_own:
        #     self._update_parent_child_counter(entity_id, -1)

        # Если статус изменился, распространяем изменение вверх
        if old_status != new_status:
            self._propagate_status_up(entity_id)

    def _update_parent_child_counter(self, entity_id: int, delta: int) -> None:
        """
        Уведомляет родителя сущности entity_id об изменении количества активных потомков.

        **Отличие от mark_child_change:**
            - Этот метод безопасно игнорирует родителя, если родительский ID is None (нет родителя).
            - Он НЕ вызывает _update_child_change для отрицательных parent_id (т.е. для временных строк).
            - Используется в сценариях, где родитель гарантированно существует (например, при удалении строки).

        **Когда использовать:**
            - При пометке строки на удаление (_delete_selected_rows).
            - При снятии пометки на удаление (_unmark_deleted_row).
            - При очистке черновиков после сохранения (clear_entity_drafts).

        Args:
            entity_id: ID сущности, у которой изменился статус (например, фото).
            delta: +1 (появился изменённый потомок), -1 (исчез).
        """

        # Если есть родитель, увеличиваем счётчик его потомков
        parent_id = self._get_parent_id(entity_id)
        if parent_id is not None:
            self.mark_child_change(parent_id, delta)