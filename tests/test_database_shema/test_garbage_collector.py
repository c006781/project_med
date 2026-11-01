# tests/test_database_shema/test_garbage_collector.py

"""
Сборщик мусора (Ф1.6.7г, шаг 3; ``app/database/table_events.py``): строки таблиц «только
используемые», на которые в транзакции убрали последнюю ссылку, удаляются перед коммитом.
Предел кругов — глубина цепочки по схеме + 1, при превышении — откат (решение владельца
2026-11-01); порядок «действия перед коммитом один раз → сборщик последним → журнал закрыт».
Настоящая SQLite, своя база моделей.
"""

from pathlib import Path
from typing import Any, List, Tuple

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import app.database.table_events as te
from app.exceptions import TableEventError
from app.schema.define import KEEP_USED, TableDef, children, column, fk, key, on


class FakeLogger:
    """Журнал для проверок: запоминает (уровень, текст)."""

    def __init__(self) -> None:
        self.records : List[Tuple[str, str]] = []

    def __getattr__(self, level: str):
        return lambda text, *a, **k: self.records.append((level, str(text)))

    def texts(self, level: str) -> List[str]:
        return [text for lvl, text in self.records if lvl == level]


def _models(
    note_events   : tuple = (),   # события заметок
    holder_events : tuple = (),   # события держателей
):
    """
    Заметки (``gc_notes``, «только используемые»; обратная коллекция ``holders`` — как у
    ``AppointmentNote.appointments``), держатели (две ссылки, подчинённые с каскадом) и
    модель без описания со ссылкой на заметку.
    """
    base = declarative_base()
    notes = TableDef(
        'gc_notes', 'GcNote', 'GcNoteDTO',
        fields = (
            key(),
            column('text', sa.Text(), 'Текст'),
        ),
        keep   = KEEP_USED,
        events = note_events,
    )
    holders = TableDef(
        'holders', 'Holder', 'HolderDTO',
        fields = (
            key(),
            fk('a_id', 'gc_notes', 'GcNote'),
            fk('b_id', 'gc_notes', 'GcNote'),
            children('kids', 'Kid', 'holder', dto=False, config=False),
        ),
        events = holder_events,
    )
    kids = TableDef(
        'kids', 'Kid', 'KidDTO',
        fields = (
            key(),
            fk('holder_id', 'holders', 'Holder', relation='holder', back='kids', nullable=False),
            fk('note_id', 'gc_notes', 'GcNote'),
        ),
    )
    # две ссылки держателя на заметки — связи с явным ключом (как note() в приложении)
    note = notes.build_model(base, {
        'holders': relationship('Holder', foreign_keys='[Holder.a_id]', back_populates='a_note'),
    })
    holder = holders.build_model(base, {
        'a_note': relationship('GcNote', foreign_keys='[Holder.a_id]', back_populates='holders'),
    })
    kid = kids.build_model(base)

    class Loose(base):   # модель без описания — ссылки смотрятся и у неё
        __tablename__ = 'loose'
        id = sa.Column(sa.Integer, primary_key=True)
        note_id = sa.Column(sa.Integer, sa.ForeignKey('gc_notes.id'))

    base.registry.configure()
    return base, note, holder, kid, Loose


def _factory(
    base : Any,    # база моделей
    path : Path,   # файл базы
):
    """Фабрика сессий с диспетчером и планом сборщика (как в ``Database``)."""
    engine = sa.create_engine(f"sqlite:///{path.as_posix()}")
    base.metadata.create_all(engine)
    events = te.TableEvents(logger=FakeLogger())
    events.configure(base)
    factory = sessionmaker(bind=engine, info={te.INFO_KEY: events})
    events.listen(factory)
    return factory, events


def _ids(session, model) -> List[int]:
    return sorted(session.scalars(sa.select(model.id)))


@pytest.fixture
def world(tmp_path):
    base, note, holder, kid, loose = _models()
    factory, events = _factory(base, tmp_path / 'gc.db')
    return factory, events, note, holder, kid, loose


# ---------------------------------------------------------------------- план


def test_plan_depth_and_limit(world):
    _, events, *_ = world
    assert (events.plan.depth, events.plan.limit) == (1, 2)
    assert [t.name for t in events.plan.order] == ['gc_notes']


