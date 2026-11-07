# app/schema/define.py

"""
Одно описание таблицы → модель SQLAlchemy, DTO (Pydantic) и ``field_configs``.

Поле описывается один раз; из описания строятся столбец(ы) модели, связи, поле(я) DTO и
запись(и) настроек полей. Виды полей:

| Функция | Модель | DTO | ``field_configs`` |
|---|---|---|---|
| ``key`` | ``id`` Integer, первичный ключ | ``Optional[int] = None`` | ID: не правится, скрыт, не обновляется |
| ``column`` | столбец заданного типа (может быть ключом и ссылаться на столбец другой таблицы) | тип; обязательность = NOT NULL | ``title`` + свои ключи |
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

Хранение и события таблицы (Ф1.6.7г, 2026-11-01): ``TableDef(keep=KEEP_USED)`` — строки
«только используемые» (неиспользуемые убирает сборщик мусора слоя базы); ``events=(on(место,
'действие', ...), ...)`` — действия по имени на местах «перед / после добавления, изменения,
удаления, перед коммитом, после коммита / отката». Исполняет их слой базы
(``app/database/table_events.py``) — модель знает своё описание (``__table_def__``).

Встроенные триггеры SQLite (Ф1.6.7д, 2026-11-07): ``triggers=(trigger('имя', 'место', 'SQL'), ...)``
— правила только внутри данных: срабатывают и при сыром SQL, и при правке сторонней программой;
вне базы ничего не умеют. Создаёт их миграция; модель несёт их текст в ``Table.info`` — так их
видят сравнение с базой и генератор миграций (``app/database/sqlite_triggers.py``).

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
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Type, Union

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy.orm import relationship

# Таблица и модель общих заметок (ссылки полей-заметок)
NOTES_TABLE = 'appointments_notes'
NOTES_MODEL = 'AppointmentNote'

# Хранение строк таблицы (TableDef.keep, Ф1.6.7г): «хранить всегда» — строки удаляет только
# явное удаление; «только используемые» — строку, на которую в транзакции убрали последнюю
# ссылку, удаляет сборщик мусора слоя базы (app/database/table_events.py) перед коммитом.
# Автоматически не определяется: по устройству таблиц заметку не отличить от справочника.
KEEP_ALWAYS : str = 'always'   # хранить всегда (по умолчанию)
KEEP_USED   : str = 'used'     # только используемые
KEEP_MODES  : Tuple[str, ...] = (KEEP_ALWAYS, KEEP_USED)

# Места событий таблицы (как события объектов RAD Studio): строки — внутри сброса в базу
# (flush), транзакции — вокруг коммита / отката. Действия подключаются по имени (on()).
ROW_EVENTS : Tuple[str, ...] = (
    'before_insert', 'after_insert',     # добавление строки
    'before_update', 'after_update',     # изменение строки
    'before_delete', 'after_delete',     # удаление строки
)
TRANSACTION_EVENTS : Tuple[str, ...] = (
    'before_commit',                     # перед коммитом (можно менять данные)
    'after_commit',                      # после коммита (данные уже в базе)
    'after_rollback',                    # после отката
)
TABLE_EVENTS : Tuple[str, ...] = ROW_EVENTS + TRANSACTION_EVENTS

# Встроенные триггеры SQLite (Ф1.6.7д): ключ Table.info — «имя триггера → текст CREATE TRIGGER».
# Через Table.info текст доходит и до копий схемы (to_metadata), и до схемы, собранной из базы.
TRIGGERS_INFO : str = 'sqlite_triggers'
_TRIGGER_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')   # имя триггера и столбца UPDATE OF


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
        cascade: Каскад связи (``children``; ``None`` — каскад SQLAlchemy по умолчанию).
        foreign_keys: Явный внешний ключ связи строкой SQLAlchemy (``children``:
            ``'[Appointment.note_id]'``; ``None`` — определяется сам).
        dto: Включать в DTO.
        dto_type: Тип поля DTO (по умолчанию — по типу столбца).
        dto_desc: Описание поля DTO.
        config: Свои ключи ``field_configs`` (``None`` — записи в настройках нет).
        id_name: Для ``note`` — имя столбца-ссылки.
        text_name: Для ``note`` — имя поля текста.
        id_config: Для ``note`` — свои ключи записи ``<x>_id``.
        id_dto_desc: Для ``note`` — описание поля DTO ``<x>_id``.
        primary_key: Для ``column`` — столбец первичный ключ таблицы (вместо ``key``).
        references: Для ``column`` — внешний ключ на столбец другой таблицы
            (``'photo_files.file_path'``); связь — ``relation`` к ``target_model``.

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
    foreign_keys: Optional[str] = None
    dto: bool = True
    dto_type: Any = None
    dto_desc: Optional[str] = None
    config: Optional[Mapping[str, Any]] = None
    id_name: Optional[str] = None
    text_name: Optional[str] = None
    id_config: Optional[Mapping[str, Any]] = None
    id_dto_desc: Optional[str] = None
    primary_key : bool = False              # column: первичный ключ (Ф1.6.7б)
    references  : Optional[str] = None      # column: внешний ключ 'таблица.столбец' (Ф1.6.7б)


@dataclass(frozen=True)
class EventSpec:
    """
    Подключение действий к месту события таблицы (создаётся функцией :func:`on`).

    Attributes:
        event   : (str) Место события (одно из ``TABLE_EVENTS``).
        actions : (Tuple[str, ...]) Имена действий из реестра слоя базы — по порядку
            выполнения.

    Example:
        >>> on(
        ...     'after_delete',        # после удаления строки
        ...     'delete_photo_file',   # действие
        ... ).actions
        ('delete_photo_file',)
    """

    event   : str
    actions : Tuple[str, ...]


def on(
    event    : str,   # место события (TABLE_EVENTS)
    *actions : str,   # имена действий по порядку выполнения
) -> EventSpec: # подключение действий к месту события
    """
    Подключает действия к месту события таблицы — для ``TableDef(events=(...))``.

    Действия — по имени: описание таблиц модули с действиями не импортирует (слой описаний
    ниже слоя базы, К6); имена сверяются с реестром действий при открытии базы
    (``app/database/table_events.py``). К одному месту можно подключить несколько
    действий — они выполняются в порядке перечисления (здесь и в следующих ``on`` того же
    места).

    Args:
        event    : (str) Место события: ``before_insert``, ``after_insert``,
            ``before_update``, ``after_update``, ``before_delete``, ``after_delete``,
            ``before_commit``, ``after_commit``, ``after_rollback``.
        *actions : (str) Имена действий (непустые строки, без повторов в одном ``on``).

    Returns:
        (EventSpec) Подключение.

    Raises:
        ValueError: Неизвестное место, нет действий, имя действия не строка или пустое,
            имя повторяется.

    Example:
        >>> on(
        ...     'before_delete',   # перед удалением строки
        ...     'forbid_if_paid',  # первое действие
        ...     'log_removal',     # второе действие
        ... ).event
        'before_delete'
    """
    if event not in TABLE_EVENTS:
        raise ValueError(f"неизвестное место события {event!r}; есть: {', '.join(TABLE_EVENTS)}")
    if not actions:
        raise ValueError(f"событие {event!r}: не названо ни одного действия")
    for name in actions:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"событие {event!r}: имя действия должно быть непустой строкой, а не {name!r}")
    if len(set(actions)) != len(actions):
        raise ValueError(f"событие {event!r}: имя действия повторяется ({', '.join(actions)})")
    return EventSpec(
        event,              # место
        tuple(actions),     # действия по порядку
    )


@dataclass(frozen=True)
class TriggerSpec:
    """
    Встроенный триггер SQLite в описании таблицы (создаётся функцией :func:`trigger`).

    Attributes:
        name  : (str) Имя триггера (единое пространство имён на всю базу).
        event : (str) Место (одно из ``ROW_EVENTS``).
        body  : (str) Команды между ``BEGIN`` и ``END``.
        when  : (str/None) Условие ``WHEN``; None — без условия.
        of    : (Tuple[str, ...]) Столбцы ``UPDATE OF``; пусто — любое изменение строки.

    Example:
        >>> trigger(
        ...     'trg_no_delete',                            # имя
        ...     'before_delete',                            # перед удалением
        ...     "SELECT RAISE(ABORT, 'удалять нельзя');",   # команды
        ... ).event
        'before_delete'
    """

    name  : str
    event : str
    body  : str
    when  : Optional[str] = None
    of    : Tuple[str, ...] = ()

    def create_sql(
        self,
        table : str,   # таблица триггера
    ) -> str: # текст CREATE TRIGGER
        """
        Возвращает текст ``CREATE TRIGGER`` для таблицы — его выполняет миграция и с ним
        сравнивается текст в базе.

        Args:
            table : (str) Имя таблицы.

        Returns:
            (str) Команда SQL без завершающей точки с запятой.

        Example:
            >>> trigger(
            ...     'trg_a',                # имя
            ...     'after_update',         # после изменения
            ...     'SELECT 1',             # команды
            ...     of  =   ('phone',),     # столбец
            ... ).create_sql(
            ...     'patients',             # таблица
            ... ).splitlines()[0]
            'CREATE TRIGGER "trg_a" AFTER UPDATE OF "phone" ON "patients"'
        """
        timing, operation = self.event.split('_')
        columns = ''
        if self.of: # только изменения названных столбцов
            columns = ' OF ' + ', '.join(f'"{name}"' for name in self.of)
        when = f"\nWHEN {self.when.strip()}" if self.when else ''
        body = self.body.strip().rstrip(';').rstrip()
        return (
            f'CREATE TRIGGER "{self.name}" {timing.upper()} {operation.upper()}{columns} ON "{table}"'
            f"{when}\nBEGIN\n{body};\nEND"
        )


def trigger(
    name  : str,                                  # имя триггера
    event : str,                                  # место (ROW_EVENTS)
    body  : str,                                  # команды между BEGIN и END
    *,
    when  : Optional[str] = None,                 # условие WHEN
    of    : Union[str, Sequence[str]] = (),       # столбцы UPDATE OF
) -> TriggerSpec: # встроенный триггер SQLite для TableDef(triggers=(...))
    """
    Описывает встроенный триггер SQLite — для ``TableDef(triggers=(...))``.

    Для правил только внутри данных: срабатывает на любое изменение строки — и через ORM, и
    сырым SQL, и из сторонней программы. Вне базы ничего не умеет (файлы, журнал программы —
    это события таблиц, :func:`on`). Создаёт триггер миграция; появление, изменение и удаление
    триггера в описании видит генератор миграций. Место — как у событий таблицы:
    ``before_insert``, ``after_insert``, ``before_update``, ``after_update``, ``before_delete``,
    ``after_delete``.

    Здесь проверяется только форма; существование таблиц и столбцов в ``body`` и ``when``,
    повтор имени на другой таблице — при открытии базы (``migrate.check_trigger_definitions``):
    SQLite принимает ``CREATE TRIGGER`` с опечаткой и упал бы только при срабатывании.

    Note:
        ORM о работе триггера не знает. Объекты, уже загруженные в сессию, после срабатывания
        устаревают до ``session.refresh(объект)`` / ``session.expire(объект)`` или до конца
        транзакции; события таблиц и сборщик мусора изменённых триггером строк не видят —
        ссылку, снятую триггером, сборщик не заметит (её найдёт полная проверка ``find_unused``).
        Триггер ``BEFORE`` не должен менять обрабатываемую строку (в SQLite поведение не
        определено). ``RAISE(IGNORE)`` не использовать: ORM ждёт, что строка изменилась, и
        упадёт с ``StaleDataError``. Функции ``lower`` / ``upper`` понимают кириллицу только в
        соединениях программы: у сторонней программы и в миграции они встроенные SQLite —
        правило на них работало бы по-разному.

    Args:
        name  : (str) Имя: латиница, цифры, ``_``; не с ``sqlite_`` (зарезервировано SQLite).
            Единое на всю базу, а не на таблицу.
        event : (str) Место срабатывания (``ROW_EVENTS``).
        body  : (str) Команды между ``BEGIN`` и ``END``; в них доступны ``NEW.`` / ``OLD.``.
            Запрет — ``SELECT RAISE(ABORT, 'текст')``: текст дойдёт до ``DbIntegrityError``.
        when  : (str/None) Условие ``WHEN``; None — без условия.
        of    : (str/Sequence[str]) Столбцы ``UPDATE OF`` (только для ``*_update``); пусто —
            любое изменение строки. Что столбцы есть в таблице, проверяет ``TableDef``.

    Returns:
        (TriggerSpec) Описание триггера.

    Raises:
        ValueError: Плохое имя триггера или столбца, неизвестное место, пустые команды или
            условие, ``of`` не у изменения, столбец в ``of`` повторяется.

    Example:
        >>> trigger(
        ...     'trg_photo_no_empty_path',                  # имя
        ...     'before_update',                            # перед изменением
        ...     "SELECT RAISE(ABORT, 'пустой путь');",      # команды
        ...     when    =   "NEW.file_path = ''",           # условие
        ...     of      =   ('file_path',),                 # столбец
        ... ).of
        ('file_path',)
    """
    if not isinstance(name, str) or not _TRIGGER_NAME_RE.fullmatch(name) or name.lower().startswith('sqlite_'):
        raise ValueError(
            f"имя триггера {name!r}: нужны латиница, цифры и _, не с цифры и не с sqlite_"
        )
    if event not in ROW_EVENTS:
        raise ValueError(f"триггер {name}: неизвестное место {event!r}; есть: {', '.join(ROW_EVENTS)}")
    if not isinstance(body, str) or not body.strip().rstrip(';').strip():
        raise ValueError(f"триггер {name}: нет команд")
    if when is not None and (not isinstance(when, str) or not when.strip()):
        raise ValueError(f"триггер {name}: условие when пустое — уберите его или задайте")
    columns = (of,) if isinstance(of, str) else tuple(of)
    if columns and not event.endswith('_update'): # UPDATE OF есть только у изменения
        raise ValueError(f"триггер {name}: of — только для изменения, а место {event!r}")
    for column_name in columns:
        if not isinstance(column_name, str) or not _TRIGGER_NAME_RE.fullmatch(column_name):
            raise ValueError(f"триггер {name}: плохое имя столбца {column_name!r}")
    if len(set(columns)) != len(columns):
        raise ValueError(f"триггер {name}: столбец в of повторяется ({', '.join(columns)})")
    return TriggerSpec(
        name,                   # имя
        event,                  # место
        body,                   # команды
        when    =   when,       # условие
        of      =   columns,    # столбцы
    )


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


def column(
    name         : str,                     # имя
    sql_type     : Any,                     # тип SQLAlchemy
    title        : str,                     # подпись
    *,
    nullable     : bool = True,             # допускает пусто
    index        : Optional[str] = None,    # имя индекса
    comment      : Optional[str] = None,    # комментарий столбца
    default      : Any = None,              # значение по умолчанию
    dto          : bool = True,             # включать в DTO
    dto_type     : Any = None,              # тип DTO; None — по типу столбца
    dto_desc     : Optional[str] = None,    # описание поля DTO
    config       : bool = True,             # запись в field_configs
    primary_key  : bool = False,            # первичный ключ таблицы (вместо key)
    references   : Optional[str] = None,    # внешний ключ 'таблица.столбец'
    relation     : Optional[str] = None,    # связь к записи цели (с references)
    target_model : Optional[str] = None,    # класс модели цели связи
    **ui         : Any,                     # свои ключи field_configs
) -> FieldSpec: # описание обычного столбца
    """
    Обычный столбец.

    Ключом таблицы может быть и обычный столбец (``primary_key=True``; тогда ``key`` в
    описании не нужен) — например, имя файла у таблицы файлов фото: строка таблицы и есть
    файл. Внешний ключ на столбец другой таблицы, не на её ``id``, — ``references``; связь
    ``relation`` к ``target_model`` нужна, чтобы ORM записывал строку цели раньше
    ссылающейся (при включённых внешних ключах; без связи порядок вставки не гарантирован —
    проверено на SQLAlchemy 2.0, Ф1.6.7б). Черновики такой столбец ссылкой не считают
    (ссылки — ``fk`` и ``note``): его значение для них — обычное поле.

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
        primary_key: Столбец — первичный ключ таблицы (NOT NULL).
        references: Внешний ключ ``'таблица.столбец'``; None — без внешнего ключа.
        relation: Имя связи к записи цели (вместе с ``references`` и ``target_model``);
            None — без связи.
        target_model: Имя класса модели цели связи.
        **ui: Свои ключи ``field_configs`` (``editable``, ``required``, ``widget_type``,
            ``order``, ``autocomplete``, ``input_mask``…).

    Returns:
        ``FieldSpec``.

    Raises:
        ValueError: Связь без внешнего ключа или без модели цели.

    Example:
        >>> column('phone', sa.String(20), 'Телефон', input_mask='+7 (999) 999-99-99').config['input_mask']
        '+7 (999) 999-99-99'
        >>> column(
        ...     'file_path',                            # имя
        ...     sa.String(500),                         # тип
        ...     'Файл',                                 # подпись
        ...     references      =   'photo_files.file_path',  # внешний ключ на имя файла
        ...     relation        =   'file',             # связь к строке файла
        ...     target_model    =   'PhotoFile',        # модель файлов
        ... ).references
        'photo_files.file_path'
    """
    if relation and not (references and target_model): # связь без ключа SQLAlchemy не построит
        raise ValueError(f"столбец {name}: связь {relation!r} — нужны references и target_model")
    if primary_key:
        nullable = False
    py_type = dto_type
    if py_type is None:
        base = _python_type(sql_type)
        py_type = Optional[base] if nullable else base
    return FieldSpec(
        name,                                               # имя
        'column',                                           # вид
        title,                                              # подпись
        sql_type,                                           # тип
        nullable,                                           # пусто
        index,                                              # индекс
        comment,                                            # комментарий
        default,                                            # по умолчанию
        target_model    =   target_model,                   # модель цели связи
        relation        =   relation,                       # связь
        dto             =   dto,                            # в DTO
        dto_type        =   py_type,                        # тип DTO
        dto_desc        =   dto_desc,                       # описание DTO
        config          =   {'title': title, **ui} if config else None,  # настройки поля
        primary_key     =   primary_key,                    # первичный ключ
        references      =   references,                     # внешний ключ на столбец
    )


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


def children(
    name            : str,                                  # имя связи (photos)
    child_model     : str,                                  # класс модели подчинённых (Photo)
    back            : str,                                  # обратная связь у подчинённых (appointment)
    *,
    child_dto       : Optional[str] = None,                 # класс DTO подчинённых; None — поля DTO нет
    cascade         : Optional[str] = 'all, delete-orphan', # каскад; None — по умолчанию SQLAlchemy
    foreign_keys    : Optional[str] = None,                 # явный внешний ключ ('[Appointment.note_id]')
    dto             : bool = True,                          # включать в DTO
    dto_desc        : Optional[str] = None,                 # описание поля DTO
    config          : bool = True,                          # делать запись в field_configs
    title           : str = '',                             # подпись
    **ui            : Any,                                  # свои ключи field_configs
) -> FieldSpec: # связь «один ко многим»
    """
    Описывает подчинённые записи — связь «один ко многим».

    По умолчанию с каскадом ``'all, delete-orphan'``: удаление владельца удаляет и их. Для
    обратной стороны ссылки (``AppointmentNote.appointments`` — приёмы, ссылающиеся на
    заметку) каскад не нужен (``cascade=None`` — каскад SQLAlchemy по умолчанию
    ``save-update, merge``), а внешних ключей на владельца у подчинённой таблицы может быть
    несколько — тогда нужный задаётся ``foreign_keys``. ``back_populates`` ставится только
    на этой стороне: у полей ``note()`` обратной связи нет (как было до описаний).

    Args:
        name         : (str) Имя связи на модели владельца.
        child_model  : (str) Имя класса модели подчинённых.
        back         : (str) Имя связи у подчинённых, с которой связана эта
            (``back_populates``).
        child_dto    : (str/None) Имя класса DTO подчинённых (поле DTO ``Optional[List[…]]``);
            None — поля в DTO нет.
        cascade      : (str/None) Каскад связи; None — каскад SQLAlchemy по умолчанию.
        foreign_keys : (str/None) Внешний ключ подчинённых на владельца строкой
            SQLAlchemy (``'[Appointment.note_id]'``); None — определяется сам (ключ один).
        dto          : (bool) Включать в DTO (нужен и ``child_dto``).
        dto_desc     : (str/None) Описание поля DTO.
        config       : (bool) Делать запись в ``field_configs``.
        title        : (str) Подпись.
        **ui         : (Any) Свои ключи ``field_configs``.

    Returns:
        (FieldSpec) Описание поля.

    Example:
        >>> children(
        ...     'photos',                           # имя связи
        ...     'Photo',                            # модель подчинённых
        ...     'appointment',                      # обратная связь
        ...     child_dto   =   'PhotoDTO',         # DTO подчинённых
        ... ).cascade
        'all, delete-orphan'
        >>> children(
        ...     'appointments',                             # приёмы, ссылающиеся на заметку
        ...     'Appointment',                              # модель подчинённых
        ...     'note',                                     # связь приёма с заметкой
        ...     cascade         =   None,                   # без каскада удаления
        ...     foreign_keys    =   '[Appointment.note_id]',  # один из пяти ключей на заметки
        ...     dto             =   False,                  # не в DTO
        ...     config          =   False,                  # не в настройках
        ... ).foreign_keys
        '[Appointment.note_id]'
    """
    dto_type = Optional[List[child_dto]] if (dto and child_dto) else None
    return FieldSpec(
        name,                                                       # имя связи
        'children',                                                 # вид поля
        title,                                                      # подпись
        target_model    =   child_model,                            # модель подчинённых
        relation        =   name,                                   # связь — под тем же именем
        back            =   back,                                   # обратная связь
        cascade         =   cascade,                                # каскад
        foreign_keys    =   foreign_keys,                           # явный внешний ключ
        dto             =   dto and child_dto is not None,          # в DTO — только с классом DTO
        dto_type        =   dto_type,                               # тип поля DTO
        dto_desc        =   dto_desc,                               # описание поля DTO
        config          =   {'title': title, **ui} if config else None,  # запись настроек
    )


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
        comment: Комментарий таблицы в БД.
        sqlite_autoincrement: ``AUTOINCREMENT`` у ключа в SQLite (id не переиспользуются).
        keep: Хранение строк (Ф1.6.7г): ``KEEP_ALWAYS`` — хранить всегда (по умолчанию),
            ``KEEP_USED`` — только используемые (строку без ссылок, ставшую такой в
            транзакции, удаляет сборщик мусора слоя базы перед коммитом).
        events: Действия, подключённые к местам событий таблицы (``on(...)``), по порядку.
        triggers: Встроенные триггеры SQLite (``trigger(...)``, Ф1.6.7д): правила внутри
            данных, создаются миграцией. Модель несёт их текст в ``Table.info``.

    Example:
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
    comment: Optional[str] = None
    sqlite_autoincrement: bool = True
    keep                : str = KEEP_ALWAYS                 # хранение строк (Ф1.6.7г)
    events              : Tuple[EventSpec, ...] = ()        # действия событий таблицы (Ф1.6.7г)
    triggers            : Tuple[TriggerSpec, ...] = ()      # встроенные триггеры SQLite (Ф1.6.7д)

    def __post_init__(self) -> None: # приводит и проверяет описание
        """
        Приводит поля, события и триггеры к кортежу, задаёт тип записи по умолчанию, проверяет
        повторы имён, режим хранения, подключения событий и триггеры.

        Raises:
            ValueError: Имя поля/столбца повторяется; неизвестный режим ``keep``; в
                ``events`` не ``EventSpec`` (подключение — только через ``on``); в ``triggers``
                не ``TriggerSpec``, имя триггера повторяется, в ``of`` неизвестный столбец.

        Example:
            >>> TableDef(
            ...     't', 'T', 'TDTO',   # таблица, модель, DTO
            ...     (key(), key()),     # поля: имя повторяется
            ... )
            Traceback (most recent call last):
            ValueError: таблица t: имя 'id' повторяется
        """
        object.__setattr__(self, 'fields', tuple(self.fields))
        object.__setattr__(self, 'events', tuple(self.events))
        object.__setattr__(self, 'triggers', tuple(self.triggers))
        if self.keep not in KEEP_MODES: # опечатка в режиме хранения — сразу, не при работе
            raise ValueError(
                f"таблица {self.name}: неизвестный режим хранения keep={self.keep!r}; "
                f"есть: {', '.join(KEEP_MODES)}"
            )
        for spec in self.events:
            if not isinstance(spec, EventSpec):
                raise ValueError(
                    f"таблица {self.name}: в events — {spec!r}; подключайте действия через on(...)"
                )
        for event in TABLE_EVENTS: # одно действие дважды на одном месте выполнилось бы дважды
            names = self.actions_for(event)
            if len(set(names)) != len(names):
                raise ValueError(
                    f"таблица {self.name}: событие {event!r} — действие подключено дважды "
                    f"({', '.join(names)})"
                )
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
        self._check_triggers()

    def _check_triggers(self) -> None: # сверяет триггеры с полями описания
        """
        Проверяет триггеры по описанию таблицы: вид записи, повтор имени, столбцы ``UPDATE OF``.
        Текст команд и повтор имени на другой таблице проверяются при открытии базы.

        Raises:
            ValueError: В ``triggers`` не ``TriggerSpec``, имя повторяется, в ``of`` столбец,
                которого в таблице нет.

        Example:
            >>> TableDef(
            ...     't', 'T', 'TDTO', (key(),),
            ...     triggers    =   (trigger('a', 'before_update', 'SELECT 1', of='nope'),),
            ... )
            Traceback (most recent call last):
            ValueError: таблица t: триггер a — в of нет столбца 'nope'
        """
        names  : set = set()
        stored = {
            spec.id_name if spec.kind == 'note' else spec.name   # столбец заметки — её ссылка
            for spec in self.fields
            if spec.kind in ('key', 'column', 'fk', 'note', 'timestamp')
        }
        for spec in self.triggers:
            if not isinstance(spec, TriggerSpec):
                raise ValueError(
                    f"таблица {self.name}: в triggers — {spec!r}; описывайте через trigger(...)"
                )
            if spec.name in names:
                raise ValueError(f"таблица {self.name}: имя триггера {spec.name!r} повторяется")
            names.add(spec.name)
            for column_name in spec.of:
                if column_name not in stored:
                    raise ValueError(
                        f"таблица {self.name}: триггер {spec.name} — в of нет столбца {column_name!r}"
                    )

    def actions_for(
        self,
        event : str,   # место события (TABLE_EVENTS)
    ) -> Tuple[str, ...]: # имена действий места по порядку выполнения
        """
        Возвращает имена действий, подключённых к месту события, в порядке выполнения: по
        порядку ``on(...)`` в ``events``, внутри ``on`` — по порядку имён.

        Args:
            event : (str) Место события.

        Returns:
            (Tuple[str, ...]) Имена действий; пусто — к месту ничего не подключено.

        Raises:
            ValueError: Неизвестное место события.

        Example:
            >>> TableDef(
            ...     't', 'T', 'TDTO', (key(),),
            ...     events  =   (on('after_delete', 'a'), on('after_delete', 'b')),
            ... ).actions_for(
            ...     'after_delete',   # место
            ... )
            ('a', 'b')
        """
        if event not in TABLE_EVENTS:
            raise ValueError(f"неизвестное место события {event!r}; есть: {', '.join(TABLE_EVENTS)}")
        return tuple(
            name
            for spec in self.events
            if spec.event == event
            for name in spec.actions
        )

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
            elif spec.kind == 'column' and (spec.primary_key or spec.references):
                # ключ-столбец и внешний ключ на столбец (Ф1.6.7б, таблица файлов фото)
                fk_args = [sa.ForeignKey(spec.references)] if spec.references else []
                result[spec.name] = sa.Column(
                    spec.sql_type,                          # тип
                    *fk_args,                               # внешний ключ на столбец цели
                    primary_key     =   spec.primary_key,   # ключ таблицы
                    nullable        =   spec.nullable,      # NOT NULL
                    default         =   spec.default,       # по умолчанию
                    comment         =   spec.comment,       # комментарий
                )
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

    def build_model(
        self,
        base        : Any,                                  # декларативная база
        namespace   : Optional[Mapping[str, Any]] = None,   # свои атрибуты класса (методы)
        module      : Optional[str] = None,                 # __module__ класса; None — этот модуль
    ) -> type: # класс модели SQLAlchemy из описания
        """
        Строит класс модели SQLAlchemy на базовом классе ``base``.

        Столбцы — в порядке ``column_order``; индексы, комментарий таблицы и
        ``sqlite_autoincrement`` — в ``__table_args__``; связи: ``note`` — к общей таблице
        заметок по своему столбцу, ``fk`` — к цели (с ``back_populates``, если задано),
        ``children`` — к подчинённым (каскад и явный внешний ключ — если заданы). Атрибуты
        ``namespace`` ставятся последними и перекрывают построенные (``__repr__``). Модель
        получает атрибут ``__table_def__`` — это описание (хранение и события таблицы для
        слоя базы, Ф1.6.7г). Триггеры описания — текстом в ``Table.info[TRIGGERS_INFO]``
        (Ф1.6.7д); таблица без триггеров ``info`` не получает.

        Args:
            base      : (Any) Декларативная база (``Base`` приложения или своя — для проверок).
            namespace : (Mapping/None) Свои атрибуты класса (методы); None — без них.
            module    : (str/None) Модуль класса (``__module__``); None — ``app.schema.define``.

        Returns:
            (type) Класс модели.

        Example:
            >>> Patient = PATIENTS.build_model(
            ...     Base,                       # декларативная база
            ...     module  =   __name__,       # модуль класса
            ... )
            >>> Patient.__tablename__
            'patients'
        """
        attrs: Dict[str, Any] = {'__tablename__': self.name, '__doc__': self.doc or self.model_name,
                                 '__repr__': _model_repr, '__module__': module or __name__}
        # описание у модели: по нему слой базы находит хранение и события таблицы (Ф1.6.7г);
        # модели без описания (написанные вручную, тестовые) — «хранить всегда», без событий
        attrs['__table_def__'] = self
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
            elif spec.kind == 'column' and spec.relation:
                # связь «многие к одному» по внешнему ключу на столбец: без неё ORM не знает,
                # что строку цели вставлять раньше (Ф1.6.7б)
                attrs[spec.relation] = relationship(
                    spec.target_model,                          # модель цели
                    foreign_keys    =   [columns[spec.name]],   # этот столбец
                )
            elif spec.kind == 'children':
                # каскад и явный внешний ключ — только если заданы: иначе умолчания SQLAlchemy
                options_rel: Dict[str, Any] = {}
                if spec.cascade is not None:
                    options_rel['cascade'] = spec.cascade
                if spec.foreign_keys is not None: # у подчинённых несколько ключей на владельца
                    options_rel['foreign_keys'] = spec.foreign_keys
                attrs[spec.relation] = relationship(
                    spec.target_model,                  # модель подчинённых
                    back_populates  =   spec.back,      # обратная связь
                    **options_rel,                      # каскад, внешний ключ
                )
                # attrs[spec.relation] = relationship(spec.target_model, back_populates=spec.back,
                #                                     cascade=spec.cascade)
                # ↑ до 2026-10-30 (Ф1.3.1): каскад передавался всегда, явного внешнего ключа не
                #   было — обратную сторону ссылки (заметка → приёмы, пять ключей на заметки)
                #   описанием не задать
        options: Dict[str, Any] = {'sqlite_autoincrement': self.sqlite_autoincrement}
        if self.comment:
            options['comment'] = self.comment
        if self.triggers: # текст триггеров — для сравнения с базой и генератора миграций
            options['info'] = {
                TRIGGERS_INFO: {
                    spec.name: spec.create_sql(self.name)   # имя → CREATE TRIGGER
                    for spec in self.triggers
                },
            }
        attrs['__table_args__'] = (*indexes, options)
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
                # id заметки — служебное поле: в model_dump() не выгружается (как в DTO,
                # написанных вручную до 2026-10-19)
                result[spec.id_name] = (Optional[int], Field(None, description=spec.id_dto_desc, exclude=True))
                # result[spec.id_name] = (Optional[int], Field(None, description=spec.id_dto_desc))
                # ↑ до rework-schema (2026-10-21): без exclude=True — id заметок попадали в
                #   model_dump() (регрессия генерации DTO 2026-10-19, DT6 в app/dto/IMPLEMENTATION.md)
                continue
            annotation = spec.dto_type
            required = spec.kind in ('column', 'fk') and not spec.nullable
            default = ... if required else None
            result[spec.name] = (annotation, Field(default, description=spec.dto_desc))
        return self._ordered(result, self.dto_order)

    def build_dto(self, namespace: Optional[Mapping[str, Any]] = None,
                  module: Optional[str] = None) -> Type[BaseModel]:
        """
        Класс DTO (``from_attributes``). Ссылки на другие DTO по имени (``List['PhotoDTO']``)
        разрешаются ``rebuild_dtos`` после создания всех.

        Args:
            namespace: Не используется (зарезервировано для своих методов DTO).
            module: Модуль класса (``__module__``; по умолчанию — этот).

        Returns:
            Класс DTO.

        Пример:
            >>> PatientDTO = PATIENTS.build_dto(); PatientDTO(last_name='П', first_name='И').id is None
            True
        """
        dto = create_model(self.dto_name, __config__=ConfigDict(from_attributes=True),
                           __doc__=self.doc or self.dto_name, __module__=module or __name__,
                           **self.dto_fields())
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
           'rebuild_dtos', 'timestamp', 'NOTES_TABLE', 'NOTES_MODEL',
           'EventSpec', 'on', 'KEEP_ALWAYS', 'KEEP_USED', 'KEEP_MODES',
           'ROW_EVENTS', 'TRANSACTION_EVENTS', 'TABLE_EVENTS',
           'TriggerSpec', 'trigger', 'TRIGGERS_INFO']
