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



# ---------------------------------------------------------------------------
# S4: страница приёмов пациента принимает дерево фильтров ({'and'/'or': …})
# ---------------------------------------------------------------------------

def test_s4_patient_page_accepts_filter_tree(appointment_service, db_session):
    patient = Patient(first_name='И', last_name='Акулов')
    other = Patient(first_name='И', last_name='Белов')
    db_session.add_all([patient, other])
    db_session.commit()
    db_session.add_all([
        Appointment(patient_id=patient.id, date=date(2026, 1, 1)),
        Appointment(patient_id=patient.id, date=date(2026, 2, 1)),
        Appointment(patient_id=patient.id, date=date(2026, 3, 1)),
        Appointment(patient_id=other.id, date=date(2026, 1, 1)),   # чужой — не попадает
    ])
    db_session.commit()
    tree = {'or': [
        {'column': 'date', 'operator': 'eq', 'value': date(2026, 1, 1)},
        {'column': 'date', 'operator': 'eq', 'value': date(2026, 3, 1)},
    ]}
    page, total = appointment_service.get_appointments_by_patient_page(
        patient.id,             # пациент
        0,                      # первая страница
        10,                     # размер
        filters   =   tree,     # дерево
        order_by  =   ['date'], # по дате
    )
    assert total == 2
    assert [a.date for a in page] == [date(2026, 1, 1), date(2026, 3, 1)]
    assert {a.patient_id for a in page} == {patient.id}


def test_s4_patient_page_flat_list_still_works(appointment_service, db_session):
    patient = Patient(first_name='И', last_name='Акулов')
    db_session.add(patient)
    db_session.commit()
    db_session.add_all([
        Appointment(patient_id=patient.id, date=date(2026, 1, 1)),
        Appointment(patient_id=patient.id, date=date(2026, 2, 1)),
    ])
    db_session.commit()
    flat = [{'column': 'date', 'operator': 'ge', 'value': date(2026, 2, 1)}]
    page, total = appointment_service.get_appointments_by_patient_page(patient.id, 0, 10, filters=flat)
    assert total == 1 and page[0].date == date(2026, 2, 1)


# ---------------------------------------------------------------------------
# S5: личные данные (ФИО, телефон, поиск, тексты заметок) не попадают в журнал
# ---------------------------------------------------------------------------

def _log_lines(service, call):
    """Выполняет ``call()`` при уровне DEBUG и возвращает строки журнала сервиса."""
    import logging
    inner = service.logger.logger
    old_level = inner.level
    inner.setLevel(logging.DEBUG)
    got = []
    handler = service.logger.add_output(
        got.append,                                         # куда складывать строки
        formatter   =   '%(levelname)s|%(plain_message)s',  # уровень и текст
    )
    try:
        call()
    finally:
        service.logger.remove_output(handler)
        inner.setLevel(old_level)
    return got


SECRETS = ('Тайнова', 'Секретина', '+79990001122', 'Секретная жалоба')


def _leaks(lines):
    """Строки журнала, в которых есть личные данные из ``SECRETS``."""
    return [line for line in lines if any(secret in line for secret in SECRETS)]


def test_s5_patient_create_update_filter_not_logged(patient_service):
    from app.dto import PatientDTO

    def scenario():
        created = patient_service.create_patient(
            PatientDTO(
                first_name         =   'Секретина',          # имя
                last_name          =   'Тайнова',            # фамилия
                birth_date         =   date(1980, 5, 17),    # дата рождения (обязательна)
                phone              =   '+79990001122',       # телефон
                description_text   =   'Секретная жалоба',   # заметка
            ),
        )
        created.last_name = 'Тайнова-Иванова'
        patient_service.update_patient(created)
        patient_service.get_patients_filtered(
            [{'column': 'last_name', 'operator': 'like', 'value': 'Тайнова'}],   # поиск
        )
        patient_service.get_by_id(created.id)

    got = _log_lines(patient_service, scenario)
    assert any(line.startswith('DEBUG|') for line in got)
    assert not _leaks(got)


def test_s5_note_text_not_logged(patient_service):
    note_service = patient_service._get_note_service()
    got = _log_lines(note_service, lambda: note_service.get_or_create_note('Секретная жалоба'))
    assert any('заметки' in line for line in got)
    assert not _leaks(got)


def test_s5_filters_outline_without_values():
    from app.services.services_all import _filters_outline

    outline = _filters_outline(
        [{'column': 'last_name', 'operator': 'like', 'value': 'Тайнова'},
         {'or': [{'column': 'date', 'operator': 'is_null'},
                 {'column': 'phone', 'operator': 'eq', 'value': '+79990001122'}]}],
    )
    assert outline == 'last_name like, or(date is_null, phone eq)'
    assert _filters_outline(None) == '—'


# ---------------------------------------------------------------------------
# S7: «не найдено» у фото — запись ERROR без ложной трассировки (exception вне except)
# ---------------------------------------------------------------------------

