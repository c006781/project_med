# tests/test_drafts/test_moved_into_deleted_new.py

"""
Запись, перенесённая пользователем в новую запись, которую потом удалили (``MovedRule``).

Ядро — адаптер в памяти; файлы, откат и настоящие переносы мимо черновиков — сервисы
приложения на временной SQLite и временной папке фото (настоящие база и папка не читаются).
"""

import datetime
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.database.database_shema.clinic import PhotoFile  # noqa: E402
from app.draft.integration import (  # noqa: E402
    DEFAULT_MOVED_RULE, ServiceAdapter, build_app_schema, make_parent_resolver,
)
from app.dto.dto_all import AppointmentDTO, AppointmentNoteDTO, PatientDTO, PhotoDTO  # noqa: E402
from app.services.patient_merge import PatientMergeService  # noqa: E402
from app.utils.drafts import (  # noqa: E402
    DraftStore, MovedRule, PlanError, RejectChildChangesPolicy, SaveScope, StalePlanError,
    build_plan, execute_plan, find_conflicts, save_with_confirmation,
)
from app.utils.drafts_qt import Column, DraftTableModel, describe_deletes, make_confirmations  # noqa: E402


FK = 'appointment_id'


@pytest.fixture
def delete_store(schema):
    """Хранилище с правилом «удалять вместе с новой записью»."""
    return DraftStore(schema, moved_rule=MovedRule.DELETE)


def _move_and_delete(store, photo=7, old=12, by_user=True, **extra):
    """Перенос фото в новый приём пациента 1, затем удаление приёма; возвращает id приёма."""
    new = store.create('appointment', {'date': 'x'}, parent_id=1)
    store.modify('photo', photo, {FK: new, **extra}, original={FK: old}, parent_id=old, by_user=by_user)
    store.delete('appointment', new)
    return new


# ------------------------------------------------------------------ правило DELETE: объём

def test_save_all_deletes_moved_record(delete_store, adapter):
    """Сохранили всё (и ветку прежнего родителя): запись удаляется вместе с новой."""
    adapter.rows[('photo', 7)] = {FK: 12}
    new = _move_and_delete(delete_store)
    plan = build_plan(delete_store)
    assert [d.key for d in plan.moved_deletes] == [('photo', 7)]
    assert plan.deletes == () and plan.moved_kept == ()
    assert plan.deleted_branches == (('appointment', new),)
    assert ('photo', 7) not in {d.key for d in plan.dropped}
    result = execute_plan(delete_store, plan, adapter)
    assert ('photo', 7) not in adapter.rows
    assert result.deleted == (('photo', 7),) and result.moved_deleted == (('photo', 7),)
    assert delete_store.is_empty


@pytest.mark.parametrize('scope', [SaveScope.SELF, SaveScope.BRANCH])
def test_save_only_new_record_absorbs(delete_store, adapter, scope):
    """Сохранили только новую запись — поглощение: запись на месте, у прежнего родителя."""
    adapter.rows[('photo', 7)] = {FK: 12}
    new = _move_and_delete(delete_store)
    plan = build_plan(delete_store, [('appointment', new)], scope)
    assert plan.moved_deletes == ()
    assert [d.key for d in plan.moved_kept] == [('photo', 7)]
    execute_plan(delete_store, plan, adapter)
    assert adapter.rows[('photo', 7)] == {FK: 12}
    assert adapter.log == []


def test_save_old_parent_branch_deletes_without_new_in_scope(delete_store, adapter):
    """Выбран прежний родитель: по связям запись уже не его потомок, но перенос — из его ветки."""
    adapter.rows[('photo', 7)] = {FK: 12}
    new = _move_and_delete(delete_store)
    plan = build_plan(delete_store, [('appointment', 12)], SaveScope.BRANCH)
    assert [d.key for d in plan.moved_deletes] == [('photo', 7)]
    assert plan.needs_confirmation
    execute_plan(delete_store, plan, adapter)
    assert ('photo', 7) not in adapter.rows
    assert delete_store.has_draft('appointment', new)      # удалённая новая вне объёма — не тронута


def test_save_old_parent_without_descendants_does_not_touch(delete_store):
    """Только сам прежний родитель, без потомков, — запись не трогается."""
    _move_and_delete(delete_store)
    plan = build_plan(delete_store, [('appointment', 12)], SaveScope.SELF)
    assert plan.moved_deletes == () and plan.is_empty


