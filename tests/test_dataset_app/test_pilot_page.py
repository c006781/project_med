# tests/test_dataset_app/test_pilot_page.py

"""Пилотный экран «пациенты → приёмы → фото» (offscreen Qt, временная SQLite)."""

import datetime
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QDateEdit, QLineEdit, QPlainTextEdit  # noqa: E402

from interfaces.gui.gui_window.pages.dataset_pilot_page import DataSetPilotPage  # noqa: E402



@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def image(tmp_path):
    path = tmp_path / 'scan.png'
    # минимальный корректный PNG 1×1
    path.write_bytes(bytes.fromhex(
        '89504e470d0a1a0a0000000d4948445200000001000000010806000000'
        '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082'))
    return str(path)


def widget_for(page, name, field):
    binding = next(b for b in page.bindings if b.field == field and b.source is page.clinic.sources[name])
    return binding.widget


def test_page_direct_mode(qapp, services, providers, filled):
    page = DataSetPilotPage(services=providers, ask_delete=lambda: True)
    page.open_data()
    model = page.models['patients']
    assert model.rowCount() == 2 and model.data(model.index(0, 0)) == 'Иванов'
    assert page.models['appointments'].rowCount() == 2
    last_name = widget_for(page, 'patients', 'last_name')
    assert isinstance(last_name, QLineEdit) and last_name.text() == 'Иванов'
    page.tables['patients'].setCurrentIndex(model.index(1, 0))                    # щелчок по Петрову
    assert page.clinic.patients.current_index == 1 and last_name.text() == 'Петров'
    assert page.models['appointments'].rowCount() == 1
    last_name.textEdited.emit('Петров-Водкин')
    page.navigators['patients'].button('post').click()
    assert services['patient'].get_by_id(filled['petrov']).last_name == 'Петров-Водкин'
    assert not hasattr(page, 'save_all_btn')                                      # без черновиков — кнопок нет


def test_page_search_and_fetch_settings(qapp, services, providers, filled):
    page = DataSetPilotPage(services=providers, fetch_size=1)
    page.open_data()
    assert page.clinic.patients.row_count == 1 and page.clinic.patients.has_more
    page.search.setText('ПЕТ')                                                    # без учёта регистра
    assert [page.clinic.patients.value('last_name', i) for i in range(page.clinic.patients.row_count)] == ['Петров']
    page.search.setText('')
    page.fetch_mode.setCurrentIndex(1)                                           # всё сразу
    assert page.clinic.patients.row_count == 2 and not page.clinic.patients.has_more


def test_page_drafts_mode_save_current(qapp, services, providers, filled, app_drafts, image):
    saved = []

    def save_handler(targets, scope):
        saved.append(targets)
        return app_drafts.save(targets, scope) is not None

    page = DataSetPilotPage(drafts=app_drafts, save_handler=save_handler, services=providers)
    page.open_data()
    reason = widget_for(page, 'appointments', 'reason_text')
    assert isinstance(reason, QPlainTextEdit) and reason.toPlainText() == ''       # сортировка -date: мартовский
    page.clinic.appointments.last()
    assert reason.toPlainText() == 'боль'
    reason.setPlainText('сильная боль')
    assert page.add_photo_file(image)                                             # пост приёма + новое фото
    assert page.clinic.photos.current_key < 0 and page.clinic.photos.value('image') == image
    assert page.models['appointments'].data(page.models['appointments'].index(
        page.clinic.appointments.current_index, 0), 0)
    assert services['appointment'].get_all()[0].reason_text == 'боль'             # в БД — ещё нет
    assert page.save(current=True)
    assert saved == [[('patient', filled['ivanov'])]]
    appointment = next(a for a in services['appointment'].get_all() if a.reason_text == 'сильная боль')
    photos = services['photo'].get_by_parent(appointment.id)
    assert len(photos) == 1 and os.path.exists(page.clinic.photos.value('image'))
    assert page.clinic.photos.current_key > 0                                     # временный id заменён
    assert app_drafts.store.is_empty and 'Сохранено' in page.status.text()


