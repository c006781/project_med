# tests/test_database_shema/test_table_events.py

"""
События таблиц (Ф1.6.7г, шаг 2; ``app/database/table_events.py``): реестр действий по
имени, события строк (в том числе каскад и «сироты»), журнал транзакции для «перед
коммитом», «после коммита / отката», отказ «перед…» — исключение приложения и откат (Р-12),
проверка имён при открытии базы (Р-9), один диспетчер на базу без повторов после
переоткрытия (Р-8). Настоящая SQLite.
"""

from dataclasses import replace
from pathlib import Path
from typing import Iterator, List, Tuple

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker

import app.database.table_events as te
from app.database.database import Database
from app.database.database_shema.clinic import Patient
from app.exceptions import PatientValidationError, TableEventError
from app.schema.clinic import PATIENTS
from app.schema.define import TableDef, children, column, fk, key, on


@pytest.fixture
def calls() -> Iterator[List[Tuple]]:
    """
    Журнал вызовов тестовых действий ``probe`` / ``probe2`` / ``reject`` / ``crash``;
    после теста действия убираются из реестра.
    """
    log : List[Tuple] = []

    def probe(ctx: te.EventContext) -> None:
        target_id = getattr(ctx.target, 'id', None)
        log.append(('probe', ctx.table, ctx.event, target_id, dict(ctx.old),
                    tuple((c.operation, c.key) for c in ctx.changes)))

    def probe2(ctx: te.EventContext) -> None:
        log.append(('probe2', ctx.table, ctx.event))

    def reject(ctx: te.EventContext) -> None:
        raise PatientValidationError('text', 'удалять нельзя')

    def crash(ctx: te.EventContext) -> None:
        raise RuntimeError('сломалось')

    for name, func in (('probe', probe), ('probe2', probe2), ('reject', reject), ('crash', crash)):
        te.register_action(name, func, replace=True)
    yield log
    for name in ('probe', 'probe2', 'reject', 'crash'):
        te.unregister_action(name)


def _models(
    owner_events : tuple = (),   # события владельца
    item_events  : tuple = (),   # события подчинённых
):
    """Владелец (``owners``) и подчинённые (``items``, каскад и «сироты») на своей базе."""
    base = declarative_base()
    owners = TableDef(
        'owners', 'Owner', 'OwnerDTO',
        fields = (
            key(),
            column('text', sa.Text(), 'Текст'),
            children('items', 'Item', 'owner', dto=False, config=False),
        ),
        events = owner_events,
    )
    items = TableDef(
        'items', 'Item', 'ItemDTO',
        fields = (
            key(),
            fk('owner_id', 'owners', 'Owner', relation='owner', back='items', nullable=False),
            column('text', sa.Text(), 'Текст'),
        ),
        events = item_events,
    )
    owner = owners.build_model(base)
    item = items.build_model(base)
    base.registry.configure()
    return base, owner, item


def _factory(
    base : object,   # база моделей
    path : Path,     # файл базы
):
    """Фабрика сессий с диспетчером событий (как в ``Database``)."""
    engine = sa.create_engine(f"sqlite:///{path.as_posix()}")
    base.metadata.create_all(engine)
    events = te.TableEvents()
    factory = sessionmaker(bind=engine, info={te.INFO_KEY: events})
    events.listen(factory)
    return factory


# ---------------------------------------------------------------------- реестр


def test_register_action_rejects_other_function_under_same_name(calls):
    with pytest.raises(ValueError, match='уже зарегистрировано'):
        te.register_action('probe', lambda ctx: None)
    # та же функция повторно — без ошибки
    func = te._ACTIONS['probe']
    assert te.register_action('probe', func) is func


def test_register_action_decorator_and_empty_name():
    @te.register_action('tmp_decorated')
    def tmp(ctx):
        pass
    try:
        assert 'tmp_decorated' in te.registered_actions()
    finally:
        te.unregister_action('tmp_decorated')
    with pytest.raises(ValueError, match='непустой'):
        te.register_action('  ', tmp)


def test_check_action_names_lists_all_unknown(calls):
    base, _, _ = _models(
        owner_events = (on('after_insert', 'probe', 'nope1'),),
        item_events  = (on('after_commit', 'nope2'),),
    )
    with pytest.raises(TableEventError) as info:
        te.check_action_names(base)
    text = str(info.value)
    assert 'owners.after_insert: nope1' in text
    assert 'items.after_commit: nope2' in text
    assert 'probe' not in text.split(':', 1)[1].replace('owners.after_insert', '')


# ---------------------------------------------------------------------- события строк


