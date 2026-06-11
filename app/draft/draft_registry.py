# app/draft/draft_registry.py
"""
Центральный реестр черновиков.

Хранит все несохранённые изменения (черновики), статусы сущностей и счётчики потомков.
Используется в `PaginatedListPage` для организации древовидных черновиков.

Основные возможности:
    - Хранение произвольных данных по плоским ключам.
    - Подписка на изменения (сигнал `draft_changed` или callback'и).
    - Специализированные методы для статусов сущностей и счётчиков потомков.
    - Операции с префиксами (удаление всех черновиков, начинающихся с определённого префикса).

**Форматы ключей:**

    - Обычный черновик:          "{entity_type}:{entity_id}:{subsystem}"  (например, "appointment:123:photos")
    - Статус сущности:           "__status__:{entity_type}:{entity_id}"
    - Счётчик потомков:          "__counter__:{entity_type}:{parent_id}"
    - Новая (не сохранённая) строка: "__new__:{entity_type}:{temp_id}"
    - Удалённая строка:          "__deleted__:{entity_type}:{entity_id}"
    - Служебный ключ балансировки счётчика: "__parent_counter_inc__:{entity_type}:{temp_id}"

**Примечания:**
    - Временные ID (temp_id) для новых строк отрицательные.
    - Счётчики потомков обновляются через вызовы `mark_child_change` в `DraftTreeMixin`.
    - Сигнал `draft_changed` испускается при добавлении или удалении черновика.
"""

from typing import (
    Dict, Any,
    Optional, Callable,
    Set, Type, List
)
from collections import defaultdict
# from weakref import ref

from app.utils.logger.logger import AppLogger

from PySide6.QtCore import QObject, Signal



