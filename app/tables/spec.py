# app/tables/spec.py

"""
Одно описание таблицы (``TableSpec``) и реестр таблиц (``TableRegistry``).

Из одного описания строится всё, что раньше перечислялось вручную в нескольких местах:

| Что | Откуда |
|---|---|
| поля набора (подписи, типы, правка, обязательность) | ``field_configs`` + DTO + модель (``fields_from_config``) |
| свои столбцы: отметки, по строке, итоги по подчинённым | ``extras`` описания (``mark``, ``calc``, ``total``) |
| родитель таблицы и поле связи | внешний ключ модели на другую таблицу реестра |
| схема черновиков (дерево таблиц) | ``TableRegistry.drafts_schema`` |
| запись черновиков через сервисы | ``TableRegistry.service_adapter`` |
| наборы данных, источники, связи «главная → подчинённая» | ``TableRegistry.build`` |
| колонки таблицы и поля формы экрана | ``columns`` / ``form`` описания |

Итог по подчинённым — на выбор (решение владельца 2026-10-18):
    * считает **программа** — ``total(...)`` в ``extras``: пачкой на окно, видит
      черновики, пересчитывается на лету;
    * считает **база** — поле в ``field_configs`` с ``sql_compute`` (как ``has_photos``):
      сортировка по всей таблице, но черновики не видны до сохранения.

Пример:
    >>> registry = TableRegistry([
    ...     TableSpec('patients', 'patient', 'Пациенты', 'Пациент', Patient, PatientDTO, PATIENT_CONFIG,
    ...               service=get_patient_service, extras=(total('visits', 'Приёмов', 'appointments'),)),
    ...     TableSpec('appointments', 'appointment', 'Приёмы', 'Приём', Appointment, AppointmentDTO,
    ...               APPOINTMENT_CONFIG, service=get_appointment_service),
    ... ])
    >>> registry.parent('appointments')
    'patients'
    >>> built = registry.build(); built['patients'].value('visits')
    2
"""

from __future__ import annotations

import dataclasses
import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.dataset_app.fields import fields_from_config, references_of
from app.dataset_app.service_backend import ServiceBackend
if TYPE_CHECKING:
    from app.draft.integration import ServiceAdapter
    from app.utils.drafts import TreeSchema

from app.utils.dataset import (
    AggFunc, AggregateDef, Condition, DataSet, DataSource, FetchMode, FieldDef, FieldKind,
    MasterDetailLink, Query,
)


@dataclass(frozen=True)
class Extra:
    """
    Столбец, которого нет в ``field_configs``: отметка, вычисляемый по строке, итог по
    подчинённым (считает программа). Создаётся функциями ``mark``, ``calc``, ``total``.

    Attributes:
        name: Имя столбца.
        label: Подпись.
        kind: ``'mark'`` / ``'calc'`` / ``'total'``.
        value_kind: Тип значения (галочка, число…).
        func: Для ``calc`` — функция от строки (или от строки и сервиса таблицы).
        child: Для ``total`` — имя подчинённой таблицы реестра.
        aggregate: Для ``total`` — вид итога.
        field: Для ``total`` — поле подчинённой строки (сумма/мин/макс/среднее).
        where: Для ``total`` — условия на подчинённые строки.
        visible: Показывать столбцом по умолчанию.
        display: Показ значения текстом.
        widget: Виджет формы (``'image'`` — картинка…; см. ``dataset_qt.forms``).
        by: Для ``total`` — кто считает: ``'program'`` (по строкам, видит черновики) или
            ``'sql'`` (БД, отдельным запросом ``GROUP BY`` — не мешает правке таблицы данных).
        unsaved: Для ``total(by='sql')`` — поправка на черновики: ``'delta'`` (числа строк)
            или ``'ignore'``.
        sql_where: Для ``total(by='sql')`` — своё условие SQL на подчинённые строки.

    Пример:
        >>> mark('selected', '✓').kind
        'mark'
    """

    name: str
    label: str = ''
    kind: str = 'calc'
    value_kind: FieldKind = FieldKind.ANY
    func: Optional[Callable[..., Any]] = None
    child: Optional[str] = None
    aggregate: Any = AggFunc.COUNT
    field: Optional[str] = None
    where: Tuple[Condition, ...] = ()
    visible: bool = True
    display: Optional[Callable[[Any], str]] = None
    widget: Optional[str] = None
    by: str = 'program'
    unsaved: str = 'delta'
    sql_where: Optional[Callable[[Any], Any]] = None