def test_save_old_parent_ancestor_branch_deletes(schema, adapter):
    """Выбран предок прежнего родителя с потомками — та же ветка."""
    store = DraftStore(schema, moved_rule=MovedRule.DELETE)
    store.remember_parent('appointment', 12, 5)
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(store)
    plan = build_plan(store, [('patient', 5)], SaveScope.BRANCH)
    assert [d.key for d in plan.moved_deletes] == [('photo', 7)]
    assert build_plan(store, [('patient', 99)], SaveScope.BRANCH).moved_deletes == ()


def test_record_itself_selected_deletes(delete_store, adapter):
    """Выбрана сама запись (её строка в таблице прежнего родителя) — удаляется, не blocked."""
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(delete_store)
    plan = build_plan(delete_store, [('photo', 7)], SaveScope.SELF)
    assert [d.key for d in plan.moved_deletes] == [('photo', 7)] and plan.blocked == ()
    execute_plan(delete_store, plan, adapter)
    assert ('photo', 7) not in adapter.rows


def test_new_ancestor_deleted_counts(delete_store):
    """Удалена не сама новая запись, а её новый предок — выше только новые: применимо."""
    patient = delete_store.create('patient', {})
    new = delete_store.create('appointment', {}, parent_id=patient)
    delete_store.modify('photo', 7, {FK: new}, original={FK: 12}, parent_id=12, by_user=True)
    delete_store.delete('patient', patient)
    assert [d.key for d in build_plan(delete_store).moved_deletes] == [('photo', 7)]


def test_moved_appointment_takes_nested_drafts(schema, adapter):
    """Перенесён приём: вложенные черновики поглощаются вместе с ним, и вне объёма тоже."""
    store = DraftStore(schema, moved_rule=MovedRule.DELETE)
    adapter.rows[('appointment', 5)] = {'patient_id': 1}
    patient = store.create('patient', {})
    store.modify('appointment', 5, {'patient_id': patient}, original={'patient_id': 1},
                 parent_id=1, by_user=True)
    store.modify('photo', 9, {'d': 'x'}, parent_id=5)
    store.delete('patient', patient)
    plan = build_plan(store, [('patient', 1)], SaveScope.BRANCH)
    assert [d.key for d in plan.moved_deletes] == [('appointment', 5)]
    assert ('photo', 9) in {d.key for d in plan.dropped}
    execute_plan(store, plan, adapter)
    assert ('appointment', 5) not in adapter.rows
    assert not store.has_draft('photo', 9)


def test_old_parent_and_moved_record_deleted_children_first(delete_store, adapter):
    """Удаляется и прежний родитель: фото удаляется раньше приёма, без ошибок и повторов."""
    adapter.rows[('photo', 7)] = {FK: 12}
    adapter.rows[('appointment', 12)] = {'patient_id': 1}
    _move_and_delete(delete_store)
    delete_store.delete('appointment', 12, parent_id=1)
    execute_plan(delete_store, build_plan(delete_store), adapter)
    assert [e[1:] for e in adapter.log] == [('photo', 7), ('appointment', 12)]


# ------------------------------------------------------------------ не применимо

def test_move_into_existing_deleted_parent_is_not_this_rule(delete_store):
    """Перенос в СУЩЕСТВУЮЩУЮ удалённую запись — прежнее поведение: поглощение."""
    delete_store.modify('photo', 7, {FK: 20}, original={FK: 12}, parent_id=12, by_user=True)
    delete_store.delete('appointment', 20, parent_id=1)
    plan = build_plan(delete_store)
    assert plan.moved_deletes == ()
    assert [d.key for d in plan.moved_kept] == [('photo', 7)]


def test_existing_record_between_is_not_this_rule(delete_store):
    """Между записью и удалённой новой — существующая запись: поглощается, как при отмене (N2)."""
    patient = delete_store.create('patient', {})
    delete_store.modify('appointment', 5, {'patient_id': patient}, original={'patient_id': 1},
                        parent_id=1, by_user=True)
    delete_store.modify('photo', 7, {FK: 5}, original={FK: 12}, parent_id=12, by_user=True)
    delete_store.delete('patient', patient)
    plan = build_plan(delete_store)
    assert [d.key for d in plan.moved_deletes] == [('appointment', 5)]
    assert [d.key for d in plan.moved_kept] == [('photo', 7)]


