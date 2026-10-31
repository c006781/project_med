# app/dataset_app/fields.py

"""
Описания полей наборов данных (``FieldDef``) из настроек полей приложения (``field_configs``).

Поля второй раз не описываются: подпись, видимость, правка, обязательность берутся из
``field_configs``, тип — из DTO, ссылка на родительскую таблицу — из внешних ключей
модели SQLAlchemy (кроме ссылок на общие заметки).

| field_configs | FieldDef |
|---|---|
| ``title`` | ``label`` |
| ``hidden`` | ``visible = not hidden`` |
| ``editable`` (по умолчанию да) | ``read_only = not editable`` |
| ``required`` | ``required`` |
| ``updatable: False`` (id, ссылки на заметки) | ``persistent=False`` — не пишется |
| ``virtual`` без ``is_note`` (ФИО у приёма, число фото) | ``persistent=False`` — значение даёт сервис |
| ``virtual`` с ``is_note`` (тексты заметок) | обычное поле: сервис сам сохраняет заметку |
| ``widget_type: 'textarea'`` | ``kind=TEXT`` |
| вложенные списки DTO (``photos``) | пропускаются — это подчинённый набор |
| весь словарь настроек | ``extra['config']`` (маска ввода, автодополнение…) |

Пример:
    >>> from app.dto.field_configs import APPOINTMENT_CONFIG
    >>> from app.dto.dto_all import AppointmentDTO
    >>> from app.database.database_shema.clinic import Appointment
    >>> fields = fields_from_config(APPOINTMENT_CONFIG, AppointmentDTO, Appointment)
    >>> {f.name: f.references for f in fields if f.references}
    {'patient_id': 'patients'}
"""

from __future__ import annotations

import datetime
import typing
from typing import Any, Dict, Iterable, List, Mapping, Optional, Type

from app.utils.dataset import FieldDef, FieldKind

# Таблица общих заметок: ссылки на неё — не родитель записи (заметка — поле записи)
NOTES_TABLE = 'appointments_notes'

_KINDS = {
    bool: FieldKind.BOOLEAN,      # bool раньше int: bool — подкласс int
    int: FieldKind.INTEGER,
    float: FieldKind.FLOAT,
    str: FieldKind.STRING,
    datetime.datetime: FieldKind.DATETIME,
    datetime.date: FieldKind.DATE,
    bytes: FieldKind.BLOB,
}


def _date_text(value: Any) -> str:
    """
    Дата так, как её показывает программа: ``дд.мм.гггг`` (F3).

    Args:
        value: Дата (не дата — как есть).

    Returns:
        Текст.

    Пример:
        >>> _date_text(datetime.date(1980, 1, 2))
        '02.01.1980'
    """
    return value.strftime('%d.%m.%Y') if isinstance(value, datetime.date) else str(value)


def _datetime_text(value: Any) -> str:
    """
    Дата и время: ``дд.мм.гггг чч:мм``.

    Args:
        value: Дата-время.

    Returns:
        Текст.

    Пример:
        >>> _datetime_text(datetime.datetime(2026, 10, 18, 9, 5))
        '18.10.2026 09:05'
    """
    return value.strftime('%d.%m.%Y %H:%M') if isinstance(value, datetime.datetime) else str(value)


# Показ значений по типу (F3, 2026-10-18: даты были в виде 1980-01-02, а в остальной
# программе — 02.01.1980)
_DISPLAY = {FieldKind.DATE: _date_text, FieldKind.DATETIME: _datetime_text}


def _unwrap(annotation: Any) -> Any:
    """
    Тип без ``Optional[...]``.

    Args:
        annotation: Аннотация поля DTO.

    Returns:
        Внутренний тип (``Optional[int]`` → ``int``).

    Пример:
        >>> _unwrap(typing.Optional[int])
        <class 'int'>
    """
    if typing.get_origin(annotation) is typing.Union:
        inner = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(inner) == 1:
            return inner[0]
    return annotation


def _is_collection(annotation: Any) -> bool:
    """
    Поле DTO — вложенный список (подчинённые записи, не поле строки).

    Args:
        annotation: Аннотация.

    Returns:
        ``True`` — список/кортеж/множество.

    Пример:
        >>> _is_collection(typing.Optional[typing.List[int]])
        True
    """
    origin = typing.get_origin(_unwrap(annotation))
    return origin in (list, tuple, set, frozenset)


def kind_of(annotation: Any, config: Mapping[str, Any]) -> FieldKind:
    """
    Тип поля: ``textarea`` → TEXT; иначе по аннотации DTO; неизвестное → ANY.

    Args:
        annotation: Аннотация поля DTO (``None`` — нет в DTO).
        config: Настройки поля.

    Returns:
        ``FieldKind``.

    Пример:
        >>> kind_of(typing.Optional[datetime.date], {})
        <FieldKind.DATE: 'date'>
    """
    if config.get('widget_type') == 'textarea':
        return FieldKind.TEXT
    inner = _unwrap(annotation)
    for python_type, kind in _KINDS.items():
        if inner is python_type:
            return kind
    return FieldKind.ANY


