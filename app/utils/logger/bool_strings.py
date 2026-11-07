# app/utils/logger/bool_strings.py

"""
Одно правило разбора строк-флагов на всю программу.

``'on'`` — истина, ``'off'`` — ложь; регистр и пробелы по краям не важны. Правилом
пользуются журналы (``BaseAppLogger._to_bool``, флаги ``enable_file_logging`` /
``use_name_in_filename``), менеджер настроек (``AppConfigManager._coerce_value``) и экран
настроек (``SettingsPage._to_bool``).

Какие строки что значат, решает только :func:`parse_bool_string`. Что делать со строкой,
которую правило не знает, решает вызывающий:

* журналы и экран настроек — ложь (:func:`to_bool`);
* менеджер настроек — оставляет строку как есть, чтобы не потерять значение из файла;
* флаги логгера — считают её именем другого логгера (``enable_file_logging='system'``).

Модуль лежит в пакете журналов, потому что пакет переносится в другие проекты простым
копированием своей папки и не может импортировать ничего из ``app``; настройки и так зависят
от журналов, а не наоборот. Сам модуль ничего из проекта не импортирует.

Example:
    >>> from app.utils.logger.bool_strings import parse_bool_string, to_bool
    >>> parse_bool_string(' ON '), parse_bool_string('off'), parse_bool_string('10 МБ')
    (True, False, None)
    >>> to_bool('10 МБ')
    False
"""

from typing import Any, Optional, Tuple

TRUE_STRINGS  : Tuple[str, ...] = ('true', '1', 'yes', 'on')         # строки, означающие «да»
FALSE_STRINGS : Tuple[str, ...] = ('false', '0', 'no', 'off', '')    # строки, означающие «нет»


# значение строки-флага по единому правилу
def parse_bool_string(
    text : str,  # строка из настроек или аргумента
) -> Optional[bool]:
    """
    Разбирает строку-флаг: да, нет или «правило такой строки не знает».

    Регистр и пробелы по краям не важны. Пустая строка — ложь. Не приводит нераспознанную
    строку ни к чему: это решает вызывающий (см. описание модуля).

    Args:
        text : (str) Строка из настроек или аргумента.

    Returns:
        (bool/None) ``True`` или ``False``; None — строка не распознана.

    Example:
        >>> parse_bool_string('On'), parse_bool_string(''), parse_bool_string('system')
        (True, False, None)
    """
    normalized = text.strip().lower()
    if normalized in TRUE_STRINGS:
        return True
    if normalized in FALSE_STRINGS:
        return False
    return None


# значение настройки как bool; нераспознанная строка — ложь
def to_bool(
    value : Any,  # строка из настроек или bool / int / None
) -> bool:
    """
    Приводит значение настройки к ``bool``.

    Строки — по :func:`parse_bool_string`, нераспознанная строка — ложь. Не строки — обычный
    ``bool(value)``.

    Args:
        value : (Any) Строка из настроек или значение другого типа.

    Returns:
        (bool) Значение флага.

    Example:
        >>> to_bool('on'), to_bool('off'), to_bool('нечто'), to_bool(1), to_bool(None)
        (True, False, False, True, False)
    """
    if isinstance(value, str):
        return parse_bool_string(value) is True
    return bool(value)
