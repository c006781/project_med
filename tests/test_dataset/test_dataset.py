# tests/test_dataset/test_dataset.py

"""Набор данных: чтение порциями, навигация, правка, события, способы записи, связи."""

import pytest

from app.utils.dataset import (
    Capabilities, Condition, DataSet, DataSetError, DataSource, EventKind, FetchMode,
    FieldDef, FieldKind, LinkError, LookupDef, MasterDetailLink, MemoryBackend, Op, Page,
    ReadOnlyError, State, ValidationError,
)


def people(n=5):
    return MemoryBackend([{'id': i, 'name': f'Имя{i}', 'age': 20 + i} for i in range(1, n + 1)],
                         fields=[FieldDef('id', read_only=True), FieldDef('name', 'Имя', FieldKind.STRING, required=True),
                                 FieldDef('age', kind=FieldKind.INTEGER)])


def recorder(ds):
    events = []
    ds.subscribe(lambda e: events.append((e.kind, e.index, e.count) if e.kind in (
        EventKind.ROWS_INSERTED, EventKind.ROWS_REMOVED) else (e.kind, e.old, e.new) if e.kind in (
        EventKind.CURRENT_CHANGED, EventKind.STATE_CHANGED) else (e.kind,)))
    return events


# --------------------------------------------------------------------------- чтение

def test_on_demand_loads_in_portions():
    backend = people(5)
    ds = DataSet(backend, fetch_size=2)
    ds.open()
    assert (ds.row_count, ds.total, ds.has_more, ds.current_index) == (2, 5, True, 0)
    assert ds.next() and ds.current_index == 1
    assert ds.next() and ds.row_count == 4                    # догрузка на краю
    assert ds.fetch_all() == 1 and not ds.has_more and ds.row_count == 5
    assert backend.fetch_count == 3


def test_fetch_all_mode_and_size_validation():
    ds = DataSet(people(5), fetch_mode=FetchMode.ALL, fetch_size=1)
    ds.open()
    assert ds.row_count == 5 and not ds.has_more
    with pytest.raises(ValueError):
        DataSet(people(), fetch_size=0)


def test_last_and_locate_load_on_demand():
    ds = DataSet(people(7), fetch_size=2)
    ds.open()
    assert ds.locate(5) and ds.current_key == 5 and ds.row_count == 6
    assert not ds.locate(99)
    assert ds.last() and ds.current_key == 7 and ds.eof
    assert ds.first() and ds.bof and not ds.prior()


def test_move_to_beyond_loaded_and_errors():
    ds = DataSet(people(4), fetch_size=1)
    with pytest.raises(DataSetError, match='не открыт'):
        ds.next()
    ds.open()
    ds.move_to(3)
    assert ds.current_key == 4
    with pytest.raises(IndexError):
        ds.move_to(10)


def test_empty_dataset():
    ds = DataSet(MemoryBackend([]))
    ds.open()
    assert ds.current_index == -1 and ds.current is None and ds.bof and ds.eof
    assert not ds.first() and not ds.next() and not ds.last()
    with pytest.raises(DataSetError, match='нет текущей'):
        ds.edit()


def test_fields_from_rows_when_backend_silent():
    ds = DataSet(MemoryBackend([{'id': 1, 'x': 2}]))
    ds.open()
    assert ds.fields.names() == ['id', 'x']


def test_filter_order_params_and_refresh_keeps_record():
    ds = DataSet(people(6), fetch_size=2, order=['-age'])
    ds.open()
    assert [ds.key_at(i) for i in range(ds.row_count)] == [6, 5]
    ds.next(); ds.next()                                       # загружено 4, текущая — id 4
    assert ds.current_key == 4
    ds.set_order('age')
    assert ds.current_key == 4 and ds.row_count >= 4           # та же запись после пересортировки
    ds.set_filter(Condition('age', Op.GE, 24))
    assert [ds.key_at(i) for i in range(ds.row_count)] == [4, 5] and ds.current_index == 0
    ds.refresh()
    assert ds.current_key == 4
    ds.set_filter()
    assert ds.total == 6


class Dumb:
    """Источник, который умеет только отдать всё (ни фильтра, ни сортировки, ни окна, ни подсчёта)."""

    key_field = 'id'
    capabilities = Capabilities(filter=False, sort=False, window=False, count=False)

    def __init__(self, rows):
        self.rows = rows

    def fields(self):
        return []

    def fetch(self, query):
        return Page([dict(r) for r in self.rows])

    def get(self, key):
        return next((dict(r) for r in self.rows if r['id'] == key), None)


