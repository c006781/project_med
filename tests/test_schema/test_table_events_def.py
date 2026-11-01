# tests/test_schema/test_table_events_def.py

"""
Ф1.6.7г, шаг 1: хранение строк (``TableDef.keep``) и события таблицы (``events``, ``on``) в
описании; модель знает своё описание (``__table_def__``). Исполнение — слой базы (шаг 2).
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

from app.schema.define import (
    KEEP_ALWAYS,
    KEEP_USED,
    TABLE_EVENTS,
    EventSpec,
    TableDef,
    column,
    key,
    on,
)


def _table(
    **kwargs,   # keep, events …
) -> TableDef: # минимальное описание для проверок
    return TableDef(
        'things',                                       # таблица
        'Thing',                                        # модель
        'ThingDTO',                                     # DTO
        fields = (
            key(),
            column(
                'text',                                 # имя
                sa.Text(),                              # тип
                'Текст',                                # подпись
            ),
        ),
        **kwargs,
    )


def test_keep_default_is_always_and_no_events():
    table = _table()
    assert table.keep == KEEP_ALWAYS
    assert table.events == ()
    assert all(table.actions_for(event) == () for event in TABLE_EVENTS)


def test_keep_used_accepted():
    assert _table(keep=KEEP_USED).keep == 'used'


def test_keep_unknown_rejected():
    with pytest.raises(ValueError, match="keep='usd'"):
        _table(keep='usd')


def test_on_builds_spec_in_order():
    spec = on('before_delete', 'a', 'b')
    assert spec == EventSpec('before_delete', ('a', 'b'))


@pytest.mark.parametrize(
    'args, message',
    [
        (('before_dlete', 'a'), 'неизвестное место'),
        (('after_commit',), 'не названо ни одного'),
        (('after_commit', ''), 'непустой строкой'),
        (('after_commit', None), 'непустой строкой'),
        (('after_commit', 'a', 'a'), 'повторяется'),
    ],
)
def test_on_rejects_bad_arguments(args, message):
    with pytest.raises(ValueError, match=message):
        on(*args)


def test_actions_for_keeps_order_across_specs():
    table = _table(
        events = [                                      # список — станет кортежем
            on('after_delete', 'a'),
            on('before_commit', 'x'),
            on('after_delete', 'b', 'c'),
        ],
    )
    assert table.events == (
        on('after_delete', 'a'),
        on('before_commit', 'x'),
        on('after_delete', 'b', 'c'),
    )
    assert table.actions_for('after_delete') == ('a', 'b', 'c')
    assert table.actions_for('before_commit') == ('x',)
    assert table.actions_for('after_insert') == ()


def test_same_action_twice_on_one_event_rejected():
    with pytest.raises(ValueError, match='подключено дважды'):
        _table(events=(on('after_delete', 'a'), on('after_delete', 'a')))


def test_events_must_be_built_by_on():
    with pytest.raises(ValueError, match='через on'):
        _table(events=(('after_delete', 'a'),))


def test_actions_for_unknown_event_rejected():
    with pytest.raises(ValueError, match='неизвестное место'):
        _table().actions_for('after_save')


def test_model_knows_its_def():
    table = _table(
        keep    = KEEP_USED,                            # только используемые
        events  = (on('after_delete', 'a'),),           # действие после удаления
    )
    model = table.build_model(
        declarative_base(),                             # своя база
    )
    assert model.__table_def__ is table
    # описание — не столбец и не связь
    assert set(model.__table__.columns.keys()) == {'id', 'text'}


def test_clinic_models_know_their_defs():
    from app.database.database_shema.clinic import Appointment, AppointmentNote, Patient, Photo
    from app.schema.clinic import APPOINTMENTS, NOTES, PATIENTS, PHOTOS

    assert Patient.__table_def__ is PATIENTS
    assert Appointment.__table_def__ is APPOINTMENTS
    assert Photo.__table_def__ is PHOTOS
    assert AppointmentNote.__table_def__ is NOTES