def mark(name: str = 'mark', label: str = '✓') -> Extra:
    """
    Столбец-отметка (галочка): своё поле набора — в базу не пишется, переживает
    перечитывание, ставится без правки строки.

    Args:
        name: Имя.
        label: Подпись.

    Returns:
        ``Extra``.

    Пример:
        >>> mark().value_kind
        <FieldKind.BOOLEAN: 'boolean'>
    """
    return Extra(name, label, 'mark', FieldKind.BOOLEAN)


def calc(name: str, label: str, func: Callable[..., Any], kind: FieldKind = FieldKind.ANY, *,
         visible: bool = True, display: Optional[Callable[[Any], str]] = None,
         widget: Optional[str] = None) -> Extra:
    """
    Столбец, вычисляемый программой по своей строке.

    Args:
        name: Имя.
        label: Подпись.
        func: ``func(строка)`` или ``func(строка, сервис_таблицы)`` (второй аргумент —
            когда для вычисления нужен сервис: например, папка снимков).
        kind: Тип значения.
        visible: Показывать столбцом.
        display: Показ текстом.
        widget: Виджет формы (``'image'``…).

    Returns:
        ``Extra``.

    Пример:
        >>> calc('age', 'Возраст', lambda r: 2026 - r['birth_date'].year, FieldKind.INTEGER).kind
        'calc'
    """
    return Extra(name, label, 'calc', kind, func=func, visible=visible, display=display, widget=widget)


def total(name: str, label: str, child: str, func: Any = AggFunc.COUNT,
          field: Optional[str] = None, where: Sequence[Condition] = (), *,
          kind: Optional[FieldKind] = None, display: Optional[Callable[[Any], str]] = None,
          by: str = 'program', unsaved: str = 'delta',
          sql_where: Optional[Callable[[Any], Any]] = None) -> Extra:
    """
    Итог по подчинённой таблице реестра, который считает программа (число фото у приёма,
    сумма чеков у пациента).

    Args:
        name: Имя.
        label: Подпись.
        child: Подчинённая таблица (по имени в реестре).
        func: Вид итога (``AggFunc``) или своя функция от списка подчинённых строк —
            любая логика (``lambda rows: sum(r['amount'] for r in rows if r['paid'])``).
        field: Поле подчинённой строки (для суммы/мин/макс/среднего).
        where: Условия на подчинённые строки.
        kind: Тип значения (по умолчанию: число — целое, остальное — без проверки).
        display: Показ текстом.
        by: Кто считает: ``'program'`` (по строкам; видит черновики; любая своя функция)
            или ``'sql'`` (БД отдельным запросом; ``func`` — count/sum/min/max/avg).
        unsaved: Для ``by='sql'``: поправка на черновики — ``'delta'`` или ``'ignore'``.
        sql_where: Для ``by='sql'``: своё условие SQL (``lambda table: table.c.paid``).

    Returns:
        ``Extra``.

    Raises:
        ValueError: Неизвестный ``by``; для ``'sql'`` — своя функция или условия ``where``.

    Пример:
        >>> total('photo_count', 'Фото', 'photos').aggregate
        <AggFunc.COUNT: 'count'>
    """
    if not callable(func) or isinstance(func, AggFunc):
        func = AggFunc(func)
    if by not in ('program', 'sql'):
        raise ValueError(f"total {name}: by={by!r} — допустимо 'program' или 'sql'")
    if by == 'sql' and (not isinstance(func, AggFunc) or where):
        raise ValueError(f"total {name}: БД считает count/sum/min/max/avg; условия — sql_where")
    if kind is None:
        kind = FieldKind.INTEGER if func is AggFunc.COUNT else FieldKind.ANY
    return Extra(name, label, 'total', kind, child=child, aggregate=func, field=field,
                 where=tuple(where), display=display, by=by, unsaved=unsaved, sql_where=sql_where)


@dataclass(frozen=True)
class Link:
    """
    Связь-ссылка поля таблицы на другую таблицу реестра (не владение; 2026-10-18).

    Без описания каждый внешний ключ на таблицу реестра (кроме связи с родителем) —
    ссылка с правилом «нельзя удалить, пока ссылаются». Описание меняет правило.

    Attributes:
        field: Поле ссылки (``doctor_id``).
        table: Таблица цели (``doctors``).
        on_delete: Цель удаляют, а на неё ссылаются записи, которые не удаляются:
            ``'restrict'`` — отказ, ``'set_null'`` — ссылка обнуляется, ``'cascade'`` —
            ссылающиеся удаляются тоже.
        collect: Цель — переиспользуемые данные: удаляется, когда больше никому не нужна.
        display: Что показывать вместо id и в списке выбора: поле цели или функция от
            строки цели (по умолчанию — первое строковое видимое поле цели).

    Пример:
        >>> ref('doctor_id', 'doctors', on_delete='set_null').on_delete
        'set_null'
    """

    field: str
    table: str
    on_delete: str = 'restrict'
    collect: bool = False
    display: Any = None


