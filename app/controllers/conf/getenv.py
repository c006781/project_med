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


def get_getenv (
    key:str,
    start_value:str = None,
    dotenv_path:str = None,
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
        save_env_file(# внесение новых ключей
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

def save_env_file(
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



if __name__ == '__main__':
    pass