def test_backend_without_capabilities_handled_in_memory():
    ds = DataSet(Dumb([{'id': i, 'v': i % 3} for i in range(1, 8)]), fetch_size=2, order=['-id'],
                 conditions=[Condition('v', Op.NE, 0)])
    ds.open()
    assert [ds.key_at(i) for i in range(ds.row_count)] == [7, 5]
    ds.fetch_all()
    assert [ds.key_at(i) for i in range(ds.row_count)] == [7, 5, 4, 2, 1]
    with pytest.raises(DataSetError, match='только для чтения'):
        ds.edit()


def test_open_events_order():
    ds = DataSet(people(2))
    events = recorder(ds)
    ds.open()
    assert events == [(EventKind.OPENED,), (EventKind.REFRESHED,),           # H2: «открыт» — первым
                      (EventKind.STATE_CHANGED, State.INACTIVE, State.BROWSE),
                      (EventKind.CURRENT_CHANGED, -1, 0)]
    events.clear()
    ds.fetch_more()
    assert events == []                                          # всё загружено — нечего
    ds.close()
    assert events[-3:] == [(EventKind.CLOSED,), (EventKind.STATE_CHANGED, State.BROWSE, State.INACTIVE),
                           (EventKind.CURRENT_CHANGED, 0, -1)] and ds.row_count == 0


def test_source_error_reported_and_dataset_stays_closed():
    class Broken(Dumb):
        def fetch(self, query):
            raise ConnectionError('нет связи')
    ds = DataSet(Broken([]))
    errors = []
    ds.subscribe(lambda e: errors.append(e.error) if e.kind is EventKind.ERROR else None)
    with pytest.raises(ConnectionError):
        ds.open()
    assert not ds.active and isinstance(errors[0], ConnectionError)


# --------------------------------------------------------------------------- значения

def test_calculated_and_lookup_values():
    patients = MemoryBackend([{'id': 1, 'last': 'Петров'}])
    ds = DataSet(MemoryBackend([{'id': 10, 'patient_id': 1, 'price': 100, 'qty': 3}]), fields=[
        FieldDef('id'), FieldDef('patient_id'), FieldDef('price'), FieldDef('qty'),
        FieldDef('sum', calculated=lambda r: r['price'] * r['qty'], display=lambda v: f'{v} ₽'),
        FieldDef('patient', lookup=LookupDef('patient_id', patients, 'last')),
    ])
    ds.open()
    assert ds.value('sum') == 300 and ds.text('sum') == '300 ₽' and ds.value('patient') == 'Петров'
    ds.set_value('qty', 4)                                     # во время правки — с правкой
    assert ds.value('sum') == 400
    with pytest.raises(DataSetError, match='только для чтения'):
        ds.set_value('sum', 1)
    ds.post()
    assert ds.backend.get(10) == {'id': 10, 'patient_id': 1, 'price': 100, 'qty': 4}  # вычисляемые не пишутся


# --------------------------------------------------------------------------- правка

def test_edit_post_cancel():
    ds = DataSet(people(3))
    ds.open()
    events = recorder(ds)
    ds.set_value('name', 'Новое')                              # AutoEdit
    assert ds.state is State.EDIT and ds.modified and ds.backend.get(1)['name'] == 'Имя1'
    ds.post()
    assert ds.state is State.BROWSE and ds.backend.get(1)['name'] == 'Новое'
    ds.edit(); ds.set_value('name', 'X'); ds.cancel()
    assert ds.value('name') == 'Новое' and ds.backend.get(1)['name'] == 'Новое'
    assert (EventKind.STATE_CHANGED, State.BROWSE, State.EDIT) in events
    with pytest.raises(DataSetError, match='только для чтения'):
        ds.set_value('id', 5)


def test_post_without_changes_does_not_write():
    calls = []

    class Spy:
        def insert(self, ds, values): calls.append('i'); return dict(values, id=1)
        def update(self, ds, key, changes, row, original): calls.append('u'); return dict(row)
        def delete(self, ds, key, row): calls.append('d')
    ds = DataSet(people(1), writer=Spy())
    ds.open(); ds.edit(); ds.post()
    assert calls == []


def test_validation_keeps_editing():
    ds = DataSet(people(2))
    ds.open()
    ds.set_value('name', '')
    with pytest.raises(ValidationError) as info:
        ds.post()
    assert 'name' in info.value.errors and ds.state is State.EDIT
    with pytest.raises(ValidationError):
        ds.next()                                              # auto_post тоже проверяет
    assert ds.current_index == 0
    ds.cancel()
    assert ds.next()


def test_auto_post_on_navigation_and_disabled():
    ds = DataSet(people(3))
    ds.open()
    ds.set_value('name', 'А')
    ds.next()
    assert ds.backend.get(1)['name'] == 'А' and ds.state is State.BROWSE
    strict = DataSet(people(3), auto_post=False)
    strict.open()
    strict.set_value('name', 'Б')
    with pytest.raises(DataSetError, match='сохраните или отмените'):
        strict.next()
    with pytest.raises(DataSetError):
        strict.refresh()


