# tests/test_file_deletions_review_pass1.py

"""
Тесты исправлений проверки модуля app.utils.file_deletions, проход 1 (2026-10-21).

Номера (FD1 …) — журнал проверок в ``app/utils/IMPLEMENTATION.md``.
"""

from types import SimpleNamespace

import pytest

from app.utils.file_deletions import (
    DeletionContext,
    DeletionType,
    copy_file_to_temp_dir,
    del_file_and_parent_dir,
    delete_empty_directory,
    delete_file_safely,
    ensure_deletions_dict,
    get_deletions_by_type,
    clear_deletions_by_type,
    resolve_photo_path,
    schedule_deletion,
)


def fake_session(active=True):
    """Сессия-заглушка: только is_active (остальное модуль добавляет сам)."""
    return SimpleNamespace(is_active=active)


@pytest.fixture
def file_in_dir(tmp_path):
    """Файл в своей папке: (папка, файл)."""
    folder = tmp_path / 'app_1'
    folder.mkdir()
    target = folder / 'a.png'
    target.write_bytes(b'x')
    return folder, target


# ---------------------------------------------------------------------------
# FD1 — DeletionContext.create без сессии
# ---------------------------------------------------------------------------

def test_fd1_create_without_session_returns_none():
    """Без сессии — None («удалить сразу»), раньше AttributeError."""
    assert DeletionContext.create(None, DeletionType.COMMIT) is None


def test_fd1_create_with_session():
    """С сессией — контекст (истинный)."""
    session = fake_session()
    ctx = DeletionContext.create(session, DeletionType.ROLLBACK)
    assert ctx and ctx.session is session and ctx.deletion_type is DeletionType.ROLLBACK


def test_fd1_instance_logger():
    """Журнал у экземпляра (раньше AttributeError: __slots__)."""
    ctx = DeletionContext(fake_session(), DeletionType.COMMIT)
    assert ctx.logger is DeletionContext._get_logger()


def test_fd1_bool():
    """Контекст без сессии/типа — ложный."""
    assert not DeletionContext(None, DeletionType.COMMIT)
    assert not DeletionContext(fake_session(), None)


def test_fd1_schedule_without_session_deletes_now(file_in_dir):
    """create(None) → schedule_deletion удаляет сразу (с папкой, если опустела)."""
    folder, target = file_in_dir
    ctx = DeletionContext.create(None, DeletionType.COMMIT)
    assert schedule_deletion(str(target), remove_parent_if_empty=True, ctx=ctx) == (True, None)
    assert not target.exists() and not folder.exists()


# ---------------------------------------------------------------------------
# Отложенное удаление
# ---------------------------------------------------------------------------

def test_deferred_on_active_session(file_in_dir):
    """Активная сессия — удаление откладывается (файл на месте, запись в списке)."""
    _, target = file_in_dir
    session = fake_session()
    ctx = DeletionContext(session, DeletionType.COMMIT)
    assert schedule_deletion(str(target), ctx=ctx) == (True, None)
    assert target.exists()
    assert get_deletions_by_type(session, DeletionType.COMMIT) == [
        {'path': str(target), 'remove_parent_if_empty': False, 'force': False}]
    assert get_deletions_by_type(session, DeletionType.ROLLBACK) == []


def test_inactive_session_deletes_now(file_in_dir):
    """Неактивная сессия — удаление сразу."""
    _, target = file_in_dir
    ctx = DeletionContext(fake_session(active=False), DeletionType.COMMIT)
    schedule_deletion(str(target), ctx=ctx)
    assert not target.exists()


def test_rollback_ctx_without_session_does_nothing(file_in_dir):
    """ROLLBACK-контекст без сессии — ничего не удаляется (отката не будет)."""
    _, target = file_in_dir
    ctx = DeletionContext(None, DeletionType.ROLLBACK)
    assert schedule_deletion(str(target), ctx=ctx) == (True, None)
    assert target.exists()


def test_clear_deletions():
    """Очистка списка по типу."""
    session = fake_session()
    schedule_deletion('/x', ctx=DeletionContext(session, DeletionType.COMMIT))
    clear_deletions_by_type(session, DeletionType.COMMIT)
    assert get_deletions_by_type(session, DeletionType.COMMIT) == []


def test_ensure_deletions_dict_migrates_old_list():
    """Старый список _pending_deletions переносится в COMMIT."""
    session = SimpleNamespace(_pending_deletions=[{'path': 'p'}])
    ensure_deletions_dict(session)
    assert session._deletions[DeletionType.COMMIT] == [{'path': 'p'}]
    assert session._pending_deletions is None


