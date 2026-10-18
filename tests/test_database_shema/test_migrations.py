# tests/test_database_shema/test_migrations.py

"""
Миграции схемы БД (``app/database/migrate.py`` + Alembic в ``app/database/migrations``).

Все базы — временные файлы. Проверяется: новая база, старые базы без отметки версии
(разных «лет»: без индекса, с лишними столбцами/таблицами, без столбца), отказ на
небезопасном, резервные копии, «модели = миграции», откат, ``Database``/``init_db``.
"""

import datetime
import os

import pytest
from sqlalchemy import MetaData, create_engine, inspect, text

from app.database import Database
from app.database.database_shema.clinic import Base
from app.database.migrate import (
    BASELINE, MigrationError, alembic_config, current_revision, describe_differences,
    head_revision, schema_differences, upgrade_database,
)

APP_TABLES = ('patients', 'appointments', 'appointments_notes', 'photos')


def app_metadata() -> MetaData:
    """Схема моделей ПРИЛОЖЕНИЯ (без тестовых моделей других тестов)."""
    meta = MetaData()
    for name in APP_TABLES:
        Base.metadata.tables[name].to_metadata(meta)
    return meta


def legacy_db(tmp_path, name='legacy.db', drop_index=True, extra_sql=()):
    """Старая база, как её строил create_all (без alembic_version), с данными."""
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}")
    app_metadata().create_all(engine)
    with engine.begin() as conn:
        if drop_index:
            conn.execute(text('DROP INDEX ix_appointment_note_text'))
        conn.execute(text("INSERT INTO appointments_notes (id, text) VALUES (1, 'Чистка')"))
        conn.execute(text("INSERT INTO patients (id, first_name, last_name, comment_id) VALUES (1, 'И', 'П', 1)"))
        conn.execute(text("INSERT INTO appointments (id, patient_id, date) VALUES (1, 1, '2026-01-01')"))
        for sql in extra_sql:
            conn.execute(text(sql))
    return path, engine


def counts(engine):
    with engine.connect() as conn:
        return {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() for t in APP_TABLES}


def backups(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir() if '.bak-' in p.name)


# ---------------------------------------------------------------------------
# Цепочка и «модели = миграции»
# ---------------------------------------------------------------------------

def test_single_head():
    assert head_revision() == BASELINE or head_revision()