def test_insert_append_defaults_and_cancel():
    backend = MemoryBackend([{'id': 1, 'name': 'А'}, {'id': 2, 'name': 'Б'}],
                            fields=[FieldDef('id'), FieldDef('name', required=True),
                                    FieldDef('status', default='new')])
    ds = DataSet(backend)
    ds.open(); ds.next()
    events = recorder(ds)
    ds.insert({'name': 'В'})                                   # перед текущей
    assert ds.current_index == 1 and ds.state is State.INSERT and ds.row_count == 3
    assert ds.current == {'id': None, 'name': 'В', 'status': 'new'}
    assert events[:2] == [(EventKind.ROWS_INSERTED, 1, 1), (EventKind.CURRENT_CHANGED, 2, 1)]  # D1/H1: прежняя запись сдвинулась на 2
    ds.cancel()
    assert ds.row_count == 2 and ds.current_key == 2 and ds.state is State.BROWSE
    ds.append({'name': 'Г'}); ds.post()
    assert ds.current_index == 2 and ds.current_key == 3 and backend.get(3)['status'] == 'new'


def test_writer_error_keeps_edit_and_reports():
    class Failing:
        def insert(self, ds, values): raise PermissionError('нельзя')
        def update(self, ds, key, changes, row, original): raise PermissionError('нельзя')
        def delete(self, ds, key, row): raise PermissionError('нельзя')
    ds = DataSet(people(2), writer=Failing())
    ds.open()
    errors = []
    ds.subscribe(lambda e: errors.append(e.error) if e.kind is EventKind.ERROR else None)
    ds.set_value('name', 'X')
    with pytest.raises(PermissionError):
        ds.post()
    assert ds.state is State.EDIT and ds.value('name') == 'X' and len(errors) == 1
    ds.cancel()
    with pytest.raises(PermissionError):
        ds.delete()
    assert ds.row_count == 2


def test_writer_must_return_key():
    class NoKey:
        def insert(self, ds, values): return dict(values)
        def update(self, ds, key, changes, row, original): return dict(row)
        def delete(self, ds, key, row): pass
    ds = DataSet(people(1), writer=NoKey())
    ds.open(); ds.append({'name': 'А'})
    with pytest.raises(DataSetError, match='ключ'):
        ds.post()


def test_read_only_and_readonly_backend():
    ds = DataSet(people(1), read_only=True)
    ds.open()
    assert not ds.can_modify
    with pytest.raises(DataSetError, match='только для чтения'):
        ds.append()

    class ReadOnly(Dumb):
        capabilities = Capabilities()

        def fetch(self, query):
            return Page([dict(r) for r in self.rows], total=len(self.rows))
    ds2 = DataSet(ReadOnly([{'id': 1}]))
    ds2.open()
    with pytest.raises(DataSetError):
        ds2.edit()
    from app.utils.dataset import DirectWriter
    with pytest.raises(ReadOnlyError):
        DirectWriter(ReadOnly([])).delete(None, 1, {})


def test_delete_and_no_skip_on_next_portion():
    backend = people(6)
    ds = DataSet(backend, fetch_size=2)
    ds.open()
    ds.delete()                                                # id 1
    assert ds.current_key == 2 and backend.get(1) is None
    ds.fetch_more()                                            # смещение учло удаление
    assert [ds.key_at(i) for i in range(ds.row_count)] == [2, 3, 4]


def test_no_duplicates_after_insert_shifts_window():
    backend = people(4)
    ds = DataSet(backend, fetch_size=2, order=['id'])
    ds.open()
    backend.insert({'id': 0, 'name': 'Первый'})               # кто-то добавил строку в начало
    ds.fetch_all()
    keys = [ds.key_at(i) for i in range(ds.row_count)]
    assert len(keys) == len(set(keys)) and set(keys) == {1, 2, 3, 4}


def test_reload_row():
    backend = people(2)
    ds = DataSet(backend)
    ds.open()
    backend.update(1, {'name': 'Извне'})
    assert ds.reload_row() and ds.value('name') == 'Извне'
    backend.delete(1)
    assert not ds.reload_row() and ds.row_count == 1 and ds.current_key == 2


# --------------------------------------------------------------------------- свой способ записи

