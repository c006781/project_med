# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

# def _add_package_name(
#     file_module:str = None, # указатель на модуль в котором вызываем
#     # = __file__
#     path_join:list = None, # указатель на подпапки, если есть
#     # = [  # указатель на подпапки, если есть
#     #     '.'
#     # ],
# ) -> None:
#     """
#     Что это (кратко): Добавление имени пакета для относительных импортов.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

#     :param file_module: (str) = __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param path_join: (list) = ['..']  - указатель на подпапки пути к модулю, папку которого делаем пакетом для относительных импортов (1н уровень выше)
#                                ['..', '..']  - указатель на подпапки пути к модулю, папку которого делаем пакетом для относительных импортов (1н и 2 уровеней выше)

#     """

#     if not file_module is None:
#         file_module: str = __file__  # __file__ — встроенная переменная: содержит путь к текущему скрипту

#     if not path_join:
#         path_join: list = [  # указатель на подпапки, если есть
#             '.'
#         ]

#     global __package__  # Делаем __package__ глобальной: это позволяет изменить системную переменную, которая влияет на импорты.

#     package_dir = os.path.dirname(
#         # Получаем директорию текущего файла: dirname убирает имя файла, оставляя путь к папке.
#         os.path.abspath(  # Получаем абсолютный путь: abspath преобразует относительный путь в полный, от корня диска.
#             file_module  # __file__ — встроенная переменная: содержит путь к текущему скрипту.
#         )
#     )

#     path_join = list(
#         reversed( # переворачиаем list
#             # list(
#                 # set(
#                     path_join
#                 # )
#             # )
#         )
#     )
#     package_dir_ = None
#     for i , _ in enumerate(
#             path_join
#     ): # Добавляем все подпапки на пути
#         package_dir_ = os.path.abspath( # Получаем абсолютный путь
#             os.path.join( # переходим в подпапку
#                 *[
#                     package_dir
#                 ] + path_join[i:]
#             )
#         )

#         new_path =  os.path.dirname(  # Получаем родительскую директорию: dirname от package_dir дает папку выше.
#             package_dir_  # package_dir — это путь к текущей папке.
#         )
        
#         if not new_path in sys.path: # Если нет в списке 
#             sys.path.append(
#                 # Добавляем в sys.path: append добавляет новый путь в конец списка, чтобы Python мог найти модули там.
#                 new_path # Получаем родительскую директорию: dirname от package_dir дает папку выше.
#             )

#     # Устанавливаем __package__ динамически
#     if package_dir_:
#         __package__ = os.path.basename(  # Устанавливаем __package__: basename берет только имя папки (без пути).
#             package_dir  # package_dir — путь к текущей папке.
#         )


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


# temp_from = 'app.controllers.conf.getenv'.split('.')
# temp_from = {
#     '.'.join(temp_from[x:]) for x in range(len(temp_from))
# }
# # if not 'get_getenv' in sys.modules.keys():
# if len(
#     set(sys.modules.keys()).intersection(temp_from)
# ) == 0:
try:
    from .getenv import get_getenv as get_getenv
except ImportError:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(
            file_module = __file__,
            levels_up = 1,
            # path_join = [
                
            # ] + [
            #     '.' for _ in range(1) # насколько шагов назад нужно
            # ],
        )

        from .getenv import get_getenv as get_getenv
    except ImportError:
        pass
# del temp_from

def get_config_env():
    """
    Получение конфигураций из  .env, если нет – создаём.
    """

    return {
        'YANDEX_TOKEN':  get_getenv(
            key =   'YANDEX_TOKEN',
            start_value= '----',
        ),

        'database_local_path':  get_getenv(
            key =   'database_local_path',
            start_value = os.path.join(*['.','clinic.db']),
        ),
        'database_remote_path': get_getenv( 
            key =   'database_remote_path',
            start_value= 'Проекты/test/bd/clinic.db',
        ),

        
        'LOG_LEVEL': get_getenv(  
            key =   'LOG_LEVEL',
            start_value= 'DEBUG', # уровень логирования (DEBUG, INFO, WARNING, ERROR)
        ),
        'LOG_FILE': get_getenv( 
            key =   'LOG_FILE',
            start_value= os.path.join(*['.','logs','app.log']), # путь к файлу лога (например, logs/app.log)
        ),
        'LOG_MAX_BYTES': get_getenv( 
            key =   'LOG_MAX_BYTES',
            start_value= str(10 * 1024 * 1024),  # максимальный размер файла до ротации (в байтах)
        ),
        'LOG_BACKUP_COUNT': get_getenv( 
            key =   'LOG_BACKUP_COUNT',
            start_value= str(5), # количество сохраняемых бэкапов
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