def test_models_match_migrations(tmp_path):
    """Модели приложения = схема после всех миграций (иначе — нужна новая миграция)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    upgrade_database(engine)
    diffs = schema_differences(engine, app_metadata())
    assert diffs == [], f"модели расходятся с миграциями: {describe_differences(diffs)} — " \
                        "создайте миграцию (alembic revision --autogenerate)"


# ---------------------------------------------------------------------------
# Новая база
# ---------------------------------------------------------------------------

def test_new_database_created_by_migrations(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    assert upgrade_database(engine) == head_revision()
    assert current_revision(engine) == head_revision()
    assert set(APP_TABLES) <= set(inspect(engine).get_table_names())
    assert backups(tmp_path) == []                         # нечего было сохранять


def test_up_to_date_database_untouched(tmp_path):
    path = tmp_path / 'db.db'
    engine = create_engine(f"sqlite:///{path}")
    upgrade_database(engine)
    before = path.read_bytes()
    upgrade_database(engine)
    assert path.read_bytes() == before and backups(tmp_path) == []


def test_downgrade_to_empty_and_back(tmp_path):
    from alembic import command
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), 'base')
    assert not set(APP_TABLES) & set(inspect(engine).get_table_names())
    upgrade_database(engine)
    assert set(APP_TABLES) <= set(inspect(engine).get_table_names())


# ---------------------------------------------------------------------------
# Старые базы без отметки версии
# ---------------------------------------------------------------------------

def test_legacy_missing_index_repaired_and_stamped(tmp_path):
    path, engine = legacy_db(tmp_path)
    before = counts(engine)
    upgrade_database(engine)
    assert current_revision(engine) == head_revision()
    assert 'ix_appointment_note_text' in {i['name'] for i in inspect(engine).get_indexes('appointments_notes')}
    assert counts(engine) == before                        # данные на месте
    assert len(backups(tmp_path)) == 1                     # копия перед изменением


def test_legacy_identical_schema_only_stamped(tmp_path):
    path, engine = legacy_db(tmp_path, drop_index=False)
    upgrade_database(engine)
    assert current_revision(engine) == head_revision()
    assert backups(tmp_path) == []                         # дописывать было нечего


def test_legacy_extras_kept_with_warning(tmp_path):
    """Лишнее (старый столбец email, посторонняя таблица) не трогается, данные целы."""
    path, engine = legacy_db(tmp_path, extra_sql=(
        "ALTER TABLE patients ADD COLUMN email VARCHAR(100)",
        "UPDATE patients SET email = 'a@b.ru'",
        "CREATE TABLE old_stuff (id INTEGER PRIMARY KEY, x TEXT)",
        "INSERT INTO old_stuff (x) VALUES ('старое')",
    ))
    import app.database.migrate as migrate_module
    got = []
    handler = migrate_module._log.add_output(got.append, formatter='%(levelname)s|%(plain_message)s')
    try:
        upgrade_database(engine)
    finally:
        migrate_module._log.remove_output(handler)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT email FROM patients')).scalar() == 'a@b.ru'
        assert conn.execute(text('SELECT x FROM old_stuff')).scalar() == 'старое'
    warnings = [line for line in got if line.startswith('WARNING|')]
    assert any('email' in w for w in warnings) and any('old_stuff' in w for w in warnings)


def test_legacy_missing_nullable_column_added(tmp_path):
    """Старая база без необязательного столбца (phone) — столбец дописан, данные целы."""
    path = tmp_path / 'old.db'
    engine = create_engine(f"sqlite:///{path}")
    meta = app_metadata()
    meta.tables['patients']._columns.remove(meta.tables['patients'].c.phone)
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))
    upgrade_database(engine)
    assert 'phone' in {c['name'] for c in inspect(engine).get_columns('patients')}
    with engine.connect() as conn:
        assert conn.execute(text('SELECT first_name FROM patients')).scalar() == 'И'


def test_legacy_missing_required_column_refused_untouched(tmp_path):
    """Не хватает ОБЯЗАТЕЛЬНОГО столбца без значения по умолчанию — отказ, база не изменена."""
    path = tmp_path / 'bad.db'
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name VARCHAR(50) NOT NULL)"))
        conn.execute(text("INSERT INTO patients (id, first_name) VALUES (1, 'И')"))
    engine.dispose()
    before = path.read_bytes()
    with pytest.raises(MigrationError, match='last_name'):
        upgrade_database(engine)
    engine.dispose()
    assert path.read_bytes() == before and current_revision(engine) is None


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    """Сбой посреди приведения старой базы — транзакция откатывается, отметки нет."""
    import app.database.migrate as migrate_module
    path, engine = legacy_db(tmp_path)

    def boom(connection, added, where=None):
        connection.execute(text("CREATE TABLE half_done (id INTEGER)"))
        raise RuntimeError('сбой')

    monkeypatch.setattr(migrate_module, '_apply_legacy_repair', boom)
    with pytest.raises(RuntimeError):
        upgrade_database(engine)
    assert current_revision(engine) is None
    assert 'half_done' not in inspect(engine).get_table_names()


# ---------------------------------------------------------------------------
# Database / init_db
# ---------------------------------------------------------------------------

def test_database_class_runs_migrations(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    try:
        assert current_revision(db.engine) == head_revision()
        db.create_tables(recreate=True)
        assert current_revision(db.engine) == head_revision()
        assert set(APP_TABLES) <= set(inspect(db.engine).get_table_names())
    finally:
        db.close()


def test_database_on_legacy_file_keeps_data(tmp_path):
    path, engine = legacy_db(tmp_path, name='clinic.db')
    engine.dispose()
    db = Database(f"sqlite:///{path}")
    try:
        assert counts(db.engine)['patients'] == 1
        assert current_revision(db.engine) == head_revision()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Проверочный проход 1 (M3, M4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('legacy', [True, False])
def test_m3_concurrent_upgrades(tmp_path, legacy):
    """M3: две копии программы одновременно открывают одну базу — обе успешно, одна отметка."""
    import threading
    if legacy:
        path, engine = legacy_db(tmp_path)
        engine.dispose()
    else:
        path = tmp_path / 'new.db'
    errors, results = [], []
    barrier = threading.Barrier(2)

    def run():
        try:
            barrier.wait()
            results.append(upgrade_database(create_engine(f"sqlite:///{path}")))
        except Exception as e:                 # pragma: no cover — должно не случиться
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert errors == [] and results == [head_revision()] * 2
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM alembic_version')).scalar() == 1
    if legacy:
        assert counts(engine)['patients'] == 1
        assert len(backups(tmp_path)) == 1                 # копия — одна, у той копии, что приводила


def test_m4_head_cached():
    from app.database import migrate
    migrate.head_revision.cache_clear()
    calls = []
    real = migrate.ScriptDirectory.from_config
    migrate.ScriptDirectory.from_config = staticmethod(lambda cfg: calls.append(1) or real(cfg))
    try:
        for _ in range(5):
            migrate.head_revision()
    finally:
        migrate.ScriptDirectory.from_config = real
    assert calls == [1]


# ---------------------------------------------------------------------------
# Проверочный проход 2: СЛЕДУЮЩАЯ миграция (0002) — как будет в работе
# ---------------------------------------------------------------------------

MIGRATION_0002 = '''
from alembic import op
import sqlalchemy as sa

revision = '0002_test_change'
down_revision = '0001_baseline'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('patients') as batch:
        batch.add_column(sa.Column('email', sa.String(100), nullable=True))
    op.execute("UPDATE patients SET phone = '' WHERE phone IS NULL")
    with op.batch_alter_table('patients') as batch:      # пересборка таблицы (SQLite)
        batch.alter_column('phone', existing_type=sa.String(20), nullable=False)
    FAIL


def downgrade():
    with op.batch_alter_table('patients') as batch:
        batch.alter_column('phone', existing_type=sa.String(20), nullable=True)
        batch.drop_column('email')
'''


@pytest.fixture
def with_0002(tmp_path, monkeypatch):
    """Копия папки миграций + миграция 0002; fail=True — сбой в конце upgrade()."""
    import shutil
    from app.database import migrate

    def make(fail=False, code=None):
        target = tmp_path / ('migrations_custom' if code else 'migrations_fail' if fail else 'migrations_ok')
        shutil.copytree(migrate.MIGRATIONS_DIR, target, ignore=shutil.ignore_patterns('__pycache__'))
        if code is None:
            code = MIGRATION_0002.replace('    FAIL\n', "    raise RuntimeError('сбой в 0002')\n" if fail else '')
        (target / 'versions' / '0002_test_change.py').write_text(code, encoding='utf-8')
        monkeypatch.setattr(migrate, 'MIGRATIONS_DIR', str(target))
        migrate.head_revision.cache_clear()
        return target

    yield make
    migrate.head_revision.cache_clear()


def test_next_migration_on_baseline_db(tmp_path, with_0002):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)                                  # 0001
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))
    with_0002()
    assert upgrade_database(engine) == '0002_test_change'
    cols = {c['name']: c for c in inspect(engine).get_columns('patients')}
    assert 'email' in cols and cols['phone']['nullable'] is False
    with engine.connect() as conn:
        assert conn.execute(text('SELECT first_name, phone FROM patients')).one() == ('И', '')
    assert len(backups(tmp_path)) == 1                        # копия перед 0002


def test_next_migration_on_legacy_db(tmp_path, with_0002):
    with_0002()
    path, engine = legacy_db(tmp_path)
    assert upgrade_database(engine) == '0002_test_change'
    assert counts(engine)['patients'] == 1
    assert 'email' in {c['name'] for c in inspect(engine).get_columns('patients')}
    # M6: одна копия (-legacy); до исправления — две одинаковые (-legacy и -0001_baseline)
    assert len(backups(tmp_path)) == 1 and backups(tmp_path)[0].endswith('-legacy')


def test_next_migration_on_new_db(tmp_path, with_0002):
    with_0002()
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    assert upgrade_database(engine) == '0002_test_change'


def test_failed_next_migration_rolls_back_everything(tmp_path, with_0002):
    """Сбой в конце 0002 (после пересборки таблицы) — откат всего, база на 0001, данные целы."""
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))
    with_0002(fail=True)
    with pytest.raises(RuntimeError, match='сбой в 0002'):
        upgrade_database(engine)
    assert current_revision(engine) == BASELINE
    cols = {c['name']: c for c in inspect(engine).get_columns('patients')}
    assert 'email' not in cols and cols['phone']['nullable'] is True
    with engine.connect() as conn:
        assert conn.execute(text('SELECT first_name, phone FROM patients')).one() == ('И', None)


def test_next_migration_downgrade(tmp_path, with_0002):
    from alembic import command
    from app.database.migrate import alembic_config
    with_0002()
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), BASELINE)
    assert current_revision(engine) == BASELINE
    assert 'email' not in {c['name'] for c in inspect(engine).get_columns('patients')}


# ---------------------------------------------------------------------------
# Проверочный проход 3: понятные сообщения об ошибках при запуске (M7)
# ---------------------------------------------------------------------------

def test_startup_error_text_for_refused_migration(tmp_path):
    from app.database.migrate import MigrationError, startup_error_text
    path, engine = legacy_db(tmp_path, extra_sql=())
    with engine.begin() as conn:                      # обязательный столбец исчез — отказ
        conn.execute(text('DROP INDEX ix_patient_last_name'))
        conn.execute(text('ALTER TABLE patients DROP COLUMN last_name'))
    with pytest.raises(MigrationError) as info:
        upgrade_database(engine)
    assert startup_error_text(info.value).startswith('Базу данных нельзя безопасно обновить')


def test_startup_error_text_for_locked_db(tmp_path):
    """Другая копия держит блокировку записи — понятное «база занята», а не трассировка."""
    import sqlite3
    from app.database.migrate import startup_error_text
    path, engine = legacy_db(tmp_path)
    holder = sqlite3.connect(str(path), isolation_level=None)
    holder.execute('BEGIN IMMEDIATE')
    try:
        slow = create_engine(f"sqlite:///{path}", connect_args={'timeout': 0.2})
        with pytest.raises(Exception) as info:
            upgrade_database(slow)
        assert 'занята другой копией' in startup_error_text(info.value)
    finally:
        holder.rollback()
        holder.close()


def test_startup_error_text_wrapped_and_unrelated():
    from app.database.migrate import MigrationError, startup_error_text
    try:
        try:
            raise MigrationError('x')
        except MigrationError as inner:
            raise RuntimeError('обёртка') from inner
    except RuntimeError as outer:
        assert startup_error_text(outer).startswith('Базу данных нельзя')
    assert startup_error_text(ValueError('не про базу')) is None


# ---------------------------------------------------------------------------
# Проверочный проход 4: резервная копия базы в режиме WAL (M8)
# ---------------------------------------------------------------------------

def test_backup_includes_wal_changes(tmp_path):
    """
    База в режиме WAL, другая программа держит её открытой — свежие строки лежат в
    файле -wal. Копия файла (shutil.copy2) их теряла; копия через backup-API SQLite — нет.
    """
    import sqlite3
    path, engine = legacy_db(tmp_path)                      # старая база без индекса — будет копия
    engine.dispose()
    writer = sqlite3.connect(str(path))
    writer.execute('PRAGMA journal_mode=WAL')
    reader = sqlite3.connect(str(path))                     # держит базу: WAL не сливается в файл
    reader.execute('SELECT count(*) FROM patients').fetchone()
    with writer:
        writer.execute("INSERT INTO patients (id, first_name, last_name) VALUES (777, 'Свежий', 'В WAL')")
    try:
        upgrade_database(create_engine(f"sqlite:///{path}"))
        copies = backups(tmp_path)
        assert len(copies) == 1
        copy = sqlite3.connect(str(tmp_path / copies[0]))
        try:
            assert copy.execute('SELECT first_name FROM patients WHERE id = 777').fetchone() == ('Свежий',)
        finally:
            copy.close()
    finally:
        reader.close()
        writer.close()


# ---------------------------------------------------------------------------
# Проверочный проход 5: база новее программы (M9), внешние ключи при пересборке (M10)
# ---------------------------------------------------------------------------

def test_db_newer_than_program_refused_untouched(tmp_path, with_0002):
    """Новая версия программы обновила базу до 0002, затем запустили старую (знает до 0001)."""
    import hashlib
    from app.database import migrate
    from app.database.migrate import MigrationError, startup_error_text
    path = tmp_path / 'db.db'
    with_0002()
    engine = create_engine(f"sqlite:///{path}")
    upgrade_database(engine)
    engine.dispose()
    migrate.MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(migrate.__file__)), 'migrations')
    migrate.head_revision.cache_clear()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(MigrationError) as info:
        upgrade_database(create_engine(f"sqlite:///{path}"))
    assert 'новее' in str(info.value)
    assert 'нельзя безопасно обновить' in startup_error_text(info.value)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert backups(tmp_path) == []                         # копию не делали — нечего менять


def test_table_rebuild_with_foreign_keys_on_keeps_children(tmp_path, with_0002):
    """
    Миграция пересобирает patients (batch). Если у приложения включены внешние ключи
    SQLite, удаление старой таблицы при пересборке не должно трогать приёмы.
    """
    from sqlalchemy import event as sa_event
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")

    @sa_event.listens_for(engine, 'connect')
    def _fk_on(dbapi_connection, record):
        dbapi_connection.execute('PRAGMA foreign_keys=ON')

    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))
        conn.execute(text("INSERT INTO appointments (id, patient_id, date) VALUES (1, 1, '2026-10-18')"))
    with_0002()
    upgrade_database(engine)
    assert counts(engine)['appointments'] == 1


ORPHAN_0002 = """
from alembic import op