class Deferred:
    """Отложенная запись: копит изменения, временные ключи < 0, удалённое видно с пометкой."""

    def __init__(self):
        self.new, self.changed, self.deleted, self._next = {}, {}, set(), -1

    def insert(self, ds, values):
        row = dict(values, id=self._next)
        self.new[self._next] = row
        self._next -= 1
        return row

    def update(self, ds, key, changes, row, original):
        (self.new if key in self.new else self.changed).setdefault(key, {}).update(changes)
        return dict(row)

    def delete(self, ds, key, row):
        if key in self.new:
            del self.new[key]
        else:
            self.deleted.add(key)

    def overlay(self, ds, rows, query, first):
        rows = [dict(r, **self.changed.get(r['id'], {})) for r in rows]
        if first:
            rows = list(self.new.values()) + rows
        return rows

    def row_status(self, ds, key):
        if key in self.deleted:
            return 'deleted'
        return 'new' if key in self.new else 'modified' if key in self.changed else None


def test_custom_writer_with_overlay_survives_refresh():
    backend = people(3)
    writer = Deferred()
    ds = DataSet(backend, writer=writer)
    ds.open()
    ds.set_value('name', 'Правка'); ds.post()
    ds.append({'name': 'Новый'}); ds.post()
    assert ds.current_key == -1 and backend.get(1)['name'] == 'Имя1'   # в хранилище — ничего
    ds.first(); ds.delete()                                    # пометка, строка остаётся видна
    ds.refresh()
    assert ds.row_count == 4 and ds.locate(-1)
    assert ds.row_status(ds.current_index) == 'new'
    ds.locate(1)
    assert ds.value('name') == 'Правка' and ds.row_status() == 'deleted'


# --------------------------------------------------------------------------- источник событий

def test_datasource_pause_switch_and_errors():
    ds1, ds2 = DataSet(people(2)), DataSet(people(3))
    source = DataSource(ds1)
    seen = []
    source.subscribe(lambda e: seen.append((e.kind, e.dataset)))
    ds1.open()
    assert (EventKind.OPENED, ds1) in seen
    seen.clear()
    with source.paused():
        ds1.next(); ds1.set_value('name', 'x'); ds1.post()
        ds1._emit(EventKind.ERROR, error=RuntimeError('сбой'))
    assert [k for k, _ in seen] == [EventKind.ERROR, EventKind.REFRESHED]  # ошибка — сразу, остальное — одним
    seen.clear()
    source.dataset = ds2
    assert seen == [(EventKind.REFRESHED, ds2)]
    ds1.prior()
    assert len(seen) == 1                                       # старый набор больше не слышно
    source.dataset = None
    assert seen[-1] == (EventKind.CLOSED, None)


def test_nested_pause():
    ds = DataSet(people(2))
    source = DataSource(ds)
    seen = []
    source.subscribe(lambda e: seen.append(e.kind))
    ds.open(); seen.clear()
    with source.paused():
        with source.paused():
            ds.next()
        assert seen == []
    assert seen == [EventKind.REFRESHED]


# --------------------------------------------------------------------------- связи

def tree():
    patients = DataSet(MemoryBackend([{'id': 1, 'name': 'П1'}, {'id': 2, 'name': 'П2'}],
                                     fields=[FieldDef('id'), FieldDef('name')]), name='patients')
    visits = DataSet(MemoryBackend(
        [{'id': 10, 'patient_id': 1}, {'id': 20, 'patient_id': 2}, {'id': 21, 'patient_id': 2}],
        fields=[FieldDef('id'), FieldDef('patient_id', references='patients')]), name='appointments')
    photos = DataSet(MemoryBackend(
        [{'id': 100, 'appointment_id': 10}, {'id': 200, 'appointment_id': 20}],
        fields=[FieldDef('id'), FieldDef('appointment_id', references='appointments')]), name='photos')
    return patients, visits, photos


def keys(ds):
    return [ds.key_at(i) for i in range(ds.row_count)]


def test_three_level_chain():
    patients, visits, photos = tree()
    MasterDetailLink(DataSource(patients), visits)
    MasterDetailLink(DataSource(visits), photos)
    for ds in (patients, visits, photos):
        ds.open()
    assert keys(visits) == [10] and keys(photos) == [100]
    patients.next()
    assert keys(visits) == [20, 21] and keys(photos) == [200]
    visits.next()
    assert keys(photos) == []
    photos.append(); photos.post()
    assert photos.backend.get(photos.current_key)['appointment_id'] == 21   # связь проставлена сама


def test_new_master_blocks_detail_until_saved():
    patients, visits, photos = tree()
    MasterDetailLink(patients, visits)
    patients.open(); visits.open()
    patients.append({'name': 'Новый'})
    assert visits.row_count == 0 and not visits.can_modify
    with pytest.raises(DataSetError, match='нет главной записи'):
        visits.append()
    patients.post()
    assert visits.can_modify and visits.row_count == 0
    visits.append(); visits.post()
    assert visits.backend.get(visits.current_key)['patient_id'] == patients.current_key


