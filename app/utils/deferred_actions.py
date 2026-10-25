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

Ограничения:
    - Список действий хранится на объекте сессии и очищается только своим событием:
      действия COMMIT из откатившейся транзакции остаются до следующего коммита той же
      сессии (``scoped_session`` — одна сессия на поток), см. DA5 в IMPLEMENTATION.md.
    - С приложением Qt действие ставится ``QTimer.singleShot(0, …)`` в цикл событий
      **вызывающего потока**: коммит из потока без цикла событий действие не выполнит.

Пример:
    >>> ctx = ActionContext(session, ActionType.COMMIT)
    >>> add_deferred_action(ctx, page.refresh, (entity_id,))
    >>> session.commit()  # обработчик after_commit вызовет page.refresh(entity_id)
"""

from typing import Callable, Optional, Tuple, List
from enum import Enum
import weakref  # не используется (остался от прежней версии; правило проекта — не удалять, DA4)

from app.utils.logger.logger import AppLogger

# QMetaObject, Qt, Q_ARG не используются — остались от вызова через
# QMetaObject.invokeMethod (закомментирован ниже); правило проекта — не удалять (DA4)
from PySide6.QtCore import QMetaObject, QTimer, Qt, Q_ARG
from PySide6.QtCore import QCoreApplication # есть ли цикл событий (DA3)
from sqlalchemy.orm import Session


class ActionType(Enum):
    """
    Тип отложенного действия: выполнить после коммита или после отката.

    Пример:
        >>> ActionType('commit') is ActionType.COMMIT
        True
    """
    COMMIT = "commit"
    ROLLBACK = "rollback"


class ActionContext:
    """
    Контекст отложенного действия: сессия SQLAlchemy и тип (COMMIT/ROLLBACK).

    Используется для того, чтобы действие было выполнено только после
    соответствующего события транзакции.

    Пример:
        >>> ctx = ActionContext(session, ActionType.COMMIT)
        >>> bool(ctx)
        True
        >>> bool(ActionContext(None, ActionType.COMMIT))  # без сессии — «выполнить сразу»
        False
    """

    __slots__ = ('session', 'action_type')

    @AppLogger.get_instance(
        name='ActionContext',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def __init__(self, session: Session, action_type: ActionType):
    # ↑ до 2026-10-25 (DA4): сигнатура без комментариев и аннотации возврата (формат
    #   skill п. 7 — правимая функция приводится к нему).
    def __init__(
        self,
        session     : Optional[Session],     # сессия SQLAlchemy (None — контекст ложный)
        action_type : Optional[ActionType],  # после коммита или после отката
    ) -> None:
        """
        Инициализирует контекст.

        Args:
            session: Сессия SQLAlchemy, в рамках которой будет выполнено действие.
            action_type: Тип действия (ActionType.COMMIT или ActionType.ROLLBACK).

        Пример:
            >>> ActionContext(session, ActionType.ROLLBACK).action_type
            <ActionType.ROLLBACK: 'rollback'>
        """
        self.session = session
        self.action_type = action_type

    @AppLogger.get_instance(
        name='ActionContext',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __bool__(self) -> bool:
        """
        Истинен, если заданы и сессия, и тип действия.

        Активность сессии (``is_active``) **не проверяется** (раньше описание обещало
        это — DA4): с неактивной сессией действие тоже ставится в очередь.

        Returns:
            bool: ``True`` — действие откладывается, ``False`` — выполняется сразу.

        Пример:
            >>> bool(ActionContext(session, None))
            False
        """
        return self.session is not None and self.action_type is not None


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def ensure_actions_dict(
    session : Session,  # сессия, к которой привязаны списки действий
) -> None:
    """
    Гарантирует, что в сессии есть словарь _actions с ключами COMMIT и ROLLBACK.

    Args:
        session: Сессия SQLAlchemy.

    Пример:
        >>> ensure_actions_dict(session)
        >>> session._actions
        {<ActionType.COMMIT: 'commit'>: [], <ActionType.ROLLBACK: 'rollback'>: []}
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
    ctx    : Optional[ActionContext],  # контекст (None / ложный — выполнить сразу)
    func   : Callable,                 # действие
    args   : Tuple = (),               # позиционные аргументы действия
    kwargs : Optional[dict] = None,    # именованные аргументы действия
) -> None:
    """
    Добавляет действие в отложенное выполнение согласно контексту.

    Если ctx истинен (заданы сессия и тип; активность сессии не проверяется), действие
    добавляется в список отложенных для соответствующего типа (COMMIT/ROLLBACK). Если ctx
    не передан или ложный, действие выполняется немедленно и синхронно (рекомендуется
    избегать); его исключение пробрасывается вызывающему.

    Args:
        ctx: Контекст (сессия + тип). Может быть None.
        func: Вызываемый объект (функция, метод, лямбда).
        args: Позиционные аргументы для func.
        kwargs: Именованные аргументы для func.

    Пример:
        >>> add_deferred_action(ActionContext(session, ActionType.COMMIT), print, ('готово',))
        >>> add_deferred_action(None, print, ('сразу',))
        сразу
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
def get_actions_by_type(
    session : Session,     # сессия со списками действий
    atype   : ActionType,  # какой список
) -> List[Tuple[Callable, Tuple, dict]]:
    """
    Возвращает список отложенных действий для указанного типа.

    Возвращается сам список сессии (не копия): изменения в нём видны сессии.

    Args:
        session: Сессия SQLAlchemy.
        atype: Тип действия (COMMIT или ROLLBACK).

    Returns:
        Список кортежей (func, args, kwargs).

    Пример:
        >>> add_deferred_action(ActionContext(session, ActionType.COMMIT), print, (1,))
        >>> get_actions_by_type(session, ActionType.COMMIT)
        [(<built-in function print>, (1,), {})]
    """
    ensure_actions_dict(session)
    return session._actions.get(atype, [])


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def clear_actions_by_type(
    session : Session,     # сессия со списками действий
    atype   : ActionType,  # какой список очистить
) -> None:
    """
    Очищает список отложенных действий для указанного типа.

    Args:
        session: Сессия SQLAlchemy.
        atype: Тип действия.

    Пример:
        >>> clear_actions_by_type(session, ActionType.COMMIT)
        >>> get_actions_by_type(session, ActionType.COMMIT)
        []
    """
    if hasattr(session, '_actions') and atype in session._actions:
        session._actions[atype].clear()


def action_name(
    func: Callable, # действие (функция, метод, partial, объект с __call__)
) -> str:
    """
    Имя действия для журнала (у partial и объектов нет ``__name__``).

    Args:
        func: Действие.

    Returns:
        str: ``__qualname__``, ``__name__`` или ``repr``.

    Пример:
        >>> import functools
        >>> action_name(functools.partial(print, 1)).startswith('functools.partial')
        True
        >>> action_name(len)
        'len'
    """
    return getattr(func, '__qualname__', None) or getattr(func, '__name__', None) or repr(func)


@AppLogger.get_instance(
    name='deferred_actions.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def execute_actions(
    actions : List[Tuple[Callable, Tuple, dict]], # действия (func, args, kwargs)
    logger  : Optional[AppLogger] = None,         # журнал (None — журнал модуля)
) -> None:
    """
    Выполняет список действий (функций с аргументами) в цикле событий Qt.

    Есть приложение Qt (``QCoreApplication.instance()``) — каждое действие ставится
    ``QTimer.singleShot(0, …)`` в цикл событий вызывающего потока и выполняется после
    возврата в цикл (не сразу); приложения нет (командная строка, тесты) — сразу (DA3).
    Ошибки отдельных действий логируются, но не прерывают выполнение остальных.
    (Описание раньше называло ``QMetaObject.invokeMethod`` — он закомментирован, DA4.)

    ВАЖНО: из-за асинхронного вызова через QTimer.singleShot необходимо фиксировать
    аргументы замыкания с помощью параметров по умолчанию (см. реализацию), иначе
    все вызовы получат последние значения из цикла.

    Args:
        actions: Список кортежей (func, args, kwargs).
        logger: Опциональный логгер для записи ошибок.

    Пример:
        >>> execute_actions([(print, ('a',), {}), (print, ('b',), {'end': '!\\n'})])
        a
        b!
    """
    if not actions:
        return

    if logger is None:
        logger = AppLogger.get_instance(
            name='deferred_actions.py', # журнал модуля
            enable_file_logging='user', # файл пользователя
            use_name_in_filename=False, # имя не в имени файла
        )
    # Без приложения Qt (командная строка, тесты) цикла событий нет — QTimer не сработает
    run_now = QCoreApplication.instance() is None

    for func, args, kwargs in actions:
        # def wrapper(f=func, a=args, k=kwargs, logg=logger):
        # ↑ до 2026-10-25 (DA4): без аннотаций (полная типизация — правило проекта)
        def wrapper(
            f    : Callable = func,     # действие (зафиксировано значением по умолчанию)
            a    : Tuple = args,        # его позиционные аргументы
            k    : dict = kwargs,       # его именованные аргументы
            logg : AppLogger = logger,  # журнал
        ) -> None:
            """Выполняет одно действие; ошибку пишет в журнал, не пробрасывая."""
            try:
                f(*a, **k)
            except Exception as e:
                logg.exception(f"Ошибка при выполнении отложенного действия {action_name(f)}: {e}")
                return
            logg.debug(f"отложенное действие выполнено: {action_name(f)}")

        if run_now:
            wrapper()
        else:
            QTimer.singleShot(0, wrapper)
    # ↓ до rework-file-deletions (2026-10-21): logger=None → print.debug/print.exception
    #   (AttributeError в таймере Qt) (DA1); f.__name__ у partial/объекта — успешное действие
    #   записывалось как ошибка (DA2); без приложения Qt действия не выполнялись (DA3)
    # if not actions:
    #     return
    #
    # for func, args, kwargs in actions:
    #     logg=logger or print
    #     # Обёртка для вызова в главном потоке
    #     # Создаём частичную функцию с фиксированными аргументами
    #     def wrapper(f=func, a=args, k=kwargs, logg=logg):
    #         try:
    #             f(*a, **k)
    #
    #             logg.debug(
    #                 f"отложенного действия выполнено: {f.__name__} " 
    #             )
    #             # 0==0
    #         except Exception as e:
    #             if logg:
    #                 logg.exception(f"Ошибка при выполнении отложенного действия: {e}")
    #
    #     # QMetaObject.invokeMethod(
    #     #     wrapper,
    #     #     Qt.QueuedConnection,
    #     #     Q_ARG(object, None)  # заглушка – метод invokeMethod требует хотя бы один аргумент
    #     # )
    #     QTimer.singleShot(0, wrapper)
