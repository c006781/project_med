# tests/test_database_shema/test_sqlite_triggers.py

"""
Встроенные триггеры SQLite и миграции (``app/database/sqlite_triggers.py``, ``migrate.py``).

Все базы — временные файлы; миграции с триггерами — во временной копии папки миграций (в
настоящих триггеров пока нет). Проверяется: сравнение с описанием и базой, генератор миграций
(появление, изменение, удаление), новая и старая база, автодостройка, настоящая пересборка
таблицы (``batch_alter_table(recreate='always')``, SQLite 3.34 без ``DROP COLUMN``), откат
транзакции, проверка описания при открытии, устаревание объектов ORM.
"""

import dataclasses
import hashlib
import shutil
from typing import Dict, Iterator, List

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import MetaData, create_engine, inspect, text

from app.database import Database, Patient, migrate
from app.database.database_shema.clinic import Base
from app.database.migrate import (
    MigrationError,
    alembic_config,
    check_trigger_definitions,
    current_revision,
    describe_differences,
    generate_migration,
    head_revision,
    pending_model_changes,
    schema_differences,
    unsafe_changes,
    upgrade_database,
)
from app.database.sqlite_triggers import (
    drop_trigger_sql,
    keep_triggers,
    normalize_sql,
    read_triggers,
    trigger_errors,
)
from app.exceptions import DbIntegrityError
from app.schema.define import TRIGGERS_INFO, trigger

APP_TABLES = ('patients', 'appointments', 'appointments_notes', 'photos', 'photo_files')
REAL_HEAD = head_revision()

GUARD = trigger(
    'trg_guard',                                            # имя
    'before_delete',                                        # перед удалением
    "SELECT RAISE(ABORT, 'пациента удалять нельзя');",      # запрет
)
GUARD_SQL = GUARD.create_sql('patients')
GUARD_V2 = trigger(
    'trg_guard',                                            # то же имя
    'before_delete',                                        # перед удалением
    "SELECT RAISE(ABORT, 'другой текст запрета');",         # другое правило
).create_sql('patients')

MIGRATION = """
from alembic import op
import sqlalchemy as sa
from app.database.sqlite_triggers import keep_triggers

revision = '{revision}'
down_revision = '{down}'
branch_labels = None
depends_on = None


def upgrade():
{upgrade}


def downgrade():
    pass
"""


def app_metadata() -> MetaData: # копия моделей приложения
    """Модели приложения (без тестовых моделей других тестов)."""
    meta = MetaData(naming_convention=Base.metadata.naming_convention)
    for name in APP_TABLES:
        Base.metadata.tables[name].to_metadata(meta)
    return meta


def with_triggers(
    described : Dict[str, Dict[str, str]],   # таблица → имя → текст
) -> MetaData: # модели приложения с триггерами в описании
    meta = app_metadata()
    for table, triggers in described.items():
        meta.tables[table].info[TRIGGERS_INFO] = dict(triggers)
    return meta


def create_op(
    sql : str,   # текст CREATE TRIGGER
) -> str: # строка тела миграции
    return f"    op.get_bind().exec_driver_sql({sql!r})"


@pytest.fixture(autouse=True)
def _restore_settings() -> Iterator[None]:
    """Настройки автоматики и голова миграций — общие на процесс."""
    saved = dataclasses.asdict(migrate._settings)
    yield
    migrate.configure(**saved)
    head_revision.cache_clear()


@pytest.fixture
def migrations(tmp_path, monkeypatch):
    """Копия папки миграций + свои ревизии по порядку: ``migrations(тело1, тело2)``."""

    def make(*bodies: str) -> List[str]:
        target = tmp_path / 'migrations_copy'
        if not target.exists():
            shutil.copytree(
                migrate.MIGRATIONS_DIR,                             # настоящие миграции
                target,                                             # копия
                ignore  =   shutil.ignore_patterns('__pycache__'),  # без кеша
            )
        down = head_revision() if migrate.MIGRATIONS_DIR == str(target) else REAL_HEAD
        revisions = []
        for number, body in enumerate(bodies, 1):
            revision = f"9{len(list((target / 'versions').glob('*.py'))):03d}_test_{number}"
            code = MIGRATION.format(revision=revision, down=down, upgrade=body)
            (target / 'versions' / f'{revision}.py').write_text(code, encoding='utf-8')
            revisions.append(revision)
            down = revision
        monkeypatch.setattr(migrate, 'MIGRATIONS_DIR', str(target))
        head_revision.cache_clear()
        return revisions

    return make


