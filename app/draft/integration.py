# app/draft/integration.py

"""
Связка переносимого пакета черновиков (``app.utils.drafts``) с приложением.

Здесь — всё, что знает о приложении (пакет черновиков не знает):
    * ``build_app_schema()`` — дерево таблиц приложения: пациент → приём → фото;
    * ``ServiceAdapter`` — сохранение через сервисы приложения в ОДНОЙ сессии SQLAlchemy
      (одна транзакция на все таблицы — D2, app/draft/IMPLEMENTATION.md);
    * ``make_parent_resolver()`` — определитель родителя записи без черновика через сервис.

Пример:
    >>> from app.dependencies import (get_patient_service, get_appointment_service,
    ...                               get_photo_service)
    >>> schema = build_app_schema()
    >>> adapter = ServiceAdapter({
    ...     'patient': (get_patient_service, PatientDTO),
    ...     'appointment': (get_appointment_service, AppointmentDTO),
    ...     'photo': (get_photo_service, PhotoDTO),
    ... })
    >>> store = DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter))
"""

from __future__ import annotations

import logging
from typing import Any, Callable, ContextManager, Dict, Hashable, Mapping, Optional, Tuple, Type

from app.utils.drafts import EntityType, TreeSchema

_log = logging.getLogger(__name__)

# Тип записи -> (функция, возвращающая сервис; класс DTO)
ServiceSpec = Tuple[Callable[[], Any], Type[Any]]


def build_app_schema() -> TreeSchema:
    """
    Дерево таблиц приложения.

    Заметки (``appointments_notes``) — поля пациента/приёма (``is_note``), а не узлы
    дерева: их сохраняют сервисы пациента и приёма вместе с записью.

    Returns:
        Схема пациент → приём → фото.

    Пример:
        >>> build_app_schema().depth('photo')
        2
    """
    return TreeSchema([
        EntityType('patient', label='Пациент'),
        EntityType('appointment', parent='patient', parent_field='patient_id', label='Приём'),
        EntityType('photo', parent='appointment', parent_field='appointment_id', label='Фото'),
    ])