def test_s7_photo_not_found_logged_without_traceback(photo_service):
    import logging
    from app.exceptions import PhotoNotFoundError

    records = []

    class _Keep(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Keep(level=logging.ERROR)
    inner = photo_service.logger.logger
    inner.addHandler(handler)
    try:
        try:
            photo_service.get_by_id(999999)
        except PhotoNotFoundError:
            pass
        else:
            raise AssertionError('ожидалась PhotoNotFoundError')
    finally:
        inner.removeHandler(handler)
    errors = [r for r in records if r.levelno == logging.ERROR]
    assert errors and not any(r.exc_info for r in errors)


# ---------------------------------------------------------------------------
# S8: «нет id» при обновлении — исключение таблицы с полем (и по-прежнему ValueError)
# ---------------------------------------------------------------------------

def test_s8_update_without_id_raises_entity_validation(photo_service, appointment_service):
    from app.dto import AppointmentDTO, AppointmentNoteDTO, PhotoDTO
    from app.exceptions import (
        AppointmentNoteValidationError, AppointmentValidationError, PhotoValidationError,
    )

    note_service = appointment_service._get_note_service()
    cases = [
        (lambda: note_service.update(AppointmentNoteDTO(text='x')), AppointmentNoteValidationError),
        (lambda: appointment_service.update(AppointmentDTO(patient_id=1, date=date(2026, 1, 1))),
         AppointmentValidationError),
        (lambda: photo_service.update(PhotoDTO(appointment_id=1, file_path='a.jpg')), PhotoValidationError),
    ]
    for call, expected in cases:
        try:
            call()
        except expected as exc:
            assert isinstance(exc, ValueError)
            assert 'id' in str(exc)
        else:
            raise AssertionError(f'ожидалась {expected.__name__}')


def test_s8_photo_create_without_appointment(photo_service, tmp_path):
    from app.dto import PhotoDTO
    from app.exceptions import PhotoValidationError

    source = tmp_path / 'a.jpg'
    source.write_bytes(b'x')
    dto = PhotoDTO(appointment_id=0, file_path=str(source))
    try:
        photo_service.create(dto)
    except PhotoValidationError as exc:
        assert isinstance(exc, ValueError) and 'приём' in str(exc)
    else:
        raise AssertionError('ожидалась PhotoValidationError')


# ---------------------------------------------------------------------------
# S9: sql_compute — MAX / MIN считаются; неизвестная функция и столбец фильтра — предупреждение
# ---------------------------------------------------------------------------

def _appointment_with_photos(db_session, photos):
    """Пациент, два приёма; у первого — фото с указанными описаниями. Возвращает приёмы."""
    from app.database.database_shema.clinic import Photo

    patient = Patient(first_name='И', last_name='Акулов')
    db_session.add(patient)
    db_session.commit()
    first = Appointment(patient_id=patient.id, date=date(2026, 1, 1))
    second = Appointment(patient_id=patient.id, date=date(2026, 1, 2))
    db_session.add_all([first, second])
    db_session.commit()
    db_session.add_all([Photo(appointment_id=first.id, file_path=f'p{i}.jpg', description=d)
                        for i, d in enumerate(photos)])
    db_session.commit()
    return first, second


def test_s9_sql_compute_max_and_min(appointment_service, db_session):
    from app.database.database_shema.clinic import Photo

    first, second = _appointment_with_photos(db_session, ['а', 'б', 'в'])
    photo_ids = [p.id for p in db_session.query(Photo).filter(Photo.appointment_id == first.id)]
    for func_name, expected in (('MAX', max(photo_ids)), ('MIN', min(photo_ids))):
        sub = appointment_service._build_sql_compute_subquery(
            'x',                                                        # поле
            {'relation': 'photos', 'func': func_name, 'column': 'id'},  # описание
        )
        assert sub is not None
        rows = dict(db_session.query(Appointment.id, sub.label('x')).all())
        assert rows[first.id] == expected and rows[second.id] is None


def test_s9_sql_compute_unknown_function_and_filter_column(appointment_service, db_session):
    first, _ = _appointment_with_photos(db_session, ['а', 'б'])
    got = _log_lines(
        appointment_service,
        lambda: appointment_service._build_sql_compute_subquery(
            'x', {'relation': 'photos', 'func': 'MEDIAN', 'column': 'id'},
        ),
    )
    assert appointment_service._build_sql_compute_subquery(
        'x', {'relation': 'photos', 'func': 'MEDIAN', 'column': 'id'},
    ) is None
    assert any(line.startswith('WARNING|') and 'MEDIAN' in line for line in got)

    sub = None

    def build():
        nonlocal sub
        sub = appointment_service._build_sql_compute_subquery(
            'x', {'relation': 'photos', 'func': 'COUNT', 'filter': {'нет_столбца': 1}},
        )

    got = _log_lines(appointment_service, build)
    assert any(line.startswith('WARNING|') and 'нет_столбца' in line for line in got)
    rows = dict(db_session.query(Appointment.id, sub.label('x')).all())
    assert rows[first.id] == 2