def ref(field: str, table: str, on_delete: str = 'restrict', collect: bool = False,
        display: Any = None) -> Link:
    """
    Настройка связи-ссылки (см. ``Link``).

    Args:
        field: Поле ссылки.
        table: Таблица цели.
        on_delete: Правило удаления цели.
        collect: Цель — переиспользуемые данные.
        display: Показ цели (поле или функция от строки).

    Returns:
        ``Link``.

    Пример:
        >>> ref('template_id', 'templates', collect=True).collect
        True
    """
    return Link(field, table, on_delete, collect, display)


@dataclass(frozen=True)
class TableSpec:
    """
    Описание таблицы.

    Attributes:
        name: Имя таблицы (= имя набора, на него ссылаются внешние ключи).
        entity: Тип записи в черновиках (``'patient'``).
        title: Заголовок для экрана (``'Пациенты'``).
        label: Одна запись (``'Пациент'`` — в вопросах при сохранении черновиков).
        model: Модель SQLAlchemy.
        dto: Класс DTO.
        config: ``field_configs`` таблицы.
        service: Поставщик сервиса (функция без аргументов).
        order: Сортировка по умолчанию (``'-date'``…).
        columns: Колонки таблицы экрана (пусто — видимые поля).
        form: Поля формы экрана (пусто — видимые поля, кроме ключа).
        extras: Свои столбцы (``mark``, ``calc``, ``total``).
        parent: Родительская таблица (по умолчанию — из внешнего ключа модели на таблицу
            реестра; задать, если таких ключей несколько).
        parent_field: Поле связи с родителем (вместе с ``parent``).
        links: Настройки связей-ссылок (``ref(...)``); без настройки — правило
            «нельзя удалить цель, пока на неё ссылаются».
        skip: Поля ``field_configs``, которые набору не нужны (например, старый итог
            ``sql_compute``, вытесненный ``total(by='sql')``: его подзапрос не утяжеляет
            запрос таблицы данных).
        fetch_size: Свой размер порции загрузки.

    Пример:
        >>> spec.columns
        ('date', 'reason_text', 'photo_count')
    """

    name: str
    entity: str
    title: str
    label: str
    model: Any
    dto: Any
    config: Mapping[str, Mapping[str, Any]]
    service: Callable[[], Any]
    order: Tuple[str, ...] = ()
    columns: Tuple[str, ...] = ()
    form: Tuple[str, ...] = ()
    extras: Tuple[Extra, ...] = ()
    parent: Optional[str] = None
    parent_field: Optional[str] = None
    links: Tuple[Link, ...] = ()
    skip: Tuple[str, ...] = ()
    fetch_size: Optional[int] = None


class SpecError(ValueError):
    """
    Описания таблиц противоречат друг другу (повтор имени, неоднозначный родитель…).

    Пример:
        >>> raise SpecError('таблица patients описана дважды')
        Traceback (most recent call last):
        SpecError: таблица patients описана дважды
    """