def file_engine(
    tmp_path : object,            # временная папка
    name     : str = 'db.db',     # имя файла
) -> sa.engine.Engine: # движок базы-файла
    return create_engine(f"sqlite:///{tmp_path / name}")


def stored(
    engine : sa.engine.Engine,   # движок
) -> Dict[str, str]: # имя триггера → текст в базе
    with engine.connect() as conn:
        return {name: item.sql for name, item in read_triggers(conn).items()}


def add_patient(
    engine : sa.engine.Engine,   # движок
) -> None: # один пациент
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name) VALUES (1, 'И', 'П')"))


def delete_refused(
    engine : sa.engine.Engine,   # движок
) -> bool: # триггер-запрет на месте: удаление пациента сырым SQL отвергнуто
    try:
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM patients WHERE id = 1'))
    except sa.exc.IntegrityError:
        return True
    return False


def backups(tmp_path) -> List[str]:
    return sorted(p.name for p in tmp_path.iterdir() if '.bak-' in p.name)


def file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Сравнение текста
# ---------------------------------------------------------------------------

def test_normalize_ignores_spacing_but_not_string_values():
    assert normalize_sql('CREATE  TRIGGER\n  t  BEGIN SELECT 1; END;') == 'CREATE TRIGGER t BEGIN SELECT 1; END'
    assert normalize_sql("SELECT 'a  b'") != normalize_sql("SELECT 'a b'")
    assert normalize_sql("SELECT 'it''s  x'  ,  1") == "SELECT 'it''s  x' , 1"


# ---------------------------------------------------------------------------
# Сравнение описания с миграциями и генератор
# ---------------------------------------------------------------------------

def test_no_trigger_differences_for_app_models():
    assert [i for i in pending_model_changes(app_metadata()) if 'trigger' in i[0]] == []


def test_pending_sees_new_trigger():
    changes = pending_model_changes(with_triggers({'patients': {'trg_guard': GUARD_SQL}}))
    assert changes == [('add_trigger', 'patients', 'trg_guard', GUARD_SQL)]
    assert describe_differences(changes) == ['add_trigger patients.trg_guard']
    assert unsafe_changes(changes) == []


def test_pending_sees_changed_and_removed_trigger(migrations):
    migrations(create_op(GUARD_SQL))
    assert pending_model_changes(with_triggers({'patients': {'trg_guard': GUARD_SQL}})) == []
    assert pending_model_changes(with_triggers({'patients': {'trg_guard': GUARD_V2}})) == [
        ('modify_trigger', 'patients', 'trg_guard', GUARD_SQL, GUARD_V2),
    ]
    assert pending_model_changes(app_metadata()) == [
        ('remove_trigger', 'patients', 'trg_guard', GUARD_SQL),
    ]


def test_pending_ignores_spacing_only_change(migrations):
    migrations(create_op(GUARD_SQL))
    spaced = GUARD_SQL.replace('\n', '\n    ')
    assert pending_model_changes(with_triggers({'patients': {'trg_guard': spaced}})) == []


def test_generate_add_then_upgrade_and_downgrade(tmp_path, migrations):
    migrations()
    models = with_triggers({'patients': {'trg_guard': GUARD_SQL}})
    path = generate_migration(models)
    body = open(path, encoding='utf-8').read()
    assert 'add_trigger patients.trg_guard' in body and 'CREATE TRIGGER' in body
    assert pending_model_changes(models) == []
    assert generate_migration(models) is None                       # повторно — нечего
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    assert delete_refused(engine)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), REAL_HEAD)
    assert stored(engine) == {}


