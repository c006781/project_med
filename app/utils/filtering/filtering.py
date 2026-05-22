# app/utils/filtering/filtering.py
"""
Модуль для фильтрации данных в SQLAlchemy запросах.

Поддерживает различные операторы сравнения, включая нечёткий поиск,
а также построение деревьев фильтров с логическими операторами AND/OR.
Для виртуальных полей-заметок автоматически строит подзапросы EXISTS
к таблице AppointmentNote.
"""

# Стандартные библиотеки Python

import datetime
from typing import (
    List, Dict, Any, 
    Optional, Tuple, 
    Union
)

from difflib import SequenceMatcher

# Импорты модулей

from app.utils.logger.logger import AppLogger

# Сторонние библиотеки

from sqlalchemy import (
    Date, Integer, 
    Float,  Time,
    # String, 
    exists, select
)
from sqlalchemy.orm import Query
from sqlalchemy import or_, and_


@AppLogger.get_instance(
    name = 'filtering.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _build_filter_condition(
    filter_node: Union[Dict, List], 
    model, 
    note_mappings: Optional[Dict] = None,
) -> Any:
    """
    Рекурсивно строит SQLAlchemy условие из узла фильтра.

    Поддерживает:
        - Составные узлы {'and': [...]} и {'or': [...]}
        - Плоский список узлов (старый формат) – объединяются через AND
        - Листовые узлы с операторами: eq, ne, gt, ge, lt, le, like, ilike,
          in, not_in, between, is_null, is_not_null.
        - Специальную обработку полей-заметок (note_mappings) через подзапрос EXISTS.

    Args:
        filter_node: Узел фильтра – может быть dict (с 'and'/'or' или листовым узлом),
                     либо list (список листовых узлов).
        model: Класс SQLAlchemy модели (например, Appointment).
        note_mappings: Словарь для полей-заметок, полученный из
                       BaseService._get_note_field_mappings_dict().
                       Структура: {
                            dto_field: {
                                'foreign_key': str, 
                                'note_model': Type,
                                'text_column': str
                            }
                        }.

    Returns:
        SQLAlchemy условие (для использования в query.filter()).
        Для составных узлов возвращает and_()/or_().
        Для листьев возвращает column == value и т.п.
        Для полей-заметок возвращает exists(subquery).

    Raises:
        ValueError: Если оператор неизвестен или столбец (не заметка) не найден в модели.
    """
    
    # if isinstance(filter_node, list):
    #     # старый формат – список листьев, объединяем через AND
    #     conditions = [_build_filter_condition(item, model) for item in filter_node]
    #     return and_(*conditions) if conditions else True

    # if 'and' in filter_node:
    #     subconds = [_build_filter_condition(sub, model) for sub in filter_node['and']]
    #     return and_(*subconds)

    # if 'or' in filter_node:
    #     subconds = [_build_filter_condition(sub, model) for sub in filter_node['or']]
    #     return or_(*subconds)

    if isinstance(filter_node, list):
        # старый формат – список листьев, объединяем через AND
        conditions = [_build_filter_condition(item, model, note_mappings) for item in filter_node]
        return and_(*conditions) if conditions else True

    if 'and' in filter_node:
        subconds = [_build_filter_condition(sub, model, note_mappings) for sub in filter_node['and']]
        return and_(*subconds)

    if 'or' in filter_node:
        subconds = [_build_filter_condition(sub, model, note_mappings) for sub in filter_node['or']]
        return or_(*subconds)

    # Узел-лист
    column_name = filter_node['column']
    op = filter_node['operator']
    value = filter_node.get('value')
    value2 = filter_node.get('value2')

    
    # Обработка поля-заметки
    # if not hasattr(model, column_name):
    # Проверяем, не является ли поле заметкой
    if note_mappings and column_name in note_mappings:
        note_info = note_mappings[column_name]
        note_model = note_info['note_model']
        fk_column = getattr(model, note_info['foreign_key'])
        text_column = getattr(note_model, note_info['text_column'])
        
        if op == 'ilike':
            subq = select(text_column).where(text_column.ilike(f"%{value}%")).where(note_model.id == fk_column)
            return exists(subq)
        elif op == 'like':
            subq = select(text_column).where(text_column.like(f"%{value}%")).where(note_model.id == fk_column)
            return exists(subq)
        elif op == 'eq':
            subq = select(text_column).where(text_column == value).where(note_model.id == fk_column)
            return exists(subq)
        else:
            raise ValueError(f"Оператор {op} не поддерживается для поля-заметки {column_name}")
    # else:
    #     raise ValueError(f"Столбец {column_name} не найден в модели {model.__name__}")

    # Обычное поле
    if not hasattr(model, column_name):
        raise ValueError(f"Столбец {column_name} не найден в модели {model.__name__}")

    column = getattr(model, column_name)
    value = _convert_value(column, value) if value is not None else None

    if op == 'eq':
        return column == value
    elif op == 'ne':
        return column != value
    elif op == 'gt':
        return column > value
    elif op == 'ge':
        return column >= value
    elif op == 'lt':
        return column < value
    elif op == 'le':
        return column <= value
    elif op == 'like':
        safe = escape_like(value)
        return column.like(f"%{safe}%", escape='\\')
    elif op == 'ilike':
        safe = escape_like(value)
        return column.ilike(f"%{safe}%", escape='\\')
    elif op == 'in':
        if not isinstance(value, (list, tuple)):
            raise ValueError("Для IN значение должно быть списком")
        
        return column.in_(value)
    
    elif op == 'not_in':
        if not isinstance(value, (list, tuple)):
            raise ValueError("Для NOT_IN значение должно быть списком")
        
        return ~column.in_(value)
    
    elif op == 'between':
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("Для BETWEEN значение должно быть списком из двух элементов")
        
        v1 = _convert_value(column, value[0])
        v2 = _convert_value(column, value[1])

        return column.between(v1, v2)
    
    elif op == 'is_null':
        return column.is_(None)
    elif op == 'is_not_null':
        return column.isnot(None)
    else:
        raise ValueError(f"Неизвестный оператор: {op}")

