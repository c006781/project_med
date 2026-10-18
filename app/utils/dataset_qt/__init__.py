# app/utils/dataset_qt/__init__.py

"""
Компоненты Qt для наборов данных (аналог data-aware компонентов RAD Studio).

Только PySide6 и ядро ``dataset``: ни БД, ни черновиков, ни кода приложения.

* ``DataSetTableModel`` + ``bind_table_view`` — таблица (``TDBGrid``);
* ``bind`` — поле ввода/флажок/дата/список/картинка (``TDBEdit``, ``TDBImage``…);
* ``DataNavigator`` — кнопки навигации и правки (``TDBNavigator``).

Пример:
    >>> source = DataSource(patients)
    >>> model = DataSetTableModel(source); bind_table_view(table_view, model)
    >>> bind(last_name_edit, source, 'last_name')
    >>> layout.addWidget(DataNavigator(source))
"""

from .bindings import Binding, bind
from .navigator import BUTTONS, DataNavigator
from .table_model import DEFAULT_STATUS_COLORS, DataSetTableModel, bind_table_view

__all__ = [
    'Binding', 'bind',
    'BUTTONS', 'DataNavigator',
    'DEFAULT_STATUS_COLORS', 'DataSetTableModel', 'bind_table_view',
]
