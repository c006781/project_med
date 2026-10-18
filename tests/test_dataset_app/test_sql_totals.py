# tests/test_dataset_app/test_sql_totals.py

"""
Итоги, которые считает БД отдельным запросом (``SqlTotals``): один ``GROUP BY`` на окно
для всех столбцов, запрос таблицы данных без подзапросов, поправка на черновики.
"""


import pytest
from sqlalchemy import event

from app.database.database_shema.clinic import Photo
from app.dataset_app import SqlTotals, create_clinic_datasets
from app.dto.dto_all import PhotoDTO
from app.tables import CLINIC, TableRegistry, TableSpec, total
from app.utils.dataset import AggFunc


@pytest.fixture
def sql_log(services):
    """Текст всех SQL-запросов к временной БД."""
    statements = []
    engine = services['db'].engine

    def listener(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', listener)
    yield statements
    event.remove(engine, 'before_cursor_execute', listener)


def photo(services, appointment_id, tmp_path, name='a.png'):
    path = tmp_path / name
    path.write_bytes(b'x')
    return services['photo'].create(PhotoDTO(appointment_id=appointment_id, file_path=str(path)))


def test_one_group_by_per_window_and_plain_data_query(services, providers, filled, sql_log, tmp_path):
    appointment = services['appointment'].get_all()[0]
    photo(services, appointment.id, tmp_path)
    base = [CLINIC.get(n) for n in CLINIC.names()]
    appointments = TableSpec(**{**base[1].__dict__, 'extras': base[1].extras + (
        total('last_photo', 'Последнее фото', 'photos', AggFunc.MAX, 'id', by='sql'),)})
    built = TableRegistry([base[0], appointments, base[2]]).build(services=providers)
    built.patients.open()
    sql_log.clear()
    built.appointments.open()
    grouped = [s for s in sql_log if 'GROUP BY' in s and 'photos' in s]
    assert len(grouped) == 1                                       # два столбца — один запрос
    visits = built.appointments
    row = next(i for i in range(visits.row_count) if visits.key_at(i) == appointment.id)
    assert visits.value('photo_count', row) == 1 and visits.value('last_photo', row) is not None
    data_queries = [s for s in sql_log if s.lstrip().upper().startswith('SELECT') and 'FROM appointments' in s
                    and 'GROUP BY' not in s]
    assert data_queries and not any('photos' in s for s in data_queries)   # без подзапроса has_photos


def test_counts_follow_drafts_with_delta(services, providers, filled, app_drafts, tmp_path):
    clinic = create_clinic_datasets(services=providers, drafts=app_drafts)
    clinic.open()
    patients, visits, photos = clinic.patients, clinic.appointments, clinic.photos
    assert [patients.value('visits', i) for i in range(patients.row_count)] == [2, 1]
    image = tmp_path / 'n.png'; image.write_bytes(b'x')
    photos.append({'file_path': str(image)}); photos.post()
    assert visits.value('photo_count') == 1                        # черновик — в числе из БД
    photos.delete()                                                # новая — просто исчезла
    assert visits.value('photo_count') == 0
    visits.delete()                                                # приём Иванова — на удаление
    assert patients.value('visits') == 1
    app_drafts.store.undo()
    assert patients.value('visits') == 2
    moved = visits.current_key
    row = visits.row()
    clinic.writers['appointments'].update(visits, moved, {'patient_id': filled['petrov']},
                                          dict(row, patient_id=filled['petrov']), row)
    patients.recalc()
    assert [patients.value('visits', i) for i in range(patients.row_count)] == [1, 2]   # перенос
    clinic.save()
    patients.recalc()
    assert [patients.value('visits', i) for i in range(patients.row_count)] == [1, 2]   # после сохранения


def test_ignore_mode_shows_only_database(services, providers, filled, app_drafts, tmp_path):
    base = [CLINIC.get(n) for n in CLINIC.names()]
    appointments = TableSpec(**{**base[1].__dict__, 'extras': (
        total('photo_count', 'Фото', 'photos', by='sql', unsaved='ignore'),)})
    built = TableRegistry([base[0], appointments, base[2]]).build(services=providers, drafts=app_drafts)
    built.open()
    image = tmp_path / 'i.png'; image.write_bytes(b'x')
    built.photos.append({'file_path': str(image)}); built.photos.post()
    assert built.appointments.value('photo_count') == 0            # только БД
    built.save()
    built.appointments.recalc()
    assert built.appointments.value('photo_count') == 1


def test_keys_chunked_and_validation(services, filled, sql_log):
    totals = SqlTotals(lambda: services['db'].engine, Photo.__table__, 'appointment_id',
                       {'n': ('count', None)})
    result = totals.compute_many(range(1, 1201))
    assert len(result) == 1200 and all(v == {'n': 0} for v in result.values())
    assert len([s for s in sql_log if 'GROUP BY' in s]) == 3        # по 500 ключей
    with pytest.raises(ValueError, match='допустимо'):
        SqlTotals(lambda: None, Photo.__table__, 'appointment_id', {'x': ('median', 'id')})
    with pytest.raises(ValueError, match='укажите поле'):
        SqlTotals(lambda: None, Photo.__table__, 'appointment_id', {'x': ('sum', None)})
    with pytest.raises(ValueError, match='by='):
        total('x', 'X', 'photos', by='cloud')
    with pytest.raises(ValueError, match='sql_where'):
        total('x', 'X', 'photos', lambda rows: 1, by='sql')