def test_new_record_is_not_this_rule(delete_store):
    """Новая запись в удалённой новой — просто поглощается, в БД её не было."""
    new = delete_store.create('appointment', {}, parent_id=1)
    delete_store.create('photo', {}, parent_id=new)
    delete_store.delete('appointment', new)
    plan = build_plan(delete_store)
    assert plan.moved_deletes == () and plan.moved_kept == ()


def test_unknown_old_parent_is_not_deleted(delete_store):
    """Откуда перенесена — неизвестно: удалять нельзя."""
    new = delete_store.create('appointment', {}, parent_id=1)
    delete_store.modify('photo', 7, {FK: new}, parent_id=12, by_user=True)
    delete_store.delete('appointment', new)
    plan = build_plan(delete_store)
    assert plan.moved_deletes == ()
    assert [d.key for d in plan.moved_kept] == [('photo', 7)]


def test_kept_not_promised_when_old_parent_deleted(schema):
    """Правило KEEP и удаление прежнего родителя: обещать «останется» нельзя."""
    store = DraftStore(schema)
    _move_and_delete(store)
    store.delete('appointment', 12, parent_id=1)
    assert build_plan(store).moved_kept == ()


# ------------------------------------------------------------------ кто перенёс

def test_move_by_code_never_deletes(delete_store, adapter):
    """Перенос кодом (объединение, импорт): modify без by_user — запись остаётся."""
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(delete_store, by_user=False)
    plan = build_plan(delete_store)
    assert plan.moved_deletes == ()
    assert [d.key for d in plan.moved_kept] == [('photo', 7)]
    execute_plan(delete_store, plan, adapter)
    assert adapter.rows[('photo', 7)] == {FK: 12}


def test_last_move_decides(delete_store):
    """Решает последний перенос: код после пользователя — не удаляем, и наоборот; отмена — назад."""
    new = delete_store.create('appointment', {}, parent_id=1)
    other = delete_store.create('appointment', {}, parent_id=1)
    delete_store.modify('photo', 7, {FK: new}, original={FK: 12}, parent_id=12, by_user=True)
    delete_store.modify('photo', 7, {FK: other})
    assert delete_store.get('photo', 7).moved_by_user is False
    delete_store.undo()
    assert delete_store.get('photo', 7).moved_by_user is True
    delete_store.redo()
    delete_store.modify('photo', 7, {FK: new}, by_user=True)
    assert delete_store.get('photo', 7).moved_by_user is True
    delete_store.modify('photo', 7, {'d': 'x'})                 # другое поле — признак не меняет
    assert delete_store.get('photo', 7).moved_by_user is True


def test_parent_info_is_not_a_user_move(delete_store):
    """Сведения о родителе (remember_parent) — не перенос: черновика с переносом нет."""
    new = delete_store.create('appointment', {}, parent_id=1)
    delete_store.remember_parent('photo', 7, new)
    delete_store.modify('photo', 7, {'d': 'x'}, by_user=True)
    delete_store.delete('appointment', new)
    assert build_plan(delete_store).moved_deletes == ()


def test_returned_move_clears_mark(delete_store):
    """Вернули поле связи (значением или отменой поля) — переноса нет, удалять нечего."""
    new = delete_store.create('appointment', {}, parent_id=1)
    delete_store.modify('photo', 7, {FK: new, 'd': 'x'}, original={FK: 12}, parent_id=12, by_user=True)
    delete_store.modify('photo', 7, {FK: 12}, by_user=True)
    assert delete_store.get('photo', 7).moved_by_user is False
    delete_store.modify('photo', 7, {FK: new}, by_user=True)
    delete_store.revert_field('photo', 7, FK)
    assert delete_store.get('photo', 7).moved_by_user is False
    delete_store.delete('appointment', new)
    assert build_plan(delete_store).moved_deletes == ()


def test_moved_elsewhere_in_database_refused(delete_store, adapter):
    """Родитель в БД уже другой (мимо черновика): отказ и откат всего, запись и черновики на месте."""
    adapter.rows[('photo', 7)] = {FK: 99}
    adapter.rows[('photo', 8)] = {FK: 12}
    new = _move_and_delete(delete_store)
    delete_store.modify('photo', 8, {'d': 'x'})
    plan = build_plan(delete_store)
    with pytest.raises(PlanError, match='перенесли не через черновики'):
        execute_plan(delete_store, plan, adapter)
    assert adapter.rows[('photo', 7)] == {FK: 99}
    assert adapter.rows[('photo', 8)] == {FK: 12}              # правка другой записи откатилась
    assert delete_store.has_draft('photo', 7) and delete_store.has_draft('appointment', new)


