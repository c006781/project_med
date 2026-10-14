# app/utils/logger/_common.py

"""
Общие служебные объекты пакета логирования.

Используются и обработчиками (``handlers.py``), и частями ``BaseAppLogger``.

Содержит:
    LOGGER_CODE_FILES   — имена файлов модулей логгера (``co_filename``); по ним логгер
                          узнаёт свои кадры стека при поиске места вызова.
    _STOP_OUTPUT        — маркер остановки фонового потока ``CallableHandler``.
    _level_to_int       — уровень по имени или числу → число.
    _NOT_FOUND          — маркер «значение не найдено» при поиске по цепочке родителей.
    _THIS_CODE_FILENAME — ``co_filename`` модуля ядра (см. ``base_logger.py``); здесь —
                          для совместимости импортов.

Пример:
    >>> from ._common import _level_to_int
    >>> _level_to_int('error')
    40
"""

import logging
from typing import List, Union


# Имена файлов (co_filename) всех модулей логгера. Каждый модуль добавляет себя при
# импорте; base_logger строит из списка правила skip_patterns_modeles. До разбиения на
# модули (2026-10-14) правило было одно — для единственного файла base_logger.py.
LOGGER_CODE_FILES: List[str] = []
LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Имя файла этого модуля так, как его видят кадры стека (frame.f_code.co_filename).
# По нему логгер пропускает свои кадры при поиске места вызова. Берётся из самого
# модуля, а не задаётся путём вида 'app/utils/logger/base_logger.py', поэтому модуль
# работает при копировании в любой проект и в сборке PyInstaller (где co_filename
# бывает относительным, а __file__ — абсолютным).
_THIS_CODE_FILENAME: str = (lambda: None).__code__.co_filename

# Маркер остановки фонового потока CallableHandler (кладётся в очередь при close()).
_STOP_OUTPUT = object()


def _level_to_int(level: Union[int, str]) -> int:
    """
    Приводит уровень к числу: ``'error'`` → 40, ``logging.ERROR`` → 40.

    Отдельная функция модуля (а не метод BaseAppLogger), чтобы ей могли пользоваться
    обработчики, объявленные раньше класса логгера.

    Args:
        level: Имя уровня без учёта регистра или неотрицательное число.

    Returns:
        Числовой уровень.

    Raises:
        ValueError: Неизвестное имя или отрицательное число.
        TypeError: Не строка и не число.

    Пример:
        >>> _level_to_int('warning'), _level_to_int(10)
        (30, 10)
    """
    if isinstance(level, int) and not isinstance(level, bool):
        if level < 0:
            raise ValueError(f"Уровень логирования не может быть отрицательным: {level}")
        return level
    if not isinstance(level, str):
        raise TypeError(f"Уровень логирования должен быть строкой или числом, получено: {level!r}")
    names = {'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING,
             'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL, 'NOTSET': logging.NOTSET}
    if level.upper() not in names:
        raise ValueError(f"Неизвестный уровень логирования: {level}")
    return names[level.upper()]


# Маркер «значение не найдено» для поиска по цепочке родителей
# (_get_config_with_inheritance): отличается от любого значения из конфига, включая None.
_NOT_FOUND = object()