def test_app_plan_notes_depth_one_limit_two():
    """
    Схема клиники: «только используемые» — заметки (Ф1.6.10ж) и файлы фото (Ф1.6.7б);
    обе — концы цепочек (сами ни на что не ссылаются): глубина 1, предел 2.
    """
    from app.database.database_shema.clinic import Base
    plan = te._CollectorPlan.build(Base)
    # assert [t.name for t in plan.order] == ['appointments_notes']
    # ↑ до 2026-11-01 (Ф1.6.7б): файлов фото ещё не было
    assert sorted(t.name for t in plan.order) == ['appointments_notes', 'photo_files']
    assert (plan.depth, plan.limit) == (1, 2)


# ---------------------------------------------------------------------- уборка


def test_changed_reference_collects_old_note_keeps_shared(world):
    factory, events, note, holder, _, _ = world
    with factory() as s:
        n1, n2, n3 = note(text='1'), note(text='2'), note(text='3')
        s.add_all([n1, n2, n3])
        s.flush()
        s.add_all([holder(a_id=n1.id, b_id=n3.id), holder(a_id=n3.id)])
        s.commit()
        h = s.get(holder, 1)
        h.a_id = n2.id                  # 1 больше не нужна
        h.b_id = None                   # 3 ещё у второго держателя
        s.commit()
        assert _ids(s, note) == [2, 3]
    info = events.logger.texts('info')
    assert len(info) == 1
    assert 'gc_notes id=1' in info[0] and 'holders id=1 (a_id)' in info[0]


def test_delete_holder_collects_own_and_cascaded_notes(world):
    factory, _, note, holder, kid, _ = world
    with factory() as s:
        n = [note(text=str(i)) for i in range(4)]
        s.add_all(n)
        s.flush()
        h = holder(a_id=n[0].id, b_id=n[1].id, kids=[kid(note_id=n[2].id)])
        s.add_all([h, holder(a_id=n[3].id)])
        s.commit()
        s.delete(h)                     # каскад — подчинённый со своей заметкой
        s.commit()
        assert _ids(s, note) == [4]


def test_rollback_collects_nothing_and_logs_nothing(world):
    factory, events, note, holder, _, _ = world
    with factory() as s:
        s.add(note(text='1'))
        s.flush()
        s.add(holder(a_id=1))
        s.commit()
        s.get(holder, 1).a_id = None
        s.flush()
        s.rollback()
        s.commit()
        assert _ids(s, note) == [1]
    assert events.logger.texts('info') == []


def test_model_without_def_releases_note(world):
    factory, _, note, _, _, loose = world
    with factory() as s:
        s.add(note(text='1'))
        s.flush()
        s.add(loose(note_id=1))
        s.commit()
        s.get(loose, 1).note_id = None
        s.commit()
        assert _ids(s, note) == []


def test_note_not_referenced_by_unconfigured_table_is_kept_if_used(world):
    """Ссылка из таблицы без описания тоже защищает заметку."""
    factory, _, note, holder, _, loose = world
    with factory() as s:
        s.add(note(text='1'))
        s.flush()
        s.add_all([holder(a_id=1), loose(note_id=1)])
        s.commit()
        s.get(holder, 1).a_id = None
        s.commit()
        assert _ids(s, note) == [1]


def test_already_deleted_note_is_skipped_and_deleted_once(tmp_path):
    """Р-7: заметку уже удалили явно (как старая уборка) — сборщик её пропускает."""
    deleted : List[int] = []
    te.register_action('gc_count_delete', lambda ctx: deleted.append(ctx.target.id), replace=True)
    try:
        base, note, holder, _, _ = _models(note_events=(on('after_delete', 'gc_count_delete'),))
        factory, _ = _factory(base, tmp_path / 'gc.db')
        with factory() as s:
            s.add(note(text='1'))
            s.flush()
            s.add(holder(a_id=1))
            s.commit()
            s.get(holder, 1).a_id = None
            s.flush()
            s.delete(s.get(note, 1))    # явное удаление в той же транзакции
            s.commit()
            assert _ids(s, note) == []
    finally:
        te.unregister_action('gc_count_delete')
    assert deleted == [1]


