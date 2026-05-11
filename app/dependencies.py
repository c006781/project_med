# app/dependencies.py

"""
Модуль зависимостей: фабричные функции для получения сервисов и работы с БД.
"""

from functools import lru_cache
import os
from typing import (
    # get_type_hints,
    # Optional,
    get_origin, 
    get_args,
    Union
)
import datetime
# import inspect

from app.utils.logger import AppLogger

# from app.database.database import Database
from app.database import Database
# from .controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import get_config_env
from app.dto.field_configs import (
    PATIENT_CONFIG, 
    APPOINTMENT_CONFIG,
    NOTE_CONFIG, 
    PHOTO_CONFIG,
)
from app.services import (
    PatientService,
    AppointmentService,
    NoteService,
    PhotoService,
    SyncService
)
# from .backend.bd.clinic import create_db
# from .backend.bd.clinic import create_db
# from .backend.bd.temp_data_bd import generate_test_data

from pydantic import BaseModel



# ------------------------------------------------------------
# Глобальный реестр для заметок
# ------------------------------------------------------------
_NOTE_USAGE_MODELS = []   # список кортежей (model_class, [поля_заметок])

from app.dto.field_configs import get_note_fields
def register_note_model(model_class, field_configs):
    fields = get_note_fields(field_configs)
    if fields:
        _NOTE_USAGE_MODELS.append((model_class, fields))

# Автоматическая регистрация всех моделей из MODEL_CONFIG_MAP
from app.dto.field_configs import MODEL_CONFIG_MAP

for model_class, field_configs in MODEL_CONFIG_MAP.items():
    register_note_model(model_class, field_configs)

#############################

_SERVICE_PROVIDERS = []

def register_service_provider(func):
    _SERVICE_PROVIDERS.append(func)
    return func





@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_db() -> Database:
    """
    Возвращает экземпляр Database, сконфигурированный из .env.

    Database - это класс, который инкапсулирует логику работы с базой данных.
    Он принимает строку подключения к базе данных в виде url (например, sqlite:///path/to/db.db).

    Returns:
        Database: экземпляр Database, готовый к работе.
    """
    config = get_config_env()
    db_path = config['database_local_path']
    db_url = f"sqlite:///{db_path}"
    
    # Логгирование: информируем о том, какой файл используется для базы данных
    AppLogger.get_instance(
        name = 'dependencies.py',
        # share_file_with = 'user',
        enable_file_logging = 'user',
        use_name_in_filename = False,  # 'user',
    ).debug(
        f"Возвращает экземпляр Database, сконфигурированный из .env.: {db_path} ({os.path.abspath(db_path)})"
    )

    return Database(db_url)

@register_service_provider
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_patient_service() -> PatientService:
    db = get_db()
    appointment_service = get_appointment_service()   # получаем экземпляр
    return PatientService(
        db, 
        field_configs=PATIENT_CONFIG,
        appointment_service=appointment_service,
    )

@register_service_provider
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_appointment_service() -> AppointmentService:
    db = get_db()
    note_service = get_note_service()
    photo_service = get_photo_service()

    return AppointmentService(
        db, 
        note_service=note_service, 
        photo_service=photo_service,
        field_configs=APPOINTMENT_CONFIG
    )

# def get_appointment_service() -> AppointmentService:
#     db = get_db()
#     note_service = get_note_service()  # можно передать существующий, но проще создать новый
#     return AppointmentService(db, note_service=note_service)

@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def clear_services_cache() -> None:
    """
    Сбрасывает кэш синглтон-сервисов при изменении конфигурации.
    Вызывается в reload_config сервисов, чтобы гарантировать получение
    новых экземпляров с обновлёнными настройками.
    """
    get_patient_service.cache_clear()
    get_appointment_service.cache_clear()
    get_note_service.cache_clear()
    get_photo_service.cache_clear()
    # Если в будущем появятся другие закэшированные сервисы, добавить их сюда

@register_service_provider
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_note_service() -> NoteService:
    """
    Возвращает экземпляр NoteService, инициализированный с помощью Database.
    Returns:
        NoteService: экземпляр NoteService, готовый к работе.
    """
    return NoteService(
        get_db(), 
        field_configs=NOTE_CONFIG
    )

@register_service_provider
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_photo_service() -> PhotoService:
    """
    Возвращает экземпляр PhotoService, инициализированный с помощью Database и пути к хранилищу фотографий.
    """
    config = get_config_env()
    photos_path = config.get(
        'PHOTOS_STORAGE_PATH', 
        # './photos'
        os.path.join(
            '.', 
            'photos'
        ),
    )  # поправить на другой, что бы был адоптив

    return PhotoService(
        get_db(), 
        photos_path, 
        field_configs=PHOTO_CONFIG
    )

@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_sync_service() -> SyncService:
    """
    Возвращает экземпляр SyncService, инициализированный с помощью токена Яндекс.Диска.
    """
    return SyncService()