def test_detail_edit_saved_when_master_moves():
    patients, visits, _ = tree()
    MasterDetailLink(patients, visits)
    patients.open(); visits.open()
    visits.edit(); visits.set_value('patient_id', 1)
    visits.backend.update(10, {'note': 'x'})
    patients.next()                                             # правка приёма сохранена до смены
    assert visits.state is State.BROWSE and keys(visits) == [20, 21]


def test_detail_opened_later_uses_master():
    patients, visits, _ = tree()
    MasterDetailLink(patients, visits)
    patients.open(); patients.next()
    visits.open()
    assert keys(visits) == [20, 21]


def test_link_fields_explicit_ambiguous_and_unlink():
    patients, visits, _ = tree()
    with pytest.raises(LinkError, match='имени'):
        MasterDetailLink(DataSet(MemoryBackend([])), visits)
    twice = DataSet(MemoryBackend([], fields=[FieldDef('id'), FieldDef('a', references='patients'),
                                              FieldDef('b', references='patients')]))
    with pytest.raises(LinkError, match='однозначно'):
        MasterDetailLink(patients, twice)
    link = MasterDetailLink(patients, visits, {'patient_id': 'id'})
    patients.open(); visits.open()
    assert keys(visits) == [10]
    link.unlink()
    assert keys(visits) == [10, 20, 21]
    patients.next()
    assert keys(visits) == [10, 20, 21]


def test_current_changed_never_reports_internal_index():
    """D1: «прежний номер» в событии — настоящий номер строки или -1, не служебный -2."""
    backend = people(4)
    ds = DataSet(backend, fetch_size=2)
    olds = []
    ds.subscribe(lambda e: olds.append(e.old) if e.kind is EventKind.CURRENT_CHANGED else None)
    ds.open(); ds.next()
    ds.refresh(); ds.set_filter(); ds.insert({'name': 'x'}); ds.cancel()
    ds.append({'name': 'y'}); ds.post(); ds.delete()
    backend.delete(1); ds.first(); ds.next(); ds.reload_row(0)
    assert olds and all(o >= -1 for o in olds)


def test_reload_row_removed_before_current_keeps_record():
    backend = people(3)
    ds = DataSet(backend)
    ds.open(); ds.move_to(2)
    backend.delete(1)
    assert not ds.reload_row(0)
    assert ds.current_key == 3 and ds.current_index == 1


def test_row_events_come_first():
    """
    D3: подписчик, считающий строки ТОЛЬКО по событиям о строках (как модель таблицы Qt),
    на любом другом событии видит то же число, что у набора.
    """
    ds = DataSet(people(3))
    ds.open()
    mirror = {'rows': ds.row_count, 'bad': []}

    def listener(event):
        if event.kind is EventKind.ROWS_INSERTED:
            mirror['rows'] += event.count
        elif event.kind is EventKind.ROWS_REMOVED:
            mirror['rows'] -= event.count
        elif event.kind is EventKind.REFRESHED:
            mirror['rows'] = ds.row_count
        elif mirror['rows'] != ds.row_count:
            mirror['bad'].append((event.kind, mirror['rows'], ds.row_count))

    ds.subscribe(listener)
    ds.append({'name': 'x'}); ds.cancel()
    ds.insert({'name': 'y'}); ds.cancel()
    ds.append({'name': 'z'}); ds.post()
    ds.delete(); ds.first(); ds.delete()
    ds.backend.delete(3); ds.reload_row(0)
    assert mirror['bad'] == []


def test_writer_gets_original_and_touch():
    seen = {}

    class Spy:
        def insert(self, ds, values): return dict(values, id=99)
        def update(self, ds, key, changes, row, original):
            seen.update(changes=changes, original=original, row=dict(row)); return dict(row)
        def delete(self, ds, key, row): pass
    ds = DataSet(people(2), writer=Spy())
    ds.open()
    ds.set_value('name', 'Новое'); ds.post()
    assert seen['original']['name'] == 'Имя1' and seen['changes'] == {'name': 'Новое'}
    changed = []
    ds.subscribe(lambda e: changed.append(e.index) if e.kind is EventKind.ROW_CHANGED else None)
    assert ds.touch([2]) == 1 and changed == [1]
    assert ds.touch() == 2


def test_master_refresh_refreshes_detail():
    """D4: «обновить» главный — подчинённый тоже перечитывается (главная строка та же)."""
    patients, visits, _ = tree()
    MasterDetailLink(patients, visits)
    patients.open(); visits.open()
    visits.backend.insert({'id': 11, 'patient_id': 1})            # появилось в хранилище
    patients.refresh()
    assert keys(visits) == [10, 11]


