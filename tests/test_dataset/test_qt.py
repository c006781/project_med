# tests/test_dataset/test_qt.py

"""Компоненты Qt наборов данных (offscreen Qt, без окна): таблица, привязки, навигатор."""

import ast
import datetime
import os
import sys

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QComboBox, QDateEdit, QLabel, QLineEdit, QPlainTextEdit, QSpinBox,
    QTableView,
)

from app.utils.dataset import (  # noqa: E402
    DataSet, DataSource, FieldDef, FieldKind, MasterDetailLink, MemoryBackend, State,
)
from app.utils.dataset_qt import DataNavigator, DataSetTableModel, bind, bind_table_view  # noqa: E402

PACKAGE = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'utils', 'dataset_qt')


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def patients(n=5, **kw):
    backend = MemoryBackend(
        [{'id': i, 'last_name': f'Фам{i}', 'age': 30 + i, 'active': i % 2 == 0,
          'birth': datetime.date(1990, 1, i), 'note': f'заметка {i}'} for i in range(1, n + 1)],
        fields=[FieldDef('id', 'ID', FieldKind.INTEGER, read_only=True),
                FieldDef('last_name', 'Фамилия', FieldKind.STRING, required=True),
                FieldDef('age', 'Возраст', FieldKind.INTEGER),
                FieldDef('active', 'Активен', FieldKind.BOOLEAN),
                FieldDef('birth', 'Рождён', FieldKind.DATE),
                FieldDef('note', 'Заметка', FieldKind.TEXT, visible=False)])
    return DataSet(backend, name='patients', **kw)


