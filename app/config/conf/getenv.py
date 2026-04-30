# app/config/conf/getenv.py

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).

# from pathlib import Path

# Сторонние библиотеки
from dotenv import load_dotenv, set_key, find_dotenv # pip install python-dotenv

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


def get_getenv(
    key:str,
    start_value:str = None,
    dotenv_path:str = None,
):
    """
    Обработчик получение заначений из окружения

    Args:
        key : (str) наименование ключа
        dotenv_path : (str) путь к .env
        start_value : (str) Начальное значение ключа (если ключа нет в dotenv_path)
    """

    # Если не передан путь к .env, то ищем .env в текущей директории или стандарт
    if not dotenv_path:
        dotenv_path = get_dotenv_path() 

    # Загрузка .env
    load_dotenv_thec = load_dotenv(
        dotenv_path = dotenv_path
    )

    # Если .env не существует, то создаем его
    if not load_dotenv_thec:
        crete_env_file(dotenv_path)

        # И снова загружаем .env
        load_dotenv_thec = load_dotenv(
            dotenv_path = dotenv_path
        )

    # Получение значения ключа
    thec = os.getenv(key)

    # Если ключа нет в .env, то добавляем его с start_value
    if (not thec) and (start_value):
        save_env_file(# внесение новых ключей
            env_key = {
                key : start_value
            },         
            dotenv_path = dotenv_path,
        )

        # И снова загружаем .env, чтобы обновить os.environ
        load_dotenv( 
            dotenv_path = dotenv_path, 
            override    = True
        )
        thec = os.getenv(key)
        
    # Если ключа нет, то выбрасываем ошибку
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

def save_env_file(
    env_key     :  dict,  # набор ключей для внесения
    dotenv_path :str    = None,  # путь к .env
    if_update:   bool   = False,  # принудительное обновление ключа в .env
):
    """
    Внесение ключей в .env

    Args:
        env_key     : (dict) набор ключей для внесения
        dotenv_path : (str) путь к .env
        if_update   : (bool) Принудительное обновление ключа в .env
    """
    # Если не передан путь к .env, то ищем .env в текущей директории
    if not dotenv_path:
        dotenv_path = get_dotenv_path() 

    # Загрузка .env
    load_dotenv(
        dotenv_path =   dotenv_path, 
        # override    =   True,
    )

    iterated = False

    # Перебрать все ключи в env_key
    for key, value in env_key.items():
        # Если ключа нет в .env (или принудительная замена значения ключа)
        if (
            not os.getenv(key)  # проверка наличия ключа
            ) or (if_update):  # если нет ключа или принудительная замена значения ключа
            iterated = True

            # Вносим новый ключ в .env
            success, message, _ = set_key( 
                dotenv_path     = dotenv_path, 
                key_to_set      = key, 
                value_to_set    = value
            )

            # Если произошла ошибка при записи, то выбрасываем ошибку
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



if __name__ == '__main__':
    pass