def test_generate_modify_and_remove(tmp_path, migrations):
    """Изменение и удаление — своими миграциями; downgrade возвращает прежний текст."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    first = head_revision()
    generate_migration(with_triggers({'patients': {'trg_guard': GUARD_V2}}))
    upgrade_database(engine)
    assert normalize_sql(stored(engine)['trg_guard']) == normalize_sql(GUARD_V2)
    second = head_revision()
    generate_migration(app_metadata())
    upgrade_database(engine)
    assert stored(engine) == {}
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), second)
    assert normalize_sql(stored(engine)['trg_guard']) == normalize_sql(GUARD_V2)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), first)
    assert normalize_sql(stored(engine)['trg_guard']) == normalize_sql(GUARD_SQL)


def test_generate_new_table_comes_before_its_trigger(tmp_path, migrations):
    """Новая таблица с триггером: в файле таблица раньше, при откате — наоборот."""
    migrations()
    meta = app_metadata()
    sa.Table(
        'prescriptions_auto',                                   # новая таблица
        meta,
        sa.Column('id', sa.Integer, primary_key=True),
        info    =   {TRIGGERS_INFO: {'trg_new': trigger(
            'trg_new',                                          # имя
            'before_delete',                                    # место
            'SELECT 1',                                         # команды
        ).create_sql('prescriptions_auto')}},
    )
    path = generate_migration(meta)
    body = open(path, encoding='utf-8').read()
    assert body.index("create_table('prescriptions_auto'") < body.index('CREATE TRIGGER')
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    assert 'trg_new' in stored(engine)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), REAL_HEAD)
    assert 'prescriptions_auto' not in inspect(engine).get_table_names()


def test_generate_text_with_colon_and_quotes(tmp_path, migrations):
    """Двоеточие в тексте — не параметр запроса; кавычки и кириллица доходят как есть."""
    migrations()
    sql = trigger(
        'trg_colon',                                            # имя
        'before_delete',                                        # место
        """SELECT RAISE(ABORT, 'нельзя :x и "y" и ''z''');""",  # текст с особыми знаками
    ).create_sql('patients')
    generate_migration(with_triggers({'patients': {'trg_colon': sql}}))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    with pytest.raises(sa.exc.IntegrityError, match="""нельзя :x и "y" и 'z'"""):
        with engine.begin() as conn:
            conn.execute(text('DELETE FROM patients'))


def test_generate_refuses_broken_trigger_without_file(migrations, tmp_path):
    migrations()
    versions = tmp_path / 'migrations_copy' / 'versions'
    before = sorted(p.name for p in versions.glob('*.py'))
    broken = trigger('trg_bad', 'after_insert', 'UPDATE nosuch SET x = 1').create_sql('patients')
    with pytest.raises(MigrationError, match='no such table'):
        generate_migration(with_triggers({'patients': {'trg_bad': broken}}))
    assert sorted(p.name for p in versions.glob('*.py')) == before


def test_generate_refuses_rebuild_losing_triggers(migrations, tmp_path):
    """Новая связь пересобирает таблицу: триггеры пропали бы молча — файла нет, ошибка понятная."""
    migrations(create_op(GUARD_SQL))
    versions = tmp_path / 'migrations_copy' / 'versions'
    before = sorted(p.name for p in versions.glob('*.py'))
    head = head_revision()
    models = with_triggers({'patients': {'trg_guard': GUARD_SQL}})
    models.tables['patients'].append_column(
        sa.Column('doctor_note_id', sa.Integer, sa.ForeignKey('appointments_notes.id'), nullable=True),
    )
    with pytest.raises(MigrationError, match='keep_triggers'):
        generate_migration(models)
    assert sorted(p.name for p in versions.glob('*.py')) == before
    assert head_revision() == head


def test_generate_refuses_rebuild_breaking_on_other_table_trigger(migrations, tmp_path):
    """Триггер другой таблицы упоминает пересобираемую — миграция падала бы; файла нет."""
    other = trigger(
        'trg_other',                                                    # имя
        'after_insert',                                                 # место
        "UPDATE patients SET phone = '1' WHERE id = NEW.patient_id",    # упоминает patients
    ).create_sql('appointments')
    migrations(create_op(other))
    models = with_triggers({'appointments': {'trg_other': other}})
    models.tables['patients'].append_column(
        sa.Column('doctor_note_id', sa.Integer, sa.ForeignKey('appointments_notes.id'), nullable=True),
    )
    with pytest.raises(MigrationError, match='keep_triggers'):
        generate_migration(models)


def test_build_check_cli_lists_trigger(migrations, monkeypatch, capsys):
    migrations()
    meta = with_triggers({'patients': {'trg_guard': GUARD_SQL}})
    monkeypatch.setattr(migrate, '_default_metadata', lambda: meta)
    assert migrate.main(['check']) == 1
    assert 'add_trigger patients.trg_guard' in capsys.readouterr().out


def test_build_check_cli_refuses_broken_trigger(migrations, monkeypatch, capsys):
    migrations()
    broken = trigger('trg_bad', 'after_insert', 'UPDATE nosuch SET x = 1').create_sql('patients')
    meta = with_triggers({'patients': {'trg_bad': broken}})
    monkeypatch.setattr(migrate, '_default_metadata', lambda: meta)
    assert migrate.main(['check']) == 1
    assert 'no such table' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Новая база, старая база, автодостройка
# ---------------------------------------------------------------------------

def test_new_database_gets_trigger(tmp_path, migrations):
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    assert delete_refused(engine)                                   # и сырым SQL
    assert backups(tmp_path) == []


def test_existing_database_gets_trigger_and_no_extra_changes(tmp_path, migrations):
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    migrations(create_op(GUARD_SQL))
    upgrade_database(engine)
    assert delete_refused(engine)
    assert len(backups(tmp_path)) == 1


def test_legacy_database_without_version_gets_trigger(tmp_path, migrations):
    """Старая база без отметки: приведение к исходной схеме и миграции создают триггер."""
    migrations(create_op(GUARD_SQL))
    path = tmp_path / 'legacy.db'
    engine = create_engine(f"sqlite:///{path}")
    legacy = MetaData(naming_convention=Base.metadata.naming_convention)
    for table in migrate.schema_at(migrate.BASELINE).tables.values():
        table.to_metadata(legacy)
    legacy.create_all(engine)
    add_patient(engine)
    assert upgrade_database(engine) == head_revision()
    assert delete_refused(engine)


def test_drift_missing_trigger_detected_and_restored(tmp_path, migrations):
    """Триггера нет, версия последняя: Alembic сам не видит — видит наше сравнение, чинит копия + дозапись."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(drop_trigger_sql('trg_guard'))
    reference = migrate.schema_at(head_revision())
    assert describe_differences(schema_differences(engine, reference)) == ['add_trigger patients.trg_guard']
    upgrade_database(engine)
    assert delete_refused(engine)
    copies = backups(tmp_path)
    assert len(copies) == 1 and copies[0].endswith('-repair')
    assert schema_differences(engine, reference) == []
    upgrade_database(engine)                                        # второй запуск — ничего
    assert len(backups(tmp_path)) == 1


