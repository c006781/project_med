# tests/test_exceptions_details.py

"""
Тесты трёх уровней текста исключений приложения (Ф1.6.8а, 2026-10-31).

``message`` — текст пользователю (``str(exc)``, как раньше); ``details`` — что делали (для
журнала); ``original`` — исходная ошибка: явно (``original=exc``) или из цепочки
``raise … from`` до первопричины; ``original_text`` — её тип и текст; ``log_text()`` — всё
вместе. Старые вызовы без новых полей ведут себя как раньше; ``pickle`` / ``copy`` не
падают и на исходной ошибке, которая сама не сериализуется.
"""

import copy
import pickle
import sqlite3
import threading
from typing import Optional

import pytest

from app.exceptions import (
    AppException,
)


def _raise_chain() -> AppException:
    """
    Возвращает исключение приложения, поднятое по цепочке KeyError → OSError → AppException.

    Example:
        >>> type(_raise_chain().__cause__).__name__
        'OSError'
    """
    try:
        try:
            try:
                raise KeyError('id')
            except KeyError as key_exc:
                raise OSError('нет файла') from key_exc
        except OSError as os_exc:
            raise AppException(
                'Не удалось открыть',   # текст пользователю
                code = 7,               # код
            ) from os_exc
    except AppException as app_exc:
        return app_exc
    raise AssertionError('исключение не поднято')


class _Unpicklable(Exception):
    """Исключение с атрибутом, который pickle не сохраняет (блокировка)."""

    def __init__(
        self,
        text : str,   # текст ошибки
    ) -> None:
        """
        Создаёт исключение с блокировкой внутри.

        Example:
            >>> str(_Unpicklable('сбой'))
            'сбой'
        """
        super().__init__(text)
        self.lock = threading.Lock()


# ---------------------------------------------------------------------------
# Старые вызовы — как раньше
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('code', [None, 7])
def test_old_call_unchanged(
    code : Optional[int],   # код ошибки
) -> None:
    """Без новых полей: текст, args и журнал — как раньше, новых сведений нет."""
    exc = AppException(
        'сбой',         # текст
        code = code,    # код
    )
    assert str(exc) == ('сбой' if code is None else '[7] сбой')
    assert exc.args == ('сбой',)
    assert exc.details is None
    assert exc.original is None
    assert exc.original_text is None
    assert exc.log_text() == str(exc)


def test_positional_code_still_works() -> None:
    """Код вторым позиционным параметром — как в старых вызовах."""
    assert str(AppException('сбой', 5)) == '[5] сбой'


# ---------------------------------------------------------------------------
# details
# ---------------------------------------------------------------------------

def test_details_text_not_in_message() -> None:
    """Подробности не попадают в текст пользователю, только в журнал."""
    exc = AppException(
        'Не удалось сохранить',                   # текст
        code    = 7,                              # код
        details = 'таблица patients, id=5',       # подробности
    )
    assert str(exc) == '[7] Не удалось сохранить'
    assert exc.details == 'таблица patients, id=5'
    assert exc.log_text() == (
        '[7] Не удалось сохранить\n'
        '  Подробности: таблица patients, id=5'
    )


def test_details_mapping_in_log_text() -> None:
    """Словарь подробностей — «ключ=значение» через «; » в порядке ключей."""
    exc = AppException(
        'сбой',                                                    # текст
        details = {'таблица': 'patients', 'sql': 'INSERT …'},      # подробности
    )
    assert exc.details == {'таблица': 'patients', 'sql': 'INSERT …'}
    assert exc.log_text() == 'сбой\n  Подробности: таблица=patients; sql=INSERT …'


@pytest.mark.parametrize('empty', ['', {}])
def test_empty_details_skipped(
    empty : object,   # пустые подробности
) -> None:
    """Пустые подробности в журнал не выводятся."""
    exc = AppException(
        'сбой',             # текст
        details = empty,    # подробности
    )
    assert exc.log_text() == 'сбой'


# ---------------------------------------------------------------------------
# original — явно
# ---------------------------------------------------------------------------

def test_explicit_original_builtin() -> None:
    """Встроенная ошибка — тип без модуля."""
    source = ValueError('плохое число')
    exc = AppException(
        'Неверный ввод',        # текст
        original = source,      # исходная ошибка
    )
    assert exc.original is source
    assert exc.original_text == 'ValueError: плохое число'
    assert str(exc) == 'Неверный ввод'


def test_explicit_original_qualified_type() -> None:
    """Не встроенная ошибка — тип с модулем (видно, откуда она)."""
    exc = AppException(
        'Запись уже есть',                                              # текст
        original = sqlite3.IntegrityError('UNIQUE constraint failed'),  # исходная ошибка
    )
    assert exc.original_text == 'sqlite3.IntegrityError: UNIQUE constraint failed'


def test_original_without_text() -> None:
    """Исходная ошибка без текста — только тип."""
    exc = AppException(
        'сбой',                     # текст
        original = KeyError(),      # исходная ошибка
    )
    assert exc.original_text == 'KeyError'


