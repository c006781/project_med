# tests/test_database_shema/test_database_errors.py

"""
Исключения базы (``app/database/database.py``, Ф1.6.7в, 2026-10-31).

``Database.__init__`` — ошибка драйвера при открытии и обновлении базы →
``DatabaseConnectionError`` (текст — ``migrate.database_error_text``, исходная ошибка — в
цепочке); ``session_scope`` — ``sqlalchemy.exc.IntegrityError`` → ``DbIntegrityError``
(``details`` — таблица, операция, SQL; значения запроса — только при ``log_sql_params``).
Значения запросов (личные данные) по умолчанию скрыты и в трассировке (``hide_parameters``).
На коде до правки тесты исключений падают (там — ошибки SQLAlchemy как есть).
"""

import sqlite3
import traceback
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy import text

import app.database.database as database_module
import app.database.migrate as migrate
from app.database.database_shema.clinic import Patient
from app.exceptions import AppException, DatabaseConnectionError, DbIntegrityError


SECRET = 'Секретова'   # значение запроса, которое не должно попадать в журнал


def db_url(
    path : Path,   # файл базы
) -> str: # URL SQLite для файла
    """URL SQLite для файла (косые — прямые, как в программе)."""
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def db(
    tmp_path : Path,  # папка временной базы
) -> Iterator[database_module.Database]:
    """Временная база с пациентом id=1; журнал — заглушка (видно, что пишет session_scope)."""
    database = database_module.Database(
        db_url(tmp_path / 't.db'),
    )
    with database.session_scope() as session:
        session.add(
            Patient(
                id         = 1,         # ключ
                last_name  = 'Иванов',  # фамилия
                first_name = 'Иван',    # имя
            ),
        )
    database.logger = MagicMock()
    yield database
    database.close()


def add_duplicate(
    database : database_module.Database,   # база с пациентом id=1
) -> DbIntegrityError: # пойманная ошибка повтора ключа
    """Добавляет пациента с тем же ключом (ошибка — при коммите) и возвращает исключение."""
    with pytest.raises(DbIntegrityError) as info:
        with database.session_scope() as session:
            session.add(
                Patient(
                    id         = 1,         # тот же ключ
                    last_name  = SECRET,    # значение запроса
                    first_name = 'Анна',    # имя
                ),
            )
    return info.value


# ---------------------------------------------------------------------------
# session_scope — DbIntegrityError
# ---------------------------------------------------------------------------

def test_duplicate_key_on_commit_is_db_integrity_error(
    db : database_module.Database,   # временная база
) -> None:
    """Повтор ключа при коммите — DbIntegrityError с понятным текстом и подробностями."""
    error = add_duplicate(db)
    assert str(error) == (
        '[6001] Нарушение целостности данных: повтор значения, которое должно быть '
        'уникальным (patients.id)'
    )
    assert error.details['таблица'] == 'patients'
    assert error.details['операция'] == 'INSERT'
    assert error.details['SQL'].startswith('INSERT INTO patients')
    assert 'параметры' not in error.details
    assert isinstance(error.__cause__, sa_exc.IntegrityError)
    assert isinstance(error.original, sqlite3.IntegrityError)
    assert error.original_text == 'sqlite3.IntegrityError: UNIQUE constraint failed: patients.id'


def test_integrity_error_rolled_back(
    db : database_module.Database,   # временная база
) -> None:
    """После ошибки — откат: в базе один пациент, база работает дальше."""
    add_duplicate(db)
    with db.session_scope() as session:
        assert session.execute(text('SELECT count(*) FROM patients')).scalar() == 1


def test_not_null_in_block_flush(
    db : database_module.Database,   # временная база
) -> None:
    """Ошибка flush внутри блока (не при коммите) — тоже DbIntegrityError, с полем."""
    with pytest.raises(DbIntegrityError) as info:
        with db.session_scope() as session:
            session.add(
                Patient(
                    first_name = 'Без фамилии',   # last_name обязателен
                ),
            )
            session.flush()
    assert info.value.detail == 'не заполнено обязательное поле (patients.last_name)'


