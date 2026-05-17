# app/draft/draft_registry.py
"""
Центральный Реестр черновиков. Использует плоские ключи для хранения данных.

**Форматы ключей:**
    - Обычные черновики: "{entity_type}:{entity_id}:{subsystem}" (например, "appointment:123:photos")
    - Статусы сущностей: "__status__:{entity_type}:{entity_id}"
    - Счётчики потомков: "__counter__:{entity_type}:{parent_id}"
    - Новые (не сохранённые) строки: "__new__:{entity_type}:{temp_id}"
    - Удалённые строки: "__deleted__:{entity_type}:{entity_id}"

**Примечание:** Отрицательные ID (temp_id) допустимы для новых строк и не должны влиять на логику,
    кроме случаев, когда нужна проверка parent_id > 0.
"""

from typing import (
    Dict, Any, 
    Optional, Callable, 
    Set
)
from collections import defaultdict
from weakref import ref

from app.utils.logger.logger import AppLogger

from PySide6.QtCore import QObject, Signal



class DraftRegistry(QObject):
    """
    Реестр черновиков.

    Хранит состояния в виде плоского словаря: key -> data.
    Поддерживает префиксные операции (отмена всех черновиков, начинающихся с префикса).

    Сигналы:
        draft_changed(key: str, has_draft: bool) – испускается при добавлении/удалении черновика.
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

        :param parent: Родительский QObject (необязательно).
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

    def set_entity_status(
        self, entity_type: str, entity_id: int, status: Optional[str]
    ) -> None:
        """
        Устанавливает статус сущности. Допустимые статусы:
        None, 'own', 'child', 'both'.
        """
        key = f"__status__:{entity_type}:{entity_id}"
        if status is None:
            self.discard(key)
        else:
            self.set(key, {"status": status})

    def get_entity_status(
        self, entity_type: str, entity_id: int
    ) -> Optional[str]:
        """Возвращает статус сущности или None."""
        data = self.get(f"__status__:{entity_type}:{entity_id}")
        return data["status"] if data else None

    def delete_entity_status(self, entity_type: str, entity_id: int) -> None:
        """Удаляет статус сущности (сбрасывает до None)."""
        self.discard(f"__status__:{entity_type}:{entity_id}")

    # ==================================================================
    # Счётчики потомков (для оптимизации пересчёта статуса родителя)
    # ==================================================================

    def inc_child_counter(
        self, parent_type: str, parent_id: int, delta: int = 1
    ) -> int:
        """
        Увеличивает счётчик ненулевых потомков для родителя.
        Возвращает новое значение счётчика.
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

    def dec_child_counter(self, parent_type: str, parent_id: int) -> int:
        """Уменьшает счётчик потомков на 1 (удобная обёртка)."""
        return self.inc_child_counter(parent_type, parent_id, -1)

    def get_child_counter(
        self, parent_type: str, parent_id: int
    ) -> int:
        """Возвращает текущее значение счётчика потомков."""
        data = self.get(f"__counter__:{parent_type}:{parent_id}")
        return data["count"] if data else 0

    # ==================================================================
    # Управление черновиками и статусами по префиксу (для поддеревьев)
    # ==================================================================

    def discard_entity_subtree(self, entity_type: str, entity_id: int) -> None:
        """
        Удаляет все черновики и статусы, связанные с сущностью и её потомками.
        Ключи вида "entity_type:entity_id:*", "__status__:entity_type:entity_id",
        "__counter__:entity_type:entity_id", "__deleted__:entity_type:entity_id",
        "__new__:entity_type:*".
        """
        prefix = f"{entity_type}:{entity_id}:"
        # Удаляем обычные черновики
        for key in list(self._storage.keys()):
            if key.startswith(prefix):
                self.discard(key)
        # Удаляем статус самой сущности
        self.delete_entity_status(entity_type, entity_id)
        # Удаляем счётчик потомков (если есть)
        self.discard(f"__counter__:{entity_type}:{entity_id}")
        # Удаляем метку удаления, если была
        self.discard(f"__deleted__:{entity_type}:{entity_id}")

    def discard_subtree_by_prefix(self, prefix: str) -> None:
        """Универсальный метод удаления по префиксу (любые ключи)."""
        for key in list(self._storage.keys()):
            if key.startswith(prefix):
                self.discard(key)

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
        Сохраняет черновик для указанного ключа.

        :param key: Уникальный ключ (например, "appointment:123:photos").
        :param data: Словарь с изменениями (структура зависит от компонента).
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

        :param key: Уникальный ключ.
        :return: Словарь с изменениями или None.
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

        :param key: Уникальный ключ.
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

        :param prefix: Префикс для поиска (например, "appointment:123:").
        """
        keys_to_remove = [key for key in self._storage if key.startswith(prefix)]

        if not keys_to_remove:
            return
        
        for key in keys_to_remove:
            del self._storage[key]
            self._notify_draft_changed(key, False)

        self.logger.debug(f"Удалены черновики по префиксу: {prefix}, количество {len(keys_to_remove)}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def has(self, key: str) -> bool:
        """
        Проверяет, существует ли черновик для данного ключа.

        :param key: Уникальный ключ.
        :return: True, если черновик есть, иначе False.
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

        :param prefix: Префикс.
        :return: True, если такие черновики есть, иначе False.
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

        :param prefix: Префикс.
        :return: Множество ключей.
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

        :return: Множество префиксов (часть ключа до последнего двоеточия).
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

        :param key: Ключ черновика.
        :param callback: Функция, принимающая (key, has_draft).
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

        :param prefix: Префикс.
        :param callback: Функция, принимающая (key, has_draft).
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

        :param key: Ключ черновика.
        :param callback: Функция.
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

        :param prefix: Префикс.
        :param callback: Функция.
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

        :param key: Ключ черновика.
        :param applier: Функция, принимающая data (словарь) и выполняющая сохранение в БД.
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
        Применяет все черновики с указанным префиксом, вызывая applier для каждого,
        затем удаляет их.

        :param prefix: Префикс.
        :param applier: Функция, принимающая (key, data) и выполняющая сохранение.
        """
        keys = self.get_keys_by_prefix(prefix)

        for key in keys:
            data = self._storage[key]
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
        Применяет все черновики, ключи которых начинаются с prefix, с помощью функции applier,
        затем удаляет их.

        Args:
            prefix: Префикс ключа (например, "appointment:123:").
            applier: Функция, принимающая (key, data) и выполняющая сохранение в БД.
        """
        
        keys = self.get_keys_by_prefix(prefix)
        for key in keys:
            data = self.get(key)
            if data is not None:
                try:
                    applier(key, data)
                except Exception as e:
                    self.logger.exception(f"Ошибка при применении черновика {key}: {e}")
                    raise
                self.discard(key)
        self.logger.debug(f"Применены черновики по префиксу {prefix}, количество {len(keys)}")

    @AppLogger.get_instance(
        name='DraftRegistry',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def discard_subtree(self, prefix: str) -> None:
        """Удаляет все черновики, ключи которых начинаются с prefix."""
        self.discard_by_prefix(prefix)