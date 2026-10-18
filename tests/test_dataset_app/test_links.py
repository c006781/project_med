# tests/test_dataset_app/test_links.py

"""
Связи-ссылки (не владение) в приложении — на настоящей SQLite во временной папке.

Тестовые таблицы: «врачи» (корень) и «назначения-заказы» (принадлежат приёму, ссылаются на
врача). Проверяется: связи определяются из модели и настраиваются в описании; новая запись
цели в черновиках выбирается в ссылке и при сохранении пишется раньше; правило удаления
(запрет / обнуление) — с откатом всего; список выбора и показ текста вместо id.
"""

import os
from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, ForeignKey, Integer, String

from app.database.database_shema.clinic import Base
from app.draft.integration import AppDrafts, make_parent_resolver
from app.services.services_all import BaseService
from app.tables import CLINIC, SpecError, TableRegistry, TableSpec, ref
from app.utils.drafts import DeleteBlocked, DraftStore

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class LinkDoctor(Base):
    """Врач (только для теста)."""
    __tablename__ = 'test_doctors'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)


class LinkOrder(Base):
    """Назначение-заказ: принадлежит приёму, ссылается на врача (только для теста)."""
    __tablename__ = 'test_orders'
    id = Column(Integer, primary_key=True, autoincrement=True)
    appointment_id = Column(Integer, ForeignKey('appointments.id'), nullable=False)
    doctor_id = Column(Integer, ForeignKey('test_doctors.id'), nullable=True)
    title = Column(String(100), nullable=False)


class DoctorDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    name: str


class OrderDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    appointment_id: int
    doctor_id: Optional[int] = None
    title: str


DOCTOR_CONFIG = {'id': {'title': 'ID', 'editable': False, 'hidden': True, 'updatable': False},
                 'name': {'title': 'Врач', 'required': True}}
ORDER_CONFIG = {'id': {'title': 'ID', 'editable': False, 'hidden': True, 'updatable': False},
                'appointment_id': {'title': 'Приём', 'required': True, 'hidden': True},
                'doctor_id': {'title': 'Врач'},
                'title': {'title': 'Назначение', 'required': True}}


@pytest.fixture
def link_services(services):
    Base.metadata.create_all(services['db'].engine)          # тестовые таблицы — без миграции
    db = services['db']
    return {'doctor': BaseService(db, None, LinkDoctor, DoctorDTO, DOCTOR_CONFIG),
            'order': BaseService(db, None, LinkOrder, OrderDTO, ORDER_CONFIG)}


def registry(link_services, **order_options):
    """Клиника + врачи + заказы (ссылка на врача — по умолчанию или настроенная)."""
    base = [CLINIC.get(n) for n in CLINIC.names()]
    return TableRegistry(base + [
        TableSpec('test_doctors', 'doctor', 'Врачи', 'Врач', LinkDoctor, DoctorDTO, DOCTOR_CONFIG,
                  service=lambda: link_services['doctor'], order=('name',)),
        TableSpec('test_orders', 'order', 'Назначения', 'Назначение', LinkOrder, OrderDTO, ORDER_CONFIG,
                  service=lambda: link_services['order'], order=('id',), **order_options),
    ])


def drafts_for(reg, services, providers, link_services):
    schema = reg.drafts_schema()
    adapter = reg.service_adapter(transaction_factory=lambda: services['db'].session_scope(),
                                  services={**providers, 'doctor': lambda: link_services['doctor'],
                                            'order': lambda: link_services['order']})
    return AppDrafts(schema, adapter, DraftStore(schema, parent_resolver=make_parent_resolver(schema, adapter)))


def build(reg, providers, link_services, drafts=None):
    built = reg.build(services={**providers, 'doctor': lambda: link_services['doctor'],
                                'order': lambda: link_services['order']}, drafts=drafts)
    built.open()
    built['test_doctors'].open()
    return built


def test_links_detected_and_configurable(link_services):
    with pytest.raises(SpecError, match='несколько ссылок'):
        registry(link_services)                               # два ключа на таблицы реестра — неоднозначно
    reg = registry(link_services, parent='appointments')
    assert reg.parent('test_orders') == 'appointments'
    assert [(l.field, l.table, l.on_delete) for l in reg.links('test_orders')] == [
        ('doctor_id', 'test_doctors', 'restrict')]            # ссылка по умолчанию — запрет
    reg = registry(link_services, links=(ref('doctor_id', 'test_doctors', on_delete='set_null'),))
    assert reg.parent('test_orders') == 'appointments'        # объявленная ссылка — не родитель
    refs = {t.name: t.references for t in reg.drafts_schema()}
    assert refs['order'][0].entity == 'doctor' and refs['order'][0].on_delete == 'set_null'
    with pytest.raises(SpecError, match='не описана'):
        registry(link_services, links=(ref('doctor_id', 'nowhere'),))


def test_choices_and_display_include_unsaved(services, providers, filled, link_services):
    link_services['doctor'].create(DoctorDTO(name='Иванова'))
    reg = registry(link_services, parent='appointments')
    drafts = drafts_for(reg, services, providers, link_services)
    built = build(reg, providers, link_services, drafts)
    doctors, orders = built['test_doctors'], built['test_orders']
    doctors.append({'name': 'Новый врач'}); doctors.post()
    new_doctor = doctors.current_key
    field = orders.fields['doctor_id']
    assert [text for _, text in field.extra['choices']()] == ['Иванова', 'Новый врач']
    orders.append({'title': 'Анализ', 'doctor_id': new_doctor}); orders.post()
    assert orders.text('doctor_id') == 'Новый врач'           # показ — текст, а не временный id


