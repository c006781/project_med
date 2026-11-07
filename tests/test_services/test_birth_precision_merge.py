# tests/test_services/test_birth_precision_merge.py

"""
Дата рождения с точностью в сервисах: запись, поиск дублей, объединение с выбором (Ф1.6.10е).

На настоящей SQLite (как test_patient_merge.py).
"""

import datetime

import pytest

from app.database.database import Database
from app.dto.dto_all import AppointmentDTO, PatientDTO
from app.dto.field_configs import APPOINTMENT_CONFIG, NOTE_CONFIG, PATIENT_CONFIG, PHOTO_CONFIG
from app.exceptions.exceptions_all import PatientValidationError
from app.services.patient_merge import (
    MergePlanChangedError,
    MergeRules,
    PatientMergeService,
    normalize_merge_choices,
)
from app.services.services_all import AppointmentService, NoteService, PatientService, PhotoService
from app.utils.record_keys import MATCH_FULL, MATCH_PARTIAL, format_birth_date

EXACT = datetime.date(1985, 6, 14)
YEAR = datetime.date(1985, 1, 1)


@pytest.fixture
def svc(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'clinic.db'}")
    storage = tmp_path / 'photos'
    storage.mkdir()
    note = NoteService(db, field_configs=NOTE_CONFIG)
    photo = PhotoService(db, str(storage), field_configs=PHOTO_CONFIG)
    appointment = AppointmentService(db, note_service=note, photo_service=photo,
                                     field_configs=APPOINTMENT_CONFIG)
    patient = PatientService(db, field_configs=PATIENT_CONFIG, appointment_service=appointment)
    yield {
        'db': db,
        'patient': patient,
        'appointment': appointment,
        'merge': PatientMergeService(db, patient, appointment),
    }
    db.close()


def _patient(svc, middle='Петровна', birth=EXACT, precision=None, last='Иванова', first='Мария', **fields):
    return svc['patient'].create(
        PatientDTO(
            last_name=last,
            first_name=first,
            middle_name=middle,
            birth_date=birth,
            birth_date_precision=precision,
            **fields,
        ),
    )


# --- запись ----------------------------------------------------------------

def test_create_full_precision_by_default(svc):
    patient = _patient(svc)
    assert patient.birth_date_precision == 'day'
    assert svc['patient'].get_by_id(patient.id).birth_date_precision == 'day'


def test_create_without_date_has_no_precision(svc):
    assert _patient(svc, birth=None, precision='year').birth_date_precision is None


def test_create_year_only_and_read_back(svc):
    patient = _patient(svc, birth=YEAR, precision='year')
    stored = svc['patient'].get_by_id(patient.id)
    assert (stored.birth_date, stored.birth_date_precision) == (YEAR, 'year')
    assert format_birth_date(stored.birth_date, stored.birth_date_precision) == '1985'


def test_create_unknown_precision_refused(svc):
    with pytest.raises(PatientValidationError, match='точность'):
        _patient(svc, precision='decade')


def test_form_without_precision_keeps_it_on_save(svc):
    """Форма, не знающая о точности, присылает DTO без неё: «только год» не становится полной датой."""
    patient = _patient(svc, birth=YEAR, precision='year')
    form = PatientDTO(id=patient.id, last_name='Иванова', first_name='Анна', birth_date=YEAR)
    assert svc['patient'].update(form).birth_date_precision == 'year'


def test_date_entered_more_exactly_becomes_full(svc):
    """Старая форма меняет только дату: точная дата при «только год» — полная, дата не обрезается."""
    patient = _patient(svc, birth=YEAR, precision='year')
    updated = svc['patient'].update(patient.model_copy(update={'birth_date': EXACT}))
    assert (updated.birth_date, updated.birth_date_precision) == (EXACT, 'day')


def test_clear_date_clears_precision(svc):
    patient = _patient(svc, birth=YEAR, precision='year')
    updated = svc['patient'].update(patient.model_copy(update={'birth_date': None}))
    stored = svc['patient'].get_by_id(patient.id)
    assert updated.birth_date_precision is None and stored.birth_date is None
    assert stored.birth_date_precision is None


def test_update_missing_patient_still_not_found(svc):
    from app.exceptions.exceptions_all import PatientNotFoundError
    with pytest.raises(PatientNotFoundError):
        svc['patient'].update(PatientDTO(id=999, last_name='Н', first_name='Н'))


# --- поиск дублей ----------------------------------------------------------

