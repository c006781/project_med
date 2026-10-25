# tests/test_exceptions_review_pass3.py

"""
Тесты сверки модуля app.exceptions, проход 3 (М9, 2026-10-25).

Номера (E9 …) — журнал проверок в ``app/exceptions/IMPLEMENTATION.md``. Здесь же — тесты
на то, что проходы 1–2 не покрыли: аргументы по умолчанию и свои коды наследников,
``args``, ловля по базовым классам, примеры в описании пакета.
"""

import doctest
import importlib.util
import os
import pickle

import pytest

import app.exceptions as exceptions_package
from app.exceptions import (
    AppException,
    DatabaseConnectionError,
    DatabaseError,
    DownloadError,
    EntityNotFoundError,
    EntityValidationError,
    IntegrityError,
    PatientNotFoundError,
    PhotoFileError,
    PhotoStorageNoSpaceError,
    PhotoStoragePermissionError,
    SyncError,
    TokenError,
    UploadError,
)

EXCEPTIONS_DIR = os.path.dirname(exceptions_package.__file__)  # папка пакета


# ---------------------------------------------------------------------------
# E9 — код 0 — тоже код
# ---------------------------------------------------------------------------

def test_e9_zero_code_is_shown() -> None:
    """Код 0 выводится (без кода — только None)."""
    assert str(AppException('сбой', code=0)) == '[0] сбой'


def test_e9_none_code_hidden() -> None:
    """Без кода — только текст (как раньше)."""
    assert str(AppException('сбой', code=None)) == 'сбой'


# ---------------------------------------------------------------------------
# E10 — __str__ не падает, если текст не строка
# ---------------------------------------------------------------------------

def test_e10_non_string_message_without_code() -> None:
    """Текст-исключение без кода — str() не бросает TypeError."""
    exc = AppException(OSError('нет файла'))
    assert str(exc) == 'нет файла'


def test_e10_non_string_message_with_code() -> None:
    """С кодом текст и раньше приводился f-строкой."""
    assert str(SyncError(OSError('нет сети'))) == '[5000] нет сети'


def test_e10_message_attribute_kept_as_is() -> None:
    """Атрибут message — то, что передали (не строка)."""
    cause = OSError('нет файла')
    assert AppException(cause).message is cause


# ---------------------------------------------------------------------------
# E11 — pyflakes без замечаний; прежнее имя ConnectionError
# ---------------------------------------------------------------------------

def test_e11_pyflakes_clean() -> None:
    """pyflakes по пакету — без замечаний (раньше: ConnectionError «imported but unused»)."""
    if importlib.util.find_spec('pyflakes') is None:
        pytest.skip('pyflakes не установлен')
    from pyflakes.api import checkRecursive
    from pyflakes.reporter import Reporter

    class _Collect:
        """Сборщик сообщений pyflakes (вместо вывода в консоль)."""

        def __init__(self) -> None:
            """Пустой список сообщений."""
            self.lines: list = []

        def write(
            self,
            text : str,   # строка сообщения
        ) -> None:
            """Запомнить строку (пустые — пропустить)."""
            if text.strip():
                self.lines.append(text)

    out = _Collect()
    count = checkRecursive(
        [EXCEPTIONS_DIR],     # что проверить
        Reporter(out, out),   # куда писать замечания и ошибки
    )
    assert count == 0, out.lines


def test_e11_old_name_same_class() -> None:
    """Прежнее имя — тот же класс, импорт по имени работает."""
    from app.exceptions import ConnectionError as OldName
    assert OldName is DatabaseConnectionError
    assert 'ConnectionError' not in exceptions_package.__all__


# ---------------------------------------------------------------------------
# Непокрытое: аргументы по умолчанию, свои коды, args, ловля по базовым
# ---------------------------------------------------------------------------

def test_cover_entity_validation_custom_code_and_message() -> None:
    """Наследник EntityValidationError задаёт свой код и текст; поле и причина — свои."""
    exc = EntityValidationError('f', 'r', entity='X', code=55, message='плохо')
    assert str(exc) == '[55] плохо'
    assert (exc.field, exc.reason, exc.entity) == ('f', 'r', 'X')


def test_cover_entity_validation_empty_entity() -> None:
    """Пустая таблица — как не указанная (без лишнего пробела в тексте)."""
    assert EntityValidationError('f', 'r', entity='').message == "Ошибка валидации, поле 'f': r."


@pytest.mark.parametrize('cls, default_code', [(SyncError, 5000), (DatabaseError, 6000)])
def test_cover_base_default_and_custom_code(
    cls          : type,   # базовый класс группы
    default_code : int,    # код по умолчанию
) -> None:
    """Базовые SyncError/DatabaseError: код по умолчанию и свой."""
    assert cls('x').code == default_code
    assert cls('x', 7).code == 7
    assert str(cls('x', code=8)) == '[8] x'


@pytest.mark.parametrize('exc, base', [
    (DownloadError('d'), SyncError),
    (UploadError('u'), SyncError),
    (TokenError(), SyncError),
    (IntegrityError('i'), DatabaseError),
    (DatabaseConnectionError('c'), DatabaseError),
    (PhotoStoragePermissionError('p', 'o'), PhotoFileError),
    (PhotoStorageNoSpaceError('p', 'o'), PhotoFileError),
], ids=lambda value: type(value).__name__ if isinstance(value, Exception) else value.__name__)
def test_cover_caught_by_group_base(
    exc  : AppException,   # исключение
    base : type,           # базовый класс группы
) -> None:
    """Исключение ловится базовым классом группы и AppException."""
    with pytest.raises(base):
        raise exc
    assert isinstance(exc, AppException)


@pytest.mark.parametrize('exc, reason', [
    (DownloadError('нет сети'), 'нет сети'),
    (UploadError('нет места'), 'нет места'),
])
def test_cover_sync_reason(
    exc    : SyncError,   # исключение
    reason : str,         # ожидаемая причина
) -> None:
    """У скачивания/загрузки причина доступна отдельно от текста."""
    assert exc.reason == reason


def test_cover_token_error_text_and_code() -> None:
    """TokenError — постоянный текст и код 5003."""
    exc = TokenError()
    assert exc.code == 5003
    assert str(exc) == '[5003] Неверный или отсутствующий токен Яндекс.Диска.'


def test_cover_args_is_message() -> None:
    """args — (текст,) у наследников с данными в __init__ (traceback, logging)."""
    assert PatientNotFoundError(5).args == ('Пациент с идентификатором 5 не найден.',)
    assert PhotoFileError('a', 'чтения', 'нет').args == ("Ошибка чтения файла 'a': нет",)


def test_cover_photo_file_error_zero_errno_not_shown() -> None:
    """errno 0 (не ошибка ОС) в текст не добавляется — поведение сохранено."""
    assert '(код ошибки' not in str(PhotoFileError('a', 'чтения', 'нет', errno=0))


def test_cover_pickle_keeps_extra_attributes() -> None:
    """pickle переносит и атрибуты, добавленные после создания."""
    exc = EntityNotFoundError('X', 1)
    exc.extra = 'доп'
    assert pickle.loads(pickle.dumps(exc)).extra == 'доп'


def test_cover_package_doctests() -> None:
    """Примеры (>>>) в описании пакета верны."""
    result = doctest.testmod(exceptions_package)
    assert result.failed == 0
    assert result.attempted > 0