def test_conflicts_show_moved_elsewhere(delete_store, adapter):
    """find_conflicts заранее видит и такой перенос."""
    adapter.rows[('photo', 7)] = {FK: 99}
    _move_and_delete(delete_store)
    [conflict] = find_conflicts(build_plan(delete_store), lambda e, i: adapter.read(e, i))
    assert (conflict.node, conflict.field, conflict.current) == (('photo', 7), FK, 99)


def test_already_gone_is_not_an_error(delete_store, adapter):
    """Записи в БД уже нет — удалять нечего, сохранение проходит, связи забыты."""
    _move_and_delete(delete_store)
    result = execute_plan(delete_store, build_plan(delete_store), adapter)
    assert adapter.log == [] and result.deleted == (('photo', 7),)
    assert delete_store.is_empty and delete_store.parent_of('photo', 7) is None


def test_adapter_without_read_refused(delete_store, adapter):
    """Адаптер не умеет читать — проверить, откуда перенесена, нельзя: отказ."""
    class NoRead:
        transaction = adapter.transaction
        delete = adapter.delete
    _move_and_delete(delete_store)
    with pytest.raises(PlanError, match='нет read'):
        execute_plan(delete_store, build_plan(delete_store), NoRead())


# ------------------------------------------------------------------ KEEP и переключение

def test_keep_rule_old_behavior(schema, adapter):
    """По умолчанию пакета (KEEP): запись остаётся, перенос и правки не пишутся."""
    store = DraftStore(schema)
    assert store.moved_rule is MovedRule.KEEP
    adapter.rows[('photo', 7)] = {FK: 12}
    new = _move_and_delete(store, d='x')
    plan = build_plan(store)
    assert plan.moved_deletes == ()
    assert [d.key for d in plan.moved_kept] == [('photo', 7)]
    assert {d.key for d in plan.dropped} == {('appointment', new), ('photo', 7)}
    execute_plan(store, plan, adapter)
    assert adapter.rows[('photo', 7)] == {FK: 12}
    assert store.is_empty


def test_keep_rule_record_selected_stays_blocked(schema):
    """KEEP и выбрана сама запись — как раньше: blocked, черновик остаётся."""
    store = DraftStore(schema)
    _move_and_delete(store)
    plan = build_plan(store, [('photo', 7)], SaveScope.SELF)
    assert plan.blocked == (('photo', 7),) and plan.is_empty


def test_rule_switch_makes_plan_stale(delete_store, adapter):
    """Значение сменили после показа плана: план не исполняется, новый — по новому значению."""
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(delete_store)
    plan = build_plan(delete_store)
    delete_store.moved_rule = 'keep'
    with pytest.raises(StalePlanError):
        execute_plan(delete_store, plan, adapter)
    assert delete_store.moved_rule is MovedRule.KEEP
    assert build_plan(delete_store).moved_deletes == ()
    version = delete_store.version
    delete_store.moved_rule = MovedRule.KEEP                   # то же значение — план жив
    assert delete_store.version == version
    with pytest.raises(ValueError):
        delete_store.moved_rule = 'x'


def test_app_default_is_delete():
    """Приложение: значение одно, DELETE (решение владельца), его берёт create_app_drafts."""
    import inspect
    from app.draft.integration import create_app_drafts
    assert DEFAULT_MOVED_RULE is MovedRule.DELETE
    parameter = inspect.signature(create_app_drafts).parameters['moved_rule']
    assert parameter.default is DEFAULT_MOVED_RULE


def test_create_app_drafts_passes_rule(monkeypatch):
    """create_app_drafts передаёт значение хранилищу — других мест выбора нет."""
    from app import dependencies
    from app.draft.integration import create_app_drafts
    monkeypatch.setattr(dependencies, 'get_db', lambda: None)
    assert create_app_drafts().store.moved_rule is MovedRule.DELETE
    assert create_app_drafts(MovedRule.KEEP).store.moved_rule is MovedRule.KEEP


def test_reject_policy_still_refuses(delete_store):
    """Строгая политика: изменения в удаляемой ветке — отказ, как и раньше."""
    _move_and_delete(delete_store)
    with pytest.raises(PlanError, match='несохранённые изменения'):
        build_plan(delete_store, delete_policy=RejectChildChangesPolicy())


