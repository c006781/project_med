# tests/test_schema/test_trigger_def.py

"""
Встроенные триггеры SQLite в описании таблицы (``TableDef.triggers``, ``trigger``): проверка
описания при его создании, текст ``CREATE TRIGGER``, передача текста в ``Table.info``. Работа с
базой и миграциями — ``tests/test_database_shema/test_sqlite_triggers.py``.
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

from app.schema.clinic import CLINIC_DEFS, NOTES, PHOTO_FILES
from app.schema.define import (
    ROW_EVENTS,
    TRIGGERS_INFO,
    TableDef,
    TriggerSpec,
    column,
    fk,
    key,
    note,
    timestamp,
    trigger,
)


def _table(
    *triggers : TriggerSpec,   # триггеры таблицы
) -> TableDef: # минимальное описание для проверок
    return TableDef(
        'things',                                                   # таблица
        'Thing',                                                    # модель
        'ThingDTO',                                                 # DTO
        (
            key(),
            column('name', sa.String(20), 'Имя'),
            fk('owner_id', 'owners', 'Owner'),
            note('reason', 'Причина'),
            timestamp(),
        ),
        triggers    =   triggers,                                   # триггеры
    )


def test_trigger_text_for_every_place():
    expected = {
        'before_insert': 'BEFORE INSERT', 'after_insert': 'AFTER INSERT',
        'before_update': 'BEFORE UPDATE', 'after_update': 'AFTER UPDATE',
        'before_delete': 'BEFORE DELETE', 'after_delete': 'AFTER DELETE',
    }
    assert set(expected) == set(ROW_EVENTS)
    for event, words in expected.items():
        sql = trigger('trg', event, 'SELECT 1').create_sql('things')
        assert sql.startswith(f'CREATE TRIGGER "trg" {words} ON "things"')
        assert sql.endswith('BEGIN\nSELECT 1;\nEND')


def test_trigger_text_when_and_of():
    sql = trigger(
        'trg',                                  # имя
        'after_update',                         # место
        'UPDATE a SET b = 1;\nUPDATE c SET d = 2;  ',   # две команды, лишнее в конце
        when    =   'NEW.name IS NULL',         # условие
        of      =   ('name', 'owner_id'),       # столбцы
    ).create_sql('things')
    assert sql == (
        'CREATE TRIGGER "trg" AFTER UPDATE OF "name", "owner_id" ON "things"\n'
        'WHEN NEW.name IS NULL\n'
        'BEGIN\nUPDATE a SET b = 1;\nUPDATE c SET d = 2;\nEND'
    )


def test_of_as_single_string():
    assert trigger('trg', 'before_update', 'SELECT 1', of='name').of == ('name',)


@pytest.mark.parametrize('kwargs, message', [
    ({'name': 'пробел в имени'}, 'имя триггера'),
    ({'name': '1trg'}, 'имя триггера'),
    ({'name': 'a"; DROP TABLE x; --'}, 'имя триггера'),
    ({'name': 'sqlite_trg'}, 'имя триггера'),
    ({'name': None}, 'имя триггера'),
    ({'event': 'before_commit'}, 'неизвестное место'),       # есть у событий, у триггера нет
    ({'event': 'after_delet'}, 'неизвестное место'),
    ({'body': ''}, 'нет команд'),
    ({'body': ' ; '}, 'нет команд'),
    ({'body': None}, 'нет команд'),
    ({'when': '  '}, 'условие when'),
    ({'event': 'before_delete', 'of': ('name',)}, 'только для изменения'),
    ({'of': ('name; DROP',)}, 'плохое имя столбца'),
    ({'of': ('name', 'name')}, 'повторяется'),
])
def test_bad_trigger_rejected_at_once(kwargs, message):
    arguments = {'name': 'trg', 'event': 'before_update', 'body': 'SELECT 1', **kwargs}
    with pytest.raises(ValueError, match=message):
        trigger(**arguments)


def test_table_rejects_not_trigger_spec():
    with pytest.raises(ValueError, match=r'описывайте через trigger'):
        _table('CREATE TRIGGER t')


def test_table_rejects_repeated_name():
    with pytest.raises(ValueError, match="имя триггера 'a' повторяется"):
        _table(
            trigger('a', 'before_delete', 'SELECT 1'),
            trigger('a', 'after_delete', 'SELECT 2'),
        )


@pytest.mark.parametrize('name', ['nope', 'reason_text', 'reason'])
def test_table_rejects_unknown_of_column(name):
    """Столбцов нет: опечатка; у заметки текст и основа имени — не столбцы таблицы."""
    with pytest.raises(ValueError, match=f"в of нет столбца '{name}'"):
        _table(trigger('a', 'before_update', 'SELECT 1', of=name))


@pytest.mark.parametrize('name', ['id', 'name', 'owner_id', 'reason_id', 'created_at'])
def test_table_accepts_stored_of_column(name):
    assert _table(trigger('a', 'before_update', 'SELECT 1', of=name)).triggers[0].of == (name,)


def test_triggers_become_tuple():
    table = TableDef('t', 'T', 'TDTO', (key(),), triggers=[trigger('a', 'before_delete', 'SELECT 1')])
    assert isinstance(table.triggers, tuple)


def test_model_carries_trigger_text_in_table_info():
    base = declarative_base()
    spec = trigger('trg', 'before_delete', "SELECT RAISE(ABORT, 'нельзя')")
    model = TableDef('t', 'T', 'TDTO', (key(),), triggers=(spec,)).build_model(base)
    assert model.__table__.info[TRIGGERS_INFO] == {'trg': spec.create_sql('t')}
    # копия схемы (to_metadata) несёт его же — так сравнивают тесты и инструменты
    copy = model.__table__.to_metadata(sa.MetaData())
    assert copy.info[TRIGGERS_INFO] == {'trg': spec.create_sql('t')}


def test_table_without_triggers_has_no_info():
    """Таблица без триггеров строится как раньше."""
    base = declarative_base()
    model = TableDef('t', 'T', 'TDTO', (key(),)).build_model(base)
    assert model.__table__.info == {}
    assert model.__table_args__ == ({'sqlite_autoincrement': True},)


def test_clinic_tables_have_no_triggers_yet():
    """Конкретных правил пока нет: появятся — новая миграция и эта проверка меняются вместе."""
    for table_def in (*CLINIC_DEFS, NOTES, PHOTO_FILES):
        assert table_def.triggers == ()
