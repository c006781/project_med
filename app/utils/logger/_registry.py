# app/utils/logger/_registry.py

"""
Часть ``BaseAppLogger``: Реестр логгеров и операции уровня класса.

Содержит примесь ``_RegistryMixin``: реестр (get_instance), группы по префиксу, *_exact, список отключённых, глобальные обработчики и выводы, watchdog файлов, close_all.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_RegistryMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _RegistryMixin)
    True
"""

import warnings
import logging
import sys
import time
from typing import Optional, Dict, Any, Callable, Union


import threading


from ._common import LOGGER_CODE_FILES
from .handlers import CallableHandler

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _RegistryMixin:
    """
    Примесь ``BaseAppLogger``: реестр (get_instance), группы по префиксу, *_exact, список отключённых, глобальные обработчики и выводы, watchdog файлов, close_all.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._RegistryMixin'>, ...)
    """

    @classmethod
    def on_show_call_depth_global(cls) -> None:
        """
        Включает классовый флаг «показывать глубину вызова везде».

        Флаг сейчас нигде не читается (в декораторе его использование закомментировано) —
        оставлен для совместимости с кодом приложения. Глубина включается параметром
        ``show_call_depth`` логгера или ``show_depth=True`` декоратора.

        Returns:
            None

        Пример:
            >>> AppLogger.on_show_call_depth_global()
            >>> AppLogger.status_show_call_depth_global()
            True
        """
        # P7 (2026-10-14): устаревшее — оставлено для совместимости, не удаляется.
        warnings.warn(
            'on_show_call_depth_global() устарел: флаг ни на что не влияет. Глубина включается параметром show_call_depth логгера или show_depth=True декоратора.',
            DeprecationWarning,
            stacklevel=2,
        )
        cls._show_call_depth_global = True

    @classmethod
    def off_show_call_depth_global(cls) -> None:
        """
        Выключает классовый флаг «показывать глубину вызова везде».

        См. ``on_show_call_depth_global`` — флаг сейчас ни на что не влияет.

        Returns:
            None

        Пример:
            >>> AppLogger.off_show_call_depth_global()
        """
        # P7 (2026-10-14): устаревшее — оставлено для совместимости, не удаляется.
        warnings.warn(
            'off_show_call_depth_global() устарел: флаг ни на что не влияет. Глубина включается параметром show_call_depth логгера или show_depth=True декоратора.',
            DeprecationWarning,
            stacklevel=2,
        )
        cls._show_call_depth_global = False


    @classmethod
    def status_show_call_depth_global(cls) -> bool:
        """
        Текущее значение классового флага глубины.

        Returns:
            ``True``, если флаг включён ``on_show_call_depth_global()``.

        Пример:
            >>> AppLogger.status_show_call_depth_global()
            False
        """
        # P7 (2026-10-14): устаревшее — оставлено для совместимости, не удаляется.
        warnings.warn(
            'status_show_call_depth_global() устарел: флаг ни на что не влияет. Глубина включается параметром show_call_depth логгера или show_depth=True декоратора.',
            DeprecationWarning,
            stacklevel=2,
        )
        return cls._show_call_depth_global


    @classmethod
    def add_disabled_logger(cls, name: str) -> None:
        """
        Запрещает логгеру с этим именем писать (точное имя, не префикс).

        Список общий для всех наследников BaseAppLogger. Логгер не выключается
        (``is_enabled()`` остаётся ``True``) — его методы и декоратор просто молчат.
        Повторное добавление ничего не меняет.

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.add_disabled_logger('gui.PaginatedTableModel')
            >>> AppLogger.is_disabled('gui.PaginatedTableModel')
            True
        """
        if name not in cls._disabled_loggers:
            cls._disabled_loggers.append(name)

    @classmethod
    def remove_disabled_logger(cls, name: str) -> None:
        """
        Снова разрешает логгеру писать. Если имени нет в списке — ничего не делает.

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.remove_disabled_logger('gui.PaginatedTableModel')
        """
        if name in cls._disabled_loggers:
            cls._disabled_loggers.remove(name)

    @classmethod
    def clear_disabled_loggers(cls) -> None:
        """
        Очищает список отключённых логгеров.

        Returns:
            None

        Пример:
            >>> AppLogger.clear_disabled_loggers()
        """
        cls._disabled_loggers.clear()

    @classmethod
    def is_disabled(cls, name: str) -> bool:
        """
        Есть ли логгер в списке отключённых (``add_disabled_logger``).

        Args:
            name: Точное имя логгера.

        Returns:
            ``True``, если логгеру запрещено писать.

        Пример:
            >>> AppLogger.is_disabled('system')
            False
        """
        return name in cls._disabled_loggers

    @classmethod
    def disable_exact(cls, name: str) -> None:
        """
        Выключает логгер с точным именем (``disable()``); неизвестное имя — ничего не делает.

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.disable_exact('gui.Table')     # 'gui.Table.Model' не затронут
        """
        inst = None

        with cls._instances_lock:
            inst = cls._instances.get(name)

        if inst:
            inst.disable()

    @classmethod
    def enable_exact(cls, name: str) -> None:
        """
        Включает логгер с точным именем (``enable()``); неизвестное имя — ничего не делает.

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.enable_exact('gui.Table')
        """
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.enable()

    @classmethod
    def disable_console_exact(cls, name: str) -> None:
        """
        Выключает вывод в консоль у логгера с точным именем.

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.disable_console_exact('gui.Table')
        """
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.disable_console()

    @classmethod
    def enable_console_exact(cls, name: str) -> None:
        """
        Включает вывод в консоль у логгера с точным именем.

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.enable_console_exact('gui.Table')
        """
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.enable_console()

    @classmethod
    def disable_file_exact(cls, name: str) -> None:
        """
        Выключает запись в файл у логгера с точным именем (``turn_off_file_logging``).

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.disable_file_exact('gui.Table')
        """
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.disable_file()

    @classmethod
    def enable_file_exact(cls, name: str) -> None:
        """
        Включает запись в файл у логгера с точным именем (``turn_on_file_logging``).

        Args:
            name: Точное имя логгера.

        Returns:
            None

        Пример:
            >>> AppLogger.enable_file_exact('gui.Table')
        """
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.enable_file()

    # @classmethod
    # def disable_group_exact(cls, name: str):
    #     """Отключает логгер с точным именем (не префикс)."""
    #     inst = cls._instances.get(name)
    #     if inst:
    #         inst.disable()

    # @classmethod
    # def enable_group_exact(cls, name: str):
    #     inst = cls._instances.get(name)
    #     if inst:
    #         inst.enable()

    @classmethod
    def start_file_watchdog(cls, interval_sec: float = 5.0) -> None:
        """
        Регистрирует класс в фоновом потоке ``LoggerWatchdog`` (и запускает поток, если его нет).

        Поток-демон один на всю программу: раз в ``interval_sec`` секунд вызывает
        ``reopen_missing_files()`` у каждого зарегистрированного класса. Классы хранятся в
        слабом множестве (``_watched_classes``) — поток их в памяти не держит. Интервал
        задаёт первый вызов. Вызывается автоматически при первом ``get_instance()`` класса.

        Args:
            interval_sec: Пауза между проверками, секунд.

        Returns:
            None

        Пример:
            >>> AppLogger.start_file_watchdog(interval_sec=10)
        """
        # import threading
        # with cls._watchdog_started_lock:
        #     if cls._watchdog_started:
        #         return
        #
        #     cls._watchdog_started = True
        # ↑ до P2 (2026-10-14): флаг ставился на каждый класс-наследник — у каждого свой
        #   вечный поток, и поток держал класс в памяти. Теперь поток один на все
        #   классы; классы регистрируются в слабом множестве и могут освобождаться.
        with BaseAppLogger._watchdog_started_lock:
            BaseAppLogger._watched_classes.add(cls)
            if BaseAppLogger._watchdog_started:
                return

            BaseAppLogger._watchdog_started = True

        def watch() -> None:
            """
            Бесконечный цикл потока ``LoggerWatchdog``: пауза → проверка файлов.

            Returns:
                None (не возвращается; поток-демон завершается вместе с программой).

            Пример:
                Запускается только из ``start_file_watchdog``.
            """
            while True:
                time.sleep(interval_sec)
                # cls.reopen_all_files()  # внутри есть блокировка
                # ↑ до 2026-10-14: каждые interval_sec ВСЕ файловые обработчики
                #   закрывались и открывались заново, даже если файл на месте.
                #   Теперь переоткрываются только файлы, которых нет на диске.
                # cls.reopen_missing_files()
                # ↑ до P2: только свой класс. Теперь — все зарегистрированные классы.
                for watched in list(BaseAppLogger._watched_classes):
                    watched.reopen_missing_files()

        thread = threading.Thread(target=watch, daemon=True, name="LoggerWatchdog")
        thread.start()

    @classmethod
    def reopen_missing_files(cls) -> int:
        """
        Переоткрывает файлы логов, которые удалили с диска во время работы.

        Вызывается фоновым потоком ``LoggerWatchdog`` (``start_file_watchdog``). Общий
        обработчик проверяется один раз, сколько бы логгеров через него ни писало.
        Файлы, которые на месте, не трогаются.

        Returns:
            Сколько файлов пришлось пересоздать.

        Пример:
            >>> os.remove('logs/app.log')
            >>> AppLogger.reopen_missing_files()
            1
        """
        with cls._instances_lock:
            handlers = {
                id(inst.file_handler): inst.file_handler
                for inst in cls._instances.values()
                if inst.file_handler is not None and hasattr(inst.file_handler, 'reopen_if_needed')
            }

        reopened = 0
        for handler in handlers.values():
            try:
                if handler.reopen_if_needed():
                    reopened += 1
            except Exception:
                # Например, нет прав на папку — об ошибке сообщит следующая запись
                pass
        return reopened

    @classmethod
    def reopen_all_files(cls) -> None:
        """
        Принудительно переоткрывает файлы всех логгеров (``force_reopen``), даже существующие.

        Для регулярной проверки используйте ``reopen_missing_files()`` — она трогает только
        удалённые файлы. Этот метод — после внешних операций с папкой логов.

        Returns:
            None

        Пример:
            >>> shutil.move('logs', 'logs_old'); os.mkdir('logs')
            >>> AppLogger.reopen_all_files()
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.file_handler and hasattr(inst.file_handler, 'force_reopen'):
                    inst.file_handler.force_reopen()

    @classmethod
    def reload_all_from_config(cls, global_config: Dict[str, Any]) -> None:
        """
        Применяет плоский конфиг ко всем логгерам класса (``reload_from_config`` каждого).

        Ключи с префиксом ``{имя}_`` дополнительно передаются логгеру без префикса (например,
        ``system_LEVEL`` → ``LEVEL`` для ``system``), остальные — общие. После перезагрузки
        файлы включённых логгеров проверяются на существование.

        Args:
            global_config: Плоский словарь настроек (как у ``AppConfigManager.get_all()``).

        Returns:
            None

        Пример:
            >>> AppLogger.reload_all_from_config({'LOG_FILE': 'logs/', 'LOG_LEVEL': 'INFO',
            ...     'LOG_MAX_BYTES': 10**7, 'LOG_BACKUP_COUNT': 5, 'system_LEVEL': 'DEBUG'})
        """
        # P8 (2026-10-14): опечатки в ключах логгера раньше молча игнорировались
        suspicious = cls.find_suspicious_config_keys(global_config)
        if suspicious:
            warnings.warn(
                'Логгер не понимает ключи конфига (опечатка или регистр?): '
                + ', '.join(suspicious)
                + '. Допустимые окончания: ' + ', '.join(sorted(cls.CONFIG_KEYS)),
                UserWarning,
                stacklevel=2,
            )
        with cls._instances_lock:

            for inst in cls._instances.values():
                # Формируем конфиг для этого логгера: сначала общие настройки, затем специфичные
                specific = {}
                for key, value in global_config.items():
                    if key.startswith(f"{inst.name}_"):
                        # Убираем префикс для внутреннего использования
                        specific[key[len(inst.name)+1:]] = value

                # Объединяем: специфичные переопределяют общие
                merged = {**global_config, **specific}
                inst.reload_from_config(merged)

            # Дополнительно: после изменения конфигурации можно принудительно переоткрыть файлы
            # для всех логгеров, у которых включено файловое логирование
            for inst in cls._instances.values():
                if inst._file_enabled and inst.file_handler:
                    inst._reopen_file_handler_if_needed()

    @classmethod
    def add_global_handler(cls, handler: logging.Handler) -> None:
        """
        Добавляет обработчик ко всем существующим и будущим логгерам (всех наследников).

        Используется окном логов GUI. Каждый логгер фильтрует записи своим уровнем;
        уровень самого обработчика логгеры не меняют (S3). Для вывода в функцию удобнее
        ``add_global_output()``.

        Args:
            handler: Любой ``logging.Handler``.

        Returns:
            None

        Пример:
            >>> class ListHandler(logging.Handler):
            ...     def emit(self, record): records.append(record)
            >>> AppLogger.add_global_handler(ListHandler())
        """
        with cls._global_handlers_lock:
            cls._global_handlers.append(handler)

        # добавление к экземплярам уже под _instances_lock
        with cls._instances_lock:
            # Добавляем ко всем уже созданным экземплярам
            for instance in cls._instances.values():
                with instance._handler_lock:
                    instance.logger.addHandler(handler)
                    # Обновляем список обработчиков экземпляра (опционально)
                    instance.handlers = instance.logger.handlers[:]

    @classmethod
    def remove_global_handler(cls, handler: logging.Handler) -> None:
        """
        Убирает глобальный обработчик из списка и со всех логгеров. Не закрывает его.

        Args:
            handler: Обработчик, добавленный ``add_global_handler``.

        Returns:
            None

        Пример:
            >>> AppLogger.remove_global_handler(handler)
            >>> handler.close()
        """

        with cls._global_handlers_lock:
            # Если обработчик есть в глобальном списке, удаляем его
            if handler in cls._global_handlers:
                cls._global_handlers.remove(handler)

        with cls._instances_lock:
            # Удаляем обработчик из каждого существующего экземпляра
            for instance in cls._instances.values():
                with instance._handler_lock:
                    instance.logger.removeHandler(handler)

                    # Обновляем список обработчиков экземпляра (опционально)
                    instance.handlers = instance.logger.handlers[:]
            
    @classmethod
    def add_global_output(
        cls,
        func: Callable[[str], Any],
        level: Union[int, str] = logging.NOTSET,
        background: bool = False,
        formatter: Optional[Union[logging.Formatter, str]] = None,
        queue_size: int = 1000,
    ) -> CallableHandler:
        """
        Добавляет вывод в функцию для ВСЕХ логгеров — существующих и будущих.

        Работает через глобальные обработчики (``add_global_handler``), поэтому общий
        для всех наследников BaseAppLogger. Каждый логгер фильтрует своим уровнем,
        затем — порог ``level``.

        Args:
            func: Функция, принимающая одну строку.
            level: Порог вывода (имя или число).
            background: Доставка в фоновом потоке (для медленных функций).
            formatter: ``None`` — стандартный формат ``LOG_FORMAT``; строка формата;
                или ``logging.Formatter``.
            queue_size: Размер очереди для ``background=True``.

        Returns:
            Созданный ``CallableHandler`` (для ``remove_global_output``).

        Пример:
            >>> AppLogger.add_global_output(send_tg, level='CRITICAL', background=True,
            ...                             formatter='%(name)s: %(plain_message)s')
        """
        handler = CallableHandler(func, level=level, background=background, queue_size=queue_size)
        handler.setFormatter(cls._make_output_formatter(formatter, logging.Formatter(cls.LOG_FORMAT)))
        cls.add_global_handler(handler)
        return handler

    @classmethod
    def remove_global_output(cls, output: Union[CallableHandler, Callable[[str], Any]]) -> bool:
        """
        Убирает глобальный вывод-функцию у всех логгеров и закрывает его.

        Args:
            output: Обработчик из ``add_global_output()`` или сама функция.

        Returns:
            ``True``, если что-то было убрано.

        Пример:
            >>> h = AppLogger.add_global_output(print)
            >>> AppLogger.remove_global_output(h)
            True
        """
        with cls._global_handlers_lock:
            matched = [
                h for h in cls._global_handlers
                if isinstance(h, CallableHandler) and (h is output or h.func == output)
            ]
        for handler in matched:
            cls.remove_global_handler(handler)
            handler.close()
        return bool(matched)

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Конфиг для логгера, созданного без ``config`` (``get_instance(name)``).

        В BaseAppLogger не задан — наследник обязан переопределить (как ``AppLogger``) или
        каждый раз передавать ``config``. Обязательные ключи: ``LEVEL``, ``FILE``,
        ``MAX_BYTES``, ``BACKUP_COUNT`` (с префиксом ``LOG_`` или без).

        Returns:
            Плоский словарь настроек.

        Raises:
            RuntimeError: Метод не переопределён.

        Пример:
            >>> class MyLogger(BaseAppLogger):
            ...     _instances = {}
            ...     @classmethod
            ...     def get_default_config(cls):
            ...         return {'LOG_LEVEL': 'INFO', 'LOG_FILE': 'logs/',
            ...                 'LOG_MAX_BYTES': 10_000_000, 'LOG_BACKUP_COUNT': 5}
        """
        raise RuntimeError(
            "Метод get_default_config() не переопределён в наследнике. "
            "Передайте config напрямую в get_instance() или переопределите метод."
        )

    @classmethod
    def disable_group(cls, name_prefix: str) -> None:
        """
        Выключает все логгеры, имя которых начинается с ``name_prefix``.

        Сравнение — ``str.startswith``: ``'gui.Table'`` захватит и ``'gui.TableX'``. Чтобы
        взять только «детей», добавьте точку: ``'gui.Table.'``.

        Args:
            name_prefix: Начало имени.

        Returns:
            None

        Пример:
            >>> AppLogger.disable_group('gui.')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.disable()

    @classmethod
    def enable_group(cls, name_prefix: str) -> None:
        """
        Включает все логгеры, имя которых начинается с ``name_prefix``.

        Args:
            name_prefix: Начало имени (``str.startswith``).

        Returns:
            None

        Пример:
            >>> AppLogger.enable_group('gui.')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.enable()

    @classmethod
    def set_group_level(cls, name_prefix: str, level: Union[str, int]) -> None:
        """
        Ставит порог ``logging.Logger`` всем логгерам группы через ``setLevel``.

        Меняется только порог ``logging.Logger``, а не ``log_level``/``get_level()``. Для
        полной смены уровня используйте ``reconfigure_group(prefix, level=...)``.

        Args:
            name_prefix: Начало имени (``str.startswith``).
            level: Имя уровня или число.

        Returns:
            None

        Пример:
            >>> AppLogger.set_group_level('api.', 'ERROR')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.setLevel(cls._parse_log_level(level))

    @classmethod
    def get_group_loggers(cls, name_prefix: str) -> list:
        """
        Имена логгеров, начинающиеся с ``name_prefix``.

        Args:
            name_prefix: Начало имени (``str.startswith``).

        Returns:
            Список имён в порядке создания.

        Пример:
            >>> AppLogger.get_group_loggers('gui.Table')
            ['gui.Table', 'gui.Table.Model']
        """
        with cls._instances_lock:
            return [
                inst.name 
                for inst in cls._instances.values() 
                if inst.name.startswith(name_prefix)
            ]

    @classmethod
    def reconfigure_group(cls, name_prefix: str, **kwargs: Any) -> None:
        """
        Вызывает ``reconfigure(**kwargs)`` у всех логгеров группы.

        Args:
            name_prefix: Начало имени (``str.startswith``).
            **kwargs: Аргументы ``reconfigure`` (``level``, ``console_enabled``, ...).

        Returns:
            None

        Пример:
            >>> AppLogger.reconfigure_group('gui.', level='WARNING', console_enabled=False)
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.reconfigure(**kwargs)

    @classmethod
    def disable_group_console(cls, name_prefix: str) -> None:
        """
        Выключает консоль у всех логгеров группы.

        Args:
            name_prefix: Начало имени (``str.startswith``).

        Returns:
            None

        Пример:
            >>> AppLogger.disable_group_console('gui.PaginatedTableModel')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.disable_console()

    @classmethod
    def enable_group_console(cls, name_prefix: str) -> None:
        """
        Включает консоль у всех логгеров группы.

        Args:
            name_prefix: Начало имени (``str.startswith``).

        Returns:
            None

        Пример:
            >>> AppLogger.enable_group_console('gui.')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.enable_console()

    @classmethod
    def disable_group_file(cls, name_prefix: str) -> None:
        """
        Выключает запись в файл у всех логгеров группы (``turn_off_file_logging``).

        Args:
            name_prefix: Начало имени (``str.startswith``).

        Returns:
            None

        Пример:
            >>> AppLogger.disable_group_file('api.')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.turn_off_file_logging()

    @classmethod
    def enable_group_file(cls, name_prefix: str) -> None:
        """
        Включает запись в файл у всех логгеров группы (``turn_on_file_logging``).

        Args:
            name_prefix: Начало имени (``str.startswith``).

        Returns:
            None

        Пример:
            >>> AppLogger.enable_group_file('api.')
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.turn_on_file_logging()

    # Также можно добавить установку уровня отдельно для консоли и файла для группы:
    @classmethod
    def set_group_console_level(cls, name_prefix: str, level: Union[str, int]) -> None:
        """
        Ставит отдельный уровень консоли всем логгерам группы (``set_console_level``).

        Отдельный уровень живёт до следующего перестроения обработчиков логгера.

        Args:
            name_prefix: Начало имени (``str.startswith``).
            level: Имя уровня или число.

        Returns:
            None

        Пример:
            >>> AppLogger.set_group_console_level('gui.', 'ERROR')
        """
        with cls._instances_lock:
            lvl = cls._parse_log_level(level)
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.set_console_level(lvl)

    @classmethod
    def set_group_file_level(cls, name_prefix: str, level: Union[str, int]) -> None:
        """
        Ставит отдельный уровень файлового обработчика всем логгерам группы.

        Если файл общий (мастер/слейв), порог действует на всех, кто через него пишет.

        Args:
            name_prefix: Начало имени (``str.startswith``).
            level: Имя уровня или число.

        Returns:
            None

        Пример:
            >>> AppLogger.set_group_file_level('api.', 'WARNING')
        """
        with cls._instances_lock:
            lvl = cls._parse_log_level(level)
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.set_file_level(lvl)

    @classmethod
    def thec_create(
        cls,
        name: str,
    ) -> bool:
        """
        Есть ли в реестре класса логгер с этим именем.

        Args:
            name: Имя логгера.

        Returns:
            ``True``, если логгер уже создан.

        Пример:
            >>> AppLogger.thec_create('system')
            True
        """
        with cls._instances_lock:
            return (name in cls._instances )

    
    @classmethod
    def _create_instance_and_share(
        cls,
        name: str, # имя экземпляра логгера (строка)
        config: Optional[Union[str, Dict[str, Any]]], # конфигурация логгера (словарь)
        enable_file_logging: Union[str, bool] = True, # включить файловое логирование
        use_name_in_filename: Union[str, bool] = False,  # использовать имя экземпляра в имени файла
        show_call_depth: bool = False, # показывать глубину вызова
        sync_full_state: Optional[bool] = False, # синхронизировать полное состояние
        auto_share: bool = True, # автоматический шаринг
    ) -> 'BaseAppLogger':
        """
        Создаёт логгер, регистрирует его в реестре и при ``auto_share`` подключает к общему файлу.

        Автоподключение при создании: к первому логгеру с тем же ``base_log_file``, который
        держит открытый обработчик и не использует имя в файле. Дальше, при перестроениях,
        работает ``_file_share_target``.

        Args:
            name: Имя логгера.
            config: Словарь настроек, имя логгера-источника или ``None``.
            enable_file_logging: См. ``__init__``.
            use_name_in_filename: См. ``__init__``.
            show_call_depth: См. ``__init__``.
            sync_full_state: См. ``__init__`` (``None`` — унаследовать у мастера).
            auto_share: Искать логгер с тем же файлом при создании.

        Returns:
            Новый логгер.

        Пример:
            Вызывается из ``get_instance``.
        """
        with cls._instances_lock:
            # Создаём новый экземпляр
            instance = cls(
                name=name,
                config=config,
                enable_file_logging = enable_file_logging,
                use_name_in_filename = use_name_in_filename,
                show_call_depth=show_call_depth, 
                sync_full_state=sync_full_state,
            )
            # instance._sync_full_state = sync_full_state
            # ↑ до S4: перезаписывало флаг, унаследованный от мастера при подключении
            #   внутри конструктора. Конструктор уже выставил его сам.
            cls._instances[name] = instance

            # Автоматический шаринг, если разрешено
            if auto_share and not instance._use_name_in_filename:
                # Ищем любой другой логгер с таким же base_log_file и без использования имени
                for other_name, other in cls._instances.items():
                    if other_name == name:
                        continue
                    # Используем effective_use_name_in_filename для проверки        
                    if (
                        # not other._use_name_in_filename and
                        not other.effective_use_name_in_filename(_visited=None) and  # Используем эффективное значение, чтобы правильно обработать строковые ссылки
                        other.base_log_file == instance.base_log_file and
                        other.file_handler is not None
                    ):
                        instance.share_file_handler_with(other)
                        break

            return instance

    @classmethod
    def _get_instance(
        cls,
        name: str,
        share_file_with: Optional[str],
        sync_full_state: Optional[bool] = None,
    ) -> 'BaseAppLogger':
        """
        Возвращает существующий логгер; если просили общий файл и связи ещё нет — подключает.

        Args:
            name: Имя существующего логгера.
            share_file_with: Имя логгера, к чьему файлу подключиться, или ``None``.
            sync_full_state: Флаг полной синхронизации для подключения.

        Returns:
            Логгер из реестра.

        Пример:
            Вызывается из ``get_instance`` для уже созданного имени.
        """
        with cls._instances_lock:
            # экземпляр с таким именем уже существует - возвращается существующий
            inst = cls._instances[name]
            # Если запрошен шаринг с другим логгером, но ещё не настроен – настраиваем
            if share_file_with and not inst.has_shared_handler():
                other = cls._instances.get(share_file_with)

                if other and other.file_handler:
                    inst.share_file_handler_with(
                        other,
                        sync_full_state=sync_full_state,
                    )

        return inst

    @classmethod
    def get_instance(
        cls,
        name: str = 'default',
        force_new: bool = False,
        config: Optional[Dict[str, Any]] = None,
        enable_file_logging: Union[str,bool] = False,
        use_name_in_filename: Union[str,bool] = False,
        share_file_with: Optional[str] = None,
        show_call_depth: bool = False, # показывать уровень вложенности
        # sync_full_state: bool = False,
        # ↑ до S4: явный False при подключении к мастеру затирал унаследованный флаг.
        #   None — для мастера False, для слейва — как у мастера.
        sync_full_state: Optional[bool] = None,
        # auto_share: bool = False, # Пока не используется
        # ↑ P7: None — не передан; любое значение — DeprecationWarning (параметр не работает).
        auto_share: Optional[bool] = None, # Пока не используется
    ) -> 'BaseAppLogger':
        """
        Главная точка получения логгера: возвращает существующий или создаёт новый.

        Если логгер с этим именем уже есть и ``force_new=False`` — возвращается он, новые
        аргументы игнорируются (кроме попытки подключиться к ``share_file_with``). Первый
        вызов с этим именем определяет настройки. ``force_new=True`` заменяет логгер в
        реестре; старый снимает свои обработчики (B3).

        Args:
            name: Имя логгера (видно в каждой строке ``[name]``).
            force_new: Создать новый, даже если имя занято.
            config: Словарь настроек, имя логгера-источника или ``None`` (``get_default_config``).
            enable_file_logging: ``True``/``False`` или имя логгера-родителя, чей файл и
                настройки использовать (так подключены почти все логгеры приложения:
                ``enable_file_logging='system'``).
            use_name_in_filename: Отдельный файл ``<name>.log``; или имя логгера-источника.
            share_file_with: Имя логгера, к чьему файлу подключиться (без наследования настроек).
            show_call_depth: Отступ ``>`` по глубине стека в каждой строке.
            sync_full_state: Флаг полной синхронизации (S4); ``None`` — для слейва как у мастера.
            auto_share: Не используется (оставлен для совместимости).

        Returns:
            Логгер.

        Пример:
            >>> log = AppLogger.get_instance('PatientService', enable_file_logging='system')
            >>> log.info('Пациент создан')

            >>> @AppLogger.get_instance('ConfigApplier', enable_file_logging='system') \\
            ...     .log_execution_time(level=logging.DEBUG)
            ... def apply(): ...
        """
        # P7 (2026-10-14): параметр auto_share никогда не работал (автоподключение задаётся
        # отсутствием share_file_with) — предупреждаем, если его передали.
        if auto_share is not None:
            warnings.warn(
                'get_instance(auto_share=...) устарел и ни на что не влияет.',
                DeprecationWarning,
                stacklevel=2,
            )

        # Если enable_file_logging – строка и это не 'true'/'false', используем как имя для шаринга
        if (
            isinstance(enable_file_logging, str) 
            # and enable_file_logging.lower() not in ('true', 'false')
        ):
            low = enable_file_logging.lower()
            if low in ('true', 'false'):
                enable_file_logging = low == 'true'
                
            else:
                share_file_with = enable_file_logging
                # enable_file_logging = True # файловое логирование включаем, но обработчик будет общим  

        if isinstance(use_name_in_filename, str):
            low = use_name_in_filename.lower()
            if low in ('true', 'false'):
                use_name_in_filename = low == 'true'
            else:
                # небулева строка – оставляем как есть, конструктор разберётся
                pass
        
        with cls._instances_lock:

            if not cls._instances:
                cls.start_file_watchdog()

            if not force_new and name in cls._instances:
                # Если экземпляр с таким именем уже существует и force_new=False, возвращается существующий
                return cls._get_instance(
                    name=name,
                    share_file_with=share_file_with,
                    sync_full_state=sync_full_state,
                )

            # force_new для существующего имени: старый экземпляр снимает свои обработчики
            # с общего logging.Logger (он один на имя). До исправления B3 они оставались,
            # и каждое сообщение выводилось дважды — старой и новой консолью.
            if force_new and name in cls._instances:
                cls._instances[name]._retire()
            auto_share_flag = share_file_with is None
            instance = cls._create_instance_and_share( # Создаём новый экземпляр и применяем шаринг
                name=name,
                config=config,
                enable_file_logging = enable_file_logging,
                use_name_in_filename = use_name_in_filename,
                show_call_depth=show_call_depth,
                sync_full_state=sync_full_state,  # None допустим (S4)

                # auto_share=False,
                auto_share=auto_share_flag
            )

            # После создания – если нужен шаринг, применяем
            # if share_file_with:
            #     other = cls._instances.get(share_file_with)
            #     # if other and other.file_handler:
            #     if other and other._file_enabled and other.file_handler:
            #         instance.share_file_handler_with(
            #             other,
            #             sync_full_state=sync_full_state,
            #         )
            #         # # Немедленно перезагружаем настройки с учётом нового мастера
            #         # instance.reload_from_config(
            #         #     instance.get_default_config()
            #         # )
            #     else:
            #         # Логгируем предупреждение, но продолжаем
            #         print(f"WARNING: Не удалось расшарить файловый обработчик с '{share_file_with}' для логгера '{name}'.", file=sys.stderr)
            #         # if instance.logger:
            #         #     instance.logger.info(
            #         #         f"Файловый обработчик не общий с '{share_file_with}': у мастера он отключён. Будет использоваться собственный."
            #         #     )

            if share_file_with:
                other = cls._instances.get(share_file_with)
                if other:
                    # Проверяем, должен ли у other быть файловый обработчик
                    # (учитываем эффективное состояние файлового логирования)
                    # if other.effective_enable_file_logging(_visited=None):
                    # ↑ до исправления S1: проверялся аргумент конструктора other, а не его
                    #   состояние; к system (файл включён конфигом) не подключался никто.
                    if other._enabled and other._file_enabled:
                        # Файловое логирование включено, но обработчик отсутствует – это ошибка
                        if other.file_handler is None:
                            print(f"WARNING: У логгера '{share_file_with}' включено файловое логирование, "
                                  f"но обработчик отсутствует. Расшаривание для '{name}' невозможно.",
                                  file=sys.stderr)
                        else:
                            instance.share_file_handler_with(
                                other,
                                sync_full_state=sync_full_state,
                            )
                    else:
                        # У other файловое логирование отключено – ничего не делаем, предупреждение не нужно
                        pass
                else:
                    # Логгер с именем share_file_with не существует
                    print(
                        f"WARNING: Логгер '{share_file_with}', с которым требуется расшарить обработчик, не найден.",
                        file=sys.stderr
                    )


            return instance

    @classmethod
    def close_all(cls) -> None:
        """
        Закрывает все логгеры класса и очищает реестр.

        Глобальные обработчики и список отключённых логгеров не трогаются.

        Returns:
            None

        Пример:
            >>> AppLogger.close_all()     # при выходе из программы или в тестах
        """

        with cls._instances_lock:
            for instance in cls._instances.values():
                instance.close()
            cls._instances.clear()

        # Общие выводы класса (OUTPUTS): доставить остаток и закрыть
        cls.close_class_outputs()
