# app/utils/logger/logger.py

"""
Модуль логирования приложения.

Содержит класс AppLogger, который:
- Управляет созданием и хранением экземпляров логгеров (паттерн Multiton).
- Каждый экземпляр настраивается индивидуально (имя, конфигурация).
- Предоставляет методы для логирования и декоратор log_execution_time.
- Не использует глобальные переменные (все данные хранятся в атрибутах класса).
- НЕ читает конфигурацию приложения сам: её передают через AppLogger.configure().

Связь с конфигом приложения:
    Модуль не импортирует app.config. Точки входа (main_gui_window.py, main_cli.py,
    pars_start.py) первым делом вызывают app.config.logging_setup.setup_logging(),
    который читает конфиг и передаёт его в AppLogger.configure(). До этого логгеры
    работают на безопасных настройках по умолчанию: консоль, уровень INFO, без файла.

    Порядок важен: всё, что залогировано до setup_logging(), в файл не попадёт.

        # main_gui_window.py
        from app.config.logging_setup import setup_logging
        setup_logging()        # ← до любой работы
        main()

    Подробности и история решения — IMPLEMENTATION.md, §4 и §7.1.

Пример использования:
    # Получить экземпляр по умолчанию
    logger = AppLogger.get_instance()
    logger.info("Приложение запущено. Добавлен в общий лог")

    # Получить или создать другой экземпляр
    logger1 = AppLogger.get_instance(name='default1')
    logger1.info("Приложение запущено. Добавлен в лог default1")

    # Использовать декоратор для метода класса (учебный класс, не сервис приложения)
    class ExampleService:
        def __init__(self):
            self.logger = AppLogger.get_instance('example')

        @AppLogger.get_instance().log_execution_time(description="Получение пациента")
        def get_patient(self, patient_id):
            self.logger.debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...

    # Использовать декоратор для обычной функции
    @AppLogger.get_instance().log_execution_time(description="Вспомогательная функция")
    def helper():
        pass
"""


# Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import os
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).
# ↑ P3: не используется.

from typing import  Dict, Any, Mapping, Optional, Tuple

# Импорты модулей
# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None

# try:
    # from ...controllers.conf.get_config import get_config_env
# from ...config.config_manager.manager import get_config_env
# # === ЗАЩИТА ОТ РЕКУРСИИ ===
# if 'app.config.config_manager.manager' not in sys.modules:
#     from ...config.config_manager.manager import get_config_env
# else:
#     get_config_env = sys.modules['app.config.config_manager.manager'].get_config_env
# except ImportError as e:
#     # try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name(file_module = __file__,levels_up = 3)
#     # from ...controllers.conf.get_config import get_config_env
#     from ...config.config_manager.manager import get_config_env
    # except ImportError as e:
    #     pass #  pass #  raise # e # pass

# try:
# from app.utils.logger.base_logger import BaseAppLogger
# ↑ до 2026-10-14: абсолютный путь привязывал пакет к расположению в этом проекте.
# Относительный импорт — пакет можно скопировать в другой проект под любым именем.
from .base_logger import BaseAppLogger


# Развязка с конфигом (2026-10-14): логгер больше НЕ читает конфиг сам.
# Раньше здесь был импорт, и каждый новый логгер вызывал get_config_env()
# (154 чтения конфига и .env за старт GUI). Теперь конфиг передаётся снаружи через
# AppLogger.configure(...) — см. app/config/logging_setup.py и IMPLEMENTATION.md §4, §7.1.
# Строка оставлена для истории: из-за неё менеджер конфига не мог логировать
# (циклический импорт, блоки sys.modules выше).
# from app.config.config_manager.manager import get_config_env

# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 0)
#         from .base_logger import BaseAppLogger
#     except ImportError as e:
#         pass #  raise # e # pass


# Сторонние библиотеки