def test_deleted_row_not_editable_nor_deleted_twice():
    """D5: строка с пометкой удаления — не правится; повторное удаление — ничего."""
    writer = Deferred()
    ds = DataSet(people(2), writer=writer)
    ds.open(); ds.delete()
    assert ds.row_status() == 'deleted'
    with pytest.raises(DataSetError, match='помечена на удаление'):
        ds.edit()
    with pytest.raises(DataSetError):
        ds.set_value('name', 'x')
    ds.delete()
    assert writer.deleted == {1}


def test_refreshed_event_sees_consistent_current_row():
    """G1: в событии «перечитано» текущая строка уже верная (было: старый номер за концом)."""
    backend = people(4)
    ds = DataSet(backend)
    ds.open(); ds.last()
    seen = []
    ds.subscribe(lambda e: seen.append((ds.current_index, ds.row_count))
                 if e.kind is EventKind.REFRESHED else None)
    for key in (2, 3, 4):
        backend.delete(key)
    ds.refresh()
    ds.set_filter(Condition('id', Op.EQ, 99))
    assert all(index < rows for index, rows in seen) and seen[-1] == (-1, 0)


def test_link_survives_detail_shrinking_on_refresh():
    """G1: подчинённый — сам главный для следующего уровня; его строк стало меньше — связь не падает."""
    patients, visits, photos = tree()
    MasterDetailLink(patients, visits)
    MasterDetailLink(visits, photos)
    for ds in (patients, visits, photos):
        ds.open()
    patients.next(); visits.last()                               # приём 21
    errors = []
    import logging
    handler = logging.Handler()
    handler.emit = lambda record: errors.append(record)
    logging.getLogger('app.utils.dataset.events').addHandler(handler)
    try:
        visits.backend.delete(21); visits.backend.delete(20)
        patients.refresh()
    finally:
        logging.getLogger('app.utils.dataset.events').removeHandler(handler)
    assert errors == [] and visits.row_count == 0 and photos.row_count == 0


def test_state_consistent_on_every_event():
    """
    H1: на КАЖДОМ событии состояние согласовано — номер текущей строки в пределах строк,
    текущую строку можно прочитать, при вставке/правке есть строка. Цепочка из трёх
    связанных наборов, все операции.
    """
    patients, visits, photos = tree()
    MasterDetailLink(patients, visits)
    MasterDetailLink(visits, photos)
    problems = []

    def check(event):
        ds = event.dataset
        if ds is None or not ds.active:
            return
        if not (-1 <= ds.current_index < ds.row_count or (ds.row_count == 0 and ds.current_index == -1)):
            problems.append((ds.name, event.kind.value, ds.current_index, ds.row_count))
        if ds.current_index >= 0:
            try:
                ds.current, ds.value(ds.key_field)
            except Exception as exc:
                problems.append((ds.name, event.kind.value, repr(exc)))
        if ds.state.editing and ds.current is None:
            problems.append((ds.name, event.kind.value, 'правка без строки'))

    for ds in (patients, visits, photos):
        ds.subscribe(check)
        ds.open()
    patients.append({'name': 'Новый'}); patients.cancel()         # отмена последней строки главного
    patients.insert({'name': 'Перед'}); patients.cancel()
    patients.next(); visits.append(); visits.cancel()
    visits.last(); photos.append(); photos.post(); photos.delete()
    visits.backend.delete(21); visits.reload_row(visits.current_index)
    patients.first(); patients.append({'name': 'Ещё'}); patients.post()
    patients.delete(); patients.refresh(); patients.set_filter(Condition('id', Op.EQ, 1))
    patients.set_filter(); patients.last(); patients.close()
    assert problems == []


# --------------------------------------------------------------------------- свои поля (отметки)

def marked_people(n=4, **kw):
    backend = MemoryBackend([{'id': i, 'name': f'Имя{i}'} for i in range(1, n + 1)],
                            fields=[FieldDef('id'), FieldDef('name', required=True),
                                    FieldDef('mark', 'Отм.', FieldKind.BOOLEAN, local=True, default=False)])
    return DataSet(backend, **kw)


def test_local_field_set_without_edit_and_not_written():
    ds = marked_people()
    ds.open()
    events = recorder(ds)
    ds.set_local('mark', True, index=2)
    assert ds.state is State.BROWSE and ds.value('mark', 2) is True and ds.value('mark', 0) is False
    ds.set_value('mark', True)                                   # и через set_value — сразу
    assert ds.state is State.BROWSE and ds.local_keys('mark') == [1, 3]
    assert (EventKind.ROW_CHANGED,) in events
    ds.set_value('name', 'Новое'); ds.post()
    assert 'mark' not in ds.backend.get(1)                       # в хранилище не пишется


