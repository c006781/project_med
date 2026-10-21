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

from pydantic import BaseModel


@AppLogger.get_instance(
    name='virtual_fields.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
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
    result = data.copy() # копируем исходный словарь
    # extra_data=None (значение по умолчанию) — пустой словарь: журнал ниже проверяет
    # `arg_name in extra_data` (раньше TypeError на первом же поле с аргументами, VF1)
    extra_data = extra_data or {}
    logger =  AppLogger.get_instance(
        name='api.virtual_fields.py',
        enable_file_logging = 'user',
        use_name_in_filename = False,
    )
    for field_name, config in field_configs.items():
        compute = config.get('compute') # получаем словарь вычислений
        
        if not compute:
            continue

        func = compute.get('func') # получаем функцию
        if not callable(func):
            continue

        args = []
        for arg_name in compute.get('args', []): # получаем позиционные аргументы
            logger.debug(
                f"arg_name = {arg_name}: "
                # f"in result ({result}) = {arg_name in result} "
                f"in result = {arg_name in result} "
                # f"| in extra_data ({extra_data}) = {arg_name in extra_data}"
                f"| in extra_data = {arg_name in extra_data}"
            )
            if arg_name in result: # если аргумент есть в исходном словаре
                args.append(result[arg_name])

            elif extra_data and (arg_name in extra_data): # если аргумент есть в дополнительном словаре
                args.append(extra_data[arg_name])

            else: 
                args.append(None)

        kwargs = compute.get('kwargs', {})

        try:
            value = func(*args, **kwargs)
            result[field_name] = value

            logger.debug(
                f"compute_virtual_fields: "
                f"вычисление виртуального поля {field_name}: "
                f"args = {args}, "
                f"kwargs = {kwargs}, "
                f"value = {value}"
            )

            # 0==0

        except Exception as e:
            logger.error(f"Ошибка вычисления виртуального поля {field_name}: {e}")
            # при ошибке оставляем None
            result[field_name] = None
            
    return result

@AppLogger.get_instance(
    name='virtual_fields.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def enrich_dto_with_computed_fields(
    dto: BaseModel,
    model_obj: Any,
    field_configs: Dict[str, Dict[str, Any]],
    extra_data: Optional[Dict[str, Any]] = None,
) -> BaseModel:
    """
    Заполняет виртуальные поля DTO значениями из вычислений.

    :param dto: DTO, который нужно обогатить.
    :param model_obj: ORM-объект, из которого можно извлечь связанные данные (по source_attr).
    :param field_configs: конфигурация полей.
    :param extra_data: дополнительные данные для вычислений (будет дополнено из model_obj).
    :return: обогащённый DTO.
    """

    # AppLogger.get_instance( name='user',  ).debug(
    #     f" model_obj: {model_obj} field_configs: {field_configs} extra_data: {extra_data}"
    # )

    logger =  AppLogger.get_instance(
        name='api.virtual_fields.py',
        enable_file_logging = 'user',
        use_name_in_filename = False,
    )

    logger.debug(
        f"extra_data: {extra_data}"
    )

    if extra_data is None:
        extra_data = {}

    # Собираем данные из model_obj по source_attr
    # DATA12 (2026-10-16): связь берётся, только если она УЖЕ загружена. Раньше getattr
    # на незагруженной связи запускал ленивую загрузку на КАЖДУЮ запись (N+1: страница из
    # 50 приёмов — 52 запроса из-за has_photos → photos, хотя число фото уже посчитано
    # одним подзапросом sql_compute). Нужные связи загружаются заранее по конфигу.
    try:
        from sqlalchemy import inspect as _sa_inspect
        unloaded = _sa_inspect(model_obj).unloaded
    except Exception:
        unloaded = set()

    # Не грузим только то, что конфиг просит не грузить заранее (eager_load: False) —
    # остальные связи при необходимости догружаются (заметки новой записи и т. п.)
    no_lazy = {config.get('source_attr') for config in field_configs.values()
               if config.get('eager_load') is False and config.get('source_attr')}
    for config in field_configs.values():
        source_attr = config.get('source_attr')
        if source_attr in unloaded and source_attr in no_lazy:
            continue

        logger.debug(
            f"config: {config} "
            f"source_attr: {source_attr} "
            f"result: {source_attr and source_attr not in extra_data}"
        )
        if source_attr and source_attr not in extra_data:
            val = getattr(model_obj, source_attr, None)
            if val is not None:
                extra_data[source_attr] = val
                logger.debug(
                    f"Добавлен {source_attr} в extra_data"
                )

    # Текущие данные DTO (только поля, не None)
    current_data = dto.model_dump(exclude_none=True)

    # Вычисляем виртуальные поля
    computed = compute_virtual_fields(
        current_data, 
        field_configs, 
        extra_data
    )

    # Дополнительно: переносим значения из extra_data для виртуальных полей,
    # которые имеют sql_compute (или просто присутствуют в extra_data и не были вычислены)
    for field_name, config in field_configs.items():
        if config.get('virtual', False) and field_name not in computed:
            if extra_data and field_name in extra_data:
                computed[field_name] = extra_data[field_name]
                logger.debug(f"Поле {field_name} взято из extra_data: {extra_data[field_name]}")

    # Применяем к DTO
    # for field_name, value in computed.items():
    # ↑ до B5 (2026-10-16): обратно записывались ВСЕ поля из model_dump — вложенные DTO
    #   (photos у приёма) превращались в словари (предупреждение pydantic при выгрузке).
    #   Теперь — только вычисленные (compute) и виртуальные из extra_data.
    produced = {
        name for name, config in field_configs.items()
        if config.get('compute') or (config.get('virtual', False) and name not in current_data)
    }
    for field_name, value in computed.items():
        if field_name not in produced:
            continue

        logger.debug(
            f"field_name: {field_name} "
            # f"value: {value} "
            f"result: {value is not None and hasattr(dto, field_name)}"
        )
        if value is not None and hasattr(dto, field_name):
            setattr(dto, field_name, value)

    # AppLogger.get_instance( name='user',  ).debug(
    #     # f"computed: {computed} dto: {dto}"
    #     f"computed: {computed} dto: {dto}"
    # )

    return dto
