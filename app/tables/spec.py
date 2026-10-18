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

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.dataset_app.fields import fields_from_config, references_of
from app.dataset_app.service_backend import ServiceBackend
from app.utils.dataset import (
    AggFunc, AggregateDef, Condition, DataSet, DataSource, FetchMode, FieldDef, FieldKind,
    MasterDetailLink,
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
    aggregate: AggFunc = AggFunc.COUNT
    field: Optional[str] = None
    where: Tuple[Condition, ...] = ()
    visible: bool = True
    display: Optional[Callable[[Any], str]] = None
    widget: Optional[str] = None


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


def total(name: str, label: str, child: str, func: AggFunc = AggFunc.COUNT,
          field: Optional[str] = None, where: Sequence[Condition] = (), *,
          kind: Optional[FieldKind] = None, display: Optional[Callable[[Any], str]] = None) -> Extra:
    """
    Итог по подчинённой таблице реестра, который считает программа (число фото у приёма,
    сумма чеков у пациента).

    Args:
        name: Имя.
        label: Подпись.
        child: Подчинённая таблица (по имени в реестре).
        func: Вид итога.
        field: Поле подчинённой строки (для суммы/мин/макс/среднего).
        where: Условия на подчинённые строки.
        kind: Тип значения (по умолчанию: число — целое, остальное — без проверки).
        display: Показ текстом.

    Returns:
        ``Extra``.

    Пример:
        >>> total('photo_count', 'Фото', 'photos').aggregate
        <AggFunc.COUNT: 'count'>
    """
    if kind is None:
        kind = FieldKind.INTEGER if AggFunc(func) is AggFunc.COUNT else FieldKind.ANY
    return Extra(name, label, 'total', kind, child=child, aggregate=AggFunc(func), field=field,
                 where=tuple(where), display=display)


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
        candidates = [(t, f) for f, t in references_of(spec.model).items() if t in self._specs and t != spec.name]
        if len(candidates) > 1:
            raise SpecError(f"у {spec.name} несколько ссылок на таблицы реестра "
                            f"({', '.join(f for _, f in candidates)}) — укажите parent")
        return candidates[0] if candidates else (None, None)

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

    def drafts_schema(self):
        """
        Схема черновиков (дерево типов записей) — из описаний.

        Returns:
            ``TreeSchema``.

        Пример:
            >>> CLINIC.drafts_schema().depth('photo')
            2
        """
        from app.utils.drafts import EntityType, TreeSchema
        types = []
        for name in self.names():
            spec, parent = self._specs[name], self.parent(name)
            if parent is None:
                types.append(EntityType(spec.entity, label=spec.label))
            else:
                types.append(EntityType(spec.entity, parent=self._specs[parent].entity,
                                        parent_field=self.parent_field(name), label=spec.label))
        return TreeSchema(types)

    def service_adapter(self, transaction_factory: Optional[Callable[[], Any]] = None,
                        services: Optional[Mapping[str, Callable[[], Any]]] = None):
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

    def _extra_field(self, spec: TableSpec, extra: Extra, datasets: Mapping[str, DataSet],
                     service: Callable[[], Any]) -> FieldDef:
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
        for name in reversed(wanted):                     # подчинённые раньше: итоги ссылаются на них
            spec = self._specs[name]
            provider = services.get(spec.entity, spec.service)
            fields = fields_from_config(spec.config, spec.dto, spec.model)
            for extra in spec.extras:
                if extra.kind == 'total' and extra.child not in datasets:
                    continue                              # подчинённая таблица не собрана
                fields.append(self._extra_field(spec, extra, datasets, provider))
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
