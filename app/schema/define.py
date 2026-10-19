# app/schema/define.py

"""
Одно описание таблицы → модель SQLAlchemy, DTO (Pydantic) и ``field_configs``.

Поле описывается один раз; из описания строятся столбец(ы) модели, связи, поле(я) DTO и
запись(и) настроек полей. Виды полей:

| Функция | Модель | DTO | ``field_configs`` |
|---|---|---|---|
| ``key`` | ``id`` Integer, первичный ключ | ``Optional[int] = None`` | ID: не правится, скрыт, не обновляется |
| ``column`` | столбец заданного типа | тип; обязательность = NOT NULL | ``title`` + свои ключи |
| ``note`` | ``<x>_id`` → общие заметки + связь ``<x>_note`` | ``<x>_text``, ``<x>_id`` | ``<x>_id`` (скрыт) и ``<x>_text`` (заметка) |
| ``fk`` | внешний ключ + связь к записи другой таблицы | ``int`` / ``Optional[int]`` | ``title`` + свои ключи |
| ``children`` | связь «один ко многим» (каскад) | ``Optional[List[ДочернийDTO]]`` | свои ключи |
| ``computed`` | — (вычисляет сервис: ``compute``/``sql_compute``) | заданный тип | свои ключи |
| ``timestamp`` | DateTime, по умолчанию «сейчас» | — | — |

Порядок полей описания — порядок ``field_configs`` (старые экраны показывают колонки в нём).
Для таблиц, уже существующих до описаний, порядок полей DTO и записей настроек можно задать
отдельно (``dto_order``, ``config_order``) — чтобы сгенерированное совпало с прежним один в
один.

Зависит только от SQLAlchemy, Pydantic и стандартной библиотеки — модуль моделей может его
импортировать без циклов.

Пример:
    >>> PRESCRIPTIONS = TableDef('prescriptions', 'Prescription', 'PrescriptionDTO', fields=(
    ...     key('ID назначения'),
    ...     fk('appointment_id', 'appointments', 'Appointment', title='Приём', nullable=False),
    ...     column('dosage', sa.String(100), 'Дозировка', nullable=False, required=True),
    ...     note('instruction', 'Инструкция'),
    ... ))
    >>> Prescription = PRESCRIPTIONS.build_model(Base)
    >>> PrescriptionDTO = PRESCRIPTIONS.build_dto()
    >>> PRESCRIPTION_CONFIG = PRESCRIPTIONS.build_config()
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Type

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy.orm import relationship

# Таблица и модель общих заметок (ссылки полей-заметок)
NOTES_TABLE = 'appointments_notes'
NOTES_MODEL = 'AppointmentNote'


def note_text(note: Any) -> Optional[str]:
    """
    Текст заметки (для ``compute`` полей-заметок).

    Args:
        note: Объект заметки или ``None``.

    Returns:
        Текст или ``None``.

    Пример:
        >>> note_text(None) is None
        True
    """
    return note.text if note else None


def _python_type(sql_type: Any) -> type:
    """
    Тип Python для DTO по типу столбца.

    Args:
        sql_type: Тип SQLAlchemy.

    Returns:
        Тип Python.

    Пример:
        >>> _python_type(sa.Date())
        <class 'datetime.date'>
    """
    for sa_type, py_type in ((sa.Boolean, bool), (sa.Integer, int), (sa.Float, float), (sa.Numeric, float),
                             (sa.DateTime, datetime.datetime), (sa.Date, datetime.date),
                             (sa.LargeBinary, bytes), (sa.String, str), (sa.Text, str)):
        if isinstance(sql_type, sa_type):
            return py_type
    return object


@dataclass(frozen=True)
class FieldSpec:
    """
    Описание поля (создаётся функциями ``key``, ``column``, ``note``, ``fk``, ``children``,
    ``computed``, ``timestamp``).

    Attributes:
        name: Имя (для заметки — основа: ``reason`` → ``reason_id``/``reason_text``).
        kind: Вид поля.
        title: Подпись (``field_configs['title']``).
        sql_type: Тип столбца.
        nullable: Столбец допускает пусто (иначе — NOT NULL и обязательное поле DTO).
        index: Имя индекса по столбцу.
        comment: Комментарий столбца в БД.
        default: Значение по умолчанию столбца (значение или функция).
        target: Для ``fk``/``children``: таблица; для ``fk`` — ещё и модель (``target_model``).
        target_model: Имя класса модели цели (для связи).
        relation: Имя связи на модели (``fk``: ``patient``; ``children``: ``photos``;
            ``note``: ``reason_note``).
        back: Имя обратной связи (``back_populates``).
        cascade: Каскад связи (``children``).
        dto: Включать в DTO.
        dto_type: Тип поля DTO (по умолчанию — по типу столбца).
        dto_desc: Описание поля DTO.
        config: Свои ключи ``field_configs`` (``None`` — записи в настройках нет).
        id_name: Для ``note`` — имя столбца-ссылки.
        text_name: Для ``note`` — имя поля текста.
        id_config: Для ``note`` — свои ключи записи ``<x>_id``.
        id_dto_desc: Для ``note`` — описание поля DTO ``<x>_id``.

    Пример:
        >>> key().name
        'id'
    """

    name: str
    kind: str
    title: str = ''
    sql_type: Any = None
    nullable: bool = True
    index: Optional[str] = None
    comment: Optional[str] = None
    default: Any = None
    target: Optional[str] = None
    target_model: Optional[str] = None
    relation: Optional[str] = None
    back: Optional[str] = None
    cascade: Optional[str] = None
    dto: bool = True
    dto_type: Any = None
    dto_desc: Optional[str] = None
    config: Optional[Mapping[str, Any]] = None
    id_name: Optional[str] = None
    text_name: Optional[str] = None
    id_config: Optional[Mapping[str, Any]] = None
    id_dto_desc: Optional[str] = None


def key(comment: Optional[str] = None, *, title: str = 'ID', dto_desc: Optional[str] = None,
        **ui: Any) -> FieldSpec:
    """
    Первичный ключ ``id`` (целое, автоувеличение).

    Args:
        comment: Комментарий столбца.
        title: Подпись.
        dto_desc: Описание поля DTO.
        **ui: Свои ключи ``field_configs`` (к стандартным: не правится, скрыт, не обновляется).

    Returns:
        ``FieldSpec``.

    Пример:
        >>> key('ID пациента', order=0).config['order']
        0
    """
    config = {'title': title, 'editable': False, 'hidden': True, 'updatable': False, **ui}
    return FieldSpec('id', 'key', title, sa.Integer(), nullable=False, comment=comment,
                     dto_type=Optional[int], dto_desc=dto_desc, config=config)


def column(name: str, sql_type: Any, title: str, *, nullable: bool = True, index: Optional[str] = None,
           comment: Optional[str] = None, default: Any = None, dto: bool = True, dto_type: Any = None,
           dto_desc: Optional[str] = None, config: bool = True, **ui: Any) -> FieldSpec:
    """
    Обычный столбец.

    Args:
        name: Имя.
        sql_type: Тип SQLAlchemy (``sa.String(50)``, ``sa.Date()``…).
        title: Подпись.
        nullable: Допускает пусто; ``False`` — NOT NULL и обязательное поле DTO.
        index: Имя индекса.
        comment: Комментарий столбца.
        default: Значение по умолчанию.
        dto: Включать в DTO.
        dto_type: Тип DTO (по умолчанию — по типу столбца; ``Optional``, если допускает пусто).
        dto_desc: Описание поля DTO.
        config: Делать запись в ``field_configs``.
        **ui: Свои ключи ``field_configs`` (``editable``, ``required``, ``widget_type``,
            ``order``, ``autocomplete``, ``input_mask``…).

    Returns:
        ``FieldSpec``.

    Пример:
        >>> column('phone', sa.String(20), 'Телефон', input_mask='+7 (999) 999-99-99').config['input_mask']
        '+7 (999) 999-99-99'
    """
    py_type = dto_type
    if py_type is None:
        base = _python_type(sql_type)
        py_type = Optional[base] if nullable else base
    return FieldSpec(name, 'column', title, sql_type, nullable, index, comment, default,
                     dto=dto, dto_type=py_type, dto_desc=dto_desc,
                     config={'title': title, **ui} if config else None)


def note(base: str, title: str, *, comment: Optional[str] = None, id_title: Optional[str] = None,
         relation: Optional[str] = None, id_name: Optional[str] = None, text_name: Optional[str] = None,
         dto_desc: Optional[str] = None, id_config: Optional[Mapping[str, Any]] = None,
         id_dto_desc: Optional[str] = None, **ui: Any) -> FieldSpec:
    """
    Поле-заметка: текст в общей таблице заметок (переиспользуемый), в записи — ссылка.

    Даёт: столбец ``<base>_id`` → ``appointments_notes.id``, связь ``<base>_note``, поля DTO
    ``<base>_text`` и ``<base>_id``, записи настроек ``<base>_id`` (скрыт, не обновляется) и
    ``<base>_text`` (заметка: правится, ``is_note``, ``compute`` — текст заметки).

    Args:
        base: Основа имён.
        title: Подпись текста.
        comment: Комментарий столбца ``<base>_id``.
        id_title: Подпись ``<base>_id`` (по умолчанию ``'ID …'``).
        relation: Имя связи (по умолчанию ``<base>_note``).
        id_name: Имя столбца (по умолчанию ``<base>_id``).
        text_name: Имя поля текста (по умолчанию ``<base>_text``).
        dto_desc: Описание поля DTO текста.
        id_config: Свои ключи записи ``<base>_id``.
        id_dto_desc: Описание поля DTO ``<base>_id``.
        **ui: Свои ключи записи текста (``order``…).

    Returns:
        ``FieldSpec``.

    Пример:
        >>> note('reason', 'Причина обращения').text_name
        'reason_text'
    """
    rel = relation or f'{base}_note'
    id_field = id_name or f'{base}_id'
    text_field = text_name or f'{base}_text'
    config = {'title': title, 'editable': True, 'virtual': True, 'widget_type': 'textarea',
              'source_attr': rel, 'compute': {'func': note_text, 'args': [rel]}, 'is_note': id_field, **ui}
    ident = {'title': id_title or f'ID {title.lower()}', 'hidden': True, 'updatable': False,
             **(id_config or {})}
    return FieldSpec(base, 'note', title, sa.Integer(), True, comment=comment, target=NOTES_TABLE,
                     target_model=NOTES_MODEL, relation=rel, dto_type=Optional[str], dto_desc=dto_desc,
                     config=config, id_name=id_field, text_name=text_field, id_config=ident,
                     id_dto_desc=id_dto_desc)


def fk(name: str, target: str, target_model: str, *, title: str = '', nullable: bool = True,
        relation: Optional[str] = None, back: Optional[str] = None, index: Optional[str] = None,
        comment: Optional[str] = None, dto_desc: Optional[str] = None, config: bool = True,
        **ui: Any) -> FieldSpec:
    """
    Внешний ключ на запись другой таблицы (родитель или ссылка) + связь к ней.

    Args:
        name: Имя столбца (``patient_id``).
        target: Таблица цели (``patients``).
        target_model: Имя класса модели цели (``Patient``).
        title: Подпись.
        nullable: Допускает пусто.
        relation: Имя связи на этой модели (``patient``; ``None`` — без связи).
        back: Имя обратной связи у цели (``appointments``).
        index: Имя индекса.
        comment: Комментарий столбца.
        dto_desc: Описание поля DTO.
        config: Делать запись в ``field_configs``.
        **ui: Свои ключи ``field_configs``.

    Returns:
        ``FieldSpec``.

    Пример:
        >>> fk('patient_id', 'patients', 'Patient', relation='patient', back='appointments').back
        'appointments'
    """
    return FieldSpec(name, 'fk', title, sa.Integer(), nullable, index, comment, target=target,
                     target_model=target_model, relation=relation, back=back,
                     dto_type=Optional[int] if nullable else int, dto_desc=dto_desc,
                     config={'title': title, **ui} if config else None)


def children(name: str, child_model: str, back: str, *, child_dto: Optional[str] = None,
             cascade: str = 'all, delete-orphan', dto: bool = True, dto_desc: Optional[str] = None,
             config: bool = True, title: str = '', **ui: Any) -> FieldSpec:
    """
    Подчинённые записи: связь «один ко многим» с каскадом (удаление владельца — удаление их).

    Args:
        name: Имя связи (``photos``).
        child_model: Класс модели подчинённых (``Photo``).
        back: Имя обратной связи у подчинённых (``appointment``).
        child_dto: Имя класса DTO подчинённых (для поля DTO ``Optional[List[…]]``).
        cascade: Каскад связи.
        dto: Включать в DTO.
        dto_desc: Описание поля DTO.
        config: Делать запись в ``field_configs``.
        title: Подпись.
        **ui: Свои ключи ``field_configs``.

    Returns:
        ``FieldSpec``.

    Пример:
        >>> children('photos', 'Photo', 'appointment', child_dto='PhotoDTO').cascade
        'all, delete-orphan'
    """
    dto_type = Optional[List[child_dto]] if (dto and child_dto) else None
    return FieldSpec(name, 'children', title, target_model=child_model, relation=name, back=back,
                     cascade=cascade, dto=dto and child_dto is not None, dto_type=dto_type,
                     dto_desc=dto_desc, config={'title': title, **ui} if config else None)


def computed(name: str, title: str, *, dto_type: Any = Optional[str], dto_desc: Optional[str] = None,
             **ui: Any) -> FieldSpec:
    """
    Поле, которое вычисляет сервис (``compute`` по связанным объектам, ``sql_compute``
    подзапросом) — в БД его нет.

    Args:
        name: Имя.
        title: Подпись.
        dto_type: Тип поля DTO.
        dto_desc: Описание поля DTO.
        **ui: Ключи ``field_configs`` (``virtual``, ``compute``, ``sql_compute``…).

    Returns:
        ``FieldSpec``.

    Пример:
        >>> computed('patient_name', 'Пациент', virtual=True).config['virtual']
        True
    """
    return FieldSpec(name, 'computed', title, dto_type=dto_type, dto_desc=dto_desc,
                     config={'title': title, **ui})


def timestamp(name: str = 'created_at', comment: Optional[str] = None) -> FieldSpec:
    """
    Время создания записи: DateTime, по умолчанию — «сейчас»; не в DTO и не в настройках.

    Args:
        name: Имя.
        comment: Комментарий столбца.

    Returns:
        ``FieldSpec``.

    Пример:
        >>> timestamp().default is datetime.datetime.now
        True
    """
    return FieldSpec(name, 'timestamp', sql_type=sa.DateTime(), nullable=True, comment=comment,
                     default=datetime.datetime.now, dto=False)


@dataclass(frozen=True)
class TableDef:
    """
    Описание таблицы: из него — модель, DTO, ``field_configs`` (и для экранов — ``app.tables``).

    Attributes:
        name: Имя таблицы.
        model_name: Имя класса модели.
        dto_name: Имя класса DTO.
        fields: Поля по порядку ``field_configs``.
        doc: Описание (документация класса модели и DTO).
        column_order: Порядок столбцов модели (по умолчанию — порядок полей).
        dto_order: Порядок полей DTO (по умолчанию — порядок полей).
        config_order: Порядок записей ``field_configs`` (по умолчанию — порядок полей).
        entity: Тип записи (черновики; по умолчанию — имя модели строчными).
        title: Заголовок для экрана.
        label: Одна запись (для сообщений).
        service: Имя функции ``app.dependencies``, возвращающей сервис таблицы (по умолчанию
            ``get_<entity>_service``).
        order: Сортировка по умолчанию (``'-date'``…).
        columns: Колонки таблицы экрана (пусто — видимые поля).
        form: Поля формы экрана (пусто — видимые поля, кроме ключа).
        extras: Свои столбцы (``app.schema.extras``: ``mark``, ``calc``, ``total``).
        links: Настройки связей-ссылок (``app.schema.extras.ref``).
        skip: Поля настроек, которые наборам данных не нужны.
        parent: Родительская таблица (если внешних ключей на таблицы реестра несколько).
        parent_field: Поле связи с родителем (вместе с ``parent``).
        fetch_size: Свой размер порции загрузки.

    Пример:
        >>> PATIENTS.build_config()['last_name']['title']
        'Фамилия'
    """

    name: str
    model_name: str
    dto_name: str
    fields: Tuple[FieldSpec, ...]
    doc: str = ''
    column_order: Tuple[str, ...] = ()
    dto_order: Tuple[str, ...] = ()
    config_order: Tuple[str, ...] = ()
    entity: str = ''
    title: str = ''
    label: str = ''
    service: str = ''
    order: Tuple[str, ...] = ()
    columns: Tuple[str, ...] = ()
    form: Tuple[str, ...] = ()
    extras: Tuple[Any, ...] = ()
    links: Tuple[Any, ...] = ()
    skip: Tuple[str, ...] = ()
    parent: Optional[str] = None
    parent_field: Optional[str] = None
    fetch_size: Optional[int] = None

    def __post_init__(self) -> None:
        """
        Поля — кортежем; тип записи по умолчанию; проверка повторов имён.

        Returns:
            None

        Raises:
            ValueError: Имя поля/столбца повторяется.

        Пример:
            >>> TableDef('t', 'T', 'TDTO', (key(), key()))
            Traceback (most recent call last):
            ValueError: таблица t: имя 'id' повторяется
        """
        object.__setattr__(self, 'fields', tuple(self.fields))
        if not self.entity:
            object.__setattr__(self, 'entity', self.model_name.lower())
        if not self.service:
            object.__setattr__(self, 'service', f'get_{self.entity}_service')
        seen: set = set()
        for spec in self.fields:
            for name in self._names(spec):
                if name in seen:
                    raise ValueError(f"таблица {self.name}: имя {name!r} повторяется")
                seen.add(name)

    @staticmethod
    def _names(spec: FieldSpec) -> List[str]:
        """
        Имена, которые поле занимает (у заметки — два).

        Args:
            spec: Поле.

        Returns:
            Имена.

        Пример:
            >>> TableDef._names(note('reason', 'Причина'))
            ['reason_id', 'reason_text']
        """
        return [spec.id_name, spec.text_name] if spec.kind == 'note' else [spec.name]

    @staticmethod
    def _ordered(items: Dict[str, Any], order: Sequence[str]) -> Dict[str, Any]:
        """
        Словарь в заданном порядке (не названные — в конце, как были).

        Args:
            items: Словарь.
            order: Порядок ключей.

        Returns:
            Новый словарь.

        Raises:
            ValueError: В порядке назван неизвестный ключ.

        Пример:
            >>> TableDef._ordered({'a': 1, 'b': 2}, ['b'])
            {'b': 2, 'a': 1}
        """
        unknown = [k for k in order if k not in items]
        if unknown:
            raise ValueError(f"в порядке неизвестные имена: {', '.join(unknown)}")
        result = {k: items[k] for k in order}
        result.update({k: v for k, v in items.items() if k not in result})
        return result

    # ------------------------------------------------------------------ модель

    def _columns(self) -> Dict[str, sa.Column]:
        """
        Столбцы модели по порядку.

        Returns:
            «имя → Column».

        Пример:
            >>> list(PATIENTS._columns())[:2]
            ['id', 'first_name']
        """
        result: Dict[str, sa.Column] = {}
        for spec in self.fields:
            if spec.kind == 'key':
                result['id'] = sa.Column(sa.Integer, primary_key=True, autoincrement=True, comment=spec.comment)
            elif spec.kind in ('column', 'timestamp'):
                result[spec.name] = sa.Column(spec.sql_type, nullable=spec.nullable, default=spec.default,
                                              comment=spec.comment)
            elif spec.kind == 'fk':
                result[spec.name] = sa.Column(sa.Integer, sa.ForeignKey(f'{spec.target}.id'),
                                              nullable=spec.nullable, comment=spec.comment)
            elif spec.kind == 'note':
                result[spec.id_name] = sa.Column(sa.Integer, sa.ForeignKey(f'{NOTES_TABLE}.id'),
                                                 nullable=True, comment=spec.comment)
        return self._ordered(result, self.column_order)

    def build_model(self, base: Any, namespace: Optional[Mapping[str, Any]] = None) -> type:
        """
        Класс модели SQLAlchemy на базовом классе ``base``.

        Args:
            base: Декларативная база (``Base`` приложения или своя — для проверок).
            namespace: Свои атрибуты класса (методы).

        Returns:
            Класс модели.

        Пример:
            >>> Patient = PATIENTS.build_model(Base)
            >>> Patient.__tablename__
            'patients'
        """
        attrs: Dict[str, Any] = {'__tablename__': self.name, '__doc__': self.doc or self.model_name,
                                 '__repr__': _model_repr}
        columns = self._columns()
        attrs.update(columns)
        indexes = []
        for spec in self.fields:
            column_name = spec.id_name if spec.kind == 'note' else spec.name
            if spec.index:
                indexes.append(sa.Index(spec.index, column_name))
            if spec.kind == 'note':
                attrs[spec.relation] = relationship(NOTES_MODEL, foreign_keys=[columns[spec.id_name]])
            elif spec.kind == 'fk' and spec.relation:
                attrs[spec.relation] = relationship(spec.target_model, back_populates=spec.back)
            elif spec.kind == 'children':
                attrs[spec.relation] = relationship(spec.target_model, back_populates=spec.back,
                                                    cascade=spec.cascade)
        if indexes:
            attrs['__table_args__'] = tuple(indexes)
        attrs.update(dict(namespace or {}))
        return type(self.model_name, (base,), attrs)

    # ------------------------------------------------------------------ DTO

    def dto_fields(self) -> Dict[str, Tuple[Any, Any]]:
        """
        Поля DTO для ``pydantic.create_model``: «имя → (тип, Field)».

        Returns:
            Словарь в порядке DTO.

        Пример:
            >>> list(PHOTOS.dto_fields())
            ['id', 'appointment_id', 'file_path', 'description']
        """
        result: Dict[str, Tuple[Any, Any]] = {}
        for spec in self.fields:
            if not spec.dto:
                continue
            if spec.kind == 'note':
                result[spec.text_name] = (Optional[str], Field(None, description=spec.dto_desc))
                result[spec.id_name] = (Optional[int], Field(None, description=spec.id_dto_desc))
                continue
            annotation = spec.dto_type
            required = spec.kind in ('column', 'fk') and not spec.nullable
            default = ... if required else None
            result[spec.name] = (annotation, Field(default, description=spec.dto_desc))
        return self._ordered(result, self.dto_order)

    def build_dto(self, namespace: Optional[Mapping[str, Any]] = None) -> Type[BaseModel]:
        """
        Класс DTO (``from_attributes``). Ссылки на другие DTO по имени (``List['PhotoDTO']``)
        разрешаются ``rebuild_dtos`` после создания всех.

        Args:
            namespace: Не используется (зарезервировано для своих методов DTO).

        Returns:
            Класс DTO.

        Пример:
            >>> PatientDTO = PATIENTS.build_dto(); PatientDTO(last_name='П', first_name='И').id is None
            True
        """
        dto = create_model(self.dto_name, __config__=ConfigDict(from_attributes=True),
                           __doc__=self.doc or self.dto_name, **self.dto_fields())
        return dto

    # ------------------------------------------------------------------ настройки полей

    def build_config(self) -> Dict[str, Dict[str, Any]]:
        """
        ``field_configs`` таблицы.

        Returns:
            «поле → настройки» в порядке ``config_order`` (или полей).

        Пример:
            >>> PHOTOS.build_config()['description']['widget_type']
            'textarea'
        """
        result: Dict[str, Dict[str, Any]] = {}
        for spec in self.fields:
            if spec.kind == 'note':
                result[spec.id_name] = dict(spec.id_config or {})
                result[spec.text_name] = _copy_config(spec.config)
            elif spec.config is not None:
                result[spec.name] = _copy_config(spec.config)
        return self._ordered(result, self.config_order)


def _copy_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Копия настроек поля (вложенные словари и списки — тоже, функции — как есть): у каждой
    сборки свой изменяемый словарь.

    Args:
        config: Настройки.

    Returns:
        Копия.

    Пример:
        >>> _copy_config({'compute': {'args': ['a']}})
        {'compute': {'args': ['a']}}
    """
    result: Dict[str, Any] = {}
    for k, v in config.items():
        if isinstance(v, dict):
            result[k] = _copy_config(v)
        elif isinstance(v, list):
            result[k] = list(v)
        else:
            result[k] = v
    return result


