# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

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


# try:
#     from .set_env import crete_env_file as crete_env_file
# except ImportError:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name(
#         file_module = __file__,
#         path_join = [
            
#         ] + [
#             '.' for _ in range(1) # насколько шагов назад нужно
#         ],
#     )

#     from .set_env import crete_env_file as crete_env_file

# try:
#     from .set_env import sawe_env_file as sawe_env_file
# except ImportError:
#     # Попытка абсолютного импорта, если модуль запущен как скрипт
#     _add_package_name(
#         file_module = __file__,
#         path_join = [
            
#         ] + [
#             '.' for _ in range(1) # насколько шагов назад нужно
#         ],
#     )

#     from .set_env import sawe_env_file as sawe_env_file

# from pathlib import Path

# Сторонние библиотеки
from dotenv import load_dotenv, set_key, find_dotenv# pip install python-dotenv

def get_dotenv_path(
    name:str = None
):
    """
    .env в текущей директории или стандарт
    
    Args:
        name : (str) путь к .env

    """
    if not name:
        name =  '.env' # .env  стандарт

    return find_dotenv() or name # ищем .env в текущей директории или стандарт


def get_getenv (
    key:str,
    dotenv_path:str = None,
    start_value:str = None,
):
    """
    Обработчик получение знаяений из окружения

    Args:
        key : (str) наименование ключа
        dotenv_path : (str) путь к .env
        start_value : (str) Начальное значение ключа (если ключа нет в dotenv_path)
    """

    if not dotenv_path:
        dotenv_path = get_dotenv_path() # ищем .env в текущей директории или стандарт

    load_dotenv_thec = load_dotenv(
        dotenv_path = dotenv_path
    )

    if not load_dotenv_thec:
        crete_env_file(dotenv_path)

        load_dotenv_thec = load_dotenv(
            dotenv_path = dotenv_path
        )

    thec = os.getenv(key)

    if (not thec) and (start_value):
        sawe_env_file(# внесение новых ключей
            env_key = {
                key : start_value
            },         
            dotenv_path = dotenv_path,
        )

        thec = os.getenv(key)
        
    if not thec:
        raise ValueError(f"{key} is required")
    
    return thec

def crete_env_file(
    dotenv_path:str = None,
):
    """
    Проверяет наличие .env, если нет – создаём.

    Args:
        dotenv_path : (str) путь к .env
    """

    if not dotenv_path:
        dotenv_path = get_dotenv_path() # ищем .env в текущей директории или стандарт   

    if not os.path.exists(dotenv_path) :
        with open(dotenv_path, 'w') as f:
            f.write(f"")

def sawe_env_file(
    env_key :  dict ,
    dotenv_path:str=None,
    if_update: bool = False,
):
    """
    Внесение ключей в .env

    Args:
        env_key     : (dict) набор ключей для внесения
        dotenv_path : (str) путь к .env
        if_update   : (bool) Принудительное обновление ключа в .env
    """
    if not dotenv_path:
        dotenv_path = get_dotenv_path() # найдёт .env в текущей директории    
    

    load_dotenv(
        dotenv_path =   dotenv_path, 
        # override    =   True,
    )

    iterated = False

    for key, value in env_key.items():

        if (
            not os.getenv(key) # проверка наличия ключа
            ) or (if_update): # если нет ключа или принудительная замена значения ключа

            iterated = True

            success, message, _ = set_key( # внесение нового ключа
                dotenv_path     = dotenv_path, 
                key_to_set      = key, 
                value_to_set    = value
            )

            if not success:
                raise ValueError(
                    f"Ошибка при записи {key}: {message}"
                )

    # Принудительно перезагружаем переменные в os.environ если было хобя бы 1но изменение
    if iterated:
        load_dotenv(
            dotenv_path =   dotenv_path, 
            override    =   True,
        )