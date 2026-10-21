# tests/test_exceptions_review_pass1.py

"""
Тесты исправлений проверки модуля app.exceptions, проход 1 (2026-10-21).

Номера (E1 …) — журнал проверок в ``app/exceptions/IMPLEMENTATION.md``.
"""

import builtins
import copy
import doctest
import pickle

import pytest

import app.exceptions as exceptions_package
import app.exceptions.exceptions_all as exceptions_module
from app.exceptions import (
    AppException,
    AppointmentNoteNotFoundError,
    AppointmentNoteValidationError,
    AppointmentNotFoundError,
    AppointmentValidationError,
    DatabaseConnectionError,
    DatabaseError,
    DownloadError,
    EntityNotFoundError,
    EntityValidationError,
    IntegrityError,
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
)

# (класс, аргументы, код, прежний текст, что не найдено / таблица)
NOT_FOUND = [
    (PatientNotFoundError, 42, 1001, 'Пациент с идентификатором 42 не найден.', 'Пациент'),
    (AppointmentNotFoundError, 7, 2001, 'Приём с идентификатором 7 не найден.', 'Приём'),
    (AppointmentNoteNotFoundError, 3, 3001, 'Заметка приёма с идентификатором 3 не найдена.', 'Заметка приёма'),
    (PhotoNotFoundError, 9, 4001, 'Фотография с идентификатором 9 не найдена.', 'Фотография'),
]

VALIDATION = [
    (PatientValidationError, 1002, "Ошибка валидации поля 'f': r.", 'Пациент'),
    (AppointmentValidationError, 2002, "Ошибка валидации приёма, поле 'f': r.", 'Приём'),
    (AppointmentNoteValidationError, 3002, "Ошибка валидации заметки, поле 'f': r.", 'Заметка'),
    (PhotoValidationError, 4002, "Ошибка валидации фотографии, поле 'f': r.", 'Фотография'),
]


# ---------------------------------------------------------------------------
# E2 — «не найдено»: общая основа, прежние тексты и коды
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cls, entity_id, code, message, entity', NOT_FOUND)
def test_e2_not_found_text_and_code_unchanged(cls, entity_id, code, message, entity):
    """Тексты и коды прежние."""
    exc = cls(entity_id)
    assert exc.code == code
    assert exc.message == message
    assert str(exc) == f'[{code}] {message}'


@pytest.mark.parametrize('cls, entity_id, code, message, entity', NOT_FOUND)
def test_e2_not_found_is_entity_not_found(cls, entity_id, code, message, entity):
    """Любое «не найдено» ловится общим EntityNotFoundError и LookupError."""
    exc = cls(entity_id)
    assert isinstance(exc, EntityNotFoundError)
    assert isinstance(exc, LookupError)
    assert isinstance(exc, AppException)
    assert (exc.entity, exc.entity_id) == (entity, entity_id)


@pytest.mark.parametrize('cls, entity_id, code, message, entity', NOT_FOUND)
def test_e2_not_found_caught_by_base(cls, entity_id, code, message, entity):
    """except EntityNotFoundError ловит исключение конкретной таблицы."""
    with pytest.raises(EntityNotFoundError):
        raise cls(entity_id)


def test_e2_entity_not_found_generic():
    """Общее исключение для новой таблицы — без своего класса."""
    exc = EntityNotFoundError('Назначение', 5)
    assert str(exc) == '[9001] Назначение с идентификатором 5 не найден(а).'
    assert (exc.entity, exc.entity_id, exc.code) == ('Назначение', 5, 9001)


def test_e2_entity_not_found_custom_code_and_message():
    """Наследник может задать свой код и текст."""
    exc = EntityNotFoundError('X', 1, code=77, message='нет X')
    assert str(exc) == '[77] нет X'


# ---------------------------------------------------------------------------
# E5 — ошибка проверки: общая основа, поле и причина доступны
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cls, code, message, entity', VALIDATION)
def test_e5_validation_text_and_code_unchanged(cls, code, message, entity):
    """Тексты и коды прежние."""
    exc = cls('f', 'r')
    assert exc.code == code
    assert exc.message == message


@pytest.mark.parametrize('cls, code, message, entity', VALIDATION)
def test_e5_validation_fields(cls, code, message, entity):
    """Поле, причина, таблица доступны (подсветить поле в окне)."""
    exc = cls('f', 'r')
    assert (exc.field, exc.reason, exc.entity) == ('f', 'r', entity)
    assert isinstance(exc, EntityValidationError)
    assert isinstance(exc, ValueError)


def test_e5_entity_validation_generic():
    """Общее исключение проверки — с таблицей и без."""
    assert str(EntityValidationError('Доза', 'пусто', entity='Назначение')) == (
        "[9002] Ошибка валидации Назначение, поле 'Доза': пусто.")
    assert str(EntityValidationError('Доза', 'пусто')) == "[9002] Ошибка валидации, поле 'Доза': пусто."


