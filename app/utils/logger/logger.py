#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль логирования приложения.

Содержит класс AppLogger, который:
- Управляет созданием и хранением экземпляров логгеров (паттерн Multiton).
- Каждый экземпляр настраивается индивидуально (имя, конфигурация).
- Предоставляет методы для логирования и декоратор log_execution_time.
- Не использует глобальные переменные (все данные хранятся в атрибутах класса).

Пример использования:
    # Получить экземпляр по умолчанию
    logger = AppLogger.get_instance()
    logger.info("Приложение запущено. Добавлен в общий лог")

    # Получить или создать другой экземпляр
    logger1 = AppLogger.get_instance(name='default1')
    logger1.info("Приложение запущено. Добавлен в лог default1")

    # Использовать декоратор для метода класса
    class PatientService:
        def __init__(self):
            self.logger = AppLogger.get_instance('patient')

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
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

from typing import  Dict, Any

# Импорты модулей
def _add_package_name(
    file_module: str = None,
    levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
) -> None:
    
    """
    Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

    :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
                       (подберите под структуру вашего проекта)
                       Примеры:
                         2 → до папки app
    """
    if file_module is None:
        file_module = __file__

    # Получаем директорию текущего файла
    current_dir = os.path.dirname(os.path.abspath(file_module))

    # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
    project_root = current_dir
    for _ in range(levels_up):
        project_root = os.path.dirname(project_root)

    # Добавляем корень проекта в начало sys.path (высокий приоритет)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Вычисляем правильное значение __package__
    # Пример: /project_med/app/models/bd → "app.models.bd"
    rel_path = os.path.relpath(current_dir, project_root)
    
    if rel_path == '.':
        package_name = ''
    else:
        package_name = rel_path.replace(os.sep, '.').strip('.')

    # Устанавливаем __package__
    global __package__
    if package_name:
        __package__ = package_name
    else:
        # Если мы в корне — можно оставить None или пустую строку
        __package__ = None

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
from app.utils.logger.base_logger import BaseAppLogger
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
    Менеджер логгеров с поддержкой нескольких именованных экземпляров.

    Атрибуты класса:
        _instances (dict): Словарь созданных экземпляров {имя: экземпляр}.

    Методы класса:
        get_instance(name='default', force_new=False, config=None) -> AppLogger:
            Возвращает экземпляр логгера с указанным именем.
    """

    _instances = {}  # переопределяем, чтобы был свой пул

    # Словарь экземпляров (ключ - имя логгера)
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]: # переопределяем,
        if 'app.config.config_manager.manager' not in sys.modules:
            from app.config.config_manager.manager import get_config_env
        else:
            get_config_env = sys.modules['app.config.config_manager.manager'].get_config_env
        
        # tt = sys.modules['app.config.config_manager.manager']
        return get_config_env()


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
    class PatientService:
        logger0 = AppLogger.get_instance('logger0')

        def __init__(self):
            self.logger = AppLogger.get_instance('logger')

        @logger0.log_execution_time(description="logger0 Получение пациента")
        def get_patient(self, patient_id):
            self.logger.debug(f"logger Запрос пациента с id={patient_id}")

        @AppLogger.get_instance().log_execution_time(description="logger avto Получение пациента")
        def get_patient2(self, patient_id):
            AppLogger.get_instance().debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...
        
        @AppLogger.get_instance(name='logger1').log_execution_time(description="Получение пациента")
        def get_patient3(self, patient_id):
            AppLogger.get_instance(name='logger1').debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...
            #    
        @AppLogger.get_instance().log_execution_time()
        def get_patient4(self, patient_id):
            AppLogger.get_instance(name='logger1').debug(f"Запрос пациента с id={patient_id}")
            # ... логика ...    

    # Использовать декоратор для обычной функции
    @AppLogger.get_instance().log_execution_time(description="Вспомогательная функция")
    def helper():
        pass
    
    PatientService_ = PatientService()
    PatientService_.get_patient(1)
    PatientService_.get_patient2(2)
    PatientService_.get_patient3(3)
    PatientService_.get_patient4(4)

    helper()



    AppLogger.get_instance(
        name='test1',
        config='default1',
    ).info("test1")
    AppLogger.get_instance(
        name='test2',
        enable_file_logging='default1',
    ).info("test2")
    AppLogger.get_instance(
        name='test3',
        use_name_in_filename='default1',
    ).info("test3")


    AppLogger.get_instance(
        name='test4',
        config='default1',
        enable_file_logging='default1',
        use_name_in_filename='default1',
    ).info("test4")

    0==0

    pass
# ------------------------------------------------------------------------------
# Экспортируем только класс – никаких глобальных переменных.
# ------------------------------------------------------------------------------
__all__ = ['AppLogger']
