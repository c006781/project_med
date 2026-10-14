# app/utils/logger/_outputs.py

"""
Часть ``BaseAppLogger``: Выводы в функции.

Содержит примесь ``_OutputsMixin``: add_output/remove_output/get_outputs.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_OutputsMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _OutputsMixin)
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


class _OutputsMixin:
    """
    Примесь ``BaseAppLogger``: add_output/remove_output/get_outputs.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._OutputsMixin'>, ...)
    """

    @staticmethod
    def _make_output_formatter(
        formatter: Optional[Union[logging.Formatter, str]],
        default: logging.Formatter,
    ) -> logging.Formatter:
        """
        Приводит аргумент ``formatter`` из ``add_output``/``add_global_output`` к Formatter.

        Args:
            formatter: ``None`` — взять ``default``; строка — формат ``logging``
                (``'%(levelname)s: %(plain_message)s'``); готовый ``logging.Formatter``.
            default: Форматтер по умолчанию.

        Returns:
            Объект ``logging.Formatter``.

        Пример:
            >>> BaseAppLogger._make_output_formatter('%(message)s', None)._fmt
            '%(message)s'
        """
        if formatter is None:
            return default
        if isinstance(formatter, str):
            return logging.Formatter(formatter)
        return formatter

    def add_output(
        self,
        func: Callable[[str], Any],
        level: Union[int, str] = logging.NOTSET,
        background: bool = False,
        formatter: Optional[Union[logging.Formatter, str]] = None,
        queue_size: int = 1000,
    ) -> CallableHandler:
        """
        Добавляет вывод этого логгера в функцию вида ``print(text)``.

        Каждая запись логгера, прошедшая его уровень и порог ``level``, форматируется
        и передаётся в ``func`` одной строкой. Консоль и файл при этом работают как
        раньше; чтобы писать только в функцию — ``disable_console()``/``disable_file()``.

        Вывод:
            * переживает перестроения обработчиков (смена уровня, флагов, конфига);
            * молчит, когда логгер выключен (``disable()``) или в списке отключённых;
            * у слейва — свой (с мастером не делится);
            * снимается ``remove_output()`` или ``close()``.

        Подробности о режимах и защитах — в ``CallableHandler``.

        Args:
            func: Функция, принимающая одну строку (``print``, ``bot_send``, ``list.append``).
            level: Порог этого вывода (имя или число). Уровень самого логгера
                фильтрует раньше: вывод не получит записей ниже ``get_level()``.
            background: ``True`` — доставка в фоновом потоке (для медленных функций:
                сеть, Telegram). Записи сверх ``queue_size`` отбрасываются.
            formatter: ``None`` — формат логгера (как в консоли и файле); строка
                формата ``logging``; или ``logging.Formatter``. Для коротких сообщений:
                ``'%(levelname)s: %(plain_message)s'``.
            queue_size: Размер очереди для ``background=True``.

        Returns:
            Созданный ``CallableHandler`` (пригодится для ``remove_output``,
            ``flush`` и счётчика ``dropped``).

        Raises:
            TypeError: ``func`` нельзя вызвать.

        Пример:
            >>> log = AppLogger.get_instance('payments')
            >>> log.add_output(print, level='INFO')

            >>> def send_tg(text: str) -> None:
            ...     bot.send_message(ADMIN_CHAT_ID, text)
            >>> log.add_output(send_tg, level='ERROR', background=True,
            ...                formatter='%(levelname)s %(name)s: %(plain_message)s')
            >>> log.error('Платёж не прошёл')   # → в консоль, файл и Telegram
        """
        handler = CallableHandler(func, level=level, background=background, queue_size=queue_size)
        handler.setFormatter(self._make_output_formatter(formatter, self.formatter))

        with self._handler_lock:
            self._outputs.append(handler)
            self.logger.addHandler(handler)
            self._save_handlers()

        return handler

    @classmethod
    def _class_output_handlers(cls) -> List[CallableHandler]:
        """
        Общие выводы класса из ``OUTPUTS`` — по одному обработчику на весь класс.

        Обработчики создаются один раз, при первом обращении, и хранятся у класса,
        в котором объявлен ``OUTPUTS`` (наследники без своего ``OUTPUTS`` используют
        те же). Каждый логгер класса подключает их в ``_update_handlers`` и фильтрует
        записи своим уровнем; порог самого вывода — ``level`` из описания.

        Описание вывода в ``OUTPUTS`` — функция (``print``) или словарь с ключами
        ``func`` и, по желанию, ``level``, ``background``, ``formatter``, ``queue_size``
        (как у ``add_output``). Формат по умолчанию — ``LOG_FORMAT`` класса (тот же,
        что у консоли и файла).

        Returns:
            Список ``CallableHandler`` (пустой, если ``OUTPUTS`` не задан).

        Raises:
            TypeError: Описание вывода — не функция и не словарь с ``func``.

        Пример:
            >>> class BotLogger(AppLogger, outputs=[print]):
            ...     pass
            >>> BotLogger._class_output_handlers()
            [<CallableHandler print (NOTSET)>]
        """
        owner = next((k for k in cls.__mro__ if 'OUTPUTS' in k.__dict__), None)
        if owner is None or not owner.__dict__['OUTPUTS']:
            return []

        cached = owner.__dict__.get('_class_outputs_cache')
        if cached is not None:
            return cached

        with BaseAppLogger._global_handlers_lock:
            cached = owner.__dict__.get('_class_outputs_cache')
            if cached is not None:
                return cached

            handlers: List[CallableHandler] = []
            for spec in owner.__dict__['OUTPUTS']:
                if callable(spec):
                    spec = {'func': spec}
                if not isinstance(spec, dict) or 'func' not in spec:
                    raise TypeError(
                        f"Описание вывода в OUTPUTS должно быть функцией или словарём с 'func': {spec!r}"
                    )
                handler = CallableHandler(
                    spec['func'],
                    level=spec.get('level', logging.NOTSET),
                    background=spec.get('background', False),
                    queue_size=spec.get('queue_size', 1000),
                )
                handler.setFormatter(owner._make_output_formatter(
                    spec.get('formatter'), logging.Formatter(owner.LOG_FORMAT)))
                handlers.append(handler)

            setattr(owner, '_class_outputs_cache', handlers)
            return handlers

    @classmethod
    def close_class_outputs(cls) -> None:
        """
        Закрывает общие выводы класса (``OUTPUTS``): дожидается фоновой доставки
        и снимает их со всех логгеров класса. Вызывайте при выходе из программы.

        Следующий созданный или перестроенный логгер класса создаст выводы заново.

        Returns:
            None

        Пример:
            >>> BotLogger.close_class_outputs()
        """
        owner = next((k for k in cls.__mro__ if '_class_outputs_cache' in k.__dict__), None)
        if owner is None:
            return
        handlers = owner.__dict__['_class_outputs_cache']
        delattr(owner, '_class_outputs_cache')
        with cls._instances_lock:
            instances = list(cls._instances.values())
        for inst in instances:
            for handler in handlers:
                inst.logger.removeHandler(handler)
            inst._save_handlers()
        for handler in handlers:
            handler.close()

    def remove_output(self, output: Union[CallableHandler, Callable[[str], Any]]) -> bool:
        """
        Убирает вывод, добавленный ``add_output()``, и закрывает его.

        Args:
            output: Обработчик, который вернул ``add_output()``, или сама функция
                (тогда убираются все выводы с этой функцией).

        Returns:
            ``True``, если что-то было убрано.

        Пример:
            >>> h = log.add_output(print)
            >>> log.remove_output(h)
            True
            >>> log.remove_output(print)   # уже нет
            False
        """
        with self._handler_lock:
            # h.func == output, а не «is»: связанный метод (list.append, bot.send)
            # при каждом обращении — новый объект, но равный прежнему
            matched = [h for h in self._outputs if h is output or h.func == output]
            for handler in matched:
                self._outputs.remove(handler)
                self.logger.removeHandler(handler)
            self._save_handlers()

        for handler in matched:
            handler.close()
        return bool(matched)

    def get_outputs(self) -> List[CallableHandler]:
        """
        Выводы-функции этого логгера (копия списка).

        Returns:
            Список ``CallableHandler`` в порядке добавления.

        Пример:
            >>> [h.func for h in log.get_outputs()]
            [<built-in function print>]
        """
        with self._handler_lock:
            return list(self._outputs)