@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def init_db(
    recreate: bool = False,
    test_data: bool = True
):
    """
    Инициализировать базу данных (создать таблицы, опционально заполнить тестовыми данными).

    :param recreate: bool, optional
        Если True, то удалить существующую базу данных перед инициализацией.
        Defaults to False.
    :param test_data: bool, optional
        Если True, то заполнить тестовыми данными.
        Defaults to True.
    """
    db = get_db()
    db.create_tables(recreate=recreate)
    if test_data:
        db.fill_test_data()

# def get_key_value_dto(
#         dto, 
#         exclude_fields=None
# )->dict:
#     """
#     Выводит все поля DTO в формате "Название поля: значение".
#     :param dto: экземпляр Pydantic DTO
#     :param exclude_fields: список полей, которые не нужно выводить (например, ['id'])
#     """
#     return_ = {}
#     data = dto.model_dump(exclude_none=True)  # исключаем поля с None
#     for key, value in data.items():
#         if exclude_fields and key in exclude_fields:
#             continue
#         # Преобразуем имя поля в заголовок (например, 'first_name' -> 'First Name')
#         title = key.replace('_', ' ').title()
#         return_[title] = value
#         # click.echo(f"{title}: {value}")
#     return return_

@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_text_echo(
    data: dict,  # Pydantic DTO
    exclude_fields: list = None,  # список полей, которые не нужно выводить (например, ['id'])
    if_str_limit: int = None,  # ограничение длины выводимого текста (например, 50)
    rename_map: dict = None,  # словарь переименований полей (например, {'first_name': 'First Name'})
):
    """
    Получает текст для вывода в термінал (например, click.echo).

    :param data: Pydantic DTO
    :param exclude_fields: список полей, которые не нужно выводить (например, ['id'])
    :param if_str_limit: ограничение длины выводимого текста (например, 50)
    :param rename_map: словарь переименования заголовков
    :return: список текстов для вывода в термінал
    """
    # если не указано ограничение длины выводимого текста, то встановим его в 50 символов
    if not if_str_limit:
        if_str_limit = 50

    # если ограничение длины выводимого текста установлено в 0, то не ограничиваем длину выводимого текста
    if if_str_limit <= 0:
        if_str_limit = None

    return_ = []  # список текстов для вывода в термінал

    lists = get_key_value_dto(  # преобразуем Pydantic DTO в словарь
        data,
        exclude_fields,  # список полей, которые не нужно выводить
        rename_map,
    )

    if not isinstance(lists, list):
        lists = [lists]    

    for a in lists:
        text_echo = []  # список строк для вывода в термінал
        for k, v in a.items():  # для каждого поля в словаре
            # если значение поля короче 53 символов, то добавляем к тексту троеточие в конце
            if (if_str_limit is not None) and (len(str(v)) > (if_str_limit+3)):
                text_echo.append(f"{k}: {str(v)[:if_str_limit]}...")  
            else:
                text_echo.append(f"{k}: {v}")  # добавляем к тексту целое значение поля
        text_echo = '\t '.join(text_echo)  # преобразуем список строк в одну строку
        return_.append(text_echo)  # добавляем к списку текст для вывода в термінал
    return return_  # возвращаем список текстов для вывода в термінал

