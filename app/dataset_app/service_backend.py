# app/dataset_app/service_backend.py

"""
Источник наборов данных поверх сервисов приложения (``DataBackend`` + ``WritableBackend``).

* Чтение — ``get_page_filtered`` сервиса: условия, сортировка, окно, общее число строк —
  всё делает БД (``Capabilities()`` — умеет всё).
* Одна строка — ``get_by_id`` (нет записи → ``None``).
* Запись — ``create``/``update``/``delete`` сервиса; после записи строка перечитывается,
  чтобы вернуть то, что вычисляет сервис (ФИО пациента у приёма, тексты заметок).
* Сервис берётся функцией при КАЖДОЙ операции: после смены пути к БД
  (``reload_config``) источник работает с актуальным.

Условия ядра → фильтры сервиса:

| ``Op`` | фильтр сервиса |
|---|---|
| EQ, NE, LT, LE, GT, GE, IN | eq, ne, lt, le, gt, ge, in |
| CONTAINS | ilike (подстрока без учёта регистра) |
| IS_NULL True / False | is_null / is_not_null |
| STARTSWITH | нет у сервисов — ``ValueError`` (не подменяем «содержит» молча) |

Свои фильтры сервиса (например, нечёткий поиск ``fuzzy``) — параметром запроса
``service_filters`` (``DataSet.set_params(service_filters=[...])``).

Пример:
    >>> backend = ServiceBackend(get_patient_service, PatientDTO, fields)
    >>> backend.fetch(Query(order=(Order('last_name'),), limit=20)).total
    20
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Hashable, Mapping, Optional, Sequence, Type

from app.utils.dataset import Capabilities, Condition, FieldDef, Op, Page, Query

_OPS = {
    Op.EQ: 'eq', Op.NE: 'ne', Op.LT: 'lt', Op.LE: 'le', Op.GT: 'gt', Op.GE: 'ge',
    Op.IN: 'in', Op.CONTAINS: 'ilike',
}


def to_service_filter(condition: Condition) -> Dict[str, Any]:
    """
    Условие ядра → фильтр сервиса (``{'column', 'operator', 'value'}``).

    Args:
        condition: Условие.

    Returns:
        Фильтр.

    Raises:
        ValueError: Сравнение, которого у сервисов нет.

    Пример:
        >>> to_service_filter(Condition('patient_id', Op.EQ, 5))
        {'column': 'patient_id', 'operator': 'eq', 'value': 5}
    """
    if condition.op is Op.IS_NULL:
        operator = 'is_null' if condition.value else 'is_not_null'
        return {'column': condition.field, 'operator': operator, 'value': None}
    if condition.op is Op.EQ and condition.value is None:
        return {'column': condition.field, 'operator': 'is_null', 'value': None}
    if condition.op not in _OPS:
        raise ValueError(f"сервисы не умеют сравнение {condition.op.value!r} "
                         f"(поле {condition.field})")
    value = list(condition.value) if condition.op is Op.IN else condition.value
    return {'column': condition.field, 'operator': _OPS[condition.op], 'value': value}


class ServiceBackend:
    """
    Источник поверх сервиса приложения.

    Attributes:
        key_field: Поле-ключ.
        capabilities: Всё делает БД.

    Пример:
        >>> ServiceBackend(get_photo_service, PhotoDTO, []).key_field
        'id'
    """

    capabilities = Capabilities()

    def __init__(self, service_provider: Callable[[], Any], dto_class: Type[Any],
                 fields: Sequence[FieldDef], *, key_field: str = 'id',
                 relations: Optional[Sequence[str]] = None) -> None:
        """
        Args:
            service_provider: Функция, возвращающая сервис (``get_patient_service``).
            dto_class: Класс DTO сервиса.
            fields: Описания полей (``fields_from_config``).
            key_field: Поле-ключ.
            relations: Связи для жадной подгрузки при чтении страницы (``None`` — как
                решит сервис по ``field_configs``).

        Пример:
            >>> ServiceBackend(get_patient_service, PatientDTO, fields)
        """
        self._service_provider = service_provider
        self._dto_class = dto_class
        self._fields = list(fields)
        self._names = {f.name for f in self._fields}
        self.key_field = key_field
        self._relations = list(relations) if relations is not None else None

    @property
    def service(self) -> Any:
        """
        Актуальный сервис.

        Returns:
            Сервис.

        Пример:
            >>> backend.service
            <PatientService ...>
        """
        return self._service_provider()

    def fields(self) -> Sequence[FieldDef]:
        """
        Описания полей.

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> [f.name for f in backend.fields()][:2]
            ['id', 'last_name']
        """
        return list(self._fields)

    def _row(self, dto: Any) -> Dict[str, Any]:
        """
        DTO → строка (только описанные поля, если описание есть).

        Args:
            dto: DTO.

        Returns:
            Словарь.

        Пример:
            >>> backend._row(PatientDTO(id=1, last_name='П', first_name='И'))['last_name']
            'П'
        """
        data = dto.model_dump()
        if self._names:
            data = {k: v for k, v in data.items() if k in self._names}
        return data

    def fetch(self, query: Query) -> Page:
        """
        Страница строк через ``get_page_filtered``.

        Args:
            query: Запрос.

        Returns:
            ``Page`` с общим числом строк.

        Raises:
            ValueError: Условие, которого у сервисов нет.

        Пример:
            >>> backend.fetch(Query(limit=10)).rows[0]['id']
            1
        """
        filters = [to_service_filter(c) for c in query.conditions]
        filters.extend(query.params.get('service_filters') or ())
        order_by = [('-' if o.descending else '') + o.field for o in query.order]
        items, total = self.service.get_page_filtered(
            query.offset, query.limit, filters or None, order_by or None, self._relations)
        return Page([self._row(dto) for dto in items], total)

    def get(self, key: Hashable) -> Optional[Dict[str, Any]]:
        """
        Строка по ключу (нет записи → ``None``).

        Args:
            key: Ключ.

        Returns:
            Строка или ``None``.

        Пример:
            >>> backend.get(404) is None
            True
        """
        if key is None:
            return None
        try:
            dto = self.service.get_by_id(key)
        except Exception as exc:
            # APP2: «нет записи» у сервисов — EntityNotFoundError (наследник LookupError) или
            # свои PatientNotFoundError/AppointmentNotFoundError… (НЕ наследники LookupError)
            if isinstance(exc, LookupError) or 'NotFound' in type(exc).__name__:
                return None
            raise
        return None if dto is None else self._row(dto)

    def _dto_values(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Значения, которые принимает DTO (без ключа и неизвестных полей).

        Args:
            values: Значения строки.

        Returns:
            Словарь для DTO.

        Пример:
            >>> backend._dto_values({'id': None, 'last_name': 'П', 'x': 1})
            {'last_name': 'П'}
        """
        accepted = getattr(self._dto_class, 'model_fields', {})
        return {k: v for k, v in values.items() if k != self.key_field and (not accepted or k in accepted)}

    def insert(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Создаёт запись через сервис и возвращает её из БД.

        Args:
            values: Значения.

        Returns:
            Строка из БД.

        Raises:
            Exception: Ошибка проверки DTO/сервиса.

        Пример:
            >>> backend.insert({'last_name': 'Петров', 'first_name': 'Иван', 'birth_date': date(1990, 1, 1)})['id']
            21
        """
        service = self.service
        created = service.create(self._dto_class(**self._dto_values(values)))
        key = getattr(created, self.key_field, None)
        return self.get(key) or self._row(created)

    def update(self, key: Hashable, changes: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Меняет запись: текущий DTO + изменения → ``service.update``.

        Args:
            key: Ключ.
            changes: Изменения.

        Returns:
            Строка из БД после изменения.

        Пример:
            >>> backend.update(1, {'phone': '+7 900'})['phone']
            '+7 900'
        """
        service = self.service
        current = service.get_by_id(key)
        dto = current.model_copy(update=self._dto_values(changes))
        service.update(dto)
        return self.get(key) or self._row(dto)

    def delete(self, key: Hashable) -> None:
        """
        Удаляет запись через сервис (подчинённые — по правилам сервиса).

        Args:
            key: Ключ.

        Returns:
            None

        Пример:
            >>> backend.delete(21)
        """
        self.service.delete(key)
