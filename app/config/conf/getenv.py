# app/config/conf/getenv.py

# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).

# from pathlib import Path

import sys
import threading

# Сторонние библиотеки
from dotenv import load_dotenv, set_key, find_dotenv, dotenv_values # pip install python-dotenv

# Глобальная блокировка для операций записи в .env файл
_env_write_lock = threading.RLock()


def _report(message: str) -> None:
    """
    Сообщает о проблеме с .env в stderr.

    Логгер здесь не используется: .env читается ДО настройки логирования
    (setup_logging сам читает конфиг), сообщение должно быть видно в любом случае.

    Args:
        message: Текст сообщения.

    Returns:
        None

    Пример:
        >>> _report('не удалось записать .env')
        WARNING [config/.env]: не удалось записать .env
    """
    print(f"WARNING [config/.env]: {message}", file=sys.stderr)

def _key_in_file(dotenv_path: str, key: str) -> bool:
    """
    Есть ли ключ в самом файле .env (с любым значением, в том числе пустым).

    В отличие от ``os.getenv`` не зависит от переменных окружения процесса и от того,
    пустое ли значение. Нужен, чтобы не дописывать ключ, который в файле уже есть (E1).

    Args:
        dotenv_path: Путь к .env.
        key: Имя ключа.

    Returns:
        ``True``, если ключ записан в файле; ``False``, если ключа или файла нет.

    Пример:
        >>> _key_in_file('.env', 'GITHUB_TOKEN')     # в файле GITHUB_TOKEN=''
        True
    """
    if not dotenv_path or not os.path.exists(dotenv_path):
        return False
    try:
        return key in dotenv_values(dotenv_path)
    except OSError:
        return False


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

    # # Если ключа нет в .env, то добавляем его с start_value
    # if (not thec) and (start_value is not None):
    # ↑ до E1 (2026-10-14): ключ с пустым значением (GITHUB_TOKEN='') ЕСТЬ в файле, но
    #   «not ''» считал его отсутствующим — .env переписывался при каждом чтении конфига
    #   (17 раз за старт GUI). Теперь дописываем только ключ, которого нет в самом файле.
    #   Возвращаемое значение не меняется: пустое → start_value (как раньше).
    if (not thec) and (start_value is not None) and not _key_in_file(dotenv_path, key):
        # Сохраняем в .env под блокировкой
        try:
            with _env_write_lock:
                save_env_file( # внесение новых ключей
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
        except OSError as e:
            # E2 (2026-10-14): .env только для чтения (Program Files, антивирус) —
            # раньше PermissionError ронял запуск приложения. Теперь работаем со значением
            # по умолчанию в памяти и сообщаем.
            _report(f"не удалось записать '{key}' в {dotenv_path}: {e}. "
                    f"Используется значение по умолчанию: {start_value!r}")
        thec = os.getenv(key)
        
    # Если ключа нет, то выбрасываем ошибку
    if not thec:
        if start_value is not None:
            thec = start_value
        else:
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
        # with open(dotenv_path, 'w') as f:
        #     f.write(f"")
        # ↑ до E2 (2026-10-14): нет прав на папку → исключение и падение запуска.
        try:
            with open(dotenv_path, 'w') as f:
                f.write("")
        except OSError as e:
            _report(f"не удалось создать {dotenv_path}: {e}")

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

    with _env_write_lock:
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