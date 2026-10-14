# app/utils/logger/_sharing.py

"""
Часть ``BaseAppLogger``: Общий файловый обработчик (мастер/слейв).

Содержит примесь ``_SharingMixin``: один обработчик на файл, подключение к мастеру, синхронизация слейвов.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_SharingMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _SharingMixin)
    True
"""

import os
from typing import List, Optional, Dict, Any, Tuple


import weakref

from ._common import LOGGER_CODE_FILES

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _SharingMixin:
    """
    Примесь ``BaseAppLogger``: один обработчик на файл, подключение к мастеру, синхронизация слейвов.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._SharingMixin'>, ...)
    """

    def _file_share_target(self) -> Optional['BaseAppLogger']:
        """
        К чьему файловому обработчику подключиться вместо открытия своего.

        Порядок:
            1. родитель по ссылке ``enable_file_logging='имя'`` (``_ref_parent_for_sharing``);
            2. любой логгер, который сам (не через мастера) держит открытый обработчик
               на тот же файл (``_same_file_owner``).

        Цель — один обработчик на файл: несколько ``RotatingFileHandler`` на одном
        файле конфликтуют при ротации (на Windows — ``PermissionError``). Уровни при
        этом не смешиваются: общий обработчик порога не имеет, каждый логгер
        фильтрует своим уровнем (S3).

        Returns:
            Логгер, к которому можно подключиться, или ``None``.

        Пример:
            >>> system = AppLogger.get_instance('system')      # открыл logs/app.log
            >>> user = AppLogger.get_instance('user')          # тот же файл
            >>> user._file_share_target() is system
            True
        """
        target = self._ref_parent_for_sharing()
        if target is None:
            target = self._same_file_owner()
        return target

    def _same_file_owner(self) -> Optional['BaseAppLogger']:
        """
        Логгер из реестра, который сам владеет открытым обработчиком на тот же файл.

        «Сам владеет» — не слейв (``_shared_handler`` ложно), включён, файл включён,
        обработчик есть. Сравниваются абсолютные пути без учёта регистра (Windows).
        Путь владельца берётся из ``file_handler.baseFilename`` — без обращения к диску.

        Returns:
            Найденный логгер или ``None`` (в том числе если автоподключение запрещено
            явным ``unshare_file_handler()``).

        Пример:
            >>> AppLogger.get_instance('a', enable_file_logging=True)._same_file_owner()  # первый
            >>> AppLogger.get_instance('b', enable_file_logging=True)._same_file_owner().name
            'a'
        """
        if not getattr(self, '_allow_auto_share', True):
            return None

        try:
            my_file = os.path.normcase(os.path.abspath(self._get_log_file()))
        except ValueError:
            return None

        cls = type(self)
        with cls._instances_lock:
            candidates = list(cls._instances.values())

        for other in candidates:
            if other is self or other._shared_handler:
                continue
            if not (other._enabled and other._file_enabled and other.file_handler is not None):
                continue
            other_file = os.path.normcase(os.path.abspath(other.file_handler.baseFilename))
            if other_file == my_file:
                return other

        return None

    def _ref_parent_for_sharing(self) -> Optional['BaseAppLogger']:
        """
        Родитель по ссылке ``enable_file_logging='имя'``, к файлу которого можно подключиться.

        Родитель подходит, если ВСЁ верно:
            * ссылка задана и логгер с таким именем есть в реестре (и это не сам логгер);
            * у родителя сейчас реально открыт файл: включён, файл включён, обработчик есть;
            * родитель пишет в тот же файл, в который писал бы этот логгер
              (иначе, например при ``use_name_in_filename=True``, подключаться нельзя).

        Проверяется ФАКТИЧЕСКОЕ состояние родителя, а не аргумент его конструктора —
        в этом и было исправление S1 (IMPLEMENTATION.md §5.2): ``system`` создаётся без
        ``enable_file_logging=True``, файл ему включает конфиг, и раньше к нему не
        подключался никто.

        Returns:
            Логгер-родитель или ``None``, если подключаться не к чему.

        Пример:
            >>> system = AppLogger.get_instance('system')            # файл включён конфигом
            >>> svc = AppLogger.get_instance('svc', enable_file_logging='system')
            >>> svc._ref_parent_for_sharing() is system
            True
        """
        if not getattr(self, '_allow_auto_share', True):
            # Логгер явно отвязали (unshare_file_handler) — пишет в свой файл
            return None

        ref = getattr(self, '_enable_file_logging_ref', None)
        if not ref:
            return None

        parent = self._get_parent(ref)
        if parent is None or parent is self:
            return None

        if not (parent._enabled and parent._file_enabled and parent.file_handler is not None):
            return None

        try:
            same_file = (
                os.path.normcase(os.path.abspath(parent._get_log_file()))
                == os.path.normcase(os.path.abspath(self._get_log_file()))
            )
        except ValueError:
            # У кого-то не задан base_log_file — сравнивать нечего
            return None

        return parent if same_file else None

    def has_shared_handler(self) -> bool:
        """
        Пишет ли логгер через чужой (общий) файловый обработчик — то есть является слейвом.

        Returns:
            ``True`` для слейва.

        Пример:
            >>> AppLogger.get_instance('svc', enable_file_logging='system').has_shared_handler()
            True
        """
        return self._shared_handler
    
    def _sync_all_from_master(self) -> None:
        """
        Копирует у мастера общие параметры файла при подключении к нему.

        Копируются: форматтер, путь, ротация, ``use_timestamp``, ``log_args``,
        ``use_name_in_filename``, ``file_enabled``, ``show_call_depth``; флаг полной
        синхронизации — если слейв не задал свой (S4); при полной синхронизации — ещё
        ``enabled`` и консоль. Уровень НЕ копируется (S3).

        Returns:
            None

        Пример:
            Вызывается из ``share_file_handler_with``.
        """
        if not self._master_logger:
            return
        
        # self.log_level = self._master_logger.log_level # устанавливаем уровень
        # self.logger.setLevel(self.log_level) # устанавливаем уровень
        # ↑ до S3: при подключении к общему файлу слейв перенимал уровень мастера —
        #   user получал DEBUG вместо user_LEVEL=INFO, ConfigApplier_LEVEL затирался (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера).

        self.formatter = self._master_logger.formatter # устанавливаем формат
        self.base_log_file = self._master_logger.base_log_file # устанавливаем имя файла
        self.log_max_bytes = self._master_logger.log_max_bytes # устанавливаем максимальный размер файла
        self.log_backup_count = self._master_logger.log_backup_count # устанавливаем количество бэкапов
        self.use_timestamp = self._master_logger.use_timestamp # устанавливаем флаг использования времени
        self.log_args = self._master_logger.log_args # устанавливаем флаг использования аргументов
        self._use_name_in_filename = self._master_logger._use_name_in_filename  # устанавливаем флаг использования имени
        self._file_enabled = self._master_logger._file_enabled  # устанавливаем флаг использования файлового обработчика

        # self._sync_full_state = self._master_logger._sync_full_state # устанавливаем флаг использования полного состояния
        # ↑ до S4: флаг мастера копировался всегда, явный отказ слейва терялся.
        if getattr(self, '_sync_full_state_explicit', None) is None:
            self._sync_full_state = self._master_logger._sync_full_state

        # Копируем флаги консоли и включения только если явно запрошено
        if self._sync_full_state: # Если нужно, чтобы слейв имел независимую консоль
            # Если нужно, чтобы слейв имел независимую консоль - убираем эти две строки
            self._console_enabled = self._master_logger._console_enabled  # устанавливаем флаг использования консольного обработчика
            self._enabled = self._master_logger._enabled    # устанавливаем флаг включения

        self._show_call_depth = self._master_logger._show_call_depth  # устанавливаем флаг использования глубины стека вызовов

        # Обновляем обработчик, если он уже привязан
        if self.console_handler: # Если есть консольный обработчик
            self.console_handler.setLevel(self.log_level) # устанавливаем уровень

        self._sync_log_level_and_formatters()  # Синхронизируем уровень и формат



    def share_file_handler_with(
        self, 
        other: 'BaseAppLogger',
        sync_full_state: Optional[bool] = None,
    ) -> None:
        """
        Подключает этот логгер к файловому обработчику ``other`` (делает слейвом).

        Подключение всегда к корневому владельцу обработчика (по цепочке мастеров).
        Ничего не делает, если это тот же логгер, если они уже связаны или у ``other`` нет
        открытого файла (тогда — предупреждение). Свой прежний файловый обработчик
        закрывается (общий — нет). Копируются параметры файла мастера
        (``_sync_all_from_master``), уровень — свой (S3).

        Не вызывайте ``turn_off_file_logging()`` у мастера, если слейвам нужен файл: он
        отвяжет всех слейвов (каждый откроет свой обработчик).

        Args:
            other: Логгер, к чьему файлу подключиться.
            sync_full_state: Явно задать флаг полной синхронизации этому логгеру;
                ``None`` — как у мастера.

        Returns:
            None

        Пример:
            >>> AppLogger.get_instance('report').share_file_handler_with(AppLogger.get_instance('system'))
        """

        # Подключаемся к корневому владельцу обработчика, а не к промежуточному
        # слейву: иначе при пересоздании обработчика у владельца новый обработчик
        # не дойдёт до «внуков» (_update_shared_slaves обновляет только прямых слейвов).
        # Пример цепочки до исправления: gui → user → system.
        while (
            other._shared_handler
            and other._master_logger is not None
            and other._master_logger is not self
        ):
            other = other._master_logger

        if self is other:
            return

        # Если уже расшарены друг с другом – выходим
        if self._master_logger is other or other._master_logger is self:
            return

        with BaseAppLogger._share_lock:
        
            if self._shared_handler:
                # self.unshare_file_handler(if_update_handlers=False)
                # Ручная отвязка без дополнительных блокировок
                self._unshare_file_handler_master_logger()
                with self._handler_lock:
                    # При отвязке от старого мастера изменение self._shared_handler, self._master_logger, self.file_handler 
                    # происходит без захвата self._handler_lock. Хотя эти поля защищены _share_lock (который уже захвачен), 
                    # в других методах они могут читаться без _share_lock. Во избежание неконсистентности рекомендуется 
                    # обернуть эти операции в self._handler_lock
                    
                    self._remove_file_handler(if_close_file_handler=False)
                    self._shared_handler = False
                    self._master_logger = None
                    self.file_handler = None

            # Упорядочиваем локи по id объектов
            first, second = sorted([self, other], key=id)
            with first._handler_lock, second._handler_lock:
                # Проверка, что у other есть активный файловый обработчик
                if other.file_handler is None or not other._file_enabled or not other._enabled:
                    self.logger.warning(
                        f"Логгер '{other.name}' не имеет активного файлового обработчика. "
                        "Сначала включите файловое логирование у исходного логгера."
                    )
                    return
                
                self._remove_file_handler( # Удаляем текущий файловый обработчик, если есть
                    if_close_file_handler=not self._shared_handler
                )
                self._set_file_handler( # Берём обработчик другого логгера
                    file_handler=other.file_handler
                )

                # if sync_full_state is None:
                #     sync_full_state = other._sync_full_state
                    
                # self._sync_full_state = sync_full_state # сохраняем флаг синхронизации

                # self.base_log_file = other.base_log_file    # синхронизация пути

                # self.log_level = other.log_level            # синхронизация уровня
                # self.logger.setLevel(self.log_level)        # применение уровня # важно: уровень логгера тоже должен совпадать

                # if self.file_handler:
                #     self.file_handler.setLevel(self.log_level)  

                # self._sync_formatters( # Синхронизация форматирования
                #     formatter=other.formatter
                # )

                # self.log_args = other.log_args

                # # Используем обработчик другого логгера
                # self.file_handler = other.file_handler
                # self.logger.addHandler(self.file_handler) # Добавляем обработчик


                # Синхронизируем параметры ротации, чтобы при возможном пересоздании обработчика
                # использовались актуальные значения
                # self.log_max_bytes = other.log_max_bytes 
                # self.log_backup_count = other.log_backup_count

                # self.use_timestamp = other.use_timestamp

                # # Синхронизируем флаги и параметры
                # self._file_enabled = other._file_enabled  # флаг, что файловое логирование включено
                # self._use_name_in_filename = other.use_name_in_filename  # копируем настройку
                # self._file_enabled = other.effective_enable_file_logging() # флаг, что файловое логирование включено
                # self._use_name_in_filename = other.effective_use_name_in_filename() # копируем настройку

                # self._file_enabled = bool(self._file_enabled)
                # self._use_name_in_filename = bool(self._use_name_in_filename)

                # Устанавливаем флаги общего обработчика
                self._shared_handler = True     # признак общего обработчика
                self._master_logger = other     # запоминаем, от кого взяли обработчик (мастер)

                # # Применяем уровень к логгеру
                # self.logger.setLevel(self.log_level)

                self._sync_all_from_master() # Синхронизируем уровень и формат для файлового обработчика # копирует все параметры, включая _sync_full_state от мастера
                
                if sync_full_state is not None:
                    self._sync_full_state = sync_full_state # сохраняем флаг синхронизации (добавляем из шапки ф-ции)

                # # После успешного шаринга зарегистрировать текущего как зависимого у мастера
                # if other != self and other not in other._shared_slaves:
                #     other._shared_slaves.append(self)

                # Регистрируем себя как слейва у мастера
                # if self not in other._shared_slaves:
                if not any(ref() is self for ref in other._shared_slaves):
                    # other._shared_slaves.append(self)
                    other._shared_slaves.append(weakref.ref(self))

                # self._sync_log_level_and_formatters() # Синхронизируем уровень и формат для файлового обработчика

                self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)

                # Перестраиваем обработчики, чтобы новый уровень применился к консоли и файлу
                self._update_handlers()
                
                self._reopen_file_handler_if_needed() # Проверяем, нужно ли переоткрыть файловый обработчик



    def get_shared_group(self) -> List['BaseAppLogger']:
        """
        Все логгеры, пишущие через тот же файловый обработчик (мастер и живые слейвы).

        Returns:
            Список логгеров; для логгера без общего файла — ``[self]``.

        Пример:
            >>> [l.name for l in AppLogger.get_instance('system').get_shared_group()][:3]
            ['system', 'user', 'main.py']
        """
        with BaseAppLogger._share_lock:
            # if self._shared_handler and self._master_logger:
            #     # слейв: возвращаем мастера и всех его слейвов
            #     result = {self._master_logger}.union(self._master_logger._shared_slaves)
            #     return list(result)
            
            # elif self._shared_slaves:
            #     # мастер: возвращаем себя и всех слейвов
            #     return [self] + self._shared_slaves
            
            # return [self]
            if self._shared_handler and self._master_logger:
                # Собираем мастера и всех живых слейвов
                result = {self._master_logger}
                for ref in self._master_logger._shared_slaves:
                    slave = ref()
                    if slave is not None:
                        result.add(slave)

                return list(result)
            
            elif self._shared_slaves:
                result = {self}
                for ref in self._shared_slaves:
                    slave = ref()
                    if slave is not None:
                        result.add(slave)

                return list(result)
            
            return [self]
    
    # def _sync_console_handler (self, slave) -> None:
    #     # Если у зависимого логгера включён консольный вывод, убедимся, что его уровень совпадает
    #     with self._handler_lock:                # блокировка мастера
    #         level = self.log_level

    #     with slave._handler_lock:
    #         if slave._console_enabled and slave.console_handler:
    #             # slave.console_handler.setLevel(self.log_level)
    #             slave.console_handler.setLevel(level)

    # def _sync_formatters_slave (self, slave, formatter) :
    #     with slave._handler_lock:
    #         if slave.formatter != formatter:
    #             slave.formatter = formatter

    #             # Для консольного обработчика тоже нужно обновить формат (если он есть)
    #             if slave.console_handler:
    #                 slave.console_handler.setFormatter(formatter)

    #             if slave.file_handler:
    #                 slave.file_handler.setFormatter(formatter)

    # def _sync_log_formatters(self, slave) -> None:
    #     # Синхронизируем формат сообщений (если изменился у мастера)
    #     with self._handler_lock:                # блокировка мастера
    #         formatter = self.formatter

    #     self._sync_formatters_slave(
    #         slave = slave,
    #         formatter = formatter
    #     )  
                
    def _update_shared_slave(self, slave: Optional['BaseAppLogger'], master_state: Dict[str, Any]) -> None:
        """
        Синхронизирует одного слейва со снимком состояния мастера.

        Если у слейва включён файл — подключает текущий обработчик мастера (старый общий
        снимается без закрытия). Копирует параметры файла, форматтер, ``log_args``,
        ``show_call_depth``. Уровень и флаги слейва НЕ меняет (S3; флаги — ``_apply_full_sync``).

        Args:
            slave: Слейв (``None`` — ничего не делать).
            master_state: Снимок ``_get_master_state()`` мастера.

        Returns:
            None

        Пример:
            >>> master._update_shared_slave(slave, master._get_master_state())
        """
        if slave is None:
            return
        
        with slave._handler_lock:
            master_handler = master_state['file_handler']
            if master_handler is None:
                return

            # --- файловый обработчик обновляем ТОЛЬКО если он есть у мастера и у слейва разрешён файловый вывод ---
            if master_handler is not None and slave._file_enabled:
                # 1. Обновляем файловый обработчик
                if slave.file_handler != master_handler:
                    if slave.file_handler and slave.file_handler in slave.logger.handlers:
                        slave.logger.removeHandler(slave.file_handler)

                    slave.file_handler = master_handler
                    slave._reopen_file_handler_if_needed()

                # 2. Добавляем обработчик, если его нет    
                if master_handler not in slave.logger.handlers:
                    slave.logger.addHandler(master_handler)

            
            # if slave.file_handler != master_handler:
            #     if slave.file_handler and slave.file_handler in slave.logger.handlers:
            #         slave.logger.removeHandler(slave.file_handler)
            #     slave.file_handler = master_handler

            #     slave._reopen_file_handler_if_needed()

            # if master_handler not in slave.logger.handlers:
            #     slave.logger.addHandler(master_handler)


            # --- основные параметры синхронизируются ВСЕГДА ---
            # 3. Синхронизируем параметры (уровень, формат, лимиты и т.д.)
            # slave.log_level = master_state['log_LEVEL']
            # slave.logger.setLevel(slave.log_level)
            # 
            # if slave.file_handler:
            # slave.file_handler.setLevel(slave.log_level)
            # ↑ до S3: слейв получал уровень мастера, персональные ключи ({name}_LEVEL)
            #   затирались, а общий файл получал уровень последнего слейва (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера).
            # Уровень слейва — его собственный (из конфига или наследованием по ссылке).

            slave.log_max_bytes = master_state['log_MAX_BYTES']
            slave.log_backup_count = master_state['log_BACKUP_COUNT']
            slave.base_log_file = master_state['base_log_FILE']
            slave._use_name_in_filename = master_state['use_name_in_filename']
            slave.use_timestamp = master_state['use_timestamp']
            # slave._sync_full_state = master_state['sync_full_state']
            # ↑ до S4: затирало явный отказ слейва от полной синхронизации.
            slave._show_call_depth = master_state['show_call_depth']
            slave.log_args = master_state['log_ARGS']

            # 4. Форматтер
            if slave.formatter != master_state['formatter']:
                slave.formatter = master_state['formatter']

                if slave.console_handler:
                    slave.console_handler.setFormatter(master_state['formatter'])

                if slave.file_handler:
                    slave.file_handler.setFormatter(master_state['formatter'])

            # 5. Консольный уровень (если консольный вывод включён)
            if slave._console_enabled and slave.console_handler:
                slave.console_handler.setLevel(slave.log_level)

            # --- полная синхронизация флагов (опционально) ---
            # 5.1. Синхронизация флагов консоли и включения, если требуется полная синхронизация
            # if master_state.get('sync_full_state', False):
            #     slave._console_enabled = master_state['console_enabled']
            #     slave._enabled = master_state['enabled']
            # ↑ до S4: флаги менялись без перестроения обработчиков (консоль не
            #   появлялась/не пропадала). Теперь — _apply_full_sync + _update_handlers.

            # 6. Сохраняем список обработчиков для GUI
            slave._save_handlers()


    def _get_shared_slaves(self) -> Tuple[List, List]: 
        """
        Живые слейвы и «мёртвые» слабые ссылки (логгеры, удалённые сборщиком мусора).

        Returns:
            Кортеж ``(живые_слейвы, мёртвые_ссылки)``.

        Пример:
            >>> alive, dead = master._get_shared_slaves()
        """
        # Разыменовываем слабые ссылки, удаляем мёртвые
        active_slaves = []
        dead_refs = []

        for ref in self._shared_slaves[:]:
            slave = ref()
            if slave is not None:
                active_slaves.append(slave)
            else:
                dead_refs.append(ref)
        
        return active_slaves, dead_refs
    

    def _get_master_state(self) -> Dict[str, Any]:
        """
        Снимок состояния этого логгера как мастера (под его блокировкой).

        Returns:
            Словарь: ``file_handler``, ``log_LEVEL``, ``formatter``, ``base_log_FILE``,
            ``log_MAX_BYTES``, ``log_BACKUP_COUNT``, ``use_timestamp``, ``use_name_in_filename``,
            ``sync_full_state``, ``show_call_depth``, ``log_ARGS``, ``console_enabled``, ``enabled``.

        Пример:
            >>> master._get_master_state()['file_handler'] is master.file_handler
            True
        """
        with self._handler_lock:
            return  {
                'file_handler': self.file_handler,
                'log_LEVEL': self.log_level,
                'formatter': self.formatter,
                'base_log_FILE': self.base_log_file,
                'log_MAX_BYTES': self.log_max_bytes,
                'log_BACKUP_COUNT': self.log_backup_count,
                'use_timestamp': self.use_timestamp,
                'use_name_in_filename': self._use_name_in_filename,
                'sync_full_state': self._sync_full_state,
                'show_call_depth': self._show_call_depth,
                'log_ARGS': self.log_args,

                'console_enabled': self._console_enabled,
                'enabled': self._enabled,
                # 'sync_full_state': self._sync_full_state,
            }  
    def _apply_full_sync(self, slave: 'BaseAppLogger', master_state: Dict[str, Any]) -> bool:
        """
        Копирует слейву флаги ``enabled`` и ``console_enabled`` мастера (S4).

        Работает, только если мастер включил полную синхронизацию
        (``sync_full_state=True``) и слейв от неё не отказался
        (его ``_sync_full_state`` тоже ``True``; по умолчанию слейв наследует флаг
        мастера, явный ``get_instance(..., sync_full_state=False)`` — отказ).

        Args:
            slave: Слейв этого мастера.
            master_state: Снимок состояния мастера (``_get_master_state()``).

        Returns:
            ``True``, если флаги слейва изменились и ему нужно перестроить обработчики.

        Пример:
            >>> master = AppLogger.get_instance('m', enable_file_logging=True, sync_full_state=True)
            >>> slave = AppLogger.get_instance('s', enable_file_logging='m')
            >>> master.disable()        # внутри _apply_full_sync → slave тоже выключен
            >>> slave.is_enabled()
            False
        """
        if not (master_state.get('sync_full_state') and slave._sync_full_state):
            return False

        with slave._handler_lock:
            changed = (
                slave._enabled != master_state['enabled']
                or slave._console_enabled != master_state['console_enabled']
            )
            slave._enabled = master_state['enabled']
            slave._console_enabled = master_state['console_enabled']
        return changed

    def _update_shared_slaves(self) -> None:
        """
        Синхронизирует всех слейвов с этим мастером после его изменения.

        * у мастера есть файл — каждому включённому слейву подключается текущий
          обработчик и копируются параметры файла (``_update_shared_slave``);
        * у мастера файла нет — у слейвов обработчик отцепляется (связь остаётся, S2);
        * при полной синхронизации слейвам копируются ``enabled``/консоль и они
          перестраиваются (S4).

        Мёртвые слабые ссылки удаляются.

        Returns:
            None

        Пример:
            Вызывается в конце ``_update_handlers`` и при смене уровня/форматтера.
        """

        with BaseAppLogger._share_lock:

            if not self._shared_slaves:
                return
            
            # Разыменовываем слабые ссылки, удаляем мёртвые
            active_slaves, dead_refs = self._get_shared_slaves() 

            for ref in dead_refs:
                # Ссылка мертва – удаляем её из списка
                self._shared_slaves.remove(ref)

            if not active_slaves:
                return
            
            # slaves_copy = list(active_slaves)   # делаем копию

        master_state = self._get_master_state()
        
        if master_state['file_handler'] is None:
            # # У мастера нет файлового обработчика – ничего не синхронизируем
            # return
            # ↑ до исправления S2: слейвы оставались с закрытым обработчиком мастера,
            #   а FileHandler при записи переоткрывает поток → слейвы продолжали писать
            #   в файл, который мастер выключил.
            # Теперь отцепляем старый общий обработчик (связь мастер/слейв сохраняется:
            # когда мастер снова откроет файл, слейвы получат новый обработчик).
            # Слейв, которому файл нужен сам, при своём перестроении откроет свой.
            for slave in active_slaves:
                with slave._handler_lock:
                    if slave._shared_handler and slave.file_handler is not None:
                        slave._remove_file_handler(if_close_file_handler=False)
                        slave._save_handlers()
                # S4: мастер выключен целиком — с полной синхронизацией выключаем и слейва
                if self._apply_full_sync(slave, master_state):
                    slave._update_handlers()
            return

        for slave in active_slaves:  # копия на случай изменения списка
            # Если зависимый логгер уже неактивен или отключил файловое логирование – пропускаем
            # if not slave._enabled or not slave._file_enabled:
            # if not slave._enabled or not slave.effective_enable_file_logging(_visited=None):
            #     continue
            # if not slave._enabled:
            #     continue
            # ↑ до исправления S4: выключенный слейв пропускался всегда — при полной
            #   синхронизации включение мастера до него не доходило.
            full_sync_changed = self._apply_full_sync(slave, master_state)
            if not slave._enabled:
                continue

            self._update_shared_slave(slave, master_state )# Убедимся, что он всё ещё использует наш обработчик # внутри будет захвачен slave._handler_lock, но _share_lock уже свободен

            # self._sync_log_formatters(slave) # Синхронизируем формат сообщений (если изменился у мастера)

            if full_sync_changed:
                # Флаги включения/консоли поменялись — у слейва нужны другие обработчики
                slave._update_handlers()
        
            # self._sync_console_handler(slave) # Если у зависимого логгера включён консольный вывод, убедимся, что его уровень совпадает

   

    def _unshare_file_handler_master_logger (self) -> None:
        """
        Удаляет этот логгер из списка слейвов его мастера.

        Ожидается, что вызывающий уже держит ``_share_lock``. Если мастера нет — WARNING.

        Returns:
            None

        Пример:
            Вызывается из ``unshare_file_handler`` и ``share_file_handler_with``.
        """
        # Предполагается, что вызывающий код уже удерживает BaseAppLogger._share_lock
   
        master = self._master_logger
        if master is not None:
            # Удаляем текущий логгер из списка зависимых у мастера
            try:
                # master._shared_slaves.remove(self)
                # Ищем слабую ссылку на self в списке мастера
                for ref in master._shared_slaves[:]:
                    if ref() is self:
                        master._shared_slaves.remove(ref)
                        break

            except ValueError:
                # Если по какой-то причине нас там нет – игнорируем
                self.logger.warning(
                    f"Логгер '{self.name}' не найден в списке зависимых мастера '{master.name}'"
                )
            # Также можно уведомить мастера, что он больше не должен обновлять нас
        else:
            self.logger.warning(
                f"Логгер '{self.name}' имеет флаг _shared_handler=True, но _master_logger отсутствует"
            )

    def unshare_file_handler(
        self,
        if_update_handlers: bool = True,
        keep_ref_sharing: bool = False,
    ) -> None:
        """
        Отвязывает логгер от общего файлового обработчика; дальше он пишет в свой.

        Общий обработчик не закрывается — им пользуются мастер и другие слейвы.

        Args:
            if_update_handlers: Сразу перестроить обработчики (создать свой файловый,
                если файл включён). ``False`` — вызывающий код перестроит сам.
            keep_ref_sharing: ``False`` (по умолчанию) — явная отвязка: логгер больше
                не подключается к родителю по ссылке ``enable_file_logging='имя'``
                автоматически. ``True`` — служебная отвязка (у мастера пропал файл,
                S2): при появлении файла у родителя логгер сможет подключиться снова.

        Returns:
            None

        Пример:
            >>> svc = AppLogger.get_instance('svc', enable_file_logging='system')
            >>> svc.unshare_file_handler()
            >>> svc.has_shared_handler(), svc.file_handler is not None
            (False, True)
        """
        if not keep_ref_sharing:
            self._allow_auto_share = False

        with BaseAppLogger._share_lock:
            if not self._shared_handler:
                return
            
            with self._handler_lock:
                self._unshare_file_handler_master_logger()

                self._remove_file_handler( # Удаляем общий обработчик  (не закрываем, т.к. он может использоваться другим)
                    if_close_file_handler=False # (не закрываем, т.к. он может использоваться другим)
                ) 
                self.file_handler = None
                self._shared_handler = False
                self._master_logger = None

        if if_update_handlers:
            # Пересоздаём собственный обработчик согласно текущим настройкам
            self._update_handlers()

    def get_master_logger(self) -> Optional['BaseAppLogger']:
        """
        Мастер, через чей обработчик пишет этот логгер.

        Returns:
            Логгер-мастер или ``None``, если файл свой или выключен.

        Пример:
            >>> AppLogger.get_instance('svc', enable_file_logging='system').get_master_logger().name
            'system'
        """
        return self._master_logger