def test_stale_reverse_collection_does_not_null_live_reference(world):
    """Р-17: загруженная обратная коллекция заметки не обнуляет ссылку держателя."""
    factory, _, note, holder, _, _ = world
    with factory() as s:
        s.add_all([note(text='1'), note(text='2')])
        s.flush()
        s.add(holder(a_id=1))
        s.commit()
        n1 = s.get(note, 1)
        assert [h.id for h in n1.holders] == [1]     # коллекция загружена
        s.get(holder, 1).a_id = 2                    # перевод через столбец
        s.commit()
        assert _ids(s, note) == [2]
        assert s.get(holder, 1).a_id == 2


def test_before_commit_action_runs_once_before_collector(tmp_path):
    """Действие «перед коммитом» отвязывает заметку — её убирает тот же коммит."""
    def unlink(ctx):
        for change in ctx.changes:
            ctx.session.get(holder, change.key).b_id = None

    te.register_action('gc_unlink_b', unlink, replace=True)
    try:
        base, note, holder, _, _ = _models(holder_events=(on('before_commit', 'gc_unlink_b'),))
        factory, _ = _factory(base, tmp_path / 'gc.db')
        with factory() as s:
            s.add(note(text='1'))
            s.flush()
            s.add(holder(b_id=1))
            s.commit()                  # действие отвязало сразу — заметка убрана
            assert _ids(s, note) == []
    finally:
        te.unregister_action('gc_unlink_b')


# ---------------------------------------------------------------------- глубина и круги


def _chain_models():
    """Цепочка «только используемые» A → B → C и корень (хранить всегда) со ссылкой на A."""
    base = declarative_base()
    defs = []
    for name, model, ref in (('ca', 'CA', ('b_id', 'cb', 'CB')), ('cb', 'CB', ('c_id', 'cc', 'CC')),
                             ('cc', 'CC', None)):
        fields = [key()]
        if ref:
            fields.append(fk(ref[0], ref[1], ref[2]))
        defs.append(TableDef(name, model, model + 'DTO', fields=tuple(fields), keep=KEEP_USED))
    models = [d.build_model(base) for d in defs]

    class Root(base):
        __tablename__ = 'root'
        id = sa.Column(sa.Integer, primary_key=True)
        a_id = sa.Column(sa.Integer, sa.ForeignKey('ca.id'))

    base.registry.configure()
    return base, models, Root


def test_chain_collected_in_depth_rounds_without_warning(tmp_path):
    base, (ca, cb, cc), root = _chain_models()
    factory, events = _factory(base, tmp_path / 'gc.db')
    assert (events.plan.depth, events.plan.limit) == (3, 4)
    with factory() as s:
        s.add(cc(id=1))
        s.flush()
        s.add(cb(id=1, c_id=1))
        s.flush()
        s.add(ca(id=1, b_id=1))
        s.flush()
        s.add(root(id=1, a_id=1))
        s.commit()
        s.delete(s.get(root, 1))
        s.commit()
        assert (_ids(s, ca), _ids(s, cb), _ids(s, cc)) == ([], [], [])
    assert events.logger.texts('warning') == []
    assert len(events.logger.texts('info')) == 3


def test_self_reference_among_used_rejected_at_configure():
    base = declarative_base()
    # модель держать: реестр SQLAlchemy хранит классы слабо — выброшенную удалит сборщик Python
    node = TableDef('nodes', 'Node', 'NodeDTO', fields=(key(), fk('next_id', 'nodes', 'Node')),
                    keep=KEEP_USED).build_model(base)
    base.registry.configure()
    with pytest.raises(TableEventError, match='по кругу.*nodes → nodes'):
        te.TableEvents(logger=FakeLogger()).configure(base)
    assert node.__tablename__ == 'nodes'


def test_mutual_reference_among_used_rejected_at_configure():
    base = declarative_base()
    models = [   # держать (реестр хранит классы слабо)
        TableDef('xa', 'XA', 'XADTO', fields=(key(), fk('b_id', 'xb', 'XB')), keep=KEEP_USED).build_model(base),
        TableDef('xb', 'XB', 'XBDTO', fields=(key(), fk('a_id', 'xa', 'XA')), keep=KEEP_USED).build_model(base),
    ]
    base.registry.configure()
    with pytest.raises(TableEventError, match='по кругу'):
        te.TableEvents(logger=FakeLogger()).configure(base)
    assert len(models) == 2


