# app/utils/logger/_emit.py

"""
Часть ``BaseAppLogger``: Запись сообщений.

Содержит примесь ``_EmitMixin``: debug…exception, поиск места вызова, глубина вложенности.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_EmitMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _EmitMixin)
    True
"""

import asyncio
import os
import logging
import sys
import time
from typing import (
    List, Optional, Dict, 
    Any, Callable, Tuple, Union
)

import warnings
import inspect

import threading

import contextvars

from functools import wraps
from logging.handlers import RotatingFileHandler
import weakref
import queue

from ._common import LOGGER_CODE_FILES, _NOT_FOUND, _STOP_OUTPUT, _level_to_int
from .handlers import CallableHandler, RobustRotatingFileHandler

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _EmitMixin:
    """
    Примесь ``BaseAppLogger``: debug…exception, поиск места вызова, глубина вложенности.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._EmitMixin'>, ...)
    """

    def _get_call_depth(self) -> int:
        """
        Глубина стека вызовов без кадров самого логгера (для ``show_call_depth=True``).

        Идёт от вызывающего кадра к корню через ``f_back`` и считает кадры, которые не
        относятся к логгеру (``_is_logger_frame``). Отступ ``>`` в строке лога равен
        этому числу.

        Returns:
            Количество «пользовательских» кадров в стеке.

        Пример:
            >>> def a(): return log._get_call_depth()
            >>> def b(): return a()
            >>> b() - a()
            1
        """
        depth = 0
        frame = sys._getframe(1)  # пропускаем текущий кадр (_get_call_depth)
        while frame is not None:
            if not self._is_logger_frame(frame.f_code):
                depth += 1
            frame = frame.f_back
        return depth

    def _get_current_depth(self) -> int:
        """
        Текущая глубина вложенности вызовов, обёрнутых декоратором (``show_depth=True``).

        Хранится в ``contextvars.ContextVar``: значение своё у каждого потока (новый
        поток стартует с пустым контекстом → 0) и у каждой задачи asyncio (задача
        получает копию контекста создателя). Поэтому отдельный ``threading.local`` не нужен.

        Returns:
            Глубина, 0 вне обёрнутых вызовов.

        Пример:
            >>> log._get_current_depth()
            0
        """
        return self._depth_context.get()

    def _set_current_depth(self, depth: int) -> None:
        """
        Устанавливает глубину вложенности для текущего потока/задачи.

        Args:
            depth: Новая глубина (не меньше 0).

        Returns:
            None

        Пример:
            >>> log._set_current_depth(2); log._get_current_depth()
            2
        """
        self._depth_context.set(depth)

    def _increase_depth(self) -> int:
        """
        Увеличивает глубину вложенности на 1 (вход в обёрнутый декоратором вызов).

        Returns:
            Новая глубина.

        Пример:
            >>> log._increase_depth()
            1
        """
        current = self._get_current_depth()
        new_depth = current + 1
        self._set_current_depth(new_depth)
        
        return new_depth

    def _decrease_depth(self) -> int:
        """
        Уменьшает глубину вложенности на 1 (выход из вызова), не ниже 0.

        Returns:
            Новая глубина.

        Пример:
            >>> log._decrease_depth()
            0
        """
        current = self._get_current_depth()
        new_depth = max(0, current - 1)
        self._set_current_depth(new_depth)

        return new_depth

    def _convert_patterns_modeles_tips(
        self,
        modeles: Any,
        simple_types: Tuple[type, ...] = (int, float, str, bool, type(None)),
    ) -> Optional[set]:
        """
        Приводит значение к множеству (служебный метод старого алгоритма пропуска кадров).

        Сейчас не используется: старый ``_thec_skip_patterns_modeles`` закомментирован.
        Особенность: для уже переданного ``set`` возвращает ``None``.

        Args:
            modeles: Одно значение или коллекция.
            simple_types: Типы, которые считаются одиночным значением.

        Returns:
            Множество или ``None`` (если передан ``set``).

        Пример:
            >>> log._convert_patterns_modeles_tips('a')
            {'a'}
        """
        
        if  isinstance(modeles, simple_types):
            return {modeles}
        
        elif  not isinstance(modeles, set):
            return set(modeles) 
       
    def _thec_patterns_modeles_is_none(
        self,
        modeles: Any,
        if_err_tip: bool,
    )-> bool:
        """
        Пустое ли значение (``None`` или длина 0). Не используется (см. ``_convert_patterns_modeles_tips``).

        Args:
            modeles: Проверяемое значение.
            if_err_tip: ``True`` — вместо ``True`` выбросить ``ValueError``.

        Returns:
            ``True``, если значение пустое.

        Raises:
            ValueError: Значение пустое и ``if_err_tip=True``.

        Пример:
            >>> log._thec_patterns_modeles_is_none([], False)
            True
        """
        # Проверка на наличие              
        if (modeles is None)  : 
            if if_err_tip :  
                raise ValueError('err: filename is None')  
            return True  
        
        if (len(modeles) == 0) :
            if if_err_tip :  
                raise ValueError('err: filename is None')  
            return True 
        
        return False 

    def _thec_patterns_modeles(
        self,
        modeles: Any,
        if_err_tip: bool,
    ) -> Optional[set]:
        """
        Пустое значение → ``None``, иначе множество. Не используется (см. ``_convert_patterns_modeles_tips``).

        Args:
            modeles: Значение или коллекция.
            if_err_tip: Выбрасывать ``ValueError`` для пустого значения.

        Returns:
            Множество или ``None``.

        Пример:
            >>> log._thec_patterns_modeles(('a', 'b'), False)
            {'a', 'b'}
        """
        
                      
        # Проверка на наличие   
        if self._thec_patterns_modeles_is_none(
            modeles     = modeles,
            if_err_tip  = if_err_tip,
        ):
            return None             
                
        modeles = self._convert_patterns_modeles_tips(
            modeles = modeles
        )
        
        return modeles 
        
    # def _thec_skip_patterns_modeles(
    #     self,
    #     patterns_modeles
    # ):  
    #     """
    #     Проверяет, если при указанных параметрах modeles стоит пропустить
    #     логирование.

    #     :param patterns_modeles: Словарь с параметрами для фильтрации.
    #     :return: True - указатель есть в блок листе, False - нет в блок листе.
    #     """



    #     # Проверяем, если указатель на место вызова есть в общем блоке лист
    #     for skip_patterns_modele in self.skip_patterns_modeles: 
    #         # общий блок лист
    #         for i in [
    #             'filename', 
    #             'function',
    #         ]:
    #             # Флаг, указывающий на то, что мы проверяем filename или function
    #             if_filename  = (i == 'filename')
                
    #             # Проверяем, есть ли указатель на место вызова в skip
    #             thec_skip = self._thec_patterns_modeles( 
    #                 modeles     = skip_patterns_modele.get(i,{}) ,
    #                 if_err_tip  = if_filename,
    #             )
    #             if thec_skip is None:
    #                 # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                 # то возвращаем True
    #                 return True  
                
    #             # Проверяем, есть ли указатель на место вызова в patterns_modeles
    #             thec_modeles = self._thec_patterns_modeles(
    #                 modeles     = patterns_modeles.get(i,{}) ,
    #                 if_err_tip  = if_filename,
    #             )
    #             if thec_modeles is None:
    #                 # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                 # то возвращаем True
    #                 return True  
                    
    #             # Проверяем, если указатель на место вызова есть в блок листе
    #             for modele in thec_modeles: 
    #                 # что проверяем на наличие в блок листе  
                
    #                 if self._thec_patterns_modeles_is_none(
    #                     modeles     = modele ,
    #                     if_err_tip  = if_filename  , 
    #                 ):
    #                     # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                     # то возвращаем True
    #                     return True

    #                 if ( # проверка на наличие в блок листе
    #                     modele in thec_skip
    #                 ) or (
    #                     modele == thec_skip
    #                 ) :
    #                     # если указатель на место вызова есть в общем блоке лист, то возвращаем True
    #                     return True  
    #                 else:
    #                     # иначе мы проверяем, если указатель на место вызова есть в skip
    #                     skip_thec = True
    #                     for skip in thec_skip:
    #                         if self._thec_patterns_modeles_is_none(
    #                             modeles     = skip ,   
    #                             if_err_tip  = if_filename  , 
    #                         ):
    #                             # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                             # то возвращаем True
    #                             return True 

    #                         # проверка на наличие каждого элимента по пути
    #                         skip_thec_ = (
    #                             (skip in modele) or (skip == modele)
    #                         )
                            
    #                         if if_filename or ( skip_thec) : 
    #                             # если filename, то нудно проверить нахождение каждого элимента по пути. Если все есть, то переход на проверку function
    #                             skip_thec = skip_thec and skip_thec_
    #                         else: 
    #                             # возможно вернуть  skip_thec_, а не continue
    #                             continue

    #                     if not skip_thec:
    #                         # если указатель на место вызова не находится в skip, то возвращаем False
    #                         return False   
    #         if not skip_thec:
    #             # если указатель на место вызова не находится в skip, то возвращаем False
    #             return False 

    #     # если указатель на место вызова не находится в общем блоке лист, то возвращаем True
    #     return True
    def _thec_skip_patterns_modeles(self, patterns_modeles: dict) -> bool:
        """
        Подходит ли кадр под одно из правил ``skip_patterns_modeles`` (кадр логгера).

        Правило срабатывает, если путь файла кадра оканчивается на путь из правила
        (сравнение без учёта регистра, ``normcase``) и имя функции входит в список правила
        (пустой список — любая функция). Без кэша; на каждый кадр вызывайте
        ``_is_logger_frame`` — он кэширует ответ.

        Args:
            patterns_modeles: ``{'filename': (co_filename,), 'function': (co_name,)}``.

        Returns:
            ``True`` — кадр нужно пропустить.

        Пример:
            >>> log._thec_skip_patterns_modeles({'filename': (_THIS_CODE_FILENAME,), 'function': ('info',)})
            True
        """

        # Извлекаем filename и function из переданного словаря
        frame_filename_tuple = patterns_modeles.get('filename')
        frame_function_tuple = patterns_modeles.get('function')
        
        # Если нет ни того, ни другого — не пропускаем
        if not frame_filename_tuple and not frame_function_tuple:
            return False
        
        # Берём первый (и единственный) элемент
        filename = frame_filename_tuple[0] if frame_filename_tuple else None
        function = frame_function_tuple[0] if frame_function_tuple else None
        
        # Перебираем все правила пропуска
        for rule in self.skip_patterns_modeles:
            # Части пути, которые должны ВСЕ присутствовать в filename
            required_parts = rule.get('filename', ())
            # Имена функций, которые должны совпадать
            required_functions = rule.get('function', ())
            
            # Проверка по filename: все required_parts должны быть подстроками в filename
            # if required_parts:
            #     if not filename:
            #         continue   # нет filename, а правило требует — пропускаем правило

            #     if not all(part in filename for part in required_parts):
            #         continue   # не все части найдены — правило не подходит


            # Проверка filename: путь должен заканчиваться на os.path.join(*required_parts)
            if required_parts:
                if not filename:
                    continue

                # Нормализуем путь и целевой суффикс
                # normcase: на Windows регистр букв в пути (диск 'c:' / 'C:') может различаться
                norm_filename = os.path.normcase(os.path.normpath(filename))
                target_suffix = os.path.normcase(os.path.normpath(os.path.join(*required_parts)))

                if not norm_filename.endswith(target_suffix):
                    continue
            
            # Проверка по function: если правило требует конкретные имена функций
            if required_functions:
                if not function or function not in required_functions:
                    continue
            
            # Если дошли сюда — правило сработало, фрейм нужно пропустить
            return True
        
        # Ни одно правило не подошло
        return False    



    # До 2026-10-14: inspect.stack() на каждую запись. Он строит FrameInfo для ВСЕХ
    # кадров стека и читает строки исходников (контекст) — ~5 мс на вызов log.info()
    # при стеке глубиной 30, а в Qt-приложении стек глубже. Заменено проходом по
    # f_back (sys._getframe) — см. новую реализацию ниже.
    # def _get_caller_info(self, levels_up: int = 2) -> str:
    #     """
    #     Возвращает строку с информацией о caller'е.

    #     - Если levels_up > 0: поднимается на указанное количество уровней (стандартное поведение).
    #     - Если levels_up == 0: автоматически ищет первый фрейм вне модулей логирования.

    #     Важно: мы используем inspect.stack() для получения стека вызываемых функций.
    #     Каждый элемент стека - это объект FrameInfo, содержащий информацию о текущей функции:
    #       - filename: путь к файлу, в котором находится функция
    #       - lineno: номер строки в файле, в которой находится функция
    #       - function: имя функции

    #     Мы ищем фрейм, чей файл не содержит 'logger' или 'base_logger', чтобы не учитывать
    #     вызовы изнутри модулей логирования. Если таких фреймов не найдено, берем последний
    #     фрейм (в конце стека).
    #     """

    #     # import inspect
    #     stack = inspect.stack()
    #     frame_info = stack[-1]

    #     if levels_up > 0:
    #         # Явно заданная глубина
    #         if len(stack) <= levels_up:
    #             frame_info = stack[-1]
    #         else:
    #             frame_info = stack[levels_up]
    #     else:
    #         # Автоматический поиск: пропускаем фреймы, относящиеся к логгеру
    #         # Пропускаем текущий фрейм (индекс 0) и ищем первый, чей файл не содержит 'logger'

    #         for frame_info in stack[1:]:

    #             if self._thec_skip_patterns_modeles( # если входит в список пропуска, то след итерация
    #                 patterns_modeles={
    #                     # co_filename, а не frame_info.filename — см. _THIS_CODE_FILENAME
    #                     'filename':(frame_info.frame.f_code.co_filename,),
    #                     'function':(frame_info.function,),  
    #                 }
    #             ):
    #                 continue
    #             # если не в списке, то выводим            
    #             filename = frame_info.filename
    #             break

    #         else:
    #             # Если не нашли (вдруг весь стек состоит из логгера), берём последний
    #             frame_info = stack[-1]

    #     filename = frame_info.filename
    #     lineno = frame_info.lineno
    #     funcname = frame_info.function

    #     return f'File "{filename}", line {lineno}, in <{funcname}>'


    def _is_logger_frame(self, code: Any) -> bool:
        """
        Относится ли кадр к самому логгеру (его надо пропустить при поиске места вызова).

        Обёртка над ``_thec_skip_patterns_modeles`` с кэшем по
        ``(класс, co_filename, co_name)``.

        Args:
            code: Объект кода кадра (``frame.f_code``).

        Returns:
            ``True`` — кадр логгера, пропустить.

        Пример:
            >>> log._is_logger_frame(BaseAppLogger.info.__code__)
            True
            >>> log._is_logger_frame((lambda: None).__code__)
            False
        """
        key = (type(self), code.co_filename, code.co_name)
        cached = BaseAppLogger._skip_cache.get(key)
        if cached is None:
            cached = self._thec_skip_patterns_modeles({
                'filename': (code.co_filename,),
                'function': (code.co_name,),
            })
            BaseAppLogger._skip_cache[key] = cached
        return cached

    def _get_caller_info(self, levels_up: int = 2) -> str:
        """
        Место вызова в формате, который IDE превращает в ссылку.

        Режимы:
            * ``levels_up > 0`` — взять кадр на ``levels_up`` уровней выше этого метода
              (если стек короче — самый внешний кадр);
            * ``levels_up == 0`` — автоматически: первый кадр, не относящийся к логгеру
              (``_is_logger_frame``); если весь стек — логгер, самый внешний кадр.

        Используется ``sys._getframe`` / ``f_back``: без построения списка кадров и без
        чтения исходников (в отличие от ``inspect.stack()``).

        Args:
            levels_up: Глубина подъёма; 0 — автоматический поиск (так вызывает ``_formatted``).

        Returns:
            Строка ``File "<путь>", line <N>, in <функция>``.

        Пример:
            >>> def handler():
            ...     return log._get_caller_info(levels_up=1)
            >>> handler()
            'File "C:\\proj\\svc.py", line 2, in <handler>'
        """
        frame = sys._getframe(0)
        outermost = frame
        target = None

        if levels_up > 0:
            # Явно заданная глубина
            target = frame
            for _ in range(levels_up):
                if target.f_back is None:
                    break
                target = target.f_back
        else:
            # Автоматический поиск: первый кадр вне логгера
            candidate = frame.f_back
            while candidate is not None:
                outermost = candidate
                if not self._is_logger_frame(candidate.f_code):
                    target = candidate
                    break
                candidate = candidate.f_back

        if target is None:
            # Весь стек — логгер: берём самый внешний кадр (как раньше stack[-1])
            target = outermost
            while target.f_back is not None:
                target = target.f_back

        code = target.f_code
        return f'File "{code.co_filename}", line {target.f_lineno}, in <{code.co_name}>'

    def _format_message(
        self, 
        caller_info: str,
        message: str,
        depth: Optional[int] = None
    ) -> str:
        """
        Собирает текст записи: ``[имя]<TAB><отступ> <место вызова>:<TAB><сообщение>``.

        Отступ ``>`` повторяется ``depth`` раз. Если ``depth`` не передан: при
        ``show_call_depth`` — глубина стека (``_get_call_depth``), иначе — глубина
        вложенности декоратора (``_get_current_depth``, 0 вне ``show_depth``).

        Args:
            caller_info: Строка ``File "...", line N, in <func>``.
            message: Текст сообщения.
            depth: Явная глубина (у декоратора с ``show_depth=True``).

        Returns:
            Текст записи (время и уровень добавит форматтер).

        Пример:
            >>> log._format_message('File "a.py", line 1, in <f>', 'привет', depth=2)
            '[svc]\\t>> File "a.py", line 1, in <f>:\\tпривет'
        """
        if depth is None:
            # Нет переданной глубины – определяем автоматически
            if self._show_call_depth:
                effective_depth = self._get_call_depth()
            else:
                effective_depth = self._get_current_depth()   # ручная глубина от декоратора (0 по умолчанию)
        else:
            # Переданная глубина (обычно из декоратора) имеет приоритет
            effective_depth = depth

        indent = ">" * effective_depth  #  уровень вложенности
        
        return f"[{self.name}]\t{indent} {caller_info}:\t{message}"

    # --------------------------------------------------------------------------
    # Прямые методы логирования
    # --------------------------------------------------------------------------
    
    def _formatted(
        self,
        message: str,  # текст сообщения, которое будет добавлено к caller_info
        levels_up: Optional[int] = None,  # глубина поиска в стеке вызов (0 - автоматически, > 0 - явно)
    ) -> str:
        """
        Текст записи для ``debug()``…``exception()``: место вызова + сообщение.

        Args:
            message: Текст сообщения.
            levels_up: Глубина поиска места вызова; ``None`` — ``_levels_up`` класса (0 —
                автоматически, первый кадр вне логгера).

        Returns:
            Текст записи; пустая строка, если логгер выключен.

        Пример:
            >>> log._formatted('привет')
            '[svc]\\t File "C:\\\\proj\\\\svc.py", line 10, in <run>:\\tпривет'
        """

        if not self._enabled:
            return ""
        
        if levels_up is None:
            levels_up = self._levels_up

        caller = self._get_caller_info(
            levels_up=levels_up
        )

        depth = self._get_call_depth() if self._show_call_depth else None

        return self._format_message(
            caller, 
            message,
            depth,
        )
        
    
    def debug(self, message: str) -> None:
        """
        Пишет сообщение уровня DEBUG с местом вызова.

        Молчит, если логгер выключен или в списке отключённых. Поле ``plain_message`` записи —
        сам текст (для ``add_output(..., formatter='%(plain_message)s')``).

        Args:
            message: Текст сообщения (уже готовая строка, без ``%``-подстановки).

        Returns:
            None

        Пример:
            >>> log.debug(f'Запрос пациента id={patient_id}')
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.debug(
            self._formatted(
                message = message,
            ),
            # Текст без имени логгера и места вызова — для коротких выводов
            # (add_output(..., formatter='%(plain_message)s'))
            extra={'plain_message': message},
        )

    def info(self, message: str) -> None:
        """
        Пишет сообщение уровня INFO с местом вызова.

        Молчит, если логгер выключен или в списке отключённых.

        Args:
            message: Текст сообщения.

        Returns:
            None

        Пример:
            >>> log.info('Настройки сохранены')
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.info(
            self._formatted(
                message = message,
            ),
            # Текст без имени логгера и места вызова — для коротких выводов
            # (add_output(..., formatter='%(plain_message)s'))
            extra={'plain_message': message},
        )

    def warning(self, message: str) -> None:
        """
        Пишет сообщение уровня WARNING с местом вызова.

        Молчит, если логгер выключен или в списке отключённых (B4).

        Args:
            message: Текст сообщения.

        Returns:
            None

        Пример:
            >>> log.warning('Файл БД не найден, будет создан новый')
        """

        # if not self._enabled:
        # ↑ до исправления B4: warning() не проверял список отключённых логгеров
        #   (add_disabled_logger), в отличие от debug/info/critical/exception.
        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.warning(
            self._formatted(
                message = message,
            ),
            # Текст без имени логгера и места вызова — для коротких выводов
            # (add_output(..., formatter='%(plain_message)s'))
            extra={'plain_message': message},
        )

    def error(self, message: str) -> None:
        """
        Пишет сообщение уровня ERROR с местом вызова (без traceback — для него ``exception``).

        Молчит, если логгер выключен или в списке отключённых (B4).

        Args:
            message: Текст сообщения.

        Returns:
            None

        Пример:
            >>> log.error('Не удалось подключиться к Яндекс.Диску')
        """

        # if not self._enabled:
        # ↑ до исправления B4: error() не проверял список отключённых логгеров
        #   (add_disabled_logger), в отличие от debug/info/critical/exception.
        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.error(
            self._formatted(
                message = message,
            ),
            # Текст без имени логгера и места вызова — для коротких выводов
            # (add_output(..., formatter='%(plain_message)s'))
            extra={'plain_message': message},
        )

    def critical(self, message: str) -> None:
        """
        Пишет сообщение уровня CRITICAL с местом вызова.

        Молчит, если логгер выключен или в списке отключённых.

        Args:
            message: Текст сообщения.

        Returns:
            None

        Пример:
            >>> log.critical('База данных повреждена')
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.critical(
            self._formatted(
                message = message,
            ),
            # Текст без имени логгера и места вызова — для коротких выводов
            # (add_output(..., formatter='%(plain_message)s'))
            extra={'plain_message': message},
        )

    def exception(self, message: str, exc_info: bool = True) -> str:
        """
        Пишет ERROR с traceback текущего исключения; вызывайте внутри ``except``.

        Место вызова — строка с ``log.exception`` (B6). Удобно сразу использовать в ``raise``:
        метод возвращает тот же текст.

        Args:
            message: Текст сообщения.
            exc_info: ``False`` — без traceback (как ``error``).

        Returns:
            ``message`` без изменений.

        Пример:
            >>> try:
            ...     save(patient)
            ... except DatabaseError as e:
            ...     raise SaveError(log.exception(f'Не сохранён пациент {patient.id}')) from e
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return message
    
        self.logger.error(
            self._formatted(
                message = message,
            ), exc_info=exc_info,
            # Текст без имени логгера и места вызова — для коротких выводов
            # (add_output(..., formatter='%(plain_message)s'))
            extra={'plain_message': message},
        )
        return message
        

    # --------------------------------------------------------------------------
    # Декоратор для замера времени выполнения
    # --------------------------------------------------------------------------
