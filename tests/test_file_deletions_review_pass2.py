# tests/test_file_deletions_review_pass2.py

"""
Тесты проверки модуля app.utils.file_deletions, проход 2 (2026-10-25).

Номера (FD7 …) — журнал проверок в ``app/utils/IMPLEMENTATION.md``.
"""

from pathlib import Path

import pytest
from sqlalchemy import text

from app.utils.file_deletions import (
    DeletionContext,
    DeletionType,
    copy_file_to_temp_dir,
    del_file_and_parent_dir,
    schedule_deletion,
)


# ---------------------------------------------------------------------------
# FD7 — родительская папка удаляется только пустой, даже при force=True
# ---------------------------------------------------------------------------

def test_fd7_force_does_not_remove_non_empty_parent(tmp_path: Path) -> None:
    """
    force=True + remove_parent_if_empty=True: удаляется папка, а её родитель — только пустой.

    Раньше родитель удалялся с ``force=force`` — рекурсивно, вместе с соседними файлами.
    """
    parent = tmp_path / 'temp'
    draft = parent / 'draft_1'
    draft.mkdir(parents=True)
    (draft / 'a.png').write_bytes(b'1')
    neighbour = parent / 'draft_2' / 'b.png'
    neighbour.parent.mkdir()
    neighbour.write_bytes(b'2')

    del_file_and_parent_dir(
        str(draft),                    # удаляемая папка
        remove_parent_if_empty = True, # родителя — только пустым
        force                  = True, # саму папку — со всем содержимым
    )

    assert not draft.exists()
    assert neighbour.exists(), 'соседняя папка родителя удалена вместе с ним'


def test_fd7_force_removes_empty_parent(tmp_path: Path) -> None:
    """Родитель, ставший пустым, удаляется и при force=True."""
    parent = tmp_path / 'temp'
    draft = parent / 'draft_1'
    draft.mkdir(parents=True)
    (draft / 'a.png').write_bytes(b'1')

    result = del_file_and_parent_dir(
        str(draft),                    # удаляемая папка
        remove_parent_if_empty = True, # родитель станет пустым
        force                  = True, # саму папку — со всем содержимым
    )

    assert result == (True, None)
    assert not parent.exists()


# ---------------------------------------------------------------------------
# FD8 — ошибка копирования: созданная пустая папка удаляется (remove_parent_if_empty)
# ---------------------------------------------------------------------------

def test_fd8_copy_error_removes_created_empty_dir(tmp_path: Path) -> None:
    """Нет исходного файла, remove_parent_if_empty=True — созданная папка не остаётся."""
    target_dir = tmp_path / 'temp' / 'draft_1'

    with pytest.raises(OSError):
        copy_file_to_temp_dir(
            str(tmp_path / 'нет.jpg'),     # исходного файла нет
            str(target_dir),               # папку создаст сама функция
            remove_parent_if_empty = True, # пустую — удалить
            unique_name            = 'a.jpg',
        )

    assert not target_dir.exists()


def test_fd8_copy_error_keeps_non_empty_dir(tmp_path: Path) -> None:
    """Папка с другими файлами при ошибке копирования остаётся."""
    target_dir = tmp_path / 'draft_1'
    target_dir.mkdir()
    (target_dir / 'old.jpg').write_bytes(b'1')

    with pytest.raises(OSError):
        copy_file_to_temp_dir(
            str(tmp_path / 'нет.jpg'),     # исходного файла нет
            str(target_dir),               # папка уже есть, не пуста
            remove_parent_if_empty = True, # пустую — удалить (эта не пуста)
            unique_name            = 'a.jpg',
        )

    assert (target_dir / 'old.jpg').exists()


def test_fd8_copy_error_without_flag_keeps_dir(tmp_path: Path) -> None:
    """remove_parent_if_empty=False (по умолчанию) — папка остаётся, как раньше."""
    target_dir = tmp_path / 'draft_1'

    with pytest.raises(OSError):
        copy_file_to_temp_dir(
            str(tmp_path / 'нет.jpg'), # исходного файла нет
            str(target_dir),           # папку создаст сама функция
            unique_name = 'a.jpg',     # имя копии
        )

    assert target_dir.is_dir()


def test_fd8_copy_error_deferred_until_rollback(tmp_path: Path) -> None:
    """С контекстом ROLLBACK удаление пустой папки откладывается в список сессии."""

    class FakeSession:
        """Сессия-заглушка: активна, списки удалений модуль добавит сам."""
        is_active = True

    session = FakeSession()
    target_dir = tmp_path / 'draft_1'

    with pytest.raises(OSError):
        copy_file_to_temp_dir(
            str(tmp_path / 'нет.jpg'),     # исходного файла нет
            str(target_dir),               # папку создаст сама функция
            remove_parent_if_empty = True, # пустую — удалить
            unique_name            = 'a.jpg',
            ctx                    = DeletionContext(session, DeletionType.ROLLBACK),
        )

    assert target_dir.is_dir()  # отложено — ещё на месте
    paths = [item['path'] for item in session._deletions[DeletionType.ROLLBACK]]
    assert str(target_dir) in paths


# ---------------------------------------------------------------------------
# FD9 — списки отложенных удалений переживают свою транзакцию (вне территории:
# обработчики app/database/database.py). Тесты фиксируют ошибку; strict — когда
# обработчики исправят, тест сообщит XPASS → снять пометку.
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path: Path):
    """Временная база (scoped_session — одна сессия на поток, как в программе)."""
    from app.database.database import Database

    database = Database(
        f"sqlite:///{(tmp_path / 't.db').as_posix()}",
    )
    yield database
    database.close()


@pytest.mark.xfail(
    strict = True,
    reason = 'FD9: after_rollback не очищает список COMMIT (app/database/database.py)',
)
def test_fd9_commit_list_dropped_after_rollback(
    tmp_path : Path,  # папка файлов
    db,               # временная база
) -> None:
    """Удаление «после коммита» из откатившейся транзакции не выполняется следующим коммитом."""
    photo = tmp_path / 'a.png'
    photo.write_bytes(b'1')

    with pytest.raises(RuntimeError):
        with db.session_scope() as session:
            session.execute(text('SELECT 1'))
            schedule_deletion(
                str(photo),
                ctx = DeletionContext(session, DeletionType.COMMIT),
            )
            raise RuntimeError('ошибка сохранения')

    with db.session_scope() as session:  # другая, успешная транзакция того же потока
        session.execute(text('SELECT 1'))

    assert photo.exists(), 'файл удалён коммитом чужой транзакции'


@pytest.mark.xfail(
    strict = True,
    reason = 'FD9: after_commit не очищает список ROLLBACK (app/database/database.py)',
)
def test_fd9_rollback_list_dropped_after_commit(
    tmp_path : Path,  # папка файлов
    db,               # временная база
) -> None:
    """Удаление «при откате» из закоммиченной транзакции не выполняется следующим откатом."""
    photo = tmp_path / 'new.png'
    photo.write_bytes(b'1')

    with db.session_scope() as session:
        session.execute(text('SELECT 1'))
        schedule_deletion(
            str(photo),
            ctx = DeletionContext(session, DeletionType.ROLLBACK),
        )

    with pytest.raises(RuntimeError):
        with db.session_scope() as session:  # другая транзакция откатывается
            session.execute(text('SELECT 1'))
            raise RuntimeError('другая ошибка')

    assert photo.exists(), 'закоммиченный файл удалён откатом чужой транзакции'