def test_year_matches_exact_date_of_same_year(svc):
    a = _patient(svc, birth=YEAR, precision='year')
    b = _patient(svc)
    _patient(svc, birth=datetime.date(1986, 1, 1), precision='year')   # другой год
    [pair] = svc['merge'].find_duplicate_pairs()
    assert (pair.first.id, pair.second.id) == (a.id, b.id)
    assert pair.match.label == MATCH_FULL and pair.match.date_precision == 'year'


def test_first_of_january_exact_is_not_year(svc):
    _patient(svc, birth=YEAR)                  # настоящее 1 января
    _patient(svc)
    assert svc['merge'].find_duplicate_pairs() == []


def test_owner_example_incomplete_match_is_found(svc):
    a = _patient(svc, middle='Петровна', birth=None)
    b = _patient(svc, middle=None)
    [pair] = svc['merge'].find_duplicate_pairs()
    assert pair.match.label == MATCH_PARTIAL
    assert pair.match.describe() == 'неполное: пусто отчество, дата рождения'
    assert [[p.id for p in g] for g in svc['merge'].find_possible_duplicates()] == [[a.id, b.id]]


def test_filled_and_different_not_found(svc):
    _patient(svc, middle='Петровна')
    _patient(svc, middle='Ивановна')
    _patient(svc, last='Петрова')
    _patient(svc, first='Анна')
    assert svc['merge'].find_duplicate_pairs() == []
    assert svc['merge'].find_possible_duplicates() == []


def test_chain_group_contains_all_but_pairs_show_real_matches(svc):
    """Сравнение не транзитивно: год связывает две разные точные даты в группу, пары — честные."""
    year = _patient(svc, birth=YEAR, precision='year')
    first = _patient(svc, birth=EXACT)
    second = _patient(svc, birth=datetime.date(1985, 6, 15))
    pairs = {(p.first.id, p.second.id) for p in svc['merge'].find_duplicate_pairs()}
    assert pairs == {(year.id, first.id), (year.id, second.id)}
    assert [[p.id for p in g] for g in svc['merge'].find_possible_duplicates()] == [[year.id, first.id, second.id]]


def test_find_does_not_merge(svc):
    _patient(svc)
    _patient(svc)
    svc['merge'].find_duplicate_pairs()
    svc['merge'].find_possible_duplicates()
    assert len(svc['patient'].get_all()) == 2


def test_two_groups_sorted(svc):
    b = [_patient(svc, last='Яковлева'), _patient(svc, last='Яковлева')]
    a = [_patient(svc), _patient(svc)]
    groups = [[p.id for p in g] for g in svc['merge'].find_possible_duplicates()]
    assert groups == [[p.id for p in a], [p.id for p in b]]


# --- объединение: правила --------------------------------------------------

def test_merge_takes_exact_date_from_duplicate(svc):
    main = _patient(svc, birth=YEAR, precision='year')
    dup = _patient(svc)
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert [(c.field, c.value) for c in plan.changes] == [('birth_date', EXACT), ('birth_date_precision', 'day')]
    assert plan.matches[0][0] == dup.id and plan.matches[0][1].label == MATCH_FULL
    assert plan.warnings == ()
    svc['merge'].merge_patients(main.id, [dup.id], expected=plan, backup=False)
    stored = svc['patient'].get_by_id(main.id)
    assert (stored.birth_date, stored.birth_date_precision) == (EXACT, 'day')


def test_merge_exact_main_keeps_date_year_duplicate_no_warning(svc):
    main = _patient(svc)
    dup = _patient(svc, birth=YEAR, precision='year')
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert plan.changes == () and plan.warnings == ()


def test_merge_only_precision_changes_when_dates_equal(svc):
    main = _patient(svc, birth=YEAR, precision='year')
    dup = _patient(svc, birth=YEAR)            # настоящее 1 января
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert [(c.field, c.value) for c in plan.changes] == [('birth_date_precision', 'day')]
    svc['merge'].merge_patients(main.id, [dup.id], expected=plan, backup=False)
    assert svc['patient'].get_by_id(main.id).birth_date_precision == 'day'


def test_merge_month_between_year_and_day(svc):
    main = _patient(svc, birth=YEAR, precision='year')
    month = _patient(svc, birth=datetime.date(1985, 6, 1), precision='month')
    day = _patient(svc)
    plan = svc['merge'].plan_merge(main.id, [month.id, day.id])
    assert {c.field: c.value for c in plan.changes} == {'birth_date': EXACT, 'birth_date_precision': 'day'}
    assert plan.warnings == ()


