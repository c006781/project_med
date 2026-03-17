
# Стандартные библиотеки Python
import os

# Сторонние библиотеки
import yadisk # pip install yadisk requests

# def yadisk_download_file(
#         ya_token:str,
#         ya_file_path:str,
#         local_file_path:str,
#         if_err:bool = False,
# ):
#     """
#     Скачивание файла с yadisk.

#     :param ya_token: Токен к диску
#     :param ya_file_path: Положение файла на диске
#         пример: '/Проекты/отчётн 1/Внесение/пример 1.xlsx',
#     :param local_file_path: Путь куда сохранять файл + его название
#         пример: './пример.xlsx',
#     :param if_err: Выводить ошибки (True) или метки на ошибки (False)
#     """
    
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         if if_err:
#             raise("Connection to Yandex.Disk could not be established.")
#         else:
#             return -1


#     if y.check_token():
#         if y.exists(ya_file_path):
#             y.download(ya_file_path, local_file_path)
#         else:
#             if if_err:
#                 raise(f"Err: The {ya_file_path} file does not exist on Yandex.Disk")
#                 # print(f'Файл {ya_file_path} не существует на Яндекс.Диске.')
#             else:
#                 return -2

#         return 0
    

# def yadisk_upload_file(
#         ya_token: str,
#         local_file_path: str,
#         ya_file_path: str,
#         if_err: bool = False,
# ):
#     """
#     Загрузка файла на Яндекс.Диск.

#     :param ya_token: Токен доступа к Яндекс.Диску
#     :param local_file_path: Путь к локальному файлу, который нужно загрузить
#                            (например, './отчёт.xlsx')
#     :param ya_file_path: Путь на Яндекс.Диске, куда сохранить файл
#                         (например, '/Проекты/отчёты/отчёт.xlsx')
#     :param if_err: Если True — при ошибках выбрасываются исключения,
#                    если False — возвращаются коды ошибок
#     :return: 0 при успехе,
#              -1 если токен недействителен или нет соединения,
#              -2 если локальный файл не существует,
#              -3 при другой ошибке (например, недостаточно места, ошибка сети)
#     """
#     # Проверяем существование локального файла
#     if not os.path.isfile(local_file_path):
#         if if_err:
#             raise FileNotFoundError(f"Локальный файл {local_file_path} не существует.")
#         return -2

#     # Создаём объект Яндекс.Диска и проверяем токен
#     y = yadisk.YaDisk(token=ya_token)
#     if not y.check_token():
#         if if_err:
#             raise ConnectionError("Не удалось подключиться к Яндекс.Диску. Проверьте токен.")
#         return -1

#     try:
#         # Создаём родительские папки на Яндекс.Диске, если их нет
#         parent_dir = os.path.dirname(ya_file_path)
#         if parent_dir and not y.exists(parent_dir):
#             y.mkdir(parent_dir)

#         # Загружаем файл (если файл уже существует, он будет перезаписан)
#         y.upload(local_file_path, ya_file_path)
#         return 0
#     except Exception as e:
#         if if_err:
#             # Пробрасываем исключение дальше
#             raise e
#         else:
#             # Возвращаем общий код ошибки
#             return -3


def yadisk_download_file(
        ya_token: str,
        ya_file_path: str,
        local_file_path: str,
        if_err: bool = False,
        progress_callback=None,
):
    """
    Скачивание файла с yandex.disk с поддержкой прогресса.

    :param ya_token: Токен к диску
    :param ya_file_path: Положение файла на диске (например, '/Проекты/отчёт.xlsx')
    :param local_file_path: Путь куда сохранять файл + его название (например, './отчёт.xlsx')
    :param if_err: Выводить ошибки (True) или возвращать коды ошибок (False)
    :param progress_callback: Функция, вызываемая для обновления прогресса.
                              Принимает два аргумента: (already_done, total)
    :return: 0 при успехе, -1 при проблеме с токеном, -2 если файл не существует на диске,
             -3 при другой ошибке.
    """
    y = yadisk.YaDisk(token=ya_token)
    if not y.check_token():
        if if_err:
            raise ConnectionError("Connection to Yandex.Disk could not be established.")
        return -1

    if not y.exists(ya_file_path):
        if if_err:
            raise FileNotFoundError(f"The file {ya_file_path} does not exist on Yandex.Disk")
        return -2

    try:
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
        y.download(ya_file_path, local_file_path, progress_callback=progress_callback)
        return 0
    except Exception as e:
        if if_err:
            raise e
        return -3


def yadisk_upload_file(
        ya_token: str,
        local_file_path: str,
        ya_file_path: str,
        if_err: bool = False,
        progress_callback=None,
):
    """
    Загрузка файла на yandex.disk с поддержкой прогресса.

    :param ya_token: Токен к диску
    :param local_file_path: Путь к локальному файлу (например, './отчёт.xlsx')
    :param ya_file_path: Путь на диске, куда сохранять файл (например, '/Проекты/отчёт.xlsx')
    :param if_err: Выводить ошибки (True) или возвращать коды ошибок (False)
    :param progress_callback: Функция, вызываемая для обновления прогресса.
                              Принимает два аргумента: (already_done, total)
    :return: 0 при успехе, -1 при проблеме с токеном, -2 если локальный файл не существует,
             -3 при другой ошибке.
    """
    if not os.path.isfile(local_file_path):
        if if_err:
            raise FileNotFoundError(f"Local file {local_file_path} does not exist.")
        return -2

    y = yadisk.YaDisk(token=ya_token)
    if not y.check_token():
        if if_err:
            raise ConnectionError("Connection to Yandex.Disk could not be established.")
        return -1

    try:
        parent_dir = os.path.dirname(ya_file_path)
        if parent_dir and not y.exists(parent_dir):
            y.mkdir(parent_dir)

        y.upload(local_file_path, ya_file_path, progress_callback=progress_callback)
        return 0
    except Exception as e:
        if if_err:
            raise e
        return -3