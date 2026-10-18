# app/utils/drafts/schema.py

"""
Описание дерева сущностей: у каждого типа — тип родителя и поле внешнего ключа.

Дерево задаётся данными, а не кодом страниц: новый тип таблицы или новый уровень
вложенности — одна строка ``schema.add(...)`` (требование 1, IMPLEMENTATION.md).

Пример:
    >>> schema = TreeSchema([
    ...     EntityType('patient', label='Пациент'),
    ...     EntityType('appointment', parent='patient', parent_field='patient_id'),
    ...     EntityType('photo', parent='appointment', parent_field='appointment_id'),
    ... ])
    >>> schema.depth('photo'), schema.parent_type('photo')
    (2, 'appointment')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from ._model import SchemaError


# Что делать с записями, которые ссылаются на удаляемую
ON_DELETE = ('restrict', 'set_null', 'cascade')


@dataclass(frozen=True)
class Reference:
    """
    Ссылка записи на запись другого типа, НЕ владение (2026-10-18): приём → врач,
    приём → общий шаблон текста. В отличие от родителя (дерево черновиков), ссылка не
    делает запись потомком: удаление цели не удаляет ссылающихся само по себе.

    Attributes:
        field: Поле записи со ссылкой (внешний ключ).
        entity: Тип записи, на которую ссылаются.
        on_delete: Если цель удаляют, а на неё ещё ссылаются записи, которые НЕ удаляются:
            ``'restrict'`` — отказ (по умолчанию), ``'set_null'`` — ссылка обнуляется,
            ``'cascade'`` — ссылающиеся удаляются тоже.
        collect: «Переиспользуемые данные»: цель удаляется, когда на неё больше никто не
            ссылается (после удаления ссылающейся записи), — и так рекурсивно вглубь.

    Пример:
        >>> Reference('doctor_id', 'doctor').on_delete
        'restrict'
    """

    field: str
    entity: str
    on_delete: str = 'restrict'
    collect: bool = False

    def __post_init__(self) -> None:
        """
        Проверка правила удаления.

        Returns:
            None

        Raises:
            SchemaError: Неизвестное правило.

        Пример:
            >>> Reference('a_id', 'a', on_delete='drop')
            Traceback (most recent call last):
            SchemaError: ссылка a_id: правило удаления 'drop' — допустимо restrict, set_null, cascade
        """
        if self.on_delete not in ON_DELETE:
            raise SchemaError(f"ссылка {self.field}: правило удаления {self.on_delete!r} — "
                              f"допустимо {', '.join(ON_DELETE)}")


@dataclass(frozen=True)
class EntityType:
    """
    Тип сущности (таблица) в дереве.

    Attributes:
        name: Уникальное имя типа (как в ключах черновиков, например ``'appointment'``).
        parent: Имя типа родителя; ``None`` — корневой тип.
        parent_field: Поле записи со ссылкой на родителя (внешний ключ). Обязательно,
            если задан ``parent``: при сохранении туда подставляется настоящий id
            только что созданного родителя.
        label: Человекочитаемое название (для сообщений и диалогов подтверждения).
        parent_required: Новую запись нельзя создать без родителя (внешний ключ
            NOT NULL). ``False`` — ссылка на родителя необязательна.
        references: Ссылки на записи других типов (не владение) — ``Reference``.

    Пример:
        >>> EntityType('photo', parent='appointment', parent_field='appointment_id').is_root
        False
    """

    name: str
    parent: Optional[str] = None
    parent_field: Optional[str] = None
    label: Optional[str] = None
    parent_required: bool = True
    references: Tuple[Reference, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """
        Ссылки — кортежем (описание неизменяемо).

        Returns:
            None

        Пример:
            >>> EntityType('a', references=[Reference('b_id', 'b')]).references
            (Reference(field='b_id', entity='b', on_delete='restrict', collect=False),)
        """
        object.__setattr__(self, 'references', tuple(self.references))

    @property
    def is_root(self) -> bool:
        """
        Корневой ли тип (без родителя).

        Returns:
            ``True`` для корня.

        Пример:
            >>> EntityType('patient').is_root
            True
        """
        return self.parent is None

    @property
    def title(self) -> str:
        """
        Название для сообщений: ``label`` или имя.

        Returns:
            Строка.

        Пример:
            >>> EntityType('photo', label='Фото').title
            'Фото'
        """
        return self.label or self.name


class TreeSchema:
    """
    Набор типов сущностей, образующих лес (у типа не больше одного родителя).

    Типы можно добавлять в любом порядке и во время работы; целостность (родитель
    существует, нет циклов, есть поле внешнего ключа) проверяется ``validate()`` —
    его вызывает хранилище перед использованием и при каждом ``add``.

    Ограничение: у типа один тип-родитель (дерево). Несколько родителей (например,
    заметка, привязанная и к пациенту, и к приёму) — несколько типов
    (``patient_note``, ``appointment_note``) или будущее расширение (IMPLEMENTATION.md §6).

    Пример:
        >>> s = TreeSchema().add(EntityType('a')).add(EntityType('b', 'a', 'a_id'))
        >>> s.children_types('a')
        ['b']
    """

    def __init__(self, types: Iterable[EntityType] = ()) -> None:
        """
        Создаёт схему из набора типов.

        Args:
            types: Типы сущностей.

        Raises:
            SchemaError: Описание неверное (см. ``validate``).

        Пример:
            >>> TreeSchema([EntityType('patient')]).names()
            ['patient']
        """
        self._types: Dict[str, EntityType] = {}
        for entity_type in types:
            self._put(entity_type)
        self.validate()

    def _put(self, entity_type: EntityType) -> None:
        """
        Добавляет тип без проверки целостности.

        Args:
            entity_type: Тип.

        Raises:
            SchemaError: Тип с таким именем уже есть.

        Пример:
            >>> TreeSchema()._put(EntityType('x'))
        """
        if entity_type.name in self._types:
            raise SchemaError(f"тип '{entity_type.name}' уже описан")
        self._types[entity_type.name] = entity_type

    def add(self, entity_type: EntityType) -> 'TreeSchema':
        """
        Добавляет тип и проверяет схему (при ошибке тип не добавляется).

        Args:
            entity_type: Тип.

        Returns:
            Эта же схема (для цепочки вызовов).

        Raises:
            SchemaError: Дубликат, неизвестный родитель, цикл, нет ``parent_field``.

        Пример:
            >>> TreeSchema().add(EntityType('patient')).names()
            ['patient']
        """
        self._put(entity_type)
        try:
            self.validate()
        except SchemaError:
            del self._types[entity_type.name]
            raise
        return self

    def validate(self) -> None:
        """
        Проверяет целостность: родители описаны, у дочерних есть ``parent_field``,
        нет циклов.

        Returns:
            None

        Raises:
            SchemaError: Описание неверное.

        Пример:
            >>> TreeSchema([EntityType('b', parent='a', parent_field='a_id')])
            Traceback (most recent call last):
            SchemaError: тип 'b': родитель 'a' не описан
        """
        for entity_type in self._types.values():
            if entity_type.parent is None:
                continue
            if entity_type.parent not in self._types:
                raise SchemaError(f"тип '{entity_type.name}': родитель '{entity_type.parent}' не описан")
            if not entity_type.parent_field:
                raise SchemaError(f"тип '{entity_type.name}': не задано поле внешнего ключа parent_field")
        for entity_type in self._types.values():
            for ref in entity_type.references:
                if ref.entity not in self._types:
                    raise SchemaError(f"тип '{entity_type.name}': ссылка {ref.field} на "
                                      f"неописанный тип '{ref.entity}'")
                if ref.field == entity_type.parent_field:
                    raise SchemaError(f"тип '{entity_type.name}': поле {ref.field} — уже связь "
                                      "с родителем, ссылкой его описывать не нужно")
        for name in self._types:
            seen = set()
            current: Optional[str] = name
            while current is not None:
                if current in seen:
                    raise SchemaError(f"цикл в описании дерева через тип '{name}'")
                seen.add(current)
                current = self._types[current].parent

    def get(self, name: str) -> EntityType:
        """
        Тип по имени.

        Args:
            name: Имя типа.

        Returns:
            Описание типа.

        Raises:
            SchemaError: Тип не описан.

        Пример:
            >>> TreeSchema([EntityType('patient')]).get('patient').is_root
            True
        """
        try:
            return self._types[name]
        except KeyError:
            raise SchemaError(f"неизвестный тип сущности: '{name}'") from None

    def __contains__(self, name: object) -> bool:
        """
        Описан ли тип.

        Args:
            name: Имя типа.

        Returns:
            ``True``, если описан.

        Пример:
            >>> 'patient' in TreeSchema([EntityType('patient')])
            True
        """
        return name in self._types

    def __iter__(self) -> Iterator[EntityType]:
        """
        Перебор типов в порядке добавления.

        Returns:
            Итератор типов.

        Пример:
            >>> [t.name for t in TreeSchema([EntityType('patient')])]
            ['patient']
        """
        return iter(list(self._types.values()))

    def names(self) -> List[str]:
        """
        Имена типов в порядке добавления.

        Returns:
            Список имён.

        Пример:
            >>> TreeSchema([EntityType('patient')]).names()
            ['patient']
        """
        return list(self._types)

    def parent_type(self, name: str) -> Optional[str]:
        """
        Имя типа родителя.

        Args:
            name: Имя типа.

        Returns:
            Имя родителя или ``None`` у корня.

        Пример:
            >>> TreeSchema([EntityType('a'), EntityType('b', 'a', 'a_id')]).parent_type('b')
            'a'
        """
        return self.get(name).parent

    def references(self, name: str) -> Tuple[Reference, ...]:
        """
        Ссылки типа на записи других типов.

        Args:
            name: Тип.

        Returns:
            Кортеж ``Reference``.

        Пример:
            >>> schema.references('appointment')
            (Reference(field='doctor_id', entity='doctor', on_delete='restrict', collect=False),)
        """
        return self.get(name).references

    def referrers(self, name: str) -> List[Tuple[str, Reference]]:
        """
        Кто ссылается на записи типа: ``(тип ссылающегося, ссылка)``.

        Args:
            name: Тип цели.

        Returns:
            Список пар.

        Пример:
            >>> schema.referrers('doctor')
            [('appointment', Reference(field='doctor_id', entity='doctor', ...))]
        """
        return [(t.name, ref) for t in self._types.values() for ref in t.references if ref.entity == name]

    def parent_field(self, name: str) -> Optional[str]:
        """
        Поле внешнего ключа на родителя.

        Args:
            name: Имя типа.

        Returns:
            Имя поля или ``None`` у корня.

        Пример:
            >>> TreeSchema([EntityType('a'), EntityType('b', 'a', 'a_id')]).parent_field('b')
            'a_id'
        """
        return self.get(name).parent_field

    def children_types(self, name: str) -> List[str]:
        """
        Типы, у которых родитель — ``name``.

        Args:
            name: Имя типа.

        Returns:
            Имена дочерних типов в порядке добавления.

        Пример:
            >>> TreeSchema([EntityType('a'), EntityType('b', 'a', 'a_id')]).children_types('a')
            ['b']
        """
        self.get(name)
        return [t.name for t in self._types.values() if t.parent == name]

    def depth(self, name: str) -> int:
        """
        Глубина типа: у корня 0, у его детей 1 и т. д.

        Args:
            name: Имя типа.

        Returns:
            Глубина.

        Пример:
            >>> TreeSchema([EntityType('a'), EntityType('b', 'a', 'a_id')]).depth('b')
            1
        """
        depth, current = 0, self.get(name).parent
        while current is not None:
            depth += 1
            current = self._types[current].parent
        return depth