# ---------------------------------------------------------------------- предел и защита


def test_ping_pong_hits_limit_and_rolls_back(world):
    """
    Чужое изменение данных во время уборки (после каждого сброса — новая заметка и
    перепривязка) зацикливает уборку: предел d + 1 = 2, на 3-м круге — откат.
    """
    factory, events, note, holder, _, _ = world
    calls = {'n': 0}

    def ping_pong(session, flush_context):
        log = session.info.get(te._TX_KEY)
        if log is None or log.phase != 'loop':
            return
        calls['n'] += 1
        assert calls['n'] < 50, 'без предела уборка не останавливается'
        session.get(holder, 1).a_note = note(text='снова')

    event.listen(factory, 'after_flush_postexec', ping_pong)
    with factory() as s:
        s.add(note(text='1'))
        s.flush()
        s.add(holder(a_id=1))
        s.commit()
        s.get(holder, 1).a_id = None
        with pytest.raises(TableEventError, match='защита от зацикливания') as info:
            s.commit()
        # повторный коммит без отката — снова ошибка
        with pytest.raises(TableEventError, match='откатить'):
            s.commit()
        s.rollback()
        assert (_ids(s, note), s.get(holder, 1).a_id) == ([1], 1)
    assert info.value.details['предел кругов'] == 2
    assert len(info.value.details['круги']) == 2
    assert events.logger.texts('info') == []


def test_late_candidate_warned_and_not_leaked(world):
    """Р-15: ссылку убрали после уборки — предупреждение, следующая транзакция её не трогает."""
    factory, events, note, holder, _, _ = world
    with factory() as s:
        s.add_all([note(text='1'), note(text='2')])
        s.flush()
        s.add(holder(a_id=1, b_id=2))
        s.commit()
    flag = {'on': True}

    def late(session):
        if flag['on']:
            session.get(holder, 1).b_id = None

    event.listen(factory, 'before_commit', late)   # после диспетчера — уже после уборки
    with factory() as s:
        s.get(holder, 1).a_id = 1                  # что-то меняем, чтобы был коммит
        s.commit()
        flag['on'] = False
        s.add(note(text='3'))
        s.commit()
        assert _ids(s, note) == [1, 2, 3]
    assert any('после уборки' in w for w in events.logger.texts('warning'))


# ---------------------------------------------------------------------- полная проверка (М19)


def test_find_and_delete_unused(world):
    factory, events, note, holder, _, _ = world
    with factory() as s:
        s.add_all([note(text=str(i)) for i in range(3)])
        s.flush()
        s.add(holder(a_id=2))
        s.commit()
        found = events.find_unused(s)
        assert found == {'gc_notes': [1, 3]}
        s.get(holder, 1).a_id = None   # пока список показывали — отвязали 2, привязали 3
        s.get(holder, 1).b_id = 3
        s.flush()
        deleted = events.delete_unused(s, found)
        s.commit()
        assert deleted == {'gc_notes': [1]}
        assert _ids(s, note) == [3]    # 2 — обычной уборкой, 3 — привязана
    assert any('полная проверка' in t for t in events.logger.texts('info'))
    with pytest.raises(ValueError, match='не таблицы'):
        with factory() as s:
            events.delete_unused(s, {'holders': [1]})


def test_delete_unused_on_fresh_session_keeps_log(world):
    """Итоговая перепроверка: delete_unused первым действием сессии — журнал удалений не теряется."""
    factory, events, note, _, _, _ = world
    with factory() as s:
        s.add_all([note(text='1'), note(text='2')])
        s.commit()
    with factory() as s:                    # транзакция ещё не начата
        deleted = events.delete_unused(s, {'gc_notes': [1, 2]})
        s.commit()
        assert (deleted, _ids(s, note)) == ({'gc_notes': [1, 2]}, [])
    info = [t for t in events.logger.texts('info') if 'полная проверка' in t]
    assert len(info) == 2
    assert not any('отброшен' in w for w in events.logger.texts('warning'))
