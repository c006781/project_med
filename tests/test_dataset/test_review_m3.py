# tests/test_dataset/test_review_m3.py

"""
Сверка модуля наборов данных (заход М3, 2026-10-25): находки DS1–DS6 и непокрытое.

Каждая находка — тест, падающий на коде до исправления (номер — в имени теста и в
``app/utils/dataset/IMPLEMENTATION.md``).
"""

import pytest

from app.utils.dataset import (
    ActionSet, AggFunc, AggregateDef, Capabilities, Condition, DataSet, DataSetError, DataSource,
    EventKind, FetchMode, FieldDef, FieldKind, KeyedTotals, MemoryBackend, Op, Order, Query,
    sort_rows,
)


def numbered(n=5, **fields):
    """Источник в памяти: строки ``id`` 1..n."""
    return MemoryBackend([{'id': i, 'name': f'Имя{i}'} for i in range(1, n + 1)], **fields)


class Hiding:
    """Способ записи с ``RowOverlay``, который прячет строки (протокол разрешает «убирать»)."""

    def __init__(self, hidden):
        self.hidden = set(hidden)

    def insert(self, ds, values):
        return ds.backend.insert(values)

    def update(self, ds, key, changes, row, original):
        return ds.backend.update(key, changes)

    def delete(self, ds, key, row):
        ds.backend.delete(key)

    def overlay(self, ds, rows, query, first):
        return [r for r in rows if r['id'] not in self.hidden]

    def row_status(self, ds, key):
        return None


class Drafts:
    """Отложенная запись: новые строки (ключи < 0) — в первое окно, удаление новой — убирает её."""

    def __init__(self, new_rows=(), changed=None, check_conditions=True):
        self.new = {r['id']: dict(r) for r in new_rows}
        self.changed = dict(changed or {})
        self.check_conditions = check_conditions

    def insert(self, ds, values):
        key = min(list(self.new) + [0]) - 1
        self.new[key] = dict(values, id=key)
        return dict(self.new[key])

    def update(self, ds, key, changes, row, original):
        self.changed.setdefault(key, {}).update(changes)
        return dict(row)

    def delete(self, ds, key, row):
        self.new.pop(key, None)

    def overlay(self, ds, rows, query, first):
        rows = [dict(r, **self.changed.get(r['id'], {})) for r in rows]
        if first:
            new = [dict(r) for r in self.new.values()]
            if self.check_conditions:
                new = [r for r in new if all(c.matches(r) for c in query.conditions)]
            rows = new + rows
        return rows

    def row_status(self, ds, key):
        return 'new' if key in self.new else None


# --------------------------------------------------------------------------- DS1

def test_ds1_in_never_matches_empty_value_like_sql():
    """DS1: «IN» с пустым значением строки — «не подходит» (как в SQL и у источника поверх БД)."""
    rows = [{'id': 1, 'p': None}, {'id': 2, 'p': 5}]
    assert not Condition('p', Op.IN, (None, 5)).matches(rows[0])
    assert Condition('p', Op.IN, (None, 5)).matches(rows[1])
    assert not Condition('p', Op.IN, None).matches(rows[1])           # пустой список — не падение
    query = Query(conditions=(Condition('p', Op.IN, [None, 5]),))
    assert MemoryBackend(rows).fetch(query).rows == [{'id': 2, 'p': 5}]


# --------------------------------------------------------------------------- DS2

def test_ds2_next_and_move_to_skip_empty_portion():
    """DS2: порция, из которой не добавилось строк (способ записи их спрятал), не конец набора."""
    ds = DataSet(numbered(5), writer=Hiding({3, 4}), fetch_size=2)
    ds.open()
    assert [ds.key_at(i) for i in range(ds.row_count)] == [1, 2]
    assert ds.next() and ds.current_key == 2
    assert ds.next() and ds.current_key == 5                          # порция [3, 4] пуста
    other = DataSet(numbered(5), writer=Hiding({3, 4}), fetch_size=2)
    other.open()
    other.move_to(2)
    assert other.current_key == 5
    with pytest.raises(IndexError):
        other.move_to(3)


# --------------------------------------------------------------------------- DS3

def test_ds3_deleting_unsaved_row_does_not_shift_next_portion():
    """DS3: новая несохранённая строка (её добавил способ записи) — не из источника: её
    удаление не сдвигает смещение догрузки (раньше порция читалась повторно, а ``next``
    на ней останавливался)."""
    backend = numbered(4)
    ds = DataSet(backend, writer=Drafts([{'id': -1, 'name': 'Новый'}]), fetch_size=1)
    ds.open()
    assert [ds.key_at(i) for i in range(ds.row_count)] == [-1, 1]
    ds.delete()                                                       # новая — убирается
    assert ds.current_key == 1
    reads = backend.fetch_count
    assert ds.next() and ds.current_key == 2
    assert backend.fetch_count == reads + 1                           # одна порция, без повтора


