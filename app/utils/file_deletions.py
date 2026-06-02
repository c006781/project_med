# app/utils/file_deletions.py
"""
Утилиты для безопасного удаления файлов и папок с поддержкой отложенного выполнения.
"""

import os
import shutil
from enum import Enum
from typing import Optional, Tuple, List

from app.utils.logger.logger import AppLogger

from sqlalchemy.orm import Session


class DeletionType(Enum):
    """
    Тип отложенного удаления.

    COMMIT   – удалить после успешного коммита транзакции.
    ROLLBACK – удалить при откате транзакции.
    """
    COMMIT = "commit"
    ROLLBACK = "rollback"

class DeletionContext:
    """
    Контекст отложенного удаления: объединяет сессию и тип удаления.

    Используется в _del_file и schedule_deletion для того, чтобы явно указать,
    при каком исходе транзакции (COMMIT или ROLLBACK) следует удалять файлы.
    Если передан None – удаление немедленное.

    Если передан в schedule_deletion, файлы будут удалены только после
    наступления соответствующего события (COMMIT или ROLLBACK).

    Пример:
        # Отложенное удаление после успешного коммита
        ctx = DeletionContext(session, DeletionType.COMMIT)

        # Отложенное удаление при откате
        ctx = DeletionContext(session, DeletionType.ROLLBACK)

        # Немедленное удаление
        ctx = None
    """
    __slots__ = ('session', 'deletion_type')

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(cls) -> AppLogger:
        try:
            return cls._logger
        except AttributeError as e:
            cls._logger = AppLogger.get_instance(
                name='api.DeletionContext',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return cls._logger

    @logger.setter
    def logger(cls, value):
        cls._logger = value

    @classmethod
    def create(cls, session, deletion_type):
        """
        Создаёт контекст отложенного удаления.

        **Назначение:**
            Удобная фабрика для создания `DeletionContext`. Если `session is None`,
            возвращает `None`, что сигнализирует о необходимости немедленного удаления.

        Args:
            session (Optional[Session]): Сессия SQLAlchemy (может быть None).
            deletion_type (DeletionType): Тип удаления (COMMIT или ROLLBACK).

        Returns:
            Optional[DeletionContext]: Контекст отложенного удаления или None,
                если сессия не передана.

        Пример:
            >>> ctx = DeletionContext.create(session, DeletionType.COMMIT)
            >>> if ctx:
            ...     # отложенное удаление
            ... else:
            ...     # немедленное удаление
        """

        if session is None:
            cls.logger.warning(
                "DeletionContext.create вызван без сессии – удаление файлов будет немедленным, "
                "атомарность не гарантирована"
            )
            return None
        return cls(session, deletion_type)

    def __init__(
        self,
        session: Session,
        deletion_type: 'DeletionType'
    ):
        self.session = session
        self.deletion_type = deletion_type

    def __bool__(self) -> bool:
        """Возвращает True, если контекст задан (отложенное удаление)."""
        return self.session is not None and self.deletion_type is not None

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def ensure_deletions_dict(session: Session) -> None:
    """
    Гарантирует, что в сессии есть словарь _deletions с ключами COMMIT и ROLLBACK.
    Для обратной совместимости также переносит старый список _pending_deletions в COMMIT.
    """
    if not hasattr(session, '_deletions'):
        session._deletions = {
            DeletionType.COMMIT: [],
            DeletionType.ROLLBACK: []
        }
        # Переносим старые записи из _pending_deletions (если есть)
        if hasattr(session, '_pending_deletions') and session._pending_deletions:
            session._deletions[DeletionType.COMMIT].extend(session._pending_deletions)
            session._pending_deletions = None

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def add_deferred_deletion(
    ctx: DeletionContext,
    path: str,
    remove_parent_if_empty: bool = False,
    force: bool = False,
) -> None:
    """
    Добавляет файл или папку в отложенное удаление согласно контексту.

    Args:
        ctx: Контекст удаления (сессия + тип). Если ctx ложный (None), ничего не делает.
        path: Путь к файлу или папке.
        remove_parent_if_empty: Удалить родительскую папку, если она станет пустой.
        force: Принудительное рекурсивное удаление (для папок).
    """
    if not ctx:
        return
    ensure_deletions_dict(ctx.session)
    ctx.session._deletions[ctx.deletion_type].append({
        'path': path,
        'remove_parent_if_empty': remove_parent_if_empty,
        'force': force,
    })


@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def get_deletions_by_type(session: Session, dt: DeletionType) -> List[dict]:
    """Возвращает список отложенных удалений для указанного типа."""
    ensure_deletions_dict(session)
    return session._deletions.get(dt, [])

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def clear_deletions_by_type(session: Session, dt: DeletionType) -> None:
    """Очищает список отложенных удалений для указанного типа."""
    if hasattr(session, '_deletions') and dt in session._deletions:
        session._deletions[dt].clear()

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
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
        return True, None

    try:
        os.remove(file_path)
        logger.debug(f"Удалён файл: {file_path}")
        return True, None
        
    except OSError as e:
        err_text = f"Не удалось удалить файл {file_path}: {e}"
        logger.warning(err_text)
        return False, err_text

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
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
            use_name_in_filename = False,  # 'system',
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
            err_text = f"Не удалось удалить {dir_path} со всем содержимым: {e}"
            logger.warning(err_text)
            return False, err_text
        
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
        err_text = f"Не удалось удалить папку {dir_path}: {e}"
        logger.warning(err_text)
        return False , err_text

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def schedule_deletion(
    path: str,
    remove_parent_if_empty: bool = False,
    force: bool = False,
    # session: Optional[Session] = None,
    ctx: Optional[DeletionContext] = None,
    logger: Optional[AppLogger] = None
) -> Tuple[bool, Optional[str]]:
    """
    Планирует удаление файла или папки после успешного коммита транзакции.

    Если передан `ctx` с активной сессией, удаление откладывается до соответствующего
    события (COMMIT или ROLLBACK). Файлы добавляются в список `session._deletions[deletion_type]`.

    Args:
        path: Путь к файлу или папке.
        remove_parent_if_empty: Если True и удаляется файл, то после успешного удаления
            файла родительская папка будет удалена, если она станет пустой.
        force: Если True и удаляется папка, удаляет её рекурсивно (даже непустую).
        ctx: Контекст отложенного удаления (сессия + тип). Если None – удаление немедленное.
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
    if ctx is None or not ctx.session.is_active:
        # Немедленное удаление
        return del_file_and_parent_dir(path, remove_parent_if_empty, force, logger)

    else:
        # Отложенное удаление
        add_deferred_deletion(ctx, path, remove_parent_if_empty, force)
        return True, None

    # if (
    #     (session is None)
    # ) or (
    #     (session is not None) and not session.is_active
    # ):
    #
    #     logger.warning("Сессия неактивна, удаление будет выполнено немедленно")
    #     return del_file_and_parent_dir(
    #         file_path = path,
    #         remove_parent_if_empty = remove_parent_if_empty,
    #         force = force,
    #         logger = logger
    #     )
    #
    # if not hasattr(session, '_pending_deletions'):
    #     session._pending_deletions = []
    #
    # session._pending_deletions.append({
    #     'path': path,
    #     'remove_parent_if_empty': remove_parent_if_empty,
    #     # 'is_directory': is_directory,
    #     'force': force,
    # })
    #
    # logger.debug(f"Запланировано удаление: {path}")
    #
    # return True, None

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
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
            use_name_in_filename = False,  # 'system',
        )
    if not file_path:
        logger.warning("Попытка запланировать удаление объекта по пустому пути, игнорируем")
        return False, None    

    if not os.path.exists(file_path):
        logger.warning(f"Попытка удалить несуществующий файл / папку: {file_path}")
        return False, None

    if_isfile = os.path.isfile(file_path)  # проверяем файл ли это
    if_isdir = os.path.isdir(file_path)  # проверяем папка ли это ли это

    if not if_isfile and not if_isdir:
        logger.warning(f"Попытка удалить не типичный объект: {file_path}")
        return False, None

    if if_isfile:
        #  удаляем немедленно файл, но с предупреждением
        success, error = delete_file_safely(
            file_path,
            logger=logger
        )
    elif if_isdir:
        #  удаляем немедленно папку, но с предупреждением
        success, error = delete_empty_directory(
            file_path,
            force = force,    
            logger = logger
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
    

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def resolve_photo_path(
    rel_path: Optional[str],
    temp_dir: Optional[str] = None,
    storage_path: Optional[str] = None,
) -> Optional[str]:
    """
    Преобразует относительный путь к фото в абсолютный.
    
    Алгоритм:
        1. Если rel_path пустой – вернуть None.
        2. Если rel_path – абсолютный путь и файл существует – вернуть его.
        3. Если передан temp_dir и файл существует в нём – вернуть полный путь.
        4. Если передан storage_path и файл существует в нём – вернуть полный путь.
        5. Иначе вернуть None.
    
    Args:
        rel_path: Относительный путь (или просто имя файла) или абсолютный путь.
        temp_dir: Временная папка черновика (может быть None).
        storage_path: Базовый путь к хранилищу фотографий (может быть None).
    
    Returns:
        Абсолютный путь к существующему файлу или None.
    """
    if not rel_path:
        return None
    
    if os.path.isabs(rel_path):
        return rel_path if os.path.exists(rel_path) else None
    
    # Проверяем временную папку
    if temp_dir:
        cand = os.path.join(temp_dir, rel_path)
        if os.path.exists(cand):
            return cand
    
    # Проверяем основное хранилище
    if storage_path:
        # Если rel_path уже содержит storage_path как префикс – не дублируем
        if rel_path.startswith(storage_path):
            cand = rel_path
        else:
            cand = os.path.join(storage_path, rel_path)
        if os.path.exists(cand):
            return cand
    
    return None