def test_explicit_original_beats_chain() -> None:
    """Явная исходная ошибка главнее цепочки и берётся как есть (без спуска по ней)."""
    explicit = ValueError('явная')
    explicit.__cause__ = KeyError('глубже')
    try:
        try:
            raise OSError('из цепочки')
        except OSError as os_exc:
            raise AppException(
                'сбой',                 # текст
                original = explicit,    # исходная ошибка
            ) from os_exc
    except AppException as exc:
        assert exc.original is explicit


# ---------------------------------------------------------------------------
# original — из цепочки
# ---------------------------------------------------------------------------

def test_original_from_chain_root_cause() -> None:
    """raise … from — исходная ошибка — первопричина цепочки (KeyError), а не ближняя."""
    exc = _raise_chain()
    assert isinstance(exc.original, KeyError)
    assert exc.original_text == "KeyError: 'id'"


def test_original_from_implicit_context() -> None:
    """Исключение, поднятое при обработке другого (без from), — исходная из __context__."""
    try:
        try:
            raise OSError('занято')
        except OSError:
            raise AppException('Не удалось')
    except AppException as exc:
        assert isinstance(exc.original, OSError)
        assert exc.original_text == 'OSError: занято'


def test_original_from_none_is_hidden() -> None:
    """raise … from None — исходную ошибку скрыли намеренно."""
    try:
        try:
            raise OSError('занято')
        except OSError:
            raise AppException('Не удалось') from None
    except AppException as exc:
        assert exc.original is None
        assert exc.log_text() == 'Не удалось'


def test_original_chain_cycle_does_not_hang() -> None:
    """Зацикленная цепочка (собрана вручную) не зависает."""
    first = ValueError('первая')
    second = KeyError('вторая')
    first.__cause__ = second
    second.__cause__ = first
    exc = AppException('сбой')
    exc.__cause__ = first
    assert exc.original in (first, second)


# ---------------------------------------------------------------------------
# log_text
# ---------------------------------------------------------------------------

def test_log_text_full() -> None:
    """Журнал: код и текст, подробности, исходная ошибка — по строке."""
    exc = AppException(
        'Нарушение целостности данных: дубликат',                       # текст
        code     = 6001,                                                # код
        details  = {'таблица': 'patients'},                             # подробности
        original = sqlite3.IntegrityError('UNIQUE constraint failed'),  # исходная ошибка
    )
    assert exc.log_text() == (
        '[6001] Нарушение целостности данных: дубликат\n'
        '  Подробности: таблица=patients\n'
        '  Исходная ошибка: sqlite3.IntegrityError: UNIQUE constraint failed'
    )


def test_log_text_non_string_message() -> None:
    """Текст не строкой — журнал не падает (как __str__, E10)."""
    exc = AppException(
        OSError('нет файла'),           # текст не строкой
        details = 'путь a.png',         # подробности
    )
    assert exc.log_text() == 'нет файла\n  Подробности: путь a.png'


# ---------------------------------------------------------------------------
# pickle / copy
# ---------------------------------------------------------------------------

def test_pickle_keeps_details_and_original_text() -> None:
    """pickle: подробности и текст исходной ошибки сохраняются, сама ошибка — нет."""
    exc = AppException(
        'сбой',                                 # текст
        code     = 7,                           # код
        details  = 'таблица patients',          # подробности
        original = _Unpicklable('блокировка'),  # не сериализуется
    )
    restored = pickle.loads(pickle.dumps(exc))
    assert str(restored) == '[7] сбой'
    assert restored.details == 'таблица patients'
    assert restored.original is None
    assert restored.original_text == f'{__name__}._Unpicklable: блокировка'
    assert restored.log_text() == exc.log_text()


def test_pickle_keeps_original_text_from_chain() -> None:
    """pickle: исходная ошибка из цепочки (её pickle не переносит) — текстом."""
    exc = _raise_chain()
    restored = pickle.loads(pickle.dumps(exc))
    assert restored.original_text == "KeyError: 'id'"
    assert restored.log_text() == exc.log_text()


def test_pickle_details_mapping_values_to_repr() -> None:
    """pickle: значения словаря сложнее строки / числа — их repr, простые — как есть."""
    marker = threading.Lock()
    exc = AppException(
        'сбой',                                                        # текст
        details = {'id': 5, 'путь': 'a.png', 'нет': None, 'объект': marker},  # подробности
    )
    restored = pickle.loads(pickle.dumps(exc))
    assert restored.details == {'id': 5, 'путь': 'a.png', 'нет': None, 'объект': repr(marker)}
    assert exc.details['объект'] is marker   # у исходного — без изменений


def test_copy_keeps_log_text() -> None:
    """copy / deepcopy — тот же журнал, исходная ошибка — текстом."""
    exc = AppException(
        'сбой',                                 # текст
        details  = {'id': 5},                   # подробности
        original = _Unpicklable('блокировка'),  # не копируется deepcopy
    )
    for copied in (copy.copy(exc), copy.deepcopy(exc)):
        assert copied.log_text() == exc.log_text()