# ------------------------------------------------------------------ отмена новой записи

@pytest.mark.parametrize('rule', list(MovedRule))
def test_discard_new_returns_to_old_parent(schema, adapter, rule):
    """Отмена новой записи при любом значении: к прежнему родителю, правки на месте, удалять нечего."""
    store = DraftStore(schema, moved_rule=rule)
    new = _move_and_delete(store, d='x')
    store.discard([('appointment', new)])
    draft = store.get('photo', 7)
    assert draft.data == {'d': 'x'} and draft.moved_by_user is False
    assert store.parent_of('photo', 7) == ('appointment', 12)
    assert build_plan(store).moved_deletes == ()


# ------------------------------------------------------------------ сценарий с вопросом

def _save(store, adapter, targets=None, scope=None, answer=True):
    asked = []

    def ask(plan):
        asked.append(plan)
        return answer
    return save_with_confirmation(store, adapter, targets, scope, ask, ask), asked


@pytest.mark.parametrize('rule, field', [(MovedRule.DELETE, 'moved_deletes'), (MovedRule.KEEP, 'moved_kept')])
def test_question_asked_for_any_rule(schema, adapter, rule, field):
    """Пользователю сообщают до сохранения при любом значении; отказ — ничего не меняется."""
    store = DraftStore(schema, moved_rule=rule)
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(store)
    result, asked = _save(store, adapter, answer=False)
    assert result is None and len(asked) == 1
    assert [d.key for d in getattr(asked[0], field)] == [('photo', 7)]
    assert adapter.rows[('photo', 7)] == {FK: 12} and store.has_draft('photo', 7)


def test_question_asked_without_deleted_branches(delete_store, adapter):
    """Удалённая новая вне объёма — веток в плане нет, а вопрос есть: запись удалится."""
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(delete_store)
    result, asked = _save(delete_store, adapter, [('appointment', 12)], SaveScope.BRANCH)
    assert asked[0].deleted_branches == () and result.moved_deleted == (('photo', 7),)


def test_answer_changed_rule_asks_again(delete_store, adapter):
    """Значение сменили, пока открыт вопрос: спросить заново, по новому плану."""
    adapter.rows[('photo', 7)] = {FK: 12}
    _move_and_delete(delete_store)
    asked = []

    def ask(plan):
        asked.append(plan)
        delete_store.moved_rule = 'keep'
        return True
    save_with_confirmation(delete_store, adapter, None, None, ask, ask)
    assert len(asked) == 2 and asked[1].moved_deletes == ()
    assert adapter.rows[('photo', 7)] == {FK: 12}


# ------------------------------------------------------------------ тексты и таблица

@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def test_text_names_deleted(delete_store):
    _move_and_delete(delete_store)
    text = describe_deletes(delete_store.schema, build_plan(delete_store))
    assert 'будут УДАЛЕНЫ' in text
    assert '• Фото №7 (перенесено из: Приём №12)' in text
    assert 'ОСТАНУТСЯ' not in text and 'будут потеряны' not in text


def test_text_names_kept(schema):
    store = DraftStore(schema)
    _move_and_delete(store)
    text = describe_deletes(schema, build_plan(store))
    assert 'ОСТАНУТСЯ у прежнего родителя' in text and '• Фото №7 (перенесено из: Приём №12)' in text
    assert 'УДАЛЕНЫ' not in text and 'будут потеряны' not in text


def test_text_without_branches_has_no_branch_header(delete_store):
    _move_and_delete(delete_store)
    text = describe_deletes(delete_store.schema, build_plan(delete_store, [('photo', 7)], SaveScope.SELF))
    assert 'ВМЕСТЕ' not in text and '• Фото №7' in text


def test_text_long_list_cut(delete_store):
    new = delete_store.create('appointment', {}, parent_id=1)
    for photo in range(100, 120):
        delete_store.modify('photo', photo, {FK: new}, original={FK: 12}, parent_id=12, by_user=True)
    delete_store.delete('appointment', new)
    assert '… и ещё 5' in describe_deletes(delete_store.schema, build_plan(delete_store))


def test_dialog_shows_text_and_returns_answer(qapp, monkeypatch, delete_store):
    shown = []

    def fake(parent, title, text, *args):
        shown.append(text)
        return QMessageBox.No
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(fake))
    _move_and_delete(delete_store)
    _, ask_delete = make_confirmations(None, delete_store.schema)
    assert ask_delete(build_plan(delete_store)) is False
    assert 'Фото №7' in shown[0] and shown[0].endswith('Продолжить?')


