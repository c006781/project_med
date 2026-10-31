# tests/test_repositories/test_repositories_check.py

"""
Сверка репозиториев (2026-10-31): края фильтров, сортировки и связей.

Находки R1–R5 описаны в ``app/repositories/IMPLEMENTATION.md`` §3; каждый тест
падал на коде до исправления.
"""

from datetime import date

from sqlalchemy import event

from app.database.database_shema.clinic import Appointment, Patient
from app.repositories.repositories_all import AppointmentRepository, PatientRepository


def _capture(repo):
    """Подключает сбор строк журнала репозитория: (список строк, обработчик)."""
    got = []
    handler = repo.logger.add_output(
        got.append,                                         # куда складывать строки
        formatter   =   '%(levelname)s|%(plain_message)s',  # уровень и текст
    )
    return got, handler


def _patients(db_session, *last_names):
    """Добавляет пациентов с указанными фамилиями и возвращает их."""
    items = [Patient(first_name='И', last_name=name) for name in last_names]
    db_session.add_all(items)
    db_session.commit()
    return items


def _eq(column, value):
    """Лист фильтра «равно»."""
    return {'column': column, 'operator': 'eq', 'value': value}


# ---------------------------------------------------------------------------
# R1: фильтры-деревья ({'and'/'or': …}) — формат apply_filters
# ---------------------------------------------------------------------------

def test_r1_get_page_and_count_accept_filter_tree(db_session):
    _patients(db_session, 'Акулов', 'Белов', 'Волков')
    repo = PatientRepository(db_session)
    tree = {'or': [_eq('last_name', 'Акулов'), _eq('last_name', 'Волков')]}
    page = repo.get_page(0, 10, filters=tree, order_by=['last_name'])
    assert [p.last_name for p in page] == ['Акулов', 'Волков']
    assert repo.count(filters=tree) == 2


def test_r1_list_with_tree_node(db_session):
    _patients(db_session, 'Акулов', 'Белов', 'Волков')
    repo = PatientRepository(db_session)
    filters = [{'or': [_eq('last_name', 'Акулов'), _eq('last_name', 'Белов')]}]
    assert repo.count(filters=filters) == 2


def test_r1_by_patient_accepts_filter_tree(db_session, sample_patient):
    for day in (1, 2, 3):
        db_session.add(Appointment(patient_id=sample_patient.id, date=date(2026, 1, day)))
    db_session.commit()
    repo = AppointmentRepository(db_session)
    tree = {'or': [_eq('date', date(2026, 1, 1)), _eq('date', date(2026, 1, 3))]}
    page = repo.get_page_by_patient(sample_patient.id, 0, 10, filters=tree, order_by=['date'])
    assert [a.date.day for a in page] == [1, 3]
    assert repo.count_by_patient(sample_patient.id, filters=tree) == 2


def test_r1_flat_list_still_works(db_session):
    _patients(db_session, 'Акулов', 'Белов')
    repo = PatientRepository(db_session)
    assert repo.count(filters=[_eq('last_name', 'Белов')]) == 1
    assert repo.count(filters=[]) == 2
    assert repo.count(filters=None) == 2


# ---------------------------------------------------------------------------
# R2: нечёткий отбор ('fuzzy') репозиторий не делает — теперь об этом пишет журнал
# ---------------------------------------------------------------------------

def test_r2_fuzzy_ignored_with_warning(db_session):
    _patients(db_session, 'Акулов', 'Белов')
    repo = PatientRepository(db_session)
    fuzzy = [{'column': 'last_name', 'operator': 'fuzzy', 'value': 'Акулв'}]
    got, handler = _capture(repo)
    try:
        assert len(repo.get_page(0, 10, filters=fuzzy)) == 2
        assert repo.count(filters=fuzzy) == 2
    finally:
        repo.logger.remove_output(handler)
    warned = [line for line in got if line.startswith('WARNING|') and 'fuzzy' in line]
    assert len(warned) == 2


def test_r2_no_warning_without_fuzzy(db_session):
    _patients(db_session, 'Акулов')
    repo = PatientRepository(db_session)
    got, handler = _capture(repo)
    try:
        repo.get_page(0, 10, filters=[_eq('last_name', 'Акулов')])
    finally:
        repo.logger.remove_output(handler)
    assert not [line for line in got if line.startswith('WARNING|')]


# ---------------------------------------------------------------------------
# R3: страницы — устойчивый порядок (ORDER BY с id последним ключом)
# ---------------------------------------------------------------------------

def _select_sql(db_session, call):
    """Выполняет ``call()`` и возвращает тексты выполненных SELECT."""
    engine = db_session.get_bind().engine
    seen = []

    def _remember(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(engine, 'before_cursor_execute', _remember)
    try:
        call()
    finally:
        event.remove(engine, 'before_cursor_execute', _remember)
    return [s for s in seen if s.lstrip().upper().startswith('SELECT')]


def test_r3_page_without_order_sorted_by_id(db_session):
    _patients(db_session, 'Акулов', 'Белов', 'Волков')
    repo = PatientRepository(db_session)
    sql = _select_sql(db_session, lambda: repo.get_page(0, 2))
    assert sql and 'ORDER BY' in sql[-1].upper()
    first = repo.get_page(0, 2)
    second = repo.get_page(2, 2)
    ids = [p.id for p in first + second]
    assert ids == sorted(ids) and len(set(ids)) == 3


def test_r3_ties_broken_by_id(db_session, sample_patient):
    # Одинаковые даты: без второго ключа страницы могли повторять / терять записи
    for _ in range(4):
        db_session.add(Appointment(patient_id=sample_patient.id, date=date(2026, 1, 1)))
    db_session.commit()
    repo = AppointmentRepository(db_session)
    sql = _select_sql(db_session, lambda: repo.get_page(0, 2, order_by=['-date']))
    order_part = sql[-1].upper().split('ORDER BY', 1)[1]
    assert 'DATE DESC' in order_part and '.ID' in order_part
    pages = repo.get_page(0, 2, order_by=['-date']) + repo.get_page(2, 2, order_by=['-date'])
    ids = [a.id for a in pages]
    assert ids == sorted(ids) and len(set(ids)) == 4


# ---------------------------------------------------------------------------
# R4: get_with_relations без списка связей
# ---------------------------------------------------------------------------

def test_r4_with_relations_none(db_session, sample_patient):
    repo = PatientRepository(db_session)
    assert repo.get_with_relations(sample_patient.id, None).id == sample_patient.id
    assert repo.get_with_relations(sample_patient.id, []).id == sample_patient.id
    assert repo.get_with_relations(-1, None) is None


# ---------------------------------------------------------------------------
# R5: уникальные значения — по возрастанию
# ---------------------------------------------------------------------------

def test_r5_unique_values_sorted(db_session):
    _patients(db_session, 'Волков', 'Акулов', 'Волков', 'Белов')
    repo = PatientRepository(db_session)
    # SQLite сейчас и без ORDER BY отдаёт DISTINCT по возрастанию, но это не гарантировано
    sql = _select_sql(db_session, lambda: repo.get_unique_values('last_name'))
    assert 'ORDER BY' in sql[-1].upper()
    assert repo.get_unique_values('last_name') == ['Акулов', 'Белов', 'Волков']
