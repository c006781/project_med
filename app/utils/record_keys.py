# app/utils/record_keys.py
"""
Ключи сравнения записей: «та же запись», если ключи равны.

Общие для импорта из Word (``parsers/word_importer.py``, ТД-8) и объединения
пациентов-дублей (``app/services/patient_merge.py``, Ф1.6.10а): ``app`` не зависит от
``parsers``, поэтому функции живут здесь, а импорт берёт их отсюда (перенесены
2026-10-31 без изменения поведения).

* ``normalize_text`` — очистка текста с сохранением переносов (тексты приёмов);
* ``normalize_match`` — строка для сравнения (регистр, «ё», пунктуация, пробелы не важны);
* ``record_key`` — ключ записи по списку полей (строки — через ``normalize_match``);
* ``appointment_key`` — ключ повторного приёма: дата и все тексты;
* дата рождения с точностью (Ф1.6.10е): ``normalize_birth_date`` (что записывать),
  ``birth_date_key`` и ``coarser_precision`` (сравнение), ``format_birth_date`` (показ);
* ``match_patients`` — тот же ли пациент: «пустое не противоречит», дата — по наименее
  точной из двух, метка «полное» / «неполное» (``PatientMatch``).

Одним ключом «тот же пациент» больше не выразить: 1999 совпадает и с 14.06.1999, и с
15.06.1999, а они друг с другом — нет (сравнение не транзитивно). Поэтому пациенты
сравниваются попарно; ``record_key`` остаётся точным ключом по полям.

Example:
    >>> record_key(
    ...     {'last_name': 'Ёлкин', 'birth_date': date(1990, 5, 12)},   # запись
    ...     ('last_name', 'birth_date'),                               # поля ключа
    ... )
    ('елкин', datetime.date(1990, 5, 12))
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional, Sequence, Tuple

# Поля пациента, по которым пациент считается тем же: ФИО и дата рождения (решения владельца
# 2026-10-31) — общие для поиска при импорте и для дублей при объединении. Как сравниваются —
# match_patients: фамилия и имя всегда, остальное — если заполнено у обеих; дата — по
# наименее точной из двух (до Ф1.6.10е — полная дата целиком)
PATIENT_KEY_FIELDS = (
    'last_name',
    'first_name',
    'middle_name',
    'birth_date',
)

# Поля пациента, которые совпадают всегда («пустое не противоречит» к ним не относится)
PATIENT_NAME_FIELDS = (
    'last_name',
    'first_name',
)

# Дата рождения и её точность (значения столбца patients.birth_date_precision)
BIRTH_DATE_FIELD = 'birth_date'
BIRTH_PRECISION_FIELD = 'birth_date_precision'
BIRTH_PRECISION_DAY = 'day'       # полная дата: 14.06.1999
BIRTH_PRECISION_MONTH = 'month'   # месяц и год: 06.1999 (хранится 01.06.1999)
BIRTH_PRECISION_YEAR = 'year'     # только год: 1999 (хранится 01.01.1999)
# от точной к грубой: по этому порядку выбирается наименее точная из двух
BIRTH_PRECISIONS = (
    BIRTH_PRECISION_DAY,
    BIRTH_PRECISION_MONTH,
    BIRTH_PRECISION_YEAR,
)

# Метки совпадения пациентов (решение владельца 2026-10-31)
MATCH_FULL = 'полное'         # все поля известны и равны
MATCH_PARTIAL = 'неполное'    # противоречий нет, но что-то пусто
MATCH_DIFFERENT = 'разные'    # заполнено у обеих и не равно

# Названия полей для текста метки совпадения
PATIENT_MATCH_TITLES = {
    'last_name'   : 'фамилия',
    'first_name'  : 'имя',
    'middle_name' : 'отчество',
    'birth_date'  : 'дата рождения',
}

# Поля приёма, по которым приём считается повторным (ТД-8: дата и все тексты)
APPOINTMENT_KEY_FIELDS = (
    'date',
    'reason_text',
    'procedure_text',
    'recommendations_text',
    'cost_procedure_text',
    'note_text',
)


def normalize_text(
    text : Optional[str],  # исходный текст (None — как пустой)
) -> str: # очистка текста с сохранением переносов
    """
    Очищает текст, но сохраняет переносы строк.

    - Заменяет ``\\r\\n`` и ``\\r`` на ``\\n``.
    - В каждой строке убирает пробелы по краям и сворачивает повторные пробельные
      символы (пробелы, табуляции, неразрывные пробелы) в один пробел; ``\\n`` не трогает.
    - Убирает пустые строки в начале и конце; внутренние пустые строки сохраняет
      (строка из одних пробелов становится пустой).

    Args:
        text : (str/None) Исходный текст; None — пустая строка.

    Returns:
        (str) Очищенная строка с сохранёнными внутренними переносами.

    Example:
        >>> normalize_text('  Тест  1 1\\r\\n причина ')
        'Тест 1 1\\nпричина'
        >>> normalize_text(None)
        ''
    """

    if not text:
        return ""

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # W1: пробелы по краям строки и повторные внутри — убрать (split() без аргумента
    # режет по любым пробельным символам, включая табуляции и неразрывный пробел)
    lines = [
        ' '.join(line.split())
        for line in text.split('\n')
    ]

    # Убираем только пустые строки в начале и конце, внутренние сохраняем
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    return '\n'.join(lines)


def normalize_match(
    s : Optional[str],  # исходная строка (заголовок столбца, ФИО, title поля)
) -> str: # строка для сравнения
    """
    Приводит строку к единому виду для сравнения.

    Нижний регистр, «ё» → «е», без знаков препинания, пробелы свёрнуты и обрезаны.

    Args:
        s : (str/None) Исходная строка; None и '' — пустая строка.

    Returns:
        (str) Нормализованная строка.

    Example:
        >>> normalize_match('Рекомендации и дата сл. приёма')
        'рекомендации и дата сл приема'
    """

    if not s:
        return ""

    s = s.lower()
    s = s.replace('ё', 'е')
    s = re.sub(r'[^\w\s]', '', s)      # удаляем всё, кроме букв, цифр, пробелов
    s = re.sub(r'\s+', ' ', s).strip() # сворачиваем множественные пробелы

    return s


def _field_value(
    record : Any,  # словарь или объект с атрибутами (DTO, модель)
    name   : str,  # имя поля
) -> Any: # значение поля записи
    """
    Возвращает значение поля записи: ключ словаря или атрибут объекта (нет — None).

    Args:
        record : (Any) Словарь или объект.
        name   : (str) Имя поля.

    Returns:
        (Any) Значение или None.

    Example:
        >>> _field_value({'phone': '1'}, 'phone')
        '1'
    """
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def record_key(
    record : Any,             # словарь или объект с атрибутами (DTO, модель)
    fields : Sequence[str],   # поля ключа по порядку
) -> Tuple[Any, ...]: # ключ «та же запись»
    """
    Ключ записи по списку полей: строки — после ``normalize_match`` (None и '' — ''),
    остальные значения (даты, числа) — как есть.

    Точный ключ: дата сравнивается целиком, отчество None и '' — одно и то же. Пациентов
    так не сравнивают: дата с точностью и пустые поля общим ключом не выражаются —
    ``match_patients`` (Ф1.6.10е).

    Args:
        record : (Any) Словарь или объект с атрибутами.
        fields : (Sequence[str]) Имена полей ключа.

    Returns:
        (Tuple[Any, ...]) Ключ для сравнения.

    Example:
        >>> record_key(
        ...     {'last_name': 'Ёлкин ', 'middle_name': None},   # запись
        ...     ('last_name', 'middle_name'),                   # поля ключа
        ... )
        ('елкин', '')
    """
    key = []
    for name in fields:
        value = _field_value(record, name)
        if value is None or isinstance(value, str):
            value = normalize_match(value)
        key.append(value)
    return tuple(key)


def appointment_key(
    appointment : Any,                                  # строка документа (словарь) или приём (DTO)
    fields      : Sequence[str] = APPOINTMENT_KEY_FIELDS,  # первое — дата, остальные — тексты
) -> Tuple[Any, ...]: # ключ повторного приёма
    """
    Ключ повторного приёма — дата и все тексты (``APPOINTMENT_KEY_FIELDS``), ТД-8.

    Тексты сравниваются после ``normalize_text`` (пустой текст — None): приём, введённый
    в окне с лишними пробелами, совпадает с приёмом из документа. Первое поле (дата)
    берётся как есть.

    Args:
        appointment : (Any) Словарь строки документа или объект с атрибутами (``AppointmentDTO``).
        fields      : (Sequence[str]) Поля ключа: первое — дата, остальные — тексты.

    Returns:
        (Tuple[Any, ...]) Ключ для сравнения.

    Example:
        >>> appointment_key({'date': date(2026, 3, 14), 'reason_text': 'боль  '})
        (datetime.date(2026, 3, 14), 'боль', None, None, None, None)
    """

    values = [_field_value(appointment, name) for name in fields]

    return (values[0],) + tuple(
        normalize_text(value) or None
        for value in values[1:]
    )


def effective_birth_precision(
    birth_date : Optional[date],  # дата рождения
    precision  : Optional[str],   # точность из записи
) -> Optional[str]: # точность, с которой дата известна
    """
    Возвращает точность, с которой дата действительно известна.

    Для чтения: страница не должна падать на странной строке, поэтому ничего не проверяет
    (проверка — ``normalize_birth_date``, при записи). Даты нет — точности нет; дата без
    точности или с неизвестным значением — полная.

    Args:
        birth_date : (date/None) Дата рождения.
        precision  : (str/None) Точность из записи.

    Returns:
        (str/None) Одно из ``BIRTH_PRECISIONS``; None — даты нет.

    Example:
        >>> effective_birth_precision(
        ...     date(1999, 1, 1),   # дата
        ...     None,               # точность не задана
        ... )
        'day'
    """
    if birth_date is None:
        return None
    return precision if precision in BIRTH_PRECISIONS else BIRTH_PRECISION_DAY


def normalize_birth_date(
    birth_date : Optional[date],  # дата рождения
    precision  : Optional[str],   # точность (None — полная)
) -> Tuple[Optional[date], Optional[str]]: # что записывать в базу
    """
    Приводит дату и точность к виду, который хранится в базе.

    * даты нет — точности тоже нет;
    * точность не задана — полная;
    * дата не укладывается в точность (14.06.1999 при «только год») — полная: это значит,
      что дату ввели точнее, чем было известно (форма, не знающая о точности, меняет только
      дату), а данные важнее пометки. Дата не обрезается.

    Args:
        birth_date : (date/None) Дата рождения.
        precision  : (str/None) Точность.

    Returns:
        (Tuple[date/None, str/None]) Дата и точность.

    Raises:
        ValueError: Неизвестная точность (текст: ``неизвестная точность даты рождения``).

    Example:
        >>> normalize_birth_date(
        ...     date(1999, 6, 14),      # точная дата
        ...     BIRTH_PRECISION_YEAR,   # точность старая
        ... )
        (datetime.date(1999, 6, 14), 'day')
    """
    if precision is not None and precision not in BIRTH_PRECISIONS:
        raise ValueError(f"неизвестная точность даты рождения: {precision}")
    if birth_date is None:
        return None, None
    fits = (
        precision == BIRTH_PRECISION_YEAR and (birth_date.month, birth_date.day) == (1, 1)
        or precision == BIRTH_PRECISION_MONTH and birth_date.day == 1
    )
    return birth_date, precision if fits else BIRTH_PRECISION_DAY


def coarser_precision(
    first  : str,  # первая точность
    second : str,  # вторая точность
) -> str: # наименее точная из двух
    """
    Возвращает наименее точную из двух точностей (порядок ``BIRTH_PRECISIONS``).

    Args:
        first  : (str) Первая точность.
        second : (str) Вторая точность.

    Returns:
        (str) Наименее точная.

    Example:
        >>> coarser_precision(
        ...     BIRTH_PRECISION_DAY,    # полная
        ...     BIRTH_PRECISION_YEAR,   # только год
        ... )
        'year'
    """
    return max(
        (first, second),                # из двух
        key = BIRTH_PRECISIONS.index,   # дальше в списке — грубее
    )


def birth_date_key(
    birth_date : date,  # дата рождения
    precision  : str,   # с какой точностью сравнивать
) -> Tuple[int, ...]: # ключ даты с этой точностью
    """
    Ключ даты для сравнения с заданной точностью: только те части, что известны.

    Args:
        birth_date : (date) Дата.
        precision  : (str) Точность сравнения.

    Returns:
        (Tuple[int, ...]) ``(год)``, ``(год, месяц)`` или ``(год, месяц, день)``.

    Example:
        >>> birth_date_key(
        ...     date(1999, 6, 14),       # дата
        ...     BIRTH_PRECISION_MONTH,   # месяц и год
        ... )
        (1999, 6)
    """
    if precision == BIRTH_PRECISION_YEAR:
        return (birth_date.year,)
    if precision == BIRTH_PRECISION_MONTH:
        return (birth_date.year, birth_date.month)
    return (birth_date.year, birth_date.month, birth_date.day)


def format_birth_date(
    birth_date : Optional[date],   # дата рождения
    precision  : Optional[str],    # точность (None — полная)
    empty      : str = '',         # что показать, если даты нет
) -> str: # дата для показа
    """
    Форматирует дату рождения с учётом точности: «1999», «06.1999», «14.06.1999».

    Единственное место этого формата: планы объединения, экраны и формы берут его отсюда.

    Args:
        birth_date : (date/None) Дата рождения.
        precision  : (str/None) Точность.
        empty      : (str) Текст, если даты нет.

    Returns:
        (str) Текст.

    Example:
        >>> format_birth_date(
        ...     date(1999, 6, 1),        # дата
        ...     BIRTH_PRECISION_MONTH,   # месяц и год
        ... )
        '06.1999'
    """
    if birth_date is None:
        return empty
    known = effective_birth_precision(
        birth_date,   # дата
        precision,    # точность
    )
    if known == BIRTH_PRECISION_YEAR:
        return f"{birth_date.year:04d}"
    if known == BIRTH_PRECISION_MONTH:
        return f"{birth_date.month:02d}.{birth_date.year:04d}"
    return f"{birth_date.day:02d}.{birth_date.month:02d}.{birth_date.year:04d}"


@dataclass(frozen=True)
class PatientMatch:
    """
    Итог сравнения двух пациентов (``match_patients``).

    Args:
        differing_fields : (tuple) Заполнены у обоих и разные (есть — разные пациенты).
        empty_fields     : (tuple) Пусты хотя бы у одного.
        one_sided_fields : (tuple) Из ``empty_fields`` — заполнены только у одного.
        date_precision   : (str/None) С какой точностью сравнены даты; None — не сравнивались.

    Example:
        >>> PatientMatch((), ('middle_name',), ('middle_name',), 'day').label
        'неполное'
    """

    differing_fields : Tuple[str, ...] = ()
    empty_fields     : Tuple[str, ...] = ()
    one_sided_fields : Tuple[str, ...] = ()
    date_precision   : Optional[str] = None

    @property
    def same(self) -> bool:
        """
        Может ли это быть один пациент: нет полей, заполненных у обоих и разных.

        Returns:
            (bool) True — противоречий нет.

        Example:
            >>> PatientMatch(('birth_date',)).same
            False
        """
        return not self.differing_fields

    @property
    def label(self) -> str:
        """
        Возвращает метку: «полное» (всё известно и равно), «неполное» (что-то пусто), «разные».

        Returns:
            (str) ``MATCH_FULL``, ``MATCH_PARTIAL`` или ``MATCH_DIFFERENT``.

        Example:
            >>> PatientMatch().label
            'полное'
        """
        if self.differing_fields:
            return MATCH_DIFFERENT
        return MATCH_PARTIAL if self.empty_fields else MATCH_FULL

    def describe(
        self,
        titles : Mapping[str, str] = PATIENT_MATCH_TITLES,  # названия полей
    ) -> str: # метка с полями
        """
        Возвращает метку с перечнем полей: что именно пусто или различается.

        Args:
            titles : (Mapping[str, str]) Названия полей; нет в словаре — имя поля.

        Returns:
            (str) Например, ``неполное: пусто отчество, дата рождения``.

        Example:
            >>> PatientMatch((), ('middle_name',), ('middle_name',), 'day').describe()
            'неполное: пусто отчество'
        """
        if self.differing_fields:
            names, verb = self.differing_fields, 'различаются'
        elif self.empty_fields:
            names, verb = self.empty_fields, 'пусто'
        else:
            return self.label
        listed = ', '.join(titles.get(name, name) for name in names)
        return f"{self.label}: {verb} {listed}"


def match_patients(
    first        : Any,                                 # словарь или объект с атрибутами
    second       : Any,                                 # словарь или объект с атрибутами
    fields       : Sequence[str] = PATIENT_KEY_FIELDS,  # сравниваемые поля
    name_fields  : Sequence[str] = PATIENT_NAME_FIELDS, # совпадают всегда
) -> PatientMatch: # итог сравнения
    """
    Сравнивает двух пациентов по правилу «пустое не противоречит» (решение владельца 2026-10-31).

    * ``name_fields`` (фамилия, имя) совпадают всегда, пустыми не считаются;
    * остальные поля сравниваются, только если заполнены у обоих; пустое совпадает с чем
      угодно и попадает в ``empty_fields`` (в том числе пустое у обоих — такое поле неизвестно);
    * дата рождения — с наименее точной из двух точностей: 1999 совпадает с 14.06.1999;
    * строки — после ``normalize_match`` (регистр, «ё», пунктуация, пробелы не важны).

    Сравнение не транзитивно (1999 ≈ 14.06.1999, 1999 ≈ 15.06.1999, но не они между собой) —
    поэтому попарно, а не общим ключом.

    Note:
        Функция только сравнивает: совмещать пациентов можно только с одобрения пользователя.

    Args:
        first       : (Any) Первый пациент (DTO, модель или словарь).
        second      : (Any) Второй пациент.
        fields      : (Sequence[str]) Сравниваемые поля.
        name_fields : (Sequence[str]) Поля, которые совпадают всегда.

    Returns:
        (PatientMatch) Итог: ``same``, ``label``, ``empty_fields`` …

    Example:
        >>> match_patients(
        ...     {'last_name': 'Иванова', 'first_name': 'Мария', 'middle_name': 'Петровна'},   # без даты
        ...     {'last_name': 'иванова', 'first_name': 'Мария', 'birth_date': date(1985, 6, 14)},   # без отчества
        ... ).describe()
        'неполное: пусто отчество, дата рождения'
    """
    differing = []
    empty = []
    one_sided = []
    date_precision = None
    for name in fields:
        [left] = record_key(first, (name,))
        [right] = record_key(second, (name,))
        if name == BIRTH_DATE_FIELD and left != '' and right != '': # даты есть у обоих
            date_precision = coarser_precision(
                effective_birth_precision(left, _field_value(first, BIRTH_PRECISION_FIELD)),
                effective_birth_precision(right, _field_value(second, BIRTH_PRECISION_FIELD)),
            )
            left = birth_date_key(left, date_precision)
            right = birth_date_key(right, date_precision)
        if name not in name_fields and (left == '' or right == ''): # пустое не противоречит
            empty.append(name)
            if left != right: # заполнено только у одного
                one_sided.append(name)
        elif left != right:
            differing.append(name)
    return PatientMatch(
        differing_fields    =   tuple(differing),   # заполнены у обоих и разные
        empty_fields        =   tuple(empty),       # пусты хотя бы у одного
        one_sided_fields    =   tuple(one_sided),   # заполнены только у одного
        date_precision      =   date_precision,     # точность сравнения дат
    )