@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_key_value_dto(
    list_,
    exclude_fields: list = None,
    rename_map: dict = None
):
    """
    Преобразует Pydantic DTO в словарь вида {человеко-читаемое название: значение}.
    
  
    :param list_: один DTO или список DTO
    :param exclude_fields: поля для исключения
    :param rename_map: словарь {исходное_имя: новое_имя} для переименования заголовков
    """
    # data = dto.model_dump(exclude_none=True)
    if isinstance(list_, list):
        # for i in list_:
        return [
            get_key_value_dto(i, exclude_fields, rename_map) for i in list_
        ]
    else:
        data = {}
        # Если передан объект с методом model_dump (Pydantic модель), используем его
        if hasattr(list_, 'model_dump'):
            items = list_.model_dump(exclude_none=True).items()
        elif isinstance(list_, dict):
            items = list_.items()
        else:
            # fallback для других случаев
            items = dict(list_).items()

        for k, v in items:
            if exclude_fields and k in exclude_fields:
                continue

            # Применяем переименование, если есть
            if rename_map and k in rename_map:
                title = rename_map[k]
            else:
                # Стандартное преобразование: замена подчёркиваний на пробелы и капитализация
                title = k.replace('_', ' ').title()

            data[title] = v

        return data
    
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_dto_fields(dto_class: BaseModel, exclude: list = None):
    """
    Возвращает список полей DTO с метаданными: имя, тип, обязательное ли.
    
    :param dto_class: класс Pydantic модели
    :param exclude: список полей, которые не нужно выводить
    """
    # исключаем поля из списка exclude
    exclude = exclude or []
    fields = []

    # перебираем все поля DTO
    for name, field in dto_class.model_fields.items():
        # если поле не должно быть исключено, то продолжаем
        if name in exclude:
            continue

        # получаем тип поля
        field_type = field.annotation
        # если тип поля Optional, то получаем реальный тип
        is_optional = False
        origin = get_origin(field_type)

        # if get_origin(field_type) is Optional:
        if origin is Union and type(None) in get_args(field_type):
            is_optional = True
            # получаем реальный тип
            args = get_args(field_type)
            field_type = args[0] if args else None

        # добавляем поле в список
        fields.append({
            # имя поля
            'name': name,
            # тип поля
            'type': field_type,
            # является ли поле обязательным
            'required': not is_optional and field.is_required(),
            # описание поля
            'description': field.description or name.replace('_', ' ').title()
        })

    return fields
    
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def create_click_options(dto_class: BaseModel, action='create'):
    """
    Возвращает декоратор с опциями click, соответствующими полям DTO.
    Для action='update' поле id добавляется как required.
    """
    import click
    exclude = ['id'] if action == 'create' else []
    fields = get_dto_fields(dto_class, exclude=exclude)

    def decorator(func):
        for f in fields:
            name = f['name']
            opt_name = f'--{name.replace("_", "-")}'
            # Для update поля необязательны
            required = f['required'] if action == 'create' else False
            field_type = f['type']
            description = f['description']

            # Определяем тип опции в click
            if field_type == str:
                param_type = str

            elif field_type == int:
                param_type = int

            elif field_type == datetime.date:
                param_type = str  # будем парсить отдельно

            elif field_type == datetime.time:
                param_type = str

            else:
                param_type = str  # fallback

            # Добавляем опцию
            decorator_func = click.option(
                opt_name,
                required=required,
                type=param_type,
                help=description
            )

            func = decorator_func(func)

        return func

    return decorator
    
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def collect_dto_from_input(
    dto_class: BaseModel, 
    exclude: list = None, 
    rename_map: dict = None
):
    """
    В интерактивном режиме запрашивает у пользователя значения полей DTO.
    Возвращает словарь {имя_поля: значение} с преобразованными типами.
    
    :param dto_class: класс Pydantic модели
    :param exclude: список полей для исключения
    :param rename_map: словарь для переименования заголовков {имя_поля: отображаемое имя}
    """
    import click
    
    # исключаем поля из списка exclude
    exclude = exclude or []

    # получаем список полей DTO с метаданными: имя, тип, обязательное ли
    fields = get_dto_fields(dto_class, exclude=exclude)
    data = {}

    # перебираем все поля DTO
    for f in fields:
        # если есть rename_map, используем его, иначе берем description из поля
        display_name = rename_map.get(f['name'], f['description']) if rename_map else f['description']
        # формируем запрос для ввода
        prompt = f"{display_name}" + (" (обязательно)" if f['required'] else "")

        # цикл ввода
        while True:
            # просим пользователя ввести значение
            value = click.prompt(
                prompt,
                default="",
                show_default=False
            )

            # если поле не является обязательным и пользователь ничего не ввёл
            if not value and not f['required']:
                # добавляем поле в словарь с None
                data[f['name']] = None
                break

            # если поле является обязательным и пользователь ничего не ввёл
            if not value and f['required']:
                # выводим сообщение об ошибке
                click.echo("Поле обязательно. Повторите ввод.")
                continue

            if not value and not f['required']:
                data[f['name']] = None
                break

            try:
                # если тип поля int, то преобразуем строку в int
                if f['type'] == int:
                    data[f['name']] = int(value)

                # если тип поля datetime.date, то преобразуем строку в datetime.date
                elif f['type'] == datetime.date:
                    data[f['name']] = datetime.date.fromisoformat(value)

                # если тип поля datetime.time, то преобразуем строку в datetime.time
                elif f['type'] == datetime.time:
                    data[f['name']] = datetime.time.fromisoformat(value)

                else:
                    # если тип поля не int, datetime.date, datetime.time, то оставляем строку как есть
                    data[f['name']] = value

                break

            except ValueError as e:
                # выводим сообщение об ошибке
                err_ = f"Неверный формат для типа {f['type'].__name__}. Попробуйте снова"

                AppLogger.get_instance(
                    name = 'user'
                ).exception(f"{err_}: {e}")

                click.echo(f"{err_}.")

    return data

AppLogger.get_instance(
    name='dependencies.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def create_database(db_path: str, fill_test_data: bool = False) -> None:
    """
    Создаёт базу данных по указанному пути (если её нет) и опционально заполняет тестовыми данными.
    
    :param db_path: путь к файлу БД.
    :param fill_test_data: если True, заполняет тестовыми данными после создания таблиц.
    """
    # from app.database import Database
    db = Database(f"sqlite:///{db_path}")
    if fill_test_data:
        db.fill_test_data()
        
    db.close()