def test_new_target_saved_first_and_reference_mapped(services, providers, filled, link_services):
    reg = registry(link_services, parent='appointments')
    drafts = drafts_for(reg, services, providers, link_services)
    built = build(reg, providers, link_services, drafts)
    doctors, orders = built['test_doctors'], built['test_orders']
    orders.append({'title': 'Анализ'}); orders.post()         # заказ — раньше врача
    doctors.append({'name': 'Петрова'}); doctors.post()
    orders.set_value('doctor_id', doctors.current_key); orders.post()
    built.save()
    saved = link_services['order'].get_page(0, 10)[0][0]
    doctor = link_services['doctor'].get_page(0, 10)[0][0]
    assert saved.doctor_id == doctor.id and doctor.name == 'Петрова'
    assert orders.text('doctor_id') == 'Петрова' and drafts.store.is_empty


def test_restrict_and_set_null_on_delete(services, providers, filled, link_services):
    doctor = link_services['doctor'].create(DoctorDTO(name='Иванова'))
    appointment = services['appointment'].get_all()[0]
    link_services['order'].create(OrderDTO(appointment_id=appointment.id, doctor_id=doctor.id, title='Анализ'))
    reg = registry(link_services, parent='appointments')
    drafts = drafts_for(reg, services, providers, link_services)
    built = build(reg, providers, link_services, drafts)
    built.patients.set_value('phone', '+7 1'); built.patients.post()
    built['test_doctors'].delete()
    with pytest.raises(DeleteBlocked, match='«Врач #1»: на неё ссылаются записи: «Назначение #1»'):
        built.save()
    assert link_services['doctor'].get_page(0, 10)[1] == 1                       # врач на месте
    assert services['patient'].get_by_id(filled['ivanov']).phone is None         # откат ВСЕГО
    reg = registry(link_services, links=(ref('doctor_id', 'test_doctors', on_delete='set_null'),))
    drafts = drafts_for(reg, services, providers, link_services)
    built = build(reg, providers, link_services, drafts)
    built['test_doctors'].delete()
    built.save()
    assert link_services['doctor'].get_page(0, 10)[1] == 0
    assert link_services['order'].get_page(0, 10)[0][0].doctor_id is None        # ссылка обнулена


def test_form_combo_lists_unsaved_targets(services, providers, filled, link_services):
    from PySide6.QtWidgets import QApplication, QComboBox
    from app.utils.dataset_qt import build_form
    QApplication.instance() or QApplication([])
    reg = registry(link_services, parent='appointments')
    drafts = drafts_for(reg, services, providers, link_services)
    built = build(reg, providers, link_services, drafts)
    built['test_orders'].append({'title': 'X'}); built['test_orders'].post()
    form = build_form(built.sources['test_orders'], ['title', 'doctor_id'])
    combo = form.widgets['doctor_id']
    assert isinstance(combo, QComboBox) and combo.count() == 1                  # только «—»
    built['test_doctors'].append({'name': 'Новый'}); built['test_doctors'].post()
    built['test_orders'].refresh()
    assert [combo.itemText(i) for i in range(combo.count())] == ['—', 'Новый']
    combo.setCurrentIndex(1)
    assert built['test_orders'].value('doctor_id') == built['test_doctors'].current_key


def test_link_text_and_choices_do_not_query_per_row(services, providers, filled, link_services):
    """P7/P8: показ ссылки и список выбора — не запрос к БД на каждую перерисовку/переход по строкам."""
    from sqlalchemy import event
    from PySide6.QtWidgets import QApplication
    from app.utils.dataset_qt import DataSetTableModel, build_form
    QApplication.instance() or QApplication([])
    doctor = link_services['doctor'].create(DoctorDTO(name='Иванова'))
    appointment = services['appointment'].get_all()[0]
    for i in range(5):
        link_services['order'].create(OrderDTO(appointment_id=appointment.id, doctor_id=doctor.id, title=f'Н{i}'))
    reg = registry(link_services, parent='appointments')
    built = build(reg, providers, link_services)
    orders = built['test_orders']
    built.appointments.locate(appointment.id)
    model = DataSetTableModel(built.sources['test_orders'], columns=['title', 'doctor_id'])
    form = build_form(built.sources['test_orders'], ['doctor_id'])
    statements = []
    engine = services['db'].engine
    listener = lambda conn, cursor, statement, *rest: statements.append(statement)  # noqa: E731
    event.listen(engine, 'before_cursor_execute', listener)
    try:
        for _ in range(3):                                       # три полные «перерисовки»
            texts = [model.data(model.index(r, 1)) for r in range(model.rowCount())]
        for _ in range(orders.row_count - 1):
            orders.next()                                        # переход по строкам
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
    assert texts == ['Иванова'] * 5
    doctor_queries = [s for s in statements if 'test_doctors' in s]
    assert len(doctor_queries) <= 2, doctor_queries              # было: на каждую ячейку и строку
    assert form.widgets['doctor_id'].currentText() == 'Иванова'
