# tests/test_dataset/test_actions.py

"""Массовые действия над отмеченными строками: механизм, встроенные действия, меню Qt."""

import contextlib
import datetime
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QCheckBox, QDateEdit, QLineEdit, QSpinBox  # noqa: E402

from app.utils.dataset import (  # noqa: E402
    Action, ActionSet, DataSet, DataSource, FieldDef, FieldKind, MemoryBackend,
)
from app.utils.dataset_qt import ActionsMenu, FieldValueDialog, widget_value  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def people(n=5, **kw):
    backend = MemoryBackend(
        [{'id': i, 'name': f'Имя{i}', 'next': None, 'age': 20 + i} for i in range(1, n + 1)],
        fields=[FieldDef('id', read_only=True), FieldDef('name', 'Имя', FieldKind.STRING, required=True),
                FieldDef('next', 'Следующий', FieldKind.DATE), FieldDef('age', 'Возраст', FieldKind.INTEGER),
                FieldDef('mark', '✓', FieldKind.BOOLEAN, local=True, default=False)])
    return DataSet(backend, **kw)


def test_builtin_actions_and_cursor_kept():
    ds = people(5, fetch_size=2)
    ds.open(); ds.next()
    actions = ActionSet()
    assert not actions.can_run('delete_marked', ds) and actions.can_run('mark_all', ds)
    assert actions.run('mark_all', ds) == 5 and ds.row_count == 5        # догрузил всё
    ds.set_local('mark', False, index=0); ds.set_local('mark', False, index=1)
    assert actions.run('set_field', ds, field='next', value=datetime.date(2026, 11, 1)) == 3
    assert [ds.backend.get(i)['next'] for i in (1, 3, 5)] == [None, datetime.date(2026, 11, 1)] * 1 + [datetime.date(2026, 11, 1)]
    assert ds.current_key == 2                                           # курсор — на месте
    assert actions.run('invert_marks', ds) == 2
    assert actions.selection(ds) == [1, 2]
    assert actions.run('delete_marked', ds) == 2
    assert ds.backend.get(1) is None and ds.backend.get(2) is None and ds.current_key == 3
    actions.run('mark_all', ds); actions.run('unmark_all', ds)
    assert actions.selection(ds) == []


def test_custom_action_order_replace_and_batch():
    calls, batches = [], []

    @contextlib.contextmanager
    def batch():
        batches.append('начало')
        yield
        batches.append('конец')

    ds = people(3)
    ds.open()
    actions = ActionSet(batch=batch)
    actions.add(Action('print', 'Печать', lambda d, keys, p: calls.append(list(keys)) or len(keys)),
                before='set_field')
    assert actions.names().index('print') == actions.names().index('set_field') - 1
    actions.add(Action('print', 'Печать 2', lambda d, keys, p: 'заменено'))
    assert actions.names().count('print') == 1 and actions.get('print').label == 'Печать 2'
    ds.set_local('mark', True, index=1)
    assert actions.run('print', ds) == 'заменено' and batches == ['начало', 'конец']
    with pytest.raises(KeyError, match='нет действия'):
        actions.get('nope')
    actions.remove('print')
    assert 'print' not in actions.names()


def test_unavailable_actions():
    ds = people(2, read_only=True)
    actions = ActionSet()
    assert not actions.can_run('mark_all', ds)                           # набор закрыт
    ds.open()
    ds.set_local('mark', True)                                           # отметка — и в «только чтение»
    assert actions.can_run('invert_marks', ds)
    assert not actions.can_run('delete_marked', ds)                      # менять нельзя
    with pytest.raises(PermissionError, match='недоступно'):
        actions.run('delete_marked', ds)
    no_marks = DataSet(MemoryBackend([{'id': 1}]))
    no_marks.open()
    assert ActionSet().selection(no_marks) == []
    only_mine = ActionSet(actions=[Action('x', 'X', lambda *a: 1, available=lambda d: False,
                                          needs_selection=False)])
    assert not only_mine.can_run('x', no_marks)


def test_actions_menu_enabling_and_trigger(qapp):
    ds = people(3)
    source = DataSource(ds)
    asked = []
    menu = ActionsMenu(source, ActionSet(), confirm=lambda parent, text: asked.append(text) or True,
                       ask_value=lambda parent, d: ('age', 99))
    errors, done = [], []
    menu.error_occurred.connect(errors.append)
    menu.done.connect(lambda name, result: done.append((name, result)))
    assert not menu.item('mark_all').isEnabled()                        # набор закрыт
    ds.open()
    assert menu.item('mark_all').isEnabled() and not menu.item('delete_marked').isEnabled()
    ds.set_local('mark', True, index=0); ds.set_local('mark', True, index=2)
    assert menu.item('delete_marked').isEnabled()
    assert menu.trigger('set_field') == 2 and ds.backend.get(3)['age'] == 99
    assert menu.trigger('delete_marked') == 2 and asked == ['Удалить отмеченные записи (2)?']
    assert done[-1] == ('delete_marked', 2) and ds.row_count == 1
    refusing = ActionsMenu(source, ActionSet(), confirm=lambda p, t: False)
    ds.set_local('mark', True)
    assert refusing.trigger('delete_marked') is None and ds.row_count == 1
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts[:3] == ['Отметить все', 'Снять все отметки', 'Обратить отметки']


def test_field_value_dialog(qapp):
    ds = people(1)
    ds.open()
    dialog = FieldValueDialog(ds)
    names = [dialog.fields.itemData(i) for i in range(dialog.fields.count())]
    assert names == ['name', 'next', 'age']                            # без ключа и отметки
    dialog.fields.setCurrentIndex(1)
    assert isinstance(dialog.value_widget, QDateEdit) and dialog.result_value() == ('next', None)
    dialog.fields.setCurrentIndex(2)
    dialog.value_widget.setValue(7)
    assert isinstance(dialog.value_widget, QSpinBox) and dialog.result_value() == ('age', 7)
    assert widget_value(QLineEdit('')) is None and widget_value(QLineEdit('а')) == 'а'
    check = QCheckBox(); check.setChecked(True)
    assert widget_value(check) is True
