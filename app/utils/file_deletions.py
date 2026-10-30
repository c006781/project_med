# app/utils/file_deletions.py
"""
Утилиты для безопасного удаления файлов и папок с поддержкой отложенного выполнения.

Удаление выполняется сразу или откладывается до исхода транзакции SQLAlchemy: пути
копятся в ``session._deletions[DeletionType]``, обработчики ``after_commit`` /
``after_rollback`` (``app/database/database.py``) вызывают для них
`del_file_and_parent_dir`. Ещё здесь — копирование файла во временную папку черновика
(`copy_file_to_temp_dir`) и поиск файла фото (`resolve_photo_path`).

Ограничение: списки очищаются только своим событием — см. FD9 в IMPLEMENTATION.md.

Пример:
    >>> ctx = DeletionContext.create(session, DeletionType.COMMIT)
    >>> schedule_deletion('photos/app_1/a.png', remove_parent_if_empty=True, ctx=ctx)
    (True, None)
    >>> session.commit()  # after_commit удалит файл и пустую папку app_1
"""

import os
import shutil
from enum import Enum
from typing import Optional, Tuple, List
import uuid

from app.utils.logger.logger import AppLogger

from sqlalchemy.orm import Session


class DeletionType(Enum):
    """
    Тип отложенного удаления.

    COMMIT   – удалить после успешного коммита транзакции.
    ROLLBACK – удалить при откате транзакции.

    Пример:
        >>> DeletionType('rollback') is DeletionType.ROLLBACK
        True
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

    # Журнал класса (один на все контексты; в __slots__ экземпляра его нет)
    _class_logger: Optional[AppLogger] = None

    @classmethod
    def _get_logger(cls) -> AppLogger:
        """
        Журнал контекстов удаления (создаётся при первом обращении).

        Returns:
            AppLogger: Журнал ``api.DeletionContext``.

        Пример:
            >>> DeletionContext._get_logger().warning('удаление без сессии')
        """
        if cls._class_logger is None:
            cls._class_logger = AppLogger.get_instance(
                name='api.DeletionContext', # имя журнала
                enable_file_logging = 'user', # файл пользователя
                use_name_in_filename = False, # имя не в имени файла
            )
        return cls._class_logger

    @property
    def logger(self) -> AppLogger:
        """
        Журнал (общий для класса).

        Пример:
            >>> ctx.logger is DeletionContext._get_logger()
            True
        """
        return type(self)._get_logger()

    # @property
    # def logger(cls) -> AppLogger:
    #     try:
    #         return cls._logger
    #     except AttributeError as e:
    #         cls._logger = AppLogger.get_instance(
    #             name='api.DeletionContext',
    #             enable_file_logging = 'user',
    #             use_name_in_filename = False, # 'system'
    #         )
    #
    #     return cls._logger
    #
    # @logger.setter
    # def logger(cls, value):
    #     cls._logger = value
    # ↑ до rework-file-deletions (2026-10-21): свойство экземпляра вызывалось из метода
    #   класса (cls.logger → объект property: create(None, …) падал AttributeError вместо
    #   «удалить сразу»); у экземпляра _logger не записывался (__slots__) (FD1)

    @classmethod
    # def create(cls, session, deletion_type):
    # ↑ до 2026-10-25 (FD12): без аннотаций (полная типизация — правило проекта; формат
    #   skill п. 7).
    def create(
        cls,
        session       : Optional[Session],  # сессия (None — удалять сразу)
        deletion_type : 'DeletionType',     # после коммита или при откате
    ) -> Optional['DeletionContext']:
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
            cls._get_logger().warning(
                "DeletionContext.create вызван без сессии – удаление файлов будет немедленным, "
                "атомарность не гарантирована"
            )
            return None
        return cls(session, deletion_type)

    # def __init__(
    #     self,
    #     session: Session,
    #     deletion_type: 'DeletionType'
    # ):
    # ↑ до 2026-10-25 (FD12): без аннотации возврата и докстринга (правило проекта;
    #   формат skill п. 7).
    def __init__(
        self,
        session       : Optional[Session],         # сессия SQLAlchemy (None — контекст ложный)
        deletion_type : Optional['DeletionType'],  # после коммита или при откате
    ) -> None:
        """
        Запоминает сессию и тип удаления.

        Args:
            session: Сессия, к исходу транзакции которой привязано удаление.
            deletion_type: Тип удаления (COMMIT или ROLLBACK).

        Пример:
            >>> DeletionContext(session, DeletionType.COMMIT).deletion_type
            <DeletionType.COMMIT: 'commit'>
        """
        self.session = session
        self.deletion_type = deletion_type

    def __bool__(self) -> bool:
        """
        Возвращает True, если контекст задан (отложенное удаление).

        Активность сессии здесь не проверяется — это делает `schedule_deletion`.

        Returns:
            bool: ``True`` — заданы и сессия, и тип.

        Пример:
            >>> bool(DeletionContext(None, DeletionType.COMMIT))
            False
        """
        return self.session is not None and self.deletion_type is not None

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
# def ensure_deletions_dict(session: Session) -> None:
# ↑ до 2026-10-25 (FD12): сигнатура без комментария к параметру (формат skill п. 7).
def ensure_deletions_dict(
    session : Session,  # сессия, к которой привязаны списки удалений
) -> None:
    """
    Гарантирует, что в сессии есть словарь _deletions с ключами COMMIT и ROLLBACK.

    Для обратной совместимости также переносит старый список _pending_deletions в COMMIT.

    Args:
        session: Сессия SQLAlchemy (или любой объект с атрибутами).

    Пример:
        >>> ensure_deletions_dict(session)
        >>> session._deletions
        {<DeletionType.COMMIT: 'commit'>: [], <DeletionType.ROLLBACK: 'rollback'>: []}
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
# def add_deferred_deletion(
#     ctx: DeletionContext,
#     path: str,
#     remove_parent_if_empty: bool = False,
#     force: bool = False,
# ) -> None:
# ↑ до 2026-10-25 (FD12): сигнатура без комментариев к параметрам (формат skill п. 7).
def add_deferred_deletion(
    ctx                    : Optional[DeletionContext],  # контекст (ложный — ничего не делать)
    path                   : str,                        # файл или папка
    remove_parent_if_empty : bool = False,               # затем удалить родителя, если пуст
    force                  : bool = False,               # папку — рекурсивно
) -> None:
    """
    Добавляет файл или папку в отложенное удаление согласно контексту.

    Args:
        ctx: Контекст удаления (сессия + тип). Если ctx ложный (None), ничего не делает.
        path: Путь к файлу или папке.
        remove_parent_if_empty: Удалить родительскую папку, если она станет пустой.
        force: Принудительное рекурсивное удаление (для папок).

    Пример:
        >>> add_deferred_deletion(DeletionContext(session, DeletionType.COMMIT), 'a.png')
        >>> session._deletions[DeletionType.COMMIT]
        [{'path': 'a.png', 'remove_parent_if_empty': False, 'force': False}]
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
# def get_deletions_by_type(session: Session, dt: DeletionType) -> List[dict]:
# ↑ до 2026-10-25 (FD12): сигнатура без комментариев к параметрам (формат skill п. 7).
def get_deletions_by_type(
    session : Session,       # сессия со списками удалений
    dt      : DeletionType,  # какой список
) -> List[dict]:
    """
    Возвращает список отложенных удалений для указанного типа.

    Возвращается сам список сессии (не копия).

    Args:
        session: Сессия SQLAlchemy.
        dt: Тип удаления.

    Returns:
        List[dict]: Записи ``{'path', 'remove_parent_if_empty', 'force'}``.

    Пример:
        >>> get_deletions_by_type(session, DeletionType.ROLLBACK)
        []
    """
    ensure_deletions_dict(session)
    return session._deletions.get(dt, [])

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
# def clear_deletions_by_type(session: Session, dt: DeletionType) -> None:
# ↑ до 2026-10-25 (FD12): сигнатура без комментариев к параметрам (формат skill п. 7).
def clear_deletions_by_type(
    session : Session,       # сессия со списками удалений
    dt      : DeletionType,  # какой список очистить
) -> None:
    """
    Очищает список отложенных удалений для указанного типа.

    Args:
        session: Сессия SQLAlchemy (без списков — ничего не делает).
        dt: Тип удаления.

    Пример:
        >>> clear_deletions_by_type(session, DeletionType.COMMIT)
        >>> get_deletions_by_type(session, DeletionType.COMMIT)
        []
    """
    if hasattr(session, '_deletions') and dt in session._deletions:
        session._deletions[dt].clear()

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
# def delete_file_safely(
#     file_path: str,
#     logger: Optional[AppLogger] = None
# ) -> Tuple[bool, Optional[str]]:
# ↑ до 2026-10-25 (FD12): сигнатура без комментариев к параметрам (формат skill п. 7).
def delete_file_safely(
    file_path : str,                        # путь к файлу
    logger    : Optional[AppLogger] = None, # журнал (None — журнал модуля)
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
            - `(False, str)` – ошибка при удалении (файл заблокирован, нет прав): текст ошибки.

    Пример:
        >>> delete_file_safely('temp/a.png')
        (True, None)
        >>> delete_file_safely('нет.png')  # нечего удалять — тоже успех
        (True, None)
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
# def delete_empty_directory(
#         dir_path: str,
#         force: bool = False,
#         logger: Optional[AppLogger] = None,
#     ) -> Tuple[bool, Optional[str]]:
# ↑ до 2026-10-25 (FD12): сигнатура без комментариев к параметрам (формат skill п. 7).
def delete_empty_directory(
    dir_path : str,                        # папка
    force    : bool = False,               # True — со всем содержимым
    logger   : Optional[AppLogger] = None, # журнал (None — журнал модуля)
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
            - `(True, None)` – директории нет (удалять нечего).
            - `(False, None)` – директория не пуста (при force=False).
            - `(False, str)` – ошибка доступа/удаления: текст ошибки.
            - `(True, None)` – пустой путь (предупреждение в журнал).

    Пример:
        >>> delete_empty_directory('temp/draft_1')  # не пуста
        (False, None)
        >>> delete_empty_directory('temp/draft_1', force=True)
        (True, None)
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
# def schedule_deletion(
#     path: str,
#     remove_parent_if_empty: bool = False,
#     force: bool = False,
#     # session: Optional[Session] = None,
#     ctx: Optional[DeletionContext] = None,
#     logger: Optional[AppLogger] = None
# ) -> Tuple[bool, Optional[str]]:
# ↑ до 2026-10-25 (FD12): сигнатура без комментариев к параметрам (формат skill п. 7).
def schedule_deletion(
    path                   : str,                               # файл или папка
    remove_parent_if_empty : bool = False,                      # затем удалить родителя, если пуст
    force                  : bool = False,                      # папку — рекурсивно (только сам объект)
    # session: Optional[Session] = None,
    ctx                    : Optional[DeletionContext] = None,  # когда удалять (None — сразу)
    logger                 : Optional[AppLogger] = None,        # журнал (None — журнал модуля)
) -> Tuple[bool, Optional[str]]:
    """
    Планирует удаление файла или папки после исхода транзакции (или удаляет сразу).

    Если передан ``ctx`` с активной сессией, удаление откладывается до соответствующего
    события (COMMIT или ROLLBACK): запись добавляется в ``session._deletions[deletion_type]``.

    Без отложенного удаления:
        - ``ctx is None`` — удаляется сразу;
        - сессия неактивна (``is_active=False``: транзакция уже упала, её ждёт только
          откат) и контекст COMMIT — **ничего не удаляется**: коммита не будет, файл
          остаётся, в журнал — предупреждение (FD10, решение владельца 2026-10-26, В-4);
          файлы без ссылок в БД находит сверка (Ф1.6.10г);
        - сессия неактивна и контекст ROLLBACK — сразу (откат будет);
        - контекст ROLLBACK без сессии — ничего не удаляется (откатывать нечего, DATA6),
          контекст COMMIT без сессии — сразу.

    Args:
        path                   : (str) Путь к файлу или папке.
        remove_parent_if_empty : (bool) Удаляется файл — затем удалить его папку, если
                                 она стала пустой.
        force                  : (bool) Удаляется папка — рекурсивно (даже непустую).
        ctx                    : (DeletionContext/None) Сессия и событие; None — удалить
                                 сразу.
        logger                 : (AppLogger/None) Журнал; None — журнал модуля.

    Returns:
        (Tuple[bool, Optional[str]]) ``(успех, текст ошибки)``: при отложенном удалении и
        при оставленном файле (FD10) — ``(True, None)``; при немедленном — результат
        ``del_file_and_parent_dir``.

    Example:
        >>> schedule_deletion(
        ...     'temp/a.png',                                       # файл
        ...     ctx   =   DeletionContext(session, DeletionType.COMMIT),  # после коммита
        ... )
        (True, None)
        >>> schedule_deletion(
        ...     'temp/b.png',   # без контекста — сразу
        ... )
        (True, None)
    """
    # ↑ до 2026-10-31 (FD10): неактивная сессия с контекстом COMMIT — удаление сразу, хотя
    #   коммита не будет; описание — в формате «Пример:».

    if logger is None:
        logger = AppLogger.get_instance(
            name = 'file_deletions',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'system',
        )
    # DATA6 (2026-10-16): контекст без сессии раньше падал на ctx.session.is_active.
    # Удаление «при откате» без сессии бессмысленно (откатывать нечего) — НЕ удаляем:
    # иначе только что скопированный файл удалился бы сразу. «После коммита» — сразу.
    if ctx is not None and ctx.session is None:
        if ctx.deletion_type == DeletionType.ROLLBACK:
            return True, None
        ctx = None
    # if ctx is None or not ctx.session.is_active:
    #     # Немедленное удаление
    #     return del_file_and_parent_dir(path, remove_parent_if_empty, force, logger)
    #
    # else:
    #     # Отложенное удаление
    #     add_deferred_deletion(ctx, path, remove_parent_if_empty, force)
    #     return True, None
    # ↑ до 2026-10-31 (FD10): «после коммита» при неактивной сессии удалялось сразу —
    #   транзакция уже упала, коммита не будет, а файл (фото записи) пропадал.
    if ctx is not None and not ctx.session.is_active:
        if ctx.deletion_type == DeletionType.COMMIT: # коммита не будет — файл остаётся
            logger.warning(
                f"Удаление после коммита не выполнено — транзакция с ошибкой, коммита не "
                f"будет; файл остаётся: {path}"
            )
            return True, None
        ctx = None  # откат будет — удалить сразу

    if ctx is None:
        # Немедленное удаление
        return del_file_and_parent_dir(
            path,                     # что удалить
            remove_parent_if_empty,   # папку, если опустела
            force,                    # папку — рекурсивно
            logger,                   # журнал
        )

    # Отложенное удаление
    add_deferred_deletion(
        ctx,                      # сессия и событие
        path,                     # что удалить
        remove_parent_if_empty,   # папку, если опустела
        force,                    # папку — рекурсивно
    )
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
# def del_file_and_parent_dir(
#     file_path: str,
#     remove_parent_if_empty: bool = False,
#     force: bool = False,
#     logger: Optional[AppLogger] = None,
# ) -> Tuple[bool, Optional[str]]:
# ↑ до 2026-10-25 (FD7): сигнатура без комментариев к параметрам (формат skill п. 7 —
#   правимая функция приводится к нему).
def del_file_and_parent_dir(
    file_path              : str,                        # путь к файлу или папке
    remove_parent_if_empty : bool = False,               # затем удалить родителя, если он пуст
    force                  : bool = False,               # папку — рекурсивно (только сам объект)
    logger                 : Optional[AppLogger] = None, # журнал (None — журнал модуля)
) -> Tuple[bool, Optional[str]]:
    """
    Немедленно удаляет файл или папку и, при необходимости, ставшую пустой родительскую папку.

    Алгоритм:
        1. Пустой путь или объекта нет — ``(False, None)`` с предупреждением (вызывающие
           опираются на это: «удалять было нечего»).
        2. Файл удаляется через `delete_file_safely`, папка — через `delete_empty_directory`
           (``force=True`` — со всем содержимым, иначе только пустая).
        3. Если удаление прошло без ошибки и `remove_parent_if_empty == True`,
           пытается удалить родительскую папку через `delete_empty_directory(force=False)` —
           **всегда только пустую**, независимо от `force` (FD7).
        4. Если удаление объекта завершилось ошибкой, родительская папка НЕ удаляется,
           и функция возвращает результат удаления объекта.

    Args:
        file_path: Путь к файлу или папке.
        remove_parent_if_empty: Если True, после успешного удаления
            попытаться удалить родительскую папку (только если она пуста).
        force: Для папки — удалить рекурсивно (со всем содержимым). На родительскую
            папку не действует.
        logger: Опциональный логгер.

    Returns:
        Tuple[bool, Optional[str]]: (успех, ошибка) для последней выполненной операции.
            - Если `remove_parent_if_empty=False` – возвращает результат удаления объекта.
            - Если `remove_parent_if_empty=True` и объект удалён успешно – возвращает
              результат удаления родительской папки (``(False, None)`` — родитель не пуст
              и оставлен).
            - Если при удалении объекта произошла ошибка – возвращает эту ошибку.

    Пример:
        >>> del_file_and_parent_dir('temp/draft_1/a.png', remove_parent_if_empty=True)
        (True, None)
        >>> del_file_and_parent_dir('temp/draft_2', force=True)  # папка со всем содержимым
        (True, None)
        >>> del_file_and_parent_dir('нет.png')  # объекта нет
        (False, None)
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

    # return delete_empty_directory(
    #     parent_dir,
    #     force = force,
    #     logger=logger
    # )
    # ↑ до 2026-10-25 (FD7): родитель удалялся с force=force — при force=True (папка
    #   черновика «со всем содержимым») рекурсивно, вместе с соседними файлами и папками,
    #   хотя remove_parent_if_empty обещает «только если стала пустой». force относится
    #   только к самому удаляемому объекту.
    return delete_empty_directory(
        parent_dir,       # родительская папка
        force  = False,   # только пустую (force — для самого объекта, не для родителя)
        logger = logger,  # журнал вызывающего
    )
    

