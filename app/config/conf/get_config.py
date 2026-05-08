# app/config/conf/get_config.py

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).


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


# temp_from = 'app.controllers.conf.getenv'.split('.')
# temp_from = {
#     '.'.join(temp_from[x:]) for x in range(len(temp_from))
# }
# # if not 'get_getenv' in sys.modules.keys():
# if len(
#     set(sys.modules.keys()).intersection(temp_from)
# ) == 0:
# try:
from app.config.conf.getenv import get_getenv as get_getenv
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(
#             file_module = __file__,
#             levels_up = 1,
#             # path_join = [
                
#             # ] + [
#             #     '.' for _ in range(1) # насколько шагов назад нужно
#             # ],
#         )

#         from .getenv import get_getenv as get_getenv
#     except ImportError as e:
#         pass #  raise # e # pass
# del temp_from

def get_config_env(path: str = None)-> dict:
    """
    Получение конфигураций из  .env, если нет – создаём.
    Возвращает словарь с конфигурациями:
        APP_CONFIG_PATH - путь к файлу конфигурации (например, config/msgpack)
        # password - пароль пользователя
        # host - хост
        # port - порт

    Если конфигурация не найдена в .env, то создаём ее с значениями по умолчанию:
        APP_CONFIG_PATH - путь к файлу лога (например, logs/app.log)
        # password - www3
        # host - www4
        # port - www5

    """
    if not path:
        path = os.path.join(*['config.msgpack']) # путь к файлу лога (например, logs/app.log)

    return {
        'APP_CONFIG_PATH': get_getenv( 
            key =   'APP_CONFIG_PATH',
            start_value= path, # путь к файлу лога (например, logs/app.log)
        ),
        'APP_CONFIG_PATH': get_getenv( 
            key =   'GITHUB_TOKEN',
            start_value= '',   # пусто по умолчанию
        ),

        # 'password': get_getenv(
        #     key =   'password_233_bi_user',
        #     start_value= 'www3',
        # ),
        # 'host': get_getenv(
        #     key =   'host_233_bi_user',
        #     start_value= 'www4',
        # ),
        # 'port': get_getenv(
        #     key =   'port_233_bi_user',
        #     start_value= 'www5',
        # ),
    }

if __name__ == '__main__':
    global env_key
    env_key = get_config_env()
    pass