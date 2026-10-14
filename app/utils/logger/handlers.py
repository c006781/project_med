# app/utils/logger/handlers.py

"""
Обработчики ``logging`` пакета логирования.

    RobustRotatingFileHandler — файл с ротацией, переживающий удаление файла и
                                кратковременные блокировки.
    CallableHandler           — передаёт записи в функцию вида ``print(text)``,
                                в том числе в фоновом потоке.

Оба можно использовать отдельно от ``BaseAppLogger``, с голым ``logging``.

Пример:
    >>> import logging
    >>> from app.utils.logger.handlers import CallableHandler
    >>> logging.getLogger('demo').addHandler(CallableHandler(print, level='INFO'))
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

from ._common import LOGGER_CODE_FILES, _STOP_OUTPUT, _level_to_int

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)


class RobustRotatingFileHandler(RotatingFileHandler):
    """
    RotatingFileHandler, который переживает удаление файла и кратковременные блокировки.

    Отличия от ``logging.handlers.RotatingFileHandler``:
        * не чаще раза в ``_check_interval`` секунд проверяет, что файл есть на диске,
          и пересоздаёт его (вместе с папкой), если его удалили;
        * при ``FileNotFoundError``/``PermissionError`` (на Windows — антивирус, второй
          экземпляр программы, ротация) повторяет запись ``MAX_RETRIES`` раз с паузой
          ``RETRY_DELAY`` и переоткрытием файла; после последней неудачи —
          ``handleError`` (стандартный traceback в stderr), запись теряется.

    Паузы идут в потоке, который пишет в лог (в GUI — в главном потоке), поэтому
    суммарное ожидание ограничено: ``(MAX_RETRIES - 1) * RETRY_DELAY`` = 0,1 с.

    Attributes:
        MAX_RETRIES: Сколько всего попыток записи.
        RETRY_DELAY: Пауза между попытками, секунд.

    Пример:
        >>> h = RobustRotatingFileHandler('logs/app.log', maxBytes=10_000_000,
        ...                               backupCount=5, encoding='utf-8')
        >>> logging.getLogger('demo').addHandler(h)
    """

    # До 2026-10-14: 5 попыток по 0,2 с — до 0,8 с подвисания GUI на КАЖДУЮ запись,
    # пока файл заблокирован. Сейчас не больше 0,1 с.
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 0.05

    def __init__(
        self,
        filename: str,
        mode: str = 'a',
        maxBytes: int = 0, backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False
    ) -> None:
        """
        Создаёт обработчик; аргументы те же, что у ``RotatingFileHandler``.

        Args:
            filename: Путь к файлу лога.
            mode: Режим открытия файла (``'a'`` — дописывать).
            maxBytes: Размер файла, после которого происходит ротация; 0 — без ротации.
            backupCount: Сколько старых файлов хранить (``app.log.1`` … ``app.log.N``).
            encoding: Кодировка файла (логгер передаёт ``'utf-8'``).
            delay: ``True`` — открыть файл при первой записи, а не сразу.

        Returns:
            None

        Пример:
            >>> RobustRotatingFileHandler('logs/app.log', maxBytes=10_000_000,
            ...                           backupCount=5, encoding='utf-8')
        """
        super().__init__(
            filename,
            mode,
            maxBytes,
            backupCount,
            encoding,
            delay
        )

        self._lock = threading.RLock()
        self._last_check = 0
        self._check_interval = 1.0  # проверять не чаще раза в секунд

    def emit(self, record: logging.LogRecord) -> None:
        """
        Записывает запись в файл, восстанавливая файл при необходимости.

        Порядок:
            1. Не чаще раза в ``_check_interval`` секунд проверяет, что файл есть на диске;
               если его удалили — переоткрывает (``_reopen``, вместе с папкой).
            2. Пишет запись стандартным ``RotatingFileHandler.emit`` (с ротацией).
            3. При ``FileNotFoundError``/``PermissionError`` повторяет до ``MAX_RETRIES`` раз
               с паузой ``RETRY_DELAY`` и переоткрытием; после последней неудачи —
               ``handleError`` (traceback в stderr), запись теряется.
            4. Любая другая ошибка — сразу ``handleError``.

        Args:
            record: Запись лога.

        Returns:
            None

        Пример:
            Вызывается самим ``logging`` при ``logger.info(...)``; напрямую — только в тестах:
            >>> handler.emit(logging.LogRecord('t', logging.INFO, __file__, 1, 'текст', None, None))
        """
        # max_retries = 5
        # retry_delay = 0.2        # добавить задержку между попытками
        max_retries = self.MAX_RETRIES
        retry_delay = self.RETRY_DELAY
        for attempt in range(max_retries):
            with self._lock:
                try:
                    need_reopen = False
                    now = time.time()
                    # Проверяем существование файла, если прошло достаточно времени
                    if now - self._last_check > self._check_interval:
                        if not os.path.exists(self.baseFilename):
                            # Файл удалён – переоткрываем
                            need_reopen = True

                        self._last_check = now 

                    if need_reopen: # Файл удалён – переоткрываем
                        with self._lock:
                            self._reopen() 
                            #  После переоткрытия принудительно сбросим таймер, чтобы следующая запись не ждала
                            self._last_check = 0

                    super().emit(record)
                    return
                
                except (FileNotFoundError, PermissionError) as e:
                    # Если файл внезапно исчез между проверкой и записью
                    # self.handleError(record)
                    if attempt == max_retries - 1:
                        self.handleError(record)
                        return
                    # print(f"подход {attempt} провал")
                    # ↑ до 2026-10-14 в stdout. Библиотека не должна писать в stdout
                    #   (там вывод программы, а теперь и функции вывода вроде print).
                    print(f"подход {attempt} провал", file=sys.stderr)
                    time.sleep(retry_delay)
                    with self._lock:

                        self._reopen()

                except Exception:
                    self.handleError(record)
                    return

    def _reopen(self) -> None:
        """
        Закрывает текущий поток и открывает файл заново (создаёт папку, если её нет).

        Returns:
            None

        Пример:
            >>> handler._reopen()      # после удаления файла
            >>> handler.stream is not None
            True
        """
        with self._lock:
            # Файл удалён – закрываем текущий поток и открываем заново
            if self.stream:
                self.stream.close()
                self.stream = None

            # Создаём директорию для файла лога, если её нет
            log_dir = os.path.dirname(self.baseFilename)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True) 

            # self._open() # открывает файл заново (определён в базовом классе)
            # ↑ до 2026-10-14 результат выбрасывался: файл открывался, сразу закрывался
            #   сборщиком мусора и открывался ещё раз при следующей записи.
            self.stream = self._open()

    def reopen_if_needed(self) -> bool:
        """
        Переоткрывает файл, только если его нет на диске.

        Returns:
            ``True``, если файл пришлось пересоздать.

        Пример:
            >>> os.remove(handler.baseFilename)
            >>> handler.reopen_if_needed()
            True
        """
        with self._lock:
            if not os.path.exists(self.baseFilename):
                self._reopen()
                return True
        return False

    def force_reopen(self) -> None:
        """
        Принудительно переоткрывает файл, даже если он на месте, и сбрасывает таймер проверки.

        Нужен после смены пути или внешних операций с файлом (архивация, перенос).

        Returns:
            None

        Пример:
            >>> handler.force_reopen()
        """
        with self._lock:
            self._reopen()
            self._last_check = time.time()

class CallableHandler(logging.Handler):
    """
    Обработчик, который передаёт каждую запись лога в функцию вида ``print(text)``.

    Нужен, чтобы выводить лог куда угодно, не разбираясь в ``logging``: в Telegram-бот,
    в окно программы, в список для тестов. Функция получает одну строку —
    запись, отформатированную ``formatter``.

    Режимы доставки:
        * ``background=False`` (по умолчанию) — функция вызывается сразу, в том же потоке,
          где сделана запись. Просто и предсказуемо; подходит для быстрых функций
          (``print``, добавление в список, вывод в виджет).
        * ``background=True`` — запись кладётся в очередь, функцию вызывает отдельный
          фоновый поток. Подходит для медленных функций (сеть, Telegram): запись в лог
          не тормозит программу. Если очередь переполнена (функция не успевает), новые
          записи отбрасываются и считаются в ``dropped`` — программа не блокируется.

    Защиты:
        * Исключение внутри функции не роняет программу: оно передаётся в
          ``handleError`` (стандартный traceback ``--- Logging error ---`` в stderr).
        * Повторный вход: если функция сама пишет в лог, эта запись в функцию не
          передаётся (иначе бесконечная рекурсия). В остальные выводы она попадает.

    Поле ``plain_message``: для записей ``BaseAppLogger`` — текст сообщения без имени
    логгера и места вызова; для прочих — ``record.getMessage()``. Используйте в
    формате для коротких сообщений: ``'%(levelname)s: %(plain_message)s'``.

    Attributes:
        func: Функция, получающая строку.
        background: Доставка в фоновом потоке.
        dropped: Сколько записей отброшено из-за переполненной очереди.

    Пример:
        >>> h = CallableHandler(print, level='INFO')
        >>> h.setFormatter(logging.Formatter('%(levelname)s: %(plain_message)s'))
        >>> logging.getLogger('demo').addHandler(h)

        >>> def send_tg(text: str) -> None:
        ...     bot.send_message(chat_id, text)
        >>> tg = CallableHandler(send_tg, level='ERROR', background=True)
        >>> tg.close()   # дождаться доставки остатка очереди и остановить поток
    """

    # Сколько ждать доставки остатка очереди при закрытии (секунд)
    CLOSE_TIMEOUT: float = 5.0

    def __init__(
        self,
        func: Callable[[str], Any],
        level: Union[int, str] = logging.NOTSET,
        background: bool = False,
        queue_size: int = 1000,
        name: Optional[str] = None,
    ) -> None:
        """
        Создаёт обработчик-функцию.

        Args:
            func: Функция вида ``print``: принимает одну строку. Возвращаемое
                значение игнорируется.
            level: Порог этого вывода: имя (``'ERROR'``) или число (``logging.ERROR``).
                Записи ниже порога в функцию не передаются.
            background: ``True`` — доставка в отдельном фоновом потоке через очередь.
            queue_size: Размер очереди для ``background=True``; при переполнении новые
                записи отбрасываются (см. ``dropped``).
            name: Имя обработчика (видно в ``repr`` и в имени фонового потока).
                По умолчанию — имя функции.

        Raises:
            TypeError: ``func`` нельзя вызвать.

        Пример:
            >>> CallableHandler(print)
            <CallableHandler print (NOTSET)>
        """
        if not callable(func):
            raise TypeError(f"func должна быть вызываемой (как print), получено: {func!r}")

        super().__init__(_level_to_int(level))
        self.func: Callable[[str], Any] = func
        self.background: bool = background
        self.dropped: int = 0
        self.set_name(name or getattr(func, '__name__', type(func).__name__))

        # Флаг «функция сейчас выполняется» — отдельно для каждого потока
        self._delivering = threading.local()

        self._queue: Optional['queue.Queue'] = None
        self._thread: Optional[threading.Thread] = None
        if background:
            self._queue = queue.Queue(maxsize=queue_size)
            self._thread = threading.Thread(
                target=self._worker, name=f"LogOutput-{self.get_name()}", daemon=True,
            )
            self._thread.start()

    def __repr__(self) -> str:
        """Пример: ``<CallableHandler send_tg (ERROR) background>``."""
        mode = ' background' if self.background else ''
        return f"<{type(self).__name__} {self.get_name()} ({logging.getLevelName(self.level)}){mode}>"

    def emit(self, record: logging.LogRecord) -> None:
        """
        Форматирует запись и передаёт её в функцию (сразу или через очередь).

        Args:
            record: Запись лога.

        Returns:
            None

        Пример:
            Вызывается самим ``logging``; напрямую обычно не используется.
        """
        if getattr(self._delivering, 'active', False):
            # Функция сама пишет в лог — не передаём ей её же запись (рекурсия)
            return

        if not hasattr(record, 'plain_message'):
            record.plain_message = record.getMessage()

        try:
            text = self.format(record)
        except Exception:
            self.handleError(record)
            return

        if self._queue is None:
            self._deliver(text, record)
            return

        try:
            self._queue.put_nowait((text, record))
        except queue.Full:
            self.dropped += 1

    def _deliver(self, text: str, record: logging.LogRecord) -> None:
        """
        Вызывает функцию с защитой от исключений и повторного входа.

        Args:
            text: Отформатированная строка.
            record: Исходная запись (нужна ``handleError`` при ошибке).

        Returns:
            None

        Пример:
            >>> h._deliver('текст', record)
        """
        self._delivering.active = True
        try:
            self.func(text)
        except Exception:
            self.handleError(record)
        finally:
            self._delivering.active = False

    def _worker(self) -> None:
        """
        Цикл фонового потока: берёт записи из очереди и доставляет их по одной.

        Останавливается, получив маркер ``_STOP_OUTPUT`` (его кладёт ``close()``).

        Returns:
            None

        Пример:
            Запускается в ``__init__`` при ``background=True``.
        """
        assert self._queue is not None
        while True:
            item = self._queue.get()
            try:
                if item is _STOP_OUTPUT:
                    return
                self._deliver(*item)
            finally:
                self._queue.task_done()

    def flush(self, timeout: Optional[float] = None) -> bool:
        """
        Ждёт, пока фоновый поток доставит всё, что уже в очереди.

        Для ``background=False`` ничего не делает (доставка и так синхронная).

        Args:
            timeout: Максимум ожидания в секундах; ``None`` — ``CLOSE_TIMEOUT``.

        Returns:
            ``True``, если очередь опустела за отведённое время.

        Пример:
            >>> tg.flush(timeout=2)
            True
        """
        if self._queue is None:
            return True
        deadline = time.monotonic() + (self.CLOSE_TIMEOUT if timeout is None else timeout)
        while self._queue.unfinished_tasks:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True

    def close(self) -> None:
        """
        Закрывает обработчик; в фоновом режиме — дожидается остатка очереди и
        останавливает поток (не дольше ``CLOSE_TIMEOUT`` секунд).

        Returns:
            None

        Пример:
            >>> tg.close()
        """
        if self._thread is not None and self._thread.is_alive():
            self.flush()
            try:
                self._queue.put(_STOP_OUTPUT, timeout=self.CLOSE_TIMEOUT)
            except queue.Full:
                pass
            self._thread.join(timeout=self.CLOSE_TIMEOUT)
        super().close()


__all__ = ['RobustRotatingFileHandler', 'CallableHandler']
