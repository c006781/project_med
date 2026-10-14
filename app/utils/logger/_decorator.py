# app/utils/logger/_decorator.py

"""
Часть ``BaseAppLogger``: Декоратор log_execution_time.

Содержит примесь ``_DecoratorMixin``: log_execution_time.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_DecoratorMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _DecoratorMixin)
    True
"""

from ._common import _level_to_int
import logging
import time
from typing import Optional, Dict, Any, Callable, Tuple, Union

import inspect


from functools import wraps

from ._common import LOGGER_CODE_FILES

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _DecoratorMixin:
    """
    Примесь ``BaseAppLogger``: log_execution_time.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._DecoratorMixin'>, ...)
    """

    def log_execution_time(
        self, 
        description: str = "", 
        # level: int = logging.DEBUG,
        # ↑ P7: теперь можно и строкой: level='INFO' (без AppLogger._parse_log_level(...)).
        level: Union[int, str] = logging.DEBUG,
        log_args: Optional[bool] = None,
        # log_args: Optional[bool] = True,
        log_return: bool = False,
        show_depth: bool = False,
        # show_depth: bool = True,
    ) -> Callable:
        """
        Декоратор: пишет ``[Начало]`` и ``[Завершение: N сек]`` вокруг вызова функции.

        Работает с обычными функциями, методами, ``staticmethod``/``classmethod`` (в любом
        порядке декораторов) и ``async``-функциями. Место вызова в строках — строка ``def``
        обёрнутой функции (вычисляется один раз, дёшево). Исключение пишется в строку
        завершения и пробрасывается дальше. Если уровень ниже порога логгера, логгер
        выключен или в списке отключённых — функция просто вызывается.

        Args:
            description: Текст перед ``[Начало]``/``[Завершение]``.
            level: Уровень обеих строк: число или имя (``'INFO'``); по умолчанию ``logging.DEBUG``.
            log_args: Писать аргументы вызова (без ``self``/``cls``; у ``__init__`` — никогда).
                ``None`` — по ``log_args`` логгера в момент вызова.
            log_return: Дописывать ``-> repr(результат)`` (кроме ``None``).
            show_depth: Отступ ``>`` по вложенности обёрнутых вызовов (отдельно для потоков
                и задач asyncio, D1).

        Returns:
            Декоратор.

        Пример:
            >>> log = AppLogger.get_instance('PatientService', enable_file_logging='system')
            >>> @log.log_execution_time(description='Сохранение', level=logging.INFO, log_args=True)
            ... def save(patient_id, force=False): ...
            >>> save(5, force=True)
            # INFO [PatientService] File "...", line 2, in <save>: Сохранение [Начало] with args: (5, force=True)
            # INFO [PatientService] File "...", line 2, in <save>: Сохранение [Завершение: 0.0031 сек]
        """
        # P7 (2026-10-14): уровень можно передать строкой ('DEBUG') или числом
        level = _level_to_int(level)

        logger_instance = self

        # if log_args is None:
        #     log_args = self.log_args
        # ↑ до 2026-10-14: значение фиксировалось в момент декорирования (при импорте
        #   модуля), и смена LOG_ARGS в настройках на уже обёрнутые функции не влияла.
        #   Теперь None означает «смотреть logger.log_args в момент вызова».

        def decorator(func: Callable) -> Callable:
            """
            Оборачивает ``func``: собирает неизменные данные (место ``def``, async ли) и возвращает обёртку.

            Args:
                func: Функция, метод, ``staticmethod``/``classmethod`` или корутина.

            Returns:
                Синхронная или асинхронная обёртка с теми же ``__name__``/``__doc__`` (``functools.wraps``).

            Пример:
                >>> wrapped = log.log_execution_time()(my_func)
            """

            # func_filename = inspect.getfile(func)
            # func_lineno = func.__code__.co_firstlineno
            # func_name = func.__name__
            # is_async = inspect.iscoroutinefunction(func)
            
            # Если указанный уровень логирования не активен, возвращаем исходную функцию без обёртки
            # if not logger_instance.logger.isEnabledFor(level):
            #     return func
            
            # сохраняем значение log_return для использования внутри обёртки
            _log_return = log_return

            # Используем квалифицированное имя (с классом, если это метод)
            func_qualname = func.__qualname__
            try:
                # Получаем имя файла, в котором находится вызов функции
                func_filename = inspect.getfile(func)
            except TypeError:
                # Если функция - встроенная, то имя файла не может быть получено
                func_filename = "<built-in>"

            # Получаем номер строки в файле, в которой находится вызов функции

            if isinstance(func, staticmethod):
                func = func.__func__
            elif isinstance(func, classmethod):
                func = func.__func__

            func_lineno = func.__code__.co_firstlineno

            # Определяем, является ли функция асинхронной
            is_async = inspect.iscoroutinefunction(func)

            # Общая логика для формирования сообщений и замера времени
            def make_wrapper() -> Callable:
                """
                Строит обёртку (синхронную или ``async``) и вспомогательные функции записи.

                Returns:
                    Обёртка для ``func``.

                Пример:
                    Вызывается только из ``decorator``.
                """
                # Формируем базовую информацию о caller'е (один раз для всех вызовов)
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'
                desc_part = f"{description} " if description else ""

                # Определяем, нужно ли показывать глубину
                _show_depth = show_depth#  or type(logger_instance).status_show_call_depth_global()

                # Определяем, нужно ли логировать аргументы
                # (None — решает logger_instance.log_args в момент вызова)
                effective_log_args = log_args
                if func.__name__ == '__init__':
                    effective_log_args = False

                # Первый параметр 'self'/'cls' — метод: этот аргумент в лог не выводим.
                # До 2026-10-14 проверялось inspect.ismethod(func) — на этапе
                # декорирования это всегда False (функция ещё не привязана к объекту),
                # и в лог попадал repr(self).
                code = func.__code__
                _skip_first_arg = (
                    code.co_argcount > 0 and code.co_varnames[0] in ('self', 'cls')
                )

                def format_args(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> str:
                    """
                    Строка с аргументами вызова для ``[Начало]`` или пустая строка.

                    Args:
                        args: Позиционные аргументы вызова.
                        kwargs: Именованные аргументы вызова.

                    Returns:
                        ``' with args: (1, x=2)'`` или ``''``, если аргументы не логируются.

                    Пример:
                        >>> format_args((svc, 5), {'force': True})   # для метода
                        ' with args: (5, force=True)'
                    """
                    enabled = (
                        logger_instance.log_args if effective_log_args is None
                        else effective_log_args
                    )
                    if not enabled:
                        return ""

                    display_args = args

                    # if args and inspect.ismethod(func) and func.__self__ is not None:
                    #     display_args = args[1:]  # убираем self
                    if args and _skip_first_arg:
                        display_args = args[1:]  # убираем self / cls

                    args_str = ', '.join(repr(a) for a in display_args)
                    kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
                    all_args = ', '.join(filter(None, [args_str, kwargs_str]))

                    return f" with args: ({all_args})"

                def log_start(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
                    """
                    Пишет строку ``[Начало]`` (с аргументами, если включены).

                    Args:
                        args: Позиционные аргументы вызова.
                        kwargs: Именованные аргументы вызова.

                    Returns:
                        None

                    Пример:
                        Вызывается обёрткой перед вызовом функции.
                    """
                    args_part = format_args(args, kwargs)
                    start_msg = f"{desc_part}[Начало]{args_part}"

                    # Определяем, нужно ли показывать глубину
                    if _show_depth:# or type(logger_instance).status_show_call_depth_global():
                        depth = logger_instance._get_current_depth()
                        formatted = logger_instance._format_message(caller_info, start_msg, depth)
                    else:
                        formatted = logger_instance._format_message(caller_info, start_msg)

                    logger_instance.logger.log(level, formatted, extra={'plain_message': start_msg})

                def log_end(
                    execution_time: float,
                    error: Optional[BaseException] = None,
                    return_value: Any = None,
                ) -> None:
                    """
                    Пишет строку ``[Завершение: N сек]`` (с ошибкой или результатом).

                    Args:
                        execution_time: Длительность вызова, секунд.
                        error: Исключение, если функция упала (текст дописывается через ``:``).
                        return_value: Результат (дописывается при ``log_return``, если не ``None``).

                    Returns:
                        None

                    Пример:
                        Вызывается обёрткой в ``finally``.
                    """

                    if desc_part:
                        end_msg = f"{desc_part}[Завершение: {execution_time:.4f} сек]" 
                    else:
                        end_msg = f"[Завершение: {execution_time:.4f} сек]"
                    
                    if error:
                        end_msg += f": {error}"

                    if _log_return and return_value is not None and not error:
                        ret_str = repr(return_value)
                        # if len(ret_str) > 200:
                        #     ret_str = ret_str[:197] + "..."
                        end_msg += f" -> {ret_str}"

                    if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                        depth = logger_instance._get_current_depth()
                        formatted = logger_instance._format_message(caller_info, end_msg, depth)
                    else:
                        formatted = logger_instance._format_message(caller_info, end_msg)

                    logger_instance.logger.log(level, formatted, extra={'plain_message': end_msg})

                    # if 'PhotoUploaderWidget.set_existing_photos' in formatted:
                    #     0==0
                    # 0==0
                def _thec(tp: type, level: int) -> bool:
                    """
                    Нужно ли МОЛЧАТЬ: уровень ниже порога, логгер выключен или в списке отключённых.

                    Args:
                        tp: Класс логгера (для списка отключённых).
                        level: Уровень строк декоратора.

                    Returns:
                        ``True`` — не писать, просто вызвать функцию.

                    Пример:
                        Вызывается синхронной обёрткой при каждом вызове.
                    """
                    return (
                        (
                            not logger_instance.logger.isEnabledFor(level)
                         ) or (
                            not logger_instance._enabled
                        )
                    ) or (
                        tp.is_disabled(logger_instance.name)
                    )

                # Создаём синхронную обёртку
                @wraps(func)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    """
                    Обёртка обычной функции: ``[Начало]`` → вызов → ``[Завершение]``.

                    Args:
                        *args: Позиционные аргументы для ``func``.
                        **kwargs: Именованные аргументы для ``func``.

                    Returns:
                        Результат ``func``.

                    Raises:
                        Exception: Любое исключение ``func`` (после записи строки завершения).

                    Пример:
                        Вызывается вместо обёрнутой функции.
                    """


                    # thec = (
                    #     (
                    #         not logger_instance.logger.isEnabledFor(level)
                    #      ) or (
                    #         not logger_instance._enabled
                    #     )
                    # ) or (
                    #     type(logger_instance).is_disabled(logger_instance.name)
                    # )

                    thec = _thec(type(logger_instance), level)

                    if not thec: 
                        if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                            logger_instance._increase_depth()
                    try:
                        
                        result = None
                        err = None
                        
                        if not thec: 
                            log_start(args, kwargs)
                            start_time = time.time()

                        try:
                            result = func(*args, **kwargs)
                        except Exception as e:
                            err = e
                            # 0==0
                        finally:

                            if not thec: 
                                # execution_time = time.time() - start_time

                                log_end(
                                    time.time() - start_time, 
                                    err, 
                                    result
                                )

                        if err:
                            raise err
                        
                        return result
                    
                    finally:
                        if not thec: 
                            if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                                logger_instance._decrease_depth()


                    # if thec:
                    #     # return func(*args, **kwargs)
                    #     # Вызываем функцию
                    #     try:
                    #         result = func(*args, **kwargs)
                    #     except Exception as e:
                    #         err = e
                    #         raise err
                    #         # 0==0
                        
                    #         # func_qualname
                    #     return result


                    # if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                    #     logger_instance._increase_depth()
                    # try:

                    #     log_start(args, kwargs)
                    #     start_time = time.time()
                    #     result = None
                    #     error = None
                        
                    #     try:
                    #         result = func(*args, **kwargs)
                    #     except Exception as e:
                    #         error = e
                    #         # raise
                    #     finally:
                    #         execution_time = time.time() - start_time

                    #         log_end(execution_time, error, result)

                    #     if error:
                    #         raise error

                    #     # if execution_time > 17:
                    #     # if execution_time > 17.2:
                    #     # if execution_time > 15.2:
                    #     #     0 == 0

                    #     return result
                    
                    # finally:
                    #     if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                    #         logger_instance._decrease_depth()

                # Создаём асинхронную обёртку
                @wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    """
                    Обёртка корутины: ``[Начало]`` → ``await func(...)`` → ``[Завершение]``.

                    Args:
                        *args: Позиционные аргументы для ``func``.
                        **kwargs: Именованные аргументы для ``func``.

                    Returns:
                        Результат корутины.

                    Raises:
                        Exception: Любое исключение корутины (после записи строки завершения).

                    Пример:
                        >>> await wrapped_coro(1)
                    """
                    
                    if (
                        (not logger_instance.logger.isEnabledFor(level))
                        or (not logger_instance._enabled)
                    ) or (
                        type(logger_instance).is_disabled(logger_instance.name)
                    ):
                        # return func(*args, **kwargs)
                        # Вызываем функцию
                        try:
                            result = await func(*args, **kwargs)
                        except Exception as e:
                            err = e
                            raise err
                            # 0==0
                            # func_qualname
                        return result

                    # if not logger_instance._enabled:
                    #     return await func(*args, **kwargs)
                    
                    if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                        logger_instance._increase_depth()

                    try:
                        log_start(args, kwargs)
                        start_time = time.time()
                        result = None
                        error = None

                        try:
                            result = await func(*args, **kwargs)
                        except Exception as e:
                            error = e
                            # raise
                        finally:
                            execution_time = time.time() - start_time

                            log_end(execution_time, error, result)

                        if error:
                            raise error
                        
                        return result
                    
                    finally:
                        if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                            logger_instance._decrease_depth()
                
                return async_wrapper if is_async else sync_wrapper
            
            return make_wrapper()
        
            # @wraps(func)
            # def sync_wrapper(*args, **kwargs):
            #     """
            #     Обернулка для синхронных функций.

            #     Она вызывает функцию, добавляя информацию о вызове функции:
            #         - имя файла, в котором находится вызов функции
            #         - номер строки в файле, в которой находится вызов функции
            #         - имя функции
            #         - информацию об аргументах (если log_args == True)

            #     description - текст, добавляемый к caller_info
            #     level - уровень логирования
            #     log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
            #     """

                

            #     # Вызываем функцию
            #     # try:
            #     #     result = func(*args, **kwargs)
            #     # except Exception as e:
            #     #     err = e
            #     #     raise e
            #     #     # func_qualname
            #     # return result
        
        
            #     caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'

            #     # Формируем строку с описанием
            #     desc_part = f"{description} " if description else ""

            #     # Определяем, нужно ли логировать аргументы
            #     effective_log_args = log_args

            #     # Для __init__ всегда отключаем логирование аргументов
            #     if func.__name__ == '__init__':
            #         effective_log_args = False
                    
            #     # Формируем строку с аргументами
            #     # args_part = ""
            #     # if log_args:
            #     #     args_str = ', '.join(repr(a) for a in args) if effective_log_args else ''
            #     #     kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #     #     all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #     #     args_part = f" with args: ({all_args})"
            #     args_part = ""
            #     if effective_log_args:
            #         # Для методов исключаем self из отображения
            #         display_args = args
            #         # Проверяем, является ли функция методом (первый аргумент обычно self)
            #         if args and inspect.ismethod(func) and func.__self__ is not None:
            #             display_args = args[1:]  # убираем self
            #         args_str = ', '.join(repr(a) for a in display_args)
            #         kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #         all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #         args_part = f" with args: ({all_args})"

            #     # Формируем строку с информацией о вызове функции
            #     start_msg = f"{desc_part}[Начало]{args_part}"

            #     # Формируем полное сообщение
            #     formatted_start = logger_instance._format_message(caller_info, start_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_start)

            #     # Получаем время начала выполнения
            #     start_time = time.time()
                
            #     err = None
            #     # Вызываем функцию
            #     try:
            #         result = func(*args, **kwargs)
            #     except Exception as e:
            #         err = e
            #         # raise

            #     # Получаем время окончания выполнения
            #     execution_time = time.time() - start_time

            #     # Формируем строку с информацией о времени выполнения
            #     end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"

            #     # Если есть ошибка, добавляем ее в конце сообщения
            #     if err:
            #         end_msg += f": {err}"

            #     # Формируем полное сообщение
            #     formatted_end = logger_instance._format_message(caller_info, end_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_end)

            #     # Возвращаем ошибку если она есть
            #     if err:
            #         raise err
                
            #     return result

            # @wraps(func)
            # async def async_wrapper(*args, **kwargs):
            #     """
            #     Обернулка для асинхронных функций.

            #     Она вызывает функцию, добавляя информацию о вызове функции:
            #         - имя файла, в котором находится вызов функции
            #         - номер строки в файле, в которой находится вызов функции
            #         - имя функции
            #         - информацию об аргументах (если log_args == True)

            #     description - текст, добавляемый к caller_info
            #     level - уровень логирования
            #     log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
            #     """
            #     caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'

            #     # Формируем строку с описанием
            #     desc_part = f"{description} " if description else ""


            #     effective_log_args = log_args
            #     if func.__name__ == '__init__':
            #         effective_log_args = False

            #     # Формируем строку с аргументами
            #     # args_part = ""
            #     # if log_args:
            #     #     args_str = ', '.join(repr(a) for a in args)
            #     #     kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #     #     all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #     #     args_part = f" with args: ({all_args})"

            #     args_part = ""
            #     if effective_log_args:
            #         display_args = args
            #         if args and inspect.ismethod(func) and func.__self__ is not None:
            #             display_args = args[1:]
            #         args_str = ', '.join(repr(a) for a in display_args)
            #         kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #         all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #         args_part = f" with args: ({all_args})"
            #     # Формируем строку с информацией о вызове функции
            #     start_msg = f"{desc_part}[Начало]{args_part}"

            #     # Формируем полное сообщение
            #     formatted_start = logger_instance._format_message(caller_info, start_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_start)

            #     # Получаем время начала выполнения
            #     start_time = time.time()

            #     err = None
            #     # Вызываем функцию
            #     try:
            #         result = await func(*args, **kwargs)
            #     except Exception as e:
            #         err = e
                
            #     # Получаем время окончания выполнения
            #     execution_time = time.time() - start_time

            #     # Формируем строку с информацией о времени выполнения
            #     end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"
                
            #     # Если есть ошибка, добавляем ее в конце сообщения
            #     if err:
            #         end_msg += f": {err}"

            #     # Формируем полное сообщение
            #     formatted_end = logger_instance._format_message(caller_info, end_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_end)

            #     # Возвращаем ошибку если она есть
            #     if err:
            #         raise err

            #     return result

            # return async_wrapper if is_async else sync_wrapper

        return decorator