revision = '0002_test_change'
down_revision = '0001_baseline'


def upgrade():
    op.execute("INSERT INTO appointments (id, patient_id, date) VALUES (50, 999, '2026-10-18')")


def downgrade():
    op.execute("DELETE FROM appointments WHERE id = 50")
"""


def test_migration_leaving_broken_links_rolled_back(tmp_path, with_0002):
    """Ошибочная миграция оставила приём без пациента — отказ, откат, база на 0001."""
    from app.database.migrate import MigrationError
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)
    with_0002(code=ORPHAN_0002)
    with pytest.raises(MigrationError, match='нарушены связи'):
        upgrade_database(engine)
    assert current_revision(engine) == BASELINE
    assert counts(engine)['appointments'] == 0


def test_old_broken_links_do_not_block_migration(tmp_path, with_0002):
    """В старой базе уже есть «висячая» ссылка (ключи не проверялись) — обновлению не мешает."""
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO appointments (id, patient_id, date) VALUES (7, 404, '2026-10-18')"))
    with_0002()
    assert upgrade_database(engine) == '0002_test_change'
    assert counts(engine)['appointments'] == 1



# ---------------------------------------------------------------------------
# Автомиграции: автодостройка, генерация миграции, проверка для сборки
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_migration_settings():
    """Настройки автоматики — общие на процесс: каждый тест начинает с умолчаний."""
    import dataclasses
    from app.database import migrate
    saved = dataclasses.asdict(migrate._settings)
    yield
    migrate.configure(**saved)


@pytest.fixture
def app_models(monkeypatch):
    """Модели по умолчанию — только таблицы приложения (не модели других тестов)."""
    from app.database import migrate
    meta = app_metadata()
    monkeypatch.setattr(migrate, '_default_metadata', lambda: meta)
    return meta


def head_db(tmp_path, name='db.db'):
    """База на последней версии с одним пациентом."""
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))
    return tmp_path / name, engine


def test_drift_missing_index_and_table_repaired(tmp_path):
    """База на последней версии, но индекс и таблицу удалили вручную — дописываются сами."""
    path, engine = head_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX ix_appointment_note_text'))
        conn.execute(text('DROP TABLE photos'))
    assert upgrade_database(engine) == BASELINE
    assert 'photos' in inspect(engine).get_table_names()
    assert 'ix_appointment_note_text' in {i['name'] for i in inspect(engine).get_indexes('appointments_notes')}
    assert counts(engine)['patients'] == 1
    copies = backups(tmp_path)
    assert len(copies) == 1 and copies[0].endswith('-repair')
    upgrade_database(engine)                                  # второй запуск — ничего
    assert len(backups(tmp_path)) == 1


def test_drift_extras_kept_and_no_backup(tmp_path):
    """Лишнее (свой столбец, своя таблица) не трогается; менять нечего — файл не трогается."""
    import hashlib
    path, engine = head_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE patients ADD COLUMN email VARCHAR(100)'))
        conn.execute(text('CREATE TABLE my_stuff (id INTEGER PRIMARY KEY)'))
    engine.dispose()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    upgrade_database(engine)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert backups(tmp_path) == []


def test_drift_missing_required_column_refused(tmp_path):
    import hashlib
    from app.database.migrate import MigrationError
    path, engine = head_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX ix_patient_last_name'))
        conn.execute(text('ALTER TABLE patients DROP COLUMN last_name'))
    engine.dispose()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(MigrationError, match='обязательного столбца patients.last_name'):
        upgrade_database(engine)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_drift_repair_can_be_disabled(tmp_path):
    from app.database.migrate import configure
    path, engine = head_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE photos'))
    configure(repair_drift=False)
    upgrade_database(engine)
    assert 'photos' not in inspect(engine).get_table_names()


INDEXED_COLUMN_0002 = """
from alembic import op
import sqlalchemy as sa