def test_merge_other_year_warns_and_keeps_main(svc):
    main = _patient(svc, birth=YEAR, precision='year')
    dup = _patient(svc, birth=datetime.date(1986, 6, 14))
    plan = svc['merge'].plan_merge(main.id, [dup.id])
    assert plan.changes == ()
    assert any('«1985»' in w and '«14.06.1986»' in w for w in plan.warnings)
    assert any('не совпадают с главным' in w for w in plan.warnings)


def test_merge_two_exact_dates_first_taken_second_warned(svc):
    main = _patient(svc, birth=YEAR, precision='year')
    first = _patient(svc)
    second = _patient(svc, birth=datetime.date(1985, 6, 15))
    plan = svc['merge'].plan_merge(main.id, [first.id, second.id])
    assert {c.field: c.value for c in plan.changes} == {'birth_date': EXACT, 'birth_date_precision': 'day'}
    assert any('«14.06.1985»' in w and '«15.06.1985»' in w for w in plan.warnings)


def test_owner_example_after_merge_full_name_and_date(svc):
    main = _patient(svc, middle='Петровна', birth=None)
    dup = _patient(svc, middle=None)
    svc['merge'].merge_patients(main.id, [dup.id], backup=False)
    stored = svc['patient'].get_by_id(main.id)
    assert (stored.middle_name, stored.birth_date, stored.birth_date_precision) == ('Петровна', EXACT, 'day')
    assert [p.id for p in svc['patient'].get_all()] == [main.id]


# --- объединение: выбор пользователя ----------------------------------------

def test_choice_overrides_rules_for_field(svc):
    main = _patient(svc, phone='+7 (999) 111-22-33')
    dup = _patient(svc, phone='+7 (999) 000-00-00')
    plan = svc['merge'].plan_merge(main.id, [dup.id], {'phone': dup.id})
    assert [(c.field, c.value, c.source_ids) for c in plan.changes] == [('phone', '+7 (999) 000-00-00', (dup.id,))]
    assert not any(w.startswith('Телефон:') for w in plan.warnings)
    svc['merge'].merge_patients(main.id, [dup.id], expected=plan, choices={'phone': dup.id}, backup=False)
    assert svc['patient'].get_by_id(main.id).phone == '+7 (999) 000-00-00'


def test_choice_of_main_keeps_value_without_warning(svc):
    main = _patient(svc, phone='+7 (999) 111-22-33')
    dup = _patient(svc, phone='+7 (999) 000-00-00')
    plan = svc['merge'].plan_merge(main.id, [dup.id], {'phone': main.id})
    assert plan.changes == () and plan.warnings == ()


def test_choice_of_empty_clears_value(svc):
    main = _patient(svc, phone='+7 (999) 111-22-33')
    dup = _patient(svc, phone=None)
    choices = {'phone': dup.id}
    svc['merge'].merge_patients(main.id, [dup.id], choices=choices, backup=False)
    assert svc['patient'].get_by_id(main.id).phone is None


def test_choice_keeps_coarse_date_over_rule(svc):
    """Правила взяли бы точную дату; пользователь выбрал год — дата и точность вместе."""
    main = _patient(svc)
    dup = _patient(svc, birth=YEAR, precision='year')
    choices = {'birth_date': dup.id}
    plan = svc['merge'].plan_merge(main.id, [dup.id], choices)
    assert {c.field: c.value for c in plan.changes} == {'birth_date': YEAR, 'birth_date_precision': 'year'}
    svc['merge'].merge_patients(main.id, [dup.id], expected=plan, choices=choices, backup=False)
    stored = svc['patient'].get_by_id(main.id)
    assert (stored.birth_date, stored.birth_date_precision) == (YEAR, 'year')


def test_choice_of_year_keeps_main_year_over_exact_duplicate(svc):
    main = _patient(svc, birth=YEAR, precision='year')
    dup = _patient(svc)
    plan = svc['merge'].plan_merge(main.id, [dup.id], {'birth_date': main.id})
    assert plan.changes == ()


def test_choice_name_from_duplicate(svc):
    main = _patient(svc, last='Иванова', first='Мария')
    dup = _patient(svc, last='ИВАНОВА', first='Мария')
    svc['merge'].merge_patients(main.id, [dup.id], choices={'last_name': dup.id}, backup=False)
    assert svc['patient'].get_by_id(main.id).last_name == 'ИВАНОВА'


