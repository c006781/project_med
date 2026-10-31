# tests/test_services/test_services_check.py

"""
Сверка сервисов (М11, 2026-10-31): находки описаны в ``app/services/IMPLEMENTATION.md`` §3.4;
каждый тест на находку падал на коде до исправления.
"""

from datetime import date

from sqlalchemy import event

from app.database.database_shema.clinic import Appointment, Patient


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


def _page_sql(db_session, call):
    """Текст SELECT страницы: последний запрос с ``LIMIT`` (счёт — отдельный ``count``)."""
    sql = [s for s in _select_sql(db_session, call) if 'LIMIT' in s.upper()]
    assert sql, 'запрос страницы не найден'
    return sql[-1].upper()


# ---------------------------------------------------------------------------
# S1 (ОСТ п. 1.11): страницы — id последним ключом сортировки (как R3 в репозиториях)
# ---------------------------------------------------------------------------

def test_s1_page_without_order_sorted_by_id(patient_service, db_session):
    db_session.add_all([Patient(first_name='И', last_name=n) for n in ('Акулов', 'Белов', 'Волков')])
    db_session.commit()
    sql = _page_sql(db_session, lambda: patient_service.get_page(0, 2))
    assert 'ORDER BY' in sql and 'PATIENTS.ID' in sql.split('ORDER BY', 1)[1]
    first, total = patient_service.get_page(0, 2)
    second, _ = patient_service.get_page(2, 2)
    ids = [p.id for p in first + second]
    assert total == 3 and ids == sorted(ids) and len(set(ids)) == 3


def test_s1_ties_broken_by_id(patient_service, appointment_service, db_session):
    patient = Patient(first_name='И', last_name='Акулов')
    db_session.add(patient)
    db_session.commit()
    # Одинаковые даты: без второго ключа страницы могли повторять / терять записи
    for _ in range(4):
        db_session.add(Appointment(patient_id=patient.id, date=date(2026, 1, 1)))
    db_session.commit()
    sql = _page_sql(
        db_session,
        lambda: appointment_service.get_page_filtered(0, 2, order_by=['-date']),
    )
    order_part = sql.split('ORDER BY', 1)[1]
    assert 'DATE DESC' in order_part and 'APPOINTMENTS.ID' in order_part
    assert order_part.index('DATE DESC') < order_part.index('APPOINTMENTS.ID')
    first, _ = appointment_service.get_page_filtered(0, 2, order_by=['-date'])
    second, _ = appointment_service.get_page_filtered(2, 2, order_by=['-date'])
    ids = [a.id for a in first + second]
    assert len(ids) == 4 and len(set(ids)) == 4


def test_s1_unknown_order_field_still_sorted_by_id(patient_service, db_session):
    # Неизвестное поле пропускается (предупреждение), но порядок страниц остаётся заданным
    db_session.add(Patient(first_name='И', last_name='Акулов'))
    db_session.commit()
    sql = _page_sql(db_session, lambda: patient_service.get_page(0, 2, order_by=['нет_поля']))
    assert 'PATIENTS.ID' in sql.split('ORDER BY', 1)[1]


# ---------------------------------------------------------------------------
# Ф1.6.10б (ОСТ п. 1.6): текст ошибки — «Ошибка проверки файла»
# ---------------------------------------------------------------------------

def test_f16_10b_missing_photo_file_message(photo_service, sample_appointment, tmp_path):
    from app.exceptions import PhotoFileError

    missing = str(tmp_path / 'нет.jpg')
    try:
        photo_service.add_photo_to_appointment(sample_appointment.id, missing)
    except PhotoFileError as exc:
        assert 'Ошибка проверки файла' in str(exc)
    else:
        raise AssertionError('ожидалась PhotoFileError')


def test_f16_10b_missing_appointment(photo_service, tmp_path):
    from app.exceptions import AppointmentNotFoundError

    source = tmp_path / 'a.jpg'
    source.write_bytes(b'x')
    try:
        photo_service.add_photo_to_appointment(999999, str(source))
    except AppointmentNotFoundError:
        pass
    else:
        raise AssertionError('ожидалась AppointmentNotFoundError')


# ---------------------------------------------------------------------------
# Ф1.6.10в (ОСТ п. 1.8): один SyncService на приложение — настройки доходят до окна
# ---------------------------------------------------------------------------

def test_f16_10v_sync_service_cached_and_applier_reaches_it():
    import app.dependencies as deps

    deps.get_sync_service.cache_clear()
    try:
        used_by_window = deps.get_sync_service()          # как MainWindow.sync_service
        assert deps.get_sync_service() is used_by_window
        applier = deps.create_config_applier()
        assert applier.apply_sync(
            {'YANDEX_TOKEN': 'новый-токен'},    # после сохранения
            {'YANDEX_TOKEN': 'старый-токен'},   # до сохранения
        )
        assert used_by_window.token == 'новый-токен'
    finally:
        deps.get_sync_service.cache_clear()