def test_row_events_in_order_with_old_values(calls, tmp_path):
    base, owner, _ = _models(
        owner_events = (
            on('before_insert', 'probe'), on('after_insert', 'probe', 'probe2'),
            on('before_update', 'probe'), on('after_update', 'probe'),
            on('before_delete', 'probe'), on('after_delete', 'probe'),
        ),
    )
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        o = owner(text='a')
        s.add(o)
        s.commit()
        s.expire(o)                     # атрибут не загружен — прежнее значение из базы
        o.text = 'b'
        s.commit()
        s.delete(o)
        s.commit()
    events = [(c[0], c[2]) for c in calls]
    assert events == [
        ('probe', 'before_insert'), ('probe', 'after_insert'), ('probe2', 'after_insert'),
        ('probe', 'before_update'), ('probe', 'after_update'),
        ('probe', 'before_delete'), ('probe', 'after_delete'),
    ]
    update = [c for c in calls if c[2] in ('before_update', 'after_update')]
    assert all(c[4] == {'text': 'a'} for c in update)


def test_cascade_and_orphan_fire_child_delete(calls, tmp_path):
    base, owner, item = _models(item_events=(on('before_delete', 'probe'),))
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        o = owner(text='a', items=[item(text='1'), item(text='2'), item(text='3')])
        s.add(o)
        s.commit()
        o.items.remove(o.items[0])      # «сирота»
        s.commit()
        s.delete(o)                     # каскад — остальные двое
        s.commit()
    assert sorted(c[3] for c in calls) == [1, 2, 3]


def test_session_without_dispatcher_does_nothing(calls, tmp_path):
    base, owner, _ = _models(owner_events=(on('after_insert', 'probe'),))
    engine = sa.create_engine(f"sqlite:///{(tmp_path / 'p.db').as_posix()}")
    base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        s.add(owner(text='a'))
        s.commit()
    assert calls == []


# ---------------------------------------------------------------------- отказ и ошибки (Р-12)


def test_before_delete_rejection_rolls_back(calls, tmp_path):
    base, owner, _ = _models(owner_events=(on('before_delete', 'reject'),))
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        s.add(owner(text='a'))
        s.commit()
        s.delete(s.get(owner, 1))
        with pytest.raises(PatientValidationError, match='удалять нельзя'):
            s.commit()
        s.rollback()
        assert s.get(owner, 1) is not None


def test_action_crash_becomes_table_event_error(calls, tmp_path):
    base, owner, _ = _models(owner_events=(on('after_insert', 'crash'),))
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        s.add(owner(text='a'))
        with pytest.raises(TableEventError) as info:
            s.commit()
        s.rollback()
        assert s.query(owner).count() == 0
    error = info.value
    assert error.code == 6003
    assert error.details['таблица'] == 'owners'
    assert error.details['место'] == 'after_insert'
    assert error.details['действие'] == 'crash'
    assert isinstance(error.__cause__, RuntimeError)


# ---------------------------------------------------------------------- журнал транзакции


def test_transaction_events_get_changes_of_their_table(calls, tmp_path):
    base, owner, item = _models(
        owner_events = (on('before_commit', 'probe'), on('after_commit', 'probe')),
    )
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        o = owner(text='a', items=[item(text='1')])
        s.add(o)
        s.commit()
        o.text = 'b'
        s.commit()
        s.delete(o)
        s.commit()
    got = [(c[2], c[5]) for c in calls]
    assert got == [
        ('before_commit', (('insert', 1),)), ('after_commit', (('insert', 1),)),
        ('before_commit', (('update', 1),)), ('after_commit', (('update', 1),)),
        ('before_commit', (('delete', 1),)), ('after_commit', (('delete', 1),)),
    ]


def test_change_values_and_old(tmp_path):
    seen : List[te.RowChange] = []
    te.register_action('keep_changes', lambda ctx: seen.extend(ctx.changes), replace=True)
    try:
        base, owner, _ = _models(owner_events=(on('after_commit', 'keep_changes'),))
        factory = _factory(base, tmp_path / 'e.db')
        with factory() as s:
            o = owner(text='a')
            s.add(o)
            s.commit()
            o.text = 'b'
            s.commit()
            s.delete(o)                 # объект истёк после коммита — строка из базы
            s.commit()
    finally:
        te.unregister_action('keep_changes')
    insert, update, delete = seen
    assert insert.values['text'] == 'a'
    assert (update.values['text'], update.old) == ('b', {'text': 'a'})
    assert delete.values == {'id': 1, 'text': 'b'}


