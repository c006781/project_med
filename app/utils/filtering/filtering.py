# app/utils/filtering/filtering.py

"""
Модуль для фильтрации данных в SQLAlchemy запросах.
Поддерживает различные операторы сравнения, включая нечеткий поиск.
"""
# Стандартные библиотеки Python

import datetime
from typing import List, Dict, Any, Tuple

from difflib import SequenceMatcher
# Импорты модулей


# Сторонние библиотеки

from sqlalchemy.orm import Query
from sqlalchemy import Date, Integer, Float, String, Time


class FilterOperator:
    """Константы операторов сравнения."""
    EQ      = 'eq'          # равно
    NE      = 'ne'          # не равно
    GT      = 'gt'          # больше
    GE      = 'ge'          # больше или равно
    LT      = 'lt'          # меньше
    LE      = 'le'          # меньше или равно
    LIKE    = 'like'        # содержит подстроку (LIKE %value%)
    ILIKE   = 'ilike'       # регистронезависимый LIKE
    IN      = 'in'          # в списке
    NOT_IN  = 'not_in'      # не в списке
    BETWEEN = 'between'     # между двумя значениями (value должно быть списком [min, max])
    IS_NULL = 'is_null'     # равно NULL (value игнорируется)
    IS_NOT_NULL = 'is_not_null' # не NULL
    FUZZY   = 'fuzzy'       # нечеткий поиск (требует пост-обработки)

def _convert_value(column, value: Any) -> Any:
    """
    Преобразует строковое значение в тип, соответствующий колонке SQLAlchemy.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [_convert_value(column, v) for v in value]
    if isinstance(column.type, Date):
        if isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(value)
    if isinstance(column.type, Integer):
        if isinstance(value, int):
            return value
        return int(value)
    if isinstance(column.type, Float):
        if isinstance(value, float):
            return value
        return float(value)
    if isinstance(column.type, Time):
        if isinstance(value, datetime.time):
            return value
        try:
            return datetime.time.fromisoformat(value)
        except AttributeError:
            h, m = map(int, value.split(':'))
            return datetime.time(h, m)
    return value

def escape_like(value: str, escape_char: str = '\\') -> str:
    """Экранирует спецсимволы % и _ в строке для LIKE."""
    return value.replace(escape_char, escape_char * 2).replace('%', escape_char + '%').replace('_', escape_char + '_')

def apply_filters(
    query: Query,
    model,
    filters: List[Dict[str, Any]],
    fuzzy_threshold: int = 60
) -> Tuple[Query, List[Tuple]]:
    """
    Применяет список фильтров к SQLAlchemy запросу.

    Аргументы:
        query: исходный запрос
        model: класс модели SQLAlchemy
        filters: список словарей, каждый с ключами:
            - column: имя столбца (строка)
            - operator: оператор из FilterOperator
            - value: значение для сравнения (зависит от оператора)
        fuzzy_threshold: порог схожести для нечеткого поиска (0-100)

    Возвращает:
        Кортеж (query, post_filters), где query — модифицированный запрос с SQL-фильтрами,
        а post_filters — список условий для пост-обработки (нечеткий поиск).
    """
    conditions = []
    post_filters = []  # для нечеткого поиска

    for f in filters:
        column_name = f['column']
        op = f['operator']
        value = f.get('value')

        # Проверяем, что столбец существует в модели
        if not hasattr(model, column_name):
            raise ValueError(f"Столбец {column_name} не найден в модели {model.__name__}")

        column = getattr(model, column_name)

        # Преобразуем значение в соответствии с типом колонки (кроме специальных операторов)
        if op not in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL, FilterOperator.FUZZY):
            value = _convert_value(column, value)

        if op == FilterOperator.EQ:
            conditions.append(column == value)
        elif op == FilterOperator.NE:
            conditions.append(column != value)
        elif op == FilterOperator.GT:
            conditions.append(column > value)
        elif op == FilterOperator.GE:
            conditions.append(column >= value)
        elif op == FilterOperator.LT:
            conditions.append(column < value)
        elif op == FilterOperator.LE:
            conditions.append(column <= value)
            
        # elif op == FilterOperator.LIKE:
        #     conditions.append(column.like(f"%{value}%"))
        # elif op == FilterOperator.ILIKE:
        #     conditions.append(column.ilike(f"%{value}%"))
        elif op == FilterOperator.LIKE:
            safe_value = escape_like(value)
            conditions.append(column.like(f"%{safe_value}%", escape='\\'))
        elif op == FilterOperator.ILIKE:
            safe_value = escape_like(value)
            conditions.append(column.ilike(f"%{safe_value}%", escape='\\'))

        elif op == FilterOperator.IN:
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"Для оператора IN значение должно быть списком, получено {type(value)}")
            conditions.append(column.in_(value))
        elif op == FilterOperator.NOT_IN:
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"Для оператора NOT_IN значение должно быть списком")
            conditions.append(~column.in_(value))
        elif op == FilterOperator.BETWEEN:
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(f"Для оператора BETWEEN значение должно быть списком из двух элементов")
            # Преобразуем оба элемента
            v1 = _convert_value(column, value[0])
            v2 = _convert_value(column, value[1])
            conditions.append(column.between(v1, v2))
        elif op == FilterOperator.IS_NULL:
            conditions.append(column.is_(None))
        elif op == FilterOperator.IS_NOT_NULL:
            conditions.append(column.isnot(None))
        elif op == FilterOperator.FUZZY:
            # Нечеткий поиск – сохраняем для пост-обработки
            post_filters.append((column_name, value, fuzzy_threshold))
        else:
            raise ValueError(f"Неизвестный оператор: {op}")

    if conditions:
        query = query.filter(*conditions)

    # Возвращаем запрос и список пост-фильтров
    return query, post_filters

def apply_post_filters(items: List[Any], post_filters: List[Tuple], model) -> List[Any]:
    """
    Применяет пост-фильтры (нечеткий поиск) к списку объектов.
    items: список ORM-объектов или DTO
    post_filters: список кортежей (column_name, search_value, threshold)
    """
    if not post_filters:
        return items

    def similarity(a, b):
        return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio() * 100

    result = []
    for item in items:
        match = True
        for col, val, thr in post_filters:
            item_val = getattr(item, col, None)
            if item_val is None:
                sim = 0
            else:
                sim = similarity(item_val, val)
            if sim < thr:
                match = False
                break
        if match:
            result.append(item)
    return result