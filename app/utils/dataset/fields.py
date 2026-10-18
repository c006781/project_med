# app/utils/dataset/fields.py

"""
Описание полей набора данных (аналог ``TField`` в RAD Studio).

Поле знает: имя, подпись, тип значения, обязательность, «только чтение», видимость,
значение по умолчанию, проверки; бывает **вычисляемым** (функция от строки, не хранится)
и **подстановкой** (показать «Петров И.» по ``patient_id`` — см. ``lookup.py``).
Ссылка на родительскую таблицу (``references``) нужна связи «главная → подчинённая»
(``links.py``), чтобы поле связи находилось само.

Только стандартная библиотека.

Пример:
    >>> f = FieldDef('last_name', 'Фамилия', FieldKind.STRING, required=True)
    >>> f.validate('', {})
    ['поле «Фамилия» обязательно']
    >>> Fields([f]).names()
    ['last_name']
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING, Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple,
)

if TYPE_CHECKING:
    from .aggregate import AggregateDef
    from .lookup import LookupDef

# Проверка значения: (значение, вся строка) -> текст ошибки или None
Validator = Callable[[Any, Mapping[str, Any]], Optional[str]]


class FieldKind(str, Enum):
    """
    Тип значения поля (для проверки при сохранении и для выбора виджета).

    ``ANY`` — без проверки типа (источник сам знает, что хранит).

    Пример:
        >>> FieldKind.DATE.accepts(datetime.date(2026, 10, 18))
        True
        >>> FieldKind.INTEGER.accepts(True)      # bool — не число
        False
    """

    ANY = 'any'
    STRING = 'string'
    TEXT = 'text'
    INTEGER = 'integer'
    FLOAT = 'float'
    BOOLEAN = 'boolean'
    DATE = 'date'
    DATETIME = 'datetime'
    BLOB = 'blob'

    def accepts(self, value: Any) -> bool:
        """
        Подходит ли значение под тип (``None`` подходит всегда — обязательность отдельно).

        Args:
            value: Значение.

        Returns:
            ``True`` — подходит.

        Пример:
            >>> FieldKind.FLOAT.accepts(3)
            True
        """
        if value is None or self is FieldKind.ANY:
            return True
        if self in (FieldKind.STRING, FieldKind.TEXT):
            return isinstance(value, str)
        if self is FieldKind.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        if self is FieldKind.FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if self is FieldKind.BOOLEAN:
            return isinstance(value, bool)
        if self is FieldKind.DATE:
            # datetime — подкласс date: дата со временем в поле «дата» — ошибка
            return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)
        if self is FieldKind.DATETIME:
            return isinstance(value, datetime.datetime)
        if self is FieldKind.BLOB:
            return isinstance(value, (bytes, bytearray, memoryview))
        return True


@dataclass(frozen=True)
class FieldDef:
    """
    Описание одного поля.

    Attributes:
        name: Имя (ключ в строке).
        label: Подпись для экрана (по умолчанию — имя).
        kind: Тип значения.
        required: Обязательное (``None`` и пустая строка — ошибка при сохранении).
        read_only: Только чтение (``set_value`` откажет; вычисляемые и подстановки — всегда).
        visible: Показывать в таблице по умолчанию.
        default: Значение для новой строки — значение или функция без аргументов.
        calculated: Вычисляемое поле: функция от строки; в хранилище не пишется.
        lookup: Подстановка (``lookup.LookupDef``): значение берётся из другого источника
            по ключу из поля строки; в хранилище не пишется.
        references: Имя родительской таблицы, на которую ссылается поле (внешний ключ) —
            для связи «главная → подчинённая».
        persistent: Пишется в хранилище (по умолчанию да). ``False`` — значение приходит
            из хранилища (его вычисляет само хранилище: ФИО пациента у приёма, число фото),
            но обратно не пишется и не правится (как ``ProviderFlags`` в FireDAC).
        aggregate: Итог по подчинённым строкам, который считает программа
            (``aggregate.AggregateDef``: число фото у приёма, сумма чеков); не пишется.
        local: Своё поле набора (как ``InternalCalc`` в RAD Studio): значение живёт в
            наборе по ключу строки, переживает перечитывание, в хранилище не пишется;
            меняется сразу, без правки строки и проверок (галочка-отметка, своя метка).
        validators: Свои проверки ``(значение, строка) -> ошибка | None``.
        display: Отображение значения текстом (по умолчанию ``str``, ``None`` → '').
        extra: Свободные данные для своих виджетов и адаптеров (ширина колонки и т. п.).

    Пример:
        >>> FieldDef('id', read_only=True).stored
        True
        >>> FieldDef('age', calculated=lambda row: 42).stored
        False
    """

    name: str
    label: str = ''
    kind: FieldKind = FieldKind.ANY
    required: bool = False
    read_only: bool = False
    visible: bool = True
    default: Any = None
    calculated: Optional[Callable[[Mapping[str, Any]], Any]] = None
    lookup: Optional['LookupDef'] = None
    references: Optional[str] = None
    persistent: bool = True
    aggregate: Optional['AggregateDef'] = None
    local: bool = False
    validators: Tuple[Validator, ...] = ()
    display: Optional[Callable[[Any], str]] = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Подпись по умолчанию — имя; проверки — кортеж (описание неизменяемо).

        Returns:
            None

        Пример:
            >>> FieldDef('phone').label
            'phone'
        """
        if not self.label:
            object.__setattr__(self, 'label', self.name)
        if not isinstance(self.validators, tuple):
            object.__setattr__(self, 'validators', tuple(self.validators))

    @property
    def stored(self) -> bool:
        """
        Пишется ли поле в хранилище: не вычисляемое, не подстановка, ``persistent``.

        Returns:
            ``True`` — пишется при сохранении (и проверяется).

        Пример:
            >>> FieldDef('name').stored, FieldDef('full_name', persistent=False).stored
            (True, False)
        """
        return (self.persistent and not self.local and self.calculated is None
                and self.lookup is None and self.aggregate is None)

    @property
    def editable(self) -> bool:
        """
        Можно ли менять значение: хранимое или своё поле набора, не только для чтения.

        Returns:
            ``True`` — можно.

        Пример:
            >>> FieldDef('id', read_only=True).editable, FieldDef('mark', local=True).editable
            (False, True)
        """
        return (self.stored or self.local) and not self.read_only

    def default_value(self) -> Any:
        """
        Значение по умолчанию для новой строки (функция — вызывается каждый раз).

        Returns:
            Значение.

        Пример:
            >>> FieldDef('date', default=lambda: 'сегодня').default_value()
            'сегодня'
        """
        return self.default() if callable(self.default) else self.default

    def validate(self, value: Any, row: Mapping[str, Any]) -> List[str]:
        """
        Проверяет значение: обязательность, тип, свои проверки.

        Args:
            value: Значение поля.
            row: Вся строка (для проверок, зависящих от других полей).

        Returns:
            Список ошибок (пусто — значение годится).

        Пример:
            >>> FieldDef('n', 'Число', FieldKind.INTEGER).validate('5', {})
            ['поле «Число»: ожидается integer, получено str']
        """
        if not self.stored:
            return []
        errors: List[str] = []
        if self.required and (value is None or (isinstance(value, str) and not value.strip())):
            errors.append(f"поле «{self.label}» обязательно")
            return errors
        if not self.kind.accepts(value):
            errors.append(f"поле «{self.label}»: ожидается {self.kind.value}, "
                          f"получено {type(value).__name__}")
            return errors
        for check in self.validators:
            message = check(value, row)
            if message:
                errors.append(f"поле «{self.label}»: {message}")
        return errors

    def text(self, value: Any) -> str:
        """
        Значение текстом для экрана.

        Args:
            value: Значение.

        Returns:
            Текст (``None`` → пустая строка).

        Пример:
            >>> FieldDef('d', display=lambda v: v.upper()).text('ok')
            'OK'
        """
        if value is None:
            return ''
        return self.display(value) if self.display else str(value)