@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
# def resolve_photo_path(
#     rel_path: Optional[str],
#     temp_dir: Optional[str] = None,
#     storage_path: Optional[str] = None,
# ) -> Optional[str]:
# ↑ до 2026-10-25 (FD-W1): сигнатура без комментариев к параметрам (формат skill п. 7 —
#   правимая функция приводится к нему).
def resolve_photo_path(
    rel_path     : Optional[str],         # относительный путь (или имя файла) или абсолютный путь
    temp_dir     : Optional[str] = None,  # временная папка черновика (None — не искать в ней)
    storage_path : Optional[str] = None,  # папка хранилища фото (None — не искать в ней)
) -> Optional[str]:
    """
    Преобразует путь к фото в абсолютный путь к существующему файлу.

    Алгоритм:
        1. Если rel_path пустой – вернуть None.
        2. Если rel_path – абсолютный путь и файл существует – вернуть его.
        3. Если передан temp_dir и файл существует в нём – вернуть полный путь.
        4. Если передан storage_path: путь, уже лежащий внутри хранилища (по частям пути,
           ``_is_inside_dir``; на Windows без учёта регистра и вида косой), — как есть, если
           файл существует; иначе — ``storage_path/rel_path``, если файл существует.
           (До FD11 / И-10 — строковым префиксом: ``./photos2/…`` считался лежащим в
           ``./photos``.)
        5. Иначе вернуть None.

    Возвращаемый путь нормализован (``os.path.normpath``): на Windows разделители — ``\\``,
    даже если в БД путь записан через ``/``. Иначе один файл получал два написания
    (``…\\photos\\app_1/a.png`` и ``…\\photos\\app_1\\a.png``), и кэш миниатюр по пути
    (``ImageThumbnailDelegate``) держал и загружал его дважды.

    Args:
        rel_path: Относительный путь (или просто имя файла) или абсолютный путь.
        temp_dir: Временная папка черновика (может быть None).
        storage_path: Базовый путь к хранилищу фотографий (может быть None).

    Returns:
        Нормализованный абсолютный путь к существующему файлу или None.

    Пример:
        >>> resolve_photo_path('app_1/a.png', storage_path='C:/data/photos')  # файл есть
        'C:\\\\data\\\\photos\\\\app_1\\\\a.png'
        >>> resolve_photo_path('нет.png', storage_path='C:/data/photos') is None
        True
    """
    if not rel_path:
        return None

    # Абсолютный путь — как есть (если файл существует)
    if os.path.isabs(rel_path):
        # return rel_path if os.path.exists(rel_path) else None
        # ↑ до 2026-10-25 (FD-W1): путь возвращался без нормализации — на Windows один файл
        #   имел два написания (`/` и `\`), сравнение путей и кэш миниатюр их различали.
        return os.path.normpath(rel_path) if os.path.exists(rel_path) else None

    # Проверяем временную папку
    if temp_dir:
        cand = os.path.join(temp_dir, rel_path)
        if os.path.exists(cand):
            # return cand
            # ↑ до 2026-10-25 (FD-W1): без нормализации (см. выше).
            return os.path.normpath(cand)

    # Проверяем основное хранилище
    if storage_path:
        # # Если rel_path уже содержит storage_path как префикс – не дублируем
        # if rel_path.startswith(storage_path):
        #     cand = rel_path
        # else:
        #     cand = os.path.join(storage_path, rel_path)
        # if os.path.exists(cand):
        #     # return cand
        #     # ↑ до 2026-10-25 (FD-W1): без нормализации (см. выше).
        #     return os.path.normpath(cand)
        # ↑ до 2026-10-25 (FD11, И-10): «путь уже в хранилище» — строковым префиксом:
        #   './photos2/a.png' считался лежащим в './photos' (выдавался файл соседней папки),
        #   а на Windows './Photos' и '.\photos\…' — нет (другой регистр / разделитель:
        #   путь дублировался и фото не находилось).
        candidates = []
        # Путь уже внутри хранилища (по частям пути) — не дублируем
        if _is_inside_dir(rel_path, storage_path):
            candidates.append(rel_path)
        # Внутри хранилища — всегда (и запасным вариантом: внутри хранилища может быть
        # подпапка с тем же именем, раньше для такого пути искалось только здесь)
        candidates.append(
            os.path.join(storage_path, rel_path),
        )
        for cand in candidates:
            if os.path.exists(cand):
                return os.path.normpath(cand)

    return None


