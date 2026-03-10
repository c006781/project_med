
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

def _add_package_name(
    file_module:str = None, # указатель на модуль в котором вызываем
    # = __file__
    path_join:list = None, # указатель на подпапки, если есть
    # = [  # указатель на подпапки, если есть
    #     '.'
    # ],
) -> None:
    """
    Что это (кратко): Добавление имени пакета для относительных импортов.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

    :param file_module: (str) = __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param path_join: (list) = ['..']  - указатель на подпапки пути к модулю, папку которого делаем пакетом для относительных импортов (1н уровень выше)
                               ['..', '..']  - указатель на подпапки пути к модулю, папку которого делаем пакетом для относительных импортов (1н и 2 уровеней выше)

    """

    if not file_module is None:
        file_module: str = __file__  # __file__ — встроенная переменная: содержит путь к текущему скрипту

    if not path_join:
        path_join: list = [  # указатель на подпапки, если есть
            '.'
        ]

    global __package__  # Делаем __package__ глобальной: это позволяет изменить системную переменную, которая влияет на импорты.

    package_dir = os.path.dirname(
        # Получаем директорию текущего файла: dirname убирает имя файла, оставляя путь к папке.
        os.path.abspath(  # Получаем абсолютный путь: abspath преобразует относительный путь в полный, от корня диска.
            file_module  # __file__ — встроенная переменная: содержит путь к текущему скрипту.
        )
    )

    path_join = list(
        reversed( # переворачиаем list
            # list(
                # set(
                    path_join
                # )
            # )
        )
    )
    package_dir_ = None
    for i , _ in enumerate(
            path_join
    ): # Добавляем все подпапки на пути
        package_dir_ = os.path.abspath( # Получаем абсолютный путь
            os.path.join( # переходим в подпапку
                *[
                    package_dir
                ] + path_join[i:]
            )
        )

        new_path =  os.path.dirname(  # Получаем родительскую директорию: dirname от package_dir дает папку выше.
            package_dir_  # package_dir — это путь к текущей папке.
        )
        
        if not new_path in sys.path: # Если нет в списке 
            sys.path.append(
                # Добавляем в sys.path: append добавляет новый путь в конец списка, чтобы Python мог найти модули там.
                new_path # Получаем родительскую директорию: dirname от package_dir дает папку выше.
            )

    # Устанавливаем __package__ динамически
    if package_dir_:
        __package__ = os.path.basename(  # Устанавливаем __package__: basename берет только имя папки (без пути).
            package_dir  # package_dir — путь к текущей папке.
        )

try:
    from .getenv import get_getenv as get_getenv
except ImportError:
    # Попытка абсолютного импорта, если модуль запущен как скрипт
    _add_package_name(
        file_module = __file__,
        path_join = [
            
        ] + [
            '.' for _ in range(1) # насколько шагов назад нужно
        ],
    )

    from .getenv import get_getenv as get_getenv

def get_config_env():
    """
    Получение конфигураций из  .env, если нет – создаём.
    """

    return {
        'database':  get_getenv(
            key =   'database_233_bi_user',
            start_value= 'www1',
        ),
        'user': get_getenv(
            key =   'user_233_bi_user',
            start_value= 'www2',
        ),
        'password': get_getenv(
            key =   'password_233_bi_user',
            start_value= 'www3',
        ),
        'host': get_getenv(
            key =   'host_233_bi_user',
            start_value= 'www4',
        ),
        'port': get_getenv(
            key =   'port_233_bi_user',
            start_value= 'www5',
        ),
    }