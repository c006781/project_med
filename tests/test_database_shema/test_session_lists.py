# tests/test_database_shema/test_session_lists.py

"""
Списки отложенных удалений и действий сессии (``app/database/database.py``, ТД-9).

``Database.Session`` — ``scoped_session``: одна сессия на поток, ``close()`` её не заменяет,
списки ``session._deletions`` / ``session._actions`` живут дольше транзакции. Транзакция
закончилась — список противоположного события должен быть отброшен, иначе его выполнит
следующая, чужая транзакция того же потока. Основные случаи (FD9, DA5) — в
``tests/test_file_deletions_review_pass2.py``, ``tests/test_deferred_actions_review_pass2.py``;
здесь — остальные.
"""

from pathlib import Path
from typing import Iterator, List
from unittest.mock import patch

import pytest
from sqlalchemy import text

import app.database.database as database_module
import app.utils.deferred_actions as actions_module
from app.utils.deferred_actions import ActionContext, ActionType, add_deferred_action
from app.utils.file_deletions import DeletionContext, DeletionType, schedule_deletion


@pytest.fixture
def no_qt_app() -> Iterator[None]:
    """Без приложения Qt — действия выполняются сразу (а не в цикле событий)."""
    with patch.object(
        actions_module.QCoreApplication,  # класс приложения Qt
        'instance',                       # «есть ли приложение»
        return_value = None,              # нет
    ):
        yield


@pytest.fixture
def db(
    tmp_path : Path,  # папка временной базы
) -> Iterator[database_module.Database]:
    """Временная база (scoped_session — одна сессия на поток, как в программе)."""
    database = database_module.Database(
        f"sqlite:///{(tmp_path / 't.db').as_posix()}",
    )
    yield database
    database.close()


def test_rollback_actions_dropped_after_commit(
    no_qt_app,                          # действия — сразу
    db : database_module.Database,      # временная база
) -> None:
    """Действие «при откате» из закоммиченной транзакции не выполняется следующим откатом."""
    done: List[str] = []

    with db.session_scope() as session:
        session.execute(text('SELECT 1'))
        add_deferred_action(
            ActionContext(session, ActionType.ROLLBACK), # при откате
            done.append,                                 # действие
            ('закоммиченная',),                          # его аргументы
        )

    with pytest.raises(RuntimeError):
        with db.session_scope() as session:  # другая транзакция откатывается
            session.execute(text('SELECT 1'))
            raise RuntimeError('другая ошибка')

    assert done == [], 'действие закоммиченной транзакции выполнено чужим откатом'


def test_commit_deletion_dropped_after_rollback_without_queries(
    tmp_path : Path,                      # папка файлов
    db       : database_module.Database,  # временная база
) -> None:
    """
    Откат блока, где не было ни одного запроса к БД (транзакция не начиналась, SQLAlchemy
    не вызывает ``after_rollback``), — удаление «после коммита» тоже отбрасывается.
    """
    photo = tmp_path / 'a.png'
    photo.write_bytes(b'1')

    with pytest.raises(RuntimeError):
        with db.session_scope() as session:
            schedule_deletion(
                str(photo),
                ctx = DeletionContext(session, DeletionType.COMMIT),
            )
            raise RuntimeError('ошибка до запросов')

    with db.session_scope() as session:  # другая, успешная транзакция того же потока
        session.execute(text('SELECT 1'))

    assert photo.exists(), 'файл удалён коммитом чужой транзакции'


def test_failed_commit_deletion_retried_after_foreign_rollback(
    tmp_path : Path,                      # папка файлов
    db       : database_module.Database,  # временная база
) -> None:
    """
    Неудавшееся удаление после своего коммита остаётся для повторной попытки и переживает
    чужой откат: повтор — при следующем коммите (как было до исправления ТД-9).
    """
    photo = tmp_path / 'a.png'
    photo.write_bytes(b'1')
    real_delete = database_module.del_file_and_parent_dir
    calls: List[str] = []

    def delete_failing_first(
        file_path : str,  # удаляемый файл
        **kwargs,         # остальные параметры удаления
    ):
        """Первая попытка — ошибка (файл занят), дальше — настоящее удаление."""
        calls.append(file_path)
        if len(calls) == 1:
            raise PermissionError('файл занят')
        return real_delete(
            file_path = file_path,
            **kwargs,
        )

    with patch.object(
        database_module,           # модуль обработчиков
        'del_file_and_parent_dir', # удаление файла
        delete_failing_first,      # первая попытка — ошибка
    ):
        with db.session_scope() as session:
            session.execute(text('SELECT 1'))
            schedule_deletion(
                str(photo),
                ctx = DeletionContext(session, DeletionType.COMMIT),
            )
        assert photo.exists()  # первая попытка не удалась

        with pytest.raises(RuntimeError):
            with db.session_scope() as session:  # чужой откат
                session.execute(text('SELECT 1'))
                raise RuntimeError('другая ошибка')

        with db.session_scope() as session:  # следующий коммит — повтор
            session.execute(text('SELECT 1'))

    assert calls == [str(photo), str(photo)]
    assert not photo.exists(), 'повтор неудавшегося удаления потерян'