def test_page_validation_error_shown(qapp, services, providers, filled):
    page = DataSetPilotPage(services=providers)
    page.open_data()
    page.navigators['patients'].button('insert').click()
    page.navigators['patients'].button('post').click()                           # фамилия обязательна
    assert 'обязательно' in page.status.text()
    birth = widget_for(page, 'patients', 'birth_date')
    assert isinstance(birth, QDateEdit)
    page.navigators['patients'].button('cancel').click()
    assert page.clinic.patients.row_count == 2


def test_page_undo_redo_buttons(qapp, services, providers, filled, app_drafts):
    page = DataSetPilotPage(drafts=app_drafts, services=providers)
    page.open_data()
    nav = page.navigators['patients']
    assert not nav.button('undo').isEnabled()
    phone = widget_for(page, 'patients', 'phone')
    phone.textEdited.emit('+7 444'); nav.button('post').click()
    assert nav.button('undo').isEnabled()
    nav.button('undo').click()
    assert page.clinic.patients.value('phone') is None and phone.text() == ''
    nav.button('redo').click()
    assert phone.text() == '+7 444'


def test_finish_pending_edits_before_close(qapp, services, providers, filled, app_drafts):
    """F7: незавершённая правка перед закрытием окна попадает в черновики (иначе пропала бы)."""
    page = DataSetPilotPage(drafts=app_drafts, services=providers)
    page.open_data()
    widget_for(page, 'patients', 'phone').textEdited.emit('+7 555')
    assert app_drafts.store.is_empty                         # правка ещё не завершена
    assert page.finish_pending_edits() is None
    assert not app_drafts.store.is_empty                     # теперь окно её увидит и спросит
    page.clinic.patients.set_value('last_name', '')
    assert 'обязательно' in page.finish_pending_edits()      # не прошла — окно не закроется


def test_dates_shown_like_rest_of_program(qapp, services, providers, filled):
    """F3: даты в таблицах — дд.мм.гггг."""
    page = DataSetPilotPage(services=providers)
    page.open_data()
    model = page.models['patients']
    assert model.data(model.index(0, model.columns.index('birth_date'))) == '01.01.1980'


def test_consistency_through_full_drafts_scenario(qapp, services, providers, filled, app_drafts, image, monkeypatch):
    """
    Итоговая проверка: на КАЖДОМ событии всех трёх наборов (черновики, настоящие сервисы)
    состояние согласовано, и таблицы Qt не перестраиваются целиком там, где хватает
    точного изменения (перестройка — только на «перечитано»).
    """
    from app.utils.dataset import EventKind
    from app.utils.dataset_qt import DataSetTableModel
    unexpected_resets = []
    # перестройка таблицы — каким событием вызвана (обёртка ДО создания экрана: модель
    # подписывает на источник именно эту функцию)
    original_on_event, original_reset = DataSetTableModel._on_event, DataSetTableModel._reset

    def on_event(self, event):
        self._last_kind = event.kind
        try:
            return original_on_event(self, event)
        finally:
            self._last_kind = None

    def reset(self):
        kind = getattr(self, '_last_kind', None)
        if kind not in (None, EventKind.REFRESHED, EventKind.OPENED, EventKind.CLOSED):
            unexpected_resets.append((self.dataset.name if self.dataset else None, kind.value))
        return original_reset(self)

    monkeypatch.setattr(DataSetTableModel, '_on_event', on_event)
    monkeypatch.setattr(DataSetTableModel, '_reset', reset)
    page = DataSetPilotPage(drafts=app_drafts, services=providers, ask_delete=lambda: True)
    problems = []

    def check(event):
        ds = event.dataset
        if ds is None or not ds.active:
            return
        if not (-1 <= ds.current_index < ds.row_count or (ds.row_count == 0 and ds.current_index == -1)):
            problems.append((ds.name, event.kind.value, ds.current_index, ds.row_count))
        if ds.current_index >= 0:
            try:
                ds.current, ds.row_status()
            except Exception as exc:
                problems.append((ds.name, event.kind.value, repr(exc)))
        model = page.models[ds.name]
        if event.kind not in (EventKind.ROWS_INSERTED, EventKind.ROWS_REMOVED) and model.rowCount() != ds.row_count:
            problems.append((ds.name, event.kind.value, 'таблица', model.rowCount(), ds.row_count))

    for ds in page.clinic.datasets:
        ds.subscribe(check)
    page.open_data()
    c = page.clinic
    c.patients.append({'last_name': 'Новый', 'first_name': 'Н', 'birth_date': datetime.date(2001, 1, 1)})
    c.patients.post()
    c.appointments.append({'date': datetime.date(2026, 10, 18), 'reason_text': 'первичный'})
    c.appointments.post()
    assert page.add_photo_file(image)
    c.photos.set_value('description', 'снимок'); c.photos.post()
    c.patients.first(); c.appointments.last(); c.appointments.delete()
    page.clinic.writers['appointments'].undelete(c.appointments)
    c.appointments.delete()
    app_drafts.store.undo(); app_drafts.store.redo()
    c.patients.last()
    assert page.save(current=False)
    c.patients.refresh(); c.patients.first(); c.patients.last()
    assert problems == []
    assert unexpected_resets == []
    new = next(p for p in services['patient'].get_all() if p.last_name == 'Новый')
    appointment = next(a for a in services['appointment'].get_all() if a.patient_id == new.id)
    assert [p.description for p in services['photo'].get_by_parent(appointment.id)] == ['снимок']