def test_values_hidden_by_default(
    db : database_module.Database,   # временная база
) -> None:
    """Значений запроса нет ни в log_text, ни в тексте ошибки драйвера, ни в трассировке."""
    error = add_duplicate(db)
    assert SECRET not in error.log_text()
    assert SECRET not in str(error.__cause__)
    assert SECRET not in ''.join(
        traceback.format_exception(
            type(error),           # тип
            error,                 # ошибка
            error.__traceback__,   # трассировка (с цепочкой)
        ),
    )


def test_session_scope_logs_log_text(
    db : database_module.Database,   # временная база (журнал — заглушка)
) -> None:
    """session_scope пишет log_text() исключения приложения: подробности и исходная ошибка."""
    error = add_duplicate(db)
    (message,), _ = db.logger.exception.call_args
    assert message == error.log_text()
    assert '  Подробности: таблица=patients; операция=INSERT; SQL=INSERT INTO patients' in message
    assert '  Исходная ошибка: sqlite3.IntegrityError: UNIQUE constraint failed' in message


def test_values_logged_with_flag(
    tmp_path : Path,   # папка временной базы
) -> None:
    """log_sql_params=True (LOG_SQL_PARAMS) — значения в details и в тексте ошибки драйвера."""
    database = database_module.Database(
        db_url(tmp_path / 't.db'),
        log_sql_params   =   True,   # отладка
    )
    try:
        with database.session_scope() as session:
            session.add(
                Patient(
                    id         = 1,         # ключ
                    last_name  = 'Иванов',  # фамилия
                    first_name = 'Иван',    # имя
                ),
            )
        error = add_duplicate(database)
        assert SECRET in str(error.details['параметры'])
        assert SECRET in error.log_text()
        assert SECRET in str(error.__cause__)
    finally:
        database.close()


def test_other_errors_unchanged(
    db : database_module.Database,   # временная база
) -> None:
    """Другие ошибки драйвера и свои исключения блока — как есть (не DbIntegrityError)."""
    with pytest.raises(sa_exc.OperationalError):
        with db.session_scope() as session:
            session.execute(text('SELECT * FROM no_such_table'))
    with pytest.raises(RuntimeError):
        with db.session_scope() as session:
            raise RuntimeError('своя ошибка')


def test_app_exception_logged_with_log_text(
    db : database_module.Database,   # временная база (журнал — заглушка)
) -> None:
    """Исключение приложения из блока — как есть, в журнале — его log_text()."""
    raised = AppException(
        'сбой',
        details   =   'что делали',   # подробности
    )
    with pytest.raises(AppException) as info:
        with db.session_scope():
            raise raised
    assert info.value is raised
    (message,), _ = db.logger.exception.call_args
    assert message == 'сбой\n  Подробности: что делали'


@pytest.mark.parametrize('message, expected', [
    ('UNIQUE constraint failed: patients.phone',
     'повтор значения, которое должно быть уникальным (patients.phone)'),
    ('NOT NULL constraint failed: patients.last_name',
     'не заполнено обязательное поле (patients.last_name)'),
    ('FOREIGN KEY constraint failed',
     'нет связанной записи или на запись ссылаются другие'),
    ('CHECK constraint failed: age_positive',
     'значение не прошло проверку (age_positive)'),
    ('something else', 'something else'),
])
def test_integrity_detail(
    message  : str,   # сообщение SQLite
    expected : str,   # текст пользователю
) -> None:
    """Сообщения SQLite — понятным текстом; незнакомое — как есть."""
    assert database_module._integrity_detail(message) == expected


