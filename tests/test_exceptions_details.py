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
import errno
import pickle
import sqlite3
import threading
from typing import Any, Callable, Optional

import pytest

import app.exceptions as exceptions_package
from app.exceptions import (
    AppException,
    AppointmentNoteNotFoundError,
    AppointmentNoteValidationError,
    AppointmentNotFoundError,
    AppointmentValidationError,
    DatabaseConnectionError,
    DatabaseError,
    DbIntegrityError,
    DownloadError,
    EntityNotFoundError,
    EntityValidationError,
    PatientNotFoundError,
    PatientValidationError,
    PhotoFileError,
    PhotoNotFoundError,
    PhotoStorageNoSpaceError,
    PhotoStoragePermissionError,
    PhotoValidationError,
    SyncError,
    TokenError,
    UploadError,
    photo_error_from_os_error,
)

# Как создать каждое исключение-наследник прежним вызовом (без новых полей)
SUBCLASS_FACTORIES = [
    (EntityNotFoundError,            ('X', 1)),
    (EntityValidationError,          ('f', 'r')),
    (PatientNotFoundError,           (1,)),
    (PatientValidationError,         ('f', 'r')),
    (AppointmentNotFoundError,       (1,)),
    (AppointmentValidationError,     ('f', 'r')),
    (AppointmentNoteNotFoundError,   (1,)),
    (AppointmentNoteValidationError, ('f', 'r')),
    (PhotoNotFoundError,             (1,)),
    (PhotoValidationError,           ('f', 'r')),
    (PhotoFileError,                 ('p', 'чтения', 'r')),
    (PhotoStoragePermissionError,    ('p', 'записи')),
    (PhotoStorageNoSpaceError,       ('p', 'записи')),
    (SyncError,                      ('s',)),
    (DownloadError,                  ('d',)),
    (UploadError,                    ('u',)),
    (TokenError,                     ()),
    (DatabaseError,                  ('db',)),
    (DbIntegrityError,               ('i',)),
    (DatabaseConnectionError,        ('c',)),
]


def _factory_id(
    value : Any,   # параметр теста: класс или аргументы
) -> str:
    """
    Возвращает имя параметра в выводе pytest: имя класса или ``''`` для аргументов.

    Example:
        >>> _factory_id(SyncError), _factory_id(('s',))
        ('SyncError', '')
    """
    return getattr(value, '__name__', '')


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


# ---------------------------------------------------------------------------
# Наследники — details / original именованными, прежний текст
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cls, args', SUBCLASS_FACTORIES, ids=_factory_id)
def test_subclass_accepts_details_and_original(
    cls  : Callable[..., AppException],   # класс исключения
    args : tuple,                         # прежние позиционные аргументы
) -> None:
    """Каждый наследник принимает details и original; текст и код — как без них."""
    plain = cls(*args)
    source = OSError('исходная')
    exc = cls(
        *args,
        details  = {'таблица': 'patients'},   # подробности
        original = source,                    # исходная ошибка
    )
    assert str(exc) == str(plain)
    assert exc.code == plain.code
    assert exc.args == plain.args
    assert exc.details == {'таблица': 'patients'}
    assert exc.original is source
    assert exc.log_text() == (
        f'{plain}\n'
        '  Подробности: таблица=patients\n'
        '  Исходная ошибка: OSError: исходная'
    )
    restored = pickle.loads(pickle.dumps(exc))
    assert type(restored) is cls
    assert restored.log_text() == exc.log_text()


@pytest.mark.parametrize('cls, args', SUBCLASS_FACTORIES, ids=_factory_id)
def test_subclass_old_call_has_no_extra(
    cls  : Callable[..., AppException],   # класс исключения
    args : tuple,                         # прежние позиционные аргументы
) -> None:
    """Прежний вызов наследника — без подробностей и исходной ошибки."""
    exc = cls(*args)
    assert exc.details is None
    assert exc.original is None
    assert exc.log_text() == str(exc)