def test_after_rollback_gets_changes_and_log_does_not_leak(calls, tmp_path):
    base, owner, _ = _models(
        owner_events = (on('after_rollback', 'probe'), on('after_commit', 'probe2')),
    )
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        s.add(owner(text='a'))
        s.flush()
        s.rollback()
        # следующая транзакция без изменений — журнал прошлой ей не достаётся
        s.commit()
    assert calls == [('probe', 'owners', 'after_rollback', None, {}, (('insert', 1),))]


def test_after_commit_error_is_logged_not_raised(calls, tmp_path):
    base, owner, _ = _models(owner_events=(on('after_commit', 'crash', 'probe2'),))
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        s.add(owner(text='a'))
        s.commit()                      # коммит прошёл, ошибка — в журнал
        assert s.query(owner).count() == 1
    assert calls == [('probe2', 'owners', 'after_commit')]


# ---------------------------------------------------------------------- Database (Р-8, Р-9)


@pytest.fixture
def patient_probe(calls, monkeypatch):
    """Описание пациентов с действием ``probe`` после добавления строки."""
    monkeypatch.setattr(
        Patient,                                                    # модель приложения
        '__table_def__',                                            # её описание
        replace(PATIENTS, events=(on('after_insert', 'probe'),)),   # + событие
    )
    return calls


def _add_patient(
    db : Database,   # база
) -> None:
    with db.session_scope() as s:
        s.add(Patient(last_name='Петров', first_name='Иван'))


def test_database_runs_actions_once_after_reopen(patient_probe, tmp_path):
    url = f"sqlite:///{(tmp_path / 'clinic.db').as_posix()}"
    first = Database(url)
    _add_patient(first)
    first.close()
    second = Database(url)              # переоткрытая база — новый диспетчер
    try:
        _add_patient(second)
    finally:
        second.close()
    assert [c[2] for c in patient_probe] == ['after_insert', 'after_insert']
    assert first.table_events is not second.table_events


def test_database_rejects_unknown_action_name_at_open(monkeypatch, tmp_path):
    monkeypatch.setattr(
        Patient,
        '__table_def__',
        replace(PATIENTS, events=(on('after_insert', 'no_such_action'),)),
    )
    path = tmp_path / 'clinic.db'
    with pytest.raises(TableEventError, match='patients.after_insert: no_such_action'):
        Database(f"sqlite:///{path.as_posix()}")
    assert not path.exists()            # до открытия базы


# ---------------------------------------------------------------------- шаг 2а (Р-16, Р-18, Р-21)


def test_close_without_rollback_does_not_leak_log(calls, tmp_path):
    """Р-16: брошенная транзакция (close() без отката) — её строки не достаются следующей."""
    base, owner, _ = _models(
        owner_events = (on('after_commit', 'probe'), on('after_rollback', 'probe2')),
    )
    factory = _factory(base, tmp_path / 'e.db')
    s = factory()
    s.add(owner(text='брошенная'))
    s.flush()
    s.close()                           # ни коммита, ни отката — только after_transaction_end
    assert calls == [('probe2', 'owners', 'after_rollback')]
    calls.clear()
    s.add(owner(text='следующая'))
    s.commit()
    s.close()
    # «после коммита» получил только строку своей транзакции
    assert [c[5] for c in calls] == [(('insert', 1),)]


def test_savepoint_is_not_transaction_event(calls, tmp_path):
    """Р-18: выпуск и откат точки сохранения — не коммит и не откат транзакции."""
    base, owner, _ = _models(
        owner_events = (
            on('before_commit', 'probe'), on('after_commit', 'probe'), on('after_rollback', 'probe2'),
        ),
    )
    factory = _factory(base, tmp_path / 'e.db')
    with factory() as s:
        s.add(owner(text='a'))
        s.begin_nested().commit()       # выпуск точки сохранения
        nested = s.begin_nested()
        s.add(owner(text='b'))
        s.flush()
        nested.rollback()               # откат точки сохранения
        assert calls == []
        s.commit()
    assert [c[2] for c in calls] == ['before_commit', 'after_commit']


@pytest.mark.filterwarnings('ignore:Usage of the .Session.add\(\). operation')
def test_row_action_changing_session_is_error(tmp_path):
    """Р-21: действие строки добавляет строку внутри flush — TableEventError, откат."""
    def sneaky(ctx):
        ctx.session.add(ctx.target.__class__(text='тайком'))

    te.register_action('sneaky', sneaky, replace=True)
    try:
        base, owner, _ = _models(owner_events=(on('after_insert', 'sneaky'),))
        factory = _factory(base, tmp_path / 'e.db')
        with factory() as s:
            s.add(owner(text='a'))
            with pytest.raises(TableEventError, match='внутри сброса'):
                s.commit()
            s.rollback()
            assert s.query(owner).count() == 0
    finally:
        te.unregister_action('sneaky')