class ServiceAdapter:
    """
    ``PersistenceAdapter`` поверх сервисов приложения.

    * ``transaction()`` — сессия первого сервиса (``_session_scope``): коммит при
      выходе без ошибки, откат при исключении; ЭТА ЖЕ сессия передаётся всем сервисам.
    * ``create`` — DTO из данных черновика (без временного ``id``) → ``service.create``;
      id появляется сразу (сервис делает ``flush``) — дети ссылаются на него в той же
      транзакции.
    * ``update`` — текущий DTO из БД + изменения → ``service.update`` (сервисы
      принимают DTO целиком; виртуальные поля-заметки обрабатывает сервис).
    * ``delete`` — ``service.delete`` (потомков в БД удаляет сервис/каскад БД).

    Сервисы берутся функциями при КАЖДОЙ операции: после смены пути к БД
    (``reload_config``) адаптер работает с актуальными.

    Пример:
        >>> ServiceAdapter({'patient': (get_patient_service, PatientDTO)}).entities()
        ['patient']
    """

    def __init__(self, specs: Mapping[str, ServiceSpec]) -> None:
        """
        Args:
            specs: Тип записи → (функция-поставщик сервиса, класс DTO).

        Raises:
            ValueError: Пустой набор.

        Пример:
            >>> ServiceAdapter({'photo': (get_photo_service, PhotoDTO)})
        """
        if not specs:
            raise ValueError("ServiceAdapter: не задано ни одного сервиса")
        self._specs: Dict[str, ServiceSpec] = dict(specs)

    def entities(self) -> list:
        """
        Типы записей, которые умеет сохранять адаптер.

        Returns:
            Список имён типов.

        Пример:
            >>> adapter.entities()
            ['patient', 'appointment', 'photo']
        """
        return list(self._specs)

    def service(self, entity: str) -> Any:
        """
        Сервис типа записи.

        Args:
            entity: Тип.

        Returns:
            Сервис приложения.

        Raises:
            KeyError: Тип не подключён.

        Пример:
            >>> adapter.service('photo')
        """
        try:
            provider, _ = self._specs[entity]
        except KeyError:
            raise KeyError(f"ServiceAdapter: нет сервиса для '{entity}'") from None
        return provider()

    def dto_class(self, entity: str) -> Type[Any]:
        """
        Класс DTO типа записи.

        Args:
            entity: Тип.

        Returns:
            Класс DTO.

        Пример:
            >>> adapter.dto_class('photo').__name__
            'PhotoDTO'
        """
        return self._specs[entity][1]

    def transaction(self) -> ContextManager[Any]:
        """
        Одна сессия SQLAlchemy на всё сохранение.

        Returns:
            Контекстный менеджер, отдающий сессию.

        Пример:
            >>> with adapter.transaction() as session: ...
        """
        first = next(iter(self._specs))
        return self.service(first)._session_scope(None)

    def create(self, entity: str, data: Mapping[str, Any], tx: Any) -> Hashable:
        """
        Создаёт запись через сервис.

        Args:
            entity: Тип.
            data: Поля из черновика (внешний ключ уже настоящий).
            tx: Сессия.

        Returns:
            Id созданной записи.

        Пример:
            >>> adapter.create('photo', {'appointment_id': 55, 'file_path': '/tmp/a.jpg'}, session)
            301
        """
        values = {k: v for k, v in data.items() if k != 'id'}
        dto = self.dto_class(entity)(**values)
        created = self.service(entity).create(dto, session=tx)
        return getattr(created, 'id', None)

    def update(self, entity: str, entity_id: Hashable, changes: Mapping[str, Any], tx: Any) -> None:
        """
        Изменяет запись: текущий DTO + изменения.

        Args:
            entity: Тип.
            entity_id: Id.
            changes: Изменённые поля.
            tx: Сессия.

        Returns:
            None

        Пример:
            >>> adapter.update('appointment', 12, {'cost': 500}, session)
        """
        service = self.service(entity)
        current = service.get_by_id(entity_id, session=tx)
        dto = current.model_copy(update={k: v for k, v in changes.items() if k != 'id'})
        service.update(dto, session=tx)

    def delete(self, entity: str, entity_id: Hashable, tx: Any) -> None:
        """
        Удаляет запись через сервис.

        Args:
            entity: Тип.
            entity_id: Id.
            tx: Сессия.

        Returns:
            None

        Пример:
            >>> adapter.delete('photo', 301, session)
        """
        self.service(entity).delete(entity_id, session=tx)


def make_parent_resolver(
    schema: TreeSchema,
    adapter: ServiceAdapter,
) -> Callable[[str, Hashable], Optional[Hashable]]:
    """
    Определитель родителя записи без черновика: читает запись из БД и берёт поле
    внешнего ключа из схемы.

    Временные id новых записей (отрицательные) в БД не ищутся. Ошибка чтения — ``None``
    (хранилище в этом случае просто не поднимет значок выше).

    Args:
        schema: Схема дерева.
        adapter: Адаптер с сервисами.

    Returns:
        Функция ``(тип, id) -> id родителя | None``.

    Пример:
        >>> resolve = make_parent_resolver(schema, adapter)
        >>> resolve('appointment', 12)
        1
    """

    def resolve(entity: str, entity_id: Hashable) -> Optional[Hashable]:
        """
        Родитель записи из БД.

        Args:
            entity: Тип.
            entity_id: Id.

        Returns:
            Id родителя или ``None``.

        Пример:
            >>> resolve('photo', 301)
            55
        """
        field = schema.parent_field(entity)
        if field is None or (isinstance(entity_id, int) and entity_id < 0):
            return None
        try:
            dto = adapter.service(entity).get_by_id(entity_id)
        except Exception:
            _log.exception("Не удалось определить родителя %s:%s", entity, entity_id)
            return None
        return getattr(dto, field, None)

    return resolve