def test_local_field_survives_refresh_portions_and_filter():
    ds = marked_people(6, fetch_size=2)
    ds.open()
    ds.set_local('mark', True, index=1)                          # id 2
    ds.refresh()
    assert ds.value('mark', 1) is True
    ds.set_filter(Condition('id', Op.GE, 4))
    assert ds.local_keys('mark') == [2]                          # не загружена — но помнится
    ds.set_filter()
    assert ds.value('mark', 1) is True
    ds.clear_local('mark')
    assert ds.local_keys('mark') == [] and ds.value('mark', 1) is False
    ds.close(); ds.open()
    assert ds.local_keys('mark') == []                           # до закрытия набора


def test_local_field_on_new_row_and_rekey():
    ds = marked_people(writer=Deferred())
    ds.open()
    ds.append({'name': 'Новый'})
    assert ds.value('mark') is False
    ds.set_local('mark', True)
    ds.post()
    temp = ds.current_key
    assert ds.local_keys('mark') == [temp]
    ds.rekey(temp, 500)
    ds.rekey(404, 600)                                           # нечего переносить — ничего
    assert set(ds.local_keys('mark')) == {temp, 500}             # строка ещё с прежним ключом


def test_local_errors():
    ds = marked_people()
    ds.open()
    with pytest.raises(DataSetError, match='не своё'):
        ds.set_local('name', 'x')
    with pytest.raises(IndexError):
        ds.set_local('mark', True, index=99)


# --------------------------------------------------------------------------- итоги по подчинённым

def clinic_with_counts(photo_writer=None):
    """Приёмы с числом фото и суммой «чеков» (итоги считает программа) + набор фото."""
    from app.utils.dataset import AggFunc, AggregateDef
    photo_backend = MemoryBackend(
        [{'id': 100, 'appointment_id': 10, 'size': 5}, {'id': 101, 'appointment_id': 10, 'size': 7},
         {'id': 200, 'appointment_id': 20, 'size': None}],
        fields=[FieldDef('id'), FieldDef('appointment_id', references='appointments'), FieldDef('size')])
    photos = DataSet(photo_backend, name='photos', writer=photo_writer)
    visits = DataSet(MemoryBackend([{'id': 10}, {'id': 20}, {'id': 30}]), name='appointments', fields=[
        FieldDef('id'),
        FieldDef('photo_count', 'Фото', aggregate=AggregateDef(photos, 'appointment_id')),
        FieldDef('photo_size', aggregate=AggregateDef(photos, 'appointment_id', AggFunc.SUM, 'size')),
        FieldDef('big', aggregate=AggregateDef(photo_backend, 'appointment_id',
                                               where=(Condition('size', Op.GT, 6),))),
    ])
    return visits, photos, photo_backend


def test_aggregates_computed_in_batch_per_window():
    visits, photos, backend = clinic_with_counts()
    visits.open()
    before = backend.fetch_count
    assert [visits.value('photo_count', i) for i in range(3)] == [2, 1, 0]
    assert [visits.value('photo_size', i) for i in range(3)] == [12, None, None]   # None не участвует; нет строк — None
    assert [visits.value('big', i) for i in range(3)] == [1, 0, 0]
    assert backend.fetch_count == before                             # показ — из запомненного
    assert not visits.fields['photo_count'].editable and not visits.fields['photo_count'].stored


def test_aggregate_recalculated_through_link():
    visits, photos, backend = clinic_with_counts()
    MasterDetailLink(visits, photos)
    visits.open(); photos.open()
    photos.append({'size': 1})
    assert visits.value('photo_count') == 2                          # строка ещё не сохранена
    photos.post()
    assert visits.value('photo_count') == 3 and visits.value('photo_size') == 13
    photos.first(); photos.delete()
    assert visits.value('photo_count') == 2
    changed = []
    visits.subscribe(lambda e: changed.append(e.fields) if e.kind is EventKind.ROW_CHANGED else None)
    photos.set_value('size', 100)                                    # правка — без пересчёта
    assert changed == []
    photos.post()
    assert visits.value('photo_size') == 101 and changed


def test_aggregate_sees_unsaved_rows_of_custom_writer():
    """Подчинённый — набор с отложенной записью: новые строки считаются, помеченные на удаление — нет."""
    visits, photos, backend = clinic_with_counts(photo_writer=Deferred())
    MasterDetailLink(visits, photos)
    visits.open(); photos.open()
    photos.append({'size': 3}); photos.post()                         # временный id < 0
    assert visits.value('photo_count') == 3 and backend.get(-1) is None
    photos.first(); photos.delete()                                   # пометка, строка видна
    assert photos.row_status() == 'deleted' and visits.value('photo_count') == 2
    assert visits.value('big', 0) == 1                                # по источнику — только хранилище