# ---------------------------------------------------------------------------
# DbIntegrityError — имя не совпадает с sqlalchemy.exc.IntegrityError
# ---------------------------------------------------------------------------

def test_db_integrity_error_text_and_code() -> None:
    """Прежний текст и код 6001; наследник DatabaseError."""
    exc = DbIntegrityError('дубликат')
    assert str(exc) == '[6001] Нарушение целостности данных: дубликат'
    assert exc.detail == 'дубликат'
    assert isinstance(exc, DatabaseError)


def test_integrity_error_old_name_is_alias() -> None:
    """Прежнее имя IntegrityError — тот же класс, импорт по имени работает, в __all__ нет."""
    from app.exceptions import IntegrityError
    from app.exceptions.exceptions_all import IntegrityError as module_alias
    assert IntegrityError is DbIntegrityError
    assert module_alias is DbIntegrityError
    assert 'IntegrityError' not in exceptions_package.__all__
    assert 'DbIntegrityError' in exceptions_package.__all__


def test_star_import_does_not_shadow_sqlalchemy_integrity_error() -> None:
    """import * не перекрывает IntegrityError драйвера (раньше перекрывал бы)."""
    namespace : dict = {'IntegrityError': sqlite3.IntegrityError}   # «модуль» с драйверным именем
    exec('from app.exceptions import *', namespace)
    assert namespace['IntegrityError'] is sqlite3.IntegrityError
    assert namespace['DbIntegrityError'] is DbIntegrityError


# ---------------------------------------------------------------------------
# photo_error_from_os_error — ошибка ОС при работе с файлом фото
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('source, cls', [
    (PermissionError(errno.EACCES, 'Permission denied'), PhotoStoragePermissionError),
    (PermissionError(errno.EPERM, 'Operation not permitted'), PhotoStoragePermissionError),
    (OSError(errno.EACCES, 'Permission denied'), PhotoStoragePermissionError),
    (OSError(errno.ENOSPC, 'No space left on device'), PhotoStorageNoSpaceError),
], ids=['EACCES', 'EPERM', 'OSError-EACCES', 'ENOSPC'])
def test_photo_error_storage_classes(
    source : OSError,                         # ошибка ОС
    cls    : Callable[..., PhotoFileError],   # ожидаемый класс
) -> None:
    """Нет прав / нет места — свои классы; исходная ошибка — в original."""
    exc = photo_error_from_os_error(
        'a.png',            # файл
        'копирования',      # операция
        source,             # ошибка ОС
    )
    assert type(exc) is cls
    assert exc.path == 'a.png'
    assert exc.operation == 'копирования'
    assert exc.original is source


def test_photo_error_other_errno() -> None:
    """Прочие ошибки ОС — PhotoFileError с текстом ОС и её errno."""
    source = FileNotFoundError(errno.ENOENT, 'No such file or directory', 'a.png')
    exc = photo_error_from_os_error(
        'a.png',                            # файл
        'чтения',                           # операция
        source,                             # ошибка ОС
        details = {'приём': 5},             # подробности
    )
    assert type(exc) is PhotoFileError
    assert exc.errno == errno.ENOENT
    assert exc.reason == 'No such file or directory'
    assert str(exc) == (
        "[4003] Ошибка чтения файла 'a.png': No such file or directory "
        f"(код ошибки: {errno.ENOENT})"
    )
    assert exc.details == {'приём': 5}
    assert exc.original is source


def test_photo_error_without_errno() -> None:
    """Ошибка ОС без errno — текст самой ошибки, без кода."""
    source = OSError('диск отключён')
    exc = photo_error_from_os_error(
        'a.png',        # файл
        'записи',       # операция
        source,         # ошибка ОС
    )
    assert type(exc) is PhotoFileError
    assert exc.errno is None
    assert str(exc) == "[4003] Ошибка записи файла 'a.png': диск отключён"