def test_note_choice_one_text_or_join(svc):
    main = _patient(svc, description_text='аллергия', comment_text='свой')
    dup = _patient(svc, description_text='астма', comment_text='чужой')
    choices = {'description_text': [dup.id], 'comment_text': [dup.id, main.id]}
    plan = svc['merge'].plan_merge(main.id, [dup.id], choices)
    assert {c.field: c.value for c in plan.changes} == {'description_text': 'астма', 'comment_text': 'чужой\nсвой'}
    svc['merge'].merge_patients(main.id, [dup.id], expected=plan, choices=choices, backup=False)
    stored = svc['patient'].get_by_id(main.id)
    assert (stored.description_text, stored.comment_text) == ('астма', 'чужой\nсвой')


def test_note_choice_empty_list_clears(svc):
    main = _patient(svc, description_text='аллергия')
    dup = _patient(svc, description_text='астма')
    svc['merge'].merge_patients(main.id, [dup.id], choices={'description_text': []}, backup=False)
    assert svc['patient'].get_by_id(main.id).description_text in (None, '')


def test_main_id_decides_where_appointments_go(svc):
    first = _patient(svc)
    second = _patient(svc)
    app = svc['appointment'].create(AppointmentDTO(patient_id=first.id, date=datetime.date(2026, 3, 1)))
    # основа — вторая строка: приёмы — к ней, значения — по выбору из первой
    svc['merge'].merge_patients(second.id, [first.id], choices={'phone': first.id}, backup=False)
    assert svc['appointment'].get_by_id(app.id).patient_id == second.id
    assert [p.id for p in svc['patient'].get_all()] == [second.id]


# --- сверка с подтверждённым планом ----------------------------------------

def test_confirmed_plan_with_choices_checked(svc):
    main = _patient(svc, phone='+7 (999) 111-22-33')
    dup = _patient(svc, phone='+7 (999) 000-00-00')
    plan = svc['merge'].plan_merge(main.id, [dup.id], {'phone': dup.id})
    # подтверждён один выбор, исполняется другой (или без выбора) — отказ, ничего не меняется
    with pytest.raises(MergePlanChangedError):
        svc['merge'].merge_patients(main.id, [dup.id], expected=plan, backup=False)
    with pytest.raises(MergePlanChangedError):
        svc['merge'].merge_patients(main.id, [dup.id], expected=plan, choices={'phone': main.id}, backup=False)
    assert len(svc['patient'].get_all()) == 2


def test_choice_order_of_keys_does_not_matter(svc):
    main = _patient(svc, phone='1', middle=None)
    dup = _patient(svc, phone='2')
    one = svc['merge'].plan_merge(main.id, [dup.id], {'phone': dup.id, 'middle_name': dup.id})
    other = svc['merge'].plan_merge(main.id, [dup.id], {'middle_name': dup.id, 'phone': dup.id})
    assert one == other


def test_data_changed_after_plan_with_choices(svc):
    main = _patient(svc, phone='1')
    dup = _patient(svc, phone='2')
    choices = {'phone': dup.id}
    plan = svc['merge'].plan_merge(main.id, [dup.id], choices)
    svc['patient'].update(svc['patient'].get_by_id(dup.id).model_copy(update={'phone': '3'}))
    with pytest.raises(MergePlanChangedError):
        svc['merge'].merge_patients(main.id, [dup.id], expected=plan, choices=choices, backup=False)


# --- неверный выбор ---------------------------------------------------------

@pytest.mark.parametrize(
    'choices, message',
    [
        ({'nope': 1}, 'нельзя выбирать'),
        ({'birth_date_precision': 1}, 'нельзя выбирать'),   # точность идёт вместе с датой
        ({'phone': 99}, 'не среди объединяемых'),
        ({'phone': [1]}, 'одна строка'),
        ({'comment_text': 1}, 'список'),
        ({'comment_text': [1, 1]}, 'дважды'),
        ({'comment_text': [99]}, 'не среди объединяемых'),
    ],
)
def test_bad_choices(choices, message):
    with pytest.raises(PatientValidationError, match=message):
        normalize_merge_choices(choices, (1, 2), MergeRules())


def test_bad_choices_refused_before_backup(svc, tmp_path):
    main = _patient(svc)
    dup = _patient(svc)
    with pytest.raises(PatientValidationError):
        svc['merge'].merge_patients(main.id, [dup.id], choices={'nope': dup.id})
    assert not list(tmp_path.glob('clinic.db.bak-*'))


def test_empty_name_choice_refused():
    from app.services.patient_merge import PatientSnapshot, build_merge_plan
    main = PatientDTO(id=1, last_name='И', first_name='М')
    other = PatientDTO(id=2, last_name='', first_name='М')
    with pytest.raises(PatientValidationError, match='пусто'):
        build_merge_plan(
            PatientSnapshot(main, (), {}),
            [PatientSnapshot(other, (), {})],
            choices={'last_name': 2},
        )
