#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Базовый модуль логирования.

Содержит класс BaseAppLogger, который:
- Управляет созданием и хранением экземпляров логгеров (паттерн Multiton).
- Каждый экземпляр настраивается индивидуально (имя, конфигурация, параметры файла).
- Предоставляет методы для логирования и декоратор log_execution_time.
- Поддерживает запись в отдельные файлы для разных экземпляров и отключение файлового логирования.
- Не использует глобальные переменные (все данные хранятся в атрибутах класса).

Пример использования:
    # Базовый логгер (пишет в файл по умолчанию)
    logger = BaseAppLogger.get_instance()
    logger.info("Сообщение")

    # Логгер, который пишет в отдельный файл с именем экземпляра
    logger_db = BaseAppLogger.get_instance(name='db', use_name_in_filename=True)
    logger_db.info("Сообщение для db")

    # Логгер только в консоль (без файла)
    logger_console = BaseAppLogger.get_instance(name='console', enable_file_logging=False)
    logger_console.info("Только в консоль")
"""

import os
import logging
import time
import inspect
from functools import wraps
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, Callable, Union


class BaseAppLogger:
    """
    Менеджер логгеров с поддержкой нескольких именованных экземпляров.

    Атрибуты класса:
        _instances (dict): Словарь созданных экземпляров {имя: экземпляр}.

    Методы класса:
        get_instance(name='default', force_new=False, config=None,
                     enable_file_logging=True, use_name_in_filename=False) -> BaseAppLogger:
            Возвращает экземпляр логгера с указанным именем.
    """

    # _levels_up = 3
    _levels_up = 0


    skip_patterns_modeles = ( # список пропусков в стеке вызовов модулей и функций для отображения логирования
        # 'filename' - часть пути до модуля, который пропускаем 
        # 'function': - ф-ции, которые пропускаем (если не указываем function', то пропуск всех ф-й из 'filename')
        {
            'filename':('app','utils','logger','base_logger.py'),
            'function':('_formatted', 'info', 'debug', 'warning', 'error', 'critical'), 
        },
    )

    # Словарь экземпляров (ключ - имя логгера)
    _instances: Dict[str, 'BaseAppLogger'] = {}

    _global_handlers = []  # список обработчиков, добавляемых ко всем логгерам

    # Простой формат лога: время, уровень, сообщение (всё остальное формируем вручную)
    LOG_FORMAT = '%(asctime)s\t%(levelname)s\t%(message)s'

    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    @classmethod
    def add_global_handler(cls, handler):
        """
        Добавляет обработчик ко всем существующим и будущим экземплярам логгеров.

        Это может быть полезно, если вам нужно добавить общий обработчик для всех логгеров в программе.
        Пример использования:
            def my_handler(record):
                # обработка записи лога
                pass
            BaseAppLogger.add_global_handler(logging.Handler(my_handler))

        """
        cls._global_handlers.append(handler)
        # Добавляем ко всем уже созданным экземплярам
        for instance in cls._instances.values():
            instance.logger.addHandler(handler)
            # Обновляем список обработчиков экземпляра (опционально)
            instance.handlers = instance.logger.handlers[:]

    @classmethod
    def remove_global_handler(cls, handler):
        """
        Удаляет обработчик из глобального списка и из каждого существующего экземпляра логгера.

        :param handler: Обработчик, который нужно удалить.
        """

        # Если обработчик есть в глобальном списке, удаляем его
        if handler in cls._global_handlers:
            cls._global_handlers.remove(handler)

        # Удаляем обработчик из каждого существующего экземпляра
        for instance in cls._instances.values():
            instance.logger.removeHandler(handler)
            # Обновляем список обработчиков экземпляра (опционально)
            instance.handlers = instance.logger.handlers[:]
            
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Возвращает конфигурацию по умолчанию, которая будет использоваться, если не указать config при вызове get_instance().

        Метод должен быть переопределён в наследнике, потому что конфигурация по умолчанию зависит от конкретного приложения.

        Если не переопределён, то будет выброшено исключение RuntimeError.

        В наследнике необходимо переопределить метод, чтобы он возвращал словарь с конфигурацией по умолчанию для конкретного приложения.

        Например, если в приложении по умолчанию логгер должен писать в файл с именем "app.log", то
        метод get_default_config() должен возвращать словарь {"LOG_FILE": "app.log"}.

        """
        raise RuntimeError(
            "Метод get_default_config() не переопределён в наследнике. "
            "Передайте config напрямую в get_instance() или переопределите метод."
        )

    def setLevel(self, level):
        """
        Установка уровня логирования для логгера.

        Уровень logging, который будет использоваться для логгера, определяется параметром level.
        """
        self.logger.setLevel(level)


    def __init__(
            self,
            name: str,
            config: Optional[Union[str,Dict[str, Any]]] = None,
            enable_file_logging: Union[str,bool] = False,
            use_name_in_filename: Union[str,bool] = False
    ): 
        """
        Инициализирует новый экземпляр логгера. Не вызывается напрямую – используйте get_instance().

        :param name: (str) Имя логгера.
        :param config: (str/dict) : Конфигурация для нового экземпляра (если None, используется провайдер
                str     - Указатель на экземпляр лога откуда берём этот параметр. 
                dict    - Словарь с настройками. 
                None    - Если не передан, загружается через get_default_config().   
        :param enable_file_logging: (str/bool) : Для нового экземпляра: включать ли запись в файл.
                str     - Указатель на экземпляр лога откуда берём этот параметр. 
                True    - добавляется файловый обработчик. 
                False   - только консоль.
        :param use_name_in_filename: (str/bool) : Для нового экземпляра: добавлять ли имя в имя файла.
                str     - Указатель на экземпляр лога откуда берём этот параметр. 
                True    - имя экземпляра вставляется в имя файла лога. 
                False   - имя экземпляра НЕ вставляется в имя файла лога.
        """

        self.name = name

        # if isinstance(enable_file_logging, str):
        #     enable_file_logging = self._instances[enable_file_logging].enable_file_logging

        # if isinstance(use_name_in_filename, str):
        #     use_name_in_filename = self._instances[use_name_in_filename].use_name_in_filename

        # if isinstance(config, str) and config is not None:
        #     config = {
        #         'LOG_LEVEL' : dict(zip(BaseAppLogger.level_map.values(), BaseAppLogger.level_map.keys()))[self._instances[config].log_level],
        #         'LOG_FILE' : self._instances[config].base_log_file,
        #         'LOG_MAX_BYTES' : self._instances[config].log_max_bytes,
        #         'LOG_BACKUP_COUNT' : self._instances[config].log_backup_count,
        #     }
                
        # self.enable_file_logging = enable_file_logging
        # self.use_name_in_filename = use_name_in_filename

        # Сохраняем ссылки, если переданы строки
        if isinstance(enable_file_logging, str):
            self._enable_file_logging_ref = enable_file_logging
            self._enable_file_logging = False  # placeholder
        else:
            self._enable_file_logging_ref = None
            self._enable_file_logging = enable_file_logging

        if isinstance(use_name_in_filename, str):
            self._use_name_in_filename_ref = use_name_in_filename
            self._use_name_in_filename = False
        else:
            self._use_name_in_filename_ref = None
            self._use_name_in_filename = use_name_in_filename

        # Обработка config: если строка, берём из другого экземпляра
        if isinstance(config, str) and config is not None:
            parent = self._instances.get(config)
            if parent is not None:
                config = {
                    'LOG_LEVEL' : dict(
                        zip(
                            BaseAppLogger.level_map.values(), 
                            BaseAppLogger.level_map.keys()
                        )
                    )[parent.log_level],
                    'LOG_FILE' : parent.base_log_file,
                    'LOG_MAX_BYTES' : parent.log_max_bytes,
                    'LOG_BACKUP_COUNT' : parent.log_backup_count,
                }
            else:
                # родитель не найден – используем дефолт
                config = None

        # Загружаем конфигурацию
        if config is None:
            config = self.get_default_config()

        # Проверяем наличие обязательных ключей
        required_keys = [
            'LOG_LEVEL', 
            'LOG_FILE', 
            'LOG_MAX_BYTES', 
            'LOG_BACKUP_COUNT'
        ]

        missing_keys = [key for key in required_keys if key not in config]

        if missing_keys:
            raise ValueError(f"Отсутствуют обязательные ключи конфигурации: {missing_keys}")

        # Преобразуем строковые значения в нужные типы
        try:
            self.log_level = self._parse_log_level(config['LOG_LEVEL'])
            self.base_log_file = config['LOG_FILE']
            self.log_max_bytes = int(config['LOG_MAX_BYTES'])
            self.log_backup_count = int(config['LOG_BACKUP_COUNT'])
            self.log_args = config.get('LOG_ARGS', False)   # новый атрибут
        except ValueError as e:
            raise ValueError(f"Ошибка преобразования параметров логирования: {e}")


        # Создаём логгер (без обработчиков)
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.log_level)
        self.logger.propagate = False  # предотвращаем дублирование, если есть корневой логгер

        # Формат сообщений
        self.formatter = logging.Formatter(self.LOG_FORMAT)

        # Консольный обработчик (всегда)
        self.console_handler = logging.StreamHandler()
        self.console_handler.setLevel(self.log_level)
        self.console_handler.setFormatter(self.formatter)
        self.logger.addHandler(self.console_handler)

        # Инициализируем файловый обработчик (может быть None)
        self.file_handler = None
        self._update_file_handler()  # создаст, если нужно

        # Добавляем глобальные обработчики
        for handler in self._global_handlers:
            self.logger.addHandler(handler)

        # Сохраняем ссылки на обработчики (может пригодиться для GUI)
        self.handlers = self.logger.handlers[:]



        # # Формируем фактическое имя файла лога (если нужно)
        # if self.enable_file_logging and self.use_name_in_filename:
        #     base, ext = os.path.splitext(self.base_log_file)
        #     self.log_file = f"{base}_{self.name}{ext}"
        # else:
        #     self.log_file = self.base_log_file

        # # Создаём папку для логов, если она не существует
        # log_dir = os.path.dirname(self.log_file)
        # if log_dir and not os.path.exists(log_dir):
        #     os.makedirs(log_dir, exist_ok=True)

        # # Настраиваем логгер
        # self.logger = logging.getLogger(name)
        # self.logger.setLevel(self.log_level)
        # self.logger.propagate = False  # предотвращаем дублирование, если есть корневой логгер

        # # Формат сообщений
        # formatter = logging.Formatter(self.LOG_FORMAT)

        # # Добавляем файловый обработчик, если разрешено
        # if self.enable_file_logging:
        #     file_handler = RotatingFileHandler(
        #         filename=self.log_file,
        #         maxBytes=self.log_max_bytes,
        #         backupCount=self.log_backup_count,
        #         encoding='utf-8'
        #     )
        #     file_handler.setLevel(self.log_level)
        #     file_handler.setFormatter(formatter)
        #     self.logger.addHandler(file_handler)
        # else :
        #     0==0
        # # Консольный обработчик (всегда включён для отладки)
        # console_handler = logging.StreamHandler()
        # console_handler.setLevel(self.log_level)
        # console_handler.setFormatter(formatter)
        # self.logger.addHandler(console_handler)

        # # Добавляем глобальные обработчики
        # for handler in self._global_handlers:
        #     self.logger.addHandler(handler)

        # # Сохраняем ссылки на обработчики (может пригодиться для добавления GUI-обработчика позже)
        # self.handlers = self.logger.handlers[:]

    def _update_file_handler(self):
        """
        Пересоздаёт файловый обработчик в соответствии с текущими настройками enable_file_logging и use_name_in_filename.
        """
        # Если нужен файловый обработчик, но его нет, или он есть, но не должен быть
        current_enabled = self.enable_file_logging
        if current_enabled and self.file_handler is None:
            # Создаём новый
            self.file_handler = self._create_file_handler()
            self.logger.addHandler(self.file_handler)
        elif not current_enabled and self.file_handler is not None:
            # Удаляем существующий
            self.logger.removeHandler(self.file_handler)
            self.file_handler.close()
            self.file_handler = None
        elif current_enabled and self.file_handler is not None:
            # Проверяем, не изменилось ли имя файла (если use_name_in_filename изменилось)
            new_log_file = self._get_log_file()
            if self.file_handler.baseFilename != new_log_file:
                # Заменяем
                self.logger.removeHandler(self.file_handler)
                self.file_handler.close()
                self.file_handler = self._create_file_handler()
                self.logger.addHandler(self.file_handler)

    def _create_file_handler(self):
        """Создаёт файловый обработчик на основе текущих настроек."""
        log_file = self._get_log_file()
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=self.log_max_bytes,
            backupCount=self.log_backup_count,
            encoding='utf-8'
        )
        handler.setLevel(self.log_level)
        handler.setFormatter(self.formatter)
        return handler

    def _get_log_file(self):
        """Возвращает имя файла лога с учётом use_name_in_filename."""
        if self.use_name_in_filename:
            base, ext = os.path.splitext(self.base_log_file)
            return f"{base}_{self.name}{ext}"
        return self.base_log_file

    # --- Свойства для динамического получения значений от родителя ---
    @property
    def enable_file_logging(self):
        if self._enable_file_logging_ref:
            parent = self._instances.get(self._enable_file_logging_ref)
            if parent is not None:
                return parent.enable_file_logging
        return self._enable_file_logging

    @enable_file_logging.setter
    def enable_file_logging(self, value):
        if self._enable_file_logging_ref:
            parent = self._instances.get(self._enable_file_logging_ref)
            if parent is not None:
                parent.enable_file_logging = value
                return
        self._enable_file_logging = value
        self._update_file_handler()

    @property
    def use_name_in_filename(self):
        if self._use_name_in_filename_ref:
            parent = self._instances.get(self._use_name_in_filename_ref)
            if parent is not None:
                return parent.use_name_in_filename
        return self._use_name_in_filename

    @use_name_in_filename.setter
    def use_name_in_filename(self, value):
        if self._use_name_in_filename_ref:
            parent = self._instances.get(self._use_name_in_filename_ref)
            if parent is not None:
                parent.use_name_in_filename = value
                return
        self._use_name_in_filename = value
        self._update_file_handler()



    @classmethod
    def thec_craete(
        cls,
        name: str,
    ) -> bool:
        """
        Проверяем, существует ли уже экземпляр класса с именем name.
        
        :param name: Имя экземпляра класса.
        :return: True, если экземпляр с именем name существует, False в противном случае.
        """
        return (name in cls._instances )

    @classmethod
    def get_instance(
        cls,
        name: str = 'default',
        force_new: bool = False,
        config: Optional[Dict[str, Any]] = None,
        enable_file_logging: Union[str,bool] = False,
        use_name_in_filename: Union[str,bool] = False
    ) -> 'BaseAppLogger':
        """
        Возвращает экземпляр логгера с указанным именем.

        Если force_new=False, то происходит следующее:
        - Если экземпляр с таким именем уже существует, возвращается существующий
          (параметры enable_file_logging и use_name_in_filename игнорируются).
        - Если экземпляр с таким именем не существует, создаётся новый экземпляр.

        Если force_new=True, то:
        - Создаётся новый экземпляр (старый при этом не удаляется).

        :param name: (str) Имя логгера.
        :param force_new: (bool) Принудительное создание нового экземпляра.
        :param config: (dict) Конфигурация для нового экземпляра (если None, используется провайдер).
        :param enable_file_logging: (bool) Для нового экземпляра: включать ли запись в файл.
        :param use_name_in_filename: (bool) Для нового экземпляра: добавлять ли имя в имя файла.
        :return: Экземпляр BaseAppLogger.
        """
        if not force_new and (cls.thec_craete(name = name)):
            # Если экземпляр с таким именем уже существует и force_new=False, возвращается существующий
            return cls._instances[name]

        # Создаём новый экземпляр
        instance = cls(
            name=name,
            config=config,
            enable_file_logging=enable_file_logging,
            use_name_in_filename=use_name_in_filename
        )
        cls._instances[name] = instance
        return instance

    @staticmethod
    def _parse_log_level(level_str: str) -> int:
        """
        Преобразует строковое представление уровня логирования в константу logging.
        """

        upper_str = level_str.upper()

        if upper_str not in BaseAppLogger.level_map:
            raise ValueError(f"Неизвестный уровень логирования: {level_str}. Допустимые: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return BaseAppLogger.level_map[upper_str]

    # --------------------------------------------------------------------------
    # Вспомогательные методы для формирования указателя на место вызова
    # --------------------------------------------------------------------------

    def _convert_patterns_modeles_tips(
        self,
        modeles,
        simple_types = (int, float, str, bool, type(None)),
    ):  
        """
        Преобразует указатель на место вызова в множество значений.

        Если указатель на место вызова является одним из простых типов (int, float, str, bool, None), то возвращает множество с одним элементом - этим указателем.
        Если указатель на место вызова не является множеством, то возвращает множество с указателем на место вызова как единственным элементом.
        """
        
        if  isinstance(modeles, simple_types):
            return {modeles}
        elif  not isinstance(modeles, set):
            return set(modeles) 
       
    def _thec_patterns_modeles_is_none(
        self,
        modeles,
        if_err_tip: bool,
    )-> bool: 
        """
        Проверяет, является ли указатель на место вызова None или пустым.
        
        :param modeles: (Any) Указатель на место вызова.
        :param if_err_tip: (bool) Если True, то если указатель на место вызова None или пустой, то будет выброшено исключение ValueError.
        :return: (bool) True, если указатель на место вызова None или пустой, False в противном случае.
        """
        # Проверка на наличие              
        if (modeles is None)  : 
            if if_err_tip :  
                raise ValueError('err: filename is None')  
            return True  
        if (len(modeles) == 0) :
            if if_err_tip :  
                raise ValueError('err: filename is None')  
            return True 
        
        return False 

    def _thec_patterns_modeles(
        self,
        modeles,
        if_err_tip,
    ): 
        """
        Проверяет, является ли указатель на место вызова None или пустым.
        
        Если указатель на место вызова None или пустой, то возвращает None.
        Если указатель на место вызова не является множеством, то возвращает множество с указателем на место вызова как единственным элементом.
        """
        
                      
        # Проверка на наличие   
        if self._thec_patterns_modeles_is_none(
            modeles     = modeles,
            if_err_tip  = if_err_tip,
        ):
            return None             
                
        modeles = self._convert_patterns_modeles_tips(
            modeles = modeles
        )
        
        return modeles 
        
    def _thec_skip_patterns_modeles(
        self,
        patterns_modeles
    ):  
        """
        Проверяет, если при указанных параметрах modeles стоит пропустить
        логирование.

        :param patterns_modeles: Словарь с параметрами для фильтрации.
        :return: True - указатель есть в блок листе, False - нет в блок листе.
        """

        # Проверяем, если указатель на место вызова есть в общем блоке лист
        for skip_patterns_modele in self.skip_patterns_modeles: 
            # общий блок лист
            for i in [
                'filename', 
                'function',
            ]:
                # Флаг, указывающий на то, что мы проверяем filename или function
                if_filename  = (i == 'filename')
                
                # Проверяем, есть ли указатель на место вызова в skip
                thec_skip = self._thec_patterns_modeles( 
                    modeles     = skip_patterns_modele.get(i,{}) ,
                    if_err_tip  = if_filename,
                )
                if thec_skip is None:
                    # если нет в skip указателя на function, блок лист (так как filename пройден)
                    # то возвращаем True
                    return True  
                
                # Проверяем, есть ли указатель на место вызова в patterns_modeles
                thec_modeles = self._thec_patterns_modeles(
                    modeles     = patterns_modeles.get(i,{}) ,
                    if_err_tip  = if_filename,
                )
                if thec_modeles is None:
                    # если нет в skip указателя на function, блок лист (так как filename пройден)
                    # то возвращаем True
                    return True  
                    
                # Проверяем, если указатель на место вызова есть в блок листе
                for modele in thec_modeles: 
                    # что проверяем на наличие в блок листе  
                
                    if self._thec_patterns_modeles_is_none(
                        modeles     = modele ,
                        if_err_tip  = if_filename  , 
                    ):
                        # если нет в skip указателя на function, блок лист (так как filename пройден)
                        # то возвращаем True
                        return True

                    if ( # проверка на наличие в блок листе
                        modele in thec_skip
                    ) or (
                        modele == thec_skip
                    ) :
                        # если указатель на место вызова есть в общем блоке лист, то возвращаем True
                        return True  
                    else:
                        # иначе мы проверяем, если указатель на место вызова есть в skip
                        skip_thec = True
                        for skip in thec_skip:
                            if self._thec_patterns_modeles_is_none(
                                modeles     = skip ,   
                                if_err_tip  = if_filename  , 
                            ):
                                # если нет в skip указателя на function, блок лист (так как filename пройден)
                                # то возвращаем True
                                return True 

                            # проверка на наличие каждого элимента по пути
                            skip_thec_ = (
                                (skip in modele) or (skip == modele)
                            )
                            
                            if if_filename or ( skip_thec) : 
                                # если filename, то нудно проверить нахождение каждого элимента по пути. Если все есть, то переход на проверку function
                                skip_thec = skip_thec and skip_thec_
                            else: 
                                # возможно вернуть  skip_thec_, а не continue
                                continue

                        if not skip_thec:
                            # если указатель на место вызова не находится в skip, то возвращаем False
                            return False   
            if not skip_thec:
                # если указатель на место вызова не находится в skip, то возвращаем False
                return False 

        # если указатель на место вызова не находится в общем блоке лист, то возвращаем True
        return True
        



    def _get_caller_info(self, levels_up: int = 2) -> str:
        """
        Возвращает строку с информацией о caller'е.

        - Если levels_up > 0: поднимается на указанное количество уровней (стандартное поведение).
        - Если levels_up == 0: автоматически ищет первый фрейм вне модулей логирования.

        Важно: мы используем inspect.stack() для получения стека вызываемых функций.
        Каждый элемент стека - это объект FrameInfo, содержащий информацию о текущей функции:
          - filename: путь к файлу, в котором находится функция
          - lineno: номер строки в файле, в которой находится функция
          - function: имя функции

        Мы ищем фрейм, чей файл не содержит 'logger' или 'base_logger', чтобы не учитывать
        вызовы изнутри модулей логирования. Если таких фреймов не найдено, берем последний
        фрейм (в конце стека).
        """
        import inspect
        stack = inspect.stack()
        frame_info = stack[-1]

        if levels_up > 0:
            # Явно заданная глубина
            if len(stack) <= levels_up:
                frame_info = stack[-1]
            else:
                frame_info = stack[levels_up]
        else:
            # Автоматический поиск: пропускаем фреймы, относящиеся к логгеру
            # Пропускаем текущий фрейм (индекс 0) и ищем первый, чей файл не содержит 'logger'
            
            for frame_info in stack[1:]:

                if self._thec_skip_patterns_modeles( # если входит в список пропуска, то след итерация
                    patterns_modeles={
                        'filename':(frame_info.filename),
                        'function':(frame_info.function),  
                    }
                ):
                    continue
                # если не в списке, то выводим            
                filename = frame_info.filename
                break
                
            else:
                # Если не нашли (вдруг весь стек состоит из логгера), берём последний
                frame_info = stack[-1]

        filename = frame_info.filename
        lineno = frame_info.lineno
        funcname = frame_info.function
        return f'File "{filename}", line {lineno}, in <{funcname}>'
    
    def _format_message(self, caller_info: str, message: str) -> str:
        """
        Форматирует итоговое сообщение, добавляя имя логгера и указатель.

        caller_info - строка, полученная из _get_caller_info, содержащая информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, который будет добавлен к caller_info

        Возвращаемый результат - строка, содержащая caller_info и message, разделенные символом табуляции '\t'
        """
        return f"[{self.name}]\t{caller_info}:\t{message}"

    # --------------------------------------------------------------------------
    # Прямые методы логирования
    # --------------------------------------------------------------------------
    
    def _formatted(
            self,
            message: str,  # текст сообщения, которое будет добавлено к caller_info
            levels_up: int = None,  # глубина поиска в стеке вызов (0 - автоматически, > 0 - явно)
    ):
        """
        Форматирует итоговое сообщение, добавляя имя логгера и указатель.

        - levels_up: глубина поиска в стеке вызов (0 - автоматически, > 0 - явно)
        - message: текст сообщения, которое будет добавлено к caller_info

        Возвращаемый результат - строка, содержащая caller_info и message, разделенные символом табуляции '\t'
        """
        if levels_up is None:
            levels_up = self._levels_up

        caller = self._get_caller_info(
            levels_up=levels_up
        )
        return self._format_message(
            caller, 
            message,
        )
        
    
    def debug(self, message: str) -> None:
        """
        Метод для логирования отладки в уровне DEBUG.

        Он вызывает self.logger.debug сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """
        self.logger.debug(
            self._formatted(
                message = message,   
            )
        )

    def info(self, message: str) -> None:
        """
        Метод для логирования информации в уровне INFO.

        Он вызывает self.logger.info сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """
        self.logger.info(
            self._formatted(
                message = message,   
            )
        )

    def warning(self, message: str) -> None:
        """
        Метод для логирования предупреждения в уровне WARNING.

        Он вызывает self.logger.warning сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """
        self.logger.warning(
            self._formatted(
                message = message,   
            )
        )

    def error(self, message: str) -> None:
        """
        Метод для логирования ошибки в уровне ERROR.

        Он вызывает self.logger.error сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """
        self.logger.error(
            self._formatted(
                message = message,   
            )
        )

    def critical(self, message: str) -> None:
        """
        Метод для логирования критических ошибок в уровне CRITICAL.

        Он вызывает self.logger.critical сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """
        self.logger.critical(
            self._formatted(
                message = message,   
            )
        )

    def exception(self, message: str, exc_info: bool = True) -> str:
        """
        Метод для логирования информации об ошибке в уровне ERROR.

        Он вызывает self.logger.error сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции
            - информацию об ошибке (если exc_info == True)

        message - текст сообщения, которое будет добавлено к caller_info
        exc_info - флаг, указывающий, нужно ли добавлять информацию об ошибке
        """
        self.logger.error(
            self._formatted(
                message = message,   
            ), exc_info=exc_info
        )
        return message
        

    # --------------------------------------------------------------------------
    # Декоратор для замера времени выполнения
    # --------------------------------------------------------------------------

    def log_execution_time(
            self, 
            description: str = "", 
            level: int = logging.DEBUG,
            log_args: Optional[bool] = None,
        ) -> Callable:
        """
        Декоратор для логирования времени выполнения функции или метода.

        :param description: дополнительное описание (будет добавлено перед сообщением)
        :param level: уровень логирования
        :param log_args: если True, в начало логирования добавляются переданные аргументы.
                         Если None, используется значение из конфигурации логгера (self.log_args).
        """
        logger_instance = self

        if log_args is None:
            log_args = self.log_args

        def decorator(func: Callable) -> Callable:
            """
            Декоратор для логирования времени выполнения функции или метода.

            Он обернул функцию, добавляя информацию о вызове функции:
                - имя файла, в котором находится вызов функции
                - номер строки в файле, в которой находится вызов функции
                - имя функции
                - информацию об ошибке (если exc_info == True)

            description - текст, добавляемый к caller_info
            level - уровень логирования
            log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
            """
            # func_filename = inspect.getfile(func)
            # func_lineno = func.__code__.co_firstlineno
            # func_name = func.__name__
            # is_async = inspect.iscoroutinefunction(func)

            # Используем квалифицированное имя (с классом, если это метод)
            func_qualname = func.__qualname__
            try:
                # Получаем имя файла, в котором находится вызов функции
                func_filename = inspect.getfile(func)
            except TypeError:
                # Если функция - встроенная, то имя файла не может быть получено
                func_filename = "<built-in>"

            # Получаем номер строки в файле, в которой находится вызов функции
            func_lineno = func.__code__.co_firstlineno
            # Определяем, является ли функция асинхронной
            is_async = inspect.iscoroutinefunction(func)

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                """
                Обернулка для синхронных функций.

                Она вызывает функцию, добавляя информацию о вызове функции:
                    - имя файла, в котором находится вызов функции
                    - номер строки в файле, в которой находится вызов функции
                    - имя функции
                    - информацию об аргументах (если log_args == True)

                description - текст, добавляемый к caller_info
                level - уровень логирования
                log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
                """
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'

                # Формируем строку с описанием
                desc_part = f"{description} " if description else ""

                # Определяем, нужно ли логировать аргументы
                effective_log_args = log_args

                # Для __init__ всегда отключаем логирование аргументов
                if func.__name__ == '__init__':
                    effective_log_args = False
                    
                # Формируем строку с аргументами
                # args_part = ""
                # if log_args:
                #     args_str = ', '.join(repr(a) for a in args) if effective_log_args else ''
                #     kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
                #     all_args = ', '.join(filter(None, [args_str, kwargs_str]))
                #     args_part = f" with args: ({all_args})"
                args_part = ""
                if effective_log_args:
                    # Для методов исключаем self из отображения
                    display_args = args
                    # Проверяем, является ли функция методом (первый аргумент обычно self)
                    if args and inspect.ismethod(func) and func.__self__ is not None:
                        display_args = args[1:]  # убираем self
                    args_str = ', '.join(repr(a) for a in display_args)
                    kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
                    all_args = ', '.join(filter(None, [args_str, kwargs_str]))
                    args_part = f" with args: ({all_args})"

                # Формируем строку с информацией о вызове функции
                start_msg = f"{desc_part}[Начало]{args_part}"

                # Формируем полное сообщение
                formatted_start = logger_instance._format_message(caller_info, start_msg)

                # Логируем сообщение
                logger_instance.logger.log(level, formatted_start)

                # Получаем время начала выполнения
                start_time = time.time()

                # Вызываем функцию
                result = func(*args, **kwargs)

                # Получаем время окончания выполнения
                execution_time = time.time() - start_time

                # Формируем строку с информацией о времени выполнения
                end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"

                # Формируем полное сообщение
                formatted_end = logger_instance._format_message(caller_info, end_msg)

                # Логируем сообщение
                logger_instance.logger.log(level, formatted_end)

                return result

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                """
                Обернулка для асинхронных функций.

                Она вызывает функцию, добавляя информацию о вызове функции:
                    - имя файла, в котором находится вызов функции
                    - номер строки в файле, в которой находится вызов функции
                    - имя функции
                    - информацию об аргументах (если log_args == True)

                description - текст, добавляемый к caller_info
                level - уровень логирования
                log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
                """
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'

                # Формируем строку с описанием
                desc_part = f"{description} " if description else ""


                effective_log_args = log_args
                if func.__name__ == '__init__':
                    effective_log_args = False

                # Формируем строку с аргументами
                # args_part = ""
                # if log_args:
                #     args_str = ', '.join(repr(a) for a in args)
                #     kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
                #     all_args = ', '.join(filter(None, [args_str, kwargs_str]))
                #     args_part = f" with args: ({all_args})"

                args_part = ""
                if effective_log_args:
                    display_args = args
                    if args and inspect.ismethod(func) and func.__self__ is not None:
                        display_args = args[1:]
                    args_str = ', '.join(repr(a) for a in display_args)
                    kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
                    all_args = ', '.join(filter(None, [args_str, kwargs_str]))
                    args_part = f" with args: ({all_args})"
                # Формируем строку с информацией о вызове функции
                start_msg = f"{desc_part}[Начало]{args_part}"

                # Формируем полное сообщение
                formatted_start = logger_instance._format_message(caller_info, start_msg)

                # Логируем сообщение
                logger_instance.logger.log(level, formatted_start)

                # Получаем время начала выполнения
                start_time = time.time()

                # Вызываем функцию
                result = await func(*args, **kwargs)

                # Получаем время окончания выполнения
                execution_time = time.time() - start_time

                # Формируем строку с информацией о времени выполнения
                end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"

                # Формируем полное сообщение
                formatted_end = logger_instance._format_message(caller_info, end_msg)

                # Логируем сообщение
                logger_instance.logger.log(level, formatted_end)

                return result

            return async_wrapper if is_async else sync_wrapper

        return decorator

    # --------------------------------------------------------------------------
    # Закрытие логгера
    # --------------------------------------------------------------------------
    def close(self) -> None:
        """
        Закрывает логгер, удаляя все хендлеры из него и очищает список хендлеров.
        
        1. Берем все хендлеры из логгера (self.logger.handlers[:])
        2. Закрываем каждый хендлер (handler.close())
        3. Удаляем каждый хендлер из логгера (self.logger.removeHandler(handler))
        4. Очищаем список хендлеров (self.handlers.clear())
        """
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        self.handlers.clear()

    @classmethod
    def close_all(cls) -> None:
        """
        Закрывает все экземпляры логгера, удаляя все хендлеры из каждого из них,
        и очищает словарь экземпляров.
        """
        for instance in cls._instances.values():
            instance.close()
        cls._instances.clear()


# ------------------------------------------------------------------------------
# Экспортируем только класс
# ------------------------------------------------------------------------------
__all__ = ['BaseAppLogger']