@AppLogger.get_instance(
    name = 'filtering.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def apply_filters(
    query, 
    model, 
    filters, 
    fuzzy_threshold=60,
    note_mappings: Optional[Dict] = None
):
    """
    Применяет фильтры к SQLAlchemy запросу.

    Поддерживает два формата filters:
        1. Список словарей (старый формат) – каждый словарь с ключами
           'column', 'operator', 'value' (и опционально 'value2').
           Такие фильтры объединяются через AND.
        2. Дерево узлов (новый формат) – может содержать ключи 'and'/'or',
           вложенные списки и листья.

    Post-фильтры (оператор 'fuzzy') извлекаются и возвращаются отдельно для
    пост-обработки (применяются в памяти).

    Args:
        query: SQLAlchemy Query объект.
        model: Класс SQLAlchemy модели.
        filters: Список или дерево фильтров (см. описание выше).
        fuzzy_threshold: Порог схожести для нечёткого поиска (используется в пост-фильтрах).
        note_mappings: Словарь для полей-заметок (передаётся в _build_filter_condition).

    Returns:
        Tuple[Query, List]: (модифицированный запрос, список пост-фильтров).
            Пост-фильтры – список кортежей (column_name, search_value, threshold)
            или список словарей, извлечённых из узлов 'fuzzy'.
    """

    if not filters:
        return query, []

    # Разделяем пост-фильтры (fuzzy) и SQL-условия
    if isinstance(filters, list) and all(isinstance(f, dict) and 'operator' in f for f in filters):
        # старый формат – список листьев
        # (для простоты сразу преобразуем в дерево AND)
        tree = {'and': filters}
        condition = _build_filter_condition(tree, model, note_mappings)
        if condition is not True:
            query = query.filter(condition)

        # Пост-фильтры (fuzzy) извлекаем из filters 
        post_filters = [f for f in filters if f.get('operator') == 'fuzzy']
        return query, post_filters
    
    else:
        # новый формат – дерево
        condition = _build_filter_condition(filters, model, note_mappings)
        if condition is not True:
            query = query.filter(condition)

        # Пост-фильтры нужно собрать рекурсивно
        post_filters = _collect_post_filters(filters)
        return query, post_filters
    