@dataclass
class BuiltTables:
    """
    Наборы, собранные по реестру.

    Attributes:
        registry: Реестр.
        tables: «имя таблицы → набор» (порядок — сверху вниз по дереву); список наборов —
            ``datasets``.
        sources: «имя таблицы → DataSource».
        links: Связи «главная → подчинённая».
        drafts: Черновики (``None`` — запись сразу в БД).
        writers: Мосты к черновикам по именам таблиц.

    Пример:
        >>> built['appointments'].row_count
        2
    """

    registry: 'TableRegistry'
    tables: Dict[str, DataSet]
    sources: Dict[str, DataSource]
    links: List[MasterDetailLink]
    drafts: Any = None
    writers: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> DataSet:
        """
        Набор по имени таблицы.

        Args:
            name: Имя таблицы.

        Returns:
            Набор.

        Пример:
            >>> built['patients'].name
            'patients'
        """
        return self.tables[name]

    @property
    def datasets(self) -> List[DataSet]:
        """
        Наборы сверху вниз по дереву.

        Returns:
            Список наборов.

        Пример:
            >>> [d.name for d in built.datasets]
            ['patients', 'appointments', 'photos']
        """
        return list(self.tables.values())

    def __getattr__(self, name: str) -> DataSet:
        """
        Набор по имени таблицы атрибутом (``built.patients``).

        Args:
            name: Имя таблицы.

        Returns:
            Набор.

        Raises:
            AttributeError: Нет такой таблицы.

        Пример:
            >>> built.photos.name
            'photos'
        """
        tables = self.__dict__.get('tables', {})
        if name in tables:
            return tables[name]
        raise AttributeError(name)

    def open(self) -> None:
        """
        Открывает наборы сверху вниз.

        Returns:
            None

        Пример:
            >>> built.open()
        """
        for dataset in self.datasets:
            dataset.open()

    def close(self) -> None:
        """
        Закрывает наборы снизу вверх и отключает мосты к черновикам.

        Returns:
            None

        Пример:
            >>> built.close()
        """
        for dataset in reversed(self.datasets):
            dataset.close()
        for writer in self.writers.values():
            writer.close()

    def post_all(self) -> None:
        """
        Завершает незавершённые правки всех наборов.

        Returns:
            None

        Raises:
            ValidationError: Строка не прошла проверку.

        Пример:
            >>> built.post_all()
        """
        for dataset in self.datasets:
            if dataset.active:
                dataset.post()

    def save(self, *args: Any, **kwargs: Any) -> Any:
        """
        Сохраняет черновики (``AppDrafts.save``); перед этим — ``post_all``.

        Args:
            *args: Аргументы ``AppDrafts.save``.
            **kwargs: То же.

        Returns:
            Итог сохранения или ``None`` (отказ пользователя).

        Raises:
            RuntimeError: Наборы без черновиков.

        Пример:
            >>> built.save()
        """
        if self.drafts is None:
            raise RuntimeError("наборы без черновиков: правки уже в БД")
        self.post_all()
        return self.drafts.save(*args, **kwargs)