def _is_inside_dir(
    path : str,  # проверяемый путь (относительный — от рабочей папки)
    base : str,  # папка (относительная — от рабочей папки)
) -> bool:
    """
    Лежит ли путь внутри папки (или совпадает с ней) — по частям пути, а не префиксом строки.

    Оба пути приводятся к абсолютным (``abspath`` — от рабочей папки) и к одному регистру и
    разделителю (``normcase``: на Windows — нижний регистр и ``\\``, на Linux — без
    изменений), затем сравниваются через ``os.path.commonpath``. Пути на разных дисках
    Windows (``commonpath`` бросает ``ValueError``) — «не внутри».

    Args:
        path: Проверяемый путь.
        base: Папка.

    Returns:
        bool: ``True`` — ``path`` внутри ``base`` или совпадает с ней.

    Пример:
        >>> _is_inside_dir('./photos/app_1/a.png', './photos')
        True
        >>> _is_inside_dir('./photos2/a.png', './photos')  # префикс строки, но другая папка
        False
        >>> _is_inside_dir('photos/a.png', 'D:/photos')  # Windows, рабочая папка на C:
        False
    """
    abs_path = os.path.normcase(
        os.path.abspath(path),
    )
    abs_base = os.path.normcase(
        os.path.abspath(base),
    )
    try:
        common = os.path.commonpath([abs_path, abs_base])
    except ValueError:
        # Разные диски Windows (или смесь абсолютного и относительного) — не внутри
        return False
    return common == abs_base



