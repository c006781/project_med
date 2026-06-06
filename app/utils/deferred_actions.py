# app/utils/deferred_actions.py
"""
Отложенные действия (обновления UI, вызовы функций) после коммита/отката транзакции.

Предоставляет механизм, аналогичный отложенному удалению файлов, для выполнения
произвольных функций после успешного коммита или отката SQLAlchemy транзакции.
Используется, например, для обновления связанных таблиц (родительских записей)
после сохранения дочерних черновиков (фото), чтобы избежать рассинхронизации.

Основные компоненты:
    - ActionType: перечисление типов отложенных действий (COMMIT, ROLLBACK).
    - ActionContext: контекст (сессия + тип действия).
    - add_deferred_action: добавление действия в очередь.
    - execute_actions: выполнение действий (с переносом в Qt-поток).

В database.py регистрируются обработчики after_commit / after_rollback,
которые извлекают накопленные действия и выполняют их.
"""

from typing import Callable, Optional, Tuple, List
from enum import Enum
import weakref

from app.utils.logger.logger import AppLogger

from PySide6.QtCore import QMetaObject, QTimer, Qt, Q_ARG
from sqlalchemy.orm import Session


class ActionType(Enum):
    """Тип отложенного действия: выполнить после коммита или после отката."""
    COMMIT = "commit"
    ROLLBACK = "rollback"


class ActionContext:
    """
    Контекст отложенного действия: сессия SQLAlchemy и тип (COMMIT/ROLLBACK).

    Используется для того, чтобы действие было выполнено только после
    соответствующего события транзакции.
    """

    __slots__ = ('session', 'action_type')

    @AppLogger.get_instance(
        name='ActionContext',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, session: Session, action_type: ActionType):
        """
        Инициализирует контекст.

        Args:
            session: Сессия SQLAlchemy, в рамках которой будет выполнено действие.
            action_type: Тип действия (ActionType.COMMIT или ActionType.ROLLBACK).
        """
        self.session = session
        self.action_type = action_type

    @AppLogger.get_instance(
        name='ActionContext',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __bool__(self) -> bool:
        """Возвращает True, если контекст задан и сессия активна."""
        return self.session is not None and self.action_type is not None


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def ensure_actions_dict(session: Session) -> None:
    """
    Гарантирует, что в сессии есть словарь _actions с ключами COMMIT и ROLLBACK.

    Args:
        session: Сессия SQLAlchemy.
    """
    if not hasattr(session, '_actions'):
        session._actions = {
            ActionType.COMMIT: [],
            ActionType.ROLLBACK: []
        }


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def add_deferred_action(
    ctx: Optional[ActionContext],
    func: Callable,
    args: Tuple = (),
    kwargs: Optional[dict] = None,
) -> None:
    """
    Добавляет действие в отложенное выполнение согласно контексту.

    Если ctx передан и активен, действие добавляется в список отложенных
    для соответствующего типа (COMMIT/ROLLBACK). Если ctx не передан или
    является ложным, действие выполняется немедленно (рекомендуется избегать).

    Args:
        ctx: Контекст (сессия + тип). Может быть None.
        func: Вызываемый объект (функция, метод, лямбда).
        args: Позиционные аргументы для func.
        kwargs: Именованные аргументы для func.
    """
    if not ctx:
        # Немедленное выполнение (для обратной совместимости)
        func(*args, **(kwargs or {}))
        return

    ensure_actions_dict(ctx.session)
    ctx.session._actions[ctx.action_type].append((func, args, kwargs or {}))
    # 0==0


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def get_actions_by_type(session: Session, atype: ActionType) -> List[Tuple[Callable, Tuple, dict]]:
    """
    Возвращает список отложенных действий для указанного типа.

    Args:
        session: Сессия SQLAlchemy.
        atype: Тип действия (COMMIT или ROLLBACK).

    Returns:
        Список кортежей (func, args, kwargs).
    """
    ensure_actions_dict(session)
    return session._actions.get(atype, [])


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def clear_actions_by_type(session: Session, atype: ActionType) -> None:
    """
    Очищает список отложенных действий для указанного типа.

    Args:
        session: Сессия SQLAlchemy.
        atype: Тип действия.
    """
    if hasattr(session, '_actions') and atype in session._actions:
        session._actions[atype].clear()


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def execute_actions(
    actions: List[Tuple[Callable, Tuple, dict]], 
    logger: Optional[AppLogger] = None
) -> None:
    """
    Выполняет список действий (функций с аргументами) в главном потоке Qt.

    Использует QMetaObject.invokeMethod для безопасного вызова в главном потоке.
    Ошибки отдельных действий логируются, но не прерывают выполнение остальных.

    Args:
        actions: Список кортежей (func, args, kwargs).
        logger: Опциональный логгер для записи ошибок.
    """
    if not actions:
        return

    for func, args, kwargs in actions:
        logg=logger or print
        # Обёртка для вызова в главном потоке
        # Создаём частичную функцию с фиксированными аргументами
        def wrapper(f=func, a=args, k=kwargs, logg=logg):
            try:
                f(*a, **k)

                logg.debug(
                    f"отложенного действия выполнено: {f.__name__} " 
                )
                # 0==0
            except Exception as e:
                if logg:
                    logg.exception(f"Ошибка при выполнении отложенного действия: {e}")

        # QMetaObject.invokeMethod(
        #     wrapper,
        #     Qt.QueuedConnection,
        #     Q_ARG(object, None)  # заглушка – метод invokeMethod требует хотя бы один аргумент
        # )
        QTimer.singleShot(0, wrapper)