# --------------------------------------------------------------------------- DS4

def test_ds4_deleted_rows_are_no_longer_marked():
    """DS4: удалённая (убранная из набора) запись не остаётся отмеченной: раньше
    «Удалить отмеченные» оставлял отмеченными удалённые записи (меню — «есть отмеченные»)."""
    backend = MemoryBackend([{'id': i} for i in range(1, 5)],
                            fields=[FieldDef('id'), FieldDef('mark', kind=FieldKind.BOOLEAN,
                                                             local=True, default=False)])
    ds = DataSet(backend)
    ds.open()
    actions = ActionSet()
    ds.set_local('mark', True, index=0); ds.set_local('mark', True, index=2)
    assert actions.run('delete_marked', ds) == 2
    assert actions.selection(ds) == [] and not actions.can_run('unmark_all', ds)
    ds.set_local('mark', True, index=0)                               # id 2
    backend.delete(2)                                                 # удалили в другом месте
    assert ds.reload_row(0) is False
    assert ds.local_keys('mark') == []


# --------------------------------------------------------------------------- DS5

def clinic(writer):
    photos_backend = MemoryBackend(
        [{'id': 1, 'visit_id': 10, 'paid': True}, {'id': 2, 'visit_id': 10, 'paid': True},
         {'id': 3, 'visit_id': 20, 'paid': True}])
    photos = DataSet(photos_backend, writer=writer)
    return AggregateDef(photos, 'visit_id', where=(Condition('paid', Op.EQ, True),))


def test_ds5_aggregate_applies_where_to_unsaved_values(monkeypatch):
    """DS5: условие итога (``where``) — и к несохранённым значениям: строку, у которой в
    отложенной записи условие перестало выполняться, итог больше не считает."""
    paid = clinic(Drafts(changed={2: {'paid': False}}))
    assert paid.compute([10, 20]) == {10: 1, 20: 1}


def test_ds5_aggregate_counts_new_row_once_across_chunks(monkeypatch):
    """DS5: новая строка способа записи, не проверяющего условия запроса, — один раз, а не
    по разу на каждый кусок ключей (``CHUNK``)."""
    from app.utils.dataset import aggregate as agg_module
    monkeypatch.setattr(agg_module, 'CHUNK', 1)
    count = clinic(Drafts([{'id': -1, 'visit_id': 20, 'paid': True}], check_conditions=False))
    assert count.compute([10, 20, 30]) == {10: 2, 20: 2, 30: 0}


# --------------------------------------------------------------------------- непокрытое: итоги

class Counts(KeyedTotals):
    """Объект-итоги: число и сумма по подчинённым из списка (вместо SQL ``GROUP BY``)."""

    def __init__(self, rows, **kw):
        super().__init__(**kw)
        self.rows, self.calls = rows, []

    def fetch(self, keys):
        self.calls.append(list(keys))
        result = {}
        for row in self.rows:
            if row['visit_id'] in keys:
                item = result.setdefault(row['visit_id'], {'n': 0, 'total': 0})
                item['n'] += 1
                item['total'] += row['sum']
        return result


class Pending(Drafts):
    """Отложенная запись, умеющая перечислить несохранённое (``PendingChanges``)."""

    def __init__(self, pairs):
        super().__init__()
        self.pairs = pairs

    def pending(self, ds):
        return list(self.pairs)


