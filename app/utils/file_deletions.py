# app/utils/file_deletions.py
"""
Утилиты для безопасного удаления файлов и папок с поддержкой отложенного выполнения.
"""

import os
import shutil
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.utils.logger.logger import AppLogger


def delete_file_safely(
    file_path: str, 
    logger: Optional[AppLogger] = None
) -> Tuple[bool, Optional[str]]:
    """
    Удаляет файл, если он существует и является файлом.

    Если файл не существует, считает операцию успешной (логирует DEBUG).
    Если путь ведёт к существующей директории, логирует DEBUG и возвращает `(True, None)`,
    т.к. удаление папок выполняется другими функциями (`delete_empty_directory`).

    Args:
        file_path: Путь к файлу.
        logger: Опциональный логгер.

    Returns:
        Tuple[bool, Optional[str]]: (успех, ошибка)
            - `(True, None)` – файл успешно удалён или не существовал.
            - `(False, Exception)` – ошибка при удалении (файл заблокирован, нет прав).
    """

    if logger is None:
        logger = AppLogger.get_instance(
            name = 'file_deletions',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system',
        )

    if not os.path.isfile(file_path):
        logger.debug(f"Файл не существует, удаление не требуется: {file_path}")
        return True , None

    try:
        os.remove(file_path)
        logger.debug(f"Удалён файл: {file_path}")
        return True, None
        
    except OSError as e:
        logger.warning(f"Не удалось удалить файл {file_path}: {e}")
        return False, str(e)


def delete_empty_directory(
        dir_path: str, 
        force: bool = False,
        logger: Optional[AppLogger] = None,
    ) -> Tuple[bool, Optional[str]]:
    """
    Удаляет директорию.

    Поведение:
        - Если `force=False` – удаляет только пустую директорию.
        - Если `force=True` – удаляет директорию рекурсивно (со всем содержимым).

    Args:
        dir_path: Путь к директории.
        force: Если True, удаляет даже непустую папку (рекурсивно).
        logger: Опциональный логгер.

    Returns:
        Tuple[bool, Optional[str]]: (успех, ошибка)
            - `(True, None)` – директория успешно удалена.
            - `(False, Exception)` – директория не существует, не пуста (при force=False),
              или произошла ошибка доступа/удаления.
    """

    if logger is None:
        logger = AppLogger.get_instance(
            name = 'file_deletions',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system',
        )

    if not dir_path:
        logger.warning("Попытка запланировать удаление пустого пути, игнорируем")
        return True, None

    if not os.path.isdir(dir_path):
        logger.debug(f"Директория не существует: {dir_path}, удаление не требуется")
        return True , None
    
    if force: # удалить папку со всем содержимым
        try:
            shutil.rmtree(dir_path)
            logger.warning(f"Принудительно удалена папка со всем содержимым: {dir_path}")
            return True , None
        
        except OSError as e:
            logger.warning(f"Не удалось удалить {dir_path} со всем содержимым: {e}")
            return False, str(e)
        
    # удалить пустую папку
    try:
        if os.path.isdir(dir_path) and not os.listdir(dir_path):
            os.rmdir(dir_path)
            logger.debug(f"Удалена пустая папка: {dir_path}")
            return True , None
        
        else:
            logger.debug(f"Папка не пуста или не существует: {dir_path}")
            return False , None
        
    except OSError as e:
        logger.warning(f"Не удалось удалить папку {dir_path}: {e}")
        return False , str(e)