def test_qt_package_imports_only_pyside_and_core():
    stdlib = set(sys.stdlib_module_names)
    for name in os.listdir(PACKAGE):
        if not name.endswith('.py'):
            continue
        tree = ast.parse(open(os.path.join(PACKAGE, name), encoding='utf-8').read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                # .модуль — свой пакет; ..dataset — только ядро
                assert node.level == 1 or node.module == 'dataset', f"{name}: from ..{node.module}"
                continue
            modules = ([a.name for a in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) else [])
            for module in modules:
                top = module.split('.')[0]
                assert top in stdlib or top in ('PySide6', 'dataset'), f"{name}: импорт {module}"


# --------------------------------------------------------------------------- таблица

def test_table_model_shows_fields(qapp):
    ds = patients(3)
    model = DataSetTableModel(DataSource(ds))
    ds.open()
    assert model.columns == ['id', 'last_name', 'age', 'active', 'birth']   # невидимые — нет
    assert model.rowCount() == 3 and model.headerData(1, Qt.Horizontal) == 'Фамилия'
    assert model.data(model.index(0, 1)) == 'Фам1'
    assert model.data(model.index(0, 2), Qt.EditRole) == 31
    assert model.data(model.index(0, 2), Qt.TextAlignmentRole) & Qt.AlignRight
    assert not model.flags(model.index(0, 0)) & Qt.ItemIsEditable            # только чтение
    assert model.flags(model.index(0, 1)) & Qt.ItemIsEditable


def test_table_edit_and_errors(qapp):
    ds = patients(3)
    model = DataSetTableModel(DataSource(ds), columns=['last_name'])
    errors = []
    model.error_occurred.connect(errors.append)
    ds.open()
    assert model.setData(model.index(2, 0), 'Новая')
    assert ds.current_index == 2 and ds.state is State.EDIT
    assert model.data(model.index(2, 0), Qt.BackgroundRole) is not None    # подсветка правки
    ds.post()
    assert ds.backend.get(3)['last_name'] == 'Новая'
    model.setData(model.index(0, 0), '')                                   # пусто — правка начата
    assert not model.setData(model.index(1, 0), 'x')                       # уход: проверка не прошла
    assert errors and 'обязательно' in errors[-1] and ds.current_index == 0


def test_table_follows_insert_delete_and_portions(qapp):
    ds = patients(5, fetch_size=2)
    model = DataSetTableModel(DataSource(ds))
    inserted, removed = [], []
    model.rowsInserted.connect(lambda parent, a, b: inserted.append((a, b, model.rowCount())))
    model.rowsRemoved.connect(lambda parent, a, b: removed.append((a, b)))
    ds.open()
    assert model.rowCount() == 2 and model.canFetchMore()
    model.fetchMore()
    assert model.rowCount() == 4 and inserted[-1] == (2, 3, 4)
    ds.append({'last_name': 'Новый'})
    assert model.rowCount() == 5 and model.data(model.index(4, 1)) == 'Новый'
    resets = []
    model.modelReset.connect(lambda: resets.append(1))
    ds.cancel()
    assert model.rowCount() == 4 and removed[-1] == (4, 4)
    assert resets == []                       # D3: удаление строки, а не перестройка таблицы
    ds.first(); ds.delete()
    assert model.rowCount() == 3 and model.data(model.index(0, 1)) == 'Фам2'
    ds.append({'last_name': 'Ещё'}); ds.post()
    assert resets == [] and model.rowCount() == 4


def test_table_switches_dataset(qapp):
    a, b = patients(2), patients(4)
    a.open(); b.open()
    source = DataSource(a)
    model = DataSetTableModel(source)
    assert model.rowCount() == 2
    source.dataset = b
    assert model.rowCount() == 4
    a.append({'last_name': 'x'})                                           # старый набор — не слышно
    assert model.rowCount() == 4


def test_table_view_selection_both_ways(qapp):
    ds = patients(4)
    model = DataSetTableModel(DataSource(ds))
    view = QTableView()
    bind_table_view(view, model)
    ds.open()
    ds.move_to(2)
    assert view.currentIndex().row() == 2
    view.setCurrentIndex(model.index(1, 1))
    assert ds.current_index == 1
    ds.set_value('last_name', '')                                          # проверка не пройдёт
    errors = []
    model.error_occurred.connect(errors.append)
    view.setCurrentIndex(model.index(3, 1))
    assert ds.current_index == 1 and view.currentIndex().row() == 1 and errors


# --------------------------------------------------------------------------- привязки

def test_bindings_show_and_write(qapp):
    ds = patients(3)
    source = DataSource(ds)
    edit, spin, check, date, memo = QLineEdit(), QSpinBox(), QCheckBox(), QDateEdit(), QPlainTextEdit()
    spin.setRange(0, 200)
    date.setMinimumDate(QDate(1900, 1, 1))
    for widget, name in ((edit, 'last_name'), (spin, 'age'), (check, 'active'), (date, 'birth'), (memo, 'note')):
        bind(widget, source, name)
    ds.open()
    assert (edit.text(), spin.value(), check.isChecked(), date.date().toPython(), memo.toPlainText()) == (
        'Фам1', 31, False, datetime.date(1990, 1, 1), 'заметка 1')
    ds.next()
    assert edit.text() == 'Фам2' and check.isChecked()
    edit.setText('')                                         # программная смена — не ввод
    edit.textEdited.emit('Иванов')
    spin.setValue(50)
    check.setChecked(False)
    date.setDate(QDate(2000, 5, 6))
    memo.setPlainText('новая заметка')
    assert ds.state is State.EDIT
    ds.post()
    assert ds.backend.get(2) == {'id': 2, 'last_name': 'Иванов', 'age': 50, 'active': False,
                                 'birth': datetime.date(2000, 5, 6), 'note': 'новая заметка'}
    ds.cancel()
    ds.set_value('age', 77)                                  # поле поменяли в коде — виджет видит
    assert spin.value() == 77


def test_binding_read_only_and_no_row(qapp):
    ds = patients(1)
    source = DataSource(ds)
    id_edit, name_edit = QLineEdit(), QLineEdit()
    bind(id_edit, source, 'id'); bind(name_edit, source, 'last_name')
    assert not name_edit.isEnabled()                         # набор закрыт — нет строки
    ds.open()
    assert id_edit.isReadOnly() and not name_edit.isReadOnly()
    ds.delete()
    assert not name_edit.isEnabled() and name_edit.text() == ''
    ro = patients(1, read_only=True)
    edit = QLineEdit()
    bind(edit, DataSource(ro), 'last_name')
    ro.open()
    assert edit.isReadOnly()


def test_binding_auto_edit_off_and_errors(qapp):
    ds = patients(1)
    source = DataSource(ds, auto_edit=False)
    messages = []
    edit = QLineEdit()
    bind(edit, source, 'last_name', on_error=messages.append)
    ds.open()
    assert edit.isReadOnly()                                 # без auto_edit — только в правке
    edit.textEdited.emit('x')
    assert ds.state is State.BROWSE and edit.text() == 'Фам1' and messages
    ds.edit()
    assert not edit.isReadOnly()
    edit.textEdited.emit('Петров')
    assert ds.value('last_name') == 'Петров'


def test_combo_and_label(qapp):
    backend = MemoryBackend([{'id': 1, 'doctor_id': 2, 'image': b''}],
                            fields=[FieldDef('id'), FieldDef('doctor_id'), FieldDef('image')])
    ds = DataSet(backend)
    source = DataSource(ds)
    combo, label, picture = QComboBox(), QLabel(), QLabel()
    bind(combo, source, 'doctor_id', choices=[(1, 'Иванов'), (2, 'Петрова')])
    bind(label, source, 'doctor_id')
    bind(picture, source, 'image', image=True)
    ds.open()
    assert combo.currentText() == 'Петрова' and label.text() == '2' and picture.pixmap().isNull()
    combo.setCurrentIndex(1)
    ds.post()
    assert backend.get(1)['doctor_id'] == 1 and label.text() == '1'
    combo.setCurrentIndex(0)                                  # «—» — пусто
    assert ds.value('doctor_id') is None


# --------------------------------------------------------------------------- навигатор

def enabled(nav):
    return {name: nav.button(name).isEnabled() for name in nav.buttons()}


def test_navigator_states_and_actions(qapp):
    ds = patients(3)
    nav = DataNavigator(DataSource(ds), confirm_delete=lambda: True, show_errors=False)
    assert not any(enabled(nav).values())                    # набор закрыт
    ds.open()
    state = enabled(nav)
    assert not state['first'] and state['next'] and state['insert'] and not state['post']
    nav.button('last').click()
    assert ds.current_index == 2 and not enabled(nav)['next']
    nav.button('edit').click()
    assert enabled(nav)['post'] and enabled(nav)['cancel'] and not enabled(nav)['edit']
    nav.button('cancel').click()
    nav.button('insert').click()
    assert ds.state is State.INSERT
    errors = []
    nav.error_occurred.connect(errors.append)
    nav.button('post').click()                               # фамилия обязательна
    assert errors and ds.state is State.INSERT
    nav.button('delete').click()                             # во время вставки — отмена
    assert ds.state is State.BROWSE and ds.row_count == 3
    nav.button('delete').click()
    assert ds.row_count == 2


def test_navigator_extra_action_and_read_only(qapp):
    ds = patients(2, read_only=True)
    flag = {'can': False, 'calls': 0}
    nav = DataNavigator(DataSource(ds), show_errors=False, buttons=['next', 'insert', 'delete'])
    nav.add_action('undo', '↶', 'Отменить', lambda: flag.__setitem__('calls', flag['calls'] + 1),
                   enabled=lambda: flag['can'])
    ds.open()
    assert enabled(nav) == {'next': True, 'insert': False, 'delete': False, 'undo': False}
    flag['can'] = True
    ds.next()
    assert enabled(nav)['undo']
    nav.button('undo').click()
    assert flag['calls'] == 1


def test_qt_with_master_detail(qapp):
    master = patients(2)
    visits = DataSet(MemoryBackend([{'id': 10, 'patient_id': 1}, {'id': 20, 'patient_id': 2}],
                                   fields=[FieldDef('id'), FieldDef('patient_id', references='patients')]))
    MasterDetailLink(master, visits)
    model = DataSetTableModel(DataSource(visits))
    master.open(); visits.open()
    assert model.rowCount() == 1 and model.data(model.index(0, 0)) == '10'
    master.next()
    assert model.data(model.index(0, 0)) == '20'
    master.append({'last_name': 'Новый'})
    assert model.rowCount() == 0 and not model.flags(model.index(0, 0)) & Qt.ItemIsEditable