def test_drift_changed_text_detected_and_replaced(tmp_path, migrations, monkeypatch):
    """Текст меняла сторонняя программа — правило программы возвращается, в журнале предупреждение."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(drop_trigger_sql('trg_guard'))
        conn.exec_driver_sql(GUARD_V2)
    warnings = []
    monkeypatch.setattr(migrate._log, 'warning', warnings.append)
    reference = migrate.schema_at(head_revision())
    assert describe_differences(schema_differences(engine, reference)) == ['modify_trigger patients.trg_guard']
    upgrade_database(engine)
    assert normalize_sql(stored(engine)['trg_guard']) == normalize_sql(GUARD_SQL)
    assert any('trg_guard' in line for line in warnings)
    assert schema_differences(engine, reference) == []


def test_drift_foreign_trigger_kept_and_file_untouched(tmp_path):
    """Чужой триггер — лишнее: не трогается, файл побайтно цел, как и другое лишнее."""
    path = tmp_path / 'db.db'
    engine = create_engine(f"sqlite:///{path}")
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(GUARD_SQL)
        conn.exec_driver_sql('CREATE TABLE my_stuff (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TRIGGER trg_my AFTER INSERT ON my_stuff BEGIN SELECT 1; END')
    engine.dispose()
    before = file_hash(path)
    reference = migrate.schema_at(head_revision())
    # посторонняя таблица и её триггер в сравнение не входят; триггер таблицы образца — «лишний»
    assert [
        line for line in describe_differences(schema_differences(engine, reference)) if 'trigger' in line
    ] == ['remove_trigger patients.trg_guard']
    upgrade_database(engine)
    assert file_hash(path) == before
    assert backups(tmp_path) == []


def test_drift_repair_disabled_keeps_missing_trigger(tmp_path, migrations):
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(drop_trigger_sql('trg_guard'))
    migrate.configure(repair_drift=False)
    upgrade_database(engine)
    assert stored(engine) == {}


def test_drift_trigger_that_fails_is_skipped(tmp_path, migrations, monkeypatch):
    """Как любой пункт автодостройки (A5): не удалось — пропустить, база открывается."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(drop_trigger_sql('trg_guard'))

    def fail(connection, item):
        raise sa.exc.OperationalError('stmt', {}, Exception('сбой'))

    monkeypatch.setattr(migrate.sqlite_triggers, 'apply_trigger_diff', fail)
    assert upgrade_database(engine) == head_revision()
    assert stored(engine) == {}


def test_drift_failed_replace_keeps_old_text(tmp_path, migrations, monkeypatch):
    """Сбой между снятием и созданием: точка отката возвращает прежний текст, а не «ничего»."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(drop_trigger_sql('trg_guard'))
        conn.exec_driver_sql(GUARD_V2)

    def half_done(connection, item):
        connection.exec_driver_sql(drop_trigger_sql(item[2]))
        raise sa.exc.OperationalError('stmt', {}, Exception('сбой'))

    monkeypatch.setattr(migrate.sqlite_triggers, 'apply_trigger_diff', half_done)
    upgrade_database(engine)
    assert normalize_sql(stored(engine)['trg_guard']) == normalize_sql(GUARD_V2)


def test_drift_table_and_its_trigger_restored_in_order(tmp_path, migrations):
    """Удалили таблицу — ушёл и её триггер: сначала таблица, потом триггер."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql('PRAGMA foreign_keys=OFF')
        conn.exec_driver_sql('DROP TABLE photos')
        conn.exec_driver_sql('DROP TABLE appointments')
        conn.exec_driver_sql('DROP TABLE patients')
    assert stored(engine) == {}
    upgrade_database(engine)
    assert 'patients' in inspect(engine).get_table_names()
    add_patient(engine)
    assert delete_refused(engine)