def _model_repr(self: Any) -> str:
    """
    Строка модели: класс и значения столбцов (без связей — не подгружать лишнего).

    Args:
        self: Объект модели.

    Returns:
        Строка вида ``<Patient(id=1, last_name='Петров', …)>``.

    Пример:
        >>> repr(Patient(id=1, last_name='П'))
        "<Patient(id=1, first_name=None, ...)>"
    """
    try:
        values = ', '.join(f"{c.name}={getattr(self, c.name, None)!r}" for c in self.__table__.columns)
    except Exception:                         # объект в неполном состоянии (отсоединён, удалён)
        values = '…'
    return f"<{type(self).__name__}({values})>"


def rebuild_dtos(*dtos: Type[BaseModel]) -> None:
    """
    Разрешает ссылки DTO друг на друга по имени (``Optional[List['PhotoDTO']]``).

    Args:
        *dtos: Классы DTO.

    Returns:
        None

    Пример:
        >>> rebuild_dtos(PatientDTO, AppointmentDTO, PhotoDTO)
    """
    namespace = {dto.__name__: dto for dto in dtos}
    for dto in dtos:
        dto.model_rebuild(_types_namespace=namespace)


__all__ = ['FieldSpec', 'TableDef', 'children', 'column', 'computed', 'fk', 'key', 'note', 'note_text',
           'rebuild_dtos', 'timestamp', 'NOTES_TABLE', 'NOTES_MODEL']