@AppLogger.get_instance(
    name='file_deletions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
# def copy_file_to_temp_dir(
#     source_path: str,
#     target_dir: str,
#     remove_parent_if_empty: bool = False,
#     unique_name: Optional[str] = None,
#     logger: Optional[AppLogger] = None,
#     delete_on_error: bool = True,
#     ctx: Optional[DeletionContext] = None
# ) -> str:
# ↑ до 2026-10-25 (FD8): сигнатура без комментариев к параметрам (формат skill п. 7 —
#   правимая функция приводится к нему).
def copy_file_to_temp_dir(
    source_path            : str,                             # исходный файл
    target_dir             : str,                             # целевая папка (создаётся, если нет)
    remove_parent_if_empty : bool = False,                    # при ошибке удалить папку, если пуста
    unique_name            : Optional[str] = None,            # имя копии (None — UUID + расширение)
    logger                 : Optional[AppLogger] = None,      # журнал (None — журнал модуля)
    delete_on_error        : bool = True,                     # при ошибке убрать недокопированное
    ctx                    : Optional[DeletionContext] = None, # когда убирать (None — сразу)
) -> str:
    """
    Копирует файл в указанную папку (обычно временную) с возможностью генерации уникального имени.

    При ошибке копирования (``delete_on_error=True``) удаляет недокопированный файл, а при
    ``remove_parent_if_empty=True`` — и целевую папку, если она пуста (в том числе только что
    созданную этой функцией, FD8). Удаление — через `schedule_deletion`: с `ctx` —
    отложенное до COMMIT/ROLLBACK сессии, без него — сразу.

    Args:
        source_path: Абсолютный путь к исходному файлу.
        target_dir: Целевая папка (должна существовать или будет создана).
        remove_parent_if_empty: При ошибке копирования удалить целевую папку, если она пуста.
        unique_name: Желаемое имя файла в целевой папке. Если None, генерируется UUID + расширение.
        logger: Опциональный логгер для записи ошибок.
        delete_on_error: Если True, при ошибке копирования удаляет целевой файл (и папку —
            см. `remove_parent_if_empty`).
        ctx: Контекст отложенного удаления для уборки при ошибке (None — немедленно).

    Returns:
        str: Имя скопированного файла в `target_dir` (без папки).

    Raises:
        RuntimeError: Не задана `target_dir`.
        OSError: Копирование не удалось (исключение пробрасывается после уборки).

    Пример:
        >>> name = copy_file_to_temp_dir('C:/in/фото.jpg', 'C:/temp/draft_1')
        >>> name  # UUID + расширение
        '3f2b9c0e8a7d4e1f9b6c5a4d3e2f1a0b.jpg'
        >>> copy_file_to_temp_dir('C:/in/фото.jpg', 'C:/temp/draft_1', unique_name='a.jpg')
        'a.jpg'
    """
    if logger is None:
        logger = AppLogger.get_instance(
            name = 'file_deletions',
            # share_file_with = 'system',
            enable_file_logging = 'user',
            use_name_in_filename = False,  # 'system',
        )

    if not target_dir:
        raise RuntimeError(
            "Для копирования файла необходима папка (target_dir). "
        )

    # Папка создаётся, если её нет (как обещает описание; раньше — FileNotFoundError, FD6)
    os.makedirs(target_dir, exist_ok=True)

    if unique_name is None:
        ext = os.path.splitext(source_path)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"

    dest_path = os.path.join(target_dir, unique_name)

    try:
        shutil.copy2(source_path, dest_path)
        return unique_name  # возвращаем только имя файла
    
    except Exception as e:
        if delete_on_error:
            # if delete_on_error:
            #     schedule_deletion(
            #         path=dest_path or target_dir,
            #         ctx=ctx,
            #         remove_parent_if_empty=(dest_path is not None) and remove_parent_if_empty ,
            #         force=False,
            #         logger=logger
            #     )
            # ↑ до 2026-10-25 (FD8): если копия не успела появиться (нет исходного файла,
            #   нет прав), del_file_and_parent_dir выходил на «объекта нет» и до родителя не
            #   доходил — созданная выше пустая папка оставалась, хотя remove_parent_if_empty
            #   обещает её убрать. Теперь: копия есть — удалить её (с родителем, если пуст);
            #   копии нет — удалить саму папку, если она пуста.
            if os.path.exists(dest_path):
                schedule_deletion(
                    path                   = dest_path,              # недокопированный файл
                    remove_parent_if_empty = remove_parent_if_empty, # и папку, если пуста
                    force                  = False,                  # файл — не рекурсивно
                    ctx                    = ctx,                    # когда удалять
                    logger                 = logger,                 # журнал
                )
            elif remove_parent_if_empty:
                schedule_deletion(
                    path   = target_dir,  # папка, в которую копировали
                    force  = False,       # только пустую
                    ctx    = ctx,         # когда удалять
                    logger = logger,      # журнал
                )

        logger.exception(f"Ошибка копирования файла {source_path} в {dest_path}: {e}")
        raise