def test_consistency_direct_mode_small_portions(qapp, services, providers, filled, monkeypatch):
    """Та же итоговая проверка — запись сразу в БД, порции по одной строке, догрузка таблицей."""
    from app.utils.dataset import EventKind
    from app.utils.dataset_qt import DataSetTableModel
    unexpected_resets, problems = [], []
    original_on_event, original_reset = DataSetTableModel._on_event, DataSetTableModel._reset

    def on_event(self, event):
        self._last_kind = event.kind
        try:
            return original_on_event(self, event)
        finally:
            self._last_kind = None

    def reset(self):
        kind = getattr(self, '_last_kind', None)
        if kind not in (None, EventKind.REFRESHED, EventKind.OPENED, EventKind.CLOSED):
            unexpected_resets.append((self.dataset.name if self.dataset else None, kind.value))
        return original_reset(self)

    monkeypatch.setattr(DataSetTableModel, '_on_event', on_event)
    monkeypatch.setattr(DataSetTableModel, '_reset', reset)
    page = DataSetPilotPage(services=providers, fetch_size=1, ask_delete=lambda: True)

    def check(event):
        ds = event.dataset
        if ds is None or not ds.active:
            return
        if not (-1 <= ds.current_index < ds.row_count or (ds.row_count == 0 and ds.current_index == -1)):
            problems.append((ds.name, event.kind.value, ds.current_index, ds.row_count))
        model = page.models[ds.name]
        if event.kind not in (EventKind.ROWS_INSERTED, EventKind.ROWS_REMOVED) and model.rowCount() != ds.row_count:
            problems.append((ds.name, event.kind.value, 'таблица', model.rowCount(), ds.row_count))

    for ds in page.clinic.datasets:
        ds.subscribe(check)
    page.open_data()
    c, model = page.clinic, page.models['patients']
    while model.canFetchMore():
        model.fetchMore()                                        # прокрутка таблицы до конца
    assert c.patients.row_count == 2
    c.patients.append({'last_name': 'Сидоров', 'first_name': 'С', 'birth_date': datetime.date(1999, 9, 9)})
    c.patients.post()
    c.appointments.append({'date': datetime.date(2026, 10, 18)}); c.appointments.post()
    c.appointments.append({'date': datetime.date(2026, 10, 19)}); c.appointments.cancel()
    c.appointments.delete()
    page.search.setText('сид'); page.search.setText('')
    c.patients.locate(filled['petrov']); c.patients.delete()
    c.patients.refresh(); c.patients.last(); c.patients.first()
    assert problems == [] and unexpected_resets == []
    assert sorted(p.last_name for p in services['patient'].get_all()) == ['Иванов', 'Сидоров']