class Fields:
    """
    Упорядоченный набор описаний полей с доступом по имени.

    Пример:
        >>> fields = Fields([FieldDef('id'), FieldDef('name', visible=False)])
        >>> fields['name'].visible, len(fields), [f.name for f in fields.visible()]
        (False, 2, ['id'])
    """

    def __init__(self, fields: Iterable[FieldDef] = ()) -> None:
        """
        Args:
            fields: Описания полей; имена должны быть уникальны.

        Raises:
            ValueError: Повтор имени.

        Пример:
            >>> Fields([FieldDef('a'), FieldDef('a')])
            Traceback (most recent call last):
            ValueError: поле 'a' описано дважды
        """
        self._items: Dict[str, FieldDef] = {}
        for f in fields:
            if f.name in self._items:
                raise ValueError(f"поле {f.name!r} описано дважды")
            self._items[f.name] = f

    def __getitem__(self, name: str) -> FieldDef:
        """
        Описание поля по имени.

        Args:
            name: Имя поля.

        Returns:
            ``FieldDef``.

        Raises:
            KeyError: Поля нет (с перечнем имеющихся).

        Пример:
            >>> Fields([FieldDef('a')])['a'].name
            'a'
        """
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"нет поля {name!r}; есть: {', '.join(self._items) or '—'}") from None

    def get(self, name: str) -> Optional[FieldDef]:
        """
        Описание поля или ``None``.

        Args:
            name: Имя поля.

        Returns:
            ``FieldDef`` или ``None``.

        Пример:
            >>> Fields().get('x') is None
            True
        """
        return self._items.get(name)

    def __contains__(self, name: object) -> bool:
        """
        Есть ли поле с таким именем.

        Args:
            name: Имя.

        Returns:
            ``True`` — есть.

        Пример:
            >>> 'a' in Fields([FieldDef('a')])
            True
        """
        return name in self._items

    def __iter__(self) -> Iterator[FieldDef]:
        """
        Поля по порядку описания.

        Returns:
            Итератор ``FieldDef``.

        Пример:
            >>> [f.name for f in Fields([FieldDef('a'), FieldDef('b')])]
            ['a', 'b']
        """
        return iter(self._items.values())

    def __len__(self) -> int:
        """
        Число полей.

        Returns:
            Количество.

        Пример:
            >>> len(Fields([FieldDef('a')]))
            1
        """
        return len(self._items)

    def names(self) -> List[str]:
        """
        Имена полей по порядку.

        Returns:
            Список имён.

        Пример:
            >>> Fields([FieldDef('a')]).names()
            ['a']
        """
        return list(self._items)

    def visible(self) -> List[FieldDef]:
        """
        Видимые поля (колонки таблицы по умолчанию).

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> Fields([FieldDef('a', visible=False)]).visible()
            []
        """
        return [f for f in self._items.values() if f.visible]

    def stored(self) -> List[FieldDef]:
        """
        Хранимые поля (пишутся при сохранении).

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> Fields([FieldDef('a'), FieldDef('b', calculated=len)]).stored()[0].name
            'a'
        """
        return [f for f in self._items.values() if f.stored]

    def aggregates(self) -> List[FieldDef]:
        """
        Поля-итоги по подчинённым (``aggregate``).

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> [f.name for f in fields.aggregates()]
            ['photo_count']
        """
        return [f for f in self._items.values() if f.aggregate is not None]

    def local(self) -> List[FieldDef]:
        """
        Свои поля набора (``local``).

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> Fields([FieldDef('mark', local=True)]).local()[0].name
            'mark'
        """
        return [f for f in self._items.values() if f.local]

    def referencing(self, table: str) -> List[FieldDef]:
        """
        Поля, ссылающиеся на таблицу ``table`` (для связи «главная → подчинённая»).

        Args:
            table: Имя родительской таблицы.

        Returns:
            Список ``FieldDef``.

        Пример:
            >>> Fields([FieldDef('patient_id', references='patients')]).referencing('patients')[0].name
            'patient_id'
        """
        return [f for f in self._items.values() if f.references == table]

    @classmethod
    def from_names(cls, names: Iterable[str]) -> 'Fields':
        """
        Поля без описаний — только имена (когда источник ничего о полях не сообщает).

        Args:
            names: Имена.

        Returns:
            ``Fields``.

        Пример:
            >>> Fields.from_names(['id', 'name']).names()
            ['id', 'name']
        """
        return cls(FieldDef(n) for n in names)