def test_keyed_totals_one_call_per_window_and_delta(monkeypatch):
    from app.utils.dataset import aggregate as agg_module
    monkeypatch.setattr(agg_module, 'CHUNK', 2)
    rows = [{'visit_id': 10, 'sum': 100}, {'visit_id': 10, 'sum': 50}, {'visit_id': 20, 'sum': 7}]
    child = DataSet(MemoryBackend([]), writer=Pending([
        (None, {'id': -1, 'visit_id': 30}),                           # новая у 30
        ({'id': 5, 'visit_id': 10}, None),                            # удалена у 10
        ({'id': 6, 'visit_id': 10}, {'id': 6, 'visit_id': 20}),       # перенесена 10 → 20
        ({'id': 7, 'visit_id': 20}, {'id': 7, 'visit_id': 20}),       # правка без переноса
    ]))
    totals = Counts(rows, child=child, link_field='visit_id', unsaved='delta', counts=('n',))
    visits = DataSet(MemoryBackend([{'id': 10}, {'id': 20}, {'id': 30}]), fields=[
        FieldDef('id'), FieldDef('n', aggregate=totals.column('n', empty=0)),
        FieldDef('total', aggregate=totals.column('total'))])
    visits.open()
    assert totals.calls == [[10, 20], [30]]                           # кусками, один раз на окно
    assert [visits.value('n', i) for i in range(3)] == [0, 2, 1]
    assert [visits.value('total', i) for i in range(3)] == [150, 7, None]
    assert totals.depends_on(child) and visits.fields['n'].aggregate.depends_on(child)
    assert visits.fields['n'].aggregate.compute([20]) == {20: 2}      # столбец отдельно
    assert totals.compute_many([None]) == {None: {'n': 0, 'total': None}}
    with pytest.raises(ValueError, match='допустимо'):
        KeyedTotals(unsaved='drop')
    with pytest.raises(ValueError, match='нужны набор'):
        KeyedTotals(unsaved='delta')
    with pytest.raises(NotImplementedError):
        KeyedTotals().fetch([1])
    plain = Counts(rows, child=DataSet(MemoryBackend([])), link_field='visit_id',
                   unsaved='delta', counts=('n',))
    assert plain.compute_many([10])[10]['n'] == 2                     # способ записи без pending


def test_aggregate_custom_function_min_and_backend_without_filter():
    class NoFilter(MemoryBackend):
        capabilities = Capabilities(filter=False, sort=False, window=False, count=False)

    backend = NoFilter([{'id': 1, 'p': 1, 'v': 5}, {'id': 2, 'p': 1, 'v': 3}, {'id': 3, 'p': 2, 'v': 9}])
    assert AggregateDef(backend, 'p', AggFunc.MIN, 'v').compute([1, 2, 3]) == {1: 3, 2: 9, 3: None}
    spread = AggregateDef(backend, 'p', lambda rows: [r['id'] for r in rows])
    assert spread.compute([1, 3]) == {1: [1, 2], 3: []}
    assert spread.empty_value == []
    assert AggregateDef(backend, 'p', 'sum', 'v').func is AggFunc.SUM  # строкой — тоже


def test_aggregate_error_while_showing_is_logged_not_raised(caplog):
    class Flaky:
        empty_value = 0
        fail = False

        def compute(self, keys):
            if self.fail:
                raise RuntimeError('нет связи')
            return {}                                                 # ключа нет — посчитать при показе

        def depends_on(self, ds):
            return False

    flaky = Flaky()
    ds = DataSet(numbered(1), fields=[FieldDef('id'), FieldDef('n', aggregate=flaky)])
    ds.open()
    flaky.fail = True
    assert ds.value('n') is None and 'не посчитан' in caplog.text    # таблица не ломается


# --------------------------------------------------------------------------- непокрытое: набор

def test_set_params_reload_and_remove():
    class Params(MemoryBackend):
        def fetch(self, query):
            self.seen = dict(query.params)
            return super().fetch(query)

    backend = Params([{'id': 1}, {'id': 2}])
    ds = DataSet(backend)
    ds.open(); ds.next()
    ds.set_params(search='Пет', page=None)
    assert backend.seen == {'search': 'Пет'} and ds.current_index == 0
    ds.set_params(search=None)
    assert backend.seen == {}


def test_sort_in_memory_with_mixed_types_falls_back_to_text():
    ds = DataSet(MemoryBackend([{'id': 1}, {'id': 2}, {'id': 3}]), fetch_mode=FetchMode.ALL,
                 fields=[FieldDef('id'), FieldDef('v', calculated=lambda r: {1: 'б', 2: 5, 3: None}[r['id']])])
    ds.open()
    ds.set_order('v')
    assert [ds.key_at(i) for i in range(3)] == [2, 1, 3]              # '5' < 'б', пустое — в конце
    assert sort_rows([{'a': 'x'}, {'a': 1}], [Order('a', True)])[0] == {'a': 'x'}


# --------------------------------------------------------------------------- DS6

