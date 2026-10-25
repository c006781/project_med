# app/utils/virtual_fields.py

"""
Утилита для вычисления виртуальных полей на основе конфигурации.

Виртуальное поле — поле DTO, которого нет в таблице: его значение вычисляется функцией из
конфигурации поля (ключ ``compute``: ``func``, ``args`` — имена аргументов, ``kwargs``) или
берётся из ``extra_data`` (связи ORM-объекта по ``source_attr``, значения ``sql_compute``).

Пример:
    >>> configs = {'full_name': {'compute': {
    ...     'func': lambda last, first: f'{last} {first}',
    ...     'args': ['last_name', 'first_name']}}}
    >>> compute_virtual_fields({'last_name': 'Иванов', 'first_name': 'Иван'}, configs)['full_name']
    'Иванов Иван'
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
# def compute_virtual_fields(
#     data: Dict[str, Any],
#     field_configs: Dict[str, Dict[str, Any]],
#     extra_data: Optional[Dict[str, Any]] = None
# ) -> Dict[str, Any]:
# ↑ до 2026-10-25 (VF2): сигнатура без комментариев к параметрам (формат skill п. 7 —
#   правимая функция приводится к нему).
def compute_virtual_fields(
    data          : Dict[str, Any],                    # исходные данные (форма, DTO)
    field_configs : Dict[str, Dict[str, Any]],         # конфигурация полей
    extra_data    : Optional[Dict[str, Any]] = None,   # дополнительные данные (связи и т. п.)
) -> Dict[str, Any]:
    """
    Вычисляет значения для полей, у которых в конфигурации есть ключ 'compute'.

    Аргумент вычисления (имя из ``compute['args']``) ищется сначала в ``data`` (и уже
    вычисленных полях — порядок конфигурации), затем в ``extra_data``; нет нигде — ``None``.
    Поля без ``compute`` или с невызываемой ``func`` пропускаются. Ошибка функции — поле
    ``None`` (в журнал), остальные поля вычисляются. Исходный ``data`` не меняется.

    Args:
        data: Исходный словарь данных (например, из формы).
        field_configs: Конфигурация полей ``{имя: {'compute': {'func', 'args', 'kwargs'}, …}}``.
        extra_data: Дополнительные данные для аргументов (None — пустой словарь, VF1).

    Returns:
        Dict[str, Any]: Копия ``data`` с вычисленными полями.

    Пример:
        >>> configs = {'age_text': {'compute': {'func': lambda age, unit: f'{age} {unit}',
        ...                                     'args': ['age'], 'kwargs': {'unit': 'лет'}}}}
        >>> compute_virtual_fields({'age': 30}, configs)
        {'age': 30, 'age_text': '30 лет'}
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
# def enrich_dto_with_computed_fields(
#     dto: BaseModel,
#     model_obj: Any,
#     field_configs: Dict[str, Dict[str, Any]],
#     extra_data: Optional[Dict[str, Any]] = None,
# ) -> BaseModel:
# ↑ до 2026-10-25 (VF2): сигнатура без комментариев к параметрам (формат skill п. 7 —
#   правимая функция приводится к нему).
def enrich_dto_with_computed_fields(
    dto           : BaseModel,                         # DTO, который заполняется (меняется на месте)
    model_obj     : Any,                               # ORM-объект — источник связей (source_attr)
    field_configs : Dict[str, Dict[str, Any]],         # конфигурация полей
    extra_data    : Optional[Dict[str, Any]] = None,   # дополнительные данные (дополняется!)
) -> BaseModel:
    """
    Заполняет виртуальные поля DTO значениями из вычислений.

    Алгоритм:
        1. В ``extra_data`` добавляются связи ``model_obj`` по ``source_attr`` конфигурации
           (незагруженная связь с ``eager_load: False`` не грузится — DATA12, без N+1).
        2. ``compute_virtual_fields`` по непустым полям DTO и ``extra_data``.
        3. Виртуальные поля без вычисления берутся из ``extra_data`` (``sql_compute``).
        4. В DTO записываются только вычисленные и виртуальные поля, и только не ``None``
           (B5: обычные поля обратно не пишутся — вложенные DTO не превращаются в словари).

    Переданный ``extra_data`` дополняется на месте (связи из шага 1).

    Args:
        dto: DTO, который нужно обогатить.
        model_obj: ORM-объект, из которого можно извлечь связанные данные (по source_attr).
        field_configs: Конфигурация полей.
        extra_data: Дополнительные данные для вычислений (будет дополнено из model_obj).

    Returns:
        BaseModel: Тот же объект ``dto`` (заполненный).

    Пример:
        >>> configs = {'patient_name': {'virtual': True, 'source_attr': 'patient',
        ...            'compute': {'func': lambda p: p.full_name, 'args': ['patient']}}}
        >>> enrich_dto_with_computed_fields(dto, appointment, configs).patient_name
        'Иванов Иван'
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
