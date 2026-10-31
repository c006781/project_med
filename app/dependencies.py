# app/dependencies.py

"""
Сборка приложения: общая база, поставщики сервисов, применитель настроек, помощники CLI.

Что здесь:
    * общая база — :func:`get_db` (один ``Database`` на приложение, ТД-6), :func:`reopen_db`,
      :func:`close_db`; создание файла базы — :func:`init_db`, :func:`create_database`;
    * поставщики сервисов ``get_*_service`` — ``lru_cache`` (один объект на приложение) и
      реестр ``_SERVICE_PROVIDERS`` (:func:`register_service_provider`): по нему
      ``ConfigApplier`` перезагружает сервисы, :func:`clear_services_cache` сбрасывает кэш;
      вне реестра — :func:`get_sync_service` (DP4) и :func:`get_patient_merge_service` (DP5);
    * :func:`create_config_applier` — ``ConfigApplier`` с обработчиками сервисов (К6);
    * помощники командной строки — :func:`get_text_echo`, :func:`get_key_value_dto`,
      :func:`get_dto_fields`, :func:`create_click_options`, :func:`collect_dto_from_input`.

Подробно — ``app/DEPENDENCIES.md``.

Example:
    >>> from app.dependencies import get_db, get_patient_service
    >>> get_patient_service()._db is get_db()
    True
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
from typing import Any, Callable, List # реестр поставщиков сервисов
from typing import Optional, Tuple      # общий Database приложения (ТД-6)
from typing import TYPE_CHECKING, Dict  # аннотации (сверка Ф1.6.11)
import datetime
import threading                        # общий Database: get_db из разных потоков (ТД-6)
# import inspect

from app.utils.logger import AppLogger

# from app.database.database import Database
from app.database import Database
# from .controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import get_config_env
# Применитель настроек получает сервисы отсюда (К6, 2026-10-25): app.config не импортирует
# app.dependencies, связь только сверху вниз.
from app.config.config_applier import ConfigApplier, ServiceHooks
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

if TYPE_CHECKING: # только для аннотации get_patient_merge_service (импорт — внутри функции)
    from app.services.patient_merge import PatientMergeService



# ------------------------------------------------------------
# Глобальный реестр для заметок
# ------------------------------------------------------------
# _NOTE_USAGE_MODELS = []   # список кортежей (model_class, [поля_заметок])
#
# from app.dto.field_configs import get_note_fields
# def register_note_model(model_class, field_configs):
#     fields = get_note_fields(field_configs)
#     if fields:
#         _NOTE_USAGE_MODELS.append((model_class, fields))
#
# # Автоматическая регистрация всех моделей из MODEL_CONFIG_MAP
# from app.dto.field_configs import MODEL_CONFIG_MAP
#
# for model_class, field_configs in MODEL_CONFIG_MAP.items():
#     register_note_model(model_class, field_configs)
# ↑ до rework-dependencies (2026-10-21): реестр моделей с заметками не читается с DYN2
#   (2026-10-16) — сервис заметок узнаёт ссылки из схемы БД (внешние ключи). Регистрация
#   при импорте была мёртвым кодом (DP3; app/dto/IMPLEMENTATION.md DT5).

#############################

# Поставщики сервисов (get_*_service): перезагрузка настроек (ConfigApplier) и сброс кэша
# (clear_services_cache) идут по этому списку — новый сервис достаточно пометить декоратором
_SERVICE_PROVIDERS: List[Callable[[], Any]] = []


def register_service_provider(
    func : Callable[[], Any],   # поставщик сервиса (обычно обёрнут lru_cache)
) -> Callable[[], Any]: # добавляет поставщика в реестр _SERVICE_PROVIDERS
    """
    Регистрирует поставщика сервиса.

    Порядок декораторов: ``@register_service_provider`` снаружи, ``@lru_cache`` под ним —
    тогда зарегистрирован кэширующий поставщик (у него есть ``cache_clear``). Сервис
    поставщика должен уметь ``reload_config()`` — его зовёт ``ConfigApplier.apply_database``.

    Args:
        func : (Callable) Поставщик сервиса.

    Returns:
        (Callable) Тот же поставщик.

    Example:
        >>> @register_service_provider
        ... @lru_cache(maxsize=1)
        ... def get_my_service():
        ...     return object()
        >>> get_my_service in _SERVICE_PROVIDERS
        True
        >>> _SERVICE_PROVIDERS.remove(get_my_service)   # убрать пример из реестра
    """
    _SERVICE_PROVIDERS.append(func)
    return func





class _SharedDatabase:
    """
    Хранит общий ``Database`` приложения и настройки, с которыми он открыт (ТД-6).

    Один объект на приложение: все сервисы работают через один движок и одну
    ``scoped_session`` потока. Сам ничего не открывает — это делают :func:`get_db`,
    :func:`reopen_db`, :func:`close_db` (под ``lock``: базу могут запросить из разных
    потоков — окно, синхронизация, импорт).

    Attributes:
        db   : (Database/None) Открытая общая база; None — ещё не открывалась или закрыта
            :func:`close_db`.
        key  : (tuple/None) ``(URL, LOG_SQL_PARAMS)``, с которыми открыта ``db``.
        lock : (threading.RLock) Блокировка открытия и замены базы.

    Example:
        >>> holder = _SharedDatabase()
        >>> holder.db is None
        True
    """

    def __init__(self) -> None:
        """
        Создаёт пустое хранилище: база ещё не открыта.

        Example:
            >>> _SharedDatabase().key is None
            True
        """
        self.db   : Optional[Database]         = None               # общая база
        self.key  : Optional[Tuple[str, bool]] = None               # (URL, LOG_SQL_PARAMS) базы
        self.lock : threading.RLock            = threading.RLock()  # открытие и замена


# Общий Database приложения (ТД-6, 2026-10-31). Тесты подменяют объект целиком
# (monkeypatch.setattr(deps, '_shared_db', _SharedDatabase())).
_shared_db = _SharedDatabase()


def _db_settings() -> Tuple[str, str, bool]: # путь, URL и флаг значений запросов из настроек
    """
    Читает из настроек путь к базе (``database_local_path``) и флаг ``LOG_SQL_PARAMS``.

    Returns:
        (tuple) ``(путь, URL sqlite:///путь, log_sql_params)``; нет флага — значения
            запросов скрыты (``False``).

    Example:
        >>> _db_settings()
        ('clinic.db', 'sqlite:///clinic.db', False)
    """
    config = get_config_env()
    db_path = config['database_local_path']
    log_sql_params = bool(
        config.get(
            'LOG_SQL_PARAMS',   # значения запросов в журнал
            False,              # нет ключа — скрыты
        ),
    )
    return db_path, f"sqlite:///{db_path}", log_sql_params


def _open_db(
    db_path        : str,    # путь к файлу (для журнала)
    db_url         : str,    # URL подключения
    log_sql_params : bool,   # значения запросов в журнал
) -> Database: # открывает новую базу и пишет в журнал, какой файл
    """
    Открывает новый ``Database`` и пишет в журнал пользователя, какой файл открыт.

    Args:
        db_path        : (str) Путь к файлу базы.
        db_url         : (str) URL подключения (``sqlite:///…``).
        log_sql_params : (bool) Значения запросов в журнал.

    Returns:
        (Database) Открытая база.

    Raises:
        DatabaseConnectionError: Базу не удалось открыть (занята, нет доступа).
        MigrationError: Базу нельзя безопасно обновить.

    Example:
        >>> db = _open_db(
        ...     'clinic.db',              # путь
        ...     'sqlite:///clinic.db',    # URL
        ...     False,                    # значения запросов скрыты
        ... )
    """
    AppLogger.get_instance(
        name                 = 'dependencies.py',   # журнал сборки
        enable_file_logging  = 'user',              # файл пользователя
        use_name_in_filename = False,               # имя не в имени файла
    ).debug(
        f"Открывается база: {db_path} ({os.path.abspath(db_path)})"
    )
    return Database(
        db_url,
        log_sql_params   =   log_sql_params,   # значения запросов в журнал
    )


@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_db() -> Database: # общий Database приложения (открывается при первом вызове)
    """
    Возвращает общий для приложения ``Database`` (ТД-6): путь — ``database_local_path``,
    значения запросов в журнал — ``LOG_SQL_PARAMS`` (по умолчанию скрыты).

    Первый вызов открывает базу, следующие отдают тот же объект — все сервисы работают
    через один движок и одну сессию потока (``scoped_session``). Новая база открывается,
    если общая закрыта (``Database.closed``: сервис закрыл её в ``reload_config``) или
    настройки (путь, флаг) сменились без :func:`reopen_db`; прежнюю в этом случае
    закрывает тот, кто её держит (сервис — в ``reload_config``). При смене настроек на
    экране базу переоткрывает ``ConfigApplier.apply_database`` (:func:`reopen_db`).

    Returns:
        (Database) База, готовая к работе.

    Raises:
        DatabaseConnectionError: Базу не удалось открыть (занята, нет доступа).
        MigrationError: Базу нельзя безопасно обновить.

    Example:
        >>> db = get_db()
        >>> db is get_db()
        True
        >>> db.log_sql_params
        False
    """
    # ↑ до 2026-10-31 (М8): описание — «из .env» (настройки — из менеджера), без флага.
    # config = get_config_env()
    # db_path = config['database_local_path']
    # db_url = f"sqlite:///{db_path}"
    # log_sql_params = bool(
    #     config.get(
    #         'LOG_SQL_PARAMS',   # значения запросов в журнал
    #         False,              # нет ключа — скрыты
    #     ),
    # )
    #
    # # Логгирование: информируем о том, какой файл используется для базы данных
    # AppLogger.get_instance(
    #     name = 'dependencies.py',
    #     # share_file_with = 'user',
    #     enable_file_logging = 'user',
    #     use_name_in_filename = False,  # 'user',
    # ).debug(
    #     f"Возвращает экземпляр Database, сконфигурированный из .env.: {db_path} ({os.path.abspath(db_path)})"
    # )
    #
    # # return Database(db_url)
    # # ↑ до 2026-10-31 (М8): без флага LOG_SQL_PARAMS.
    # return Database(
    #     db_url,
    #     log_sql_params   =   log_sql_params,   # значения запросов в журнал
    # )
    # ↑ до 2026-10-31 (ТД-6): новый Database на каждый вызов — у каждого сервиса своё
    #   подключение к одному файлу SQLite (транзакция одного не видела незафиксированного
    #   другого, блокировки файла делились между ними).
    db_path, db_url, log_sql_params = _db_settings()
    key = (db_url, log_sql_params)
    with _shared_db.lock:
        db = _shared_db.db
        if db is not None and not db.closed and _shared_db.key == key:
            return db
        # Базы нет, она закрыта или настройки сменились — открыть по текущим
        db = _open_db(
            db_path,          # путь (журнал)
            db_url,           # URL
            log_sql_params,   # значения запросов в журнал
        )
        _shared_db.db, _shared_db.key = db, key
        return db


@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def reopen_db() -> Database: # открывает общую базу по текущим настройкам, прежнюю закрывает
    """
    Переоткрывает общий ``Database`` по текущим настройкам (ТД-6): сначала открывает новый,
    потом закрывает прежний (``engine.dispose()``, ``scoped_session.remove()``).

    Вызывает ``ConfigApplier.apply_database`` (обработчик ``ServiceHooks.reopen_database``)
    до перезагрузки сервисов: сервис в ``reload_config`` закрывает свою (уже закрытую)
    базу и получает из :func:`get_db` новую. Новая не открылась — исключение, общей
    остаётся прежняя, открытая: сервисы продолжают работать со старой базой.

    Returns:
        (Database) Новая общая база.

    Raises:
        DatabaseConnectionError: Новую базу не удалось открыть (прежняя не тронута).
        MigrationError: Новую базу нельзя безопасно обновить (прежняя не тронута).

    Example:
        >>> old = get_db()
        >>> new = reopen_db()
        >>> (new is get_db(), old.closed)
        (True, True)
    """
    db_path, db_url, log_sql_params = _db_settings()
    with _shared_db.lock:
        new_db = _open_db(
            db_path,          # путь (журнал)
            db_url,           # URL
            log_sql_params,   # значения запросов в журнал
        )
        old_db = _shared_db.db
        _shared_db.db, _shared_db.key = new_db, (db_url, log_sql_params)
    if old_db is not None and not old_db.closed: # прежняя общая база больше не нужна
        old_db.close()
    return new_db


def close_db() -> None: # закрывает общую базу; следующий get_db откроет новую
    """
    Закрывает общий ``Database`` (если открыт) и забывает его: следующий :func:`get_db`
    откроет базу заново (ТД-6).

    Для завершения работы, замены файла базы и тестов. Сервисы, которые держат закрытую
    базу, получат новую при ``reload_config``.

    Example:
        >>> db = get_db()
        >>> close_db()
        >>> (db.closed, get_db() is db)
        (True, False)
    """
    with _shared_db.lock:
        db = _shared_db.db
        _shared_db.db, _shared_db.key = None, None
    if db is not None and not db.closed: # базу открывали — закрыть
        db.close()

@register_service_provider
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_patient_service() -> PatientService: # общий сервис пациентов (кэш, реестр)
    """
    Возвращает общий для приложения ``PatientService`` (создаётся при первом вызове).

    База — общая (:func:`get_db`), сервис приёмов — :func:`get_appointment_service` (нужен
    для каскадного удаления приёмов пациента). Кэш ``lru_cache`` и реестр
    ``_SERVICE_PROVIDERS``: при смене базы ``ConfigApplier`` перезагружает этот же объект.

    Returns:
        (PatientService) Сервис пациентов.

    Example:
        >>> get_patient_service() is get_patient_service()
        True
    """
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
def get_appointment_service() -> AppointmentService: # общий сервис приёмов (кэш, реестр)
    """
    Возвращает общий для приложения ``AppointmentService`` (создаётся при первом вызове).

    База — общая (:func:`get_db`); сервисы заметок и фото — :func:`get_note_service`,
    :func:`get_photo_service` (тексты заметок и фото приёма). Кэш и реестр — как у
    :func:`get_patient_service`.

    Returns:
        (AppointmentService) Сервис приёмов.

    Example:
        >>> get_appointment_service()._db is get_db()
        True
    """
    db = get_db()
    note_service = get_note_service()
    photo_service = get_photo_service()

    return AppointmentService(
        db, 
        note_service=note_service, 
        photo_service=photo_service,
        field_configs=APPOINTMENT_CONFIG
    )

def get_patient_merge_service() -> 'PatientMergeService': # объединение пациентов-дублей
    """
    Возвращает сервис поиска и объединения пациентов-дублей (Ф1.6.10а).

    Собирается при каждом вызове из текущих (кэшированных) базы и сервисов пациентов и
    приёмов — своего состояния нет, после смены настроек берёт уже новые. Не в реестре
    ``_SERVICE_PROVIDERS`` и без кэша: реестр при смене настроек зовёт ``reload_config()``,
    которого у этого сервиса нет (и не нужно).

    Returns:
        (PatientMergeService) Сервис объединения.

    Example:
        >>> plan = get_patient_merge_service().plan_merge(12, [40])
    """
    from app.services.patient_merge import PatientMergeService
    return PatientMergeService(
        db                    =   get_db(),                    # база
        patient_service       =   get_patient_service(),       # пациенты
        appointment_service   =   get_appointment_service(),   # приёмы
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
def clear_services_cache() -> None: # сбрасывает кэш поставщиков реестра
    """
    Сбрасывает кэш всех поставщиков реестра ``_SERVICE_PROVIDERS`` (у кого есть
    ``cache_clear``): следующий ``get_*_service()`` создаст новый объект.

    Приложение при смене настроек кэш НЕ сбрасывает (страницы окна держат прежние объекты —
    их перезагружает ``ConfigApplier.apply_database``); функция — для тестов и сборки заново.
    Общую базу (:func:`close_db`) и ``get_sync_service`` (вне реестра) не трогает.

    Example:
        >>> service = get_patient_service()
        >>> clear_services_cache()
        >>> get_patient_service() is service
        False
    """
    # get_patient_service.cache_clear()
    # get_appointment_service.cache_clear()
    # get_note_service.cache_clear()
    # get_photo_service.cache_clear()
    # # Если в будущем появятся другие закэшированные сервисы, добавить их сюда
    # ↑ до rework-dependencies (2026-10-21): список вручную — новый сервис легко забыть (DP2).
    #   Теперь — все зарегистрированные поставщики с кэшем.
    for provider in _SERVICE_PROVIDERS:
        cache_clear = getattr(provider, 'cache_clear', None)
        if callable(cache_clear):
            cache_clear()

@register_service_provider
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_note_service() -> NoteService: # общий сервис заметок (кэш, реестр)
    """
    Возвращает общий для приложения ``NoteService`` на общей базе (:func:`get_db`).

    Кэш и реестр — как у :func:`get_patient_service`.

    Returns:
        (NoteService) Сервис заметок.

    Example:
        >>> get_note_service() is get_appointment_service()._note_service
        True
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
def get_photo_service() -> PhotoService: # общий сервис фото (кэш, реестр)
    """
    Возвращает общий для приложения ``PhotoService`` на общей базе (:func:`get_db`).

    Папка фото — ``PHOTOS_STORAGE_PATH`` (нет — ``./photos``); смену папки применяет
    ``ConfigApplier.apply_photos_storage``. Кэш и реестр — как у :func:`get_patient_service`.

    Returns:
        (PhotoService) Сервис фото.

    Example:
        >>> get_photo_service() is get_appointment_service()._photo_service
        True
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

# Кэш — один объект на приложение (Ф1.6.10в, 2026-10-31); в реестр _SERVICE_PROVIDERS не
# включён: реестр перезагружается при смене базы (apply_database), а токен и пути
# SyncService получает от ConfigApplier.apply_sync; clear_services_cache по реестру сбросил
# бы общий объект — окно осталось бы со старым
@lru_cache(maxsize=1)
@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def get_sync_service() -> SyncService: # общий сервис синхронизации
    """
    Возвращает общий для приложения ``SyncService`` (создаётся при первом вызове).

    Кэшируется (``lru_cache``): окно (``MainWindow.sync_service``), командная строка и
    ``ConfigApplier.apply_sync`` работают с одним объектом — смена токена Яндекс.Диска и
    путей синхронизации в настройках доходит до окна. Раньше каждый вызов создавал новый
    объект, и ``apply_sync`` правил временный (ОСТ п. 1.8). Токен и пути объект читает из
    ``.env`` один раз при создании; новый объект — после ``get_sync_service.cache_clear()``.

    Returns:
        (SyncService) Сервис синхронизации.

    Example:
        >>> get_sync_service() is get_sync_service()
        True
    """
    return SyncService()


def create_config_applier() -> ConfigApplier: # применитель настроек с сервисами приложения
    """
    Применитель настроек с обработчиками сервисов приложения (К6, 2026-10-25).

    ``app.config`` больше не импортирует этот модуль: сервисы передаются применителю
    отсюда. Поставщики берутся из реестра в момент применения (``_SERVICE_PROVIDERS`` —
    те же объекты из кэша, что у страниц GUI). Новый применитель на каждый вызов: у него
    свои ``errors`` последнего применения. При смене пути базы или ``LOG_SQL_PARAMS``
    применитель сначала переоткрывает общую базу (:func:`reopen_db`, ТД-6), потом
    перезагружает сервисы.

    Returns:
        (ConfigApplier) Применитель с ``ServiceHooks``.

    Example:
        >>> applier = create_config_applier()
        >>> applier.apply_changes(old_config, new_config)
        {'database', 'sync'}
        >>> applier.errors
        {}
    """
    # return ConfigApplier(
    #     services = ServiceHooks(
    #         service_providers = lambda: list(_SERVICE_PROVIDERS),  # реестр на момент применения
    #         photo_service     = get_photo_service,                 # сервис фото (кэш)
    #         sync_service      = get_sync_service,                  # сервис синхронизации
    #     ),
    # )
    # ↑ до 2026-10-31 (ТД-6): без переоткрытия общей базы — у каждого сервиса была своя.
    return ConfigApplier(
        services = ServiceHooks(
            service_providers = lambda: list(_SERVICE_PROVIDERS),  # реестр на момент применения
            photo_service     = get_photo_service,                 # сервис фото (кэш)
            sync_service      = get_sync_service,                  # сервис синхронизации
            reopen_database   = reopen_db,                         # общая база (ТД-6)
        ),
    )

@AppLogger.get_instance(
    name = 'dependencies.py',
    enable_file_logging = 'system',
    use_name_in_filename = False,
).log_execution_time(
    level = AppLogger._parse_log_level('DEBUG')
)
def init_db(
    recreate  : bool = False,   # удалить таблицы и создать заново
    test_data : bool = True,    # заполнить тестовыми данными
) -> None: # таблицы общей базы и тестовые данные (CLI init-db)
    """
    Создаёт таблицы общей базы (:func:`get_db`) и по желанию заполняет её тестовыми
    данными (команда CLI ``init-db``).

    Args:
        recreate  : (bool) Удалить существующие таблицы перед созданием (данные теряются).
        test_data : (bool) Заполнить тестовыми данными (``Database.fill_test_data``).

    Example:
        >>> init_db(
        ...     recreate    =   False,   # таблицы не удалять
        ...     test_data   =   False,   # без тестовых данных
        ... )
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
    data           : Any,                             # DTO, словарь или список из них
    exclude_fields : Optional[List[str]] = None,      # поля, которые не выводить (например, ['id'])
    if_str_limit   : Optional[int] = None,            # длина значения; None — 50, 0 и меньше — без ограничения
    rename_map     : Optional[Dict[str, str]] = None, # заголовки полей ({'first_name': 'Имя'})
) -> List[str]: # строки «Поле: значение» для вывода в терминал (CLI)
    """
    Возвращает строки для вывода в терминал (``click.echo``): по строке на запись, поля
    ``Заголовок: значение`` через табуляцию.

    Длинное значение обрезается до ``if_str_limit`` символов с ``...`` (если длиннее
    ``if_str_limit + 3``). Пустые поля DTO не выводятся (``model_dump(exclude_none=True)``).

    Args:
        data           : (Any) DTO, словарь или список из них.
        exclude_fields : (List[str]/None) Поля, которые не выводить; None — все.
        if_str_limit   : (int/None) Длина значения; None — 50; 0 и меньше — без ограничения.
        rename_map     : (Dict[str, str]/None) Заголовки полей; None — из имени
            (``first_name`` → ``First Name``).

    Returns:
        (List[str]) Строка на запись.

    Example:
        >>> get_text_echo(
        ...     {'first_name': 'Иван', 'id': 1},   # запись
        ...     exclude_fields   =   ['id'],          # без ID
        ... )
        ['First Name: Иван']
    """
    # # если не указано ограничение длины выводимого текста, то встановим его в 50 символов
    # if not if_str_limit:
    #     if_str_limit = 50
    # ↑ до 2026-10-31 (Ф1.6.11): 0 («не ограничивать», ниже) тоже превращался в 50 (`not 0`).
    if if_str_limit is None: # не задано — 50 символов
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
    list_          : Any,                              # DTO, словарь или список из них
    exclude_fields : Optional[List[str]] = None,       # поля, которые пропустить
    rename_map     : Optional[Dict[str, str]] = None,  # {имя_поля: заголовок}
) -> Any: # словарь «заголовок: значение» (для списка — список словарей)
    """
    Преобразует DTO (или словарь) в словарь ``{заголовок: значение}``; список — в список
    таких словарей.

    DTO — через ``model_dump(exclude_none=True)`` (пустые поля пропускаются); другой объект —
    ``dict(объект)``. Заголовок — из ``rename_map`` или из имени поля (``first_name`` →
    ``First Name``).

    Args:
        list_          : (Any) DTO, словарь или список из них.
        exclude_fields : (list/None) Поля, которые пропустить.
        rename_map     : (dict/None) ``{имя_поля: заголовок}``.

    Returns:
        (Dict[str, Any] / List[Dict[str, Any]]) Словарь или список словарей.

    Example:
        >>> get_key_value_dto(
        ...     {'first_name': 'Иван'},                # запись
        ...     rename_map   =   {'first_name': 'Имя'},   # заголовок
        ... )
        {'Имя': 'Иван'}
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
def get_dto_fields(
    dto_class : BaseModel,                     # класс DTO (не объект)
    exclude   : Optional[List[str]] = None,    # поля, которые пропустить
) -> List[Dict[str, Any]]: # поля DTO с метаданными для CLI
    """
    Возвращает поля класса DTO с метаданными для командной строки.

    ``Optional[X]`` разворачивается в ``X`` (поле необязательное); ``required`` — поле не
    ``Optional`` и обязательно в модели.

    Args:
        dto_class : (Type[BaseModel]) Класс DTO (не объект).
        exclude   : (list/None) Поля, которые пропустить.

    Returns:
        (List[Dict[str, Any]]) Словари ``name``, ``type``, ``required``, ``description``
            (нет описания — из имени поля).

    Example:
        >>> [field['name'] for field in get_dto_fields(PatientDTO, exclude=['id'])][:2]
        ['first_name', 'middle_name']
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
def create_click_options(
    dto_class : BaseModel,          # класс DTO
    action    : str = 'create',     # 'create' — без id; 'update' — с --id, всё необязательно
) -> Callable[[Callable], Callable]: # декоратор команды с опциями click по полям DTO
    """
    Возвращает декоратор команды click с опцией ``--<поле>`` на каждое поле DTO.

    ``action='create'`` — без ``id``, обязательность — как у поля; иначе (``'update'``) —
    с ``--id``, и все опции необязательны: наличие ``id`` проверяет сама команда (CLI
    ``patient update`` и др.). Тип опции — ``int`` для целых, иначе строка (даты и время
    команда разбирает сама).

    Args:
        dto_class : (Type[BaseModel]) Класс DTO.
        action    : (str) ``'create'`` или ``'update'``.

    Returns:
        (Callable) Декоратор команды.

    Example:
        >>> @create_click_options(PatientDTO, action='update')
        ... def patient_update(**kwargs):
        ...     ...
    """
    import click
    exclude = ['id'] if action == 'create' else []
    fields = get_dto_fields(dto_class, exclude=exclude)

    def decorator(
        func : Callable,   # команда click
    ) -> Callable: # команда с опциями полей DTO
        """
        Добавляет команде опцию ``--<поле>`` на каждое поле DTO.

        Args:
            func : (Callable) Команда click.

        Returns:
            (Callable) Та же команда с опциями.

        Example:
            >>> command = decorator(patient_update)
        """
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
    dto_class  : BaseModel,                          # класс DTO
    exclude    : Optional[List[str]] = None,         # поля, которые не запрашивать
    rename_map : Optional[Dict[str, str]] = None,    # {имя_поля: подпись запроса}
) -> Dict[str, Any]: # значения полей DTO, введённые в терминале
    """
    Запрашивает в терминале (``click.prompt``) значения полей DTO и возвращает их с
    переведёнными типами.

    Пустой ввод необязательного поля — ``None``; обязательного — повтор запроса. Целые,
    даты (``ГГГГ-ММ-ДД``) и время (``ЧЧ:ММ``) переводятся; неверный формат — сообщение и
    повтор запроса. Остальные поля — строкой.

    Args:
        dto_class  : (Type[BaseModel]) Класс DTO.
        exclude    : (list/None) Поля, которые не запрашивать.
        rename_map : (dict/None) ``{имя_поля: подпись запроса}``; нет — описание поля.

    Returns:
        (Dict[str, Any]) ``{имя_поля: значение}``.

    Example:
        >>> data = collect_dto_from_input(
        ...     PatientDTO,
        ...     exclude   =   ['id'],   # ID не спрашивать
        ... )
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

            # if not value and not f['required']:
            #     data[f['name']] = None
            #     break
            # ↑ до 2026-10-31 (Ф1.6.11): недостижимо — тот же случай разобран выше.

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

# AppLogger.get_instance(
# ↑ до 2026-10-31 (Ф1.6.11): без «@» — выражение вычислялось и отбрасывалось, функция не
#   оборачивалась (время выполнения не писалось в журнал, как у остальных функций модуля).
@AppLogger.get_instance(
    name='dependencies.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def create_database(db_path: str, fill_test_data: bool = False) -> None: # новый файл базы (экран настроек)
    """
    Создаёт базу по указанному пути (нет файла — новый, схема — миграциями) и по желанию
    заполняет тестовыми данными; затем закрывает её.

    Отдельный ``Database``, не общий (:func:`get_db`): файл создаётся для выбора на экране
    настроек, общая база переключается на него позже — ``ConfigApplier.apply_database``.

    Args:
        db_path        : (str) Путь к файлу базы.
        fill_test_data : (bool) Заполнить тестовыми данными (пустую базу).

    Raises:
        DatabaseConnectionError: Файл не открыть (занят, нет доступа).
        MigrationError: Базу нельзя безопасно обновить.

    Example:
        >>> create_database(
        ...     'D:/clinic_new.db',             # новый файл
        ...     fill_test_data   =   False,     # без тестовых данных
        ... )
    """
    # from app.database import Database
    db = Database(f"sqlite:///{db_path}")
    if fill_test_data:
        db.fill_test_data()
        
    db.close()