def schedule_deletion(
    path: str,
    remove_parent_if_empty: bool = False,
    force: bool = False,     
    session: Optional[Session] = None,
    logger: Optional[AppLogger] = None
) -> Tuple[bool, Optional[str]]:
    """
    Планирует удаление файла или папки после успешного коммита транзакции.

    Если передан `session`, удаление откладывается до вызова обработчика `after_commit`.
    Если `session` не передан или сессия неактивна, удаление выполняется немедленно
    (через `del_file_and_parent_dir`).

    Args:
        path: Путь к файлу или папке.
        remove_parent_if_empty: Если True и удаляется файл, то после успешного удаления
            файла родительская папка будет удалена, если она станет пустой.
        force: Если True и удаляется папка, удаляет её рекурсивно (даже непустую).
        session: Сессия SQLAlchemy (если указана, удаление откладывается).
        logger: Опциональный логгер.

    Returns:
        Tuple[bool, Optional[str]]: (успех, ошибка)
            При отложенном удалении всегда возвращает `(True, None)`.
            При немедленном удалении возвращает результат `del_file_and_parent_dir`.
    """

    if logger is None:
        logger = AppLogger.get_instance(
            name = 'file_deletions',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system',
        )

    if (
        (session is None) 
    ) or (
        (session is not None) and not session.is_active
    ):
        logger.warning("Сессия неактивна, удаление будет выполнено немедленно")
        return del_file_and_parent_dir(
            file_path = path, 
            remove_parent_if_empty = remove_parent_if_empty,
            force = force,    
            logger = logger
        )

    if not hasattr(session, '_pending_deletions'):
        session._pending_deletions = []

    session._pending_deletions.append({
        'path': path,
        'remove_parent_if_empty': remove_parent_if_empty,
        # 'is_directory': is_directory,
        'force': force,
    })

    logger.debug(f"Запланировано удаление: {path}")

    return True, None 
    
def del_file_and_parent_dir(
    file_path: str,
    remove_parent_if_empty: bool = False,
    force: bool = False,    
    logger: Optional[AppLogger] = None, 
) -> Tuple[bool, Optional[str]]:    
    """
    Немедленно удаляет файл , при необходимости, родительскую папку. Или просто указанную папку

    Алгоритм:
        1. Удаляет файл через `delete_file_safely`. или папку через 
        2. Если удаление файла прошло успешно и `remove_parent_if_empty == True`,
           пытается удалить родительскую папку через `delete_empty_directory(force=False)`.
        3. Если удаление файла завершилось ошибкой, родительская папка НЕ удаляется,
           и функция возвращает результат удаления файла.

    Args:
        file_path: Путь к файлу (не папке).
        remove_parent_if_empty: Если True, после успешного удаления файла
            попытаться удалить родительскую папку (только если она пуста).
        force: Параметр `force` передаётся в `delete_empty_directory`.
        logger: Опциональный логгер.

    Returns:
        Tuple[bool, Optional[str]]: (успех, ошибка) для последней выполненной операции.
            - Если `remove_parent_if_empty=False` – возвращает результат удаления файла.
            - Если `remove_parent_if_empty=True` и файл удалён успешно – возвращает
              результат удаления родительской папки.
            - Если при удалении файла произошла ошибка – возвращает ошибку файла.
    """

    if logger is None:
        logger = AppLogger.get_instance(
            name = 'file_deletions',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system',
        )
    
    if not file_path:
        logger.warning("Попытка запланировать удаление объекта по пустому пути, игнорируем")
        return False, None    

  
    if not os.path.exists(file_path):
        logger.warning(f"Попытка удалить несуществующий файл / папку: {file_path}")
        return False, None

    if_isfile = os.path.isfile(file_path) # проверяем файл ли это 
    if_isdir= os.path.isdir(file_path) # проверяем папка ли это ли это 

    if not if_isfile and not if_isdir:
        logger.warning(f"Попытка удалить не типичный объект: {file_path}")
        return False, None

    if if_isfile:
        #  удаляем немедленно файл, но с предупреждением
        success, error = delete_file_safely(file_path, logger=logger)
    elif if_isdir:
        #  удаляем немедленно папку, но с предупреждением
        success, error = delete_empty_directory(
            file_path,
            force = force,    
            logger=logger
        )
    else:        
        logger.warning(f"Попытка удалить не типичный объект: {file_path}")
        return False, None

    if (
        not remove_parent_if_empty
    # ) or ( # реакция должна быть только на ошибку
    #     not success
    ) or (
        error is not None
    ):
        return success, error
    
    # Удаляем родительскую папку, если она стала пустой
    parent_dir = os.path.dirname(file_path) 

    if not parent_dir:
        # Файл находится в корневой директории (без родителя)
        logger.debug("Файл в корне, родительская папка не удаляется")
        return True, None 
     
    return delete_empty_directory(
        parent_dir,
        force = force,    
        logger=logger
    )
    