# ---------------------------------------------------------------------------
# Настоящая пересборка таблицы (Р-10)
# ---------------------------------------------------------------------------

REBUILD_LOSES = """
    with op.batch_alter_table('patients', recreate='always') as batch:
        batch.add_column(sa.Column('email', sa.String(100), nullable=True))
"""

REBUILD_KEEPS = """
    with keep_triggers():
        with op.batch_alter_table('patients', recreate='always') as batch:
            batch.add_column(sa.Column('email', sa.String(100), nullable=True))
"""


def test_rebuild_really_loses_trigger_and_generator_sees_it(tmp_path, migrations):
    """Без защиты пересборка убирает триггер молча; сверка «модели = миграции» это показывает."""
    migrations(create_op(GUARD_SQL), REBUILD_LOSES)
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    assert stored(engine) == {}
    assert not delete_refused(engine)
    models = with_triggers({'patients': {'trg_guard': GUARD_SQL}})
    models.tables['patients'].append_column(sa.Column('email', sa.String(100), nullable=True))
    assert [i[0] for i in pending_model_changes(models)] == ['add_trigger']


def test_keep_triggers_survives_real_rebuild(tmp_path, migrations):
    migrations(create_op(GUARD_SQL), REBUILD_KEEPS)
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    assert 'email' in {c['name'] for c in inspect(engine).get_columns('patients')}
    assert normalize_sql(stored(engine)['trg_guard']) == normalize_sql(GUARD_SQL)
    assert delete_refused(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM patients')).scalar() == 1


def test_keep_triggers_on_database_with_rows(tmp_path, migrations):
    """Данные и триггер на месте, перенос данных триггер не вызывает."""
    audit = trigger(
        'trg_audit',                                                    # имя
        'after_insert',                                                 # при вставке
        "UPDATE patients SET phone = 'изменён' WHERE id = NEW.id;",     # меняет строку
    ).create_sql('patients')
    migrations(create_op(audit))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO patients (id, first_name, last_name, phone) VALUES (1, 'И', 'П', '7')"))
        conn.execute(text("UPDATE patients SET phone = '7' WHERE id = 1"))
    migrations(REBUILD_KEEPS)
    upgrade_database(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT phone FROM patients')).scalar() == '7'
    assert 'trg_audit' in stored(engine)


def test_rebuild_with_other_table_trigger_fails_without_keep_and_rolls_back(tmp_path, migrations):
    """Триггер другой таблицы упоминает пересобираемую: без защиты — ошибка и откат, не порча."""
    other = trigger(
        'trg_other',                                                    # имя
        'after_insert',                                                 # место
        "UPDATE patients SET phone = '1' WHERE id = NEW.patient_id",    # упоминает patients
    ).create_sql('appointments')
    first = migrations(create_op(other))[0]
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    migrations(REBUILD_LOSES)
    with pytest.raises(sa.exc.OperationalError, match='trg_other'):
        upgrade_database(engine)
    assert current_revision(engine) == first
    assert 'email' not in {c['name'] for c in inspect(engine).get_columns('patients')}
    assert 'trg_other' in stored(engine)


def test_keep_triggers_with_other_table_trigger(tmp_path, migrations):
    other = trigger(
        'trg_other',                                                    # имя
        'after_insert',                                                 # место
        "UPDATE patients SET phone = '1' WHERE id = NEW.patient_id",    # упоминает patients
    ).create_sql('appointments')
    migrations(create_op(other), REBUILD_KEEPS)
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    assert normalize_sql(stored(engine)['trg_other']) == normalize_sql(other)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO appointments (id, patient_id, date) VALUES (1, 1, '2026-01-01')"))
        assert conn.execute(text('SELECT phone FROM patients')).scalar() == '1'   # работает


def test_keep_triggers_skips_trigger_of_dropped_table_and_keeps_recreated(tmp_path):
    engine = file_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE a (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TABLE b (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TRIGGER ta BEFORE DELETE ON a BEGIN SELECT 1; END')
        conn.exec_driver_sql('CREATE TRIGGER tb BEFORE DELETE ON b BEGIN SELECT 1; END')
        with keep_triggers(conn):
            assert read_triggers(conn) == {}                        # внутри блока триггеров нет
            conn.exec_driver_sql('DROP TABLE a')
            conn.exec_driver_sql('CREATE TRIGGER tb BEFORE DELETE ON b BEGIN SELECT 2; END')
        triggers = read_triggers(conn)
    assert list(triggers) == ['tb'] and 'SELECT 2' in triggers['tb'].sql


def test_migration_breaking_trigger_rolled_back(tmp_path, migrations):
    """Столбец нужен триггеру и удалён пересборкой: не при первой записи у пользователя, а сейчас."""
    needs_phone = trigger(
        'trg_phone',                                # имя
        'after_update',                             # место
        "UPDATE patients SET phone = NEW.phone WHERE id = NEW.id AND 0",   # нужен phone
    ).create_sql('patients')
    first = migrations(create_op(needs_phone))[0]
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    migrations("""
    with keep_triggers():
        with op.batch_alter_table('patients', recreate='always') as batch:
            batch.drop_column('phone')
""")
    with pytest.raises(MigrationError, match=r'сломаны триггеры.*phone'):
        upgrade_database(engine)
    assert current_revision(engine) == first
    assert 'phone' in {c['name'] for c in inspect(engine).get_columns('patients')}
    assert 'trg_phone' in stored(engine)


def test_old_broken_foreign_trigger_does_not_block_migration(tmp_path, migrations):
    """Сломанный чужой триггер был до миграции — обновлению не мешает (как старые висячие ссылки)."""
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TRIGGER trg_old AFTER INSERT ON photos BEGIN UPDATE nosuch SET x = 1; END')
    migrations('    pass')
    assert upgrade_database(engine) == head_revision()
    assert 'trg_old' in stored(engine)


# ---------------------------------------------------------------------------
# Откат транзакции миграции
# ---------------------------------------------------------------------------

def test_failed_migration_leaves_no_partial_trigger(tmp_path, migrations):
    """Сбой после создания триггера и после пересборки: нет ни триггера, ни изменений."""
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    add_patient(engine)
    second = trigger('trg_second', 'after_insert', 'SELECT 1').create_sql('photos')
    migrations(
        create_op(GUARD_SQL) + '\n' + create_op(second) + REBUILD_KEEPS + "    raise RuntimeError('сбой')\n",
    )
    with pytest.raises(RuntimeError, match='сбой'):
        upgrade_database(engine)
    assert stored(engine) == {}
    assert current_revision(engine) == REAL_HEAD
    assert 'email' not in {c['name'] for c in inspect(engine).get_columns('patients')}
    assert not delete_refused(engine)


def test_failed_migration_restores_existing_trigger_after_keep(tmp_path, migrations):
    """Сбой внутри keep_triggers (триггеры сняты) — откат возвращает их с прежним текстом."""
    migrations(create_op(GUARD_SQL))
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    before = stored(engine)
    migrations("""
    with keep_triggers():
        raise RuntimeError('сбой в блоке')
""")
    with pytest.raises(RuntimeError, match='сбой в блоке'):
        upgrade_database(engine)
    assert stored(engine) == before


# ---------------------------------------------------------------------------
# Проверка описания и компиляции
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('spec, message', [
    (trigger('trg_x', 'after_insert', 'UPDATE nosuch SET x = 1'), 'no such table'),
    (trigger('trg_x', 'after_insert', "UPDATE photos SET description = NEW.nope"), 'no such column'),
    (trigger('trg_x', 'before_update', 'SELECT 1', when='NEW.nope IS NULL'), 'no such column'),
    (trigger('trg_x', 'before_delete', 'UPDATE photos SET description = OLD.nope'), 'no such column'),
    (trigger('trg_x', 'after_update', 'UPDATE photos SET description = NEW.nope', of='phone'), 'no such column'),
    (trigger('trg_x', 'after_insert', 'SELEC 1'), 'syntax error'),
])
def test_definition_typo_found_before_firing(spec, message):
    meta = with_triggers({'patients': {spec.name: spec.create_sql('patients')}})
    with pytest.raises(MigrationError, match=rf'patients\.trg_x: .*{message}'):
        check_trigger_definitions(meta)


def test_definition_ok_and_names_every_error():
    ok = trigger('trg_ok', 'before_delete', 'SELECT 1').create_sql('patients')
    check_trigger_definitions(with_triggers({'patients': {'trg_ok': ok}}))
    meta = with_triggers({
        'patients': {'trg_a': trigger('trg_a', 'after_insert', 'UPDATE nosuch SET x = 1').create_sql('patients')},
        'photos': {'trg_b': trigger('trg_b', 'after_insert', 'UPDATE nosuch2 SET x = 1').create_sql('photos')},
    })
    with pytest.raises(MigrationError) as error:
        check_trigger_definitions(meta)
    assert 'trg_a' in str(error.value) and 'trg_b' in str(error.value)


def test_definition_repeated_name_on_two_tables():
    """Имена триггеров едины на базу, а не на таблицу: вторая миграция упала бы."""
    meta = with_triggers({
        'patients': {'trg_same': trigger('trg_same', 'before_delete', 'SELECT 1').create_sql('patients')},
        'photos': {'trg_same': trigger('trg_same', 'before_delete', 'SELECT 1').create_sql('photos')},
    })
    with pytest.raises(MigrationError, match='trg_same повторяется'):
        check_trigger_definitions(meta)


def test_definition_without_triggers_creates_nothing(monkeypatch):
    """Таблицы без триггеров: проверка не строит базу и не касается моделей."""
    from app.database import sqlite_triggers

    def forbidden(*args, **kwargs):
        raise AssertionError('база не нужна')

    monkeypatch.setattr(sqlite_triggers.sa, 'create_engine', forbidden)
    check_trigger_definitions(app_metadata())


def test_database_open_refuses_typo_before_touching_file(tmp_path, monkeypatch):
    broken = trigger('trg_bad', 'after_insert', 'UPDATE nosuch SET x = 1').create_sql('patients')
    table = Base.metadata.tables['patients']
    monkeypatch.setitem(table.info, TRIGGERS_INFO, {'trg_bad': broken})
    path = tmp_path / 'db.db'
    with pytest.raises(MigrationError, match='no such table') as error:
        Database(f"sqlite:///{path}")
    assert not path.exists()
    assert 'нельзя безопасно обновить' in migrate.startup_error_text(error.value)


def test_trigger_errors_not_fooled_by_statement_cache(tmp_path):
    """Кеш запросов sqlite3 + EXPLAIN показал бы план до изменения схемы — та же ошибка не нашлась бы."""
    engine = file_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE a (id INTEGER PRIMARY KEY, x TEXT)')
        conn.exec_driver_sql('CREATE TABLE b (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TRIGGER t BEFORE DELETE ON a BEGIN UPDATE b SET id = OLD.id; END')
        assert trigger_errors(conn) == []
        conn.exec_driver_sql('DROP TRIGGER t')
        conn.exec_driver_sql('CREATE TRIGGER t BEFORE DELETE ON a BEGIN UPDATE b SET id = OLD.nope; END')
        errors = trigger_errors(conn)
    assert len(errors) == 1 and 'a, DELETE' in errors[0] and 'OLD.nope' in errors[0]


def test_trigger_named_like_operation(tmp_path):
    """Имя триггера — слово операции: проверяется настоящая операция, а не слово из имени."""
    engine = file_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE a (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TRIGGER "update" BEFORE DELETE ON a BEGIN SELECT OLD.nope; END')
        assert 'a, DELETE' in trigger_errors(conn)[0]


def test_trigger_update_of_column_added_after_first_check(tmp_path):
    """Список столбцов для UPDATE читается заново: кеш запросов не скрывает новый столбец."""
    engine = file_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE a (id INTEGER PRIMARY KEY)')
        conn.exec_driver_sql('CREATE TRIGGER t0 BEFORE UPDATE ON a BEGIN SELECT 1; END')
        assert trigger_errors(conn) == []
        conn.exec_driver_sql('ALTER TABLE a ADD COLUMN x TEXT')
        conn.exec_driver_sql('CREATE TRIGGER t1 BEFORE UPDATE OF x ON a BEGIN SELECT NEW.nope; END')
        assert 'NEW.nope' in trigger_errors(conn)[0]


def test_trigger_errors_runs_nothing(tmp_path):
    """Проверка компилирует, но не выполняет: строки и правила не задеты."""
    engine = file_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE a (id INTEGER PRIMARY KEY, x TEXT)')
        conn.exec_driver_sql("INSERT INTO a VALUES (1, 'x')")
        conn.exec_driver_sql("CREATE TRIGGER t BEFORE DELETE ON a BEGIN SELECT RAISE(ABORT, 'нет'); END")
        conn.exec_driver_sql("CREATE TRIGGER u BEFORE UPDATE OF x ON a BEGIN SELECT RAISE(ABORT, 'нет'); END")
        conn.exec_driver_sql("CREATE TRIGGER i BEFORE INSERT ON a BEGIN SELECT RAISE(ABORT, 'нет'); END")
        assert trigger_errors(conn) == []
        assert conn.exec_driver_sql('SELECT x FROM a').scalar() == 'x'


# ---------------------------------------------------------------------------
# ORM и приложение
# ---------------------------------------------------------------------------

def test_database_session_scope_gets_trigger_refusal_text(tmp_path, migrations):
    """Запрет триггера при работе через ORM: понятный текст в исключении приложения."""
    migrations(create_op(GUARD_SQL))
    db = Database(f"sqlite:///{tmp_path / 'db.db'}")
    try:
        with db.session_scope() as session:
            session.add(Patient(id=1, first_name='И', last_name='П'))
        with pytest.raises(DbIntegrityError, match='пациента удалять нельзя'):
            with db.session_scope() as session:
                session.delete(session.get(Patient, 1))
        with db.session_scope() as session:
            assert session.get(Patient, 1) is not None
    finally:
        db.close()


def test_orm_object_stale_until_refresh(tmp_path, migrations):
    """ORM не знает о работе триггера: объект устарел до refresh — поведение описано в докстринге."""
    change_other = trigger(
        'trg_change',                                                   # имя
        'after_update',                                                 # после изменения
        "UPDATE patients SET phone = 'из триггера' WHERE id = NEW.id;", # меняет ту же строку
        of      =   'first_name',                                       # только при смене имени
    ).create_sql('patients')
    migrations(create_op(change_other))
    db = Database(f"sqlite:///{tmp_path / 'db.db'}")
    try:
        with db.session_scope() as session:
            patient = Patient(id=1, first_name='И', last_name='П', phone='7')
            session.add(patient)
            session.flush()
            patient.first_name = 'Новое'
            session.flush()                                             # триггер сработал
            assert patient.phone == '7'                                 # объект устарел
            session.refresh(patient)
            assert patient.phone == 'из триггера'
    finally:
        db.close()


def test_trigger_dangling_reference_refused_by_foreign_keys(tmp_path, migrations):
    """Внешние ключи основного движка (Р-2) действуют и на команды триггера."""
    dangling = trigger(
        'trg_dangling',                                                         # имя
        'after_update',                                                         # после изменения
        'UPDATE patients SET comment_id = 999 WHERE id = NEW.id;',              # нет такой заметки
        of      =   'first_name',                                               # при смене имени
    ).create_sql('patients')
    migrations(create_op(dangling))
    db = Database(f"sqlite:///{tmp_path / 'db.db'}")
    try:
        with db.session_scope() as session:
            session.add(Patient(id=1, first_name='И', last_name='П'))
        with pytest.raises(DbIntegrityError):
            with db.session_scope() as session:
                session.get(Patient, 1).first_name = 'Новое'
        with db.session_scope() as session:
            assert session.get(Patient, 1).first_name == 'И'            # откат целиком
    finally:
        db.close()


def test_raise_ignore_breaks_orm_as_documented(tmp_path, migrations):
    """RAISE(IGNORE): ORM ждёт изменённую строку — ошибка и откат, а не тихая потеря правки."""
    from sqlalchemy.orm.exc import StaleDataError
    ignore = trigger(
        'trg_ignore',               # имя
        'before_update',            # перед изменением
        'SELECT RAISE(IGNORE);',    # молча пропустить строку
    ).create_sql('patients')
    migrations(create_op(ignore))
    db = Database(f"sqlite:///{tmp_path / 'db.db'}")
    try:
        with db.session_scope() as session:
            session.add(Patient(id=1, first_name='И', last_name='П'))
        with pytest.raises(StaleDataError):
            with db.session_scope() as session:
                session.get(Patient, 1).first_name = 'Новое'
    finally:
        db.close()


def test_create_tables_recreate_restores_trigger(tmp_path, migrations):
    migrations(create_op(GUARD_SQL))
    db = Database(f"sqlite:///{tmp_path / 'db.db'}")
    try:
        db.create_tables(recreate=True)
        assert 'trg_guard' in stored(db.engine)
    finally:
        db.close()


def test_backup_copy_keeps_trigger(tmp_path, migrations):
    """Резервная копия перед миграцией — с триггерами: откатиться на неё можно без потерь."""
    first = migrations(create_op(GUARD_SQL))[0]
    engine = file_engine(tmp_path)
    upgrade_database(engine)
    assert current_revision(engine) == first
    migrations('    pass')
    upgrade_database(engine)
    copy = tmp_path / backups(tmp_path)[0]
    assert 'trg_guard' in stored(create_engine(f"sqlite:///{copy}"))