class TableRegistry:
    """
    Реестр описаний таблиц: дерево, черновики, наборы — из одного места.

    Пример:
        >>> CLINIC.names()
        ['patients', 'appointments', 'photos']
    """

    def __init__(self, specs: Iterable[TableSpec]) -> None:
        """
        Args:
            specs: Описания таблиц.

        Raises:
            SpecError: Повтор имени/типа записи, неоднозначный или неизвестный родитель,
                итог по таблице, которая не подчинена этой.

        Пример:
            >>> TableRegistry([spec, spec])
            Traceback (most recent call last):
            SpecError: таблица patients описана дважды
        """
        self._specs: Dict[str, TableSpec] = {}
        entities = set()
        for spec in specs:
            if spec.name in self._specs:
                raise SpecError(f"таблица {spec.name} описана дважды")
            if spec.entity in entities:
                raise SpecError(f"тип записи {spec.entity} описан дважды")
            self._specs[spec.name] = spec
            entities.add(spec.entity)
        self._parents: Dict[str, Tuple[Optional[str], Optional[str]]] = {
            name: self._find_parent(spec) for name, spec in self._specs.items()}
        self._links: Dict[str, Tuple[Link, ...]] = {
            name: self._find_links(spec) for name, spec in self._specs.items()}
        self._check_totals()

    # ------------------------------------------------------------------ дерево

    def _find_parent(self, spec: TableSpec) -> Tuple[Optional[str], Optional[str]]:
        """
        Родитель таблицы и поле связи: заданные явно или по внешнему ключу модели на
        таблицу реестра.

        Args:
            spec: Описание.

        Returns:
            ``(родитель, поле)`` или ``(None, None)`` — корень дерева.

        Raises:
            SpecError: Ключей на таблицы реестра несколько (укажите ``parent``) или
                указанный родитель неизвестен.

        Пример:
            >>> registry._find_parent(photos_spec)
            ('appointments', 'appointment_id')
        """
        if spec.parent is not None:
            if spec.parent not in self._specs:
                raise SpecError(f"у {spec.name} родитель {spec.parent} не описан")
            field_name = spec.parent_field or next(
                (f for f, t in references_of(spec.model).items() if t == spec.parent), None)
            if field_name is None:
                raise SpecError(f"у {spec.name} нет поля связи с {spec.parent} (parent_field)")
            return spec.parent, field_name
        declared = {link.field for link in spec.links}
        candidates = [(t, f) for f, t in references_of(spec.model).items()
                      if t in self._specs and t != spec.name and f not in declared]
        if len(candidates) > 1:
            raise SpecError(f"у {spec.name} несколько ссылок на таблицы реестра "
                            f"({', '.join(f for _, f in candidates)}) — укажите parent")
        return candidates[0] if candidates else (None, None)

    def _find_links(self, spec: TableSpec) -> Tuple[Link, ...]:
        """
        Связи-ссылки таблицы: описанные явно + остальные внешние ключи на таблицы реестра
        (кроме связи с родителем) с правилом по умолчанию.

        Args:
            spec: Описание.

        Returns:
            Кортеж ``Link``.

        Raises:
            SpecError: Ссылка на неописанную таблицу или на поле связи с родителем.

        Пример:
            >>> registry._find_links(orders_spec)
            (Link(field='doctor_id', table='doctors', on_delete='restrict', ...),)
        """
        parent_field = self._parents[spec.name][1]
        result: Dict[str, Link] = {}
        for field_name, table in references_of(spec.model).items():
            if table in self._specs and field_name != parent_field:
                result[field_name] = Link(field_name, table)
        for link in spec.links:
            if link.table not in self._specs:
                raise SpecError(f"ссылка {spec.name}.{link.field}: таблица {link.table} не описана")
            if link.field == parent_field:
                raise SpecError(f"ссылка {spec.name}.{link.field}: это связь с родителем, а не ссылка")
            result[link.field] = link
        return tuple(result.values())

    def links(self, name: str) -> Tuple[Link, ...]:
        """
        Связи-ссылки таблицы.

        Args:
            name: Имя таблицы.

        Returns:
            Кортеж ``Link``.

        Пример:
            >>> registry.links('test_orders')[0].table
            'test_doctors'
        """
        return self._links[name]

    def _check_totals(self) -> None:
        """
        Итог по подчинённым — только по таблице, которая действительно подчинена этой.

        Returns:
            None

        Raises:
            SpecError: Неизвестная или не подчинённая таблица итога.

        Пример:
            >>> registry._check_totals()
        """
        for spec in self._specs.values():
            for extra in spec.extras:
                if extra.kind != 'total':
                    continue
                if extra.child not in self._specs:
                    raise SpecError(f"итог {spec.name}.{extra.name}: таблица {extra.child} не описана")
                if self.parent(extra.child) != spec.name:
                    raise SpecError(f"итог {spec.name}.{extra.name}: {extra.child} не подчинена {spec.name}")

    def get(self, name: str) -> TableSpec:
        """
        Описание по имени таблицы.

        Args:
            name: Имя.

        Returns:
            ``TableSpec``.

        Raises:
            KeyError: Нет такой таблицы.

        Пример:
            >>> CLINIC.get('photos').label
            'Фото'
        """
        try:
            return self._specs[name]
        except KeyError:
            raise KeyError(f"нет таблицы {name!r}; есть: {', '.join(self._specs)}") from None

    def __contains__(self, name: object) -> bool:
        """
        Описана ли таблица.

        Args:
            name: Имя.

        Returns:
            ``True`` — описана.

        Пример:
            >>> 'photos' in CLINIC
            True
        """
        return name in self._specs

    def names(self) -> List[str]:
        """
        Имена таблиц сверху вниз по дереву (родитель раньше подчинённых).

        Returns:
            Список имён.

        Пример:
            >>> CLINIC.names()
            ['patients', 'appointments', 'photos']
        """
        ordered: List[str] = []

        def visit(name: str) -> None:
            """
            Добавляет таблицу после её родителя (обход вверх по дереву).

            Args:
                name: Имя таблицы.

            Returns:
                None

            Пример:
                >>> visit('photos')       # добавит patients, appointments, photos
            """
            if name in ordered:
                return
            parent = self.parent(name)
            if parent is not None:
                visit(parent)
            ordered.append(name)

        for name in self._specs:
            visit(name)
        return ordered

    def parent(self, name: str) -> Optional[str]:
        """
        Родительская таблица.

        Args:
            name: Имя таблицы.

        Returns:
            Имя родителя или ``None`` (корень).

        Пример:
            >>> CLINIC.parent('photos')
            'appointments'
        """
        return self._parents[name][0]

    def parent_field(self, name: str) -> Optional[str]:
        """
        Поле связи таблицы с родителем.

        Args:
            name: Имя таблицы.

        Returns:
            Имя поля или ``None``.

        Пример:
            >>> CLINIC.parent_field('photos')
            'appointment_id'
        """
        return self._parents[name][1]

    def children(self, name: str) -> List[str]:
        """
        Подчинённые таблицы.

        Args:
            name: Имя таблицы.

        Returns:
            Имена (по порядку описания).

        Пример:
            >>> CLINIC.children('patients')
            ['appointments']
        """
        return [n for n in self._specs if self.parent(n) == name]

    def chain(self, root: Optional[str] = None) -> List[str]:
        """
        Цепочка «главная → подчинённая → …» от таблицы (у каждой берётся первая
        подчинённая) — для экрана из колонок.

        Args:
            root: Начало (по умолчанию — первый корень).

        Returns:
            Имена таблиц.

        Пример:
            >>> CLINIC.chain()
            ['patients', 'appointments', 'photos']
        """
        name = root or next(n for n in self.names() if self.parent(n) is None)
        result = [name]
        while self.children(name):
            name = self.children(name)[0]
            result.append(name)
        return result

    # ------------------------------------------------------------------ черновики

    def drafts_schema(self) -> 'TreeSchema':
        """
        Схема черновиков (дерево типов записей) — из описаний.

        Returns:
            ``TreeSchema``.

        Пример:
            >>> CLINIC.drafts_schema().depth('photo')
            2
        """
        from app.utils.drafts import EntityType, Reference, TreeSchema
        types = []
        for name in self.names():
            spec, parent = self._specs[name], self.parent(name)
            references = [Reference(link.field, self._specs[link.table].entity, link.on_delete,
                                    link.collect) for link in self.links(name)]
            if parent is None:
                types.append(EntityType(spec.entity, label=spec.label, references=references))
            else:
                types.append(EntityType(spec.entity, parent=self._specs[parent].entity,
                                        parent_field=self.parent_field(name), label=spec.label,
                                        references=references))
        return TreeSchema(types)

    def service_adapter(self, transaction_factory: Optional[Callable[[], Any]] = None,
                        services: Optional[Mapping[str, Callable[[], Any]]] = None) -> 'ServiceAdapter':
        """
        Запись черновиков через сервисы — из описаний.

        Args:
            transaction_factory: Откуда брать транзакцию (одна на всё сохранение).
            services: Свои поставщики сервисов по типам записей (тесты).

        Returns:
            ``ServiceAdapter``.

        Пример:
            >>> CLINIC.service_adapter().entities()
            ['patient', 'appointment', 'photo']
        """
        from app.draft.integration import ServiceAdapter
        services = dict(services or {})
        return ServiceAdapter({spec.entity: (services.get(spec.entity, spec.service), spec.dto)
                               for spec in (self._specs[n] for n in self.names())},
                              transaction_factory=transaction_factory)

    # ------------------------------------------------------------------ наборы

    def _sql_totals(self, spec: TableSpec, child: str, datasets: Mapping[str, DataSet],
                    services: Mapping[str, Callable[[], Any]], cache: Dict[Any, Any]) -> Any:
        """
        Общий объект SQL-итогов таблицы по подчинённой таблице (все её ``total(by='sql')`` —
        одним запросом на окно).

        Args:
            spec: Описание главной таблицы.
            child: Подчинённая таблица.
            datasets: Собранные наборы.
            services: Свои поставщики сервисов.
            cache: Объекты этой сборки (один на пару «главная, подчинённая»; не на реестре —
                реестр общий, старые наборы держались бы в памяти).

        Returns:
            ``SqlTotals``.

        Пример:
            >>> registry._sql_totals(appointments_spec, 'photos', datasets, {})
            <SqlTotals ...>
        """
        from app.dataset_app.sql_totals import SqlTotals
        key = (spec.name, child)
        if key in cache:
            return cache[key]
        child_spec = self._specs[child]
        extras = [e for e in spec.extras if e.kind == 'total' and e.by == 'sql' and e.child == child]
        columns = {e.name: (e.aggregate.value, e.field) for e in extras}
        provider = services.get(child_spec.entity, child_spec.service)
        where = next((e.sql_where for e in extras if e.sql_where is not None), None)
        unsaved = 'ignore' if all(e.unsaved == 'ignore' for e in extras) else 'delta'
        totals = SqlTotals(lambda: provider()._db.engine, child_spec.model.__table__,
                           self.parent_field(child), columns, where=where,
                           child=datasets.get(child), unsaved=unsaved)
        cache[key] = totals
        return totals

    def _extra_field(self, spec: TableSpec, extra: Extra, datasets: Mapping[str, DataSet],
                     service: Callable[[], Any], services: Optional[Mapping[str, Callable[[], Any]]] = None,
                     cache: Optional[Dict[Any, Any]] = None) -> FieldDef:
        """
        ``FieldDef`` своего столбца.

        Args:
            spec: Описание таблицы.
            extra: Свой столбец.
            datasets: Уже собранные наборы (подчинённые — для итогов).
            service: Поставщик сервиса таблицы (для ``calc`` с двумя аргументами).

        Returns:
            ``FieldDef``.

        Пример:
            >>> registry._extra_field(spec, mark(), {}, service).local
            True
        """
        label = extra.label or extra.name
        if extra.kind == 'mark':
            return FieldDef(extra.name, label, FieldKind.BOOLEAN, local=True, default=False,
                            visible=extra.visible)
        if extra.kind == 'total':
            child = extra.child
            if extra.by == 'sql':
                aggregate = self._sql_totals(spec, child, datasets, services or {},
                                             cache if cache is not None else {}).column(
                    extra.name, 0 if extra.aggregate is AggFunc.COUNT else None)
            else:
                aggregate = AggregateDef(datasets[child], self.parent_field(child), extra.aggregate,
                                         extra.field, extra.where)
            return FieldDef(extra.name, label, extra.value_kind, aggregate=aggregate,
                            visible=extra.visible, display=extra.display)
        func = extra.func
        try:
            takes_service = len(inspect.signature(func).parameters) >= 2
        except (TypeError, ValueError):
            takes_service = False
        compute = (lambda row, f=func: f(row, service())) if takes_service else func
        return FieldDef(extra.name, label, extra.value_kind, calculated=compute,
                        visible=extra.visible, display=extra.display,
                        extra={'widget': extra.widget} if extra.widget else {})

    def _link_field(self, definition: FieldDef, spec: TableSpec, drafts: Any,
                    services: Mapping[str, Callable[[], Any]]) -> FieldDef:
        """
        Поле-ссылка: показ цели вместо id и список выбора (записи цели из БД + новые
        несохранённые из черновиков). Остальные поля — как есть.

        Args:
            definition: Поле из ``field_configs``.
            spec: Описание таблицы.
            drafts: Черновики (``None`` — без них).
            services: Свои поставщики сервисов.

        Returns:
            ``FieldDef`` (новое — для ссылки, то же — для остальных).

        Пример:
            >>> registry._link_field(FieldDef('doctor_id'), orders_spec, None, {}).extra['choices']()
            [(5, 'Иванов')]
        """
        link = next((l for l in self.links(spec.name) if l.field == definition.name), None)
        if link is None:
            return definition
        target = self._specs[link.table]
        show = _display_of(target, link)
        provider = services.get(target.entity, target.service)
        target_fields = fields_from_config(target.config, target.dto, target.model)
        backend = ServiceBackend(provider, target.dto, target_fields)

        def target_row(key: Any) -> Optional[Mapping[str, Any]]:
            """
            Строка цели по ключу: из БД, а новая — из черновиков.

            Args:
                key: Ключ.

            Returns:
                Строка или ``None``.

            Пример:
                >>> target_row(-1)
                {'name': 'Новый врач'}
            """
            if key is None:
                return None
            row = backend.get(key)
            if row is None and drafts is not None:
                draft = drafts.store.get(target.entity, key)
                if draft is not None:
                    row = dict(draft.data, id=key)
            elif row is not None and drafts is not None and drafts.store.has_draft(target.entity, key):
                row = drafts.store.effective(target.entity, key, row)
            return row

        def text(key: Any) -> str:
            """
            Ключ ссылки → текст для показа.

            Args:
                key: Ключ.

            Returns:
                Текст.

            Пример:
                >>> text(5)
                'Иванов'
            """
            row = target_row(key)
            return '' if key is None else (str(show(row)) if row is not None else f"#{key}")

        def choices() -> List[Tuple[Any, str]]:
            """
            Список выбора: записи цели (из БД, с правками черновиков) + новые черновики.

            Returns:
                ``[(id, текст), …]``.

            Пример:
                >>> choices()
                [(5, 'Иванов'), (-1, 'Новый врач')]
            """
            rows = list(backend.fetch(Query()).rows)
            if drafts is not None:
                store = drafts.store
                rows = [store.effective(target.entity, r['id'], r) if store.has_draft(target.entity, r['id'])
                        else r for r in rows]
                rows = [r for r in rows if not ((d := store.get(target.entity, r['id'])) and d.deleted)]
                rows += [dict(d.data, id=d.id) for d in store.drafts(target.entity, new_only=True)
                         if not d.deleted]
            return [(r['id'], str(show(r))) for r in rows]

        return dataclasses.replace(definition, display=text,
                                   extra={**definition.extra, 'choices': choices, 'link': link})

    def build(self, *, drafts: Any = None, services: Optional[Mapping[str, Callable[[], Any]]] = None,
              fetch_mode: FetchMode = FetchMode.ON_DEMAND, fetch_size: int = 50,
              sizes: Optional[Mapping[str, int]] = None,
              tables: Optional[Sequence[str]] = None) -> BuiltTables:
        """
        Собирает наборы по описаниям: поля, свои столбцы, способ записи (сразу в БД или
        черновики), связи «главная → подчинённая».

        Args:
            drafts: Черновики (``AppDrafts``); ``None`` — запись сразу в БД.
            services: Свои поставщики сервисов по типам записей (тесты).
            fetch_mode: Всё сразу или порциями.
            fetch_size: Размер порции.
            sizes: Свой размер порции по именам таблиц (важнее ``fetch_size`` описания).
            tables: Только эти таблицы (вместе с их родителями); по умолчанию — все.

        Returns:
            ``BuiltTables`` (наборы закрыты — ``open()``).

        Пример:
            >>> built = CLINIC.build(drafts=create_app_drafts()); built.open()
        """
        services = dict(services or {})
        wanted = self.names()
        if tables is not None:
            keep = set()
            for name in tables:
                while name is not None:
                    keep.add(name)
                    name = self.parent(name)
            wanted = [n for n in wanted if n in keep]
        datasets: Dict[str, DataSet] = {}
        writers: Dict[str, Any] = {}
        sql_cache: Dict[Any, Any] = {}                     # объекты SQL-итогов этой сборки
        for name in reversed(wanted):                     # подчинённые раньше: итоги ссылаются на них
            spec = self._specs[name]
            provider = services.get(spec.entity, spec.service)
            fields = fields_from_config(spec.config, spec.dto, spec.model, skip=spec.skip)
            fields = [self._link_field(f, spec, drafts, services) for f in fields]
            for extra in spec.extras:
                if extra.kind == 'total' and extra.child not in datasets:
                    continue                              # подчинённая таблица не собрана
                fields.append(self._extra_field(spec, extra, datasets, provider, services, sql_cache))
            backend = ServiceBackend(provider, spec.dto, [f for f in fields if not _is_program(f)])
            writer = None
            if drafts is not None:
                from app.dataset_app.drafts_writer import DraftsWriter
                writer = DraftsWriter(drafts.store, spec.entity)
                writers[name] = writer
            size = (sizes or {}).get(name) or spec.fetch_size or fetch_size
            dataset = DataSet(backend, fields=fields, name=name, writer=writer, order=spec.order,
                              fetch_mode=fetch_mode, fetch_size=size)
            if writer is not None:
                writer.attach(dataset)
            datasets[name] = dataset
        ordered = {name: datasets[name] for name in wanted}
        sources = {name: DataSource(ds) for name, ds in ordered.items()}
        links = [MasterDetailLink(sources[self.parent(name)], ordered[name],
                                  {self.parent_field(name): ordered[self.parent(name)].key_field})
                 for name in wanted if self.parent(name) in ordered]
        return BuiltTables(self, ordered, sources, links, drafts, writers)