def test_ds6_failed_reread_keeps_rows_and_current_row():
    """DS6: ошибка чтения при перечитывании (``refresh``, ``set_filter``, смена главной) —
    набор остаётся как был. Раньше строки уже были стёрты, а номер текущей строки указывал
    за конец (правило H1 нарушено): таблица пустела, «следующая порция» — не читалась."""
    class Failing(MemoryBackend):
        fail = False

        def fetch(self, query):
            if self.fail:
                raise ConnectionError('нет связи')
            return super().fetch(query)

    backend = Failing([{'id': i} for i in range(1, 5)])
    ds = DataSet(backend, fetch_size=2)
    errors = []
    ds.subscribe(lambda e: errors.append(e.error) if e.kind is EventKind.ERROR else None)
    ds.open(); ds.next()
    query = ds.query
    backend.fail = True
    for call in (ds.refresh, lambda: ds.set_filter(Condition('id', Op.GT, 1)),
                 lambda: ds.set_master({'id': 1}), lambda: ds.set_params(search='x'),
                 lambda: ds.set_order('-id'), ds.fetch_more):
        with pytest.raises(ConnectionError):
            call()
        assert (ds.row_count, ds.current_index, ds.current_key, ds.has_more) == (2, 1, 2, True)
        assert ds.query == query                                      # условия — прежние
    assert len(errors) == 6 and all(isinstance(e, ConnectionError) for e in errors)
    backend.fail = False
    assert ds.next() and ds.current_key == 3                          # набор работает дальше


def test_ds6_link_retries_after_detail_read_error():
    """DS6: связь «главная → подчинённая» после ошибки чтения подчинённого не считает его
    сверенным — на следующем событии главного пробует снова."""
    class Failing(MemoryBackend):
        fail = False

        def fetch(self, query):
            if self.fail:
                raise ConnectionError('нет связи')
            return super().fetch(query)

    from app.utils.dataset import MasterDetailLink
    patients = DataSet(MemoryBackend([{'id': 1}, {'id': 2}]), name='patients')
    visits_backend = Failing([{'id': 10, 'patient_id': 1}, {'id': 20, 'patient_id': 2}],
                             fields=[FieldDef('id'), FieldDef('patient_id', references='patients')])
    visits = DataSet(visits_backend)
    MasterDetailLink(patients, visits)
    patients.open(); visits.open()
    visits_backend.fail = True
    patients.next()                                                   # ошибка — в журнал
    assert visits.current_key == 10                                   # подчинённый — как был
    visits_backend.fail = False
    patients.refresh()                                                # следующее событие главного
    assert visits.current_key == 20 and visits.row_count == 1


def test_delete_during_edit_discards_edit_and_misc_guards():
    ds = DataSet(numbered(3))
    assert ds.recalc() == 0 and ds.touch() == 0                       # закрыт — ничего
    ds.open()
    ds.set_value('name', 'Правка')
    ds.delete()                                                       # правка отброшена, строка удалена
    assert ds.backend.get(1) is None and ds.current_key == 2
    ds.edit()
    with pytest.raises(DataSetError, match='в правке'):
        ds.reload_row()
    ds.edit()                                                         # уже в правке — ничего
    ds.post()                                                         # без изменений — без записи
    assert ds.modified is False and ds.backend.get(2) == {'id': 2, 'name': 'Имя2'}
    assert repr(ds).startswith('<DataSet MemoryBackend browse')
    with pytest.raises(KeyError):
        ds.set_value('нет_поля', 1)


def test_reload_row_with_overlay_and_local_field():
    backend = MemoryBackend([{'id': 1, 'name': 'А'}],
                            fields=[FieldDef('id'), FieldDef('name'), FieldDef('mark', local=True, default=False)])
    writer = Drafts(changed={1: {'name': 'Черновик'}})
    ds = DataSet(backend, writer=writer)
    ds.open()
    ds.set_local('mark', True)
    backend.update(1, {'name': 'Б'})
    writer.changed = {}
    assert ds.reload_row() and ds.value('name') == 'Б' and ds.value('mark') is True
    hiding = Hiding(())
    hidden = DataSet(MemoryBackend([{'id': 1}]), writer=hiding)
    hidden.open()
    hiding.hidden.add(1)
    assert hidden.reload_row() is False and hidden.row_count == 0     # способ записи спрятал


def test_datasource_switch_to_none_and_listeners():
    from app.utils.dataset import Emitter, DataEvent
    ds = DataSet(numbered(1))
    source = DataSource(ds)
    seen = []
    source.subscribe(lambda e: seen.append(e.kind))
    source.dataset = ds                                               # тот же — ничего
    source.dataset = None
    assert seen == [EventKind.CLOSED] and source.enabled
    emitter = Emitter()
    emitter.subscribe(seen.append)
    assert emitter.listeners == (seen.append,)

    def broken(event):
        raise RuntimeError('упал')

    emitter.subscribe(broken)
    emitter.emit(DataEvent(EventKind.OPENED, None))                   # ошибка подписчика — в журнал
    assert seen[-1].kind is EventKind.OPENED
