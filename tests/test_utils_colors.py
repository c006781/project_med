# tests/test_utils_colors.py

"""
Тесты app.utils.colors (2026-10-25, заход М5; до этого тестов не было).

Проверяют приоритет статусов ``get_color_for_entity_status`` и значения цветов.
"""

import pytest
from PySide6.QtGui import QColor

from app.utils.colors import RowStatusColor, get_color_for_entity_status


def test_colors_values() -> None:
    """Цвета строк — светлые оттенки (как в описании)."""
    assert RowStatusColor.NEW.name() == '#c8ffc8'
    assert RowStatusColor.MODIFIED.name() == '#ffffb4'
    assert RowStatusColor.DELETED.name() == '#ffc8c8'
    assert RowStatusColor.NORMAL.name() == '#ffffff'
    assert all(
        isinstance(c, QColor)
        for c in (RowStatusColor.NEW, RowStatusColor.MODIFIED, RowStatusColor.DELETED, RowStatusColor.NORMAL)
    )


@pytest.mark.parametrize('status', ['own', 'child', 'both'])
def test_modified_statuses(
    status : str,  # статус несохранённых изменений
) -> None:
    """Статусы черновика — «изменена» (жёлтый)."""
    assert get_color_for_entity_status(status) is RowStatusColor.MODIFIED


@pytest.mark.parametrize('status', [None, '', 'none', 'OWN', 'другое'])
def test_other_statuses_normal(
    status : object,  # статус, не означающий изменений
) -> None:
    """Прочие статусы (и None) — обычная строка (белый); регистр важен."""
    assert get_color_for_entity_status(status) is RowStatusColor.NORMAL


def test_priority_deleted_over_new_and_status() -> None:
    """Удалённая важнее новой и изменённой."""
    assert get_color_for_entity_status('own', is_new=True, is_deleted=True) is RowStatusColor.DELETED


def test_priority_new_over_status() -> None:
    """Новая важнее изменённой."""
    assert get_color_for_entity_status('both', is_new=True) is RowStatusColor.NEW


def test_returns_shared_objects() -> None:
    """Возвращаются общие объекты класса (а не копии) — описание предупреждает не менять их."""
    assert get_color_for_entity_status(None) is get_color_for_entity_status(None)