revision = '0002_test_change'
down_revision = '0001_baseline'


def upgrade():
    with op.batch_alter_table('patients') as batch:
        batch.add_column(sa.Column('email', sa.String(100), nullable=True))
        batch.create_index('ix_patient_email', ['email'])


def downgrade():
    with op.batch_alter_table('patients') as batch:
        batch.drop_index('ix_patient_email')
        batch.drop_column('email')
"""


def test_drift_adds_column_before_its_index(tmp_path, with_0002):
    """M12: недостающий столбец С ИНДЕКСОМ — сначала столбец, потом индекс (раньше — наоборот, сбой)."""
    with_0002(code=INDEXED_COLUMN_0002)
    path, engine = head_db(tmp_path)
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX ix_patient_email'))
        conn.execute(text('ALTER TABLE patients DROP COLUMN email'))
    upgrade_database(engine)
    assert 'email' in {c['name'] for c in inspect(engine).get_columns('patients')}
    assert 'ix_patient_email' in {i['name'] for i in inspect(engine).get_indexes('patients')}


NOOP_0002 = """
revision = '0002_test_change'
down_revision = '0001_baseline'


def upgrade():
    pass


def downgrade():
    pass
"""


def _models_with(extra):
    """Модели приложения + изменение ``extra(meta)``."""
    meta = app_metadata()
    extra(meta)
    return meta


def _add_table(meta):
    import sqlalchemy as sa
    sa.Table('prescriptions_auto', meta,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('appointment_id', sa.Integer, sa.ForeignKey('appointments.id'), nullable=False),
             sa.Column('drug', sa.String(100), nullable=False))


def _add_nullable_column(meta):
    import sqlalchemy as sa
    meta.tables['patients'].append_column(sa.Column('email', sa.String(100), nullable=True))


def _rename_column(meta):
    """Переименование phone → mobile: автоматика видит «удалить phone + добавить mobile»."""
    import sqlalchemy as sa
    table = meta.tables['patients']
    phone = table.c.phone
    table._columns.remove(phone)
    table.append_column(sa.Column('mobile', sa.String(20), nullable=True))


def test_pending_changes_empty_for_app_models():
    from app.database.migrate import pending_model_changes
    assert pending_model_changes(app_metadata()) == []


def test_generate_migration_safe_changes(tmp_path, with_0002):
    """Новая таблица + новый необязательный столбец → файл миграции; он применяется, модели = миграции."""
    import glob
    from app.database import migrate
    target = with_0002(code=NOOP_0002)
    models = _models_with(lambda m: (_add_table(m), _add_nullable_column(m)))
    path = migrate.generate_migration(models)
    assert path and os.path.dirname(path) == str(target / 'versions')
    name = os.path.basename(path)
    assert name.startswith('0003_auto_') and name.endswith('.py')
    body = open(path, encoding='utf-8').read()
    assert 'создана автоматически' in body and 'add_table prescriptions_auto' in body
    assert migrate.head_revision() == name[:-3]
    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    upgrade_database(engine)
    assert 'prescriptions_auto' in inspect(engine).get_table_names()
    assert migrate.pending_model_changes(models) == []        # модели = миграции
    assert migrate.generate_migration(models) is None          # повторно — нечего


def test_generate_migration_refuses_unsafe(tmp_path, with_0002):
    """Переименование столбца — отказ, файл не создаётся (автоматика потеряла бы данные)."""
    import glob
    from app.database import migrate
    target = with_0002()
    before = sorted(glob.glob(str(target / 'versions' / '*.py')))
    with pytest.raises(migrate.MigrationError, match='вручную'):
        migrate.generate_migration(_models_with(_rename_column))
    assert sorted(glob.glob(str(target / 'versions' / '*.py'))) == before


def test_autogenerate_on_startup(tmp_path, with_0002, app_models, monkeypatch):
    """configure(autogenerate=True): модели опередили миграции — при открытии базы миграция создаётся и применяется."""
    from app.database import migrate
    with_0002(code=NOOP_0002)
    path, engine = head_db(tmp_path)
    _add_table(app_models)
    migrate.configure(autogenerate=True)
    head = upgrade_database(engine)
    assert head.startswith('0003_auto_')
    assert 'prescriptions_auto' in inspect(engine).get_table_names()
    assert counts(engine)['patients'] == 1
    assert len(backups(tmp_path)) == 1


def test_autogenerate_off_by_default(tmp_path, with_0002, app_models):
    import glob
    target = with_0002(code=NOOP_0002)
    _add_table(app_models)
    before = sorted(glob.glob(str(target / 'versions' / '*.py')))
    upgrade_database(create_engine(f"sqlite:///{tmp_path / 'db.db'}"))
    assert sorted(glob.glob(str(target / 'versions' / '*.py'))) == before


def test_build_check_cli(tmp_path, with_0002, app_models, capsys):
    """python -m app.database.migrate check: 0 — совпадает; 1 — отличается; --generate — файл и 1."""
    import glob
    from app.database import migrate
    target = with_0002(code=NOOP_0002)
    assert migrate.main(['check']) == 0
    _add_table(app_models)
    assert migrate.main(['check']) == 1
    assert 'add_table prescriptions_auto' in capsys.readouterr().out
    assert migrate.main(['check', '--generate']) == 1
    assert len(glob.glob(str(target / 'versions' / '*_auto_*.py'))) == 1
    assert migrate.main(['check']) == 0                        # после генерации — совпадает
    assert migrate.main(['bogus']) == 2


def test_build_check_cli_unsafe(with_0002, app_models, capsys):
    from app.database import migrate
    with_0002(code=NOOP_0002)
    _rename_column(app_models)
    assert migrate.main(['check', '--generate']) == 1
    assert 'вручную' in capsys.readouterr().out


def test_configure_rejects_unknown():
    from app.database.migrate import configure
    with pytest.raises(TypeError):
        configure(auto=True)