def _display_of(target: TableSpec, link: Link) -> Callable[[Mapping[str, Any]], Any]:
    """
    Как показать запись цели ссылки: поле/функция из настройки или первое строковое
    видимое поле цели (иначе — id).

    Args:
        target: Описание таблицы цели.
        link: Связь.

    Returns:
        Функция от строки цели.

    Пример:
        >>> _display_of(doctors_spec, ref('doctor_id', 'doctors'))({'id': 5, 'name': 'Иванов'})
        'Иванов'
    """
    if callable(link.display):
        return link.display
    name = link.display
    if name is None:
        for field_name, cfg in target.config.items():
            annotation = getattr(target.dto, 'model_fields', {}).get(field_name)
            if (annotation is not None and 'str' in str(annotation.annotation)
                    and not cfg.get('hidden') and not cfg.get('virtual')):
                name = field_name
                break
    return (lambda row: row.get(name)) if name else (lambda row: row.get('id'))


def _is_program(definition: FieldDef) -> bool:
    """
    Поле, которое считает программа (его нет в строках сервиса).

    Args:
        definition: Описание поля.

    Returns:
        ``True`` — считает программа.

    Пример:
        >>> _is_program(FieldDef('mark', local=True))
        True
    """
    return (definition.local or definition.aggregate is not None
            or definition.calculated is not None or definition.lookup is not None)
