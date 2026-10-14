# app/utils/logger/_config.py

"""
Часть ``BaseAppLogger``: Чтение конфигурации.

Содержит примесь ``_ConfigMixin``: приоритеты ключей и наследование от родителя, проверка и загрузка конфига, reload_from_config, разбор уровней.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_ConfigMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _ConfigMixin)
    True
"""

import warnings
import logging
import sys
from typing import List, Optional, Dict, Any, Callable, Union


from ._common import LOGGER_CODE_FILES, _NOT_FOUND

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _ConfigMixin:
    """
    Примесь ``BaseAppLogger``: приоритеты ключей и наследование от родителя, проверка и загрузка конфига, reload_from_config, разбор уровней.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._ConfigMixin'>, ...)
    """

    # Окончания ключей конфига, которые понимает логгер (после префикса {имя}_ или LOG_,
    # либо без префикса). Регистр важен: 'system_level' не то же, что 'system_LEVEL'.
    CONFIG_KEYS = frozenset({
        'LEVEL', 'FILE', 'DIR', 'MAX_BYTES', 'BACKUP_COUNT', 'ARGS',
        'enabled', 'console_enabled', 'file_enabled',
        'use_name_in_filename', 'use_timestamp', 'show_call_depth',
    })

    @classmethod
    def find_suspicious_config_keys(
        cls,
        config: Dict[str, Any],
        logger_names: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Ключи конфига, похожие на настройки логгера, но с неизвестным окончанием (P8).

        Конфиг приложения общий: в нём много чужих ключей (``YANDEX_TOKEN``, пути),
        поэтому проверяются только ключи, начинающиеся с ``LOG_`` или с
        ``<имя логгера>_``. Если окончание такого ключа не входит в ``CONFIG_KEYS`` —
        это, скорее всего, опечатка или неверный регистр, и логгер ключ проигнорирует.

        Args:
            config: Плоский словарь настроек.
            logger_names: Имена логгеров для проверки префиксов; ``None`` — все из реестра.

        Returns:
            Список подозрительных ключей в порядке словаря (пустой — всё в порядке).

        Пример:
            >>> AppLogger.find_suspicious_config_keys(
            ...     {'system_LEVLE': 'DEBUG', 'system_level': 'INFO', 'LOG_LEVEL': 'INFO',
            ...      'YANDEX_TOKEN': '...'}, logger_names=['system'])
            ['system_LEVLE', 'system_level']
        """
        if logger_names is None:
            with cls._instances_lock:
                logger_names = list(cls._instances)
        # длинные имена раньше: 'gui.Table' должен победить 'gui'
        prefixes = sorted((n + '_' for n in logger_names), key=len, reverse=True)

        suspicious = []
        for key in config:
            if not isinstance(key, str):
                continue
            if key.startswith('LOG_'):
                suffix = key[len('LOG_'):]
            else:
                prefix = next((p for p in prefixes if key.startswith(p)), None)
                if prefix is None:
                    continue
                suffix = key[len(prefix):]
            if suffix not in cls.CONFIG_KEYS:
                suspicious.append(key)
        return suspicious


    def _get_settings_parent(self) -> Optional['BaseAppLogger']:
        """
        Логгер, от которого этот наследует настройки при чтении конфига.

        Приоритет: мастер общего файла → ссылка ``enable_file_logging='имя'`` → ссылка
        ``use_name_in_filename='имя'``.

        Returns:
            Логгер-родитель или ``None``.

        Пример:
            >>> svc = AppLogger.get_instance('svc', enable_file_logging='system')
            >>> svc._get_settings_parent().name
            'system'
        """
        with self._handler_lock:
            # Приоритет: мастер файлового обработчика > ссылка enable_file_logging > ссылка use_name_in_filename
            if self._master_logger:
                return self._master_logger
            
            if self._enable_file_logging_ref:
                return self._get_parent(self._enable_file_logging_ref)
            
            if self._use_name_in_filename_ref:
                return self._get_parent(self._use_name_in_filename_ref)
        
        return None

    def _get_config_with_inheritance(
        self,
        config: Dict[str, Any],
        key: str,
        default: Any = None,
        _visited: Optional[set] = None
    ) -> Any:
        """
        Возвращает значение параметра из конфига с учётом иерархии мастер-слейв.
        Приоритет (по убыванию):
        1. {self.name}_{key}
        2. если есть мастер, значение от мастера (рекурсивно, с его именем)
        3. LOG_{key}
        4. key
        5. default

        Цикл ссылок (a → b → a): повторный заход в уже пройденный логгер возвращает
        маркер «не найдено», и поиск продолжается с шага 3 у того, кто начал цикл.
        До исправления (B1) возвращался ``default`` — шаги 3–4 пропускались, и,
        например, путь к файлу из ``LOG_FILE`` подменялся на ``'logs'``.

        Args:
            config: Плоский словарь конфигурации.
            key: Ключ без префикса (``'LEVEL'``, ``'FILE'``, ``'file_enabled'``...).
            default: Значение, если ключ не найден нигде.
            _visited: Служебное: ``id`` уже пройденных логгеров (защита от циклов).

        Returns:
            Найденное значение или ``default``.

        Пример:
            >>> log._get_config_with_inheritance({'LOG_LEVEL': 'INFO', 'svc_LEVEL': 'ERROR'}, 'LEVEL')
            'ERROR'   # для логгера с именем 'svc'
        """
        
        if _visited is None:
            _visited = set()

        # if self.name in _visited:
        #     # защита от циклической ссылки
        #     return default
        
        if id(self) in _visited:          # используем id для защиты от циклов
            # return default
            # ↑ до исправления B1: цикл обрывал поиск значением по умолчанию.
            return _NOT_FOUND
        
        _visited.add(id(self))

        # 1. Специфичный ключ для текущего логгера
        specific_key = f"{self.name}_{key}"
        if specific_key in config:
            return config[specific_key]

        # # 2. Если есть мастер, запросить у него (рекурсивно)
        # if self._master_logger:
        #     return self._master_logger._get_config_with_inheritance(
        #         config, key, default, _visited
        #     )

        # 2. Родитель по настройкам (мастер файлового обработчика или ссылка enable_file_logging)
        parent = self._get_settings_parent()
        if parent:
            # return parent._get_config_with_inheritance(config, key, default, _visited)
            # ↑ до исправления B1: результат родителя возвращался всегда, даже если это
            #   был обрыв цикла. Теперь «не найдено» у родителя → ищем дальше сами.
            inherited = parent._get_config_with_inheritance(config, key, _NOT_FOUND, _visited)
            if inherited is not _NOT_FOUND:
                return inherited

        # 3. Общий префикс LOG_
        log_key = f"LOG_{key}"
        if log_key in config:
            return config[log_key]

        # 4. Простой ключ
        if key in config:
            return config[key]

        # 5. default
        return default

    def _apply_config(self, config_dict: Dict[str, Any]) -> None:
        """
        Записывает в атрибуты логгера значения, вычисленные ``_init_config_load()``.

        Обработчики не перестраивает — только состояние и порог ``logging.Logger``.

        Args:
            config_dict: Результат ``_init_config_load()`` (ключи ``enabled``, ``LEVEL``,
                ``FILE``, ``MAX_BYTES``…).

        Returns:
            None

        Пример:
            >>> log._apply_config(log._init_config_load(config, None, None))
        """
        self._enabled = config_dict['enabled']
        self._console_enabled = config_dict['console_enabled']
        self._file_enabled = config_dict['file_enabled']
        self._use_name_in_filename = config_dict['use_name_in_filename']
        self.use_timestamp = config_dict['use_timestamp']
        self.log_args = config_dict['ARGS']
        self.log_level = config_dict['LEVEL']
        self.base_log_file = config_dict['FILE']
        self.log_max_bytes = config_dict['MAX_BYTES']
        self.log_backup_count = config_dict['BACKUP_COUNT']
        self._show_call_depth = config_dict['show_call_depth']

        self.logger.setLevel(self.log_level)

    # До 2026-10-14: inspect.stack() на каждую запись. Он строит FrameInfo для ВСЕХ
    # кадров стека и читает строки исходников (контекст) — ~5 мс на вызов log.info()
    # при стеке глубиной 30, а в Qt-приложении стек глубже. Заменено проходом по
    # f_back (sys._getframe) — см. новую реализацию ниже.
    # def _get_call_depth(self) -> int:
    #     """
    #     Вычисляет реальную глубину вызовов на основе стека.
    #     Пропускает фреймы самого логгера и его внутренних методов.
    #     Возвращает количество пользовательских фреймов (глубину вложенности).
    #     """
    #     # import inspect
    #     stack = inspect.stack()
    #     depth = 0
    #     for frame_info in stack[1:]:  # пропускаем текущий фрейм
    #         # Пропускаем фреймы, относящиеся к логгеру
    #         if self._thec_skip_patterns_modeles({
    #             # frame_info.filename может отличаться от co_filename (inspect ищет исходник)
    #             'filename': (frame_info.frame.f_code.co_filename,),
    #             'function': (frame_info.function,)
    #         }):
    #             continue

    #         depth += 1

    #     return depth

    # # До исправления D1 (2026-10-14). Запись шла в contextvars (set не бросает
    # # LookupError, ветка с threading.local не срабатывала никогда), а чтение в
    # # синхронном коде — из threading.local, где всегда 0. Итог: декоратор с
    # # show_depth=True всегда показывал глубину 0.
    # # def _get_current_depth(self) -> int:
    # #     """Возвращает текущую глубину вложенности для текущего контекста (поток/задача)."""

    # #     try:
    # #         loop = asyncio.get_running_loop()
    # #         # Если есть текущая задача, считаем, что это асинхронный контекст
    # #         if asyncio.current_task(loop) is not None:
    # #             return self._depth_context.get()

    # #         else:
    # #             return getattr(self._depth_local, 'depth', 0)

    # #     except (RuntimeError, LookupError) as e:
    # #         err = e
    # #         # Если не задан, используем threading.local (синхронный поток)
    # #         # Нет запущенного event loop – синхронный контекст
    # #         return getattr(self._depth_local, 'depth', 0)

    # # def _set_current_depth(self, depth: int) -> None:
    # #     """Устанавливает глубину для текущего контекста."""
    # #     try:
    # #         self._depth_context.set(depth)

    # #     except LookupError:
    # #         self._depth_local.depth = depth

    def apply_config_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """
        Применяет конфиг к этому логгеру; аналог ``reload_from_config``.

        Обработчики перестраиваются, только если изменились флаги или параметры файла
        (или файл нужен, а обработчика нет); иначе обновляется уровень консоли и
        синхронизируются слейвы.

        Args:
            config_dict: Плоский словарь настроек (ключи — IMPLEMENTATION.md §3.4).

        Returns:
            None

        Пример:
            >>> log.apply_config_from_dict({'LOG_FILE': 'logs/', 'LOG_LEVEL': 'INFO',
            ...     'LOG_MAX_BYTES': 10**7, 'LOG_BACKUP_COUNT': 5, 'file_enabled': 'True'})
        """
        # # Если используем общий обработчик, перенаправляем мастеру
        # if self._shared_handler and self._master_logger:
        #     self._master_logger.apply_config_from_dict(config_dict)
        #     return
        
        need_rebuild = False
        with self._handler_lock:      
            # Сохраняем старые флаги
            old_file = self._file_enabled
            old_console = self._console_enabled
            old_enabled = self._enabled
            old_base_log_file = self.base_log_file
            old_max_bytes = self.log_max_bytes
            old_backup_count = self.log_backup_count
            old_use_timestamp = self.use_timestamp
            old_use_name = self._use_name_in_filename

            # Обновляем текущие параметры

            self._update_config_from(config_dict)
    
            # self._init_config_load(config_dict, None, None)

            # # обновление остальных параметров

            # if 'LOG_LEVEL' in config_dict:
            #     self.log_level = self._parse_log_level(config_dict['LOG_LEVEL'])
            #     self.logger.setLevel(self.log_level)

            # if 'LOG_FILE' in config_dict:
            #     self.base_log_file = config_dict['LOG_FILE']

            # if 'LOG_MAX_BYTES' in config_dict:
            #     self.log_max_bytes = int(config_dict['LOG_MAX_BYTES'])

            # if 'LOG_BACKUP_COUNT' in config_dict:
            #     self.log_backup_count = int(config_dict['LOG_BACKUP_COUNT'])

            # if 'LOG_ARGS' in config_dict:
            #     self.log_args = self._to_bool(config_dict['LOG_ARGS'])

            # if 'show_call_depth' in config_dict:
            #     self._show_call_depth = self._to_bool(config_dict['show_call_depth'])

            # if self._shared_slaves:
            #     self._update_shared_slaves()

            # Проверяем, изменились ли параметры файла
            file_params_changed = (
                self.base_log_file != old_base_log_file or
                self.log_max_bytes != old_max_bytes or
                self.log_backup_count != old_backup_count or
                self.use_timestamp != old_use_timestamp or
                self._use_name_in_filename != old_use_name
            )

            need_rebuild = (
                self._file_enabled != old_file or
                self._console_enabled != old_console or
                self._enabled != old_enabled or
                file_params_changed or
                # Флаги могли не измениться, а обработчик пропасть (мастер выключил
                # общий файл, S2) — тогда тоже перестраиваем.
                self._file_output_missing()
            )

        # применение изменений БЕЗ блокировки
        if need_rebuild:
            self._update_handlers()
            
        else:
            # обновить уровни
            # for handler in self.logger.handlers:
            # handler.setLevel(self.log_level)
            # ↑ до S3: менялся уровень общего файла и глобальных обработчиков (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера).
            if self.console_handler:
                self.console_handler.setLevel(self.log_level)

            if self._shared_slaves:
                self._update_shared_slaves()

    # @property # убираем изза циклических ссылок _visited
    def effective_enable_file_logging(self, _visited: Optional[set] = None) -> bool:
        """
        Аргумент ``enable_file_logging`` конструктора с учётом ссылки на родителя.

        ВНИМАНИЕ: это НЕ текущее состояние файла (оно — ``is_file_enabled()``). Значение
        используется только как умолчание ``file_enabled`` при создании логгера. Путаница
        этих двух была причиной R2, R3, S1 (IMPLEMENTATION.md §6).

        Ссылка ``'имя'`` разрешается рекурсивно; цикл ссылок обрывается (B1) с сообщением.

        Args:
            _visited: Служебное: ``id`` пройденных логгеров (защита от циклов).

        Returns:
            ``True``/``False``.

        Пример:
            >>> AppLogger.get_instance('a', enable_file_logging=True).effective_enable_file_logging()
            True
        """

        if _visited is None:
            _visited = set()

        obj_id = id(self)

        # if self.name in _visited:
        # ↑ до исправления B1: проверялось имя, а в _visited клали id(self) — проверка
        #   никогда не срабатывала, цикл ссылок (a→b→a) давал RecursionError.
        if obj_id in _visited:
            self._report_self_problem(f"Циклическая ссылка в effective_enable_file_logging для {self.name}")
            return self._enable_file_logging
        
        # _visited.add(self.name)
        _visited.add(obj_id)
        
        if self._enable_file_logging_ref:
            # parent = self._instances.get(self._enable_file_logging_ref)
            parent = self._get_parent(self._enable_file_logging_ref)
            
            if parent:
                return parent.effective_enable_file_logging(_visited=_visited)
            
            # # если родитель не найден, логируем предупреждение и возвращаем собственное значение
            # self.logger.warning(
            #     f"Логгер '{self.name}' ссылается на несуществующий '{self._enable_file_logging_ref}'"
            # )
            # родитель не найден

            # if hasattr(self, 'logger') and self.logger:
            # ↑ до R6 работало «случайно»: в __init__ у logging.Logger ещё нет обработчиков,
            #   и warning выводил logging.lastResort. С постоянным NullHandler запись
            #   пропала бы, поэтому пока свои обработчики не созданы — пишем в stderr.
            if self._has_output_handlers():
                self.logger.warning(
                    f"Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._enable_file_logging_ref}'"
                )
            else:
                # логгер ещё не создан — выводим в stderr
                # import sys
                print(
                    f"WARNING: Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._enable_file_logging_ref}'", 
                    file=sys.stderr
                )

        return self._enable_file_logging

    # def effective_enable_file_logging(self, _visited=None):
    #     visited = set()
    #     current = self
    #     while True:
    #         if current.name in visited:
    #             current.logger.error(f"Циклическая ссылка в effective_enable_file_logging для {current.name}")
    #             return current._enable_file_logging
            
    #         visited.add(current.name)
    #         if current._enable_file_logging_ref is None:
    #             return current._enable_file_logging
            
    #         parent = current._get_parent(current._enable_file_logging_ref)
    #         if parent is None:
    #             return current._enable_file_logging
            
    #         current = parent


    # @property # убираем изза циклических ссылок _visited
    def effective_use_name_in_filename(self, _visited: Optional[set] = None) -> bool:
        """
        Аргумент ``use_name_in_filename`` конструктора с учётом ссылки на родителя.

        Как и ``effective_enable_file_logging``, это умолчание при создании, а текущее
        значение — ``use_name_in_filename`` (свойство).

        Args:
            _visited: Служебное: ``id`` пройденных логгеров (защита от циклов).

        Returns:
            ``True``/``False``.

        Пример:
            >>> AppLogger.get_instance('b', use_name_in_filename=True).effective_use_name_in_filename()
            True
        """
        if _visited is None:
            _visited = set()
        obj_id = id(self)
        # if self.name in _visited:
        # ↑ до исправления B1: проверялось имя, а в _visited клали id(self) — проверка
        #   никогда не срабатывала, цикл ссылок (a→b→a) давал RecursionError.
        if obj_id in _visited:
            self._report_self_problem(f"Циклическая ссылка в effective_use_name_in_filename для {self.name}")
            # return self._enable_file_logging
            return self._use_name_in_filename
        
        _visited.add(obj_id)
        # _visited.add(self.name)

        if self._use_name_in_filename_ref:
            # parent = self._instances.get(self._use_name_in_filename_ref)
            parent = self._get_parent(self._use_name_in_filename_ref)

            if parent:
                return parent.effective_use_name_in_filename(_visited=_visited)
            # родитель не найден — логируем предупреждение, если логгер уже существует

            # if hasattr(self, 'logger') and self.logger:
            # ↑ до R6 работало «случайно»: в __init__ у logging.Logger ещё нет обработчиков,
            #   и warning выводил logging.lastResort. С постоянным NullHandler запись
            #   пропала бы, поэтому пока свои обработчики не созданы — пишем в stderr.
            if self._has_output_handlers():
                self.logger.warning(
                    f"Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._use_name_in_filename_ref}'"
                )
            else:
                # логгер ещё не создан — выводим в stderr
                # import sys
                print(
                    f"WARNING: Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._use_name_in_filename_ref}'", 
                    file=sys.stderr
                )
            
        return self._use_name_in_filename


    # ----------------------------------------------------------------------
    # Выводы-функции (add_output): лог в print, Telegram-бот, виджет и т. п.
    # ----------------------------------------------------------------------

    def _get_parent(self, key: str) -> Optional['BaseAppLogger']:
        """
        Логгер с именем ``key`` из реестра этого класса.

        Args:
            key: Имя логгера.

        Returns:
            Логгер или ``None``, если такого нет.

        Пример:
            >>> log._get_parent('system').name
            'system'
        """
        cls = type(self)
        with cls._instances_lock:
        # with type(self)._instances_lock:
            # return self._instances.get(
            return cls._instances.get(
                key 
            )
        
    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Проверяет, что в конфиге есть обязательные ключи.

        Обязательны ``LEVEL``, ``FILE``, ``MAX_BYTES``, ``BACKUP_COUNT`` — в любом варианте:
        ``{name}_KEY``, ``LOG_KEY`` или ``KEY``. ``LOG_DIR`` вместо ``LOG_FILE`` не подходит.

        Args:
            config: Плоский словарь настроек.

        Returns:
            None

        Raises:
            ValueError: Нет ни одного варианта какого-либо ключа.

        Пример:
            >>> log._validate_config({'LOG_LEVEL': 'INFO'})
            Traceback (most recent call last):
            ValueError: Отсутствует обязательный ключ 'FILE' ...
        """
        # required_keys = [
        #     'LOG_LEVEL', 
        #     'LOG_FILE', 
        #     'LOG_MAX_BYTES', 
        #     'LOG_BACKUP_COUNT'
        # ]


        required_keys = ['LEVEL', 'FILE', 'MAX_BYTES', 'BACKUP_COUNT']
        for key in required_keys:
            # Проверяем, есть ли хотя бы один из возможных вариантов ключа
            variants = self._get_key_name_config(key)
            if not any(v in config for v in variants):
                raise ValueError(f"Отсутствует обязательный ключ '{key}' (ни один из вариантов {variants})")     

        # required_keys = []

        # for key in [
        #     'LEVEL', 
        #     'FILE', 
        #     'MAX_BYTES', 
        #     'BACKUP_COUNT'
        # ]:
        #     thec = False
        #     for key2 in self._get_key_name_config(key):
        #         if key2  in config:
        #             required_keys.append(key2)
        #             thec = True

        #     if not thec:
        #         raise ValueError(f"Отсутствует обязательный ключ '{key}' в конфигурации")

        # missing_keys = [key for key in required_keys if key not in config]

        # if missing_keys:
        #     raise ValueError(f"Отсутствуют обязательные ключи конфигурации: {missing_keys}")        

    def _load_config(self, config: Optional[Union[str, Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Превращает аргумент ``config`` конструктора в словарь.

        * словарь — возвращается как есть;
        * строка — имя существующего логгера: собирается словарь из его текущих
          настроек (уровень, файл, ротация, флаги); неизвестное имя — предупреждение в
          stderr и ``get_default_config()``;
        * ``None`` — ``get_default_config()``.

        Args:
            config: Словарь, имя логгера или ``None``.

        Returns:
            Плоский словарь настроек.

        Пример:
            >>> log._load_config('system')['LOG_LEVEL']
            'DEBUG'
        """
        # Обработка config: если строка, берём из другого экземпляра
        if isinstance(config, str) and config is not None:
            # parent = self._instances.get(config)
            # with type(self)._instances_lock:
            #     parent = self._instances.get(config)
            parent = self._get_parent(config)

            if parent is not None:
                # config = {
                #     'LOG_LEVEL' : dict(
                #         zip(
                #             BaseAppLogger.level_map.values(), 
                #             BaseAppLogger.level_map.keys()
                #         )
                #     )[parent.log_level],
                #     'LOG_FILE' : parent.base_log_file,
                #     'LOG_MAX_BYTES' : parent.log_max_bytes,
                #     'LOG_BACKUP_COUNT' : parent.log_backup_count,
                # }
                config = {
                    'LOG_LEVEL': dict(
                        zip(
                            BaseAppLogger.level_map.values(), 
                            BaseAppLogger.level_map.keys()
                        )
                    )[parent.log_level],
                    'LOG_FILE': parent.base_log_file,
                    'LOG_MAX_BYTES': parent.log_max_bytes,
                    'LOG_BACKUP_COUNT': parent.log_backup_count,
                    'enabled': parent._enabled,
                    'console_enabled': parent._console_enabled,
                    'file_enabled': parent._file_enabled,
                    'use_name_in_filename': parent._use_name_in_filename,
                    'use_timestamp': parent.use_timestamp,
                    'LOG_ARGS': parent.log_args,
                    'show_call_depth': parent._show_call_depth,
                }
            else:
                # родитель не найден – используем дефолт
                print(f"WARNING: Logger '{self.name}' references unknown config '{config}'", file=sys.stderr)
                config = None

        # Загружаем конфигурацию
        if config is None:
            config = self.get_default_config()

        return config

    @staticmethod
    def _to_bool(value: Any) -> bool:
        """
        Приводит значение из конфига к ``bool``.

        Строки: ``'true'``, ``'1'``, ``'yes'`` (без учёта регистра) → ``True``, любые другие
        (в том числе ``'on'``) → ``False``. Не строки — обычный ``bool(value)``.

        Args:
            value: Значение из конфига (строка из msgpack/.env или bool/int).

        Returns:
            ``True``/``False``.

        Пример:
            >>> BaseAppLogger._to_bool('Yes'), BaseAppLogger._to_bool('on'), BaseAppLogger._to_bool(1)
            (True, False, True)
        """
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)
    
    def _get_config_param (
            self,
            config: Dict[str, Any],
            key: str,
            default: Any=None,
            fun: Optional[Callable[[Any], Any]]=None
        )-> Any:
        """
        Значение ключа (``{name}_KEY`` → ``LOG_KEY`` → ``KEY``), приведённое функцией ``fun``.

        Сейчас не используется (его заменил ``_get_config_with_inheritance`` в
        ``_init_config_load``); оставлен для совместимости.

        Args:
            config: Плоский словарь настроек.
            key: Ключ без префикса.
            default: Значение, если ключа нет.
            fun: Функция приведения (``int``, ``_to_bool``); ``None`` — без приведения.

        Returns:
            Значение.

        Raises:
            ValueError: ``fun`` не смогла привести значение.

        Пример:
            >>> log._get_config_param({'LOG_MAX_BYTES': '100'}, 'MAX_BYTES', fun=int)
            100
        """
        # P7 (2026-10-14): устаревшее — оставлено для совместимости, не удаляется.
        warnings.warn(
            '_get_config_param() устарел: используйте _get_config_with_inheritance().',
            DeprecationWarning,
            stacklevel=2,
        )

        # if key == 'LEVEL':
        #     0==0

        temp = self._get_config(
            config= config, 
            key= key, 
            default= default,
        )

        if fun is not None:
            try:
                temp = fun(temp)
            except ValueError as e:
                raise ValueError(f"Ошибка преобразования параметров логирования: {e}")
            
        return temp

        
    def _init_config_load (
        self,
        config: Dict[str, Any],
        enable_file_logging: Any,
        use_name_in_filename: Any,
    )-> Dict[str, Any]:
        """
        Вычисляет все настройки логгера из конфига с учётом иерархии и умолчаний.

        Каждый ключ ищется ``_get_config_with_inheritance`` (свой ``{name}_KEY`` → родитель
        → ``LOG_KEY`` → ``KEY`` → умолчание) и приводится к типу. Умолчания:
        ``file_enabled``/``use_name_in_filename`` — аргументы конструктора
        (``effective_*``), ``show_call_depth`` — текущее значение (аргумент, B5),
        ``FILE`` → ``DIR`` → ``'logs'``.

        Args:
            config: Плоский словарь настроек.
            enable_file_logging: Не используется (оставлен для совместимости вызовов).
            use_name_in_filename: Не используется (оставлен для совместимости вызовов).

        Returns:
            Словарь с ключами ``enabled``, ``console_enabled``, ``file_enabled``,
            ``use_name_in_filename``, ``use_timestamp``, ``ARGS``, ``LEVEL`` (число), ``FILE``,
            ``MAX_BYTES``, ``BACKUP_COUNT``, ``show_call_depth``.

        Raises:
            ValueError: Значение не приводится (уровень, число).

        Пример:
            >>> log._init_config_load({'LOG_LEVEL': 'info', 'LOG_FILE': 'logs/',
            ...     'LOG_MAX_BYTES': '100', 'LOG_BACKUP_COUNT': 1}, None, None)['LEVEL']
            20
        """
        # Чтение флагов из конфигурации (с значениями по умолчанию)
        # self._enabled = config.get('enabled', True)
        # self._console_enabled = config.get('console_enabled', True)
        # self._file_enabled = config.get('file_enabled', bool(enable_file_logging)) # флаг для файлового вывода
        # self._use_name_in_filename = config.get('use_name_in_filename', bool(use_name_in_filename))
        # self.use_timestamp = config.get('use_timestamp', False)


        # Определяем эффективное значение флагов (с учётом ссылок)
        effective_file = self.effective_enable_file_logging(_visited=None)
        effective_name = self.effective_use_name_in_filename(_visited=None)

        # if self.name in (
        #     'Database',
        #     'DynamicTableModel',
        # ):
        #     0==0

        # Общие флаги (если есть специфичные для имени)
        result = {}
        
        # temp = self._get_config(config, 'FILE', None)
        temp = self._get_config_with_inheritance(config, 'FILE', None)
        if temp is None:
            # temp = self._get_config(config, 'DIR', 'logs')
            temp = self._get_config_with_inheritance(config, 'DIR', 'logs')

        result['FILE'] = temp

        del temp  

        for key, default, fun  in [
            ['enabled',True,self._to_bool],
            ['console_enabled',True,self._to_bool],
            ['file_enabled',effective_file, self._to_bool],
            ['use_name_in_filename',effective_name, self._to_bool],
            ['use_timestamp',False, self._to_bool],
            ['ARGS', False, self._to_bool],

            ['LEVEL', 'DEBUG', self._parse_log_level],
            # ['FILE', None, None],
            # ['DIR', None, None],
            ['MAX_BYTES', 10*1024*1024, int],
            ['BACKUP_COUNT', 5, int],
            # ['show_call_depth', False, self._to_bool],
            # ↑ до исправления B5: аргумент show_call_depth конструктора/get_instance()
            #   всегда затирался значением False. Теперь он — значение по умолчанию,
            #   а явный ключ в конфиге сильнее (как у file_enabled).
            ['show_call_depth', getattr(self, '_show_call_depth', False), self._to_bool],
            # ['show_call_depth', True, self._to_bool],
        ]:
            # if key == 'LEVEL':
            #     0==0
            
            # result[key] = self._get_config_param(
            #     config= config, 
            #     key= key, 
            #     default= default,
            #     fun= fun,
            # )

            raw = self._get_config_with_inheritance(config, key, default)
            result[key] = fun(raw) if fun is not None else raw
            

     

        # self._enabled = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_enabled', 
        #     #     config.get('enabled', True)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'enabled', 
        #     #     default= True,
        #     # )    
        #     # 
        #     _config['enabled']            
        # )

        # self._console_enabled = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_console_enabled', 
        #     #     config.get('console_enabled', True)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'console_enabled', 
        #     #     default= True,
        #     # )  
        #     _config['console_enabled']
        # )


        # # Берём значение из конфига, если нет — используем эффективное
        # self._file_enabled = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_file_enabled', 
        #     #     # config.get('file_enabled', enable_file_logging)
        #     #     config.get('file_enabled', effective_file)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'file_enabled',
        #     #     default= effective_file,
        #     # )  
        #     _config['file_enabled']
        # )
        # self._use_name_in_filename = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_use_name_in_filename', 
        #     #     # use_name_in_filename
        #     #     effective_name
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'use_name_in_filename',
        #     #     default= effective_name,
        #     # )  
        #     _config['use_name_in_filename']
        # )

        # # Приводим к bool (на случай, если в конфиге оказалась строка)
        # self._file_enabled = bool(self._file_enabled)
        # self._use_name_in_filename = bool(self._use_name_in_filename)

        # self.use_timestamp = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_use_timestamp', 
        #     #     config.get('use_timestamp', False)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'use_timestamp', 
        #     #     default= False,
        #     # )  
        #     _config['use_timestamp']
        # )

        # self.log_args = self._to_bool(
        #     # config.get('LOG_ARGS', False)
        #     # self._get_config(
        #     #     config= config, 
        #     #     key=  'ARGS', 
        #     #     default= False,
        #     # )  
        #     _config['ARGS']
        # )

        # # сохраняем во внутренние атрибуты
        # self._enabled = result['enabled']
        # self._console_enabled = result['console_enabled']
        # self._file_enabled = result['file_enabled']
        # self._use_name_in_filename = result['use_name_in_filename']
        # self.use_timestamp = result['use_timestamp']
        # self.log_args = result['ARGS']
        
        # self.log_level = result['LEVEL']
        # self.base_log_file = result['FILE']
        # self.log_max_bytes = result['MAX_BYTES']
        # self.log_backup_count = result['BACKUP_COUNT']
        # self._show_call_depth = result['show_call_depth']


        return result

    def dump_config(self) -> Dict[str, Any]:
        """
        Краткий снимок состояния логгера для отладки.

        Returns:
            Словарь: ``name``, ``enabled``, ``console_enabled``, ``file_enabled``, ``level``
            (имя), ``use_name_in_filename``, ``use_timestamp``, ``log_FILE`` (итоговый путь).

        Пример:
            >>> AppLogger.get_instance('system').dump_config()['log_FILE']
            'logs\\app.log'
        """
        return {
            'name': self.name,
            'enabled': self._enabled,
            'console_enabled': self._console_enabled,
            'file_enabled': self._file_enabled,
            'level': logging.getLevelName(self.log_level),
            'use_name_in_filename': self._use_name_in_filename,
            'use_timestamp': self.use_timestamp,
            'log_FILE': self._get_log_file(),
        }

    def get_config(self) -> Dict[str, Any]:
        """
        Текущие настройки логгера.

        Returns:
            Словарь: ``level``, ``base_log_FILE``, ``log_MAX_BYTES``, ``log_BACKUP_COUNT``,
            ``log_ARGS``, ``enabled``, ``console_enabled``, ``file_enabled``,
            ``use_name_in_filename``, ``use_timestamp``.

        Пример:
            >>> log.get_config()['level']
            'INFO'
        """
        return {
            'level': logging.getLevelName(self.log_level),
            'base_log_FILE': self.base_log_file,
            'log_MAX_BYTES': self.log_max_bytes,
            'log_BACKUP_COUNT': self.log_backup_count,
            'log_ARGS': self.log_args,
            'enabled': self._enabled,
            'console_enabled': self._console_enabled,
            'file_enabled': self._file_enabled,
            'use_name_in_filename': self._use_name_in_filename,
            'use_timestamp': self.use_timestamp,
        }

    def _get_key_name_config (self, key: str, list_name: Optional[List[Optional[str]]] = None) -> List[str]:
        """
        Варианты имени ключа в порядке приоритета: ``{name}_KEY``, ``LOG_KEY``, ``KEY``.

        Args:
            key: Ключ без префикса.
            list_name: Свои префиксы (``None`` в списке — без префикса); по умолчанию
                ``[self.name, 'LOG', None]``.

        Returns:
            Список имён ключей.

        Пример:
            >>> AppLogger.get_instance('svc')._get_key_name_config('LEVEL')
            ['svc_LEVEL', 'LOG_LEVEL', 'LEVEL']
        """
        rezult = []

        if list_name is None:
            list_name = [
                self.name,  # Сначала ищем специфичный для этого логгера
                'LOG',      # Затем общий для всех логгеров (с префиксом LOG_)
                None,       # Наконец, просто ключ (без префикса)
            ]

        for i in list_name:
            name_key = "_".join(
                [i, key]
            ) if i else key

            rezult.append(name_key)

        return rezult

    def _get_config (
        self, 
        config: Dict[str, Any], 
        key: str, 
        default: Any = None,
        if_lower: bool = False,
    ) -> Any:
        """
        Первое найденное значение среди ``{name}_KEY`` → ``LOG_KEY`` → ``KEY``, без учёта родителей.

        С учётом родителей ищет ``_get_config_with_inheritance``.

        Args:
            config: Плоский словарь настроек.
            key: Ключ без префикса.
            default: Значение, если ничего не найдено.
            if_lower: Искать ключи без учёта регистра.

        Returns:
            Значение или ``default``.

        Пример:
            >>> log._get_config({'LOG_LEVEL': 'INFO'}, 'LEVEL')
            'INFO'
        """
        # if key == 'LEVEL':
        #     0==0

        if if_lower:
            list_key = list(config.keys())
            lowercase_dict = list(map(str.lower, list_key))

        for name_key in self._get_key_name_config(key):
            if if_lower:
                try:
                    index= lowercase_dict.index(name_key.lower())
                except ValueError:
                    index= None

                if index is not None:
                    return config[list_key[index]]
            else:
                if name_key in config :
                    return config[name_key]
                      
        else:
            return default


    def _update_config_from (self, config_dict: Dict[str, Any]) -> None:
            """
            Вычисляет настройки из конфига и записывает их в логгер (без перестроения обработчиков).

            Args:
                config_dict: Плоский словарь настроек.

            Returns:
                None

            Пример:
                Вызывается из ``reload_from_config`` и ``apply_config_from_dict``.
            """
        # Обновляем текущие параметры

            _config = self._init_config_load(config_dict, None, None)

            self._apply_config(_config)   # вместо ручного присваивания

            # # обновление остальных параметров
            # self._enabled = _config['enabled']
            # self._console_enabled = _config['console_enabled']
            # self._file_enabled = _config['file_enabled']
            # self._use_name_in_filename = _config['use_name_in_filename']
            # self.use_timestamp = _config['use_timestamp']
            # self.log_args = _config['ARGS']
            
            # self.log_level = _config['LEVEL']
            # self.base_log_file = _config['FILE']
            # self.log_max_bytes = _config['MAX_BYTES']
            # self.log_backup_count = _config['BACKUP_COUNT']
            # self._show_call_depth = _config['show_call_depth']

            # if 'LEVEL' in _config:
            #     # self.log_level = self._parse_log_level(config_dict['LOG_LEVEL'])
            #     # self.log_level = self._parse_log_level(_config['LEVEL'])
            #     self.logger.setLevel(self.log_level)

            # if 'FILE' in config_dict:
            #     # self.base_log_file = config_dict['LOG_FILE']
            #     self.base_log_file = _config['FILE']


            # if 'BYTES' in config_dict:
            #     # self.log_max_bytes = int(config_dict['LOG_MAX_BYTES'])
            #     self.log_max_bytes = int(_config['MAX_BYTES'])

            # if 'BACKUP_COUNT' in config_dict:
            #     # self.log_backup_count = int(config_dict['LOG_BACKUP_COUNT'])
            #     self.log_backup_count = int(_config['BACKUP_COUNT'])

            # if 'ARGS' in config_dict:
            #     # self.log_args = self._to_bool(config_dict['LOG_ARGS'])
            #     self.log_args = self._to_bool(_config['ARGS'])

            # if 'show_call_depth' in config_dict:
            #     # self._show_call_depth = self._to_bool(config_dict['show_call_depth'])
            #     self._show_call_depth = self._to_bool(_config['show_call_depth'])


    def reload_from_config(self, new_config: Dict[str, Any]) -> None:
        """
        Полностью перечитывает настройки логгера из конфига.

        Обработчики перестраиваются, если изменились флаги или параметры файла, либо файл
        нужен, а обработчика нет (S2). Иначе — только уровень консоли и синхронизация слейвов.
        Обычно вызывается для всех логгеров сразу через ``reload_all_from_config`` /
        ``AppLogger.configure``.

        Args:
            new_config: Плоский словарь настроек (ключи — IMPLEMENTATION.md §3.4).

        Returns:
            None

        Пример:
            >>> log.reload_from_config({'LOG_FILE': 'logs/', 'LOG_LEVEL': 'WARNING',
            ...     'LOG_MAX_BYTES': 10**7, 'LOG_BACKUP_COUNT': 5, 'file_enabled': 'True'})
        """
        # # Если используем общий обработчик, перенаправляем вызов мастеру
        # if self._shared_handler and self._master_logger:
        #     self._master_logger.reload_from_config(new_config)
        #     return
        
        need_rebuild = False
        with self._handler_lock:
            # Сохраняем старые флаги для сравнения
            old_file_enabled = self._file_enabled
            old_console_enabled = self._console_enabled
            old_enabled = self._enabled
            old_base_log_file = self.base_log_file
            old_max_bytes = self.log_max_bytes
            old_backup_count = self.log_backup_count
            old_use_timestamp = self.use_timestamp
            old_use_name = self._use_name_in_filename

            self._update_config_from(new_config)

            # # Применяем новые настройки
            # # self._init_config_load(new_config, self._file_enabled, self._use_name_in_filename)
            # self._init_config_load(new_config, None, None)

            # # Обновляем остальные параметры
            # if 'LOG_LEVEL' in new_config:
            #     # self.log_level = self._parse_log_level(new_config['LOG_LEVEL'])
            #     self.log_level = self._parse_log_level(
            #         self._get_config(
            #             config=new_config, 
            #             key='LEVEL',
            #         )
            #     )
            #     self.logger.setLevel(self.log_level)

            # if 'LOG_FILE' in new_config:
            #     # self.base_log_file = new_config['LOG_FILE']
            #     self.base_log_file = self._get_config(
            #         config= new_config, 
            #         key= 'FILE',
            #     )

            # if 'LOG_MAX_BYTES' in new_config:
            #     # self.log_max_bytes = int(new_config['LOG_MAX_BYTES'])
            #     self.log_max_bytes = int(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'MAX_BYTES',
            #         )
            #     )

            # if 'LOG_BACKUP_COUNT' in new_config:
            #     # self.log_backup_count = int(new_config['LOG_BACKUP_COUNT'])
            #     self.log_backup_count = int(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'BACKUP_COUNT',
            #         )
            #     )

            # if 'LOG_ARGS' in new_config:
            #     # self.log_args = self._to_bool(new_config['LOG_ARGS'])
            #     self.log_args = self._to_bool(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'ARGS',
            #         )
            #     )

            # if 'show_call_depth' in new_config:
            #     # self._show_call_depth = self._to_bool(new_config['show_call_depth'])
            #     self._show_call_depth = self._to_bool(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'show_call_depth',
            #         )
            #     )

            # if 'use_timestamp' in new_config:
            #     # self.use_timestamp = self._to_bool(new_config['use_timestamp'])
            #     self.use_timestamp = self._to_bool(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'use_timestamp',
            #         )
            #     )


            need_rebuild = ( # Проверяем, изменились ли параметры, требующие перестройки обработчиков
                self._file_enabled != old_file_enabled or
                self._console_enabled != old_console_enabled or
                self._enabled != old_enabled or
                self.base_log_file != old_base_log_file or
                self.log_max_bytes != old_max_bytes or
                self.log_backup_count != old_backup_count or
                self.use_timestamp != old_use_timestamp or
                self._use_name_in_filename != old_use_name or
                # Флаги могли не измениться, а обработчик пропасть (мастер выключил
                # общий файл, S2) — тогда тоже перестраиваем.
                self._file_output_missing()
            )

        # применение изменений БЕЗ блокировки
        # Если изменились флаги – перестраиваем обработчики
        if need_rebuild:
            self._update_handlers()

        else:
            # Иначе просто обновляем уровни у существующих обработчиков
            # for handler in self.logger.handlers:
            # handler.setLevel(self.log_level)
            # ↑ до S3: перезагрузка слейва меняла уровень общего файла мастера и окна логов
            #   GUI (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера). Теперь — только своя консоль.
            if self.console_handler:
                self.console_handler.setLevel(self.log_level)

            # if self._shared_slaves:
            self._update_shared_slaves()

            # if self._shared_slaves:
            #     self._update_shared_slaves()
    
    
    # ----------------------------------------------------------------------
    # Методы для включения/отключения логирования
    # ----------------------------------------------------------------------



    @staticmethod
    def _parse_log_level(level_str: Union[str, int]) -> int:
        """
        Приводит уровень логирования к числу из модуля ``logging``.

        Принимает:
            * строку-имя уровня без учёта регистра: ``'DEBUG'``, ``'info'``, ...;
            * число (``logging.INFO``, ``20``, свои уровни ``>= 0``) — возвращается как есть.

        Числа принимаются с 2026-10-14 (исправление B2): групповые
        ``set_group_console_level``/``set_group_file_level`` переводили строку в число и
        передавали его в ``set_*_level``, который снова вызывал этот метод → ``AttributeError``.

        Args:
            level_str: Имя уровня или число.

        Returns:
            Числовой уровень.

        Raises:
            ValueError: Неизвестное имя уровня или отрицательное число.
            TypeError: Не строка и не число (например, ``None``).

        Пример:
            >>> BaseAppLogger._parse_log_level('warning')
            30
            >>> BaseAppLogger._parse_log_level(logging.ERROR)
            40
        """
        # bool — подкласс int, но True/False как уровень — почти наверняка ошибка
        if isinstance(level_str, int) and not isinstance(level_str, bool):
            if level_str < 0:
                raise ValueError(f"Уровень логирования не может быть отрицательным: {level_str}")
            return level_str

        if not isinstance(level_str, str):
            raise TypeError(
                f"Уровень логирования должен быть строкой или числом, получено: {level_str!r}"
            )

        upper_str = level_str.upper()

        if upper_str not in BaseAppLogger.level_map:
            raise ValueError(f"Неизвестный уровень логирования: {level_str}. Допустимые: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        
        return BaseAppLogger.level_map[upper_str]
    
    @staticmethod
    def parse_log_level(level_str: Union[str, int]) -> int:
        """
        Публичное имя ``_parse_log_level``: уровень по имени или числу → число.

        Args:
            level_str: ``'INFO'``, ``'debug'``, ``logging.ERROR``…

        Returns:
            Числовой уровень.

        Raises:
            ValueError: Неизвестное имя или отрицательное число.
            TypeError: Не строка и не число.

        Пример:
            >>> AppLogger.parse_log_level('warning')
            30
        """
        return BaseAppLogger._parse_log_level(level_str)    
    
    # --------------------------------------------------------------------------
    # Вспомогательные методы для формирования указателя на место вызова
    # --------------------------------------------------------------------------