def test_table_edit_is_user_move(qapp, delete_store):
    """Правка поля связи в таблице — перенос пользователя; вернули значение — признака нет."""
    model = DraftTableModel(delete_store, 'photo', [Column(FK, 'Приём')])
    model.set_rows([{'id': 7, FK: 12}], parent_id=12)
    new = delete_store.create('appointment', {}, parent_id=1)
    assert model.setData(model.index(0, 0), new)
    assert delete_store.get('photo', 7).moved_by_user is True
    delete_store.delete('appointment', new)
    assert [d.key for d in build_plan(delete_store).moved_deletes] == [('photo', 7)]
    delete_store.undelete('appointment', new)
    assert model.setData(model.index(0, 0), 12)
    assert not delete_store.has_draft('photo', 7)
    model.detach()


# ------------------------------------------------------------------ настоящие сервисы и файлы

@pytest.fixture
def app_adapter(services):
    """Адаптер как в приложении: одна сессия общей базы на всё сохранение."""
    return ServiceAdapter({
        'patient': (lambda: services['patient'], PatientDTO),
        'appointment': (lambda: services['appointment'], AppointmentDTO),
        'photo': (lambda: services['photo'], PhotoDTO),
        'note': (lambda: services['note'], AppointmentNoteDTO),
    }, transaction_factory=lambda: services['db'].session_scope())


@pytest.fixture
def app_store(app_adapter):
    schema = build_app_schema()
    return DraftStore(schema, parent_resolver=make_parent_resolver(schema, app_adapter),
                      moved_rule=MovedRule.DELETE)


@pytest.fixture
def scan(tmp_path):
    path = tmp_path / 'scan.jpg'
    path.write_bytes(b'\xff\xd8fake')
    return str(path)


@pytest.fixture
def clinic(services, scan):
    """Пациент, два приёма, фото у первого; storage — папка фото."""
    patient = services['patient'].create(PatientDTO(first_name='Иван', last_name='Петров',
                                                    birth_date=datetime.date(1980, 5, 5)))
    a1, a2 = [services['appointment'].create(AppointmentDTO(patient_id=patient.id,
                                                            date=datetime.date(2026, 10, day)))
              for day in (1, 2)]
    photo = services['photo'].create(PhotoDTO(appointment_id=a1.id, file_path=scan))
    storage = services['photo']._storage_path
    return {'patient': patient, 'a1': a1, 'a2': a2, 'photo': photo, 'storage': storage}


def _app_move_and_delete(store, photo, clinic):
    new = store.create('appointment', {'date': datetime.date(2026, 10, 9)}, parent_id=clinic['patient'].id)
    store.modify('photo', photo.id, {FK: new}, original={FK: photo.appointment_id},
                 parent_id=photo.appointment_id, by_user=True)
    store.delete('appointment', new)
    return new


def _file_rows(services):
    with services['db'].session_scope() as session:
        return sorted(r.file_path for r in session.query(PhotoFile))


def _ids(services):
    return sorted(p.id for p in services['photo'].get_all())


def test_services_last_link_removes_file(services, app_store, app_adapter, clinic):
    """Последняя ссылка: фото удалено, строка файла и файл — действием таблицы файлов."""
    name = clinic['photo'].file_path
    _app_move_and_delete(app_store, clinic['photo'], clinic)
    result = save_with_confirmation(app_store, app_adapter, None, None, None, lambda plan: True)
    assert result.moved_deleted == (('photo', clinic['photo'].id),)
    assert _ids(services) == []
    assert _file_rows(services) == []
    assert not os.path.exists(os.path.join(clinic['storage'], name))


def test_services_other_link_keeps_file(services, app_store, app_adapter, clinic):
    """Есть другая ссылка на файл: фото удалено, файл на месте."""
    name = clinic['photo'].file_path
    other = services['photo'].create(PhotoDTO(appointment_id=clinic['a2'].id, file_path=name))
    assert other.file_path == name
    _app_move_and_delete(app_store, clinic['photo'], clinic)
    save_with_confirmation(app_store, app_adapter, None, None, None, lambda plan: True)
    assert _ids(services) == [other.id]
    assert _file_rows(services) == [name]
    assert os.path.exists(os.path.join(clinic['storage'], name))