@pytest.mark.parametrize('statement, expected', [
    ('INSERT INTO patients (a) VALUES (?)', ('INSERT', 'patients')),
    ('insert or replace into "photos" (a) values (?)', ('INSERT', 'photos')),
    ('UPDATE appointments SET date=? WHERE id = ?', ('UPDATE', 'appointments')),
    ('DELETE FROM photos WHERE id = ?', ('DELETE', 'photos')),
    ('SELECT 1', (None, None)),
    (None, (None, None)),
])
def test_statement_target(
    statement : str,     # текст SQL
    expected  : tuple,   # (операция, таблица)
) -> None:
    """Операция и таблица из текста запроса изменения данных."""
    assert database_module._statement_target(statement) == expected


# ---------------------------------------------------------------------------
# Database.__init__ — DatabaseConnectionError
# ---------------------------------------------------------------------------

def test_locked_db_is_connection_error(
    tmp_path : Path,   # папка временной базы
) -> None:
    """База занята другой копией — DatabaseConnectionError; окно запуска — тот же текст."""
    path = tmp_path / 'locked.db'
    holder = sqlite3.connect(
        str(path),
        isolation_level   =   None,   # BEGIN — вручную
    )
    holder.execute('BEGIN IMMEDIATE')  # блокировка записи — миграции не начать
    try:
        with pytest.raises(DatabaseConnectionError) as info:
            database_module.Database(
                db_url(path) + '?timeout=0.2',   # не ждать 5 с
            )
    finally:
        holder.rollback()
        holder.close()
    error = info.value
    assert 'занята другой копией' in error.detail
    assert str(error).startswith('[6002] Ошибка подключения к БД: База данных занята')
    assert Path(error.details['база']) == path
    assert error.details['операция'] == 'открытие базы и обновление схемы'
    assert 'locked' in error.original_text
    assert migrate.startup_error_text(error) == error.detail   # без кода [6002]


def test_unopenable_db_is_connection_error(
    tmp_path : Path,   # папка временной базы
) -> None:
    """Файл базы не открыть (нет папки) — DatabaseConnectionError «нет доступа»."""
    with pytest.raises(DatabaseConnectionError) as info:
        database_module.Database(
            db_url(tmp_path / 'нет_папки' / 'db.db'),
        )
    assert info.value.detail.startswith('Нет доступа на запись к файлу базы данных')
    assert isinstance(info.value.__cause__, (sa_exc.DatabaseError, sqlite3.Error))


def test_migration_error_not_wrapped(
    tmp_path    : Path,                  # папка временной базы
    monkeypatch : pytest.MonkeyPatch,    # подмена upgrade_database
) -> None:
    """MigrationError — как раньше (свой текст у окна запуска), не DatabaseConnectionError."""

    def refuse(
        engine : object,   # движок
        **kwargs,          # прочие параметры
    ) -> None:
        """Отказ миграции."""
        raise migrate.MigrationError('нет обязательного столбца')

    monkeypatch.setattr(migrate, 'upgrade_database', refuse)
    with pytest.raises(migrate.MigrationError) as info:
        database_module.Database(
            db_url(tmp_path / 'db.db'),
        )
    assert migrate.startup_error_text(info.value).startswith('Базу данных нельзя безопасно')


def test_database_error_text_for_sqlite_error() -> None:
    """Ошибка sqlite3 напрямую (резервная копия — мимо SQLAlchemy) — тот же разбор."""
    assert migrate.database_error_text(
        sqlite3.OperationalError('database is locked'),
    ).startswith('База данных занята')
    assert migrate.database_error_text(
        sqlite3.DatabaseError('file is not a database'),
    ).startswith('Ошибка базы данных при запуске: file is not a database')


def test_log_sql_params_default_off(
    tmp_path : Path,   # папка временной базы
) -> None:
    """По умолчанию значения скрыты (hide_parameters), с флагом — нет."""
    hidden = database_module.Database(
        db_url(tmp_path / 'a.db'),
    )
    shown = database_module.Database(
        db_url(tmp_path / 'b.db'),
        log_sql_params   =   True,   # отладка
    )
    try:
        assert hidden.log_sql_params is False and hidden.engine.hide_parameters is True
        assert shown.log_sql_params is True and shown.engine.hide_parameters is False
    finally:
        hidden.close()
        shown.close()