def foreign_keys_of(model: Any) -> Dict[str, str]: # все внешние ключи модели, в том числе на заметки
    """
    Возвращает все поля модели с внешним ключом и таблицы, на которые они ссылаются.

    В отличие от :func:`references_of` ссылки на общие заметки не отбрасываются: их
    использует реестр таблиц (``app/tables``), чтобы описать заметки как ссылки на общие
    данные (черновики не дают удалить заметку, на которую ссылаются записи).

    Args:
        model : (type/None) Класс модели SQLAlchemy; None — ссылок нет.

    Returns:
        (dict) «столбец → таблица» в порядке столбцов модели.

    Example:
        >>> from app.database.database_shema.clinic import Patient
        >>> foreign_keys_of(
        ...     Patient,   # модель пациента
        ... )
        {'description_id': 'appointments_notes', 'comment_id': 'appointments_notes'}
    """
    if model is None:
        return {}
    result: Dict[str, str] = {}
    for column in model.__table__.columns:
        for fk in column.foreign_keys:
            result[column.name] = fk.column.table.name
    return result


def references_of(model: Any) -> Dict[str, str]: # ссылки на таблицы-родители (без заметок)
    """
    Возвращает поля-ссылки модели на родительские таблицы (внешние ключи, кроме заметок).

    Args:
        model : (type/None) Класс модели SQLAlchemy; None — ссылок нет.

    Returns:
        (dict) «столбец → таблица».

    Example:
        >>> from app.database.database_shema.clinic import Photo
        >>> references_of(
        ...     Photo,     # модель фото
        ... )
        {'appointment_id': 'appointments'}
    """
    # if model is None:
    #     return {}
    # result: Dict[str, str] = {}
    # for column in model.__table__.columns:
    #     for fk in column.foreign_keys:
    #         table = fk.column.table.name
    #         if table != NOTES_TABLE:
    #             result[column.name] = table
    # return result
    # ↑ до 2026-10-31 (Ф1.3.4): обход внешних ключей был здесь; теперь он общий с
    #   foreign_keys_of (реестру таблиц нужны и ключи на заметки), поведение то же.
    return {
        name: table
        for name, table in foreign_keys_of(model).items()
        if table != NOTES_TABLE                 # заметка — поле записи, а не её родитель
    }


def fields_from_config(config: Mapping[str, Mapping[str, Any]], dto_class: Optional[Type[Any]] = None,
                       model: Any = None, *, key_field: str = 'id',
                       skip: Iterable[str] = ()) -> List[FieldDef]:
    """
    ``FieldDef`` всех полей настроек (порядок — по ``order``, затем как в настройках).

    Args:
        config: Настройки полей (``PATIENT_CONFIG`` …).
        dto_class: Класс DTO (тип полей; вложенные списки пропускаются).
        model: Модель SQLAlchemy (ссылки на родителей).
        key_field: Поле-ключ.
        skip: Поля, которые не нужны в наборе.

    Returns:
        Список ``FieldDef``.

    Пример:
        >>> from app.dto.field_configs import PATIENT_CONFIG
        >>> [f.name for f in fields_from_config(PATIENT_CONFIG)][:3]
        ['id', 'last_name', 'first_name']
    """
    annotations = {}
    if dto_class is not None and hasattr(dto_class, 'model_fields'):
        annotations = {name: info.annotation for name, info in dto_class.model_fields.items()}
    refs = references_of(model)
    skipped = set(skip)
    ordered = sorted(enumerate(config.items()), key=lambda item: (item[1][1].get('order', 10_000), item[0]))
    result: List[FieldDef] = []
    for _, (name, cfg) in ordered:
        if name in skipped or _is_collection(annotations.get(name)):
            continue
        is_note = bool(cfg.get('is_note'))
        computed_by_service = bool(cfg.get('virtual')) and not is_note
        persistent = name != key_field and cfg.get('updatable', True) is not False and not computed_by_service
        kind = kind_of(annotations.get(name), cfg)
        result.append(FieldDef(
            name=name,
            label=cfg.get('title') or name,
            kind=kind,
            display=_DISPLAY.get(kind),
            required=bool(cfg.get('required')) and name != key_field,
            read_only=name == key_field or not cfg.get('editable', True) or computed_by_service,
            visible=not cfg.get('hidden', False),
            references=refs.get(name),
            persistent=persistent,
            extra={'config': dict(cfg)},
        ))
    return result