def test_services_rollback_keeps_photo_and_file(services, app_store, app_adapter, clinic, monkeypatch, scan):
    """Сбой в той же транзакции после удаления: фото, строка файла и файл на месте, черновики тоже."""
    first = clinic['photo']
    second = services['photo'].create(PhotoDTO(appointment_id=clinic['a1'].id, file_path=scan))
    new = _app_move_and_delete(app_store, first, clinic)
    app_store.modify('photo', second.id, {FK: new}, original={FK: clinic['a1'].id},
                     parent_id=clinic['a1'].id, by_user=True)
    real_delete = services['photo'].delete
    calls = []

    def fails_on_second(photo_id, session=None):
        calls.append(photo_id)
        if len(calls) == 2:
            raise RuntimeError('сбой записи')
        real_delete(photo_id, session=session)
    monkeypatch.setattr(services['photo'], 'delete', fails_on_second)
    with pytest.raises(RuntimeError, match='сбой записи'):
        save_with_confirmation(app_store, app_adapter, None, None, None, lambda plan: True)
    assert len(calls) == 2
    assert _ids(services) == sorted([first.id, second.id])
    assert _file_rows(services) == sorted([first.file_path, second.file_path])
    assert os.path.exists(os.path.join(clinic['storage'], first.file_path))
    assert os.path.exists(os.path.join(clinic['storage'], second.file_path))
    assert app_store.has_draft('photo', first.id) and app_store.has_draft('appointment', new)


def test_services_only_new_saved_keeps_photo_and_file(services, app_store, app_adapter, clinic):
    """Сохранили только новую запись: поглощение, фото у прежнего приёма, файл на месте."""
    new = _app_move_and_delete(app_store, clinic['photo'], clinic)
    save_with_confirmation(app_store, app_adapter, [('appointment', new)], SaveScope.BRANCH,
                           None, lambda plan: True)
    assert services['photo'].get_by_id(clinic['photo'].id).appointment_id == clinic['a1'].id
    assert os.path.exists(os.path.join(clinic['storage'], clinic['photo'].file_path))


def test_services_move_by_code_keeps_photo_and_file(services, app_store, app_adapter, clinic):
    """Перенос в черновике кодом (без by_user): фото и файл остаются."""
    new = app_store.create('appointment', {'date': datetime.date(2026, 10, 9)}, parent_id=clinic['patient'].id)
    app_store.modify('photo', clinic['photo'].id, {FK: new}, original={FK: clinic['a1'].id},
                     parent_id=clinic['a1'].id)
    app_store.delete('appointment', new)
    save_with_confirmation(app_store, app_adapter, None, None, None, lambda plan: True)
    assert services['photo'].get_by_id(clinic['photo'].id).appointment_id == clinic['a1'].id
    assert os.path.exists(os.path.join(clinic['storage'], clinic['photo'].file_path))


def test_services_real_merge_moved_photo_is_not_deleted(services, app_store, app_adapter, clinic, scan):
    """Настоящее объединение пациентов перенесло фото, пока лежал черновик: отказ, фото и файл целы."""
    duplicate = services['patient'].create(PatientDTO(first_name='Иван', last_name='Петров',
                                                      birth_date=datetime.date(1980, 5, 5)))
    repeated = services['appointment'].create(AppointmentDTO(patient_id=duplicate.id,
                                                             date=clinic['a1'].date))
    photo = services['photo'].create(PhotoDTO(appointment_id=repeated.id, file_path=scan))
    new = _app_move_and_delete(app_store, photo, clinic)
    merge = PatientMergeService(services['db'], services['patient'], services['appointment'])
    merge.merge_patients(clinic['patient'].id, [duplicate.id], backup=False)
    after_merge = services['photo'].get_by_id(photo.id)
    assert after_merge.appointment_id == clinic['a1'].id       # объединение действительно перенесло
    with pytest.raises(PlanError, match='перенесли не через черновики'):
        save_with_confirmation(app_store, app_adapter, None, None, None, lambda plan: True)
    assert services['photo'].get_by_id(photo.id).appointment_id == clinic['a1'].id
    assert os.path.exists(os.path.join(clinic['storage'], photo.file_path))
    assert app_store.has_draft('photo', photo.id)
    app_store.discard([('appointment', new)])                  # выход: отменить новую запись
    save_with_confirmation(app_store, app_adapter, None, None, None, lambda plan: True)
    assert services['photo'].get_by_id(photo.id).appointment_id == clinic['a1'].id
