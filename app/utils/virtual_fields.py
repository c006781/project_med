# app/utils/virtual_fields.py

"""
Утилита для вычисления виртуальных полей на основе конфигурации.
"""

from typing import (
    Dict, 
    Any, 
    Optional, 
    # Callable,
)

from app.utils.logger.logger import AppLogger

@AppLogger.get_instance(
    name='system',
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def compute_virtual_fields(
    data: Dict[str, Any], 
    field_configs: Dict[str, Dict[str, Any]],
    extra_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Вычисляет значения для полей, у которых в конфигурации есть ключ 'compute'.

    :param data: исходный словарь данных (например, из формы)
    :param field_configs: конфигурация полей
    :param extra_data: дополнительные данные (например, из extra_data)
    :return: словарь с вычисленными значениями (может содержать и исходные поля)
    """
    result = data.copy()
    for field_name, config in field_configs.items():
        compute = config.get('compute')
        if not compute:
            continue

        func = compute.get('func')
        if not callable(func):
            continue

        args = []
        for arg_name in compute.get('args', []):
            if arg_name in result:
                args.append(result[arg_name])
            elif extra_data and arg_name in extra_data:
                args.append(extra_data[arg_name])
            else:
                args.append(None)

        kwargs = compute.get('kwargs', {})

        try:
            value = func(*args, **kwargs)
            result[field_name] = value
        except Exception as e:
            AppLogger.get_instance( name = 'user').error(f"Ошибка вычисления виртуального поля {field_name}: {e}")
            # при ошибке оставляем None
            result[field_name] = None
    return result