# ---------------------------------------------------------------------------
# Немедленное удаление
# ---------------------------------------------------------------------------

def test_delete_file_safely_missing(tmp_path):
    """Нет файла — успех."""
    assert delete_file_safely(str(tmp_path / 'нет')) == (True, None)


def test_delete_file_safely_dir_is_not_deleted(tmp_path):
    """Папка — не удаляется этой функцией."""
    assert delete_file_safely(str(tmp_path)) == (True, None)
    assert tmp_path.exists()


def test_delete_empty_directory_variants(tmp_path):
    """Пустая — удаляется; непустая без force — (False, None); с force — удаляется."""
    empty = tmp_path / 'e'
    empty.mkdir()
    assert delete_empty_directory(str(empty)) == (True, None)
    full = tmp_path / 'f'
    full.mkdir()
    (full / 'x').write_text('1')
    assert delete_empty_directory(str(full)) == (False, None)
    assert delete_empty_directory(str(full), force=True) == (True, None)
    assert not full.exists()
    assert delete_empty_directory('') == (True, None)
    assert delete_empty_directory(str(tmp_path / 'нет')) == (True, None)


def test_del_file_parent_kept_if_not_empty(file_in_dir):
    """Родительская папка не пуста — остаётся."""
    folder, target = file_in_dir
    (folder / 'b.png').write_bytes(b'y')
    del_file_and_parent_dir(str(target), remove_parent_if_empty=True)
    assert not target.exists() and folder.exists()


def test_del_file_missing_and_empty_path(tmp_path):
    """Нет объекта / пустой путь — (False, None)."""
    assert del_file_and_parent_dir(str(tmp_path / 'нет')) == (False, None)
    assert del_file_and_parent_dir('') == (False, None)


# ---------------------------------------------------------------------------
# FD6 — копирование во временную папку
# ---------------------------------------------------------------------------

def test_fd6_copy_creates_target_dir(tmp_path):
    """Папки нет — создаётся (раньше FileNotFoundError)."""
    source = tmp_path / 'src.jpg'
    source.write_bytes(b'img')
    target_dir = tmp_path / 'temp' / 'draft_1'
    name = copy_file_to_temp_dir(str(source), str(target_dir))
    assert name.endswith('.jpg') and len(name) == 32 + 4
    assert (target_dir / name).read_bytes() == b'img'


def test_fd6_copy_unique_name(tmp_path):
    """Своё имя файла."""
    source = tmp_path / 'src.jpg'
    source.write_bytes(b'img')
    assert copy_file_to_temp_dir(str(source), str(tmp_path / 't'), unique_name='a.jpg') == 'a.jpg'


def test_fd6_copy_without_dir_raises(tmp_path):
    """Без папки — RuntimeError."""
    with pytest.raises(RuntimeError):
        copy_file_to_temp_dir(str(tmp_path / 'src.jpg'), '')


def test_fd6_copy_missing_source_raises_and_cleans(tmp_path):
    """Нет исходного файла — исключение, в целевой папке ничего не остаётся."""
    target_dir = tmp_path / 't'
    with pytest.raises(OSError):
        copy_file_to_temp_dir(str(tmp_path / 'нет.jpg'), str(target_dir), unique_name='a.jpg')
    assert not (target_dir / 'a.jpg').exists()


# ---------------------------------------------------------------------------
# resolve_photo_path
# ---------------------------------------------------------------------------

def test_resolve_photo_path(tmp_path):
    """Порядок поиска: абсолютный → временная папка → хранилище."""
    storage = tmp_path / 'photos'
    temp = tmp_path / 'temp'
    (storage / 'app_1').mkdir(parents=True)
    temp.mkdir()
    (storage / 'app_1' / 'a.png').write_bytes(b'1')
    (temp / 'b.png').write_bytes(b'2')
    assert resolve_photo_path(None) is None
    assert resolve_photo_path('app_1/a.png', storage_path=str(storage)) == str(storage / 'app_1' / 'a.png')
    assert resolve_photo_path('b.png', temp_dir=str(temp), storage_path=str(storage)) == str(temp / 'b.png')
    assert resolve_photo_path(str(temp / 'b.png')) == str(temp / 'b.png')
    assert resolve_photo_path(str(temp / 'нет.png')) is None
    assert resolve_photo_path('нет.png', temp_dir=str(temp), storage_path=str(storage)) is None