def test_aggregate_touch_and_recalc_from_outside():
    visits, photos, backend = clinic_with_counts()
    visits.open()
    backend.insert({'appointment_id': 30, 'size': 2})                 # изменили извне
    assert visits.value('photo_count', 2) == 0                        # запомненное
    visits.touch([30])
    assert visits.value('photo_count', 2) == 1
    backend.insert({'appointment_id': 20, 'size': 2})
    assert visits.recalc() == 1 and visits.value('photo_count', 1) == 2


def test_aggregate_chunks_and_errors(monkeypatch):
    from app.utils.dataset import AggFunc, AggregateDef, aggregate as agg_module
    backend = MemoryBackend([{'id': i, 'parent': i % 7} for i in range(1, 50)])
    monkeypatch.setattr(agg_module, 'CHUNK', 3)
    counts = AggregateDef(backend, 'parent').compute(range(7))
    assert sum(counts.values()) == 49 and counts[0] == 7
    assert AggregateDef(backend, 'parent', AggFunc.MAX, 'id').compute([1])[1] == 43
    assert AggregateDef(backend, 'parent', AggFunc.AVG, 'id').compute([None]) == {None: None}
    with pytest.raises(ValueError, match='укажите поле'):
        AggregateDef(backend, 'parent', AggFunc.SUM)


# --------------------------------------------------------------------------- сортировка по вычисляемым

def test_sort_by_program_side_column_only_when_all_loaded():
    from app.utils.dataset import AggregateDef
    photos = MemoryBackend([{'id': 1, 'appointment_id': 30}, {'id': 2, 'appointment_id': 30},
                            {'id': 3, 'appointment_id': 10}])
    fields = [FieldDef('id'), FieldDef('date'),
              FieldDef('photo_count', 'Фото', aggregate=AggregateDef(photos, 'appointment_id')),
              FieldDef('mark', local=True, default=False)]
    rows = [{'id': 10, 'date': 3}, {'id': 20, 'date': 1}, {'id': 30, 'date': 2}]
    portions = DataSet(MemoryBackend(rows), fields=fields, fetch_size=2)
    portions.open()
    assert portions.sortable('date') and not portions.sortable('photo_count')
    with pytest.raises(DataSetError, match='загружено всё'):
        portions.set_order('-photo_count')
    portions.fetch_all()
    assert portions.sortable('photo_count')
    portions.set_order('-photo_count', 'date')                     # теперь можно — всё загружено
    assert keys(portions) == [30, 10, 20]
    everything = DataSet(MemoryBackend(rows), fields=fields, fetch_mode=FetchMode.ALL)
    everything.set_order('photo_count')                            # до открытия — тоже можно
    everything.open()
    assert keys(everything) == [20, 10, 30]
    assert everything.query.order == ()                            # источнику сортировка не уходит
    photos.insert({'appointment_id': 20}); photos.insert({'appointment_id': 20}); photos.insert({'appointment_id': 20})
    everything.refresh()
    assert keys(everything) == [10, 30, 20]                        # после перечитывания — снова верно
    everything.set_local('mark', True, index=2)
    everything.set_order('-mark', 'id')
    assert keys(everything)[0] == 20
    everything.set_order('date')                                   # снова по полю хранилища
    assert everything.query.order[0].field == 'date' and keys(everything) == [20, 30, 10]


def test_detail_mark_or_own_total_does_not_recalc_master():
    """V5: отметка/итог в подчинённом — у главного итог не пересчитывается (лишние запросы)."""
    from app.utils.dataset import AggregateDef
    visit_backend = MemoryBackend([{'id': 10, 'patient_id': 1}, {'id': 11, 'patient_id': 1}],
                                  fields=[FieldDef('id'), FieldDef('patient_id', references='patients')])
    visits = DataSet(visit_backend, name='appointments', fields=[
        FieldDef('id'), FieldDef('patient_id', references='patients'),
        FieldDef('mark', kind=FieldKind.BOOLEAN, local=True, default=False)])
    patients = DataSet(MemoryBackend([{'id': 1}]), name='patients', fields=[
        FieldDef('id'), FieldDef('visits', aggregate=AggregateDef(visits, 'patient_id'))])
    MasterDetailLink(patients, visits)
    patients.open(); visits.open()
    before = visit_backend.fetch_count
    visits.set_local('mark', True); visits.set_local('mark', True, index=1)
    assert visit_backend.fetch_count == before                    # ни одного запроса
    visits.append(); visits.post()
    assert patients.value('visits') == 3 and visit_backend.fetch_count == before + 1