class DraftRegistry(QObject):
    """
    Реестр черновиков.

    Хранит состояния в виде плоского словаря: key -> data.
    Поддерживает префиксные операции (отмена всех черновиков, начинающихся с префикса).

    Сигналы:
        draft_changed(key: str, has_draft: bool) – испускается при добавлении/удалении черновика.

    Атрибуты:
        _storage (Dict[str, Dict[str, Any]]): Словарь ключ -> данные.
        _listeners (Dict[str, Set[Callable]]): Словарь точных ключей -> множество callback'ов.
        _prefix_listeners (Dict[str, Set[Callable]]): Словарь префиксов -> множество callback'ов.
        logger (AppLogger): Логгер для записи событий.
    """

    draft_changed = Signal(str, bool)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, parent: QObject = None):
        """
        Инициализирует реестр.

        Args:
            parent: Родительский QObject (необязательно).
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='draft.DraftRegistry',
            enable_file_logging='user',
            use_name_in_filename=False,
        )

        self._storage: Dict[str, Dict[str, Any]] = {}
        self._listeners: Dict[str, Set[Callable[[str, bool], None]]] = defaultdict(set)
        self._prefix_listeners: Dict[str, Set[Callable[[str, bool], None]]] = defaultdict(set)

    # ==================================================================
    # Работа со статусами сущностей
    # ==================================================================

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def set_entity_status(
        self, entity_type: str, entity_id: int, status: Optional[str]
    ) -> None:
        """
        Устанавливает статус сущности.

        Допустимые статусы: None, 'own', 'child', 'both'.

        Args:
            entity_type: Тип сущности (например, "appointment").
            entity_id: ID сущности.
            status: Новый статус (None для удаления записи о статусе).
        """

        key = f"__status__:{entity_type}:{entity_id}"
        if status is None:
            self.discard(key)

        else:
            self.set(key, {"status": status})
        0==0

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_entity_status(
        self, 
        entity_type: str, 
        entity_id: int,
    ) -> Optional[str]:
        """
        Возвращает статус сущности или None.

        Args:
            entity_type: Тип сущности.
            entity_id: ID сущности.

        Returns:
            Статус ('own', 'child', 'both') или None.
        """

        data = self.get(f"__status__:{entity_type}:{entity_id}")
        return data["status"] if data else None

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def delete_entity_status(self, entity_type: str, entity_id: int) -> None:
        """
        Удаляет статус сущности (сбрасывает до None).

        Args:
            entity_type: Тип сущности.
            entity_id: ID сущности.
        """

        self.discard(f"__status__:{entity_type}:{entity_id}")

    # ==================================================================
    # Счётчики потомков (для оптимизации пересчёта статуса родителя)
    # ==================================================================

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def inc_child_counter(
        self, 
        parent_type: str, 
        parent_id: int, 
        delta: int = 1
    ) -> int:
        """
        Увеличивает счётчик ненулевых потомков для родителя.

        Args:
            entity_type: Тип родительской сущности.
            parent_id: ID родителя.
            delta: Изменение (обычно +1 или -1).

        Returns:
            Новое значение счётчика (неотрицательное).
        """

        key = f"__counter__:{parent_type}:{parent_id}"

        current = self.get(key)

        count = current.get("count", 0) if current else 0

        new_count = max(0, count + delta)

        if new_count == 0:
            self.discard(key)

        else:
            self.set(key, {"count": new_count})

        return new_count

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def dec_child_counter(self, parent_type: str, parent_id: int) -> int:
        """Уменьшает счётчик потомков на -1 (удобная обёртка)."""

        return self.inc_child_counter(parent_type, parent_id, -1)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_child_counter(
        self, 
        parent_type: str, 
        parent_id: int
    ) -> int:
        """
        Возвращает текущее значение счётчика потомков.

        Args:
            entity_type: Тип родительской сущности.
            parent_id: ID родителя.

        Returns:
            Количество активных потомков (с ненулевым статусом).
        """
                
        data = self.get(f"__counter__:{parent_type}:{parent_id}")
        return data["count"] if data else 0

    # ==================================================================
    # Управление черновиками и статусами по префиксу (для поддеревьев)
    # ==================================================================

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard_entity_subtree(self, entity_type: str, entity_id: int) -> None:
        """
        Удаляет черновики и статус ТОЛЬКО для указанной сущности (не рекурсивно).

        ВНИМАНИЕ: Этот метод НЕ удаляет статусы дочерних сущностей.
        Для полного рекурсивного удаления поддерева используйте
        `DraftTreeMixin.discard_entity_subtree`.

        Удаляются ключи вида:
            - "{entity_type}:{entity_id}:*"
            - "__status__:{entity_type}:{entity_id}"
            - "__counter__:{entity_type}:{entity_id}"
            - "__deleted__:{entity_type}:{entity_id}"
            - "__new__:{entity_type}:*" (для потомков)

        Args:
            entity_type: Тип сущности.
            entity_id: ID сущности.
        """
        prefix = f"{entity_type}:{entity_id}:"

        # Удаляем обычные черновики
        self.discard_subtree_by_prefix(prefix)
        # for key in list(self._storage.keys()):
        #     if key.startswith(prefix):
        #         discard(key)
                
        # Удаляем статус самой сущности
        self.delete_entity_status(entity_type, entity_id)

        # Удаляем счётчик потомков (если есть)
        self.discard(f"__counter__:{entity_type}:{entity_id}")

        # Удаляем метку удаления, если была
        self.discard(f"__deleted__:{entity_type}:{entity_id}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard_subtree_by_prefix(self, prefix: str) -> None:
        """Универсальный метод удаления по префиксу (любые ключи)."""
        # for key in list(self._storage.keys()):
        #     if key.startswith(prefix):
        #         self.discard(key)

        self.discard_by_prefix(prefix)

    # ----------------------------------------------------------------------
    # Основные операции с черновиками
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def set(self, key: str, data: Dict[str, Any]) -> None:
        """
        ССохраняет черновик для указанного ключа.

        Args:
            key: Уникальный ключ (например, "appointment:123:photos").
            data: Словарь с изменениями (структура зависит от компонента).
        """
        was_empty = key not in self._storage
        self._storage[key] = data

        if was_empty:
            self._notify_draft_changed(key, True)

        self.logger.debug(f"Черновик сохранён: {key}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает черновик для ключа или None.

        Args:
            key: Уникальный ключ.

        Returns:
            Словарь с изменениями или None.
        """

        return self._storage.get(key)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard(self, key: str) -> None:
        """
        Удаляет черновик для конкретного ключа.

        Args:
            key: Уникальный ключ.
        """

        if key in self._storage:
            del self._storage[key]

            self._notify_draft_changed(key, False)

            self.logger.debug(f"Черновик удалён: {key}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard_by_prefix(self, prefix: str) -> None:
        """
        Удаляет все черновики, чьи ключи начинаются с указанного префикса.

        Args:
            prefix: Префикс (например, "appointment:123:").
        """

        # сбор списка всех ключей, которые начинаются с переданного префикса, перед их удалением
        # Словарь self._storage изменяется во время итерации, если удалять элементы напрямую в цикле for key in self._storage:, это вызовет ошибку
        keys_to_remove = [key for key in self._storage if key.startswith(prefix)]

        if not keys_to_remove:
            return
        
        for key in keys_to_remove:
            # del self._storage[key]
            # self._notify_draft_changed(key, False)
        
            self.discard(key)

        self.logger.debug(f"Удалены черновики по префиксу: {prefix}, количество {len(keys_to_remove)}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def has(self, key: str) -> bool:
        """
        Проверяет, существует ли черновик для данного ключа.

        Args:
            key: Уникальный ключ.

        Returns:
            True, если черновик есть, иначе False.
        """

        return key in self._storage

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def has_prefix(self, prefix: str) -> bool:
        """
        Проверяет, существует ли хотя бы один черновик с указанным префиксом.

        Args:
            prefix: Префикс.

        Returns:
            True, если такие черновики есть, иначе False.
        """

        return any(key.startswith(prefix) for key in self._storage)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_keys_by_prefix(self, prefix: str) -> Set[str]:
        """
        Возвращает множество ключей, начинающихся с указанного префикса.

        Args:
            prefix: Префикс.

        Returns:
            Множество ключей.
        """

        return {key for key in self._storage if key.startswith(prefix)}

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_all_modified_prefixes(self) -> Set[str]:
        """
        Возвращает множество уникальных префиксов (корневых ключей) всех изменённых записей.

        Полезно для быстрой проверки любых изменений.

        Returns:
            Множество префиксов (часть ключа до последнего двоеточия).
        """
        prefixes = set()
        for key in self._storage:
            prefix = key.split(':')
            # Берём хотя бы первые два компонента (entity_type:entity_id)
            if len(prefix) >= 2:
                prefixes.add(f"{prefix[0]}:{prefix[1]}:")

        return prefixes

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def clear(self) -> None:
        """
        Удаляет все черновики из реестра.
        """
        keys = list(self._storage.keys())
        self._storage.clear()
        for key in keys:
            self._notify_draft_changed(key, False)

        self.logger.debug("Все черновики очищены")

    # ----------------------------------------------------------------------
    # Подписка на изменения
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def subscribe(self, key: str, callback: Callable[[str, bool], None]) -> None:
        """
        Подписывает callback на изменения черновика с точным ключом.

        Args:
            key: Ключ черновика.
            callback: Функция, принимающая (key, has_draft).
        """

        self._listeners[key].add(callback)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def subscribe_prefix(self, prefix: str, callback: Callable[[str, bool], None]) -> None:
        """
        Подписывает callback на изменения всех черновиков, ключи которых начинаются с prefix.

        Args:
            prefix: Префикс.
            callback: Функция, принимающая (key, has_draft).
        """

        self._prefix_listeners[prefix].add(callback)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def unsubscribe(self, key: str, callback: Callable[[str, bool], None]) -> None:
        """
        Отписывает callback от изменений черновика с точным ключом.

        Args:
            key: Ключ черновика.
            callback: Функция.
        """

        if key in self._listeners:
            self._listeners[key].discard(callback)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def unsubscribe_prefix(self, prefix: str, callback: Callable[[str, bool], None]) -> None:
        """
        Отписывает callback от изменений по префиксу.

        Args:
            prefix: Префикс.
            callback: Функция.
        """

        if prefix in self._prefix_listeners:
            self._prefix_listeners[prefix].discard(callback)

    # ----------------------------------------------------------------------
    # Применение изменений
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def apply_and_clear(self, key: str, applier: Callable[[Dict[str, Any]], None]) -> None:
        """
        Применяет изменения для ключа с помощью функции applier, затем удаляет черновик.

        Args:
            key: Ключ черновика.
            applier: Функция, принимающая data (словарь) и выполняющая сохранение в БД.

        Raises:
            Exception: Любое исключение из applier пробрасывается, черновик не удаляется.
        """

        data = self.get(key)
        if data is not None:
            try:
                applier(data)

            except Exception as e:
                self.logger.exception(f"Ошибка при применении черновика {key}: {e}")
                raise

            self.discard(key)
            self.logger.debug(f"Черновик {key} применён и удалён")

        else:
            self.logger.warning(f"Попытка применить несуществующий черновик {key}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def apply_by_prefix(self, prefix: str, applier: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Применяет все черновики с указанным префиксом, вызывая applier для каждого, затем удаляет их.

        Args:
            prefix: Префикс ключа (например, "appointment:123:").
            applier: Функция, принимающая (key, data) и выполняющая сохранение.
        """
        keys = self.get_keys_by_prefix(prefix)

        for key in keys:
            # data = self._storage[key]
            data = self.get(key)
            if data is not None:
                try:
                    applier(key, data)

                except Exception as e:
                    self.logger.exception(f"Ошибка при применении черновика {key}: {e}")
                    raise

                self.discard(key)

        self.logger.debug(f"Применены черновики по префиксу {prefix}, количество {len(keys)}")

    # ----------------------------------------------------------------------
    # Внутренние уведомления
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _notify_draft_changed(self, key: str, has_draft: bool) -> None:
        """
        Уведомляет всех подписчиков об изменении статуса черновика.

        :param key: Ключ.
        :param has_draft: True – черновик добавлен, False – удалён.
        """
        # Сигнал Qt
        self.draft_changed.emit(key, has_draft)

        # Точные подписчики
        for cb in self._listeners.get(key, []):
            try:
                cb(key, has_draft)
            except Exception as e:
                self.logger.exception(f"Ошибка в callback для ключа {key}: {e}")

        # Подписчики по префиксу
        for prefix, cbs in self._prefix_listeners.items():
            if key.startswith(prefix):
                for cb in cbs:
                    try:
                        cb(key, has_draft)
                    except Exception as e:
                        self.logger.exception(f"Ошибка в callback для префикса {prefix}: {e}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def apply_subtree(self, prefix: str, applier: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Применяет все черновики, ключи которых начинаются с prefix, с помощью функции applier, затем удаляет их. Синоним apply_by_prefix.

        Args:
            prefix: Префикс ключа (например, "appointment:123:").
            applier: Функция, принимающая (key, data) и выполняющая сохранение в БД.
        """
        
        self.apply_by_prefix(prefix, applier)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard_subtree(self, prefix: str) -> None:
        """Удаляет все черновики, ключи которых начинаются с prefix."""
        self.discard_by_prefix(prefix)

    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def save_draft_dto(
        self,
        dto: Any,
        entity_type: str,
        entity_id: int,
        field_configs: Dict[str, Dict[str, Any]],
        exclude_fields: Optional[set] = None
    ) -> None:
        """
        Сохраняет сериализованную копию DTO в реестр как черновик.

        **Динамическое исключение полей:**
            Поля, помеченные в `field_configs` как `virtual=True` без `is_note`,
            а также поля с `compute` без `is_note`, автоматически исключаются из сохранения.
            Это позволяет сохранять только те данные, которые реально изменяются пользователем.

        **Параметры:**
            dto (Any): Экземпляр DTO (Pydantic модель).
            entity_type (str): Тип сущности (например, "appointment").
            entity_id (int): ID сущности (положительный для существующих, отрицательный для новых).
            field_configs (Dict[str, Dict[str, Any]]): Конфигурация полей (из модуля `field_configs`).
            exclude_fields (Optional[set]): Дополнительный набор имён полей для исключения.

        **Возвращает:**
            None

        **Пример:**
            >>> registry.save_draft_dto(appointment_dto, "appointment", 123, APPOINTMENT_CONFIG)
        """
        if exclude_fields is None:
            exclude_fields = set()

        # Динамически собираем поля для исключения
        for field_name, config in field_configs.items():
            if config.get('virtual', False) and not config.get('is_note'):
                exclude_fields.add(field_name)
            if config.get('compute') and not config.get('is_note'):
                exclude_fields.add(field_name)

        data = dto.model_dump(exclude=exclude_fields, exclude_none=False)
        key = f"{entity_type}:{entity_id}:draft"
        self.set(key, {"dto": data})

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def load_draft_dto(
        self,
        entity_type: str,
        entity_id: int,
        dto_class: Type
    ) -> Optional[Any]:
        """
        Загружает черновик DTO из реестра.

        **Параметры:**
            entity_type (str): Тип сущности.
            entity_id (int): ID сущности.
            dto_class (Type): Класс DTO (Pydantic модель) для восстановления объекта.

        **Возвращает:**
            Optional[Any]: Экземпляр DTO, если черновик существует, иначе None.

        **Пример:**
            >>> restored = registry.load_draft_dto("appointment", 123, AppointmentDTO)
        """
        key = f"{entity_type}:{entity_id}:draft"
        data = self.get(key)
        if data:
            return dto_class(**data["dto"])
        return None

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def clear_draft_dto(
        self,
        entity_type: str,
        entity_id: int
    ) -> None:
        """
        Удаляет черновик DTO из реестра.

        **Параметры:**
            entity_type (str): Тип сущности.
            entity_id (int): ID сущности.

        **Возвращает:**
            None

        **Пример:**
            >>> registry.clear_draft_dto("appointment", 123)
        """
        key = f"{entity_type}:{entity_id}:draft"
        self.discard(key)

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def get_new_dtos(self, entity_type: str, dto_class: Type) -> List[Any]:
        """
        Возвращает список DTO всех новых строк для указанного типа сущности.

        **Назначение:**
            Извлекает из реестра все ключи вида `__new__:{entity_type}:{temp_id}`
            и восстанавливает DTO из сохранённых словарей.

        **Параметры:**
            entity_type (str): Тип сущности (например, "appointment").
            dto_class (Type): Класс DTO (Pydantic модель) для восстановления объектов.

        **Возвращает:**
            List[Any]: Список DTO новых строк (может быть пустым).

        **Пример:**
            >>> new_dtos = registry.get_new_dtos("appointment", AppointmentDTO)
            >>> for dto in new_dtos:
            ...     print(dto.id, dto.date)  # id отрицательные
        """
        result = []
        prefix = f"__new__:{entity_type}:"
        for key in self.get_keys_by_prefix(prefix):
            data = self.get(key)
            if data and 'dto' in data:
                dto_dict = data['dto']
                # Если уже экземпляр DTO (например, при прямом сохранении), используем его
                if hasattr(dto_dict, 'id') and hasattr(dto_dict, 'model_dump'):
                    result.append(dto_dict)
                else:
                    # Восстанавливаем из словаря
                    result.append(dto_class(**dto_dict))
        return result

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def merge_new_dtos(
            self,
            entity_type: str,
            page_data: List[Any],
            dto_class: Type,
            sort_by_id: bool = True
    ) -> List[Any]:
        """
        Объединяет список DTO, загруженных из БД, со списком новых строк из реестра.

        **Назначение:**
            Добавляет в конец `page_data` все новые строки (из `__new__`), которые
            ещё не присутствуют в `page_data` (по id). Предотвращает дублирование.

        **Параметры:**
            entity_type (str): Тип сущности.
            page_data (List[Any]): Список DTO, загруженных из БД (или из пагинации).
            dto_class (Type): Класс DTO для восстановления.
            sort_by_id (bool): Если True, результат сортируется по id (отрицательные
                               идут первыми, затем положительные). По умолчанию True.

        **Возвращает:**
            List[Any]: Объединённый список DTO.

        **Пример:**
            >>> merged = registry.merge_new_dtos("appointment", db_page, AppointmentDTO)
            >>> # merged содержит сначала новые строки (id < 0), затем загруженные из БД
        """
        new_dtos = self.get_new_dtos(entity_type, dto_class)
        # Исключаем дубликаты: если в page_data уже есть DTO с тем же id
        existing_ids = {dto.id for dto in page_data if dto.id is not None}
        filtered_new = [dto for dto in new_dtos if dto.id not in existing_ids]
        merged = page_data + filtered_new
        if sort_by_id:
            merged.sort(key=lambda x: x.id)
        return merged

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def update_foreign_key_in_new_dtos(
        self,
        old_parent_id: int,
        new_parent_id: int,
        foreign_key_field: str
    ) -> int:
        """
        Обновляет значение внешнего ключа во всех новых строках (__new__),
        у которых поле foreign_key_field равно old_parent_id.

        Args:
            old_parent_id: Старый (временный) ID родителя.
            new_parent_id: Новый (реальный) ID родителя после сохранения.
            foreign_key_field: Имя поля в DTO, содержащего внешний ключ на родителя.
                Например, 'appointment_id' для фото.

        Returns:
            int: Количество обновлённых записей.
        """
        updated_count = 0
        prefix = "__new__:"
        for key in list(self.get_keys_by_prefix(prefix)):
            data = self.get(key)
            if not data or 'dto' not in data:
                continue

            dto = data['dto']
            if (
                hasattr(dto, foreign_key_field)
            ) and (
                getattr(dto, foreign_key_field) == old_parent_id
            ):
                setattr(dto, foreign_key_field, new_parent_id)
                self.set(key, {'dto': dto})
                updated_count += 1
                self.logger.debug(
                    f"Обновлён {foreign_key_field} в {key} с {old_parent_id} на {new_parent_id}"
                )
        return updated_count