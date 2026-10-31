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
* ``appointment_key`` — ключ повторного приёма: дата и все тексты.

Example:
    >>> record_key(
    ...     {'last_name': 'Ёлкин', 'birth_date': date(1990, 5, 12)},   # запись
    ...     ('last_name', 'birth_date'),                               # поля ключа
    ... )
    ('елкин', datetime.date(1990, 5, 12))
"""

import re
from typing import Any, Optional, Sequence, Tuple

# Поля пациента, по которым пациент считается тем же: ФИО и ПОЛНАЯ дата рождения (решение
# владельца 2026-10-31) — общие для поиска при импорте и для дублей при объединении
PATIENT_KEY_FIELDS = (
    'last_name',
    'first_name',
    'middle_name',
    'birth_date',
)

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

    Поиск дублей пациентов (Ф1.6.10а) — ``record_key(patient, ('last_name', 'first_name',
    'middle_name', 'birth_date'))``: дата рождения сравнивается целиком (решение владельца
    2026-10-31), отчество None и '' — одно и то же.

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