def test_e5_value_error_catch_still_works():
    """Интерфейс, ловящий ValueError, по-прежнему ловит ошибки проверки."""
    with pytest.raises(ValueError):
        raise PatientValidationError('first_name', 'пусто')


# ---------------------------------------------------------------------------
# E1 — ConnectionError не перекрывает встроенный
# ---------------------------------------------------------------------------

def test_e1_star_import_does_not_shadow_builtin():
    """import * не перекрывает встроенный ConnectionError."""
    namespace = {}
    exec('from app.exceptions import *', namespace)
    assert 'ConnectionError' not in namespace or namespace['ConnectionError'] is builtins.ConnectionError


def test_e1_old_name_still_importable():
    """Прежнее имя импортируется по имени — тот же класс."""
    from app.exceptions import ConnectionError as OldName
    assert OldName is DatabaseConnectionError


def test_e1_database_connection_error_not_builtin():
    """Ошибка БД — не сетевая (встроенный ConnectionError её не ловит)."""
    exc = DatabaseConnectionError('файл занят')
    assert not isinstance(exc, builtins.ConnectionError)
    assert isinstance(exc, DatabaseError)
    assert str(exc) == '[6002] Ошибка подключения к БД: файл занят'
    assert exc.detail == 'файл занят'


def test_e1_integrity_error():
    """IntegrityError — прежний текст и подробности."""
    exc = IntegrityError('дубликат')
    assert str(exc) == '[6001] Нарушение целостности данных: дубликат'
    assert exc.detail == 'дубликат'


# ---------------------------------------------------------------------------
# E4 — экспорт пакета
# ---------------------------------------------------------------------------

def test_e4_all_exported_names_exist():
    """Всё из __all__ есть в пакете."""
    for name in exceptions_package.__all__:
        assert hasattr(exceptions_package, name), name


def test_e4_every_exception_class_exported():
    """Каждый класс-исключение модуля экспортируется пакетом."""
    classes = {
        name for name, value in vars(exceptions_module).items()
        if isinstance(value, type) and issubclass(value, AppException) and value.__name__ == name
    }
    assert classes <= set(exceptions_package.__all__)


def test_e4_storage_errors():
    """Ошибки хранилища фото — тексты и errno."""
    assert PhotoStoragePermissionError('p', 'записи').errno == 13
    assert PhotoStorageNoSpaceError('p', 'записи').errno == 28
    assert 'недостаточно места' in str(PhotoStorageNoSpaceError('p', 'записи'))


def test_e4_photo_file_error_attributes():
    """PhotoFileError хранит путь, операцию, причину."""
    exc = PhotoFileError('a.png', 'копирования', 'занят')
    assert (exc.path, exc.operation, exc.reason, exc.errno) == ('a.png', 'копирования', 'занят', None)
    assert str(exc) == "[4003] Ошибка копирования файла 'a.png': занят"


# ---------------------------------------------------------------------------
# E8 — pickle / copy
# ---------------------------------------------------------------------------

ALL_SAMPLES = [
    AppException('a', 1),
    EntityNotFoundError('X', 1),
    EntityValidationError('f', 'r', entity='X'),
    PatientNotFoundError(1), PatientValidationError('f', 'r'),
    AppointmentNotFoundError(1), AppointmentValidationError('f', 'r'),
    AppointmentNoteNotFoundError(1), AppointmentNoteValidationError('f', 'r'),
    PhotoNotFoundError(1), PhotoValidationError('f', 'r'),
    PhotoFileError('p', 'o', 'r', errno=5),
    PhotoStoragePermissionError('p', 'o'), PhotoStorageNoSpaceError('p', 'o'),
    SyncError('s'), DownloadError('d'), UploadError('u'), TokenError(),
    DatabaseError('db'), IntegrityError('i'), DatabaseConnectionError('c'),
]


@pytest.mark.parametrize('exc', ALL_SAMPLES, ids=lambda e: type(e).__name__)
def test_e8_pickle_roundtrip(exc):
    """pickle сохраняет класс, текст и атрибуты (раньше PhotoFileError падал TypeError)."""
    restored = pickle.loads(pickle.dumps(exc))
    assert type(restored) is type(exc)
    assert str(restored) == str(exc)
    assert restored.__dict__ == exc.__dict__
    assert restored.args == exc.args


@pytest.mark.parametrize('exc', ALL_SAMPLES, ids=lambda e: type(e).__name__)
def test_e8_copy(exc):
    """copy/deepcopy — то же."""
    for copied in (copy.copy(exc), copy.deepcopy(exc)):
        assert type(copied) is type(exc)
        assert str(copied) == str(exc)


# ---------------------------------------------------------------------------
# E3 — без кода; E7 — примеры в докстрингах
# ---------------------------------------------------------------------------

def test_e3_without_code():
    """Без кода — только текст."""
    assert str(AppException('x')) == 'x'
    assert AppException('x').code is None


def test_e7_doctests():
    """Примеры (>>>) в докстрингах верны (раньше пример EntityNotFoundError падал)."""
    result = doctest.testmod(exceptions_module)
    assert result.failed == 0
    assert result.attempted > 0