class AppLogger(BaseAppLogger):
    """
    Логгер приложения: BaseAppLogger + настройки, переданные из конфига приложения.

    Отличия от BaseAppLogger:
        * свой реестр экземпляров (``_instances``);
        * ``get_default_config()`` строит конфиг логгера из словаря, переданного в
          ``configure()``, а до этого — из безопасных значений по умолчанию;
        * ``configure()`` — единственная точка, через которую конфиг приложения попадает
          в логгеры.

    Модуль конфигурацию НЕ читает (см. докстринг модуля и IMPLEMENTATION.md §7.1).

    Атрибуты класса:
        _instances (Dict[str, BaseAppLogger]): Реестр экземпляров {имя: экземпляр}.
        _app_config (Optional[Dict[str, Any]]): Последний конфиг приложения из
            ``configure()``; ``None`` — логгер ещё не настроен.
        UNCONFIGURED_APP_CONFIG (Dict[str, Any]): Конфиг приложения, который
            используется до вызова ``configure()``.

    Пример:
        >>> AppLogger.configure({'LOG_DIR': './logs', 'system_LEVEL': 'DEBUG'})
        >>> log = AppLogger.get_instance('PatientService', enable_file_logging='system')
        >>> log.info('Пациент сохранён')
    """

    _instances = {}  # переопределяем, чтобы был свой пул

    # Конфиг приложения, переданный через configure(). None — ещё не настроен.
    _app_config: Optional[Dict[str, Any]] = None

    # До configure(): только консоль. Файл не создаём, чтобы скрипты и тесты, которые
    # не вызывали setup_logging(), не писали в ./logs/app.log.
    # Остальные значения берутся из умолчаний build_logger_config().
    UNCONFIGURED_APP_CONFIG: Dict[str, Any] = {
        'file_enabled': False,
    }

    # Логгеры, которые создаются автоматически при первом get_instance() класса (P6).
    # На них ссылаются остальные (enable_file_logging='system'), поэтому они должны
    # существовать раньше. Наследник может переопределить кортеж (пустой — не создавать).
    DEFAULT_LOGGERS: Tuple[Dict[str, Any], ...] = (
        # show_call_depth=True — как было при импорте; ключ show_call_depth в конфиге сильнее
        {'name': 'system', 'use_name_in_filename': False, 'show_call_depth': True},
        {'name': 'user', 'use_name_in_filename': False},
    )

    # Флаг «идёт создание логгеров по умолчанию» — защита от рекурсии
    # (_ensure_default_loggers сам вызывает get_instance)
    _creating_default_loggers: bool = False

    @classmethod
    def _ensure_default_loggers(cls) -> None:
        """
        Создаёт логгеры из ``DEFAULT_LOGGERS``, которых ещё нет в реестре класса.

        Вызывается из ``get_instance()`` перед созданием любого логгера. Повторно создаёт
        логгеры после ``close_all()``. Защищён от рекурсии и от параллельных вызовов.

        Returns:
            None

        Пример:
            >>> AppLogger.get_instance('PatientService', enable_file_logging='system')
            >>> AppLogger.thec_create('system')     # создан автоматически раньше
            True
        """
        if cls._creating_default_loggers:
            return
        with cls._instances_lock:
            if cls._creating_default_loggers:
                return
            cls._creating_default_loggers = True
            try:
                for spec in cls.DEFAULT_LOGGERS:
                    if not cls.thec_create(spec['name']):
                        super().get_instance(**spec)
            finally:
                cls._creating_default_loggers = False

    @classmethod
    def get_instance(cls, name: str = 'default', **kwargs: Any) -> 'BaseAppLogger':
        """
        То же, что ``BaseAppLogger.get_instance``, но сначала создаёт ``DEFAULT_LOGGERS``.

        Так логгеры ``system``/``user`` существуют раньше любого логгера, который на них
        ссылается, — без побочного эффекта при импорте модуля (P6).

        Args:
            name: Имя логгера.
            **kwargs: Аргументы ``BaseAppLogger.get_instance``.

        Returns:
            Логгер.

        Пример:
            >>> log = AppLogger.get_instance('svc', enable_file_logging='system')
        """
        cls._ensure_default_loggers()
        return super().get_instance(name, **kwargs)

    # # Словарь экземпляров (ключ - имя логгера)
    # @classmethod
    # def get_default_config(cls) -> Dict[str, Any]: # переопределяем,
    #     if 'app.config.config_manager.manager' not in sys.modules:
    #         from app.config.config_manager.manager import get_config_env
    #     else:
    #         get_config_env = sys.modules['app.config.config_manager.manager'].get_config_env

    #     config = get_config_env()
    #     # Добавляем ключ LOG_ARGS, если его нет (по умолчанию False)
    #     config.setdefault('LOG_ARGS', False)

    #     # tt = sys.modules['app.config.config_manager.manager']
    #     return config

    # Реализация до развязки с конфигом (до 2026-10-14). Сохранена для понимания:
    # каждый новый логгер сам вызывал get_config_env() → чтение msgpack и .env
    # (154 раза за старт GUI). Логика преобразования перенесена в build_logger_config(),
    # чтение конфига — в app/config/logging_setup.py.
    # @classmethod
    # def get_default_config(cls) -> Dict[str, Any]:
    #     # from app.config.config_manager.manager import get_config_env
    #     config = get_config_env() # уже содержит все настройки из msgpack (или .env по умолчанию)

    #     # Используем LOG_DIR, если есть, иначе LOG_FILE (для обратной совместимости)
    #     log_path = config.get('LOG_DIR', config.get('LOG_FILE', 'logs'))
    #     # Если путь не оканчивается на разделитель, считаем его директорией
    #     if not log_path.endswith(('/', '\\')) and not log_path.lower().endswith('.log'):
    #         log_path = log_path + os.sep

    #     result =  {
    #         # 'LOG_LEVEL': config.get('LOG_LEVEL', 'DEBUG'),
    #         'LOG_LEVEL': config.get('LOG_LEVEL', 'INFO'),
    #         'LOG_FILE': log_path,                     # именно LOG_FILE ожидает BaseAppLogger
    #         'LOG_MAX_BYTES': config.get('LOG_MAX_BYTES', 10*1024*1024),
    #         'LOG_BACKUP_COUNT': config.get('LOG_BACKUP_COUNT', 5),
    #         'LOG_ARGS': config.get('LOG_ARGS', False),
    #         # Общие флаги
    #         'enabled': config.get('enabled', True),
    #         'console_enabled': config.get('console_enabled', True), # 
    #         'file_enabled': config.get('file_enabled', True),
    #         'use_timestamp': config.get('use_timestamp', False),
    #     }


    #     # Добавляем специфичные для разных логгеров ключи (чтобы BaseAppLogger мог их прочитать через _get_config_with_inheritance)
    #     # Они нужны для того, чтобы при создании логгера 'system' его настройки были взяты из system_LEVEL и т.д.
    #     for key, value in config.items():
    #         if (
    #             key.startswith('system_') 
    #             or key.startswith('user_') 
    #             or key in ('enabled', 'console_enabled', 'file_enabled', 'use_timestamp')
    #         ):
    #             if key not in result:
    #                 result[key] = value

    #     return result

    # @classmethod
    # def reload_all_from_app_config(cls):
    #     """
    #     Загружает текущую конфигурацию приложения и применяет её ко всем существующим логгерам.

    #     Вызывается автоматически при изменении настроек через SettingsPage.
    #     Использует `get_config_env()` для получения словаря настроек и передаёт его в
    #     `cls.reload_all_from_config(full_config)`.

    #     Пример:
    #         >>> AppLogger.reload_all_from_app_config()
    #         # После этого все логгеры перечитают настройки (уровни, директории и т.д.)
    #     """

    #     # from app.config.config_manager.manager import get_config_env
    #     full_config = get_config_env()
    #     cls.reload_all_from_config(full_config)

    @staticmethod
    def build_logger_config(app_config: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Строит конфиг для BaseAppLogger из плоского конфига приложения.

        Что делает:
            1. Путь к логам: берёт ``LOG_DIR``, иначе ``LOG_FILE``, иначе ``'logs'``.
               Если путь не оканчивается на разделитель и не на ``.log`` — добавляет
               ``os.sep``, чтобы BaseAppLogger однозначно считал его папкой.
            2. Кладёт его в ``LOG_FILE`` — именно этот ключ проверяет BaseAppLogger
               (``LOG_DIR`` валидацию не проходит, см. IMPLEMENTATION.md §3.4).
            3. Заполняет общие ключи значениями по умолчанию.
            4. Переносит как есть ключи ``system_*`` и ``user_*``: через них
               логгеры ``system``/``user`` и все их «наследники»
               (``enable_file_logging='system'``) получают свои настройки.
            5. Переносит ``show_call_depth``, если он задан (отступ ``>`` по глубине
               стека; дополнительный обход стека на каждую запись).

        Значения не приводятся к типам (``'True'`` остаётся строкой) — это делает
        BaseAppLogger при чтении.

        Args:
            app_config: Плоский словарь настроек приложения
                (обычно ``AppConfigManager.get_all()``). Не изменяется.

        Returns:
            Новый словарь, пригодный для ``BaseAppLogger.get_instance(config=...)``.

        Пример:
            >>> cfg = AppLogger.build_logger_config({'LOG_DIR': 'logs', 'system_LEVEL': 'DEBUG'})
            >>> cfg['LOG_FILE'] == 'logs' + os.sep, cfg['system_LEVEL'], cfg['LOG_LEVEL']
            (True, 'DEBUG', 'INFO')
        """
        config = app_config

        # Используем LOG_DIR, если есть, иначе LOG_FILE (для обратной совместимости)
        log_path = config.get('LOG_DIR', config.get('LOG_FILE', 'logs'))
        # Если путь не оканчивается на разделитель, считаем его директорией
        if not log_path.endswith(('/', '\\')) and not log_path.lower().endswith('.log'):
            log_path = log_path + os.sep

        result: Dict[str, Any] = {
            # 'LOG_LEVEL': config.get('LOG_LEVEL', 'DEBUG'),
            'LOG_LEVEL': config.get('LOG_LEVEL', 'INFO'),
            'LOG_FILE': log_path,                     # именно LOG_FILE ожидает BaseAppLogger
            'LOG_MAX_BYTES': config.get('LOG_MAX_BYTES', 10*1024*1024),
            'LOG_BACKUP_COUNT': config.get('LOG_BACKUP_COUNT', 5),
            'LOG_ARGS': config.get('LOG_ARGS', False),
            # Общие флаги
            'enabled': config.get('enabled', True),
            'console_enabled': config.get('console_enabled', True), #
            'file_enabled': config.get('file_enabled', True),
            'use_timestamp': config.get('use_timestamp', False),
        }

        # Добавляем специфичные для разных логгеров ключи (чтобы BaseAppLogger мог их прочитать через _get_config_with_inheritance)
        # Они нужны для того, чтобы при создании логгера 'system' его настройки были взяты из system_LEVEL и т.д.
        for key, value in config.items():
            if (
                key.startswith('system_')
                or key.startswith('user_')
                # or key in ('enabled', 'console_enabled', 'file_enabled', 'use_timestamp')
                # ↑ до исправления R5: show_call_depth из конфига отбрасывался,
                #   и ключ в config.msgpack ни на что не влиял.
                or key in ('enabled', 'console_enabled', 'file_enabled', 'use_timestamp',
                           'show_call_depth')
            ):
                if key not in result:
                    result[key] = value

        return result

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Конфиг для нового логгера, у которого в ``get_instance()`` не передан ``config``.

        Источник:
            * после ``configure()`` — переданный туда конфиг приложения;
            * до ``configure()`` — ``UNCONFIGURED_APP_CONFIG`` (консоль, без файла).

        Конфиг приложения здесь НЕ читается — только то, что передали в ``configure()``.

        Returns:
            Словарь для BaseAppLogger (результат ``build_logger_config()``).

        Пример:
            >>> AppLogger.configure({'LOG_LEVEL': 'WARNING'})
            >>> AppLogger.get_default_config()['LOG_LEVEL']
            'WARNING'
        """
        return cls.build_logger_config(cls._current_app_config())

    @classmethod
    def is_configured(cls) -> bool:
        """
        Передавался ли уже конфиг приложения через ``configure()``.

        Returns:
            ``True`` после первого ``configure()``, ``False`` до него
            и после ``reset_configuration()``.

        Пример:
            >>> AppLogger.reset_configuration()
            >>> AppLogger.is_configured()
            False
            >>> AppLogger.configure({})
            >>> AppLogger.is_configured()
            True
        """
        return cls._app_config is not None

    @classmethod
    def current_app_config(cls) -> Dict[str, Any]:
        """
        Конфиг приложения, с которым логгеры настроены сейчас (копия).

        Нужен, чтобы понять, изменились ли настройки логирования относительно того,
        что логгеры уже применили, — а не относительно файла конфигурации, который к
        моменту проверки может быть уже перезаписан (так было в ConfigApplier, R1).

        Returns:
            Копия последнего конфига из ``configure()``; до первого вызова —
            копия ``UNCONFIGURED_APP_CONFIG``.

        Пример:
            >>> AppLogger.configure({'system_LEVEL': 'DEBUG'})
            >>> AppLogger.current_app_config()['system_LEVEL']
            'DEBUG'
            >>> AppLogger.current_app_config()['system_LEVEL'] = 'ERROR'  # не влияет на логгеры
        """
        return dict(cls._current_app_config())

    @classmethod
    def configure(cls, app_config: Mapping[str, Any]) -> None:
        """
        Передаёт логгерам конфиг приложения и применяет его ко всем существующим.

        Единственная точка входа конфига в логгеры. Вызывается:
            * при старте — из ``app.config.logging_setup.setup_logging()``, до любой работы;
            * при сохранении настроек — из ``ConfigApplier.apply_logging()``;
            * при открытии главного окна — из ``MainWindow`` (повторно, для надёжности).

        Что делает:
            1. Запоминает копию ``app_config`` — по ней будут настроены логгеры,
               созданные позже (``get_default_config()``).
            2. Перенастраивает все уже созданные логгеры через
               ``reload_all_from_config()``: уровни, флаги, путь к файлу.

        Во второй шаг уходит сырой конфиг, дополненный результатом
        ``build_logger_config()``: так сохраняются персональные ключи вида
        ``ConfigApplier_LEVEL``, а путь к файлу (``LOG_FILE``) у созданных раньше и
        созданных позже логгеров совпадает (от этого зависит автопривязка к общему файлу).

        Args:
            app_config: Плоский словарь настроек приложения
                (обычно ``AppConfigManager.get_all()``). Копируется, не изменяется.

        Returns:
            None

        Пример:
            >>> from app.config.config_manager.manager import get_config_env
            >>> AppLogger.configure(get_config_env())
        """
        cls._app_config = dict(app_config)
        cls.reload_all_from_config(cls._config_for_reload(cls._app_config))

    @classmethod
    def reset_configuration(cls) -> None:
        """
        Возвращает класс в состояние «не настроен» (для тестов).

        Существующие логгеры НЕ перенастраиваются — меняется только то, с чем будут
        созданы новые.

        Returns:
            None

        Пример:
            >>> AppLogger.reset_configuration()
            >>> AppLogger.is_configured()
            False
        """
        cls._app_config = None

    @classmethod
    def reload_all_from_app_config(cls) -> None:
        """
        Повторно применяет ко всем логгерам последний конфиг из ``configure()``.

        Раньше метод сам читал конфиг приложения (``get_config_env()``). После развязки
        логгер конфиг не читает, поэтому метод только переприменяет уже переданный.
        Чтобы применить НОВЫЙ конфиг, вызывайте ``configure(new_config)``.

        Если ``configure()`` ещё не вызывался, применяются значения по умолчанию
        (``UNCONFIGURED_APP_CONFIG``).

        Returns:
            None

        Пример:
            >>> AppLogger.configure({'system_LEVEL': 'ERROR'})
            >>> AppLogger.get_instance('system').reconfigure(level='DEBUG')
            >>> AppLogger.reload_all_from_app_config()   # system снова ERROR
        """
        cls.reload_all_from_config(cls._config_for_reload(cls._current_app_config()))

    @classmethod
    def _current_app_config(cls) -> Mapping[str, Any]:
        """
        Конфиг приложения, действующий сейчас.

        Returns:
            Последний конфиг из ``configure()`` или ``UNCONFIGURED_APP_CONFIG``,
            если ``configure()`` ещё не вызывался. Возвращается без копирования —
            не изменяйте результат.

        Пример:
            >>> AppLogger.reset_configuration()
            >>> AppLogger._current_app_config() is AppLogger.UNCONFIGURED_APP_CONFIG
            True
        """
        return cls._app_config if cls._app_config is not None else cls.UNCONFIGURED_APP_CONFIG

    @classmethod
    def _config_for_reload(cls, app_config: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Конфиг для ``reload_all_from_config()``: сырой конфиг + нормализованные ключи.

        Сырой конфиг нужен ради персональных ключей (``ConfigApplier_LEVEL`` и т. п.),
        которые ``build_logger_config()`` отбрасывает. Нормализованные ключи нужны,
        чтобы ``LOG_FILE`` совпадал с тем, с которым создаются новые логгеры.

        Args:
            app_config: Плоский словарь настроек приложения.

        Returns:
            Новый словарь: все ключи ``app_config``, поверх них — результат
            ``build_logger_config(app_config)``.

        Пример:
            >>> cfg = AppLogger._config_for_reload({'LOG_DIR': 'logs', 'ConfigApplier_LEVEL': 'ERROR'})
            >>> cfg['LOG_FILE'] == 'logs' + os.sep, cfg['ConfigApplier_LEVEL']
            (True, 'ERROR')
        """
        return {**app_config, **cls.build_logger_config(app_config)}


# До P6 (2026-10-14) логгеры system и user создавались ПРИ ИМПОРТЕ модуля — в другом
# проекте импорт пакета создавал логгеры как побочный эффект. Теперь их создаёт
# AppLogger._ensure_default_loggers() при первом get_instance() (см. DEFAULT_LOGGERS).
# # Автоматическое создание экземпляров при импорте
# if not AppLogger.thec_create('system'):
#     ее = AppLogger.get_instance(
#         name='system',
#         # enable_file_logging = False,
#         # enable_file_logging = True,
#         use_name_in_filename = False, # True, # False,   # используем общий файл из конфига
#         # share_file_with='system',
#         show_call_depth=True,
#     )
#     # 0==0
#
# if not AppLogger.thec_create('user'):
#     AppLogger.get_instance(
#         name='user',
#         # enable_file_logging = False,    
#         # enable_file_logging = True,    
#         # enable_file_logging = 'system',   # строка – значит использовать общий обработчик system
#         use_name_in_filename = False, # True, # False, # используем общий файл из конфига
#         # share_file_with='system',
#     )
#     # 0==0

if __name__ == '__main__':
    # logging.basicConfig(  # Настройка базового логирования
    #     level=logging.DEBUG,
    #     # filename="py_log.log",
    #     # filemode="w",
    #     # format="%(asctime)s %(levelname)s %(message)s",

    #     format='%(asctime)s\t%(levelname)s\tFile "%(pathname)s", line %(lineno)d,\tin <%(funcName)s>:\t%(message)s',
    #     # # Формат лога: время, уровень, путь к файлу, номер строки, имя функции, сообщение.
    #     # format='%(asctime)s\t%(levelname)s\t%(message)s',  # Новый: дата/время, уровень, сообщение (с кастомным указателем внутри).
    # )
    # тест и пример логирования:
 
    # Получить экземпляр по умолчанию
    logger = AppLogger.get_instance()
    logger.info("Приложение запущено. Добавлен в общий лог")

    # Получить или создать 2й экземпляр
    logger1 = AppLogger.get_instance(name='default1')
    logger1.info("Приложение запущено. Добавлен в лог default1")

    # Получить или создать 3й экземпляр
    AppLogger.get_instance(name='default1').info("Приложение запущено. Добавлен в лог default2")

    # Использовать декоратор для метода класса
    # К8 (2026-10-25): учебный класс назывался PatientService — при поиске и в описи кода
    # путался с сервисом пациентов app.services (PatientService); переименован, логика та же.
    class ExampleService:
        """
        Учебный класс для демонстрации декоратора на методах (не сервис приложения).

        Пример:
            >>> ExampleService().get_patient(1)
        """

        logger0 = AppLogger.get_instance('logger0')

        def __init__(self) -> None:
            """
            Логгер экземпляра — ``logger``.

            Пример:
                >>> ExampleService().logger.name
                'logger'
            """
            self.logger = AppLogger.get_instance('logger')

        @logger0.log_execution_time(description="logger0 Получение пациента")
        def get_patient(
            self,
            patient_id : int,   # id записи (для текста в журнале)
        ) -> None:
            """
            Декоратор логгера, взятого атрибутом класса, и запись логгером экземпляра.

            Пример:
                >>> ExampleService().get_patient(1)
            """
            self.logger.debug(f"logger Запрос пациента с id={patient_id}")

        @AppLogger.get_instance().log_execution_time(description="logger avto Получение пациента")
        def get_patient2(
            self,
            patient_id : int,   # id записи (для текста в журнале)
        ) -> None:
            """
            Декоратор логгера по умолчанию (``default``).

            Пример:
                >>> ExampleService().get_patient2(2)
            """
            AppLogger.get_instance().debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...

        @AppLogger.get_instance(name='logger1').log_execution_time(description="Получение пациента")
        def get_patient3(
            self,
            patient_id : int,   # id записи (для текста в журнале)
        ) -> None:
            """
            Декоратор именованного логгера ``logger1``.

            Пример:
                >>> ExampleService().get_patient3(3)
            """
            AppLogger.get_instance(name='logger1').debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...

        @AppLogger.get_instance().log_execution_time()
        def get_patient4(
            self,
            patient_id : int,   # id записи (для текста в журнале)
        ) -> None:
            """
            Декоратор без описания (в журнале — имя функции).

            Пример:
                >>> ExampleService().get_patient4(4)
            """
            AppLogger.get_instance(name='logger1').debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...

    # Использовать декоратор для обычной функции
    @AppLogger.get_instance().log_execution_time(description="Вспомогательная функция")
    def helper() -> None:
        """
        Декоратор на обычной функции.

        Пример:
            >>> helper()
        """
        pass

    example_service = ExampleService()
    example_service.get_patient(1)
    example_service.get_patient2(2)
    example_service.get_patient3(3)
    example_service.get_patient4(4)

    helper()



    AppLogger.get_instance(
        name='test1',
        config='default1',
    ).info("test1")
    AppLogger.get_instance(
        name='test2',
        # # share_file_with = 'default1',
        enable_file_logging = 'default1',
    ).info("test2")
    AppLogger.get_instance(
        name='test3',
        use_name_in_filename = False, # 'default1',
    ).info("test3")


    AppLogger.get_instance(
        name='test4',
        config='default1',
        # # share_file_with = 'default1',
        enable_file_logging = 'default1',
        use_name_in_filename = False, # 'default1',
    ).info("test4")

    # 0==0

    pass
# ------------------------------------------------------------------------------
# Экспортируем только класс – никаких глобальных переменных.
# ------------------------------------------------------------------------------
__all__ = ['AppLogger']