@AppLogger.get_instance(
    name = 'filtering.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _collect_post_filters(node):
    """
    Рекурсивно собирает все узлы с оператором 'fuzzy'.

    Args:
        node: Узел дерева фильтров (dict, list или лист).

    Returns:
        List[Union[Dict, List]]: Список узлов, содержащих оператор 'fuzzy'.
            Каждый узел – словарь с ключами 'column', 'operator', 'value' (и 'value2').
    """

    if isinstance(node, dict):
        if node.get('operator') == 'fuzzy':
            return [node]
        
        if 'and' in node:
            return [item for sub in node['and'] for item in _collect_post_filters(sub)]
        
        if 'or' in node:
            return [item for sub in node['or'] for item in _collect_post_filters(sub)]
        
    elif isinstance(node, list):
        return [item for sub in node for item in _collect_post_filters(sub)]
    
    return []

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

@AppLogger.get_instance(
    name = 'filtering.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def _convert_value(column, value: Any) -> Any:
    """
    Преобразует строковое значение в тип, соответствующий колонке SQLAlchemy.

    Args:
        column: Колонка SQLAlchemy (объект Column).
        value: Значение для преобразования (может быть строкой, числом, датой и т.д.).

    Returns:
        Преобразованное значение, подходящее для сравнения с колонкой.
        Для дат и времени возвращает datetime.date / datetime.time.
        Для чисел – int/float.
        Для списков – рекурсивно преобразует каждый элемент.

    Raises:
        ValueError: Если преобразование невозможно (например, неверный формат даты).
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
        
        except AttributeError as e:            
            AppLogger.get_instance( 
                name = '_convert_value',
                enable_file_logging = 'user',
                use_name_in_filename = False, 
            ).error(f"Ошибка преобразования времени {e}")

            h, m = map(int, value.split(':'))

            return datetime.time(h, m)
        
    return value

@AppLogger.get_instance(
    name = 'filtering.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def escape_like(value: str, escape_char: str = '\\') -> str:
    """
    Экранирует спецсимволы % и _ в строке для LIKE.

    Args:
        value: Строка, которую нужно экранировать.
        escape_char: Символ экранирования (по умолчанию '\\').

    Returns:
        Строка, в которой символы '%', '_' и сам escape_char экранированы.
    """

    return value.replace(
        escape_char, escape_char * 2
    ).replace(
        '%', escape_char + '%'
    ).replace(
        '_', escape_char + '_'
    )

# @AppLogger.get_instance(
#     name = 'system',
# ).log_execution_time(
#     level=AppLogger._parse_log_level('DEBUG')
# )
# def apply_filters(
#     query: Query,
#     model,
#     filters: List[Dict[str, Any]],
#     fuzzy_threshold: int = 60
# ) -> Tuple[Query, List[Tuple]]:
#     """
#     Применяет список фильтров к SQLAlchemy запросу.

#     Аргументы:
#         query: исходный запрос
#         model: класс модели SQLAlchemy
#         filters: список словарей, каждый с ключами:
#             - column: имя столбца (строка)
#             - operator: оператор из FilterOperator
#             - value: значение для сравнения (зависит от оператора)
#         fuzzy_threshold: порог схожести для нечеткого поиска (0-100)

#     Возвращает:
#         Кортеж (query, post_filters), где query — модифицированный запрос с SQL-фильтрами,
#         а post_filters — список условий для пост-обработки (нечеткий поиск).
#     """
#     conditions = []
#     post_filters = []  # для нечеткого поиска

#     for f in filters:
#         column_name = f['column']
#         op = f['operator']
#         value = f.get('value')

#         # Проверяем, что столбец существует в модели
#         if not hasattr(model, column_name):
#             AppLogger.get_instance( name = 'user').exception(f"Столбец {column_name} не найден в модели {model.__name__}")
#             raise ValueError(f"Столбец {column_name} не найден в модели {model.__name__}")

#         column = getattr(model, column_name)

#         # Преобразуем значение в соответствии с типом колонки (кроме специальных операторов)
#         if op not in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL, FilterOperator.FUZZY):
#             value = _convert_value(column, value)

#         if op == FilterOperator.EQ:
#             conditions.append(column == value)
#         elif op == FilterOperator.NE:
#             conditions.append(column != value)
#         elif op == FilterOperator.GT:
#             conditions.append(column > value)
#         elif op == FilterOperator.GE:
#             conditions.append(column >= value)
#         elif op == FilterOperator.LT:
#             conditions.append(column < value)
#         elif op == FilterOperator.LE:
#             conditions.append(column <= value)
            
#         # elif op == FilterOperator.LIKE:
#         #     conditions.append(column.like(f"%{value}%"))
#         # elif op == FilterOperator.ILIKE:
#         #     conditions.append(column.ilike(f"%{value}%"))
#         elif op == FilterOperator.LIKE:
#             safe_value = escape_like(value)
#             conditions.append(column.like(f"%{safe_value}%", escape='\\'))
#         elif op == FilterOperator.ILIKE:
#             safe_value = escape_like(value)
#             conditions.append(column.ilike(f"%{safe_value}%", escape='\\'))

#         elif op == FilterOperator.IN:
#             if not isinstance(value, (list, tuple)):
#                 err_ = f"я оператора IN значение должно быть списком, получено {type(value)}"
#                 AppLogger.get_instance( name = 'user').exception(err_)
#                 raise ValueError(err_)
            
#             conditions.append(column.in_(value))
#         elif op == FilterOperator.NOT_IN:
#             if not isinstance(value, (list, tuple)):
#                 err_ = f"Для оператора NOT_IN значение должно быть списком"
#                 AppLogger.get_instance( name = 'user').exception(err_)
#                 raise ValueError(err_)
            
#             conditions.append(~column.in_(value))
#         elif op == FilterOperator.BETWEEN:
#             if not isinstance(value, (list, tuple)) or len(value) != 2:
#                 # self.logger.exception(err_.message)
#                 err_ = f"Для оператора BETWEEN значение должно быть списком из двух элементов"
#                 AppLogger.get_instance( name = 'user').exception(err_)
#                 raise ValueError(err_)

#             # Преобразуем оба элемента
#             v1 = _convert_value(column, value[0])
#             v2 = _convert_value(column, value[1])
#             conditions.append(column.between(v1, v2))
#         elif op == FilterOperator.IS_NULL:
#             conditions.append(column.is_(None))
#         elif op == FilterOperator.IS_NOT_NULL:
#             conditions.append(column.isnot(None))
#         elif op == FilterOperator.FUZZY:
#             # Нечеткий поиск – сохраняем для пост-обработки
#             post_filters.append((column_name, value, fuzzy_threshold))
#         else:
#             err_ = f"Неизвестный оператор: {op}"
#             AppLogger.get_instance( name = 'user').exception(err_)
#             raise ValueError(err_)

#     if conditions:
#         query = query.filter(*conditions)

#     # Возвращаем запрос и список пост-фильтров
#     return query, post_filters

@AppLogger.get_instance(
    name = 'filtering.py',
    enable_file_logging = 'system',
    use_name_in_filename = False, 
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def apply_post_filters(items: List[Any], post_filters: List[Tuple], model) -> List[Any]:
    """
    Применяет пост-фильтры (нечёткий поиск) к списку объектов.

    Args:
        items: Список ORM-объектов или DTO.
        post_filters: Список кортежей (column_name, search_value, threshold),
            где search_value – строка для поиска, threshold – порог схожести (0-100).
        model: Класс модели (используется для получения атрибутов, но в текущей
            реализации не используется; оставлен для совместимости).

    Returns:
        List[Any]: Отфильтрованный список объектов, для которых каждый пост-фильтр
        дал схожесть >= threshold.

    Примечание:
        Схожесть вычисляется через difflib.SequenceMatcher (регистронезависимо).
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