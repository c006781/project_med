# interfaces/gui/gui_window/utils/filter_converter.py
"""
Конвертер фильтров из формата UI (используемого FilterColumnDialog и FilterBar)
в формат списка словарей для методов сервиса (get_page_filtered).

Входной формат (хранится в self._current_filters):
    {
        column_index: {
            'logic': 'AND' | 'OR',
            'conditions': [
                {'operator': 'eq', 'value': ...},
                {'operator': 'like', 'value': ...},
                ...
            ]
        }
    }

Выходной формат (для сервиса):
    [
        {'column': 'column_name', 'operator': 'eq', 'value': ...},
        ...
    ]
Логика объединения (AND/OR) на данном этапе не поддерживается сервисом,
поэтому для нескольких условий используем список и полагаемся на сервисный apply_filters,
который применяет их через AND. Если в UI выбран OR, нужно преобразовывать в несколько
вызовов или расширять сервис. Пока оставляем AND.
"""

from typing import List, Dict, Any, Optional, Union

from app.utils.logger.logger import AppLogger

@AppLogger.get_instance(
    name = 'filter_converter.py',
    # share_file_with = 'system',
    enable_file_logging = 'system',
    use_name_in_filename = False, # 'system',
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def convert_ui_filters_to_sql(
    column_filters: Dict[int, Dict[str, Any]],
    column_names: Dict[int, str]
) -> Union[Dict, List]:
    """
    Преобразует фильтры из UI в дерево условий для сервисного слоя.

    Args:
        column_filters: {column_index: {'logic': 'AND'/'OR', 'conditions': [...]}}
        column_names: {column_index: name_of_field}

    Returns:
        Словарь вида {'and': [...]} или {'or': [...]} или список (если простой случай).
        Может содержать вложенные узлы.
    """
    if not column_filters:
        return []

    sub_nodes = []
    for col, filter_def in column_filters.items():
        if col not in column_names:
            continue
        col_name = column_names[col]
        logic = filter_def.get('logic', 'AND').upper()
        conditions = filter_def.get('conditions', [])

        if not conditions:
            continue

        # Преобразуем условия столбца в листья
        leaves = []
        for cond in conditions:
            leaf = {'column': col_name, 'operator': cond['operator']}
            if 'value' in cond:
                leaf['value'] = cond['value']
            if 'value2' in cond:
                leaf['value2'] = cond['value2']
            leaves.append(leaf)

        if len(leaves) == 1:
            sub_nodes.append(leaves[0])
        else:
            if logic == 'AND':
                sub_nodes.append({'and': leaves})
            else:  # OR
                sub_nodes.append({'or': leaves})

    if len(sub_nodes) == 0:
        return []
    elif len(sub_nodes) == 1:
        return sub_nodes[0]
    else:
        # Если несколько столбцов с фильтрами, объединяем через AND
        return {'and': sub_nodes}